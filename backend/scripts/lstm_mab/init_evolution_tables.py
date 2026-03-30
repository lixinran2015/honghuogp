"""
LSTM-MAB 模型进化系统数据库表初始化
创建预测记录、反馈、模型版本等表
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from sqlalchemy import create_engine, text
from data_warehouse.config import DATABASE_URL

def init_evolution_tables():
    """初始化模型进化相关表"""

    engine = create_engine(DATABASE_URL)

    with engine.connect() as conn:
        # 1. 预测记录表 - 记录每次预测
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS lstm_mab_predictions (
                id SERIAL PRIMARY KEY,
                prediction_date DATE NOT NULL,
                ts_code VARCHAR(20) NOT NULL,
                total_score FLOAT NOT NULL,
                grade VARCHAR(5) NOT NULL,
                expected_return FLOAT,
                confidence FLOAT,
                factor_scores JSONB,
                factor_weights JSONB,
                emotion_cycle VARCHAR(20),
                model_version VARCHAR(50),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """))

        # 2. 预测反馈表 - 记录实际收益反馈
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS lstm_mab_feedback (
                id SERIAL PRIMARY KEY,
                prediction_id INTEGER REFERENCES lstm_mab_predictions(id),
                ts_code VARCHAR(20) NOT NULL,
                prediction_date DATE NOT NULL,
                actual_return FLOAT NOT NULL,
                holding_days INTEGER DEFAULT 5,
                feedback_date DATE NOT NULL,
                prediction_accuracy FLOAT,  -- 预测准确度 (1 - |预测-实际|/|实际|)
                factor_contributions JSONB, -- 各因子实际贡献
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """))

        # 3. 模型版本表 - 记录模型版本历史
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS lstm_mab_model_versions (
                id SERIAL PRIMARY KEY,
                version VARCHAR(50) NOT NULL UNIQUE,
                trained_date DATE NOT NULL,
                train_r2 FLOAT,
                val_r2 FLOAT,
                n_samples INTEGER,
                model_path VARCHAR(500),
                is_active BOOLEAN DEFAULT FALSE,
                performance_summary JSONB,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """))

        # 4. 模型性能监控表 - 每日性能指标
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS lstm_mab_performance (
                id SERIAL PRIMARY KEY,
                date DATE NOT NULL UNIQUE,
                total_predictions INTEGER DEFAULT 0,
                avg_prediction_score FLOAT,
                avg_actual_return FLOAT,
                prediction_correlation FLOAT,  -- 预测与实际的相关系数
                hit_rate FLOAT,  -- 命中率 (预测方向正确的比例)
                rmse FLOAT,  -- 均方根误差
                mab_learning_stats JSONB,  -- MAB学习状态
                emotion_cycle_stats JSONB,  -- 各情绪周期表现
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """))

        # 5. 因子性能追踪表
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS lstm_mab_factor_performance (
                id SERIAL PRIMARY KEY,
                date DATE NOT NULL,
                factor_name VARCHAR(50) NOT NULL,
                avg_weight FLOAT,
                avg_return_contribution FLOAT,
                hit_rate FLOAT,
                sharpe_ratio FLOAT,
                cumulative_reward FLOAT DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(date, factor_name)
            );
        """))

        # 创建索引
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_predictions_date ON lstm_mab_predictions(prediction_date);
            CREATE INDEX IF NOT EXISTS idx_predictions_ts_code ON lstm_mab_predictions(ts_code);
            CREATE INDEX IF NOT EXISTS idx_feedback_date ON lstm_mab_feedback(feedback_date);
            CREATE INDEX IF NOT EXISTS idx_performance_date ON lstm_mab_performance(date);
            CREATE INDEX IF NOT EXISTS idx_factor_perf_date ON lstm_mab_factor_performance(date);
        """))

        conn.commit()
        print("✅ LSTM-MAB 进化系统数据库表初始化完成")

        # 显示创建的表
        result = conn.execute(text("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_name LIKE 'lstm_mab%'
            ORDER BY table_name;
        """))

        print("\n📊 已创建的表:")
        for row in result:
            print(f"  - {row[0]}")

if __name__ == "__main__":
    init_evolution_tables()
