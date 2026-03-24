-- 数据仓库数据库表结构
-- PostgreSQL 14+

-- ============================================
-- 维度表（Dim）
-- ============================================

-- 股票维表
CREATE TABLE IF NOT EXISTS dim_stock (
    ts_code        VARCHAR(20) PRIMARY KEY,  -- tushare 风格，如 600519.SH
    exchange       VARCHAR(10) NOT NULL,     -- SSE / SZSE / BSE
    symbol         VARCHAR(10) NOT NULL,     -- 600519
    name           VARCHAR(50) NOT NULL,
    list_date      DATE,
    delist_date    DATE,
    industry       VARCHAR(100),
    concept_tags   TEXT[],                   -- 概念标签数组
    updated_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_dim_stock_exchange ON dim_stock(exchange);
CREATE INDEX IF NOT EXISTS idx_dim_stock_symbol ON dim_stock(symbol);

-- 交易日历
CREATE TABLE IF NOT EXISTS dim_trade_calendar (
    trade_date DATE PRIMARY KEY,
    is_open    BOOLEAN NOT NULL DEFAULT TRUE,
    exchange   VARCHAR(10) NOT NULL,  -- SSE / SZSE
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_dim_trade_calendar_exchange ON dim_trade_calendar(exchange, is_open);

-- ============================================
-- 原始层（Raw Layer）
-- ============================================

-- 日线行情原始表
CREATE TABLE IF NOT EXISTS raw_daily_price (
    id           BIGSERIAL PRIMARY KEY,
    ts_code      VARCHAR(20) NOT NULL,
    trade_date   DATE NOT NULL,
    open         NUMERIC(12,4),
    high         NUMERIC(12,4),
    low          NUMERIC(12,4),
    close        NUMERIC(12,4),
    pre_close    NUMERIC(12,4),
    vol          NUMERIC(20,4),   -- 手
    amount       NUMERIC(20,4),   -- 元
    turnover_rate NUMERIC(8,4),   -- 换手率（%）
    source       VARCHAR(20) NOT NULL,  -- 'tushare' | 'akshare' | 'eastmoney'
    raw_payload  JSONB,           -- 原始返回(备查)
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(ts_code, trade_date, source)
);

CREATE INDEX IF NOT EXISTS idx_raw_daily_price_key ON raw_daily_price(ts_code, trade_date, source);
CREATE INDEX IF NOT EXISTS idx_raw_daily_price_date ON raw_daily_price(trade_date);
CREATE INDEX IF NOT EXISTS idx_raw_daily_price_source ON raw_daily_price(source);

-- 财务数据原始表
CREATE TABLE IF NOT EXISTS raw_fundamental (
    id            BIGSERIAL PRIMARY KEY,
    ts_code       VARCHAR(20) NOT NULL,
    end_date      DATE NOT NULL,           -- 报告期
    report_type   VARCHAR(20) NOT NULL,    -- 'annual','q1','q2','q3'
    roe           NUMERIC(8,4),            -- ROE（%）
    net_margin    NUMERIC(8,4),            -- 净利率（%）
    gross_margin  NUMERIC(8,4),            -- 毛利率（%）
    op_cf         NUMERIC(20,4),            -- 经营现金流（元）
    total_debt    NUMERIC(20,4),            -- 总负债（元）
    total_asset   NUMERIC(20,4),            -- 总资产（元）
    debt_ratio    NUMERIC(8,4),            -- 负债率（%）
    profit_volatility NUMERIC(8,4),       -- 盈利波动率
    source        VARCHAR(20) NOT NULL,    -- 'tushare','akshare',etc.
    raw_payload   JSONB,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(ts_code, end_date, report_type, source)
);

CREATE INDEX IF NOT EXISTS idx_raw_fundamental_key ON raw_fundamental(ts_code, end_date, report_type, source);
CREATE INDEX IF NOT EXISTS idx_raw_fundamental_date ON raw_fundamental(end_date);

-- ============================================
-- 标准层（Clean Layer）
-- ============================================

-- 标准日线行情表
CREATE TABLE IF NOT EXISTS fact_daily_price (
    ts_code      VARCHAR(20) NOT NULL,
    trade_date   DATE NOT NULL,
    open         NUMERIC(12,4) NOT NULL,
    high         NUMERIC(12,4) NOT NULL,
    low          NUMERIC(12,4) NOT NULL,
    close        NUMERIC(12,4) NOT NULL,
    pre_close    NUMERIC(12,4),
    vol          NUMERIC(20,4),   -- 手
    amount       NUMERIC(20,4),   -- 元
    turnover_rate NUMERIC(8,4),   -- 换手率（%）
    avg_volume_5  NUMERIC(20,4),  -- 5日均量（手）
    data_quality VARCHAR(10) NOT NULL DEFAULT 'B',  -- 'A','B','C' 等级
    sources_used VARCHAR(50)[],  -- 实际参与合并的数据源数组
    updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ts_code, trade_date)
);

CREATE INDEX IF NOT EXISTS idx_fact_daily_price_date ON fact_daily_price(trade_date);
CREATE INDEX IF NOT EXISTS idx_fact_daily_price_quality ON fact_daily_price(data_quality);

-- 标准财务数据表
CREATE TABLE IF NOT EXISTS fact_fundamental (
    ts_code       VARCHAR(20) NOT NULL,
    end_date      DATE NOT NULL,
    report_type   VARCHAR(20) NOT NULL,
    roe           NUMERIC(8,4),
    net_margin    NUMERIC(8,4),
    gross_margin  NUMERIC(8,4),
    op_cf         NUMERIC(20,4),
    total_debt    NUMERIC(20,4),
    total_asset   NUMERIC(20,4),
    debt_ratio    NUMERIC(8,4),
    profit_volatility NUMERIC(8,4),
    data_quality  VARCHAR(10) NOT NULL DEFAULT 'B',
    sources_used  VARCHAR(50)[],
    updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ts_code, end_date, report_type)
);

