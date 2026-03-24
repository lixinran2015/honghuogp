-- 今日涨停且60日新高表
-- 记录每日计算的"今日涨停且60日新高"股票结果

CREATE TABLE IF NOT EXISTS fact_limit_up_today_60d_high (
    -- 主键
    id BIGSERIAL PRIMARY KEY,
    
    -- 计算日期和股票信息
    trade_date DATE NOT NULL,  -- 计算日期
    ts_code VARCHAR(20) NOT NULL,  -- 股票代码（Tushare格式，如 600519.SH）
    stock_name VARCHAR(100),  -- 股票名称（冗余存储，方便查询）
    
    -- 人气榜信息
    rank_position INTEGER,  -- 人气榜排名
    rank_change INTEGER,  -- 排名变动（正数=上升，负数=下降）
    max_rank INTEGER,  -- 计算时使用的人气榜范围（前N名）
    
    -- 价格和涨幅信息
    today_close NUMERIC(10, 2),  -- 今日收盘价
    change_pct NUMERIC(8, 4),  -- 今日涨幅（%）
    change_5d NUMERIC(8, 4),  -- 近5日涨幅（%）
    change_10d NUMERIC(8, 4),  -- 近10日涨幅（%）
    
    -- 判断结果
    is_60d_high BOOLEAN,  -- 是否60日新高
    
    -- 时间戳
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,  -- 创建时间
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,  -- 更新时间
    
    -- 唯一约束：同一日期同一股票只保存一条记录
    CONSTRAINT idx_limit_up_60d_date_code UNIQUE (trade_date, ts_code)
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_limit_up_60d_trade_date ON fact_limit_up_today_60d_high(trade_date DESC);
CREATE INDEX IF NOT EXISTS idx_limit_up_60d_ts_code ON fact_limit_up_today_60d_high(ts_code);
CREATE INDEX IF NOT EXISTS idx_limit_up_60d_rank_position ON fact_limit_up_today_60d_high(rank_position);
CREATE INDEX IF NOT EXISTS idx_limit_up_60d_change_5d ON fact_limit_up_today_60d_high(change_5d DESC);
CREATE INDEX IF NOT EXISTS idx_limit_up_60d_change_10d ON fact_limit_up_today_60d_high(change_10d DESC);
CREATE INDEX IF NOT EXISTS idx_limit_up_60d_is_60d_high ON fact_limit_up_today_60d_high(is_60d_high);

-- 创建更新时间触发器
CREATE OR REPLACE FUNCTION update_limit_up_60d_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_update_limit_up_60d_updated_at
    BEFORE UPDATE ON fact_limit_up_today_60d_high
    FOR EACH ROW
    EXECUTE FUNCTION update_limit_up_60d_updated_at();

-- 注释
COMMENT ON TABLE fact_limit_up_today_60d_high IS '今日涨停且60日新高表-记录每日计算的今日涨停且60日新高股票结果';
COMMENT ON COLUMN fact_limit_up_today_60d_high.trade_date IS '计算日期';
COMMENT ON COLUMN fact_limit_up_today_60d_high.ts_code IS '股票代码（Tushare格式）';
COMMENT ON COLUMN fact_limit_up_today_60d_high.stock_name IS '股票名称（冗余存储，方便查询）';
COMMENT ON COLUMN fact_limit_up_today_60d_high.rank_position IS '人气榜排名';
COMMENT ON COLUMN fact_limit_up_today_60d_high.rank_change IS '排名变动（正数=上升，负数=下降）';
COMMENT ON COLUMN fact_limit_up_today_60d_high.max_rank IS '计算时使用的人气榜范围（前N名）';
COMMENT ON COLUMN fact_limit_up_today_60d_high.today_close IS '今日收盘价';
COMMENT ON COLUMN fact_limit_up_today_60d_high.change_pct IS '今日涨幅（%）';
COMMENT ON COLUMN fact_limit_up_today_60d_high.change_5d IS '近5日涨幅（%）';
COMMENT ON COLUMN fact_limit_up_today_60d_high.change_10d IS '近10日涨幅（%）';
COMMENT ON COLUMN fact_limit_up_today_60d_high.is_60d_high IS '是否60日新高';
