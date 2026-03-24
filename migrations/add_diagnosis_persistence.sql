-- 批量诊断结果持久化 + 待候选监控功能
-- 添加字段用于存储诊断结果和监控状态
-- 执行日期: 2025-12-05

-- 添加诊断结果字段到启动候选表
ALTER TABLE fact_stock_startup_candidate
ADD COLUMN IF NOT EXISTS diagnosis_result JSONB,
ADD COLUMN IF NOT EXISTS last_diagnosis_date DATE;

-- 添加待候选监控字段
ALTER TABLE fact_stock_startup_candidate
ADD COLUMN IF NOT EXISTS is_watching BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS missing_conditions TEXT[],
ADD COLUMN IF NOT EXISTS watch_start_date DATE,
ADD COLUMN IF NOT EXISTS last_check_time TIMESTAMP,
ADD COLUMN IF NOT EXISTS check_count INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS alert_sent BOOLEAN DEFAULT FALSE;

-- 添加列注释
COMMENT ON COLUMN fact_stock_startup_candidate.diagnosis_result IS '批量诊断结果（JSON）：{core_checks, passed_count, advice, distance_from_high等}';
COMMENT ON COLUMN fact_stock_startup_candidate.last_diagnosis_date IS '最后诊断日期';
COMMENT ON COLUMN fact_stock_startup_candidate.is_watching IS '是否加入待候选监控（2/3条件）';
COMMENT ON COLUMN fact_stock_startup_candidate.missing_conditions IS '缺少的核心条件列表';
COMMENT ON COLUMN fact_stock_startup_candidate.watch_start_date IS '开始监控日期';
COMMENT ON COLUMN fact_stock_startup_candidate.last_check_time IS '最后检查时间';
COMMENT ON COLUMN fact_stock_startup_candidate.check_count IS '已检查次数';
COMMENT ON COLUMN fact_stock_startup_candidate.alert_sent IS '是否已发送语音提醒';

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_startup_candidate_diagnosis_date ON fact_stock_startup_candidate(last_diagnosis_date);
CREATE INDEX IF NOT EXISTS idx_startup_candidate_watching ON fact_stock_startup_candidate(is_watching);
CREATE INDEX IF NOT EXISTS idx_startup_candidate_watch_date ON fact_stock_startup_candidate(watch_start_date);

-- 验证
SELECT 
    column_name,
    data_type,
    is_nullable
FROM information_schema.columns
WHERE table_name = 'fact_stock_startup_candidate'
AND column_name IN ('diagnosis_result', 'last_diagnosis_date', 'is_watching', 'missing_conditions', 'watch_start_date', 'last_check_time', 'check_count', 'alert_sent')
ORDER BY ordinal_position;

-- 输出完成信息
SELECT '✅ 诊断持久化 + 待候选监控功能数据库迁移完成' AS status;

