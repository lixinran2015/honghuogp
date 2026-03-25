-- 为 fact_leader_tracking_pool 表添加主线雷达相关字段
-- 执行时间: 2026-03-25

-- 添加主线雷达状态字段
ALTER TABLE fact_leader_tracking_pool
    ADD COLUMN IF NOT EXISTS startup_is_started BOOLEAN,
    ADD COLUMN IF NOT EXISTS startup_core_passed BOOLEAN,
    ADD COLUMN IF NOT EXISTS startup_assist_count INTEGER,
    ADD COLUMN IF NOT EXISTS startup_risk_passed BOOLEAN,
    ADD COLUMN IF NOT EXISTS startup_stage VARCHAR(20),
    ADD COLUMN IF NOT EXISTS startup_score INTEGER,
    ADD COLUMN IF NOT EXISTS startup_indicators JSONB;

-- 创建索引以优化查询
CREATE INDEX IF NOT EXISTS idx_leader_pool_startup_score
    ON fact_leader_tracking_pool(startup_score)
    WHERE startup_score IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_leader_pool_startup_stage
    ON fact_leader_tracking_pool(startup_stage)
    WHERE startup_stage IS NOT NULL;

-- 更新注释
COMMENT ON TABLE fact_leader_tracking_pool IS '龙头跟踪池：成员持久化（去重：ts_code 唯一），支持主线雷达数据';

-- 列注释
COMMENT ON COLUMN fact_leader_tracking_pool.startup_is_started IS '主线雷达-是否已启动';
COMMENT ON COLUMN fact_leader_tracking_pool.startup_core_passed IS '主线雷达-核心条件通过';
COMMENT ON COLUMN fact_leader_tracking_pool.startup_assist_count IS '主线雷达-辅助条件满足数';
COMMENT ON COLUMN fact_leader_tracking_pool.startup_risk_passed IS '主线雷达-风险排除通过';
COMMENT ON COLUMN fact_leader_tracking_pool.startup_stage IS '主线雷达-阶段';
COMMENT ON COLUMN fact_leader_tracking_pool.startup_score IS '主线雷达-启动得分';
COMMENT ON COLUMN fact_leader_tracking_pool.startup_indicators IS '主线雷达-技术指标数据';
