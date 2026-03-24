-- 股票启动候选表
-- 记录得分60分的股票（通过前3层但被风险条件排除）

CREATE TABLE IF NOT EXISTS fact_stock_startup_candidate (
    -- 主键
    id BIGSERIAL PRIMARY KEY,
    
    -- 股票基本信息
    ts_code VARCHAR(20) NOT NULL,
    trade_date DATE NOT NULL,
    
    -- 启动判断结果
    score INTEGER NOT NULL,  -- 启动得分（通常是60）
    is_started BOOLEAN DEFAULT FALSE,  -- 是否判定为启动
    
    -- 通过的层级
    basic_passed BOOLEAN DEFAULT FALSE,  -- 基础过滤是否通过
    core_passed BOOLEAN DEFAULT FALSE,   -- 核心判定是否通过
    assist_count INTEGER DEFAULT 0,      -- 辅助确认满足数量
    risk_passed BOOLEAN DEFAULT FALSE,   -- 风险排除是否通过
    
    -- 满足的信号（文本数组）
    passed_signals TEXT[],
    
    -- 风险原因（文本数组）
    risk_reasons TEXT[],
    
    -- 详细指标数据（JSON格式）
    indicators JSONB,
    
    -- 元数据
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    
    -- 唯一约束
    UNIQUE(ts_code, trade_date)
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_startup_candidate_date ON fact_stock_startup_candidate(trade_date DESC);
CREATE INDEX IF NOT EXISTS idx_startup_candidate_score ON fact_stock_startup_candidate(score DESC);
CREATE INDEX IF NOT EXISTS idx_startup_candidate_risk ON fact_stock_startup_candidate(risk_passed, score DESC);

-- 注释
COMMENT ON TABLE fact_stock_startup_candidate IS '股票启动候选表-记录接近启动但有风险的股票';
COMMENT ON COLUMN fact_stock_startup_candidate.score IS '启动得分(0-100)';
COMMENT ON COLUMN fact_stock_startup_candidate.passed_signals IS '满足的启动信号列表';
COMMENT ON COLUMN fact_stock_startup_candidate.risk_reasons IS '风险原因列表';
COMMENT ON COLUMN fact_stock_startup_candidate.indicators IS '详细指标数据(JSON)';

