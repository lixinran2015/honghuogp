-- Phase 1: 龙头跟踪池升级 - 数据库表结构扩展
-- 日期: 2026-03-24

-- ============================================
-- 1. 扩展 fact_leader_tracking_pool 表
-- ============================================

-- 多因子评分相关字段
ALTER TABLE fact_leader_tracking_pool
    ADD COLUMN IF NOT EXISTS score DECIMAL(5,2),                    -- 综合评分 0-100
    ADD COLUMN IF NOT EXISTS grade VARCHAR(2),                       -- 评级 S/A/B/C
    ADD COLUMN IF NOT EXISTS buy_signal VARCHAR(50),                 -- 当前买点信号
    ADD COLUMN IF NOT EXISTS risk_level VARCHAR(10),                 -- 风险等级 高/中/低
    ADD COLUMN IF NOT EXISTS emotion_cycle VARCHAR(20),              -- 入池时情绪周期
    ADD COLUMN IF NOT EXISTS sector_strength DECIMAL(5,2),           -- 板块强度
    ADD COLUMN IF NOT EXISTS block_ratio DECIMAL(5,2),               -- 封单比
    ADD COLUMN IF NOT EXISTS score_breakdown JSONB,                  -- 评分明细
    ADD COLUMN IF NOT EXISTS entry_reason TEXT,                      -- 入池原因
    ADD COLUMN IF NOT EXISTS failed_case_id INTEGER;                 -- 关联的失败案例ID

-- 创建索引优化查询
CREATE INDEX IF NOT EXISTS idx_leader_tracking_score ON fact_leader_tracking_pool(score);
CREATE INDEX IF NOT EXISTS idx_leader_tracking_grade ON fact_leader_tracking_pool(grade);
CREATE INDEX IF NOT EXISTS idx_leader_tracking_buy_signal ON fact_leader_tracking_pool(buy_signal);
CREATE INDEX IF NOT EXISTS idx_leader_tracking_risk_level ON fact_leader_tracking_pool(risk_level);
CREATE INDEX IF NOT EXISTS idx_leader_tracking_emotion_cycle ON fact_leader_tracking_pool(emotion_cycle);

-- 复合索引：评分+评级（用于筛选高质量龙头）
CREATE INDEX IF NOT EXISTS idx_leader_tracking_score_grade ON fact_leader_tracking_pool(score, grade);

-- ============================================
-- 2. 创建失败案例跟踪表（缓解幸存者偏差）
-- ============================================

CREATE TABLE IF NOT EXISTS fact_leader_tracking_failed (
    id SERIAL PRIMARY KEY,
    ts_code VARCHAR(20) NOT NULL,
    name VARCHAR(128) NOT NULL,
    trade_date DATE NOT NULL,
    reason VARCHAR(50) NOT NULL,                    -- 失败原因: score_too_low/炸板/冲高回落/其他
    score DECIMAL(5,2),                             -- 当时评分
    score_breakdown JSONB,                          -- 评分明细
    period_return_pct DECIMAL(8,2),                 -- 当时区间涨幅
    continuous_limit INTEGER,                       -- 当时连板数
    sector_name VARCHAR(100),                       -- 所属板块

    -- 后续表现（用于复盘分析）
    day_1_return DECIMAL(8,2),                      -- 第1日表现
    day_3_return DECIMAL(8,2),                      -- 第3日表现
    day_5_return DECIMAL(8,2),                      -- 第5日表现
    subsequent_performance JSONB,                   -- 详细后续表现数据

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(ts_code, trade_date)                     -- 避免重复记录
);

-- 失败案例表索引
CREATE INDEX IF NOT EXISTS idx_failed_ts_code ON fact_leader_tracking_failed(ts_code);
CREATE INDEX IF NOT EXISTS idx_failed_trade_date ON fact_leader_tracking_failed(trade_date);
CREATE INDEX IF NOT EXISTS idx_failed_reason ON fact_leader_tracking_failed(reason);

COMMENT ON TABLE fact_leader_tracking_failed IS '龙头跟踪失败案例（缓解幸存者偏差）';

-- ============================================
-- 3. 创建评分历史表（用于模型监控和回测）
-- ============================================

