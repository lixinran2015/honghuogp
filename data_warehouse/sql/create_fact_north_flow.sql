-- 北向资金市场净流入表
-- 数据来源：Tushare moneyflow_hsgt 接口（沪深港通资金流向）
-- 用于市场环境分析中的北向资金净流入
-- 单位：net_amount 为元（元），除以 1e8 即为亿

CREATE TABLE IF NOT EXISTS fact_north_flow (
    trade_date  DATE NOT NULL PRIMARY KEY,
    net_amount  NUMERIC(20,2),           -- 北向资金净流入（元）
    hgt         NUMERIC(20,2),           -- 沪股通净流入（百万元，同 Tushare 单位）
    sgt         NUMERIC(20,2),           -- 深股通净流入（百万元，同 Tushare 单位）
    south_money NUMERIC(20,2),           -- 南向资金（百万元）
    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_fact_north_flow_date ON fact_north_flow(trade_date);

COMMENT ON TABLE fact_north_flow IS '北向资金市场净流入（Tushare moneyflow_hsgt）';
