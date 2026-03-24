-- 为 fact_fundamental 增加扣非净利率字段
-- 执行: psql -U <user> -d <db> -f migrations/add_deduct_net_margin.sql
ALTER TABLE fact_fundamental ADD COLUMN IF NOT EXISTS deduct_net_margin NUMERIC(8,4);
COMMENT ON COLUMN fact_fundamental.deduct_net_margin IS '扣非净利率（%）';
