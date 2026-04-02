"""
LSTM-MAB 每日反馈脚本

功能：
1. 获取前N日的预测记录
2. 计算实际收益
3. 反馈给MAB模型更新权重
4. 记录预测准确度
5. 触发模型保存

支持同步和异步两种模式

建议定时：每日收盘后 15:30 执行
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../..'))

import asyncio
import logging
import argparse
import json
from datetime import datetime, date, timedelta
from typing import List, Dict, Optional
from concurrent.futures import ThreadPoolExecutor
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

# 异步线程池
_executor = ThreadPoolExecutor(max_workers=4)


class DailyFeedbackLoop:
    """每日反馈闭环（支持同步和异步模式）"""

    def __init__(self):
        self.ws = WarehouseService()
        self.model: Optional[LSTMMABModel] = None
        self._model_lock = asyncio.Lock()
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
        计算实际收益（使用批量查询优化性能）

        对于 prediction_date 的预测，计算 holding_days 后的实际收益
        """
        if predictions_df.empty:
            return predictions_df

        session = self.ws.get_session()
        try:
            # 收集所有需要查询的日期和股票代码
            ts_codes = predictions_df['ts_code'].unique().tolist()
            pred_dates = predictions_df['prediction_date'].unique().tolist()
            max_target_date = max(pred_dates) + timedelta(days=holding_days + 5)  # 预留缓冲

            # 批量获取所有相关价格数据
            price_query = text("""
                SELECT ts_code, trade_date, close
                FROM fact_daily_price_qfq
                WHERE ts_code = ANY(:ts_codes)
                AND trade_date >= :min_date
                AND trade_date <= :max_date
            """)

            price_df = pd.read_sql(
                price_query,
                session.bind,
                params={
                    'ts_codes': ts_codes,
                    'min_date': min(pred_dates),
                    'max_date': max_target_date
                }
            )

            if price_df.empty:
                logger.warning("⚠️ 未找到任何价格数据")
                return pd.DataFrame()

            # 将价格数据转为字典格式便于查找
            price_dict = {}
            for _, row in price_df.iterrows():
                key = (row['ts_code'], row['trade_date'])
                price_dict[key] = row['close']

            results = []
            missing_count = 0

            for _, row in predictions_df.iterrows():
                ts_code = row['ts_code']
                pred_date = row['prediction_date']
                target_date = pred_date + timedelta(days=holding_days)

                # 查找买入价
                buy_price = price_dict.get((ts_code, pred_date))
                if buy_price is None:
                    missing_count += 1
                    if missing_count <= 5:  # 只记录前5个警告
                        logger.warning(f"⚠️ 未找到 {ts_code} 在 {pred_date} 的价格数据")
                    continue

                # 查找卖出价（找到目标日期或之前最近的交易日）
                sell_price = None
                for offset in range(5):  # 向后查找最多5天
                    check_date = target_date - timedelta(days=offset)
                    sell_price = price_dict.get((ts_code, check_date))
                    if sell_price is not None:
                        break

                if sell_price is None:
                    missing_count += 1
                    if missing_count <= 5:
                        logger.warning(f"⚠️ 未找到 {ts_code} 在 {target_date} 附近的价格数据")
                    continue

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

            if missing_count > 5:
                logger.warning(f"⚠️ 共有 {missing_count} 条记录缺少价格数据（仅显示前5条）")

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

    # ==================== 异步处理方法 ====================

    async def run_async(self, target_date: Optional[date] = None, dry_run: bool = False):
        """
        异步执行完整的反馈循环

        Args:
            target_date: 要处理的目标日期，默认为5天前
            dry_run: 如果为True，只打印不实际更新
        """
        logger.info("=" * 60)
        logger.info("🚀 LSTM-MAB 每日反馈循环开始 (异步模式)")
        logger.info("=" * 60)

        if target_date is None:
            target_date = date.today() - timedelta(days=5)

        logger.info(f"📅 目标日期: {target_date}")

        # 1. 异步获取待反馈的预测
        predictions = await self.get_pending_feedback_async(target_date)

        if predictions.empty:
            logger.info("📭 没有待反馈的预测")
            return

        # 2. 异步计算实际收益
        logger.info("💰 异步计算实际收益...")
        feedback = await self.calculate_actual_returns_async(predictions)

        if feedback.empty:
            logger.warning("⚠️ 无法计算实际收益，可能缺少价格数据")
            return

        logger.info(f"📊 成功计算 {len(feedback)} 条实际收益")

        # 3. 异步更新模型
        if not dry_run and self.model:
            await self.update_model_with_feedback_async(feedback)
            await self._save_model_async()

        # 4. 异步保存反馈到数据库
        if not dry_run:
            await asyncio.gather(
                self.save_feedback_to_db_async(feedback),
                self.update_performance_metrics_async(feedback),
                return_exceptions=True
            )

        logger.info("=" * 60)
        logger.info("✅ 每日反馈循环完成 (异步模式)")
        logger.info("=" * 60)

    async def get_pending_feedback_async(self, target_date: Optional[date] = None) -> pd.DataFrame:
        """异步获取待反馈的预测记录"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_executor, self.get_pending_feedback, target_date)

    async def calculate_actual_returns_async(
        self, predictions_df: pd.DataFrame, holding_days: int = 5
    ) -> pd.DataFrame:
        """异步计算实际收益"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            _executor, self.calculate_actual_returns, predictions_df, holding_days
        )

    async def update_model_with_feedback_async(self, feedback_df: pd.DataFrame):
        """异步使用反馈更新模型"""
        async with self._model_lock:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(_executor, self.update_model_with_feedback, feedback_df)

    async def save_feedback_to_db_async(self, feedback_df: pd.DataFrame):
        """异步保存反馈到数据库"""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(_executor, self.save_feedback_to_db, feedback_df)

    async def update_performance_metrics_async(self, feedback_df: pd.DataFrame):
        """异步更新性能指标"""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(_executor, self.update_performance_metrics, feedback_df)

    async def _save_model_async(self):
        """异步保存模型状态"""
        async with self._model_lock:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(_executor, self._save_model)

    async def run_batch_async(self, dates: List[date], dry_run: bool = False, max_concurrency: int = 3):
        """
        批量异步处理多个日期的反馈

        Args:
            dates: 要处理的日期列表
            dry_run: 如果为True，只打印不实际更新
            max_concurrency: 最大并发数，默认3
        """
        logger.info(f"🚀 批量异步处理 {len(dates)} 个日期的反馈")

        semaphore = asyncio.Semaphore(max_concurrency)

        async def process_with_limit(target_date: date):
            async with semaphore:
                await self.run_async(target_date=target_date, dry_run=dry_run)
                await asyncio.sleep(0.5)  # 小延迟避免数据库压力过大

        tasks = [process_with_limit(d) for d in dates]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 统计结果
        success_count = sum(1 for r in results if not isinstance(r, Exception))
        error_count = len(results) - success_count

        logger.info(f"✅ 批量反馈处理完成: 成功 {success_count} 个, 失败 {error_count} 个")
        return results


