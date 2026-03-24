-- ============================================================
-- 数据库优化脚本 04: 添加优化索引
-- ============================================================

-- 1. fact_daily_price_qfq: 新高查询优化索引
CREATE INDEX IF NOT EXISTS idx_qfq_date_close ON fact_daily_price_qfq(trade_date, close);
CREATE INDEX IF NOT EXISTS idx_qfq_date_high ON fact_daily_price_qfq(trade_date, high);

-- 2. fact_daily_price_qfq: MA均线查询优化
CREATE INDEX IF NOT EXISTS idx_qfq_date_ma10 ON fact_daily_price_qfq(trade_date, ma10);
CREATE INDEX IF NOT EXISTS idx_qfq_date_ma20 ON fact_daily_price_qfq(trade_date, ma20);

-- 3. fact_darwin_result: 按分数排序优化
CREATE INDEX IF NOT EXISTS idx_darwin_date_final_score_desc 
    ON fact_darwin_result(trade_date, final_score DESC NULLS LAST);

-- 4. fact_limit_up_daily: 连板查询优化
CREATE INDEX IF NOT EXISTS idx_limit_up_continuous 
    ON fact_limit_up_daily(trade_date, continuous_days DESC NULLS LAST) 
    WHERE is_continuous = true;

-- 5. fact_user_holding: 状态查询优化
CREATE INDEX IF NOT EXISTS idx_holding_status 
    ON fact_user_holding(status, user_id);

-- 6. dim_stock: 按板块类型查询
CREATE INDEX IF NOT EXISTS idx_stock_exchange ON dim_stock(exchange);
CREATE INDEX IF NOT EXISTS idx_stock_industry ON dim_stock(industry);

-- 7. 分析表统计信息（优化查询计划）
ANALYZE dim_stock;
ANALYZE dim_sector;
ANALYZE fact_daily_price_qfq;
ANALYZE fact_darwin_result;
ANALYZE fact_limit_up_daily;

