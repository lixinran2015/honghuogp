-- 北向资金个股持仓表
-- 数据来源：Tushare hk_hold 接口（沪股通+深股通）
-- 用于推荐模块资金流分析
-- 注：2024-08-20 后交易所停止日度披露，改为季度，历史日度数据仍可用

CREATE TABLE IF NOT EXISTS fact_north_holding (
    ts_code     VARCHAR(20) NOT NULL,
    trade_date  DATE NOT NULL,
    hold_vol    BIGINT,                -- 持股数量（股）
    hold_ratio  NUMERIC(8,4),          -- 持股占比（%）
    exchange    VARCHAR(10),           -- SH 沪股通 / SZ 深股通
    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ts_code, trade_date)
);

CREATE INDEX IF NOT EXISTS idx_fact_north_holding_date ON fact_north_holding(trade_date);
CREATE INDEX IF NOT EXISTS idx_fact_north_holding_ts_code ON fact_north_holding(ts_code);

COMMENT ON TABLE fact_north_holding IS '北向资金个股持仓（Tushare hk_hold）';
