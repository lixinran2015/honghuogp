-- 为 fact_stock_startup_candidate 表添加核心确认日期、辅助确认日期、风险排除日期字段
-- 
-- 业务逻辑说明：
-- 1. core_confirmed_date: 记录核心条件（突破90日高点、量能放大、均线多头排列）全部通过的日期
-- 2. assist_confirmed_date: 记录辅助条件（MACD金叉、KDJ金叉、大单净流入）至少满足1个的日期
-- 3. risk_passed_date: 记录风险排除条件全部通过的日期

-- 添加核心确认日期字段
ALTER TABLE fact_stock_startup_candidate 
ADD COLUMN IF NOT EXISTS core_confirmed_date DATE;

-- 添加辅助确认日期字段
ALTER TABLE fact_stock_startup_candidate 
ADD COLUMN IF NOT EXISTS assist_confirmed_date DATE;

-- 添加风险排除日期字段
ALTER TABLE fact_stock_startup_candidate 
ADD COLUMN IF NOT EXISTS risk_passed_date DATE;


-- 添加注释
COMMENT ON COLUMN fact_stock_startup_candidate.core_confirmed_date IS '核心确认日期（核心条件全部通过的日期）';
COMMENT ON COLUMN fact_stock_startup_candidate.assist_confirmed_date IS '辅助确认日期（辅助条件至少满足1个的日期）';
COMMENT ON COLUMN fact_stock_startup_candidate.risk_passed_date IS '风险排除日期（风险排除条件全部通过的日期）';

