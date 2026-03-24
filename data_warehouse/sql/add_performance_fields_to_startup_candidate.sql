-- 为股票启动候选表添加表现字段（后5日、10日、20日、60日涨幅）
-- 执行日期: 2025-12-25

-- 添加表现字段
ALTER TABLE fact_stock_startup_candidate
ADD COLUMN IF NOT EXISTS change_5d NUMERIC(10, 2),
ADD COLUMN IF NOT EXISTS change_5d_days INTEGER,
ADD COLUMN IF NOT EXISTS change_10d NUMERIC(10, 2),
ADD COLUMN IF NOT EXISTS change_10d_days INTEGER,
ADD COLUMN IF NOT EXISTS change_20d NUMERIC(10, 2),
ADD COLUMN IF NOT EXISTS change_20d_days INTEGER,
ADD COLUMN IF NOT EXISTS change_60d NUMERIC(10, 2),
ADD COLUMN IF NOT EXISTS change_60d_days INTEGER,
ADD COLUMN IF NOT EXISTS performance_calculated_at TIMESTAMP;

-- 添加列注释
COMMENT ON COLUMN fact_stock_startup_candidate.change_5d IS '后5日涨幅（百分比）';
COMMENT ON COLUMN fact_stock_startup_candidate.change_5d_days IS '后5日涨幅实际交易日数';
COMMENT ON COLUMN fact_stock_startup_candidate.change_10d IS '后10日涨幅（百分比）';
COMMENT ON COLUMN fact_stock_startup_candidate.change_10d_days IS '后10日涨幅实际交易日数';
COMMENT ON COLUMN fact_stock_startup_candidate.change_20d IS '后20日涨幅（百分比）';
COMMENT ON COLUMN fact_stock_startup_candidate.change_20d_days IS '后20日涨幅实际交易日数';
COMMENT ON COLUMN fact_stock_startup_candidate.change_60d IS '后60日涨幅（百分比）';
COMMENT ON COLUMN fact_stock_startup_candidate.change_60d_days IS '后60日涨幅实际交易日数';
COMMENT ON COLUMN fact_stock_startup_candidate.performance_calculated_at IS '表现数据计算时间';

-- 索引说明：
-- 1. change_5d 和 change_10d 索引：
--    - 这些字段主要用于统计计算，不是作为主要的WHERE条件
--    - 查询时主要使用 trade_date 和 score（已有索引）
--    - 如果数据量不大（<10万条），这些索引可能不是必需的
--    - 如果经常需要按涨幅排序或过滤，可以考虑添加索引
-- 
-- 2. performance_calculated_at 索引：
--    - 仅用于记录计算时间，通常不作为查询条件
--    - 如果不需要查询"哪些记录已计算"，可以不加索引
--
-- 建议：根据实际查询需求和数据量决定是否创建索引
-- 如果数据量较小或查询频率不高，可以跳过索引创建以减少写入开销

-- 可选：如果需要按涨幅查询或排序，可以取消下面的注释
-- CREATE INDEX IF NOT EXISTS idx_startup_candidate_change_5d 
-- ON fact_stock_startup_candidate(change_5d) WHERE change_5d IS NOT NULL;
--
-- CREATE INDEX IF NOT EXISTS idx_startup_candidate_change_10d 
-- ON fact_stock_startup_candidate(change_10d) WHERE change_10d IS NOT NULL;
--
-- CREATE INDEX IF NOT EXISTS idx_startup_candidate_performance_calculated 
-- ON fact_stock_startup_candidate(performance_calculated_at);

-- 验证
SELECT 
    column_name,
    data_type,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_name = 'fact_stock_startup_candidate'
AND column_name LIKE 'change_%' OR column_name = 'performance_calculated_at'
ORDER BY ordinal_position;

-- 输出完成信息
SELECT '✅ 启动表现字段添加完成' AS status;

