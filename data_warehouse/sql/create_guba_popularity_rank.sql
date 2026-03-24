-- 股吧人气榜表
CREATE TABLE IF NOT EXISTS fact_guba_popularity_rank (
    id SERIAL PRIMARY KEY,
    crawl_date DATE NOT NULL,
    crawl_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    rank_position INTEGER NOT NULL,
    rank_change INTEGER DEFAULT 0,
    ts_code VARCHAR(20) NOT NULL,
    stock_name VARCHAR(100) NOT NULL,
    latest_price NUMERIC(10, 2),
    change_amount NUMERIC(10, 2),
    change_pct NUMERIC(8, 2),
    new_fans NUMERIC(6, 2),
    loyal_fans NUMERIC(6, 2),
    CONSTRAINT idx_guba_rank_date_code UNIQUE (crawl_date, ts_code)
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_guba_rank_date ON fact_guba_popularity_rank(crawl_date);
CREATE INDEX IF NOT EXISTS idx_guba_rank_code ON fact_guba_popularity_rank(ts_code);
CREATE INDEX IF NOT EXISTS idx_guba_rank_date_position ON fact_guba_popularity_rank(crawl_date, rank_position);

COMMENT ON TABLE fact_guba_popularity_rank IS '股吧人气榜数据表';
COMMENT ON COLUMN fact_guba_popularity_rank.id IS '主键ID';
COMMENT ON COLUMN fact_guba_popularity_rank.crawl_date IS '爬取日期';
COMMENT ON COLUMN fact_guba_popularity_rank.crawl_time IS '爬取时间';
COMMENT ON COLUMN fact_guba_popularity_rank.rank_position IS '当前排名';
COMMENT ON COLUMN fact_guba_popularity_rank.rank_change IS '排名较昨日变动（正数=上升，负数=下降）';
COMMENT ON COLUMN fact_guba_popularity_rank.ts_code IS '股票代码';
COMMENT ON COLUMN fact_guba_popularity_rank.stock_name IS '股票名称';
COMMENT ON COLUMN fact_guba_popularity_rank.latest_price IS '最新价';
COMMENT ON COLUMN fact_guba_popularity_rank.change_amount IS '涨跌额';
COMMENT ON COLUMN fact_guba_popularity_rank.change_pct IS '涨跌幅(%)';
COMMENT ON COLUMN fact_guba_popularity_rank.new_fans IS '新晋粉丝百分比';
COMMENT ON COLUMN fact_guba_popularity_rank.loyal_fans IS '铁杆粉丝百分比';

