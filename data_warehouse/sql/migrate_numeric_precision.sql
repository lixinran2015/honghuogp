-- 修改财务数据字段精度从 NUMERIC(8,4) 到 NUMERIC(12,4)
-- 执行时间: 2026-03-30

-- ============================================
-- 1. raw_fundamental 表
-- ============================================
ALTER TABLE raw_fundamental ALTER COLUMN roe TYPE NUMERIC(12,4);
ALTER TABLE raw_fundamental ALTER COLUMN net_margin TYPE NUMERIC(12,4);
ALTER TABLE raw_fundamental ALTER COLUMN gross_margin TYPE NUMERIC(12,4);
ALTER TABLE raw_fundamental ALTER COLUMN profit_volatility TYPE NUMERIC(12,4);

-- ============================================
-- 2. fact_fundamental 表
-- ============================================
ALTER TABLE fact_fundamental ALTER COLUMN roe TYPE NUMERIC(12,4);
ALTER TABLE fact_fundamental ALTER COLUMN net_margin TYPE NUMERIC(12,4);
ALTER TABLE fact_fundamental ALTER COLUMN gross_margin TYPE NUMERIC(12,4);
ALTER TABLE fact_fundamental ALTER COLUMN profit_volatility TYPE NUMERIC(12,4);

-- ============================================
-- 3. fact_daily_fundamental 表
-- ============================================
-- ROE 字段
ALTER TABLE fact_daily_fundamental ALTER COLUMN roe_ttm TYPE NUMERIC(12,4);
ALTER TABLE fact_daily_fundamental ALTER COLUMN roe_lyr TYPE NUMERIC(12,4);
ALTER TABLE fact_daily_fundamental ALTER COLUMN roe_mrq TYPE NUMERIC(12,4);
ALTER TABLE fact_daily_fundamental ALTER COLUMN roe_q4 TYPE NUMERIC(12,4);
ALTER TABLE fact_daily_fundamental ALTER COLUMN roe_q2 TYPE NUMERIC(12,4);
ALTER TABLE fact_daily_fundamental ALTER COLUMN roe_q4_3 TYPE NUMERIC(12,4);

-- 净利率字段
ALTER TABLE fact_daily_fundamental ALTER COLUMN net_margin_ttm TYPE NUMERIC(12,4);
ALTER TABLE fact_daily_fundamental ALTER COLUMN net_margin_lyr TYPE NUMERIC(12,4);
ALTER TABLE fact_daily_fundamental ALTER COLUMN net_margin_mrq TYPE NUMERIC(12,4);
ALTER TABLE fact_daily_fundamental ALTER COLUMN net_margin_q4 TYPE NUMERIC(12,4);
ALTER TABLE fact_daily_fundamental ALTER COLUMN net_margin_q2 TYPE NUMERIC(12,4);
ALTER TABLE fact_daily_fundamental ALTER COLUMN net_margin_q4_3 TYPE NUMERIC(12,4);
