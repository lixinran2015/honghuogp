-- 为股票启动候选表添加退出相关字段

-- 添加退出相关字段
ALTER TABLE fact_stock_startup_candidate 
ADD COLUMN IF NOT EXISTS is_exited BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS exit_date DATE,
ADD COLUMN IF NOT EXISTS exit_reason VARCHAR(100);

-- 创建索引优化查询性能
CREATE INDEX IF NOT EXISTS idx_startup_candidate_exited 
ON fact_stock_startup_candidate(is_exited, exit_date DESC);

-- 添加注释
COMMENT ON COLUMN fact_stock_startup_candidate.is_exited IS '是否已退出启动';
COMMENT ON COLUMN fact_stock_startup_candidate.exit_date IS '退出日期';
COMMENT ON COLUMN fact_stock_startup_candidate.exit_reason IS '退出原因';
