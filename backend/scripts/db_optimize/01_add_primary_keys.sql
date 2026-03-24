-- ============================================================
-- 数据库优化脚本 01: 添加缺失的主键约束
-- ============================================================

-- 1. dim_stock 添加主键
ALTER TABLE dim_stock ADD CONSTRAINT dim_stock_pkey PRIMARY KEY (ts_code);

-- 2. dim_sector 添加主键
ALTER TABLE dim_sector ADD CONSTRAINT dim_sector_pkey PRIMARY KEY (sector_id);

-- 3. dim_stock_universe 添加主键
ALTER TABLE dim_stock_universe ADD CONSTRAINT dim_stock_universe_pkey PRIMARY KEY (ts_code, universe_type, trade_date);

-- 4. dim_hotspot_window 添加主键
ALTER TABLE dim_hotspot_window ADD CONSTRAINT dim_hotspot_window_pkey PRIMARY KEY (id);

-- 5. dim_sector_rotation_config 添加主键
ALTER TABLE dim_sector_rotation_config ADD CONSTRAINT dim_sector_rotation_config_pkey PRIMARY KEY (config_id);

-- 6. etl_log 添加主键
ALTER TABLE etl_log ADD CONSTRAINT etl_log_pkey PRIMARY KEY (id);

-- 7. fact_daily_fundamental 添加主键
ALTER TABLE fact_daily_fundamental ADD CONSTRAINT fact_daily_fundamental_pkey PRIMARY KEY (ts_code, trade_date);

