-- 添加财务检测结果字段到启动候选表
-- 执行日期: 2026-01-26

-- 添加财务检测结果字段
ALTER TABLE fact_stock_startup_candidate
ADD COLUMN IF NOT EXISTS financial_check_result JSONB,
ADD COLUMN IF NOT EXISTS last_financial_check_date DATE;

-- 添加列注释
COMMENT ON COLUMN fact_stock_startup_candidate.financial_check_result IS '财务检测结果（JSON）：{is_passed, failure_reasons, industry, sector, check_date等}';
COMMENT ON COLUMN fact_stock_startup_candidate.last_financial_check_date IS '最后财务检测日期';

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_startup_candidate_financial_check_date ON fact_stock_startup_candidate(last_financial_check_date);
CREATE INDEX IF NOT EXISTS idx_startup_candidate_financial_check_passed ON fact_stock_startup_candidate((financial_check_result->>'is_passed'));

-- 验证
SELECT 
    column_name,
    data_type,
    is_nullable
FROM information_schema.columns
WHERE table_name = 'fact_stock_startup_candidate'
AND column_name IN ('financial_check_result', 'last_financial_check_date');
