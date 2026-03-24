-- 个股主力资金流向表
-- 数据来源：Tushare moneyflow 接口
-- 用于推荐模块资金流分析

CREATE TABLE IF NOT EXISTS fact_money_flow (
    ts_code            VARCHAR(20) NOT NULL,
    trade_date         DATE NOT NULL,
    main_net_inflow    NUMERIC(20,4),   -- 主力净流入（万元），大单+特大单净额
    main_net_inflow_rate NUMERIC(8,4),  -- 主力净流入占比（%）
    updated_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ts_code, trade_date)
);

CREATE INDEX IF NOT EXISTS idx_fact_money_flow_date ON fact_money_flow(trade_date);
CREATE INDEX IF NOT EXISTS idx_fact_money_flow_ts_code ON fact_money_flow(ts_code);

COMMENT ON TABLE fact_money_flow IS '个股主力资金流向（Tushare moneyflow）';
