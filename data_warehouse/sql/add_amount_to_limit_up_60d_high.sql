-- 为 fact_limit_up_today_60d_high 表添加成交额字段
-- 执行时间：2025-12-09

-- 添加成交额字段
ALTER TABLE fact_limit_up_today_60d_high 
ADD COLUMN IF NOT EXISTS amount NUMERIC(20, 2);

-- 添加字段注释
COMMENT ON COLUMN fact_limit_up_today_60d_high.amount IS '成交额（元）';
