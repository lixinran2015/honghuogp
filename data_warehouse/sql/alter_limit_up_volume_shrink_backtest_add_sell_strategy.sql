-- 为 fact_limit_up_volume_shrink_backtest 表添加 sell_strategy 字段
-- 执行前请先检查字段是否存在，如果已存在则跳过

-- 方法1：直接执行（如果字段已存在会报错，可以忽略）
ALTER TABLE fact_limit_up_volume_shrink_backtest 
ADD COLUMN sell_strategy VARCHAR(50);

-- 添加注释
COMMENT ON COLUMN fact_limit_up_volume_shrink_backtest.sell_strategy IS '卖出策略：profit_stop(止盈止损), ma5_loss(破跌5日线或亏损10%), ma5_loss_5pct(破跌5日线或亏损5%)';
