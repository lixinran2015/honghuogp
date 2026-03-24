-- 投资笔记表：记录用户的投资复盘、教训、心得
CREATE TABLE IF NOT EXISTS fact_investment_notes (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL DEFAULT 1,
    symbol VARCHAR(20),                          -- 关联股票代码（可选）
    stock_name VARCHAR(100),                     -- 股票名称
    note_type VARCHAR(20) NOT NULL DEFAULT 'general',  -- 笔记类型：general/lesson/success/mistake
    title VARCHAR(200) NOT NULL,                 -- 笔记标题
    content TEXT NOT NULL,                       -- 笔记内容
    tags VARCHAR(500),                           -- 标签，逗号分隔
    trade_date DATE,                             -- 相关交易日期
    profit_rate NUMERIC(8,4),                    -- 相关盈亏率
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_investment_notes_user ON fact_investment_notes(user_id);
CREATE INDEX IF NOT EXISTS idx_investment_notes_symbol ON fact_investment_notes(symbol);
CREATE INDEX IF NOT EXISTS idx_investment_notes_type ON fact_investment_notes(note_type);
CREATE INDEX IF NOT EXISTS idx_investment_notes_created ON fact_investment_notes(created_at DESC);

COMMENT ON TABLE fact_investment_notes IS '投资笔记表';
COMMENT ON COLUMN fact_investment_notes.note_type IS '笔记类型：general-一般笔记, lesson-教训, success-成功经验, mistake-错误总结';
