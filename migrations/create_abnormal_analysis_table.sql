-- 异动分析结果表：保存每日异动股票及分析结果
CREATE TABLE IF NOT EXISTS fact_abnormal_analysis (
    id SERIAL PRIMARY KEY,
    trade_date DATE NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    stock_name VARCHAR(100),
    pct_chg NUMERIC(8,4),                        -- 涨跌幅
    volume_ratio NUMERIC(8,4),                   -- 量比
    turnover_rate NUMERIC(8,4),                  -- 换手率
    abnormal_types VARCHAR(200),                 -- 异动类型，逗号分隔
    severity VARCHAR(20),                        -- 严重程度: low/medium/high
    news_count INTEGER DEFAULT 0,                -- 新闻数量
    announcement_count INTEGER DEFAULT 0,        -- 公告数量
    dragon_tiger BOOLEAN DEFAULT FALSE,          -- 是否有龙虎榜
    block_trade BOOLEAN DEFAULT FALSE,           -- 是否有大宗交易
    ai_analysis TEXT,                            -- AI 分析结果
    summary VARCHAR(500),                        -- 简短摘要
    events_json JSONB,                           -- 完整事件 JSON
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(trade_date, symbol)
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_abnormal_trade_date ON fact_abnormal_analysis(trade_date DESC);
CREATE INDEX IF NOT EXISTS idx_abnormal_symbol ON fact_abnormal_analysis(symbol);
CREATE INDEX IF NOT EXISTS idx_abnormal_severity ON fact_abnormal_analysis(severity);
CREATE INDEX IF NOT EXISTS idx_abnormal_pct_chg ON fact_abnormal_analysis(pct_chg DESC);

COMMENT ON TABLE fact_abnormal_analysis IS '异动分析结果表';
COMMENT ON COLUMN fact_abnormal_analysis.abnormal_types IS '异动类型：涨停/大涨/大跌/放量/高换手等';
COMMENT ON COLUMN fact_abnormal_analysis.severity IS '严重程度：low/medium/high';