CREATE INDEX IF NOT EXISTS idx_fact_fundamental_date ON fact_fundamental(end_date);

-- 每日基本面指标表（每日估值指标：PE、PB、ROE等）
CREATE TABLE IF NOT EXISTS fact_daily_fundamental (
    ts_code          VARCHAR(20) NOT NULL,
    trade_date       DATE NOT NULL,
    pe_ttm           NUMERIC(20,4),      -- 市盈率(TTM)
    pe_lyr           NUMERIC(20,4),      -- 市盈率(年报LYR)
    pe_mrq           NUMERIC(20,4),      -- 市盈率(最新报告MRQ)
    pe_q4            NUMERIC(20,4),      -- 市盈率(最近一季度*4)
    pe_q2            NUMERIC(20,4),      -- 市盈率(最近半年*2)
    pe_q4_3          NUMERIC(20,4),      -- 市盈率(最近3季度*4/3)
    pe_ttm_excl      NUMERIC(20,4),      -- 市盈率(TTM) 扣除非经常性损益
    pe_lyr_excl      NUMERIC(20,4),      -- 市盈率(年报LYR) 扣除非经常性损益
    pe_mrq_excl      NUMERIC(20,4),      -- 市盈率(最新报告MRQ) 扣除非经常性损益
    pe_q4_excl       NUMERIC(20,4),      -- 市盈率(最近一季度*4) 扣除非经常性损益
    pe_q2_excl       NUMERIC(20,4),      -- 市盈率(最近半年*2) 扣除非经常性损益
    pe_q4_3_excl     NUMERIC(20,4),      -- 市盈率(最近3季度*4/3) 扣除非经常性损益
    pb_lyr           NUMERIC(20,4),      -- 市净率(年报LYR)
    pb_mrq           NUMERIC(20,4),      -- 市净率(最新报告MRQ)
    pb_lyr_excl      NUMERIC(20,4),      -- 市净率(年报LYR) 扣除其他权益工具
    pb_mrq_excl      NUMERIC(20,4),      -- 市净率(最新报告MRQ) 扣除其他权益工具
    roe_ttm          NUMERIC(8,4),      -- ROE(TTM)
    roe_lyr          NUMERIC(8,4),      -- ROE(年报LYR)
    roe_mrq          NUMERIC(8,4),      -- ROE(最新报告MRQ)
    roe_q4           NUMERIC(8,4),      -- ROE(最近一季度*4)
    roe_q2           NUMERIC(8,4),      -- ROE(最近半年*2)
    roe_q4_3         NUMERIC(8,4),      -- ROE(最近3季度*4/3)
    net_margin_ttm   NUMERIC(8,4),      -- 净利率(TTM)
    net_margin_lyr   NUMERIC(8,4),      -- 净利率(年报LYR)
    net_margin_mrq   NUMERIC(8,4),      -- 净利率(最新报告MRQ)
    net_margin_q4    NUMERIC(8,4),      -- 净利率(最近一季度*4)
    net_margin_q2    NUMERIC(8,4),      -- 净利率(最近半年*2)
    net_margin_q4_3  NUMERIC(8,4),      -- 净利率(最近3季度*4/3)
    gross_margin_ttm NUMERIC(8,4),      -- 毛利率(TTM)
    op_cf_ttm        NUMERIC(20,4),      -- 经营现金流(TTM)
    op_cf_lyr        NUMERIC(20,4),      -- 经营现金流(年报LYR)
    op_cf_mrq        NUMERIC(20,4),      -- 经营现金流(最新报告MRQ)
    op_cf_q4         NUMERIC(20,4),      -- 经营现金流(最近一季度*4)
    op_cf_q2         NUMERIC(20,4),      -- 经营现金流(最近半年*2)
    op_cf_q4_3       NUMERIC(20,4),      -- 经营现金流(最近3季度*4/3)
    dividend_yield_ttm NUMERIC(8,4),      -- 股息率(最近12月TTM)
    dividend_yield_lyr NUMERIC(8,4),      -- 股息率(上一年度LFY)
    peg_lyr          NUMERIC(8,4),      -- 历史PEG值(年报增长率)
    peg_mrq          NUMERIC(8,4),      -- 历史PEG值(最新报告增长率)
    peg_q4           NUMERIC(8,4),      -- 历史PEG值(最近1季度*4增长率)
    peg_q2           NUMERIC(8,4),      -- 历史PEG值(最近半年*2增长率)
    peg_q4_3         NUMERIC(8,4),      -- 历史PEG值(最近3季度*4/3增长率)
    peg_ttm_3y       NUMERIC(8,4),      -- 历史PEG值(PE_TTM近3年复合增长率)
    data_quality     VARCHAR(10) NOT NULL DEFAULT 'B',  -- 数据质量：A/B/C
    source           VARCHAR(20) NOT NULL DEFAULT 'fundamental_csv',  -- 数据源
    updated_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ts_code, trade_date)
);

