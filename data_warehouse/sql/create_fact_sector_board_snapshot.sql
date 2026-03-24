-- 东财行业板块快照表（含领涨股）
-- 存储每日/实时拉取的行业板块排名及领涨股数据

CREATE TABLE IF NOT EXISTS fact_sector_board_snapshot (
    trade_date       DATE NOT NULL,
    sector_id        VARCHAR(50) NOT NULL,
    rank             INTEGER,
    name             VARCHAR(100),
    price            NUMERIC(12, 4),
    change_pct       NUMERIC(8, 4),
    change_amount    NUMERIC(12, 4),
    market_cap       NUMERIC(20, 4),
    turnover_rate    NUMERIC(8, 4),
    up_count         INTEGER,
    down_count       INTEGER,
    limit_up_count   INTEGER,
    leader_stock     VARCHAR(64),
    leader_change_pct NUMERIC(8, 4),
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (trade_date, sector_id)
);

CREATE INDEX IF NOT EXISTS ix_fact_sector_board_snapshot_trade_date
    ON fact_sector_board_snapshot (trade_date);
CREATE INDEX IF NOT EXISTS ix_fact_sector_board_snapshot_rank
    ON fact_sector_board_snapshot (trade_date, rank);

COMMENT ON TABLE fact_sector_board_snapshot IS '东财行业板块快照（含领涨股，每日/实时拉取）';
COMMENT ON COLUMN fact_sector_board_snapshot.trade_date IS '交易日期';
COMMENT ON COLUMN fact_sector_board_snapshot.sector_id IS '板块代码（如 BK1027）';
COMMENT ON COLUMN fact_sector_board_snapshot.rank IS '涨跌幅排名';
COMMENT ON COLUMN fact_sector_board_snapshot.name IS '板块名称';
COMMENT ON COLUMN fact_sector_board_snapshot.price IS '最新价/指数';
COMMENT ON COLUMN fact_sector_board_snapshot.change_pct IS '涨跌幅(%)';
COMMENT ON COLUMN fact_sector_board_snapshot.market_cap IS '总市值';
COMMENT ON COLUMN fact_sector_board_snapshot.up_count IS '上涨家数';
COMMENT ON COLUMN fact_sector_board_snapshot.limit_up_count IS '涨停家数';
COMMENT ON COLUMN fact_sector_board_snapshot.leader_stock IS '领涨股名称';
COMMENT ON COLUMN fact_sector_board_snapshot.leader_change_pct IS '领涨股涨跌幅(%)';
