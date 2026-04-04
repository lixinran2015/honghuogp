-- 为 short_term_signal_tracking 表增加实盘交易相关字段
-- 用于 Phase 6 小仓位实盘验证的数据闭环

ALTER TABLE short_term_signal_tracking
ADD COLUMN IF NOT EXISTS prediction_id INTEGER,
ADD COLUMN IF NOT EXISTS actual_entry_price NUMERIC(10, 2),
ADD COLUMN IF NOT EXISTS actual_quantity INTEGER;

COMMENT ON COLUMN short_term_signal_tracking.prediction_id IS '关联的 LSTM-MAB 预测记录 ID';
COMMENT ON COLUMN short_term_signal_tracking.actual_entry_price IS '实际成交买入价';
COMMENT ON COLUMN short_term_signal_tracking.actual_quantity IS '实际成交数量';
