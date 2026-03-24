-- 为启动候选表添加两阶段筛选字段

-- 添加阶段字段
ALTER TABLE fact_stock_startup_candidate 
ADD COLUMN IF NOT EXISTS stage VARCHAR(20) DEFAULT 'golden_cross';

-- 添加金叉日期字段
ALTER TABLE fact_stock_startup_candidate 
ADD COLUMN IF NOT EXISTS golden_cross_date DATE;

-- 添加距金叉天数字段
ALTER TABLE fact_stock_startup_candidate 
ADD COLUMN IF NOT EXISTS days_since_cross INTEGER;

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_startup_candidate_stage 
ON fact_stock_startup_candidate(stage, trade_date DESC);

CREATE INDEX IF NOT EXISTS idx_startup_candidate_golden_cross_date 
ON fact_stock_startup_candidate(golden_cross_date DESC);

-- 添加注释
COMMENT ON COLUMN fact_stock_startup_candidate.stage IS '阶段：golden_cross(金叉候选) / confirmed(启动确认)';
COMMENT ON COLUMN fact_stock_startup_candidate.golden_cross_date IS '5日金叉10日发生的日期';
COMMENT ON COLUMN fact_stock_startup_candidate.days_since_cross IS '距离金叉发生的天数';

