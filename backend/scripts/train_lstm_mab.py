"""
LSTM-MAB 模型训练脚本
Usage:
    python backend/scripts/train_lstm_mab.py --start-date 2023-01-01 --end-date 2026-03-29
"""

import argparse
import logging
import sys
import os
from datetime import date

# 添加项目根目录到路径
project_root = os.path.join(os.path.dirname(__file__), '../..')
sys.path.insert(0, os.path.abspath(project_root))

import numpy as np
import pandas as pd
from sqlalchemy import text

from data_warehouse.service.warehouse_service import WarehouseService
from backend.services.lstm_mab import LSTMMABModel

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def fetch_price_data(start_date: str, end_date: str):
    ws = WarehouseService()
    session = ws.get_session()
    try:
        query = text("""
            SELECT ts_code, trade_date, open, high, low, close, vol as volume
            FROM fact_daily_price_qfq
            WHERE trade_date BETWEEN :start_date AND :end_date
            ORDER BY ts_code, trade_date
        """)
        df = pd.read_sql(query, session.bind, params={'start_date': start_date, 'end_date': end_date})
        return df
    finally:
        session.close()


def train_model(start_date: str, end_date: str, factors=None):
    factors = factors or ['leader_position', 'technical']
    logger.info(f"开始训练 LSTM-MAB 模型，因子: {factors}")

    price_df = fetch_price_data(start_date, end_date)
    if len(price_df) < 100:
        logger.error("价格数据不足")
        return False

    model = LSTMMABModel(factor_names=factors)

    X_all, y_all = [], []
    valid_stocks = 0
    for ts_code, group in price_df.groupby('ts_code'):
        group = group.sort_values('trade_date')
        try:
            X, y = model.lstm.prepare_sequences(group, target_horizon=5)
            if len(X) > 0:
                X_all.append(X)
                y_all.append(y)
                valid_stocks += 1
        except Exception as e:
            logger.warning(f"生成 {ts_code} 序列失败: {e}")

    if not X_all:
        logger.error("没有生成任何有效训练样本")
        return False

    X_all = np.vstack(X_all)
    y_all = np.concatenate(y_all)
    logger.info(f"合并训练样本: {len(X_all)} 条，来自 {valid_stocks} 只股票")

    metrics = model.lstm.train_from_arrays(X_all, y_all)
    logger.info(f"训练完成: train_r2={metrics['train_r2']:.4f}, val_r2={metrics['val_r2']:.4f}, n_samples={metrics['n_samples']}")

    # 保存模型
    os.makedirs('backend/models', exist_ok=True)
    model_path = f"backend/models/lstm_mab_{date.today().strftime('%Y%m%d')}.pkl"
    model.save(model_path)
    logger.info(f"模型已保存: {model_path}")
    return True


def main():
    parser = argparse.ArgumentParser(description="Train LSTM-MAB model")
    parser.add_argument("--start-date", default="2023-01-01", help="训练开始日期")
    parser.add_argument("--end-date", default=date.today().isoformat(), help="训练结束日期")
    parser.add_argument("--factors", nargs="+", default=None, help="要使用的因子列表")
    args = parser.parse_args()

    success = train_model(args.start_date, args.end_date, args.factors)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
