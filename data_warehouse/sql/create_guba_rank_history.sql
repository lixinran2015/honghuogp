-- 股吧人气榜历史趋势表
CREATE TABLE IF NOT EXISTS fact_guba_rank_history (
    id SERIAL PRIMARY KEY,
    ts_code VARCHAR(20) NOT NULL,
    trade_date DATE NOT NULL,
    rank_position INTEGER NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT idx_guba_history_code_date UNIQUE (ts_code, trade_date)
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_guba_history_code ON fact_guba_rank_history(ts_code);
CREATE INDEX IF NOT EXISTS idx_guba_history_date ON fact_guba_rank_history(trade_date);
CREATE INDEX IF NOT EXISTS idx_guba_history_code_date ON fact_guba_rank_history(ts_code, trade_date);

COMMENT ON TABLE fact_guba_rank_history IS '股吧人气榜历史趋势表';
COMMENT ON COLUMN fact_guba_rank_history.id IS '主键ID';
COMMENT ON COLUMN fact_guba_rank_history.ts_code IS '股票代码';
COMMENT ON COLUMN fact_guba_rank_history.trade_date IS '交易日期';
COMMENT ON COLUMN fact_guba_rank_history.rank_position IS '排名位置';
COMMENT ON COLUMN fact_guba_rank_history.created_at IS '创建时间';

