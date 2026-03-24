-- ============================================================
-- 数据库优化脚本 05: 删除废弃的 fact_daily_price 表
-- ============================================================
-- 注意：执行前请确保代码已更新，不再使用此表

-- 1. 删除索引
DROP INDEX IF EXISTS ix_fact_daily_price_trade_date;

-- 2. 删除表
DROP TABLE IF EXISTS fact_daily_price;

-- 验证删除成功
-- SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'fact_daily_price';

