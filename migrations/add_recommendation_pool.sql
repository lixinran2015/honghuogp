-- 推荐股票池功能数据库迁移脚本
-- 执行日期: 2025-12-04

-- ============================================
-- 1. 创建推荐股票表
-- ============================================
CREATE TABLE IF NOT EXISTS fact_recommended_stocks (
    id SERIAL PRIMARY KEY,
    
    -- 股票信息
    ts_code VARCHAR(10) NOT NULL,
    recommend_date DATE NOT NULL,
    entry_price NUMERIC(10, 2),
    current_price NUMERIC(10, 2),
    
    -- 推荐原因
    recommend_reason TEXT,
    recommend_tags TEXT[],
    
    -- 信号强度
    startup_score INTEGER,
    signal_strength VARCHAR(20),
    
    -- 技术指标状态
    macd_status VARCHAR(20),
    kdj_status VARCHAR(20),
    volume_ratio NUMERIC(10, 2),
    
    -- 市场表现
    change_5d NUMERIC(10, 2),
    change_10d NUMERIC(10, 2),
    amount NUMERIC(20, 2),
    
    -- 风险提示
    risk_level VARCHAR(20),
    risk_note TEXT,
    
    -- 状态管理
    status VARCHAR(20) DEFAULT 'active',
    stop_loss_price NUMERIC(10, 2),
    take_profit_price NUMERIC(10, 2),
    
    -- 追踪数据
    max_gain NUMERIC(10, 2),
    max_drawdown NUMERIC(10, 2),
    
    -- 时间戳
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- 唯一约束
    UNIQUE(ts_code, recommend_date)
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_recommended_stocks_date ON fact_recommended_stocks(recommend_date);
CREATE INDEX IF NOT EXISTS idx_recommended_stocks_ts_code ON fact_recommended_stocks(ts_code);
CREATE INDEX IF NOT EXISTS idx_recommended_stocks_status ON fact_recommended_stocks(status);
CREATE INDEX IF NOT EXISTS idx_recommended_stocks_score ON fact_recommended_stocks(startup_score);

-- 添加列注释
COMMENT ON TABLE fact_recommended_stocks IS '推荐股票事实表';
COMMENT ON COLUMN fact_recommended_stocks.ts_code IS '股票代码';
COMMENT ON COLUMN fact_recommended_stocks.recommend_date IS '推荐日期';
COMMENT ON COLUMN fact_recommended_stocks.entry_price IS '入选价格';
COMMENT ON COLUMN fact_recommended_stocks.current_price IS '当前价格';
COMMENT ON COLUMN fact_recommended_stocks.recommend_reason IS '推荐原因（完整描述）';
COMMENT ON COLUMN fact_recommended_stocks.recommend_tags IS '推荐标签';
COMMENT ON COLUMN fact_recommended_stocks.startup_score IS '启动得分（60-100）';
COMMENT ON COLUMN fact_recommended_stocks.signal_strength IS '信号强度：强/中/弱';
COMMENT ON COLUMN fact_recommended_stocks.status IS '状态：active/closed/stopped';

-- ============================================
-- 2. 更新启动候选表（添加推荐相关字段）
-- ============================================
ALTER TABLE fact_stock_startup_candidate
ADD COLUMN IF NOT EXISTS is_recommended BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS recommend_date DATE,
ADD COLUMN IF NOT EXISTS recommend_id INTEGER;

-- 添加列注释
COMMENT ON COLUMN fact_stock_startup_candidate.is_recommended IS '是否已加入推荐池';
COMMENT ON COLUMN fact_stock_startup_candidate.recommend_date IS '推荐日期';
COMMENT ON COLUMN fact_stock_startup_candidate.recommend_id IS '推荐记录ID';

-- ============================================
-- 验证
-- ============================================
-- 查看推荐表结构
SELECT 
    column_name,
    data_type,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_name = 'fact_recommended_stocks'
ORDER BY ordinal_position;

-- 查看启动候选表新增字段
SELECT 
    column_name,
    data_type,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_name = 'fact_stock_startup_candidate'
AND column_name IN ('is_recommended', 'recommend_date', 'recommend_id');

-- 输出完成信息
SELECT '✅ 推荐股票池功能数据库迁移完成' AS status;

