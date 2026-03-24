-- 为股票启动候选表添加MA10相关字段

-- 添加最新价格字段
ALTER TABLE fact_stock_startup_candidate 
ADD COLUMN IF NOT EXISTS latest_price NUMERIC(10, 2);

-- 添加10日均线字段
ALTER TABLE fact_stock_startup_candidate 
ADD COLUMN IF NOT EXISTS ma10 NUMERIC(10, 2);

-- 添加是否破10日线字段
ALTER TABLE fact_stock_startup_candidate 
ADD COLUMN IF NOT EXISTS is_broken_ma10 BOOLEAN DEFAULT FALSE;

-- 添加最后检查日期字段
ALTER TABLE fact_stock_startup_candidate 
ADD COLUMN IF NOT EXISTS last_check_date DATE;

-- 创建索引（用于快速过滤破线股票）
CREATE INDEX IF NOT EXISTS idx_startup_candidate_broken_ma10 
ON fact_stock_startup_candidate(is_broken_ma10, trade_date DESC);

-- 添加注释
COMMENT ON COLUMN fact_stock_startup_candidate.latest_price IS '最新价格';
COMMENT ON COLUMN fact_stock_startup_candidate.ma10 IS '10日均线';
COMMENT ON COLUMN fact_stock_startup_candidate.is_broken_ma10 IS '是否破10日线';
COMMENT ON COLUMN fact_stock_startup_candidate.last_check_date IS '最后检查日期';

