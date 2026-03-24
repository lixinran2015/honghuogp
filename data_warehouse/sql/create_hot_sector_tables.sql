-- 热门板块管理表
-- 存储用户自定义的热门板块信息

-- 1. 热门板块表
CREATE TABLE IF NOT EXISTS dim_hot_sector (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,  -- 板块名称
    description TEXT,  -- 板块描述
    sort_order INTEGER DEFAULT 0,  -- 排序序号
    status VARCHAR(20) DEFAULT 'active',  -- 状态：active/inactive
    notes TEXT,  -- 备注信息
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,  -- 创建时间
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,  -- 更新时间
    created_by VARCHAR(50)  -- 创建人（预留）
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_hot_sector_status ON dim_hot_sector(status);
CREATE INDEX IF NOT EXISTS idx_hot_sector_sort ON dim_hot_sector(sort_order);

-- 添加注释
COMMENT ON TABLE dim_hot_sector IS '热门板块表';
COMMENT ON COLUMN dim_hot_sector.id IS '板块ID';
COMMENT ON COLUMN dim_hot_sector.name IS '板块名称';
COMMENT ON COLUMN dim_hot_sector.description IS '板块描述';
COMMENT ON COLUMN dim_hot_sector.sort_order IS '排序序号';
COMMENT ON COLUMN dim_hot_sector.status IS '状态：active/inactive';
COMMENT ON COLUMN dim_hot_sector.notes IS '备注信息';
COMMENT ON COLUMN dim_hot_sector.created_at IS '创建时间';
COMMENT ON COLUMN dim_hot_sector.updated_at IS '更新时间';
COMMENT ON COLUMN dim_hot_sector.created_by IS '创建人（预留）';

-- 2. 热门板块-股票关联表
CREATE TABLE IF NOT EXISTS fact_hot_sector_stock (
    id BIGSERIAL PRIMARY KEY,
    sector_id BIGINT NOT NULL REFERENCES dim_hot_sector(id) ON DELETE CASCADE,  -- 板块ID
    ts_code VARCHAR(20) NOT NULL,  -- 股票代码（Tushare格式，如 600519.SH）
    stock_name VARCHAR(100),  -- 股票名称（冗余存储）
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,  -- 添加时间
    added_by VARCHAR(50),  -- 添加人（预留）
    notes TEXT,  -- 备注
    UNIQUE(sector_id, ts_code)  -- 确保同一板块中股票不重复
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_hot_sector_stock_sector ON fact_hot_sector_stock(sector_id);
CREATE INDEX IF NOT EXISTS idx_hot_sector_stock_code ON fact_hot_sector_stock(ts_code);

-- 添加注释
COMMENT ON TABLE fact_hot_sector_stock IS '热门板块-股票关联表';
COMMENT ON COLUMN fact_hot_sector_stock.id IS '关联ID';
COMMENT ON COLUMN fact_hot_sector_stock.sector_id IS '板块ID';
COMMENT ON COLUMN fact_hot_sector_stock.ts_code IS '股票代码';
COMMENT ON COLUMN fact_hot_sector_stock.stock_name IS '股票名称（冗余存储）';
COMMENT ON COLUMN fact_hot_sector_stock.added_at IS '添加时间';
COMMENT ON COLUMN fact_hot_sector_stock.added_by IS '添加人（预留）';
COMMENT ON COLUMN fact_hot_sector_stock.notes IS '备注';
