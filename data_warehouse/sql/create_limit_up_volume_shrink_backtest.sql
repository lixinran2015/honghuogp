-- 涨停缩量回测结果表
-- 存储回测交易明细和结果

CREATE TABLE IF NOT EXISTS fact_limit_up_volume_shrink_backtest (
    -- 主键
    id BIGSERIAL PRIMARY KEY,
    
    -- 信号信息
    signal_date DATE NOT NULL,
    ts_code VARCHAR(20) NOT NULL,
    stock_name VARCHAR(100),
    
    -- 交易信息
    buy_date DATE NOT NULL,
    buy_price NUMERIC(12, 4) NOT NULL,
    sell_date DATE,
    sell_price NUMERIC(12, 4),
    
    -- 收益信息
    return_pct NUMERIC(8, 4),
    hold_days INTEGER,
    exit_reason VARCHAR(50),  -- profit_target, stop_loss, time_limit
    
    -- 回测参数（用于区分不同回测配置）
    profit_target NUMERIC(8, 4),
    stop_loss NUMERIC(8, 4),
    max_hold_days INTEGER,
    sell_strategy VARCHAR(50),  -- 卖出策略：profit_stop, ma5_loss, ma5_loss_5pct
    
    -- 时间戳
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_backtest_signal_date ON fact_limit_up_volume_shrink_backtest(signal_date);
CREATE INDEX IF NOT EXISTS idx_backtest_ts_code ON fact_limit_up_volume_shrink_backtest(ts_code);
CREATE INDEX IF NOT EXISTS idx_backtest_buy_date ON fact_limit_up_volume_shrink_backtest(buy_date);
CREATE INDEX IF NOT EXISTS idx_backtest_exit_reason ON fact_limit_up_volume_shrink_backtest(exit_reason);

COMMENT ON TABLE fact_limit_up_volume_shrink_backtest IS '涨停缩量回测结果表';
COMMENT ON COLUMN fact_limit_up_volume_shrink_backtest.signal_date IS '信号日期（找到股票的日期）';
COMMENT ON COLUMN fact_limit_up_volume_shrink_backtest.ts_code IS '股票代码';
COMMENT ON COLUMN fact_limit_up_volume_shrink_backtest.buy_date IS '买入日期';
COMMENT ON COLUMN fact_limit_up_volume_shrink_backtest.buy_price IS '买入价格';
COMMENT ON COLUMN fact_limit_up_volume_shrink_backtest.sell_date IS '卖出日期';
COMMENT ON COLUMN fact_limit_up_volume_shrink_backtest.sell_price IS '卖出价格';
COMMENT ON COLUMN fact_limit_up_volume_shrink_backtest.return_pct IS '收益率（小数，如0.15表示15%）';
COMMENT ON COLUMN fact_limit_up_volume_shrink_backtest.hold_days IS '持有天数（交易日）';
COMMENT ON COLUMN fact_limit_up_volume_shrink_backtest.exit_reason IS '退出原因：profit_target(止盈), stop_loss(止损), time_limit(时间限制)';
