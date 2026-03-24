-- ============================================================
-- 数据库优化脚本 06: 精简 fact_daily_fundamental 表
-- 只保留每只股票最新一条数据
-- ============================================================

-- 步骤1: 查看当前数据量
SELECT 
    COUNT(*) as total_rows,
    COUNT(DISTINCT ts_code) as unique_stocks,
    MIN(trade_date) as earliest_date,
    MAX(trade_date) as latest_date,
    pg_size_pretty(pg_total_relation_size('fact_daily_fundamental')) as total_size
FROM fact_daily_fundamental;

-- 步骤2: 创建临时表保存最新数据
CREATE TABLE fact_daily_fundamental_latest AS
SELECT DISTINCT ON (ts_code) *
FROM fact_daily_fundamental
ORDER BY ts_code, trade_date DESC;

-- 步骤3: 验证临时表数据
SELECT COUNT(*) as rows_to_keep FROM fact_daily_fundamental_latest;

-- 步骤4: 清空原表并重新插入（保留表结构和索引）
TRUNCATE TABLE fact_daily_fundamental;

INSERT INTO fact_daily_fundamental
SELECT * FROM fact_daily_fundamental_latest;

-- 步骤5: 删除临时表
DROP TABLE fact_daily_fundamental_latest;

-- 步骤6: 回收空间
VACUUM FULL fact_daily_fundamental;
ANALYZE fact_daily_fundamental;

-- 步骤7: 验证结果
SELECT 
    COUNT(*) as total_rows,
    COUNT(DISTINCT ts_code) as unique_stocks,
    MIN(trade_date) as earliest_date,
    MAX(trade_date) as latest_date,
    pg_size_pretty(pg_total_relation_size('fact_daily_fundamental')) as total_size
FROM fact_daily_fundamental;

