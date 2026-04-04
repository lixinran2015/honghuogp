-- 短线信号跟踪表
-- 用于记录每日推荐信号的后续表现，支撑回测验证与模型监控

CREATE TABLE IF NOT EXISTS short_term_signal_tracking (
    id SERIAL PRIMARY KEY,
    signal_id VARCHAR(50) UNIQUE NOT NULL,
    ts_code VARCHAR(20) NOT NULL,
    signal_date DATE NOT NULL,
    signal_type VARCHAR(20) NOT NULL,         -- leader / limit_up / startup
    buy_point_type VARCHAR(50),               -- 买点类型：首板放量 / 二板缩量 / 三板换手 / 断板反包 / 龙头首阴 / 分时低吸
    entry_price DECIMAL(10,2),                -- 建议买入价（信号发出日收盘价或开盘价）

    -- 后续表现（每日收盘后更新）
    day1_high DECIMAL(10,2),                  -- 次日最高价
    day1_close DECIMAL(10,2),                 -- 次日收盘价
    day3_max DECIMAL(10,2),                   -- 3日内最高价
    day3_close DECIMAL(10,2),                 -- 第3日收盘价
    day5_max DECIMAL(10,2),                   -- 5日内最高价
    day5_close DECIMAL(10,2),                 -- 第5日收盘价

    -- 退出标记
    exit_price DECIMAL(10,2),                 -- 实际退出价
    exit_date DATE,                           -- 实际退出日期
    exit_reason VARCHAR(20),                  -- stop_loss / take_profit / time_exit / emotion_exit / manual
    total_return DECIMAL(8,4),                -- 总收益率（小数，如 0.0850 = 8.50%）
    max_drawdown DECIMAL(8,4),                -- 最大回撤（小数，负值）
    holding_days INTEGER,                     -- 实际持仓天数

    -- 策略相关
    lstm_mab_score DECIMAL(6,2),              -- 信号发出时的 AI 评分
    grade VARCHAR(2),                         -- 信号发出时的等级 S/A/B/C
    emotion_cycle VARCHAR(20),                -- 信号发出时的情绪周期

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_signal_tracking_ts_code ON short_term_signal_tracking(ts_code);
CREATE INDEX IF NOT EXISTS idx_signal_tracking_date ON short_term_signal_tracking(signal_date);
CREATE INDEX IF NOT EXISTS idx_signal_tracking_exit_date ON short_term_signal_tracking(exit_date);

COMMENT ON TABLE short_term_signal_tracking IS '短线龙头推荐信号跟踪表（用于回测与模型监控）';
