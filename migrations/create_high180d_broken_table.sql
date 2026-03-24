-- 180日新高「已破线」股票表
-- 从监控页一键清理破线后移入此表，站稳10日线后可移回监控

CREATE TABLE IF NOT EXISTS fact_high180d_broken (
    id BIGSERIAL PRIMARY KEY,
    ts_code VARCHAR(20) NOT NULL,
    broken_date DATE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uk_high180d_broken_ts UNIQUE (ts_code)
);

CREATE INDEX IF NOT EXISTS idx_high180d_broken_broken_date ON fact_high180d_broken(broken_date);
COMMENT ON TABLE fact_high180d_broken IS '180日新高已破线股票（跌破10日线后移出监控，站稳可移回）';
