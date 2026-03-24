-- 已卖出股票表
-- 记录已卖出股票的表现分析

CREATE TABLE IF NOT EXISTS fact_sold_stock (
    -- 主键
    id BIGSERIAL PRIMARY KEY,
    
    -- 股票基本信息
    ts_code VARCHAR(20) NOT NULL,  -- 股票代码（Tushare格式，如 600519.SH）
    stock_name VARCHAR(50),  -- 股票名称（冗余存储，方便查询）
    
    -- 卖出信息
    sell_date DATE NOT NULL,  -- 卖出日期
    
    -- 卖出后表现分析
    change_5d_after_sell NUMERIC(8, 4),  -- 卖出后5日涨幅（卖出后5个交易日的涨幅，单位：%）
    change_10d_after_sell NUMERIC(8, 4),  -- 卖出后10日涨幅（卖出后10个交易日的涨幅，单位：%）
    is_above_ma10 BOOLEAN,  -- 是否站稳10日线（卖出后是否在10日线上方）
    is_above_ma20 BOOLEAN,  -- 是否站稳20日线（卖出后是否在20日线上方）
    is_above_ma30 BOOLEAN,  -- 是否站稳30日线（卖出后是否在30日线上方）
    
    -- 其他信息
    notes TEXT,  -- 备注信息
    
    -- 时间戳
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,  -- 创建时间
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP  -- 更新时间
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_sold_stock_ts_code ON fact_sold_stock(ts_code);
CREATE INDEX IF NOT EXISTS idx_sold_stock_sell_date ON fact_sold_stock(sell_date DESC);
CREATE INDEX IF NOT EXISTS idx_sold_stock_change_5d ON fact_sold_stock(change_5d_after_sell DESC);
CREATE INDEX IF NOT EXISTS idx_sold_stock_change_10d ON fact_sold_stock(change_10d_after_sell DESC);

-- 创建更新时间触发器
CREATE OR REPLACE FUNCTION update_sold_stock_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_update_sold_stock_updated_at
    BEFORE UPDATE ON fact_sold_stock
    FOR EACH ROW
    EXECUTE FUNCTION update_sold_stock_updated_at();

-- 注释
COMMENT ON TABLE fact_sold_stock IS '已卖出股票表-记录已卖出股票的表现分析';
COMMENT ON COLUMN fact_sold_stock.ts_code IS '股票代码（Tushare格式）';
COMMENT ON COLUMN fact_sold_stock.stock_name IS '股票名称（冗余存储，方便查询）';
COMMENT ON COLUMN fact_sold_stock.sell_date IS '卖出日期';
COMMENT ON COLUMN fact_sold_stock.change_5d_after_sell IS '卖出后5日涨幅（卖出后5个交易日的涨幅，单位：%）';
COMMENT ON COLUMN fact_sold_stock.change_10d_after_sell IS '卖出后10日涨幅（卖出后10个交易日的涨幅，单位：%）';
COMMENT ON COLUMN fact_sold_stock.is_above_ma10 IS '是否站稳10日线（卖出后是否在10日线上方）';
COMMENT ON COLUMN fact_sold_stock.is_above_ma20 IS '是否站稳20日线（卖出后是否在20日线上方）';
COMMENT ON COLUMN fact_sold_stock.is_above_ma30 IS '是否站稳30日线（卖出后是否在30日线上方）';
COMMENT ON COLUMN fact_sold_stock.notes IS '备注信息';