def main():
    parser = argparse.ArgumentParser(description='LSTM-MAB 每日反馈脚本')
    parser.add_argument('--date', type=str, help='目标日期 (YYYY-MM-DD)，默认为5天前')
    parser.add_argument('--dry-run', action='store_true', help='试运行，不实际更新')
    parser.add_argument('--init', action='store_true', help='初始化数据库表')
    parser.add_argument('--async', dest='use_async', action='store_true',
                        help='使用异步模式执行')
    parser.add_argument('--batch', type=str,
                        help='批量处理日期范围，格式: start_date,end_date (YYYY-MM-DD,YYYY-MM-DD)，需要配合 --async 使用')
    parser.add_argument('--max-concurrency', type=int, default=3,
                        help='异步批量处理时的最大并发数，默认3')

    args = parser.parse_args()

    if args.init:
        from init_evolution_tables import init_evolution_tables
        init_evolution_tables()
        return

    target_date = None
    if args.date:
        target_date = datetime.strptime(args.date, '%Y-%m-%d').date()

    loop = DailyFeedbackLoop()

    # 异步模式
    if args.use_async or args.batch:
        if args.batch:
            # 批量处理模式
            start_str, end_str = args.batch.split(',')
            start_date = datetime.strptime(start_str.strip(), '%Y-%m-%d').date()
            end_date = datetime.strptime(end_str.strip(), '%Y-%m-%d').date()

            # 生成日期列表（排除周末）
            dates = []
            current = start_date
            while current <= end_date:
                if current.weekday() < 5:  # 0-4 是周一到周五
                    dates.append(current)
                current += timedelta(days=1)

            asyncio.run(loop.run_batch_async(dates, dry_run=args.dry_run, max_concurrency=args.max_concurrency))
        else:
            # 单日期异步模式
            asyncio.run(loop.run_async(target_date=target_date, dry_run=args.dry_run))
    else:
        # 同步模式（默认）
        loop.run(target_date=target_date, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
