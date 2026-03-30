"""
LSTM-MAB 每日反馈脚本

功能：
1. 获取前N日的预测记录
2. 计算实际收益
3. 反馈给MAB模型更新权重
4. 记录预测准确度
5. 触发模型保存

建议定时：每日收盘后 15:30 执行
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../..'))

import logging
import argparse
from datetime import datetime, date, timedelta
from typing import List, Dict, Optional
import pandas as pd
import numpy as np
from sqlalchemy import text

from data_warehouse.service.warehouse_service import WarehouseService
from backend.services.lstm_mab import LSTMMABModel

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 模型保存路径
MODEL_DIR = "backend/models/lstm_mab"
MODEL_FILENAME = "lstm_mab_latest.pkl"


class DailyFeedbackLoop:
    """每日反馈闭环"""

    def __init__(self):
        self.ws = WarehouseService()
        self.model: Optional[LSTMMABModel] = None
        self._load_model()

    def _load_model(self):
        """加载最新模型"""
        model_path = os.path.join(MODEL_DIR, MODEL_FILENAME)

        if os.path.exists(model_path):
            try:
                self.model = LSTMMABModel()
                self.model.load(model_path)
                logger.info(f"✅ 已加载模型: {model_path}")
            except Exception as e:
                logger.error(f"❌ 加载模型失败: {e}")
                self.model = None
        else:
            logger.warning(f"⚠️ 模型文件不存在: {model_path}")
            self.model = None

    def _save_model(self):
        """保存模型状态"""
        if self.model is None:
            logger.warning("⚠️ 模型未加载，无法保存")
            return

        os.makedirs(MODEL_DIR, exist_ok=True)
        model_path = os.path.join(MODEL_DIR, MODEL_FILENAME)

        try:
            self.model.save(model_path)
            logger.info(f"✅ 模型已保存: {model_path}")

            # 同时创建版本备份（按日期）
            version_path = os.path.join(
                MODEL_DIR,
                f"lstm_mab_{date.today().isoformat()}.pkl"
            )
            self.model.save(version_path)

            # 记录到数据库
            self._record_model_version(version_path)

        except Exception as e:
            logger.error(f"❌ 保存模型失败: {e}")

    def _record_model_version(self, model_path: str):
        """记录模型版本到数据库"""
        session = self.ws.get_session()
        try:
            stats = self.model.get_model_stats()
            version = f"v_{date.today().isoformat()}_{datetime.now().strftime('%H%M%S')}"

            query = text("""
                INSERT INTO lstm_mab_model_versions
                (version, trained_date, model_path, is_active, performance_summary)
                VALUES (:version, :date, :path, TRUE, :summary)
                ON CONFLICT (version) DO UPDATE SET
                    model_path = EXCLUDED.model_path,
                    is_active = TRUE,
                    performance_summary = EXCLUDED.performance_summary
            """)

            session.execute(query, {
                'version': version,
                'date': date.today(),
                'path': model_path,
                'summary': json.dumps(stats)
            })
            session.commit()
            logger.info(f"✅ 模型版本已记录: {version}")
        except Exception as e:
            logger.error(f"❌ 记录模型版本失败: {e}")
        finally:
            session.close()

    def get_pending_feedback(self, target_date: Optional[date] = None) -> pd.DataFrame:
        """
        获取待反馈的预测记录

        默认获取前5日的预测（因为预测周期是5天）
        """
        if target_date is None:
            target_date = date.today() - timedelta(days=5)

        session = self.ws.get_session()
        try:
            query = text("""
                SELECT p.id, p.prediction_date, p.ts_code, p.total_score,
                       p.grade, p.expected_return, p.factor_weights,
                       p.emotion_cycle
                FROM lstm_mab_predictions p
                LEFT JOIN lstm_mab_feedback f ON p.id = f.prediction_id
                WHERE p.prediction_date = :target_date
                AND f.id IS NULL
                ORDER BY p.ts_code
            """)

            df = pd.read_sql(query, session.bind, params={'target_date': target_date})
            logger.info(f"📊 找到 {len(df)} 条待反馈的预测记录 ({target_date})")
            return df

        finally:
            session.close()

    def calculate_actual_returns(self, predictions_df: pd.DataFrame, holding_days: int = 5) -> pd.DataFrame:
        """
        计算实际收益

        对于 prediction_date 的预测，计算 holding_days 后的实际收益
        """
        if predictions_df.empty:
            return predictions_df

        session = self.ws.get_session()
        try:
            results = []

            for _, row in predictions_df.iterrows():
                ts_code = row['ts_code']
                pred_date = row['prediction_date']

                # 计算目标日期（prediction_date + holding_days）
                target_date = pred_date + timedelta(days=holding_days)

                # 查询买入价（prediction_date的收盘价）
                buy_query = text("""
                    SELECT close FROM fact_daily_price_qfq
                    WHERE ts_code = :ts_code AND trade_date = :date
                    LIMIT 1
                """)

                buy_result = session.execute(buy_query, {
                    'ts_code': ts_code,
                    'date': pred_date
                }).fetchone()

                if not buy_result:
                    logger.warning(f"⚠️ 未找到 {ts_code} 在 {pred_date} 的价格数据")
                    continue

                buy_price = buy_result[0]

                # 查询卖出价（target_date的收盘价）
                sell_query = text("""
                    SELECT close FROM fact_daily_price_qfq
                    WHERE ts_code = :ts_code AND trade_date <= :date
                    ORDER BY trade_date DESC
                    LIMIT 1
                """)

                sell_result = session.execute(sell_query, {
                    'ts_code': ts_code,
                    'date': target_date
                }).fetchone()

                if not sell_result:
                    logger.warning(f"⚠️ 未找到 {ts_code} 在 {target_date} 附近的价格数据")
                    continue

                sell_price = sell_result[0]

                # 计算收益率
                actual_return = (sell_price - buy_price) / buy_price

                results.append({
                    'prediction_id': row['id'],
                    'ts_code': ts_code,
                    'prediction_date': pred_date,
                    'buy_price': buy_price,
                    'sell_price': sell_price,
                    'actual_return': actual_return,
                    'expected_return': row['expected_return'],
                    'factor_weights': row['factor_weights'],
                    'emotion_cycle': row['emotion_cycle']
                })

            return pd.DataFrame(results)

        finally:
            session.close()

    def update_model_with_feedback(self, feedback_df: pd.DataFrame):
        """
        使用反馈更新模型
        """
        if self.model is None:
            logger.error("❌ 模型未加载，无法更新")
            return

        if feedback_df.empty:
            logger.info("📭 没有反馈数据需要更新")
            return

        logger.info(f"🔄 开始更新模型，共 {len(feedback_df)} 条反馈")

        # 按因子更新MAB
        for factor_name in self.model.factor_names:
            # 计算该因子在每条反馈中的贡献
            # 简化处理：使用实际收益作为该因子的奖励
            for _, row in feedback_df.iterrows():
                actual_return = row['actual_return']

                # 更新MAB（内部会将收益率转换为奖励信号）
                self.model.update_factor_performance(factor_name, actual_return)

                logger.debug(f"更新因子 {factor_name}: 收益={actual_return:.4f}")

        logger.info("✅ 模型更新完成")

    def save_feedback_to_db(self, feedback_df: pd.DataFrame):
        """保存反馈到数据库"""
        if feedback_df.empty:
            return

        session = self.ws.get_session()
        try:
            for _, row in feedback_df.iterrows():
                # 计算预测准确度
                if pd.notna(row['expected_return']) and row['expected_return'] != 0:
                    accuracy = 1 - abs(row['actual_return'] - row['expected_return']) / abs(row['expected_return'])
                    accuracy = max(0, min(1, accuracy))  # 限制在0-1范围内
                else:
                    accuracy = None

                query = text("""
                    INSERT INTO lstm_mab_feedback
                    (prediction_id, ts_code, prediction_date, actual_return,
                     holding_days, feedback_date, prediction_accuracy)
                    VALUES (:pred_id, :ts_code, :pred_date, :actual_return,
                            :holding_days, :feedback_date, :accuracy)
                """)

                session.execute(query, {
                    'pred_id': row['prediction_id'],
                    'ts_code': row['ts_code'],
                    'pred_date': row['prediction_date'],
                    'actual_return': row['actual_return'],
                    'holding_days': 5,
                    'feedback_date': date.today(),
                    'accuracy': accuracy
                })

            session.commit()
            logger.info(f"✅ 已保存 {len(feedback_df)} 条反馈记录")

        except Exception as e:
            logger.error(f"❌ 保存反馈失败: {e}")
            session.rollback()
        finally:
            session.close()

    def update_performance_metrics(self, feedback_df: pd.DataFrame):
        """更新性能指标"""
        if feedback_df.empty:
            return

        session = self.ws.get_session()
        try:
            # 计算今日指标
            total = len(feedback_df)
            avg_actual = feedback_df['actual_return'].mean()

            # 预测方向命中率
            if 'expected_return' in feedback_df.columns:
                feedback_df['direction_match'] = (
                    (feedback_df['expected_return'] > 0) == (feedback_df['actual_return'] > 0)
                )
                hit_rate = feedback_df['direction_match'].mean()

                # 相关系数
                correlation = feedback_df['expected_return'].corr(feedback_df['actual_return'])

                # RMSE
                rmse = np.sqrt(((feedback_df['expected_return'] - feedback_df['actual_return']) ** 2).mean())
            else:
                hit_rate = None
                correlation = None
                rmse = None

            query = text("""
                INSERT INTO lstm_mab_performance
                (date, total_predictions, avg_actual_return, hit_rate,
                 prediction_correlation, rmse)
                VALUES (:date, :total, :avg_return, :hit_rate, :corr, :rmse)
                ON CONFLICT (date) DO UPDATE SET
                    total_predictions = EXCLUDED.total_predictions,
                    avg_actual_return = EXCLUDED.avg_actual_return,
                    hit_rate = EXCLUDED.hit_rate,
                    prediction_correlation = EXCLUDED.prediction_correlation,
                    rmse = EXCLUDED.rmse
            """)

            session.execute(query, {
                'date': date.today(),
                'total': total,
                'avg_return': avg_actual,
                'hit_rate': hit_rate,
                'corr': correlation,
                'rmse': rmse
            })
            session.commit()

            logger.info(f"📈 性能指标: 平均收益={avg_actual:.4f}, 命中率={hit_rate:.2% if hit_rate else 'N/A'}")

        except Exception as e:
            logger.error(f"❌ 更新性能指标失败: {e}")
        finally:
            session.close()

    def run(self, target_date: Optional[date] = None, dry_run: bool = False):
        """
        执行完整的反馈循环

        Args:
            target_date: 要处理的目标日期，默认为5天前
            dry_run: 如果为True，只打印不实际更新
        """
        logger.info("=" * 60)
        logger.info("🚀 LSTM-MAB 每日反馈循环开始")
        logger.info("=" * 60)

        if target_date is None:
            target_date = date.today() - timedelta(days=5)

        logger.info(f"📅 目标日期: {target_date}")

        # 1. 获取待反馈的预测
        predictions = self.get_pending_feedback(target_date)

        if predictions.empty:
            logger.info("📭 没有待反馈的预测")
            return

        # 2. 计算实际收益
        logger.info("💰 计算实际收益...")
        feedback = self.calculate_actual_returns(predictions)

        if feedback.empty:
            logger.warning("⚠️ 无法计算实际收益，可能缺少价格数据")
            return

        logger.info(f"📊 成功计算 {len(feedback)} 条实际收益")

        # 3. 更新模型
        if not dry_run and self.model:
            self.update_model_with_feedback(feedback)
            self._save_model()

        # 4. 保存反馈到数据库
        if not dry_run:
            self.save_feedback_to_db(feedback)
            self.update_performance_metrics(feedback)

        logger.info("=" * 60)
        logger.info("✅ 每日反馈循环完成")
        logger.info("=" * 60)


def main():
    parser = argparse.ArgumentParser(description='LSTM-MAB 每日反馈脚本')
    parser.add_argument('--date', type=str, help='目标日期 (YYYY-MM-DD)，默认为5天前')
    parser.add_argument('--dry-run', action='store_true', help='试运行，不实际更新')
    parser.add_argument('--init', action='store_true', help='初始化数据库表')

    args = parser.parse_args()

    if args.init:
        from init_evolution_tables import init_evolution_tables
        init_evolution_tables()
        return

    target_date = None
    if args.date:
        target_date = datetime.strptime(args.date, '%Y-%m-%d').date()

    loop = DailyFeedbackLoop()
    loop.run(target_date=target_date, dry_run=args.dry_run)


if __name__ == "__main__":
    import json  # 用于记录模型版本
    main()
