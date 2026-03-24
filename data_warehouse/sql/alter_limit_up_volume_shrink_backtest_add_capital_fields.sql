-- 添加资金管理相关字段到涨停缩量回测结果表

ALTER TABLE fact_limit_up_volume_shrink_backtest 
ADD COLUMN IF NOT EXISTS buy_amount NUMERIC(20, 2),
ADD COLUMN IF NOT EXISTS buy_quantity INTEGER,
ADD COLUMN IF NOT EXISTS sell_amount NUMERIC(20, 2),
ADD COLUMN IF NOT EXISTS profit_loss NUMERIC(20, 2),
ADD COLUMN IF NOT EXISTS profit_loss_pct NUMERIC(8, 4);

COMMENT ON COLUMN fact_limit_up_volume_shrink_backtest.buy_amount IS '买入金额（元）';
COMMENT ON COLUMN fact_limit_up_volume_shrink_backtest.buy_quantity IS '买入数量（股）';
COMMENT ON COLUMN fact_limit_up_volume_shrink_backtest.sell_amount IS '卖出金额（元）';
COMMENT ON COLUMN fact_limit_up_volume_shrink_backtest.profit_loss IS '盈亏金额（元）';
COMMENT ON COLUMN fact_limit_up_volume_shrink_backtest.profit_loss_pct IS '盈亏比例（%，如-8.17表示-8.17%）';