CREATE INDEX IF NOT EXISTS idx_fact_daily_fundamental_date ON fact_daily_fundamental(trade_date);
CREATE INDEX IF NOT EXISTS idx_fact_daily_fundamental_code ON fact_daily_fundamental(ts_code);

-- 前复权日线行情表（用于技术分析和回测）
CREATE TABLE IF NOT EXISTS fact_daily_price_qfq (
    ts_code          VARCHAR(20) NOT NULL,
    trade_date       DATE NOT NULL,
    open             NUMERIC(12,4) NOT NULL,      -- 开盘价（前复权）
    high             NUMERIC(12,4) NOT NULL,      -- 最高价（前复权）
    low              NUMERIC(12,4) NOT NULL,      -- 最低价（前复权）
    close            NUMERIC(12,4) NOT NULL,      -- 收盘价（前复权）
    pre_close        NUMERIC(12,4),              -- 前收盘价（前复权）
    vol              NUMERIC(20,4),              -- 成交量（手）
    amount           NUMERIC(20,4),              -- 成交额（元）
    turnover_rate    NUMERIC(12,4),              -- 换手率（%）
    change_pct       NUMERIC(8,4),              -- 涨跌幅（%）
    pe_ttm           NUMERIC(12,4),              -- 滚动市盈率(TTM)
    pb               NUMERIC(12,4),              -- 市净率
    ps_ttm           NUMERIC(12,4),              -- 滚动市销率(TTM)
    pcf_ttm          NUMERIC(12,4),              -- 滚动市现率(TTM)
    is_suspended     BOOLEAN DEFAULT FALSE,      -- 是否停牌（未停牌=1表示未停牌）
    is_st            BOOLEAN DEFAULT FALSE,      -- 是否ST
    source           VARCHAR(20) NOT NULL DEFAULT 'qfq_csv',  -- 数据源
    updated_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ts_code, trade_date)
);

CREATE INDEX IF NOT EXISTS idx_fact_daily_price_qfq_date ON fact_daily_price_qfq(trade_date);
CREATE INDEX IF NOT EXISTS idx_fact_daily_price_qfq_code ON fact_daily_price_qfq(ts_code);

-- ============================================
-- ETL日志表
-- ============================================

