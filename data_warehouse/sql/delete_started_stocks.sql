-- 删除"已启动"股票数据的SQL脚本
-- 表名：fact_stock_startup_candidate

-- ============================================
-- 1. 先查询，确认要删除的数据
-- ============================================

-- 查询所有已启动的股票（is_started = TRUE）
SELECT 
    ts_code,
    trade_date,
    stage,
    score,
    is_started,
    passed_signals,
    created_at
FROM fact_stock_startup_candidate
WHERE is_started = TRUE
ORDER BY trade_date DESC, ts_code;

-- 查询完全启动的股票（stage = 'started'）
SELECT 
    ts_code,
    trade_date,
    stage,
    score,
    is_started,
    passed_signals,
    created_at
FROM fact_stock_startup_candidate
WHERE stage = 'started'
ORDER BY trade_date DESC, ts_code;

-- 查询启动确认的股票（stage = 'confirmed'）
SELECT 
    ts_code,
    trade_date,
    stage,
    score,
    is_started,
    passed_signals,
    created_at
FROM fact_stock_startup_candidate
WHERE stage = 'confirmed'
ORDER BY trade_date DESC, ts_code;

-- 统计各状态的数量
SELECT 
    stage,
    COUNT(*) as count,
    COUNT(*) FILTER (WHERE is_started = TRUE) as started_count
FROM fact_stock_startup_candidate
GROUP BY stage
ORDER BY count DESC;

-- ============================================
-- 2. 删除操作（请谨慎使用！）
-- ============================================

-- 选项1：删除所有已启动的股票（is_started = TRUE）
-- DELETE FROM fact_stock_startup_candidate
-- WHERE is_started = TRUE;

-- 选项2：只删除完全启动的股票（stage = 'started'）
-- DELETE FROM fact_stock_startup_candidate
-- WHERE stage = 'started';

-- 选项3：删除启动确认和完全启动的股票（stage IN ('confirmed', 'started')）
-- DELETE FROM fact_stock_startup_candidate
-- WHERE stage IN ('confirmed', 'started');

-- 选项4：删除指定日期之后的已启动股票
-- DELETE FROM fact_stock_startup_candidate
-- WHERE is_started = TRUE
--   AND trade_date >= '2025-12-01';

-- 选项5：删除指定股票的已启动记录
-- DELETE FROM fact_stock_startup_candidate
-- WHERE is_started = TRUE
--   AND ts_code IN ('603122.SH', '002044.SZ');

-- 选项6：删除通过特殊规则（人气票）启动的股票（如果还有残留）
-- 这些股票通常只有1-2个核心条件，但被标记为已启动
-- DELETE FROM fact_stock_startup_candidate
-- WHERE is_started = TRUE
--   AND stage = 'started'
--   AND (
--     -- 只有1个核心条件通过
--     (passed_signals IS NOT NULL AND array_length(passed_signals, 1) <= 2)
--     OR
--     -- 得分较低但被标记为已启动
--     (score < 60 AND is_started = TRUE)
--   );

-- ============================================
-- 3. 安全删除（推荐）：先备份再删除
-- ============================================

-- 步骤1：创建备份表
-- CREATE TABLE fact_stock_startup_candidate_backup AS
-- SELECT * FROM fact_stock_startup_candidate
-- WHERE is_started = TRUE;

-- 步骤2：确认备份数据
-- SELECT COUNT(*) FROM fact_stock_startup_candidate_backup;

-- 步骤3：执行删除
-- DELETE FROM fact_stock_startup_candidate
-- WHERE is_started = TRUE;

-- 步骤4：如果需要恢复，可以从备份表恢复
-- INSERT INTO fact_stock_startup_candidate
-- SELECT * FROM fact_stock_startup_candidate_backup;

-- ============================================
-- 4. 更新操作（替代删除）：重置状态
-- ============================================

-- 将已启动的股票重置为金叉候选状态
-- UPDATE fact_stock_startup_candidate
-- SET 
--     is_started = FALSE,
--     stage = 'golden_cross',
--     is_watching = FALSE,
--     alert_sent = FALSE
-- WHERE is_started = TRUE;

-- 只重置通过特殊规则启动的股票（得分<60但已启动）
-- UPDATE fact_stock_startup_candidate
-- SET 
--     is_started = FALSE,
--     stage = 'golden_cross',
--     is_watching = FALSE,
--     alert_sent = FALSE
-- WHERE is_started = TRUE
--   AND stage = 'started'
--   AND score < 60;

