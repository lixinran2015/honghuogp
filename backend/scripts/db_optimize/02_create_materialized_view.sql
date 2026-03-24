-- ============================================================
-- 数据库优化脚本 02: 用物化视图替代 fact_base_universe_daily
-- ============================================================

-- 步骤1: 创建物化视图（替代冗余表）
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_base_universe_daily AS
SELECT 
    qfq.ts_code,
    qfq.trade_date,
    qfq.open,
    qfq.high,
    qfq.low,
    qfq.close,
    qfq.pre_close,
    qfq.vol,
    qfq.amount,
    qfq.turnover_rate,
    qfq.change_pct,
    qfq.pe_ttm,
    qfq.pb,
    qfq.ps_ttm,
    qfq.pcf_ttm,
    qfq.is_suspended,
    qfq.is_st,
    qfq.ma5,
    qfq.ma10,
    qfq.ma20,
    qfq.ma60,
    qfq.avg_volume_5,
    qfq.volume_ratio,
    qfq.slope_ma20,
    'mv_qfq' as source
FROM fact_daily_price_qfq qfq
INNER JOIN dim_stock ds ON qfq.ts_code = ds.ts_code
WHERE 
    -- 基础股票池过滤条件：创业板/科创板 + 非ST
    (ds.ts_code LIKE '300%' OR ds.ts_code LIKE '301%' OR ds.ts_code LIKE '688%')
    AND (ds.name NOT LIKE '%ST%' OR ds.name IS NULL)
    AND qfq.is_st = false;

-- 步骤2: 为物化视图创建索引
CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_base_universe_pk ON mv_base_universe_daily(ts_code, trade_date);
CREATE INDEX IF NOT EXISTS idx_mv_base_universe_date ON mv_base_universe_daily(trade_date);
CREATE INDEX IF NOT EXISTS idx_mv_base_universe_code ON mv_base_universe_daily(ts_code);

-- 步骤3: 刷新物化视图的函数
CREATE OR REPLACE FUNCTION refresh_mv_base_universe()
RETURNS void AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_base_universe_daily;
END;
$$ LANGUAGE plpgsql;

-- 注意：执行后需要修改代码中对 fact_base_universe_daily 的引用
-- 改为使用 mv_base_universe_daily

-- 如果确认物化视图工作正常，可以删除旧表：
-- DROP TABLE IF EXISTS fact_base_universe_daily;

