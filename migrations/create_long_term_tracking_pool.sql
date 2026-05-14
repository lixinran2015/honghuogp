-- 长线跟踪池表：记录通过四步精选等渠道入选的候选标的
CREATE TABLE IF NOT EXISTS fact_long_term_tracking_pool (
    id SERIAL PRIMARY KEY,
    ts_code VARCHAR(20) NOT NULL,
    name VARCHAR(50),
    industry VARCHAR(50),
    sector_type VARCHAR(50),
    track_date DATE NOT NULL,
    source VARCHAR(50) DEFAULT 'four_step_selection',
    status VARCHAR(20) DEFAULT 'watching',
    composite_score NUMERIC(6,2),
    darwin_score NUMERIC(6,2),
    financial_health NUMERIC(6,4),
    pe_ttm NUMERIC(10,4),
    pb NUMERIC(10,4),
    roe_ttm NUMERIC(10,4),
    amount NUMERIC(20,4),
    close_price NUMERIC(12,4),
    check_result JSON,
    drop_reason TEXT,
    note TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_lttracking_ts_code ON fact_long_term_tracking_pool(ts_code);
CREATE INDEX IF NOT EXISTS idx_lttracking_status ON fact_long_term_tracking_pool(status);
CREATE INDEX IF NOT EXISTS idx_lttracking_source ON fact_long_term_tracking_pool(source);
CREATE INDEX IF NOT EXISTS idx_lttracking_created ON fact_long_term_tracking_pool(created_at DESC);

COMMENT ON TABLE fact_long_term_tracking_pool IS '长线跟踪池：记录入选的候选标的及其检查结果';
COMMENT ON COLUMN fact_long_term_tracking_pool.source IS '来源：four_step_selection-四步精选, manual-手动添加';
COMMENT ON COLUMN fact_long_term_tracking_pool.status IS '状态：watching-观察中, promoted-已买入, dropped-已剔除';
COMMENT ON COLUMN fact_long_term_tracking_pool.check_result IS '最近一次检查结果JSON';
COMMENT ON COLUMN fact_long_term_tracking_pool.drop_reason IS '剔除理由：当状态为dropped时填写';
