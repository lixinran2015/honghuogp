-- 涨停缩量表
-- 记录每日计算的"最近5天有涨停且量能缩小（量比<0.6）"的股票结果

CREATE TABLE IF NOT EXISTS fact_limit_up_volume_shrink (
    -- 主键
    id BIGSERIAL PRIMARY KEY,
    
    -- 计算日期和股票信息
    trade_date DATE NOT NULL,  -- 计算日期
    ts_code VARCHAR(20) NOT NULL,  -- 股票代码（Tushare格式，如 600519.SH）
    stock_name VARCHAR(100),  -- 股票名称（冗余存储，方便查询）
    
    -- 涨停信息
    limit_up_date DATE,  -- 最近一次涨停日期
    limit_up_days_ago INTEGER,  -- 距离涨停天数
    
    -- 当前数据
    volume_ratio NUMERIC(8, 4),  -- 当前量比
    today_close NUMERIC(10, 2),  -- 今日收盘价
    today_change_pct NUMERIC(8, 4),  -- 今日涨幅（%）
    today_amount NUMERIC(20, 2),  -- 今日成交额（元）
    
    -- 时间戳
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,  -- 创建时间
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,  -- 更新时间
    
    -- 唯一约束：同一日期同一股票只保存一条记录
    CONSTRAINT idx_limit_up_volume_shrink_date_code UNIQUE (trade_date, ts_code)
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_limit_up_volume_shrink_trade_date ON fact_limit_up_volume_shrink(trade_date DESC);
CREATE INDEX IF NOT EXISTS idx_limit_up_volume_shrink_ts_code ON fact_limit_up_volume_shrink(ts_code);
CREATE INDEX IF NOT EXISTS idx_limit_up_volume_shrink_limit_up_date ON fact_limit_up_volume_shrink(limit_up_date DESC);
CREATE INDEX IF NOT EXISTS idx_limit_up_volume_shrink_volume_ratio ON fact_limit_up_volume_shrink(volume_ratio);

-- 创建更新时间触发器
CREATE OR REPLACE FUNCTION update_limit_up_volume_shrink_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_update_limit_up_volume_shrink_updated_at
    BEFORE UPDATE ON fact_limit_up_volume_shrink
    FOR EACH ROW
    EXECUTE FUNCTION update_limit_up_volume_shrink_updated_at();

-- 注释
COMMENT ON TABLE fact_limit_up_volume_shrink IS '涨停缩量表-记录最近5天有涨停且量能缩小（量比<0.6）的股票结果';
COMMENT ON COLUMN fact_limit_up_volume_shrink.trade_date IS '计算日期';
COMMENT ON COLUMN fact_limit_up_volume_shrink.ts_code IS '股票代码（Tushare格式）';
COMMENT ON COLUMN fact_limit_up_volume_shrink.stock_name IS '股票名称（冗余存储，方便查询）';
COMMENT ON COLUMN fact_limit_up_volume_shrink.limit_up_date IS '最近一次涨停日期';
COMMENT ON COLUMN fact_limit_up_volume_shrink.limit_up_days_ago IS '距离涨停天数';
COMMENT ON COLUMN fact_limit_up_volume_shrink.volume_ratio IS '当前量比';
COMMENT ON COLUMN fact_limit_up_volume_shrink.today_close IS '今日收盘价';
COMMENT ON COLUMN fact_limit_up_volume_shrink.today_change_pct IS '今日涨幅（%）';
COMMENT ON COLUMN fact_limit_up_volume_shrink.today_amount IS '今日成交额（元）';
