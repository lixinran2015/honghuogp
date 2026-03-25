-- 为 fact_stock_startup_candidate 表添加 name 字段
-- 执行时间: 2026-03-25

-- 添加股票名称字段
ALTER TABLE fact_stock_startup_candidate
    ADD COLUMN IF NOT EXISTS name VARCHAR(128);

-- 添加注释
COMMENT ON COLUMN fact_stock_startup_candidate.name IS '股票名称';

-- 创建索引优化查询
CREATE INDEX IF NOT EXISTS idx_startup_candidate_name
    ON fact_stock_startup_candidate(name)
    WHERE name IS NOT NULL;
