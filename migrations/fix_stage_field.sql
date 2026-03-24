-- 修复 stage 字段：将完全启动的股票的 stage 改为 'started'
-- 优先级1修复：统一 stage 字段逻辑

-- 1. 将现有 is_started=True 且 score >= 70 的记录的 stage 改为 'started'
UPDATE fact_stock_startup_candidate
SET stage = 'started'
WHERE is_started = True
  AND score >= 70
  AND stage != 'started';

-- 2. 将现有 is_started=True 且 score >= 60 且 risk_passed=True 的记录的 stage 改为 'started'
-- （这些是完全启动的股票，即使分数较低也应该标记为 'started'）
UPDATE fact_stock_startup_candidate
SET stage = 'started'
WHERE is_started = True
  AND score >= 60
  AND risk_passed = True
  AND stage != 'started';

-- 3. 确保 stage='started' 的记录 is_started=True（数据一致性检查）
UPDATE fact_stock_startup_candidate
SET is_started = True
WHERE stage = 'started'
  AND is_started = False;

-- 4. 统计更新结果
SELECT 
    '更新前统计' as description,
    COUNT(*) FILTER (WHERE is_started = True AND stage = 'confirmed') as started_but_confirmed,
    COUNT(*) FILTER (WHERE is_started = True AND stage = 'started') as started_and_started_stage
FROM fact_stock_startup_candidate
UNION ALL
SELECT 
    '更新后统计' as description,
    COUNT(*) FILTER (WHERE is_started = True AND stage = 'confirmed') as started_but_confirmed,
    COUNT(*) FILTER (WHERE is_started = True AND stage = 'started') as started_and_started_stage
FROM fact_stock_startup_candidate;

-- 5. 创建索引优化查询（如果不存在）
CREATE INDEX IF NOT EXISTS idx_startup_candidate_stage_started 
ON fact_stock_startup_candidate(stage) 
WHERE stage = 'started';

-- 6. 添加注释说明
COMMENT ON COLUMN fact_stock_startup_candidate.stage IS '阶段：golden_cross(金叉候选) / confirmed(启动确认) / started(完全启动)';

