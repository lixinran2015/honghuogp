-- 为 fact_limit_up_volume_shrink 表添加 strategy_type 字段
-- 用于区分主板涨停缩量策略和创业板科创板涨幅缩量策略

-- 1. 添加 strategy_type 字段
ALTER TABLE fact_limit_up_volume_shrink 
ADD COLUMN IF NOT EXISTS strategy_type VARCHAR(50) NOT NULL DEFAULT 'mainboard_limit_up';

-- 2. 添加注释
COMMENT ON COLUMN fact_limit_up_volume_shrink.strategy_type IS '策略类型：mainboard_limit_up(主板涨停缩量), cyb_rise_shrink(创业板科创板涨幅缩量)';

-- 3. 创建索引以提高查询性能
CREATE INDEX IF NOT EXISTS idx_limit_up_volume_shrink_strategy_type_trade_date 
ON fact_limit_up_volume_shrink(strategy_type, trade_date DESC);

CREATE INDEX IF NOT EXISTS idx_limit_up_volume_shrink_strategy_type_ts_code 
ON fact_limit_up_volume_shrink(strategy_type, ts_code);

-- 4. 为现有数据设置默认值（虽然已经有DEFAULT，但确保所有现有记录都有值）
UPDATE fact_limit_up_volume_shrink 
SET strategy_type = 'mainboard_limit_up' 
WHERE strategy_type IS NULL OR strategy_type = '';