CREATE TABLE IF NOT EXISTS fact_leader_score_history (
    id SERIAL PRIMARY KEY,
    ts_code VARCHAR(20) NOT NULL,
    trade_date DATE NOT NULL,

    -- 综合评分
    total_score DECIMAL(5,2) NOT NULL,
    grade VARCHAR(2),

    -- 因子评分明细
    leader_position_score DECIMAL(5,2),             -- 龙头地位 30%
    technical_score DECIMAL(5,2),                   -- 技术形态 25%
    money_flow_score DECIMAL(5,2),                  -- 资金流向 25%
    sentiment_score DECIMAL(5,2),                   -- 情绪热度 20%

    -- 因子原始数据（用于归因分析）
    leader_position_data JSONB,
    technical_data JSONB,
    money_flow_data JSONB,
    sentiment_data JSONB,

    -- 市场环境
    emotion_cycle VARCHAR(20),                      -- 情绪周期
    market_status VARCHAR(20),                      -- 市场状态

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(ts_code, trade_date)                     -- 每个股票每天一条记录
);

-- 评分历史表索引
CREATE INDEX IF NOT EXISTS idx_score_history_ts_code ON fact_leader_score_history(ts_code);
CREATE INDEX IF NOT EXISTS idx_score_history_trade_date ON fact_leader_score_history(trade_date);
CREATE INDEX IF NOT EXISTS idx_score_history_total_score ON fact_leader_score_history(total_score);
CREATE INDEX IF NOT EXISTS idx_score_history_grade ON fact_leader_score_history(grade);

COMMENT ON TABLE fact_leader_score_history IS '龙头评分历史（用于模型监控和回测）';

-- ============================================
-- 4. 创建买点检测记录表
-- ============================================

CREATE TABLE IF NOT EXISTS fact_leader_buy_signal (
    id SERIAL PRIMARY KEY,
    ts_code VARCHAR(20) NOT NULL,
    trade_date DATE NOT NULL,
    signal_type VARCHAR(30) NOT NULL,               -- 买点类型: 首板放量/二板缩量/三板换手/断板反包/龙头首阴/其他

    -- 信号强度
    strength_score DECIMAL(5,2),                    -- 信号强度评分 0-100
    confidence_level VARCHAR(10),                   -- 置信度: high/medium/low

    -- 触发条件详情
    trigger_conditions JSONB,                       -- 触发条件详情
    technical_indicators JSONB,                     -- 技术指标数据

    -- 信号结果（后续回填）
    is_valid BOOLEAN,                               -- 是否有效信号
    actual_return_1d DECIMAL(8,2),                  -- 1日后实际收益
    actual_return_3d DECIMAL(8,2),                  -- 3日后实际收益
    actual_return_5d DECIMAL(8,2),                  -- 5日后实际收益

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(ts_code, trade_date, signal_type)        -- 同一天同类型信号只记录一次
);

-- 买点信号表索引
CREATE INDEX IF NOT EXISTS idx_buy_signal_ts_code ON fact_leader_buy_signal(ts_code);
CREATE INDEX IF NOT EXISTS idx_buy_signal_trade_date ON fact_leader_buy_signal(trade_date);
CREATE INDEX IF NOT EXISTS idx_buy_signal_type ON fact_leader_buy_signal(signal_type);
CREATE INDEX IF NOT EXISTS idx_buy_signal_strength ON fact_leader_buy_signal(strength_score);

COMMENT ON TABLE fact_leader_buy_signal IS '龙头买点信号检测记录';

-- ============================================
-- 5. 设置表权限
-- ============================================

-- 授予权限
GRANT ALL PRIVILEGES ON fact_leader_tracking_failed TO postgres;
GRANT ALL PRIVILEGES ON fact_leader_score_history TO postgres;
GRANT ALL PRIVILEGES ON fact_leader_buy_signal TO postgres;

-- 序列权限
GRANT ALL PRIVILEGES ON SEQUENCE fact_leader_tracking_failed_id_seq TO postgres;
GRANT ALL PRIVILEGES ON SEQUENCE fact_leader_score_history_id_seq TO postgres;
GRANT ALL PRIVILEGES ON SEQUENCE fact_leader_buy_signal_id_seq TO postgres;

-- 默认权限
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO postgres;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO postgres;
