-- 行业龙头股票表（静态权威数据）
-- 存储各行各业的龙头股票，用于AI诊断参考和RAG知识库

CREATE TABLE IF NOT EXISTS dim_industry_leader (
    id BIGSERIAL PRIMARY KEY,
    
    -- 股票信息
    ts_code VARCHAR(20) NOT NULL,
    stock_name VARCHAR(100) NOT NULL,
    
    -- 行业信息
    industry VARCHAR(100) NOT NULL,
    sector_code VARCHAR(50),
    sector_name VARCHAR(100),
    
    -- 龙头信息
    leader_type VARCHAR(50) NOT NULL,  -- 行业龙头/板块龙头/细分龙头
    leader_reason TEXT,  -- 为什么是龙头（50-200字）
    main_business TEXT,  -- 主营业务
    
    -- 财务指标（可选）
    market_cap NUMERIC(20, 2),  -- 市值（亿元）
    roe NUMERIC(8, 4),  -- ROE
    revenue_growth NUMERIC(8, 4),  -- 营收增长率
    
    -- 元数据
    source VARCHAR(50) DEFAULT 'manual',  -- 数据来源：manual/api/expert
    is_active BOOLEAN DEFAULT TRUE,  -- 是否有效
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- 唯一约束：同一股票在同一行业只能有一条记录
    CONSTRAINT uk_industry_leader_ts_industry UNIQUE (ts_code, industry)
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_industry_leader_ts_code ON dim_industry_leader(ts_code);
CREATE INDEX IF NOT EXISTS idx_industry_leader_industry ON dim_industry_leader(industry);
CREATE INDEX IF NOT EXISTS idx_industry_leader_sector_code ON dim_industry_leader(sector_code);
CREATE INDEX IF NOT EXISTS idx_industry_leader_active ON dim_industry_leader(is_active);

-- 添加注释
COMMENT ON TABLE dim_industry_leader IS '行业龙头股票表（静态权威数据）';
COMMENT ON COLUMN dim_industry_leader.ts_code IS '股票代码';
COMMENT ON COLUMN dim_industry_leader.stock_name IS '股票名称';
COMMENT ON COLUMN dim_industry_leader.industry IS '所属行业';
COMMENT ON COLUMN dim_industry_leader.sector_code IS '板块代码（关联dim_sector）';
COMMENT ON COLUMN dim_industry_leader.sector_name IS '板块名称';
COMMENT ON COLUMN dim_industry_leader.leader_type IS '龙头类型：行业龙头/板块龙头/细分龙头';
COMMENT ON COLUMN dim_industry_leader.leader_reason IS '龙头判断理由';
COMMENT ON COLUMN dim_industry_leader.main_business IS '主营业务';
COMMENT ON COLUMN dim_industry_leader.market_cap IS '市值（亿元）';
COMMENT ON COLUMN dim_industry_leader.source IS '数据来源：manual（手动导入）/api（API获取）/expert（专家标注）';
