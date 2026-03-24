-- 操作建议历史记录表
CREATE TABLE IF NOT EXISTS fact_operation_advice_history (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    name VARCHAR(100) NOT NULL,
    advice_date DATE NOT NULL,
    today_action VARCHAR(20) NOT NULL,
    today_action_reason TEXT,
    profit_rate DOUBLE PRECISION,
    chase_risk_level VARCHAR(20),
    chase_risk_score DOUBLE PRECISION,
    holding_days INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_advice_user_date ON fact_operation_advice_history(user_id, advice_date);
CREATE INDEX IF NOT EXISTS idx_advice_symbol ON fact_operation_advice_history(symbol);
CREATE INDEX IF NOT EXISTS idx_advice_user_symbol_date ON fact_operation_advice_history(user_id, symbol, advice_date);

-- 添加表注释
COMMENT ON TABLE fact_operation_advice_history IS '每日操作建议历史记录表';
COMMENT ON COLUMN fact_operation_advice_history.user_id IS '用户ID';
COMMENT ON COLUMN fact_operation_advice_history.symbol IS '股票代码（6位数字）';
COMMENT ON COLUMN fact_operation_advice_history.name IS '股票名称';
COMMENT ON COLUMN fact_operation_advice_history.advice_date IS '建议日期';
COMMENT ON COLUMN fact_operation_advice_history.today_action IS '操作建议：buy/add/hold/reduce/close/skip';
COMMENT ON COLUMN fact_operation_advice_history.today_action_reason IS '建议原因';
COMMENT ON COLUMN fact_operation_advice_history.profit_rate IS '当日盈亏比例（%）';
COMMENT ON COLUMN fact_operation_advice_history.chase_risk_level IS '追高风险等级：low/medium/high';
COMMENT ON COLUMN fact_operation_advice_history.chase_risk_score IS '追高风险评分（0-100）';
COMMENT ON COLUMN fact_operation_advice_history.holding_days IS '持仓天数';

-- 操作建议遵从度分析表
CREATE TABLE IF NOT EXISTS fact_advice_compliance (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    name VARCHAR(100) NOT NULL,
    buy_date DATE NOT NULL,
    close_date DATE NOT NULL,
    advice_history JSONB,
    first_advice VARCHAR(20),
    last_advice VARCHAR(20),
    days_ignored_reduce INTEGER DEFAULT 0,
    days_ignored_close INTEGER DEFAULT 0,
    should_reduce_date DATE,
    should_close_date DATE,
    actual_close_date DATE NOT NULL,
    profit_rate DOUBLE PRECISION NOT NULL,
    max_profit_rate DOUBLE PRECISION,
    max_loss_rate DOUBLE PRECISION,
    compliance_type VARCHAR(32) NOT NULL,
    compliance_score INTEGER DEFAULT 0,
    review_tags VARCHAR[],
    review_comment TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_compliance_user_close ON fact_advice_compliance(user_id, close_date);
CREATE INDEX IF NOT EXISTS idx_compliance_symbol ON fact_advice_compliance(symbol);

-- 添加表注释
COMMENT ON TABLE fact_advice_compliance IS '操作建议遵从度分析表 - 记录建议vs实际的对比';
COMMENT ON COLUMN fact_advice_compliance.user_id IS '用户ID';
COMMENT ON COLUMN fact_advice_compliance.symbol IS '股票代码';
COMMENT ON COLUMN fact_advice_compliance.name IS '股票名称';
COMMENT ON COLUMN fact_advice_compliance.buy_date IS '买入日期';
COMMENT ON COLUMN fact_advice_compliance.close_date IS '清仓日期';
COMMENT ON COLUMN fact_advice_compliance.advice_history IS '持仓期间每日建议记录（JSON数组）';
COMMENT ON COLUMN fact_advice_compliance.first_advice IS '首次建议';
COMMENT ON COLUMN fact_advice_compliance.last_advice IS '清仓前最后建议';
COMMENT ON COLUMN fact_advice_compliance.days_ignored_reduce IS '忽视减仓建议的天数';
COMMENT ON COLUMN fact_advice_compliance.days_ignored_close IS '忽视清仓建议的天数';
COMMENT ON COLUMN fact_advice_compliance.should_reduce_date IS '首次建议减仓日期';
COMMENT ON COLUMN fact_advice_compliance.should_close_date IS '首次建议清仓日期';
COMMENT ON COLUMN fact_advice_compliance.actual_close_date IS '实际清仓日期';
COMMENT ON COLUMN fact_advice_compliance.profit_rate IS '实际盈亏比例（%）';
COMMENT ON COLUMN fact_advice_compliance.max_profit_rate IS '期间最大盈利（%）';
COMMENT ON COLUMN fact_advice_compliance.max_loss_rate IS '期间最大亏损（%）';
COMMENT ON COLUMN fact_advice_compliance.compliance_type IS '遵从度类型：perfect/good/delayed/ignored_early/ignored_late';
COMMENT ON COLUMN fact_advice_compliance.compliance_score IS '遵从度评分（0-100）';
COMMENT ON COLUMN fact_advice_compliance.review_tags IS '复盘标签：如[该止损没止损, 该减仓没减, 卖飞了]';
COMMENT ON COLUMN fact_advice_compliance.review_comment IS '复盘评语';