-- ETL执行日志
CREATE TABLE IF NOT EXISTS etl_log (
    id           BIGSERIAL PRIMARY KEY,
    ts_code      VARCHAR(20),
    trade_date   DATE,
    source       VARCHAR(20) NOT NULL,
    data_type    VARCHAR(20) NOT NULL,  -- 'daily_price' | 'fundamental'
    status       VARCHAR(20) NOT NULL,   -- 'success' | 'failed' | 'skipped'
    error_message TEXT,
    records_count INTEGER DEFAULT 0,
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_etl_log_ts_code ON etl_log(ts_code, trade_date);
CREATE INDEX IF NOT EXISTS idx_etl_log_status ON etl_log(status, created_at);

-- ============================================
-- 注释
-- ============================================

COMMENT ON TABLE dim_stock IS '股票维表';
COMMENT ON TABLE dim_trade_calendar IS '交易日历';
COMMENT ON TABLE raw_daily_price IS '日线行情原始表（多数据源）';
COMMENT ON TABLE raw_fundamental IS '财务数据原始表（多数据源）';
COMMENT ON TABLE fact_daily_price IS '标准日线行情表（多源合并后）';
COMMENT ON TABLE fact_fundamental IS '标准财务数据表（多源合并后）';
COMMENT ON TABLE fact_daily_fundamental IS '每日基本面指标表（PE、PB、ROE等每日估值指标）';
COMMENT ON TABLE fact_daily_price_qfq IS '前复权日线行情表（用于技术分析和回测）';
COMMENT ON TABLE etl_log IS 'ETL执行日志';

-- ============================================
-- 数据源二期：新增表结构
-- ============================================

-- 1. 分钟级分时数据表（只保留最近 N 日）
CREATE TABLE IF NOT EXISTS fact_intraday_price_1m (
    ts_code        VARCHAR(20) NOT NULL,                -- 600519.SH
    trade_time     TIMESTAMP   NOT NULL,                -- 精确到分钟
    trade_date     DATE        NOT NULL,
    open           NUMERIC(12,4),
    high           NUMERIC(12,4),
    low            NUMERIC(12,4),
    close          NUMERIC(12,4),
    volume         NUMERIC(20,4),                       -- 分钟成交量（股/手，按源注释）
    amount         NUMERIC(20,4),                       -- 分钟成交额（元）
    avg_price      NUMERIC(12,4),                       -- 分钟均价（腾讯会给）
    source         VARCHAR(20) NOT NULL,                -- tencent/eastmoney
    updated_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ts_code, trade_time)
);

CREATE INDEX IF NOT EXISTS idx_intraday_date 
    ON fact_intraday_price_1m (trade_date);

-- 2. 每日涨停板明细（情绪 & 龙头识别基础）
CREATE TABLE IF NOT EXISTS fact_limit_up_daily (
    ts_code          VARCHAR(20) NOT NULL,
    trade_date       DATE        NOT NULL,
    first_hit_time   TIMESTAMP,             -- 首次触及涨停时间
    last_hit_time    TIMESTAMP,             -- 最后一次封住涨停时间
    is_one_word      BOOLEAN,               -- 是否一字板
    close            NUMERIC(12,4),
    change_pct       NUMERIC(8,4),
    limit_up_price   NUMERIC(12,4),
    turnover_rate    NUMERIC(8,4),
    amount           NUMERIC(20,4),
    seal_amount      NUMERIC(20,4),         -- 涨停板封单金额（东财）
    is_continuous    BOOLEAN,               -- 是否连板
    continuous_days  INTEGER,               -- 连板天数（2、3、4板…）
    limit_reason     TEXT,                  -- 东财/同花顺的涨停原因摘要
    source           VARCHAR(20) NOT NULL,  -- eastmoney 等
    updated_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ts_code, trade_date)
);

CREATE INDEX IF NOT EXISTS idx_limitup_date 
    ON fact_limit_up_daily (trade_date);

