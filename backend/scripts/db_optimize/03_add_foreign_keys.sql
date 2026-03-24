-- ============================================================
-- 数据库优化脚本 03: 添加外键约束
-- ============================================================
-- 注意：外键会影响写入性能，根据实际情况选择是否启用

-- 1. fact_daily_price -> dim_stock
-- ALTER TABLE fact_daily_price 
--     ADD CONSTRAINT fk_daily_price_stock 
--     FOREIGN KEY (ts_code) REFERENCES dim_stock(ts_code);

-- 2. fact_daily_price_qfq -> dim_stock
-- ALTER TABLE fact_daily_price_qfq 
--     ADD CONSTRAINT fk_daily_price_qfq_stock 
--     FOREIGN KEY (ts_code) REFERENCES dim_stock(ts_code);

-- 3. fact_stock_sector -> dim_stock
-- ALTER TABLE fact_stock_sector 
--     ADD CONSTRAINT fk_stock_sector_stock 
--     FOREIGN KEY (ts_code) REFERENCES dim_stock(ts_code);

-- 4. fact_stock_sector -> dim_sector
-- ALTER TABLE fact_stock_sector 
--     ADD CONSTRAINT fk_stock_sector_sector 
--     FOREIGN KEY (sector_id) REFERENCES dim_sector(sector_id);

-- 5. fact_sector_daily -> dim_sector
-- ALTER TABLE fact_sector_daily 
--     ADD CONSTRAINT fk_sector_daily_sector 
--     FOREIGN KEY (sector_id) REFERENCES dim_sector(sector_id);

-- 推荐：使用软约束（应用层校验）而非硬外键，避免影响批量导入性能
-- 以下是检查数据一致性的查询：

-- 检查孤立的行情数据（ts_code不在dim_stock中）
SELECT DISTINCT ts_code 
FROM fact_daily_price_qfq 
WHERE ts_code NOT IN (SELECT ts_code FROM dim_stock)
LIMIT 10;

-- 检查孤立的板块关系数据
SELECT DISTINCT sector_id 
FROM fact_stock_sector 
WHERE sector_id NOT IN (SELECT sector_id FROM dim_sector)
LIMIT 10;

