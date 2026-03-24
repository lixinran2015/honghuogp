-- 推荐效果追踪表
-- 用于追踪每日推荐股票的表现，计算胜率和收益统计

-- 创建追踪表
CREATE TABLE IF NOT EXISTS fact_recommendation_tracking (
    id SERIAL PRIMARY KEY,
    recommendation_id INTEGER,
    ts_code VARCHAR(10) NOT NULL,
    
    -- 推荐时数据
    recommend_date DATE NOT NULL,
    entry_price NUMERIC(10,2),
    stop_loss_price NUMERIC(10,2),
    target_price_1 NUMERIC(10,2),
    target_price_2 NUMERIC(10,2),
    
    -- 每日追踪数据
    track_date DATE NOT NULL,
    current_price NUMERIC(10,2),
    daily_return_pct NUMERIC(10,2),      -- 当日涨跌幅
    total_return_pct NUMERIC(10,2),      -- 累计收益率
    max_return_pct NUMERIC(10,2),        -- 最大涨幅
    max_drawdown_pct NUMERIC(10,2),      -- 最大回撤
    
    -- 状态标记
    hit_stop_loss BOOLEAN DEFAULT FALSE,  -- 是否触及止损
    hit_target_1 BOOLEAN DEFAULT FALSE,   -- 是否触及目标1
    hit_target_2 BOOLEAN DEFAULT FALSE,   -- 是否触及目标2
    holding_days INTEGER,                 -- 持有自然日
    holding_trading_days INTEGER,         -- 持有交易日（5日/10日收益按此计算）
    
    -- 最终结果（平仓时填写）
    is_closed BOOLEAN DEFAULT FALSE,
    close_date DATE,
    close_price NUMERIC(10,2),
    final_return_pct NUMERIC(10,2),
    close_reason VARCHAR(50),             -- stop_loss/target_reached/manual/timeout
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(recommendation_id, track_date)
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_tracking_ts_code ON fact_recommendation_tracking(ts_code);
CREATE INDEX IF NOT EXISTS idx_tracking_recommend_date ON fact_recommendation_tracking(recommend_date);
CREATE INDEX IF NOT EXISTS idx_tracking_track_date ON fact_recommendation_tracking(track_date);
CREATE INDEX IF NOT EXISTS idx_tracking_is_closed ON fact_recommendation_tracking(is_closed);

-- 为推荐表添加新字段（如果不存在）
DO $$ 
BEGIN
    -- 添加 stop_loss_price 字段
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name = 'fact_recommended_stocks' AND column_name = 'stop_loss_price') THEN
        ALTER TABLE fact_recommended_stocks ADD COLUMN stop_loss_price NUMERIC(10,2);
    END IF;
    
    -- 添加 target_price_1 字段
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name = 'fact_recommended_stocks' AND column_name = 'target_price_1') THEN
        ALTER TABLE fact_recommended_stocks ADD COLUMN target_price_1 NUMERIC(10,2);
    END IF;
    
    -- 添加 target_price_2 字段
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name = 'fact_recommended_stocks' AND column_name = 'target_price_2') THEN
        ALTER TABLE fact_recommended_stocks ADD COLUMN target_price_2 NUMERIC(10,2);
    END IF;
    
    -- 添加 position_suggestion 字段
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name = 'fact_recommended_stocks' AND column_name = 'position_suggestion') THEN
        ALTER TABLE fact_recommended_stocks ADD COLUMN position_suggestion VARCHAR(50);
    END IF;
    
    -- 添加 holding_period 字段
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name = 'fact_recommended_stocks' AND column_name = 'holding_period') THEN
        ALTER TABLE fact_recommended_stocks ADD COLUMN holding_period VARCHAR(50);
    END IF;
    
    -- 添加 ai_analysis 字段
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name = 'fact_recommended_stocks' AND column_name = 'ai_analysis') THEN
        ALTER TABLE fact_recommended_stocks ADD COLUMN ai_analysis TEXT;
    END IF;
    
    -- 添加 dimension_scores 字段（JSON）
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name = 'fact_recommended_stocks' AND column_name = 'dimension_scores') THEN
        ALTER TABLE fact_recommended_stocks ADD COLUMN dimension_scores JSONB;
    END IF;
    
    -- 添加 user_tags 字段（数组）
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name = 'fact_recommended_stocks' AND column_name = 'user_tags') THEN
        ALTER TABLE fact_recommended_stocks ADD COLUMN user_tags TEXT[];
    END IF;
    
END $$;

-- 为追踪表添加 holding_trading_days 列（用于 5日/10日收益按交易日计算）
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name = 'fact_recommendation_tracking' AND column_name = 'holding_trading_days') THEN
        ALTER TABLE fact_recommendation_tracking ADD COLUMN holding_trading_days INTEGER;
    END IF;
END $$;

-- 添加注释
COMMENT ON TABLE fact_recommendation_tracking IS '推荐股票效果追踪表';
COMMENT ON COLUMN fact_recommendation_tracking.recommendation_id IS '关联推荐表ID';
COMMENT ON COLUMN fact_recommendation_tracking.ts_code IS '股票代码';
COMMENT ON COLUMN fact_recommendation_tracking.recommend_date IS '推荐日期';
COMMENT ON COLUMN fact_recommendation_tracking.entry_price IS '推荐买入价';
COMMENT ON COLUMN fact_recommendation_tracking.stop_loss_price IS '止损价';
COMMENT ON COLUMN fact_recommendation_tracking.target_price_1 IS '第一目标价';
COMMENT ON COLUMN fact_recommendation_tracking.target_price_2 IS '第二目标价';
COMMENT ON COLUMN fact_recommendation_tracking.track_date IS '追踪日期';
COMMENT ON COLUMN fact_recommendation_tracking.current_price IS '当日收盘价';
COMMENT ON COLUMN fact_recommendation_tracking.total_return_pct IS '累计收益率';
COMMENT ON COLUMN fact_recommendation_tracking.max_return_pct IS '期间最大涨幅';
COMMENT ON COLUMN fact_recommendation_tracking.max_drawdown_pct IS '期间最大回撤';
COMMENT ON COLUMN fact_recommendation_tracking.hit_stop_loss IS '是否触及止损';
COMMENT ON COLUMN fact_recommendation_tracking.hit_target_1 IS '是否触及目标1';
COMMENT ON COLUMN fact_recommendation_tracking.hit_target_2 IS '是否触及目标2';
COMMENT ON COLUMN fact_recommendation_tracking.holding_days IS '持有自然日';
COMMENT ON COLUMN fact_recommendation_tracking.holding_trading_days IS '持有交易日（5日/10日收益按此计算）';
COMMENT ON COLUMN fact_recommendation_tracking.is_closed IS '是否已平仓';
COMMENT ON COLUMN fact_recommendation_tracking.close_reason IS '平仓原因：stop_loss/target_reached/manual/timeout';