-- 3. 市场情绪日度统计
CREATE TABLE IF NOT EXISTS fact_market_emotion_daily (
    trade_date       DATE PRIMARY KEY,
    total_limit_up   INTEGER,       -- 涨停家数
    total_limit_down INTEGER,       -- 跌停家数
    broken_limit_up  INTEGER,       -- 炸板数量
    highest_streak   INTEGER,       -- 市场最高连板高度
    mainline_sector  VARCHAR(100),  -- 主线板块名称（可选，后续策略写入）
    emotion_stage    VARCHAR(20),   -- 冰点/回暖/高潮/退潮/震荡
    updated_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 4. 行业 & 板块维表
CREATE TABLE IF NOT EXISTS dim_sector (
    sector_id     VARCHAR(50) PRIMARY KEY, -- 如 SW_801010 / BK0471 / EM_I_X
    sector_type   VARCHAR(20) NOT NULL,    -- industry / concept / index
    name          VARCHAR(100) NOT NULL,
    level         INTEGER,                 -- 1: 一级行业; 2: 二级; null: 概念
    provider      VARCHAR(20),             -- sw / citic / eastmoney 等
    updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 5.1 股票所属板块（行业/概念）关联
CREATE TABLE IF NOT EXISTS fact_stock_sector (
    ts_code      VARCHAR(20) NOT NULL,
    sector_id    VARCHAR(50) NOT NULL,
    start_date   DATE NOT NULL,
    end_date     DATE,                     -- null 表示当前仍有效
    is_primary   BOOLEAN DEFAULT TRUE,     -- 是否主行业（vs 概念、辅行业）
    updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ts_code, sector_id, start_date)
);

CREATE INDEX IF NOT EXISTS idx_stock_sector_ts 
    ON fact_stock_sector (ts_code);
CREATE INDEX IF NOT EXISTS idx_stock_sector_sector 
    ON fact_stock_sector (sector_id);

-- 5.2 板块指数日线（用于板块热度 & 主线识别）
CREATE TABLE IF NOT EXISTS fact_sector_daily (
    sector_id       VARCHAR(50) NOT NULL,
    trade_date      DATE NOT NULL,
    close           NUMERIC(12,4),
    pre_close       NUMERIC(12,4),
    change_pct      NUMERIC(8,4),
    volume          NUMERIC(20,4),      -- 成交量
    amount          NUMERIC(20,4),      -- 成交额
    num_stocks      INTEGER,            -- 板块成分股数量
    num_up          INTEGER,            -- 上涨家数
    num_limit_up    INTEGER,            -- 涨停家数
    heat_score      NUMERIC(8,4),       -- 板块热度评分（策略层回写）
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (sector_id, trade_date)
);

CREATE INDEX IF NOT EXISTS idx_sector_daily_date 
    ON fact_sector_daily (trade_date);

-- 5.3 事件驱动热点表
CREATE TABLE IF NOT EXISTS fact_event_driven_hotspot (
    event_id          BIGSERIAL PRIMARY KEY,
    event_type        VARCHAR(50) NOT NULL,      -- 'news' / 'policy' / 'meeting' / 'war' / 'other'
    event_title       VARCHAR(200) NOT NULL,
    event_content     TEXT,
    event_date        DATE NOT NULL,
    related_sectors   TEXT[],                    -- 相关板块ID数组
    sentiment_score   NUMERIC(4, 2),             -- 情绪得分 -1到1
    impact_level      VARCHAR(20),               -- 'high' / 'medium' / 'low'
    source_url        VARCHAR(500),
    created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_event_date 
    ON fact_event_driven_hotspot (event_date);
CREATE INDEX IF NOT EXISTS idx_event_type 
    ON fact_event_driven_hotspot (event_type);
CREATE INDEX IF NOT EXISTS idx_event_impact 
    ON fact_event_driven_hotspot (impact_level);

-- 5.4 板块轮动配置表
CREATE TABLE IF NOT EXISTS dim_sector_rotation_config (
    config_id         BIGSERIAL PRIMARY KEY,
    month             INTEGER NOT NULL,          -- 1-12
    sector_id         VARCHAR(50) NOT NULL,
    sector_name       VARCHAR(100),
    rotation_type     VARCHAR(20),               -- 'fixed' / 'seasonal' / 'event'
    priority          INTEGER,                   -- 优先级 1-10
    start_date        DATE,
    end_date          DATE,
    is_active         BOOLEAN DEFAULT TRUE,
    updated_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(month, sector_id)
);

CREATE INDEX IF NOT EXISTS idx_rotation_month 
    ON dim_sector_rotation_config (month);
CREATE INDEX IF NOT EXISTS idx_rotation_sector 
    ON dim_sector_rotation_config (sector_id);
CREATE INDEX IF NOT EXISTS idx_rotation_active 
    ON dim_sector_rotation_config (is_active);

-- 注释
COMMENT ON TABLE fact_intraday_price_1m IS '分钟级分时数据表（只保留最近 N 日）';
COMMENT ON TABLE fact_limit_up_daily IS '每日涨停板明细（情绪 & 龙头识别基础）';
COMMENT ON TABLE fact_market_emotion_daily IS '市场情绪日度统计';
COMMENT ON TABLE dim_sector IS '行业 & 板块维表';
COMMENT ON TABLE fact_stock_sector IS '股票所属板块（行业/概念）关联';
COMMENT ON TABLE fact_sector_daily IS '板块指数日线（用于板块热度 & 主线识别）';
COMMENT ON TABLE fact_event_driven_hotspot IS '事件驱动热点表（新闻、政策、会议、战争等）';
COMMENT ON TABLE dim_sector_rotation_config IS '板块轮动配置表（月度固定板块配置）';

