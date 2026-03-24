-- 同花顺涨跌停数据表
-- 存储从同花顺 THS_BD 接口获取的涨跌停状态和量比数据

CREATE TABLE IF NOT EXISTS fact_tonghuashun_limit_up (
    -- 主键
    id BIGSERIAL PRIMARY KEY,
    
    -- 股票信息和日期
    ts_code VARCHAR(20) NOT NULL,
    trade_date DATE NOT NULL,
    
    -- 涨跌停状态（同花顺返回的状态值）
    up_and_down_status VARCHAR(50),
    
    -- 量比
    volume_ratio NUMERIC(10, 4),
    
    -- 股票简称
    stock_name VARCHAR(100),
    
    -- 收盘价
    close_price NUMERIC(12, 4),
    
    -- 成交额（元）
    amount NUMERIC(20, 4),
    
    -- 涨跌幅（%）
    change_pct NUMERIC(8, 4),
    
    -- 时间戳
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- 唯一约束：同一股票同一日期只有一条记录
    CONSTRAINT uk_tonghuashun_limit_up_code_date UNIQUE (ts_code, trade_date)
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_tonghuashun_limit_up_trade_date ON fact_tonghuashun_limit_up(trade_date DESC);
CREATE INDEX IF NOT EXISTS idx_tonghuashun_limit_up_ts_code ON fact_tonghuashun_limit_up(ts_code);
CREATE INDEX IF NOT EXISTS idx_tonghuashun_limit_up_status ON fact_tonghuashun_limit_up(up_and_down_status);

-- 创建更新时间触发器
CREATE OR REPLACE FUNCTION update_tonghuashun_limit_up_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_update_tonghuashun_limit_up_updated_at
    BEFORE UPDATE ON fact_tonghuashun_limit_up
    FOR EACH ROW
    EXECUTE FUNCTION update_tonghuashun_limit_up_updated_at();

COMMENT ON TABLE fact_tonghuashun_limit_up IS '同花顺涨跌停数据表';
COMMENT ON COLUMN fact_tonghuashun_limit_up.ts_code IS '股票代码（Tushare格式）';
COMMENT ON COLUMN fact_tonghuashun_limit_up.trade_date IS '交易日期';
COMMENT ON COLUMN fact_tonghuashun_limit_up.up_and_down_status IS '涨跌停状态（同花顺返回的状态值）';
COMMENT ON COLUMN fact_tonghuashun_limit_up.volume_ratio IS '量比';
