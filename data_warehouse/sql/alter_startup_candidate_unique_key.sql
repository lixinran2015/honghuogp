-- 修改 fact_stock_startup_candidate 表的唯一约束
-- 从 UNIQUE(ts_code, trade_date) 改为 UNIQUE(ts_code, golden_cross_date)
-- 
-- 业务逻辑说明：
-- 1. 同一个金叉应该只有一条记录
-- 2. trade_date 应该是最新满足条件的日期，可以更新
-- 3. 如果同一个股票有多个金叉（不同日期），每个金叉应该有独立的记录
--
-- 执行前请先：
-- 1. 备份数据库
-- 2. 清理重复数据（保留每个 (ts_code, golden_cross_date) 的最新 trade_date 记录）

-- 步骤1：删除现有的唯一约束
ALTER TABLE fact_stock_startup_candidate 
DROP CONSTRAINT IF EXISTS fact_stock_startup_candidate_ts_code_trade_date_key;

-- 步骤2：清理重复数据（保留每个 (ts_code, golden_cross_date) 的最新 trade_date 记录）
-- 注意：这个查询只是展示，实际删除需要谨慎执行
-- DELETE FROM fact_stock_startup_candidate
-- WHERE id IN (
--     SELECT id
--     FROM (
--         SELECT id,
--                ROW_NUMBER() OVER (
--                    PARTITION BY ts_code, golden_cross_date 
--                    ORDER BY trade_date DESC, id DESC
--                ) as rn
--         FROM fact_stock_startup_candidate
--         WHERE golden_cross_date IS NOT NULL
--     ) t
--     WHERE rn > 1
-- );

-- 步骤3：添加新的唯一约束（基于 ts_code 和 golden_cross_date）
-- 注意：golden_cross_date 可能为 NULL，需要先处理 NULL 值
-- 对于 golden_cross_date 为 NULL 的记录，可以：
-- 1. 设置为 trade_date（如果业务逻辑允许）
-- 2. 或者保留 NULL，但需要单独处理唯一约束

-- 先更新 golden_cross_date 为 NULL 的记录（如果业务逻辑允许）
-- UPDATE fact_stock_startup_candidate
-- SET golden_cross_date = trade_date
-- WHERE golden_cross_date IS NULL;

-- 添加新的唯一约束
ALTER TABLE fact_stock_startup_candidate
ADD CONSTRAINT fact_stock_startup_candidate_ts_code_golden_cross_date_key 
UNIQUE(ts_code, golden_cross_date);

-- 步骤4：创建索引以支持基于 trade_date 的查询（trade_date 仍然需要索引）
CREATE INDEX IF NOT EXISTS idx_startup_candidate_trade_date 
ON fact_stock_startup_candidate(trade_date DESC);

-- 步骤5：创建复合索引以支持基于 (ts_code, golden_cross_date) 的查询
CREATE INDEX IF NOT EXISTS idx_startup_candidate_code_cross_date 
ON fact_stock_startup_candidate(ts_code, golden_cross_date);

