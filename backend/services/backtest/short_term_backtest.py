"""
短线龙头评分排序回测

轻量回测逻辑：
1. 遍历指定时间段内的每个交易日
2. 获取当日龙头池，并按 LSTM-MAB 评分排序
3. 取 Top N 股票
4. 计算这些股票未来 1/3/5 日的平均收益、胜率、最大回撤
"""

import logging
from datetime import date, timedelta
from typing import Dict, List, Optional
import numpy as np

from backend.services.leader_tracking.leader_tracking_pool_service import LeaderTrackingPoolService
from backend.services.lstm_mab import LSTMMABModel
from backend.services.leader_tracking.buy_signal_integration import get_buy_signals_for_pool
from backend.services.data.postgres_warehouse import PostgresWarehouse

logger = logging.getLogger(__name__)


class ScoreRankingBacktest:
    """基于 LSTM-MAB 评分排序的轻量回测"""

    def __init__(self, warehouse: Optional[PostgresWarehouse] = None):
        self.ws = None
        try:
            from data_warehouse.service.warehouse_service import WarehouseService
            self.ws = WarehouseService()
        except Exception as e:
            logger.warning(f"初始化 WarehouseService 失败: {e}")
        self.warehouse = warehouse or PostgresWarehouse()
        self.model: Optional[LSTMMABModel] = None
        self._init_model()

    def _init_model(self):
        """尝试加载 LSTM-MAB 模型"""
        try:
            import os
            model_path = os.environ.get(
                'LSTM_MAB_MODEL_PATH',
                'backend/models/lstm_mab/lstm_mab_latest.pkl'
            )
            if os.path.exists(model_path):
                self.model = LSTMMABModel()
                self.model.load(model_path)
                logger.info("回测：LSTM-MAB 模型加载成功")
        except Exception as e:
            logger.warning(f"回测：LSTM-MAB 模型加载失败: {e}")

    def _get_trading_dates(self, start_date: date, end_date: date) -> List[date]:
        """获取交易日列表（从 fact_daily_price_qfq 推断）"""
        if self.warehouse is None or not self.warehouse.warehouse_service:
            return []
        try:
            session = self.warehouse.warehouse_service.get_session()
            try:
                from sqlalchemy import func
                from data_warehouse.models import FactDailyPriceQfq
                rows = session.query(FactDailyPriceQfq.trade_date).filter(
                    FactDailyPriceQfq.trade_date >= start_date,
                    FactDailyPriceQfq.trade_date <= end_date,
                ).distinct().order_by(FactDailyPriceQfq.trade_date).all()
                return [r[0] for r in rows]
            finally:
                session.close()
        except Exception as e:
            logger.error(f"获取交易日列表失败: {e}")
            return []

    def _get_future_returns(
        self,
        ts_code: str,
        trade_date: date,
        horizons: List[int] = (1, 3, 5),
    ) -> Dict[int, float]:
        """获取某只股票在 trade_date 之后第 h 个交易日的收益率"""
        if not self.warehouse or not self.warehouse.warehouse_service:
            return {}

        max_h = max(horizons)
        try:
            session = self.warehouse.warehouse_service.get_session()
            try:
                from sqlalchemy import func
                from data_warehouse.models import FactDailyPriceQfq
                # 获取 trade_date 及之后的 max_h+5 天的价格（留足交易日裕量）
                rows = session.query(
                    FactDailyPriceQfq.trade_date,
                    FactDailyPriceQfq.close,
                ).filter(
                    FactDailyPriceQfq.ts_code == ts_code,
                    FactDailyPriceQfq.trade_date >= trade_date,
                ).order_by(FactDailyPriceQfq.trade_date).limit(max_h + 5).all()
            finally:
                session.close()
        except Exception as e:
            logger.warning(f"查询未来收益失败 {ts_code}: {e}")
            return {}

        if len(rows) < 2:
            return {}

        entry_price = float(rows[0][1]) if rows[0][1] else 0.0
        if entry_price <= 0:
            return {}

        result = {}
        for h in horizons:
            idx = h  # rows[0] 是 signal_date，rows[1] 是 day1
            if idx < len(rows) and rows[idx][1] is not None:
                result[h] = (float(rows[idx][1]) / entry_price) - 1.0
        return result

    def run(
        self,
        start_date: date,
        end_date: date,
        top_n: int = 10,
        min_score: int = 60,
        stage_filter: str = 'confirmed',
    ) -> Dict:
        """
        执行回测

        Returns:
            {
                'total_days': int,
                'avg_stocks_per_day': float,
                'horizons': {
                    1: {'avg_return': float, 'win_rate': float, 'max_drawdown': float},
                    3: {...},
                    5: {...},
                },
                'raw_results': [...]
            }
        """
        trading_dates = self._get_trading_dates(start_date, end_date)
        if not trading_dates:
            return {'success': False, 'error': '指定区间无交易日数据'}

        raw_results = []
        all_returns: Dict[int, List[float]] = {1: [], 3: [], 5: []}

        for td in trading_dates:
            try:
                svc = LeaderTrackingPoolService(self.ws)
                pool_result = svc.get_pool(
                    trade_date=td,
                    min_score=min_score,
                    stage_filter=stage_filter,
                    stable_window_id='rolling_30d_v2',
                )
                if not pool_result or not pool_result.get('success') or not pool_result.get('pool'):
                    continue

                pool = pool_result['pool']
                td_str = pool_result.get('trade_date', td.isoformat())

                # 评分
                scored = []
                if self.model:
                    from backend.api.leaders.leader_tracking import _get_auto_emotion_cycle
                    emotion_cycle = _get_auto_emotion_cycle(td_str, self.warehouse)
                    if emotion_cycle:
                        self.model.update_emotion_cycle(emotion_cycle)

                    buy_signals = get_buy_signals_for_pool(
                        pool, td_str, self.warehouse, emotion_cycle or '震荡期'
                    )

                    for stock in pool:
                        try:
                            from backend.api.leaders.leader_tracking import _calculate_factor_values, _get_price_history
                            fv = _calculate_factor_values(
                                stock, trade_date=td_str, warehouse=self.warehouse
                            )
                            ph = _get_price_history(stock['ts_code'], limit=40)
                            pred = self.model.predict(
                                ts_code=stock['ts_code'],
                                factor_values=fv,
                                price_history=ph,
                                trade_date=td_str,
                            )
                            stock['_score'] = pred.total_score
                            stock['_grade'] = pred.grade
                            stock['_buy_signal'] = buy_signals.get(stock['ts_code'])
                        except Exception:
                            stock['_score'] = 0
                            stock['_grade'] = 'D'
                else:
                    for stock in pool:
                        stock['_score'] = 0

                # 排序取 Top N
                pool.sort(key=lambda x: x.get('_score', 0), reverse=True)
                selected = pool[:top_n]

                day_result = {
                    'trade_date': td_str,
                    'selected': [],
                }
                for s in selected:
                    tc = s['ts_code']
                    rets = self._get_future_returns(tc, td, [1, 3, 5])
                    entry = {
                        'ts_code': tc,
                        'score': s.get('_score'),
                        'grade': s.get('_grade'),
                        'buy_signal': s.get('_buy_signal'),
                        'returns': rets,
                    }
                    day_result['selected'].append(entry)
                    for h, ret in rets.items():
                        all_returns[h].append(ret)

                raw_results.append(day_result)
            except Exception as e:
                logger.warning(f"回测 {td} 失败: {e}")
                continue

        # 汇总统计
        horizons = {}
        for h in [1, 3, 5]:
            arr = all_returns[h]
            if not arr:
                horizons[h] = {'avg_return': 0, 'win_rate': 0, 'max_drawdown': 0}
                continue
            arr = np.array(arr)
            equity = np.cumprod(1 + arr)
            peak = np.maximum.accumulate(equity)
            drawdown = (equity - peak) / peak
            horizons[h] = {
                'avg_return': round(float(np.mean(arr)), 4),
                'win_rate': round(float(np.mean(arr > 0)), 4),
                'max_drawdown': round(float(np.min(drawdown)), 4),
            }

        return {
            'success': True,
            'total_days': len(raw_results),
            'avg_stocks_per_day': round(
                sum(len(d['selected']) for d in raw_results) / max(len(raw_results), 1), 2
            ),
            'horizons': horizons,
            'raw_results': raw_results,
        }
