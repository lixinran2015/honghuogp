"""
统一短线评分引擎

将 LSTM-MAB 评分、买点识别、情绪周期定位、仓位建议整合为一致的评分接口。
"""

from __future__ import annotations

import logging
import os
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from backend.services.lstm_mab import LSTMMABModel, get_evolution_service
from backend.services.leader_tracking.buy_signal_integration import get_buy_signals_for_pool
from backend.services.leader_tracking import detect_emotion_cycle
from backend.services.leader_tracking.leader_retreat_at_date import compute_retreat_stats_at_end_date
from backend.services.data.postgres_warehouse import PostgresWarehouse

logger = logging.getLogger(__name__)


class UnifiedShortTermScorer:
    """
    统一短线龙头评分引擎

    职责：
    1. 自动识别情绪周期并更新 LSTM-MAB 模型
    2. 计算 4 因子得分并输出总分/评级
    3. 批量识别买点信号
    4. 生成仓位与风控建议
    """

    def __init__(self, warehouse: Optional[PostgresWarehouse] = None):
        self.warehouse = warehouse or self._init_warehouse()
        self.model: Optional[LSTMMABModel] = None
        self._init_model()

    # ------------------------------------------------------------------
    # 内部工具方法
    # ------------------------------------------------------------------
    @staticmethod
    def _init_warehouse() -> Optional[PostgresWarehouse]:
        try:
            return PostgresWarehouse()
        except Exception as e:
            logger.warning(f"初始化数据仓库失败: {e}")
            return None

    def _init_model(self) -> None:
        model_path = os.environ.get(
            "LSTM_MAB_MODEL_PATH",
            "backend/models/lstm_mab/lstm_mab_latest.pkl",
        )
        if not os.path.exists(model_path):
            logger.warning(f"LSTM-MAB 模型文件不存在: {model_path}")
            return
        try:
            self.model = LSTMMABModel()
            self.model.load(model_path)
            logger.info("统一评分引擎：LSTM-MAB 模型加载成功")
        except Exception as e:
            logger.error(f"统一评分引擎加载模型失败: {e}", exc_info=True)
            self.model = None

    def _get_price_history(self, ts_code: str, limit: int = 40) -> Optional[Any]:
        """获取股票历史价格数据（DataFrame）"""
        if self.warehouse is None:
            return None
        try:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=limit * 2)
            df = self.warehouse.load_history_kline_batch(
                codes=[ts_code],
                start_date=start_date.strftime("%Y-%m-%d"),
                end_date=end_date.strftime("%Y-%m-%d"),
            )
            if df is None or df.empty:
                return None
            required_cols = ["open", "high", "low", "close", "volume"]
            for col in required_cols:
                if col not in df.columns:
                    logger.warning(f"K线数据缺少必要列: {col}")
                    return None
            df = df.sort_values("trade_date").tail(limit).reset_index(drop=True)
            return df[required_cols]
        except Exception as e:
            logger.warning(f"获取 {ts_code} 历史价格失败: {e}")
            return None

    def _get_money_flow_factor(self, ts_code: str, trade_date: Optional[str]) -> float:
        if self.warehouse is None or not trade_date:
            return 50.0
        try:
            session = self.warehouse.warehouse_service.get_session()
            try:
                from data_warehouse.models import FactMoneyFlow
                from sqlalchemy import desc

                record = (
                    session.query(FactMoneyFlow)
                    .filter(
                        FactMoneyFlow.ts_code == ts_code,
                        FactMoneyFlow.trade_date <= trade_date,
                    )
                    .order_by(desc(FactMoneyFlow.trade_date))
                    .first()
                )
                if record and record.main_net_inflow_rate is not None:
                    rate = float(record.main_net_inflow_rate)
                    if rate >= 10:
                        return 100.0
                    elif rate >= 5:
                        return 80.0
                    elif rate >= 2:
                        return 65.0
                    elif rate >= 0:
                        return 50.0
                    elif rate >= -2:
                        return 35.0
                    elif rate >= -5:
                        return 20.0
                    else:
                        return 10.0
            finally:
                session.close()
        except Exception as e:
            logger.warning(f"获取 {ts_code} 资金流向失败: {e}")
        return 50.0

    def _get_sentiment_factor(self, stock_data: Dict[str, Any], trade_date: Optional[str]) -> float:
        if self.warehouse is None or not trade_date:
            return 50.0
        score = 0.0
        try:
            session = self.warehouse.warehouse_service.get_session()
            try:
                from data_warehouse.models import FactSectorHeatSnapshot

                sectors = stock_data.get("sectors") or []
                max_heat = 0.0
                for sector in sectors:
                    rec = (
                        session.query(FactSectorHeatSnapshot)
                        .filter(
                            FactSectorHeatSnapshot.window_id == "rolling_30d_v2",
                            FactSectorHeatSnapshot.sector_name == sector,
                        )
                        .first()
                    )
                    if rec and rec.heat_score is not None:
                        max_heat = max(max_heat, float(rec.heat_score))
                if max_heat >= 25:
                    score += 70
                elif max_heat >= 20:
                    score += 60
                elif max_heat >= 15:
                    score += 50
                elif max_heat >= 10:
                    score += 40
                else:
                    score += 30
            finally:
                session.close()
        except Exception as e:
            logger.warning(f"获取 {stock_data.get('ts_code')} 板块热度失败: {e}")
            score += 30

        if stock_data.get("is_space"):
            score += 10
        if stock_data.get("is_new"):
            score += 5
        cl = stock_data.get("continuous_limit") or 0
        if cl >= 5:
            score += 10
        elif cl >= 3:
            score += 5
        elif cl >= 2:
            score += 2

        return max(0.0, min(100.0, score))

    def get_emotion_cycle(self, trade_date: Optional[str]) -> str:
        """基于 FactMarketEmotionDaily 自动识别情绪周期"""
        if not trade_date:
            return "震荡期"
        try:
            from datetime import date as dt_date

            d = dt_date.fromisoformat(trade_date) if isinstance(trade_date, str) else trade_date
            return detect_emotion_cycle(d, self.warehouse)
        except Exception as e:
            logger.warning(f"自动识别情绪周期失败: {e}")
            return "震荡期"

    def calculate_factor_values(
        self, stock_data: Dict[str, Any], trade_date: Optional[str]
    ) -> Dict[str, float]:
        """计算 LSTM-MAB 所需的 4 因子值"""
        factors = {}

        # 龙头地位因子
        leader_score = 0.0
        continuous_limit = stock_data.get("continuous_limit") or 0
        if continuous_limit >= 5:
            leader_score += 40
        elif continuous_limit >= 3:
            leader_score += 30
        elif continuous_limit >= 2:
            leader_score += 20
        elif continuous_limit >= 1:
            leader_score += 10

        is_space = stock_data.get("is_space", False)
        is_new = stock_data.get("is_new", False)
        if is_space and is_new:
            leader_score += 30
        elif is_space:
            leader_score += 25
        elif is_new:
            leader_score += 20

        sectors = stock_data.get("sectors") or []
        sector_count = len(sectors)
        if sector_count >= 3:
            leader_score += 20
        elif sector_count >= 2:
            leader_score += 15
        elif sector_count >= 1:
            leader_score += 10

        first_date = stock_data.get("first_space_date") or stock_data.get("first_new_date")
        if first_date:
            leader_score += 10

        factors["leader_position"] = min(100.0, leader_score)

        # 技术形态因子
        technical_score = 50.0
        stats = stock_data.get("stats", {})
        pct20d = stats.get("pct20d")
        if pct20d is not None:
            if pct20d >= 50:
                technical_score += 20
            elif pct20d >= 30:
                technical_score += 15
            elif pct20d >= 20:
                technical_score += 10
            elif pct20d >= 10:
                technical_score += 5
            elif pct20d < -10:
                technical_score -= 15
            elif pct20d < -5:
                technical_score -= 10

        retreat_label = stats.get("retreat_label", "")
        if retreat_label == "强势":
            technical_score += 15
        elif retreat_label == "震荡":
            technical_score += 5
        elif retreat_label == "退潮风险":
            technical_score -= 20

        position_tag = stats.get("positionTag", "")
        if "强于20日线" in position_tag:
            technical_score += 10
        elif "跌破20日线" in position_tag:
            technical_score -= 15

        factors["technical"] = max(0.0, min(100.0, technical_score))

        # 资金流向因子
        factors["money_flow"] = self._get_money_flow_factor(
            stock_data.get("ts_code"), trade_date
        )

        # 情绪热度因子
        factors["sentiment"] = self._get_sentiment_factor(stock_data, trade_date)

        return factors

    # ------------------------------------------------------------------
    # 评分与建议
    # ------------------------------------------------------------------
    def score_stock(
        self, stock_data: Dict[str, Any], trade_date: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        对单只股票进行完整评分（含 LSTM-MAB + 建议）。

        Returns:
            结构化评分结果字典，兼容 v2 设计中的接口约定。
        """
        if self.model is None:
            return {
                "ts_code": stock_data.get("ts_code"),
                "name": stock_data.get("name"),
                "total_score": 0.0,
                "grade": "D",
                "breakdown": {},
                "signals": {},
                "recommendation": {},
                "model_available": False,
                "error": "LSTM-MAB 模型未加载",
            }

        factor_values = self.calculate_factor_values(stock_data, trade_date)
        price_history = self._get_price_history(stock_data.get("ts_code"), limit=40)

        prediction = self.model.predict(
            ts_code=stock_data.get("ts_code"),
            factor_values=factor_values,
            price_history=price_history,
            trade_date=trade_date,
        )

        # 记录到模型进化服务（预测历史）
        prediction_id = None
        try:
            evo_service = get_evolution_service()
            emotion_cycle = self.model.mab.current_emotion
            prediction_id = evo_service.record_prediction(
                ts_code=stock_data.get("ts_code"),
                result=prediction,
                factor_values=factor_values,
                emotion_cycle=emotion_cycle,
            )
        except Exception as e:
            logger.warning(f"记录预测历史失败: {e}")

        total_score = round(prediction.total_score, 2)
        grade = prediction.grade
        breakdown = {
            "leader_position": prediction.factor_scores.get("leader_position", 0),
            "technical": prediction.factor_scores.get("technical", 0),
            "money_flow": prediction.factor_scores.get("money_flow", 0),
            "sentiment": prediction.factor_scores.get("sentiment", 0),
        }

        recommendation = self._generate_recommendation(total_score, grade)

        return {
            "ts_code": stock_data.get("ts_code"),
            "name": stock_data.get("name"),
            "total_score": total_score,
            "grade": grade,
            "breakdown": breakdown,
            "expected_return": round(prediction.expected_return * 100, 2),
            "confidence": round(prediction.confidence * 100, 1),
            "factor_weights": prediction.factor_weights,
            "factor_values": factor_values,
            "prediction_id": prediction_id,
            "signals": {},  # 由 batch_score 填充买点后回填
            "recommendation": recommendation,
            "model_available": True,
        }

    def batch_score(
        self, pool: List[Dict[str, Any]], trade_date: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        对股票池进行批量评分，并统一附加买点信号。
        注意：有退潮风险的股票会被过滤，不参与评分。

        Returns:
            评分后的股票字典列表（已按 total_score 降序）。
        """
        if self.model is None:
            logger.warning("统一评分引擎：模型未加载，返回原始数据")
            return pool

        # 自动识别情绪周期
        emotion_cycle = self.get_emotion_cycle(trade_date)
        if emotion_cycle:
            self.model.update_emotion_cycle(emotion_cycle)

        # 过滤有退潮风险的股票
        filtered_pool = []
        if self.warehouse is not None and trade_date:
            try:
                session = self.warehouse.warehouse_service.get_session()
                try:
                    td = date.fromisoformat(trade_date) if isinstance(trade_date, str) else trade_date
                    for stock in pool:
                        ts_code = stock.get("ts_code")
                        if not ts_code:
                            continue
                        # 计算退潮状态
                        stats = compute_retreat_stats_at_end_date(session, ts_code, td)
                        if stats and stats.get("retreat_label") == "退潮风险":
                            logger.info(f"AI评分：跳过退潮风险股票 {ts_code}")
                            continue
                        # 将stats添加到stock中，避免重复计算
                        if stats:
                            stock["stats"] = stats
                        filtered_pool.append(stock)
                finally:
                    session.close()
            except Exception as e:
                logger.warning(f"过滤退潮风险股票失败: {e}")
                filtered_pool = pool
        else:
            filtered_pool = pool

        if not filtered_pool:
            logger.info("AI评分：过滤后没有符合条件的股票")
            return []

        scored = []
        for stock in filtered_pool:
            try:
                score_result = self.score_stock(stock, trade_date)
                merged = {
                    **stock,
                    "lstm_mab_score": {
                        "total_score": score_result["total_score"],
                        "grade": score_result["grade"],
                        "expected_return": score_result.get("expected_return"),
                        "confidence": score_result.get("confidence"),
                        "factor_scores": score_result["breakdown"],
                        "factor_weights": score_result.get("factor_weights"),
                        "factor_values": score_result.get("factor_values"),
                        "prediction_id": score_result.get("prediction_id"),
                        "recommendation": score_result.get("recommendation"),
                    },
                }
                scored.append(merged)
            except Exception as e:
                logger.error(f"评分失败 {stock.get('ts_code')}: {e}", exc_info=True)
                scored.append({
                    **stock,
                    "lstm_mab_score": {
                        "total_score": 0,
                        "grade": "D",
                        "expected_return": 0,
                        "confidence": 0,
                        "error": str(e),
                    },
                })

        # 批量买点识别
        try:
            buy_signals = get_buy_signals_for_pool(
                scored,
                trade_date_str=trade_date,
                warehouse=self.warehouse,
                emotion_cycle=emotion_cycle,
            )
            for item in scored:
                signal = buy_signals.get(item.get("ts_code"))
                item["buy_signal"] = signal
                if item.get("lstm_mab_score") and signal:
                    item["lstm_mab_score"]["buy_signal"] = signal
        except Exception as e:
            logger.warning(f"批量买点识别失败（不影响主逻辑）: {e}")

        scored.sort(
            key=lambda x: x.get("lstm_mab_score", {}).get("total_score", 0),
            reverse=True,
        )
        return scored

    def get_top_picks(
        self,
        pool: List[Dict[str, Any]],
        trade_date: Optional[str] = None,
        min_grade: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """获取评分最高的精选股票"""
        scored = self.batch_score(pool, trade_date)
        if min_grade:
            grade_order = {"S": 4, "A": 3, "B": 2, "C": 1, "D": 0}
            threshold = grade_order.get(min_grade, 0)
            scored = [
                s
                for s in scored
                if grade_order.get(s.get("lstm_mab_score", {}).get("grade", "D"), 0)
                >= threshold
            ]
        if limit:
            scored = scored[:limit]
        return scored

    # ------------------------------------------------------------------
    # 静态建议生成
    # ------------------------------------------------------------------
    @staticmethod
    def _generate_recommendation(total_score: float, grade: str) -> Dict[str, Any]:
        """基于得分和等级生成仓位与操作建议"""
        if grade == "S":
            return {
                "action": "强烈推荐",
                "position_size": 20,
                "stop_loss_pct": -3,
                "take_profit_1_pct": 10,
                "take_profit_2_pct": 15,
            }
        elif grade == "A":
            return {
                "action": "重点关注",
                "position_size": 15,
                "stop_loss_pct": -3,
                "take_profit_1_pct": 8,
                "take_profit_2_pct": 12,
            }
        elif grade == "B":
            return {
                "action": "适当关注",
                "position_size": 10,
                "stop_loss_pct": -3,
                "take_profit_1_pct": 6,
                "take_profit_2_pct": 10,
            }
        elif grade == "C":
            return {
                "action": "观望",
                "position_size": 5,
                "stop_loss_pct": -3,
                "take_profit_1_pct": 5,
                "take_profit_2_pct": 8,
            }
        else:
            return {
                "action": "回避",
                "position_size": 0,
                "stop_loss_pct": -3,
                "take_profit_1_pct": 0,
                "take_profit_2_pct": 0,
            }
