from typing import Optional
import datetime
import decimal

from sqlalchemy import ARRAY, BigInteger, Boolean, Column, Date, DateTime, Double, ForeignKeyConstraint, Index, Integer, JSON, Numeric, PrimaryKeyConstraint, String, Table, Text, Time, UniqueConstraint, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


t_temp_sector_daily_theme_rotation = Table(
    'temp_sector_daily_theme_rotation', Base.metadata,
    Column('sector_id', Text),
    Column('trade_date', Date),
    Column('close', Double(53)),
    Column('pre_close', Text),
    Column('change_pct', Double(53)),
    Column('volume', Double(53)),
    Column('amount', Double(53)),
)


class BtLeaderBuyMeta(Base):
    __tablename__ = 'bt_leader_buy_meta'

    id: Mapped[Optional[int]] = mapped_column(BigInteger, primary_key=True, server_default=text("nextval('bt_leader_buy_meta_id_seq'::regclass)"))
    last_run_start_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    last_run_end_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    rule_version: Mapped[str] = mapped_column(String(32), nullable=False)
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('now()'))


class BtLeaderBuySignals(Base):
    __tablename__ = 'bt_leader_buy_signals'
    __table_args__ = (
        UniqueConstraint('trade_date', 'ts_code', 'signal_type', name='bt_leader_buy_signals_trade_date_ts_code_signal_type_key'),
    )

    id: Mapped[Optional[int]] = mapped_column(BigInteger, primary_key=True, server_default=text("nextval('bt_leader_buy_signals_id_seq'::regclass)"))
    trade_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    ts_code: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(100))
    sector_key: Mapped[str] = mapped_column(String(100))
    sector_name: Mapped[str] = mapped_column(String(200))
    sector_type: Mapped[str] = mapped_column(String(50))
    strength_score: Mapped[Optional[float]] = mapped_column(Double(53))
    signal_type: Mapped[str] = mapped_column(String(10))
    market_regime: Mapped[str] = mapped_column(String(20))
    entry_model: Mapped[str] = mapped_column(String(20))
    entry_price_raw: Mapped[Optional[float]] = mapped_column(Double(53))
    entry_price_with_costs: Mapped[Optional[float]] = mapped_column(Double(53))
    exit_price_5d: Mapped[Optional[float]] = mapped_column(Double(53))
    exit_price_10d: Mapped[Optional[float]] = mapped_column(Double(53))
    ret_5d: Mapped[Optional[float]] = mapped_column(Double(53))
    ret_10d: Mapped[Optional[float]] = mapped_column(Double(53))
    net_ret_5d: Mapped[Optional[float]] = mapped_column(Double(53))
    net_ret_10d: Mapped[Optional[float]] = mapped_column(Double(53))
    max_drawdown_5d: Mapped[Optional[float]] = mapped_column(Double(53))
    max_drawdown_10d: Mapped[Optional[float]] = mapped_column(Double(53))
    benchmark_ret_5d: Mapped[Optional[float]] = mapped_column(Double(53))
    benchmark_ret_10d: Mapped[Optional[float]] = mapped_column(Double(53))
    created_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('now()'))


class DimHotSector(Base):
    __tablename__ = 'dim_hot_sector'
    __table_args__ = (
        Index('idx_hot_sector_sort', 'sort_order'),
        Index('idx_hot_sector_status', 'status'),
    )

    id: Mapped[Optional[int]] = mapped_column(BigInteger, primary_key=True, server_default=text("nextval('dim_hot_sector_id_seq'::regclass)"), comment='板块ID')
    name: Mapped[str] = mapped_column(String(100), nullable=False, comment='板块名称')
    description: Mapped[str] = mapped_column(Text, comment='板块描述')
    sort_order: Mapped[Optional[int]] = mapped_column(Integer, server_default=text('0'), comment='排序序号')
    status: Mapped[str] = mapped_column(String(20), server_default=text("'\1'::character varying"), comment='状态：active/inactive')
    notes: Mapped[str] = mapped_column(Text, comment='备注信息')
    created_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('CURRENT_TIMESTAMP'), comment='创建时间')
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('CURRENT_TIMESTAMP'), comment='更新时间')
    created_by: Mapped[str] = mapped_column(String(50), comment='创建人（预留）')


class DimHotspotCluster(Base):
    __tablename__ = 'dim_hotspot_cluster'

    cluster_id: Mapped[str] = mapped_column(String(64), primary_key=True, comment='热点簇ID，如 EC_D11 / IT_AI / CAP_HIGH_DIV')
    name: Mapped[str] = mapped_column(String(64), nullable=False, comment='热点簇名称，如"双十一热点"')
    category: Mapped[str] = mapped_column(String(32), nullable=False, comment='类别：EC(事件驱动) / IT(产业趋势) / FD(资金结构) / CY(周期) / POL(政策)')
    sectors: Mapped[list] = mapped_column(ARRAY(String()), nullable=False, comment='包含的板块ID列表')
    sector_names: Mapped[Optional[list]] = mapped_column(ARRAY(String()), comment='包含的板块名称列表（冗余，方便查询）')
    weight: Mapped[Optional[dict]] = mapped_column(JSON, comment='每个板块的权重（可选），格式：{"sector_id": 0.3, ...}')
    description: Mapped[str] = mapped_column(String(512), comment='热点簇描述')
    is_active: Mapped[Optional[bool]] = mapped_column(Boolean, comment='是否启用')
    created_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('now()'), comment='创建时间')
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('now()'), comment='更新时间')


class DimIndustryLeader(Base):
    __tablename__ = 'dim_industry_leader'
    __table_args__ = (
        Index('idx_industry_leader_active', 'is_active'),
        Index('idx_industry_leader_industry', 'industry'),
        Index('idx_industry_leader_sector_code', 'sector_code'),
        Index('idx_industry_leader_ts_code', 'ts_code'),
        UniqueConstraint('ts_code', 'industry', name='uk_industry_leader_ts_industry'),
    )

    id: Mapped[Optional[int]] = mapped_column(BigInteger, primary_key=True, server_default=text("nextval('dim_industry_leader_id_seq'::regclass)"))
    ts_code: Mapped[str] = mapped_column(String(20), nullable=False, comment='股票代码')
    stock_name: Mapped[str] = mapped_column(String(100), nullable=False, comment='股票名称')
    industry: Mapped[str] = mapped_column(String(100), nullable=False, comment='所属行业')
    sector_code: Mapped[str] = mapped_column(String(50), comment='板块代码（关联dim_sector）')
    sector_name: Mapped[str] = mapped_column(String(100), comment='板块名称')
    leader_type: Mapped[str] = mapped_column(String(50), nullable=False, comment='龙头类型：行业龙头/板块龙头/细分龙头')
    leader_reason: Mapped[str] = mapped_column(Text, comment='龙头判断理由')
    main_business: Mapped[str] = mapped_column(Text, comment='主营业务')
    market_cap: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(20, 2), comment='市值（亿元）')
    roe: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(8, 4))
    revenue_growth: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(8, 4))
    source: Mapped[str] = mapped_column(String(50), server_default=text("'\1'::character varying"), comment='数据来源：manual（手动导入）/api（API获取）/expert（专家标注）')
    is_active: Mapped[Optional[bool]] = mapped_column(Boolean, server_default=text('true'))
    created_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('CURRENT_TIMESTAMP'))
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('CURRENT_TIMESTAMP'))


class DimScheduledTask(Base):
    __tablename__ = 'dim_scheduled_task'
    __table_args__ = (
        UniqueConstraint('task_name', name='dim_scheduled_task_task_name_key'),
        Index('idx_scheduled_task_enabled', 'is_enabled'),
        Index('idx_scheduled_task_name', 'task_name'),
        Index('idx_scheduled_task_type', 'task_type'),
    )

    id: Mapped[Optional[int]] = mapped_column(Integer, primary_key=True, server_default=text("nextval('dim_scheduled_task_id_seq'::regclass)"))
    task_name: Mapped[str] = mapped_column(String(50), nullable=False)
    task_display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    task_description: Mapped[str] = mapped_column(Text)
    cron_expression: Mapped[str] = mapped_column(String(100))
    schedule_time: Mapped[str] = mapped_column(String(20))
    schedule_days: Mapped[str] = mapped_column(String(50))
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('true'))
    is_running: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('false'))
    task_type: Mapped[str] = mapped_column(String(50), nullable=False)
    task_handler: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('CURRENT_TIMESTAMP'))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('CURRENT_TIMESTAMP'))
    last_run_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)
    next_run_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)


class DimSector(Base):
    __tablename__ = 'dim_sector'

    sector_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment='板块ID，如 SW_801010 / BK0471 / EM_I_X')
    sector_type: Mapped[str] = mapped_column(String(20), nullable=False, comment='板块类型：industry / concept / index')
    name: Mapped[str] = mapped_column(String(100), nullable=False, comment='板块名称')
    level: Mapped[Optional[int]] = mapped_column(Integer, comment='行业级别：1=一级行业; 2=二级; null=概念')
    provider: Mapped[str] = mapped_column(String(20), comment='数据提供商：sw / citic / eastmoney 等')
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('now()'), comment='更新时间')


class DimSectorRotationConfig(Base):
    __tablename__ = 'dim_sector_rotation_config'
    __table_args__ = (
        Index('idx_rotation_month', 'month'),
        Index('idx_rotation_sector', 'sector_id'),
    )

    config_id: Mapped[Optional[int]] = mapped_column(BigInteger, primary_key=True, server_default=text("nextval('dim_sector_rotation_config_config_id_seq'::regclass)"))
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    sector_id: Mapped[str] = mapped_column(String(50), nullable=False)
    sector_name: Mapped[str] = mapped_column(String(100))
    rotation_type: Mapped[str] = mapped_column(String(20))
    priority: Mapped[Optional[int]] = mapped_column(Integer)
    start_date: Mapped[Optional[datetime.date]] = mapped_column(Date)
    end_date: Mapped[Optional[datetime.date]] = mapped_column(Date)
    is_active: Mapped[Optional[bool]] = mapped_column(Boolean, server_default=text('true'))
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('CURRENT_TIMESTAMP'))


class DimStock(Base):
    __tablename__ = 'dim_stock'
    __table_args__ = (
        Index('idx_stock_exchange', 'exchange'),
        Index('idx_stock_industry', 'industry'),
    )

    ts_code: Mapped[str] = mapped_column(String(20), primary_key=True, comment='股票代码（Tushare格式）')
    exchange: Mapped[str] = mapped_column(String(10), nullable=False, comment='交易所：SSE/SZSE/BSE')
    symbol: Mapped[str] = mapped_column(String(10), nullable=False, comment='股票代码（6位数字）')
    name: Mapped[str] = mapped_column(String(50), nullable=False, comment='股票名称')
    list_date: Mapped[Optional[datetime.date]] = mapped_column(Date, comment='上市日期')
    delist_date: Mapped[Optional[datetime.date]] = mapped_column(Date, comment='退市日期')
    industry: Mapped[str] = mapped_column(String(100), comment='行业')
    concept_tags: Mapped[Optional[list]] = mapped_column(ARRAY(String()), comment='概念标签数组')
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('now()'), comment='更新时间')
    created_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('now()'), comment='创建时间')
    industry_simple: Mapped[str] = mapped_column(String(50), comment='行业简称（用于显示）')


class DimTradeCalendar(Base):
    __tablename__ = 'dim_trade_calendar'

    trade_date: Mapped[Optional[datetime.date]] = mapped_column(Date, primary_key=True, comment='交易日期')
    is_open: Mapped[bool] = mapped_column(Boolean, nullable=False, comment='是否开市')
    exchange: Mapped[str] = mapped_column(String(10), nullable=False, comment='交易所：SSE/SZSE')
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('now()'), comment='更新时间')


class EtlLog(Base):
    __tablename__ = 'etl_log'
    __table_args__ = (
        Index('idx_etl_log_ts_code_date', 'ts_code', 'trade_date'),
        Index('ix_etl_log_created_at', 'created_at'),
    )

    id: Mapped[Optional[int]] = mapped_column(BigInteger, primary_key=True, server_default=text("nextval('etl_log_id_seq'::regclass)"))
    ts_code: Mapped[str] = mapped_column(String(20), comment='股票代码')
    trade_date: Mapped[Optional[datetime.date]] = mapped_column(Date, comment='交易日期')
    source: Mapped[str] = mapped_column(String(20), nullable=False, comment='数据源')
    data_type: Mapped[str] = mapped_column(String(20), nullable=False, comment='数据类型：daily_price/fundamental')
    status: Mapped[str] = mapped_column(String(20), nullable=False, comment='状态：success/failed/skipped')
    error_message: Mapped[str] = mapped_column(Text, comment='错误信息')
    records_count: Mapped[Optional[int]] = mapped_column(Integer, comment='记录数')
    created_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('now()'), comment='创建时间')


class FactAbnormalAnalysis(Base):
    __tablename__ = 'fact_abnormal_analysis'
    __table_args__ = (
        UniqueConstraint('trade_date', 'symbol', name='fact_abnormal_analysis_trade_date_symbol_key'),
        Index('idx_abnormal_pct_chg', 'pct_chg'),
        Index('idx_abnormal_severity', 'severity'),
        Index('idx_abnormal_symbol', 'symbol'),
        Index('idx_abnormal_trade_date', 'trade_date'),
    )

    id: Mapped[Optional[int]] = mapped_column(Integer, primary_key=True, server_default=text("nextval('fact_abnormal_analysis_id_seq'::regclass)"))
    trade_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    stock_name: Mapped[str] = mapped_column(String(100))
    pct_chg: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(8, 4))
    volume_ratio: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(8, 4))
    turnover_rate: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(8, 4))
    abnormal_types: Mapped[str] = mapped_column(String(200), comment='异动类型：涨停/大涨/大跌/放量/高换手等')
    severity: Mapped[str] = mapped_column(String(20), comment='严重程度：low/medium/high')
    news_count: Mapped[Optional[int]] = mapped_column(Integer, server_default=text('0'))
    announcement_count: Mapped[Optional[int]] = mapped_column(Integer, server_default=text('0'))
    dragon_tiger: Mapped[Optional[bool]] = mapped_column(Boolean, server_default=text('false'))
    block_trade: Mapped[Optional[bool]] = mapped_column(Boolean, server_default=text('false'))
    ai_analysis: Mapped[str] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(String(500))
    events_json: Mapped[Optional[dict]] = mapped_column(JSON)
    created_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('now()'))


class FactAdviceCompliance(Base):
    __tablename__ = 'fact_advice_compliance'
    __table_args__ = (
        Index('idx_compliance_symbol', 'symbol'),
        Index('idx_compliance_user_close', 'user_id', 'close_date'),
    )

    id: Mapped[Optional[int]] = mapped_column(Integer, primary_key=True, server_default=text("nextval('fact_advice_compliance_id_seq'::regclass)"))
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, comment='用户ID')
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, comment='股票代码')
    name: Mapped[str] = mapped_column(String(100), nullable=False, comment='股票名称')
    buy_date: Mapped[datetime.date] = mapped_column(Date, nullable=False, comment='买入日期')
    close_date: Mapped[datetime.date] = mapped_column(Date, nullable=False, comment='清仓日期')
    advice_history: Mapped[Optional[dict]] = mapped_column(JSON, comment='持仓期间每日建议记录（JSON数组）')
    first_advice: Mapped[str] = mapped_column(String(20), comment='首次建议')
    last_advice: Mapped[str] = mapped_column(String(20), comment='清仓前最后建议')
    days_ignored_reduce: Mapped[Optional[int]] = mapped_column(Integer, server_default=text('0'), comment='忽视减仓建议的天数')
    days_ignored_close: Mapped[Optional[int]] = mapped_column(Integer, server_default=text('0'), comment='忽视清仓建议的天数')
    should_reduce_date: Mapped[Optional[datetime.date]] = mapped_column(Date, comment='首次建议减仓日期')
    should_close_date: Mapped[Optional[datetime.date]] = mapped_column(Date, comment='首次建议清仓日期')
    actual_close_date: Mapped[datetime.date] = mapped_column(Date, nullable=False, comment='实际清仓日期')
    profit_rate: Mapped[float] = mapped_column(Double(53), nullable=False, comment='实际盈亏比例（%）')
    close_price: Mapped[Optional[float]] = mapped_column(Double(53), comment='清仓价格')
    daily_close_price: Mapped[Optional[float]] = mapped_column(Double(53), comment='当日收盘价')
    post_close_gain: Mapped[Optional[float]] = mapped_column(Double(53), comment='清仓后涨幅（%）：当日收盘价相对清仓价的涨幅')
    max_profit_rate: Mapped[Optional[float]] = mapped_column(Double(53), comment='期间最大盈利（%）')
    max_loss_rate: Mapped[Optional[float]] = mapped_column(Double(53), comment='期间最大亏损（%）')
    compliance_type: Mapped[str] = mapped_column(String(32), nullable=False, comment='遵从度类型：perfect/good/delayed/ignored_early/ignored_late')
    compliance_score: Mapped[Optional[int]] = mapped_column(Integer, server_default=text('0'), comment='遵从度评分（0-100）')
    review_tags: Mapped[Optional[list]] = mapped_column(ARRAY(String()), comment='复盘标签：如[该止损没止损, 该减仓没减, 卖飞了]')
    review_comment: Mapped[str] = mapped_column(Text, comment='复盘评语')
    created_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('CURRENT_TIMESTAMP'))


class FactDailyFundamental(Base):
    __tablename__ = 'fact_daily_fundamental'

    ts_code: Mapped[str] = mapped_column(String(20), primary_key=True)
    trade_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    pe_ttm: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(12, 4))
    pe_lyr: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(12, 4))
    pe_mrq: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(12, 4))
    pe_q4: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(12, 4))
    pe_q2: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(12, 4))
    pe_q4_3: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(12, 4))
    pe_ttm_excl: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(12, 4))
    pe_lyr_excl: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(12, 4))
    pe_mrq_excl: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(12, 4))
    pe_q4_excl: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(12, 4))
    pe_q2_excl: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(12, 4))
    pe_q4_3_excl: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(12, 4))
    pb_lyr: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(12, 4))
    pb_mrq: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(12, 4))
    pb_lyr_excl: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(12, 4))
    pb_mrq_excl: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(12, 4))
    roe_ttm: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(8, 4))
    roe_lyr: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(8, 4))
    roe_mrq: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(8, 4))
    roe_q4: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(8, 4))
    roe_q2: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(8, 4))
    roe_q4_3: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(8, 4))
    net_margin_ttm: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(8, 4))
    net_margin_lyr: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(8, 4))
    net_margin_mrq: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(8, 4))
    net_margin_q4: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(8, 4))
    net_margin_q2: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(8, 4))
    net_margin_q4_3: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(8, 4))
    gross_margin_ttm: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(8, 4))
    op_cf_ttm: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(20, 4))
    op_cf_lyr: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(20, 4))
    op_cf_mrq: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(20, 4))
    op_cf_q4: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(20, 4))
    op_cf_q2: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(20, 4))
    op_cf_q4_3: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(20, 4))
    dividend_yield_ttm: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(8, 4))
    dividend_yield_lyr: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(8, 4))
    peg_lyr: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(8, 4))
    peg_mrq: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(8, 4))
    peg_q4: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(8, 4))
    peg_q2: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(8, 4))
    peg_q4_3: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(8, 4))
    peg_ttm_3y: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(8, 4))
    data_quality: Mapped[str] = mapped_column(String(10), nullable=False, server_default=text("'\1'::character varying"))
    source: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'\1'::character varying"))
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('CURRENT_TIMESTAMP'))
    revenue_growth_yoy: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(8, 4))
    profit_growth_yoy: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(8, 4))
    revenue_ttm: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(20, 2))
    net_profit_ttm: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(20, 2))
    profit_volatility: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 4))
    op_cf_growth_yoy: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 4))
    debt_ratio: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(8, 4), comment='负债率（小数，如0.5表示50%）')


class FactDailyPriceQfq(Base):
    __tablename__ = 'fact_daily_price_qfq'
    __table_args__ = (
        PrimaryKeyConstraint('ts_code', 'trade_date', name='fact_daily_price_qfq_pkey'),
        Index('idx_qfq_date_close', 'trade_date', 'close'),
        Index('idx_qfq_date_high', 'trade_date', 'high'),
    )

    ts_code: Mapped[str] = mapped_column(String(20), primary_key=True)
    trade_date: Mapped[Optional[datetime.date]] = mapped_column(Date, primary_key=True)
    open: Mapped[decimal.Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    high: Mapped[decimal.Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    low: Mapped[decimal.Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    close: Mapped[decimal.Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    pre_close: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(12, 4))
    vol: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(20, 4))
    amount: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(20, 4))
    turnover_rate: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(12, 4))
    change_pct: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(8, 4))
    pe_ttm: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(12, 4))
    pb: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(12, 4))
    ps_ttm: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(12, 4))
    pcf_ttm: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(12, 4))
    is_suspended: Mapped[Optional[bool]] = mapped_column(Boolean, server_default=text('false'))
    is_st: Mapped[Optional[bool]] = mapped_column(Boolean, server_default=text('false'))
    source: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'\1'::character varying"))
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('CURRENT_TIMESTAMP'))
    ma5: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(12, 4))
    ma10: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(12, 4))
    ma20: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(12, 4))
    ma60: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(12, 4))
    avg_volume_5: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(20, 4))
    volume_ratio: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(8, 4))
    slope_ma20: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(12, 4), comment='MA20斜率（每日变化率）')
    float_share: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(20, 4))
    total_share: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(20, 4))


class FactDarwinResult(Base):
    __tablename__ = 'fact_darwin_result'
    __table_args__ = (
        Index('idx_darwin_date_final_score_desc', 'trade_date', 'final_score'),
        UniqueConstraint('ts_code', 'trade_date', name='idx_darwin_ts_date'),
    )

    id: Mapped[Optional[int]] = mapped_column(Integer, primary_key=True, server_default=text("nextval('fact_darwin_result_id_seq'::regclass)"), comment='自增ID')
    ts_code: Mapped[str] = mapped_column(String(20), nullable=False, comment='股票代码')
    trade_date: Mapped[datetime.date] = mapped_column(Date, nullable=False, comment='交易日期')
    darwin_score: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 4), comment='达尔文评分')
    final_score: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 4), comment='最终评分')
    financial_health: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(6, 4), comment='财务健康度')
    trend_score: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(6, 4), comment='趋势分数')
    sector_heat: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(6, 4), comment='板块热度')
    long_term_tag: Mapped[str] = mapped_column(String(20), comment='长期标签：观察/关注/优选')
    name: Mapped[str] = mapped_column(String(50), comment='股票名称')
    close_price: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(12, 4), comment='收盘价')
    change_pct: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(8, 4), comment='涨跌幅')
    turnover_rate: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(8, 4), comment='换手率')
    amount: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(20, 4), comment='成交额')
    roe: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 4), comment='ROE')
    pe_ttm: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(12, 4), comment='PE(TTM)')
    pb: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 4), comment='PB')
    industry: Mapped[str] = mapped_column(String(50), comment='所属行业')
    is_industry_leader: Mapped[Optional[bool]] = mapped_column(Boolean, comment='是否行业龙头')
    is_today_limit_up: Mapped[Optional[bool]] = mapped_column(Boolean, comment='今日是否涨停')
    continuous_days: Mapped[Optional[int]] = mapped_column(Integer, comment='连板天数')
    extra_data: Mapped[Optional[dict]] = mapped_column(JSON, comment='额外数据')
    generated_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, comment='生成时间')
    created_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('now()'), comment='创建时间')


class FactEventDrivenHotspot(Base):
    __tablename__ = 'fact_event_driven_hotspot'
    __table_args__ = (
        Index('idx_event_date', 'event_date'),
    )

    event_id: Mapped[Optional[int]] = mapped_column(BigInteger, primary_key=True, server_default=text("nextval('fact_event_driven_hotspot_event_id_seq'::regclass)"))
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    event_title: Mapped[str] = mapped_column(String(200), nullable=False)
    event_content: Mapped[str] = mapped_column(Text)
    event_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    related_sectors: Mapped[Optional[list]] = mapped_column(ARRAY(String()))
    sentiment_score: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(4, 2))
    impact_level: Mapped[str] = mapped_column(String(20))
    source_url: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('CURRENT_TIMESTAMP'))
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('CURRENT_TIMESTAMP'))


class FactFundamental(Base):
    __tablename__ = 'fact_fundamental'
    __table_args__ = (
        PrimaryKeyConstraint('ts_code', 'end_date', 'report_type', name='fact_fundamental_pkey'),
        Index('ix_fact_fundamental_end_date', 'end_date'),
    )

    ts_code: Mapped[str] = mapped_column(String(20), primary_key=True, comment='股票代码')
    end_date: Mapped[Optional[datetime.date]] = mapped_column(Date, primary_key=True, comment='报告期')
    report_type: Mapped[str] = mapped_column(String(20), primary_key=True, comment='报告类型：annual/q1/q2/q3')
    roe: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(12, 4), comment='ROE（%）')
    net_margin: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(12, 4), comment='净利率（%）')
    gross_margin: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(12, 4), comment='毛利率（%）')
    op_cf: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(20, 4), comment='经营现金流（元）')
    total_debt: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(20, 4), comment='总负债（元）')
    total_asset: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(20, 4), comment='总资产（元）')
    debt_ratio: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(8, 4), comment='负债率（%）')
    profit_volatility: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(12, 4), comment='盈利波动率')
    data_quality: Mapped[str] = mapped_column(String(10), nullable=False, comment='数据质量：A/B/C')
    sources_used: Mapped[Optional[list]] = mapped_column(ARRAY(String()), comment='实际参与合并的数据源数组')
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('now()'), comment='更新时间')
    revenue: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(20, 4), comment='营业收入（元）')
    revenue_growth: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(12, 4), comment='营收增长率（%）')
    net_profit: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(20, 4), comment='净利润（元）')
    ocf_to_revenue: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(8, 4), comment='经营现金流/营收（%）')
    operate_profit: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(20, 4), comment='营业利润（元）')
    fin_exp: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(20, 4), comment='财务费用（元）')
    goodwill: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(20, 4), comment='商誉（元）')
    total_equity: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(20, 4), comment='归属母公司净资产（元）')
    audit_result: Mapped[str] = mapped_column(String(200), comment='审计意见')
    deduct_net_margin: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(12, 4), comment='扣非净利率（%）')


class FactGubaPopularityRank(Base):
    __tablename__ = 'fact_guba_popularity_rank'
    __table_args__ = (
        Index('idx_guba_rank_code', 'ts_code'),
        Index('idx_guba_rank_date', 'crawl_date'),
        UniqueConstraint('crawl_date', 'ts_code', name='idx_guba_rank_date_code'),
        Index('idx_guba_rank_date_position', 'crawl_date', 'rank_position'),
    )

    id: Mapped[Optional[int]] = mapped_column(Integer, primary_key=True, server_default=text("nextval('fact_guba_popularity_rank_id_seq'::regclass)"), comment='主键ID')
    crawl_date: Mapped[datetime.date] = mapped_column(Date, nullable=False, comment='爬取日期')
    crawl_time: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('CURRENT_TIMESTAMP'), comment='爬取时间')
    rank_position: Mapped[int] = mapped_column(Integer, nullable=False, comment='当前排名')
    rank_change: Mapped[Optional[int]] = mapped_column(Integer, server_default=text('0'), comment='排名较昨日变动（正数=上升，负数=下降）')
    ts_code: Mapped[str] = mapped_column(String(20), nullable=False, comment='股票代码')
    stock_name: Mapped[str] = mapped_column(String(100), nullable=False, comment='股票名称')
    latest_price: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2), comment='最新价')
    change_amount: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2), comment='涨跌额')
    change_pct: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(8, 2), comment='涨跌幅(%)')
    new_fans: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(6, 2), comment='新晋粉丝百分比')
    loyal_fans: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(6, 2), comment='铁杆粉丝百分比')


class FactGubaRankHistory(Base):
    __tablename__ = 'fact_guba_rank_history'
    __table_args__ = (
        Index('idx_guba_history_code', 'ts_code'),
        UniqueConstraint('ts_code', 'trade_date', name='idx_guba_history_code_date'),
        Index('idx_guba_history_date', 'trade_date'),
    )

    id: Mapped[Optional[int]] = mapped_column(Integer, primary_key=True, server_default=text("nextval('fact_guba_rank_history_id_seq'::regclass)"), comment='主键ID')
    ts_code: Mapped[str] = mapped_column(String(20), nullable=False, comment='股票代码')
    trade_date: Mapped[datetime.date] = mapped_column(Date, nullable=False, comment='交易日期')
    rank_position: Mapped[int] = mapped_column(Integer, nullable=False, comment='排名位置')
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('CURRENT_TIMESTAMP'), comment='创建时间')


class FactHigh180dBroken(Base):
    __tablename__ = 'fact_high180d_broken'
    __table_args__ = (
        Index('idx_high180d_broken_broken_date', 'broken_date'),
        UniqueConstraint('ts_code', name='uk_high180d_broken_ts'),
    )

    id: Mapped[Optional[int]] = mapped_column(BigInteger, primary_key=True, server_default=text("nextval('fact_high180d_broken_id_seq'::regclass)"))
    ts_code: Mapped[str] = mapped_column(String(20), nullable=False)
    broken_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    created_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('CURRENT_TIMESTAMP'))


class FactHotSectorStock(Base):
    __tablename__ = 'fact_hot_sector_stock'
    __table_args__ = (
        UniqueConstraint('sector_id', 'ts_code', name='fact_hot_sector_stock_sector_id_ts_code_key'),
        Index('idx_hot_sector_stock_code', 'ts_code'),
        Index('idx_hot_sector_stock_sector', 'sector_id'),
        ForeignKeyConstraint(['sector_id'], ['dim_hot_sector.id']),
    )

    id: Mapped[Optional[int]] = mapped_column(BigInteger, primary_key=True, server_default=text("nextval('fact_hot_sector_stock_id_seq'::regclass)"), comment='关联ID')
    sector_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment='板块ID')
    ts_code: Mapped[str] = mapped_column(String(20), nullable=False, comment='股票代码')
    stock_name: Mapped[str] = mapped_column(String(100), comment='股票名称（冗余存储）')
    added_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('CURRENT_TIMESTAMP'), comment='添加时间')
    added_by: Mapped[str] = mapped_column(String(50), comment='添加人（预留）')
    notes: Mapped[str] = mapped_column(Text, comment='备注')


class FactHotspotClusterSnapshot(Base):
    __tablename__ = 'fact_hotspot_cluster_snapshot'
    __table_args__ = (
        PrimaryKeyConstraint('window_id', 'cluster_id', name='fact_hotspot_cluster_snapshot_pkey'),
        ForeignKeyConstraint(['cluster_id'], ['dim_hotspot_cluster.cluster_id']),
    )

    window_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    cluster_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    cluster_name: Mapped[str] = mapped_column(String(64), nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    heat_score: Mapped[Optional[float]] = mapped_column(Double(53), comment='总热度分，0~20')
    short_heat_score: Mapped[Optional[float]] = mapped_column(Double(53), comment='短线热度分，0~20')
    swing_heat_score: Mapped[Optional[float]] = mapped_column(Double(53), comment='波段热度分，0~20')
    style_bias: Mapped[str] = mapped_column(String(16), comment='热度风格：short/swing/balanced/cold')
    avg_price_momentum: Mapped[Optional[float]] = mapped_column(Double(53), comment='平均价格动量（板块收益）')
    avg_money_flow: Mapped[Optional[float]] = mapped_column(Double(53), comment='平均资金流（成交额）')
    avg_breadth: Mapped[Optional[float]] = mapped_column(Double(53), comment='平均广度（活跃股比例）')
    avg_event_heat: Mapped[Optional[float]] = mapped_column(Double(53), comment='平均事件热度')
    avg_industry_trend: Mapped[Optional[float]] = mapped_column(Double(53), comment='平均产业趋势')
    avg_capital_preference: Mapped[Optional[float]] = mapped_column(Double(53), comment='平均资金偏好')
    top_sectors: Mapped[Optional[dict]] = mapped_column(JSON, comment='热点簇内部最高热度板块列表，格式：[{"sector_code": "...", "sector_name": "...", "heat_score": 15.2}, ...]')
    sector_scores: Mapped[Optional[dict]] = mapped_column(JSON, comment='所有板块的热度分，格式：{"sector_code": 12.1, ...}')
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('now()'), comment='更新时间')


class FactIntradayPrice1m(Base):
    __tablename__ = 'fact_intraday_price_1m'
    __table_args__ = (
        PrimaryKeyConstraint('ts_code', 'trade_time', name='fact_intraday_price_1m_pkey'),
        Index('ix_fact_intraday_price_1m_trade_date', 'trade_date'),
    )

    ts_code: Mapped[str] = mapped_column(String(20), primary_key=True, comment='股票代码')
    trade_time: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, primary_key=True, comment='精确到分钟')
    trade_date: Mapped[datetime.date] = mapped_column(Date, nullable=False, comment='交易日期')
    open: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(12, 4), comment='开盘价')
    high: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(12, 4), comment='最高价')
    low: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(12, 4), comment='最低价')
    close: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(12, 4), comment='收盘价')
    volume: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(20, 4), comment='分钟成交量（股/手，按源注释）')
    amount: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(20, 4), comment='分钟成交额（元）')
    avg_price: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(12, 4), comment='分钟均价（腾讯会给）')
    source: Mapped[str] = mapped_column(String(20), nullable=False, comment='数据源：tencent/eastmoney')
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('now()'), comment='更新时间')


class FactInvestmentNotes(Base):
    __tablename__ = 'fact_investment_notes'
    __table_args__ = (
        Index('idx_investment_notes_created', 'created_at'),
        Index('idx_investment_notes_symbol', 'symbol'),
        Index('idx_investment_notes_type', 'note_type'),
        Index('idx_investment_notes_user', 'user_id'),
    )

    id: Mapped[Optional[int]] = mapped_column(Integer, primary_key=True, server_default=text("nextval('fact_investment_notes_id_seq'::regclass)"))
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('1'))
    symbol: Mapped[str] = mapped_column(String(20))
    stock_name: Mapped[str] = mapped_column(String(100))
    note_type: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'\1'::character varying"), comment='笔记类型：general-一般笔记, lesson-教训, success-成功经验, mistake-错误总结')
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tags: Mapped[str] = mapped_column(String(500))
    trade_date: Mapped[Optional[datetime.date]] = mapped_column(Date)
    profit_rate: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(8, 4))
    created_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('now()'))
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('now()'))


class FactLeaderDiagnosis(Base):
    __tablename__ = 'fact_leader_diagnosis'
    __table_args__ = (
        Index('idx_leader_diagnosis_generated_at', 'generated_at'),
        Index('idx_leader_diagnosis_trade_date', 'trade_date'),
        Index('idx_leader_diagnosis_ts_code', 'ts_code'),
        UniqueConstraint('ts_code', 'trade_date', name='uk_leader_diagnosis_ts_date'),
    )

    id: Mapped[Optional[int]] = mapped_column(BigInteger, primary_key=True, server_default=text("nextval('fact_leader_diagnosis_id_seq'::regclass)"))
    ts_code: Mapped[str] = mapped_column(String(20), nullable=False, comment='股票代码')
    trade_date: Mapped[datetime.date] = mapped_column(Date, nullable=False, comment='交易日期')
    diagnosis_result: Mapped[dict] = mapped_column(JSON, nullable=False, comment='诊断结果（JSON）：包含analysis, level1_logic, level2_market, level3_timing, recommendation等')
    generated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('CURRENT_TIMESTAMP'), comment='生成时间')
    prompt_tokens: Mapped[Optional[int]] = mapped_column(Integer, comment='Prompt token数量（输入token，用于计算成本）')
    completion_tokens: Mapped[Optional[int]] = mapped_column(Integer, comment='Completion token数量（输出token，通常比输入更贵）')
    total_tokens: Mapped[Optional[int]] = mapped_column(Integer, comment='总token数量（prompt_tokens + completion_tokens，用于成本统计和预算管理）')


class FactLeaderTrackingPool(Base):
    __tablename__ = 'fact_leader_tracking_pool'

    ts_code: Mapped[str] = mapped_column(String(20), primary_key=True, comment='股票代码（Tushare格式）')
    name: Mapped[str] = mapped_column(String(128), nullable=False, comment='股票名称')
    is_space: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('false'), comment='是否为空间龙头（出现过即可）')
    is_new: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('false'), comment='是否为刚启动龙头（出现过即可）')
    first_space_date: Mapped[Optional[datetime.date]] = mapped_column(Date, comment='首次出现为空间龙头的交易日')
    first_new_date: Mapped[Optional[datetime.date]] = mapped_column(Date, comment='首次出现为刚启动龙头的交易日')
    last_seen_date: Mapped[datetime.date] = mapped_column(Date, nullable=False, comment='最近一次进入/命中的交易日')
    sectors: Mapped[dict] = mapped_column(JSON, nullable=False, server_default=text("'[]'::jsonb"), comment='关联主线/板块名称列表')
    continuous_limit: Mapped[Optional[int]] = mapped_column(Integer, comment='连板高度（取历史最大）')
    created_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('now()'), comment='创建时间')
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('now()'), comment='更新时间')


class FactLeaderTrackingPoolSyncLog(Base):
    __tablename__ = 'fact_leader_tracking_pool_sync_log'

    trade_date: Mapped[Optional[datetime.date]] = mapped_column(Date, primary_key=True, comment='交易日')
    synced_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('now()'), comment='同步完成时间')


class FactLimitUpDaily(Base):
    __tablename__ = 'fact_limit_up_daily'
    __table_args__ = (
        PrimaryKeyConstraint('ts_code', 'trade_date', name='fact_limit_up_daily_pkey'),
        Index('idx_limit_up_continuous', 'trade_date', 'continuous_days'),
    )

    ts_code: Mapped[str] = mapped_column(String(20), primary_key=True, comment='股票代码')
    trade_date: Mapped[Optional[datetime.date]] = mapped_column(Date, primary_key=True, comment='交易日期')
    first_hit_time: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, comment='首次触及涨停时间')
    last_hit_time: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, comment='最后一次封住涨停时间')
    is_one_word: Mapped[Optional[bool]] = mapped_column(Boolean, comment='是否一字板')
    close: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(12, 4), comment='收盘价')
    change_pct: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(8, 4), comment='涨跌幅（%）')
    limit_up_price: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(12, 4), comment='涨停价')
    turnover_rate: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(8, 4), comment='换手率（%）')
    amount: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(20, 4), comment='成交额（元）')
    seal_amount: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(20, 4), comment='涨停板封单金额（东财）')
    is_continuous: Mapped[Optional[bool]] = mapped_column(Boolean, comment='是否连板')
    continuous_days: Mapped[Optional[int]] = mapped_column(Integer, comment='连板天数（2、3、4板…）')
    limit_reason: Mapped[str] = mapped_column(Text, comment='东财/同花顺的涨停原因摘要')
    source: Mapped[str] = mapped_column(String(20), nullable=False, comment='数据源：eastmoney 等')
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('now()'), comment='更新时间')


class FactLimitUpToday60dHigh(Base):
    __tablename__ = 'fact_limit_up_today_60d_high'
    __table_args__ = (
        Index('idx_limit_up_60d_change_10d', 'change_10d'),
        Index('idx_limit_up_60d_change_5d', 'change_5d'),
        UniqueConstraint('trade_date', 'ts_code', name='idx_limit_up_60d_date_code'),
        Index('idx_limit_up_60d_is_60d_high', 'is_60d_high'),
        Index('idx_limit_up_60d_rank_position', 'rank_position'),
        Index('idx_limit_up_60d_trade_date', 'trade_date'),
        Index('idx_limit_up_60d_ts_code', 'ts_code'),
    )

    id: Mapped[Optional[int]] = mapped_column(BigInteger, primary_key=True, server_default=text("nextval('fact_limit_up_today_60d_high_id_seq'::regclass)"))
    trade_date: Mapped[datetime.date] = mapped_column(Date, nullable=False, comment='计算日期')
    ts_code: Mapped[str] = mapped_column(String(20), nullable=False, comment='股票代码（Tushare格式）')
    stock_name: Mapped[str] = mapped_column(String(100), comment='股票名称（冗余存储，方便查询）')
    rank_position: Mapped[Optional[int]] = mapped_column(Integer, comment='人气榜排名')
    rank_change: Mapped[Optional[int]] = mapped_column(Integer, comment='排名变动（正数=上升，负数=下降）')
    max_rank: Mapped[Optional[int]] = mapped_column(Integer, comment='计算时使用的人气榜范围（前N名）')
    today_close: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2), comment='今日收盘价')
    change_pct: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(8, 4), comment='今日涨幅（%）')
    change_5d: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(8, 4), comment='近5日涨幅（%）')
    change_10d: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(8, 4), comment='近10日涨幅（%）')
    is_60d_high: Mapped[Optional[bool]] = mapped_column(Boolean, comment='是否60日新高')
    created_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('CURRENT_TIMESTAMP'))
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('CURRENT_TIMESTAMP'))
    amount: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(20, 2), comment='成交额（元）')


class FactLimitUpVolumeShrink(Base):
    __tablename__ = 'fact_limit_up_volume_shrink'
    __table_args__ = (
        UniqueConstraint('trade_date', 'ts_code', name='idx_limit_up_volume_shrink_date_code'),
        Index('idx_limit_up_volume_shrink_limit_up_date', 'limit_up_date'),
        Index('idx_limit_up_volume_shrink_strategy_type_trade_date', 'strategy_type', 'trade_date'),
        Index('idx_limit_up_volume_shrink_strategy_type_ts_code', 'strategy_type', 'ts_code'),
        Index('idx_limit_up_volume_shrink_trade_date', 'trade_date'),
        Index('idx_limit_up_volume_shrink_ts_code', 'ts_code'),
        Index('idx_limit_up_volume_shrink_volume_ratio', 'volume_ratio'),
    )

    id: Mapped[Optional[int]] = mapped_column(BigInteger, primary_key=True, server_default=text("nextval('fact_limit_up_volume_shrink_id_seq'::regclass)"))
    trade_date: Mapped[datetime.date] = mapped_column(Date, nullable=False, comment='计算日期')
    ts_code: Mapped[str] = mapped_column(String(20), nullable=False, comment='股票代码（Tushare格式）')
    stock_name: Mapped[str] = mapped_column(String(100), comment='股票名称（冗余存储，方便查询）')
    limit_up_date: Mapped[Optional[datetime.date]] = mapped_column(Date, comment='最近一次涨停日期')
    limit_up_days_ago: Mapped[Optional[int]] = mapped_column(Integer, comment='距离涨停天数')
    volume_ratio: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(8, 4), comment='当前量比')
    today_close: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2), comment='今日收盘价')
    today_change_pct: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(8, 4), comment='今日涨幅（%）')
    today_amount: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(20, 2), comment='今日成交额（元）')
    created_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('CURRENT_TIMESTAMP'))
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('CURRENT_TIMESTAMP'))
    strategy_type: Mapped[str] = mapped_column(String(50), nullable=False, server_default=text("'\1'::character varying"), comment='策略类型：mainboard_limit_up(主板涨停缩量), cyb_rise_shrink(创业板科创板涨幅缩量)')


class FactLimitUpVolumeShrinkBacktest(Base):
    __tablename__ = 'fact_limit_up_volume_shrink_backtest'
    __table_args__ = (
        Index('idx_backtest_buy_date', 'buy_date'),
        Index('idx_backtest_exit_reason', 'exit_reason'),
        Index('idx_backtest_signal_date', 'signal_date'),
        Index('idx_backtest_strategy_type_signal_date', 'strategy_type', 'signal_date'),
        Index('idx_backtest_strategy_type_ts_code', 'strategy_type', 'ts_code'),
        Index('idx_backtest_ts_code', 'ts_code'),
    )

    id: Mapped[Optional[int]] = mapped_column(BigInteger, primary_key=True, server_default=text("nextval('fact_limit_up_volume_shrink_backtest_id_seq'::regclass)"))
    signal_date: Mapped[datetime.date] = mapped_column(Date, nullable=False, comment='信号日期（找到股票的日期）')
    ts_code: Mapped[str] = mapped_column(String(20), nullable=False, comment='股票代码')
    stock_name: Mapped[str] = mapped_column(String(100))
    buy_date: Mapped[datetime.date] = mapped_column(Date, nullable=False, comment='买入日期')
    buy_price: Mapped[decimal.Decimal] = mapped_column(Numeric(12, 4), nullable=False, comment='买入价格')
    sell_date: Mapped[Optional[datetime.date]] = mapped_column(Date, comment='卖出日期')
    sell_price: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(12, 4), comment='卖出价格')
    return_pct: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(8, 4), comment='收益率（小数，如0.15表示15%）')
    hold_days: Mapped[Optional[int]] = mapped_column(Integer, comment='持有天数（交易日）')
    exit_reason: Mapped[str] = mapped_column(String(50), comment='退出原因：profit_target(止盈), stop_loss(止损), time_limit(时间限制)')
    profit_target: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(8, 4))
    stop_loss: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(8, 4))
    max_hold_days: Mapped[Optional[int]] = mapped_column(Integer)
    created_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('CURRENT_TIMESTAMP'))
    sell_strategy: Mapped[str] = mapped_column(String(50), comment='卖出策略：profit_stop(止盈止损), ma5_loss(破跌5日线或亏损10%), ma5_loss_5pct(破跌5日线或亏损5%)')
    buy_amount: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(20, 2), comment='买入金额（元）')
    buy_quantity: Mapped[Optional[int]] = mapped_column(Integer, comment='买入数量（股）')
    sell_amount: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(20, 2), comment='卖出金额（元）')
    profit_loss: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(20, 2), comment='盈亏金额（元）')
    profit_loss_pct: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(8, 4), comment='盈亏比例（%，如-8.17表示-8.17%）')
    strategy_type: Mapped[str] = mapped_column(String(50), nullable=False, server_default=text("'\1'::character varying"), comment='策略类型：mainboard_limit_up(主板涨停缩量), cyb_rise_shrink(创业板科创板涨幅缩量)')


class FactMarketEmotionDaily(Base):
    __tablename__ = 'fact_market_emotion_daily'

    trade_date: Mapped[Optional[datetime.date]] = mapped_column(Date, primary_key=True, comment='交易日期')
    total_limit_up: Mapped[Optional[int]] = mapped_column(Integer, comment='涨停家数')
    total_limit_down: Mapped[Optional[int]] = mapped_column(Integer, comment='跌停家数')
    broken_limit_up: Mapped[Optional[int]] = mapped_column(Integer, comment='炸板数量')
    highest_streak: Mapped[Optional[int]] = mapped_column(Integer, comment='市场最高连板高度')
    mainline_sector: Mapped[str] = mapped_column(String(100), comment='主线板块名称（可选，后续策略写入）')
    emotion_stage: Mapped[str] = mapped_column(String(20), comment='情绪阶段：冰点/回暖/高潮/退潮/震荡')
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('now()'), comment='更新时间')


class FactMoneyFlow(Base):
    __tablename__ = 'fact_money_flow'
    __table_args__ = (
        PrimaryKeyConstraint('ts_code', 'trade_date', name='fact_money_flow_pkey'),
        Index('idx_fact_money_flow_date', 'trade_date'),
        Index('idx_fact_money_flow_ts_code', 'ts_code'),
    )

    ts_code: Mapped[str] = mapped_column(String(20), primary_key=True)
    trade_date: Mapped[Optional[datetime.date]] = mapped_column(Date, primary_key=True)
    main_net_inflow: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(20, 4))
    main_net_inflow_rate: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(8, 4))
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('CURRENT_TIMESTAMP'))


class FactMonitorNear5940(Base):
    __tablename__ = 'fact_monitor_near5_940'
    __table_args__ = (
        Index('idx_monitor_time', 'monitor_time'),
        UniqueConstraint('trade_date', 'monitor_time', 'stock_code', name='uq_monitor_date_time_code'),
    )

    id: Mapped[Optional[int]] = mapped_column(Integer, primary_key=True, server_default=text("nextval('fact_monitor_near5_940_id_seq'::regclass)"), comment='自增ID')
    trade_date: Mapped[datetime.date] = mapped_column(Date, nullable=False, comment='交易日期')
    monitor_time: Mapped[str] = mapped_column(String(255), nullable=False, comment='监控时间点')
    stock_code: Mapped[str] = mapped_column(String(10), nullable=False, comment='股票代码（6位）')
    stock_name: Mapped[str] = mapped_column(String(50), comment='股票名称')
    pct_today: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(8, 4), comment='今日涨幅(%)')
    pct_5d: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(8, 4), comment='5日涨幅(%)')
    pct_10d: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(8, 4), comment='10日涨幅(%)')
    amount: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(20, 4), comment='成交金额(元)')
    created_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('now()'), comment='创建时间')
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('now()'), comment='更新时间')


class FactNorthFlow(Base):
    __tablename__ = 'fact_north_flow'
    __table_args__ = (
        Index('idx_fact_north_flow_date', 'trade_date'),
    )

    trade_date: Mapped[Optional[datetime.date]] = mapped_column(Date, primary_key=True)
    net_amount: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(20, 2))
    hgt: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(20, 2))
    sgt: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(20, 2))
    south_money: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(20, 2))
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('CURRENT_TIMESTAMP'))


class FactNorthHolding(Base):
    __tablename__ = 'fact_north_holding'
    __table_args__ = (
        PrimaryKeyConstraint('ts_code', 'trade_date', name='fact_north_holding_pkey'),
        Index('idx_fact_north_holding_date', 'trade_date'),
        Index('idx_fact_north_holding_ts_code', 'ts_code'),
    )

    ts_code: Mapped[str] = mapped_column(String(20), primary_key=True)
    trade_date: Mapped[Optional[datetime.date]] = mapped_column(Date, primary_key=True)
    hold_vol: Mapped[Optional[int]] = mapped_column(BigInteger)
    hold_ratio: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(8, 4))
    exchange: Mapped[str] = mapped_column(String(10))
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('CURRENT_TIMESTAMP'))


class FactOperationAdviceHistory(Base):
    __tablename__ = 'fact_operation_advice_history'
    __table_args__ = (
        Index('idx_advice_symbol', 'symbol'),
        Index('idx_advice_user_date', 'user_id', 'advice_date'),
        Index('idx_advice_user_symbol_date', 'user_id', 'symbol', 'advice_date'),
    )

    id: Mapped[Optional[int]] = mapped_column(Integer, primary_key=True, server_default=text("nextval('fact_operation_advice_history_id_seq'::regclass)"))
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, comment='用户ID')
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, comment='股票代码（6位数字）')
    name: Mapped[str] = mapped_column(String(100), nullable=False, comment='股票名称')
    advice_date: Mapped[datetime.date] = mapped_column(Date, nullable=False, comment='建议日期')
    today_action: Mapped[str] = mapped_column(String(20), nullable=False, comment='操作建议：buy/add/hold/reduce/close/skip')
    today_action_reason: Mapped[str] = mapped_column(Text, comment='建议原因')
    profit_rate: Mapped[Optional[float]] = mapped_column(Double(53), comment='当日盈亏比例（%）')
    chase_risk_level: Mapped[str] = mapped_column(String(20), comment='追高风险等级：low/medium/high')
    chase_risk_score: Mapped[Optional[float]] = mapped_column(Double(53), comment='追高风险评分（0-100）')
    holding_days: Mapped[Optional[int]] = mapped_column(Integer, comment='持仓天数')
    created_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('CURRENT_TIMESTAMP'))


class FactRecommendationResult(Base):
    __tablename__ = 'fact_recommendation_result'
    __table_args__ = (
        Index('idx_recommendation_date_type', 'trade_date', 'recommendation_type'),
        Index('idx_recommendation_generated', 'generated_at', 'recommendation_type'),
        Index('idx_recommendation_type_score', 'recommendation_type', 'final_score'),
        Index('ix_fact_recommendation_result_ts_code', 'ts_code'),
    )

    id: Mapped[Optional[int]] = mapped_column(Integer, primary_key=True, server_default=text("nextval('fact_recommendation_result_id_seq'::regclass)"), comment='自增ID')
    ts_code: Mapped[str] = mapped_column(String(20), nullable=False, comment='股票代码（Tushare格式）')
    trade_date: Mapped[datetime.date] = mapped_column(Date, nullable=False, comment='交易日期')
    generated_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, comment='生成时间（快照时间点）')
    recommendation_type: Mapped[str] = mapped_column(String(20), nullable=False, comment='推荐类型：today/short/swing/darwin')
    strategy_signal: Mapped[Optional[dict]] = mapped_column(JSON, comment='策略信号数据')
    risk_type: Mapped[str] = mapped_column(String(20), comment='风险类型：attack/bottom_fishing/stable')
    final_score: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(8, 2), comment='综合得分')
    rank_order: Mapped[Optional[int]] = mapped_column(Integer, comment='排序位置（用于取TOP N）')
    recommendation_details: Mapped[Optional[dict]] = mapped_column(JSON, comment='推荐详情（买入区间、理由、建议等）')
    snapshot_price: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(12, 4), comment='快照时刻价格')
    snapshot_change_pct: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(8, 4), comment='快照时刻涨跌幅')
    snapshot_turnover_rate: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(8, 4), comment='快照时刻换手率')
    snapshot_amount: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(20, 4), comment='快照时刻成交额')
    created_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('now()'), comment='创建时间')


class FactRecommendationTracking(Base):
    __tablename__ = 'fact_recommendation_tracking'
    __table_args__ = (
        UniqueConstraint('recommendation_id', 'track_date', name='fact_recommendation_tracking_recommendation_id_track_date_key'),
        Index('idx_tracking_is_closed', 'is_closed'),
        Index('idx_tracking_recommend_date', 'recommend_date'),
        Index('idx_tracking_track_date', 'track_date'),
        Index('idx_tracking_ts_code', 'ts_code'),
    )

    id: Mapped[Optional[int]] = mapped_column(Integer, primary_key=True, server_default=text("nextval('fact_recommendation_tracking_id_seq'::regclass)"))
    recommendation_id: Mapped[Optional[int]] = mapped_column(Integer, comment='关联推荐表ID')
    ts_code: Mapped[str] = mapped_column(String(10), nullable=False, comment='股票代码')
    recommend_date: Mapped[datetime.date] = mapped_column(Date, nullable=False, comment='推荐日期')
    entry_price: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2), comment='推荐买入价')
    stop_loss_price: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2), comment='止损价')
    target_price_1: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2), comment='第一目标价')
    target_price_2: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2), comment='第二目标价')
    track_date: Mapped[datetime.date] = mapped_column(Date, nullable=False, comment='追踪日期')
    current_price: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2), comment='当日收盘价')
    daily_return_pct: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2))
    total_return_pct: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2), comment='累计收益率')
    max_return_pct: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2), comment='期间最大涨幅')
    max_drawdown_pct: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2), comment='期间最大回撤')
    hit_stop_loss: Mapped[Optional[bool]] = mapped_column(Boolean, server_default=text('false'), comment='是否触及止损')
    hit_target_1: Mapped[Optional[bool]] = mapped_column(Boolean, server_default=text('false'), comment='是否触及目标1')
    hit_target_2: Mapped[Optional[bool]] = mapped_column(Boolean, server_default=text('false'), comment='是否触及目标2')
    holding_days: Mapped[Optional[int]] = mapped_column(Integer, comment='持有自然日')
    holding_trading_days: Mapped[Optional[int]] = mapped_column(Integer, comment='持有交易日（5日/10日收益按此计算）')
    is_closed: Mapped[Optional[bool]] = mapped_column(Boolean, server_default=text('false'), comment='是否已平仓')
    close_date: Mapped[Optional[datetime.date]] = mapped_column(Date)
    close_price: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2))
    final_return_pct: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2))
    close_reason: Mapped[str] = mapped_column(String(50), comment='平仓原因：stop_loss/target_reached/manual/timeout')
    created_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('CURRENT_TIMESTAMP'))


class FactRecommendedStocks(Base):
    __tablename__ = 'fact_recommended_stocks'
    __table_args__ = (
        UniqueConstraint('ts_code', 'recommend_date', name='fact_recommended_stocks_ts_code_recommend_date_key'),
        Index('idx_recommended_stocks_date', 'recommend_date'),
        Index('idx_recommended_stocks_status', 'status'),
    )

    id: Mapped[Optional[int]] = mapped_column(Integer, primary_key=True, server_default=text("nextval('fact_recommended_stocks_id_seq'::regclass)"))
    ts_code: Mapped[str] = mapped_column(String(10), nullable=False, comment='股票代码')
    recommend_date: Mapped[datetime.date] = mapped_column(Date, nullable=False, comment='推荐日期')
    entry_price: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2), comment='入选价格')
    current_price: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2), comment='当前价格')
    recommend_reason: Mapped[str] = mapped_column(Text, comment='推荐原因（完整描述）')
    recommend_tags: Mapped[Optional[list]] = mapped_column(ARRAY(String()), comment='推荐标签')
    startup_score: Mapped[Optional[int]] = mapped_column(Integer, comment='启动得分（60-100）')
    signal_strength: Mapped[str] = mapped_column(String(20), comment='信号强度：强/中/弱')
    macd_status: Mapped[str] = mapped_column(String(20))
    kdj_status: Mapped[str] = mapped_column(String(20))
    volume_ratio: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2))
    change_5d: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2))
    change_10d: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2))
    amount: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(20, 2))
    risk_level: Mapped[str] = mapped_column(String(20))
    risk_note: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), server_default=text("'\1'::character varying"), comment='状态：active/closed/stopped')
    stop_loss_price: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2))
    take_profit_price: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2))
    max_gain: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2))
    max_drawdown: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2))
    created_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('CURRENT_TIMESTAMP'))
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('CURRENT_TIMESTAMP'))
    target_price_1: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2))
    target_price_2: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2))
    position_suggestion: Mapped[str] = mapped_column(String(50))
    holding_period: Mapped[str] = mapped_column(String(50))
    ai_analysis: Mapped[str] = mapped_column(Text)
    dimension_scores: Mapped[Optional[dict]] = mapped_column(JSON)
    user_tags: Mapped[Optional[list]] = mapped_column(ARRAY(String()))


class FactSectorBoardSnapshot(Base):
    __tablename__ = 'fact_sector_board_snapshot'
    __table_args__ = (
        PrimaryKeyConstraint('trade_date', 'sector_id', name='fact_sector_board_snapshot_pkey'),
        Index('ix_fact_sector_board_snapshot_rank', 'trade_date', 'rank'),
        Index('ix_fact_sector_board_snapshot_trade_date', 'trade_date'),
    )

    trade_date: Mapped[Optional[datetime.date]] = mapped_column(Date, primary_key=True, comment='交易日期')
    sector_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment='板块代码（如 BK1027）')
    rank: Mapped[Optional[int]] = mapped_column(Integer, comment='涨跌幅排名')
    name: Mapped[str] = mapped_column(String(100), comment='板块名称')
    price: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(12, 4), comment='最新价/指数')
    change_pct: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(8, 4), comment='涨跌幅(%)')
    change_amount: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(12, 4))
    market_cap: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(20, 4), comment='总市值')
    turnover_rate: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(8, 4))
    up_count: Mapped[Optional[int]] = mapped_column(Integer, comment='上涨家数')
    down_count: Mapped[Optional[int]] = mapped_column(Integer)
    limit_up_count: Mapped[Optional[int]] = mapped_column(Integer, comment='涨停家数')
    leader_stock: Mapped[str] = mapped_column(String(64), comment='领涨股名称')
    leader_change_pct: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(8, 4), comment='领涨股涨跌幅(%)')
    created_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('CURRENT_TIMESTAMP'))


class FactSectorDaily(Base):
    __tablename__ = 'fact_sector_daily'
    __table_args__ = (
        PrimaryKeyConstraint('sector_id', 'trade_date', name='fact_sector_daily_pkey'),
        Index('ix_fact_sector_daily_trade_date', 'trade_date'),
    )

    sector_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment='板块ID')
    trade_date: Mapped[Optional[datetime.date]] = mapped_column(Date, primary_key=True, comment='交易日期')
    close: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(12, 4), comment='收盘价')
    pre_close: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(12, 4), comment='前收盘价')
    change_pct: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(8, 4), comment='涨跌幅（%）')
    volume: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(20, 4), comment='成交量')
    amount: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(20, 4), comment='成交额')
    num_stocks: Mapped[Optional[int]] = mapped_column(Integer, comment='板块成分股数量')
    num_up: Mapped[Optional[int]] = mapped_column(Integer, comment='上涨家数')
    num_limit_up: Mapped[Optional[int]] = mapped_column(Integer, comment='涨停家数')
    heat_score: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(8, 4), comment='板块热度评分（策略层回写）')
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('now()'), comment='更新时间')


class FactSectorEvent(Base):
    __tablename__ = 'fact_sector_event'
    __table_args__ = (
        Index('idx_sector_event_date', 'date'),
        Index('idx_sector_event_sector', 'sector_code'),
        Index('idx_sector_event_window', 'window_id'),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    window_id: Mapped[str] = mapped_column(String(64))
    sector_code: Mapped[str] = mapped_column(String(32), nullable=False)
    date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    title: Mapped[str] = mapped_column(String(128), nullable=False)
    summary: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(64), server_default=text("''::character varying"))
    created_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('CURRENT_TIMESTAMP'))
    event_type: Mapped[str] = mapped_column(String(32))
    expected_impact: Mapped[str] = mapped_column(Text)


class FactSectorHeatSnapshot(Base):
    __tablename__ = 'fact_sector_heat_snapshot'
    __table_args__ = (
        PrimaryKeyConstraint('window_id', 'sector_code', name='fact_sector_heat_snapshot_pkey'),
    )

    window_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    sector_code: Mapped[str] = mapped_column(String(32), primary_key=True)
    sector_name: Mapped[str] = mapped_column(String(64), nullable=False)
    return_30d: Mapped[Optional[float]] = mapped_column(Double(53))
    return_index: Mapped[Optional[float]] = mapped_column(Double(53))
    avg_turnover_ratio_now: Mapped[Optional[float]] = mapped_column(Double(53))
    avg_turnover_ratio_prev: Mapped[Optional[float]] = mapped_column(Double(53))
    amount_now: Mapped[Optional[float]] = mapped_column(Double(53))
    amount_prev: Mapped[Optional[float]] = mapped_column(Double(53))
    active_stock_ratio_30d: Mapped[Optional[float]] = mapped_column(Double(53))
    trend_stability_30d: Mapped[Optional[float]] = mapped_column(Double(53))
    return_5d: Mapped[Optional[float]] = mapped_column(Double(53))
    return_5d_index: Mapped[Optional[float]] = mapped_column(Double(53))
    amount_5d: Mapped[Optional[float]] = mapped_column(Double(53))
    avg_turnover_ratio_5d: Mapped[Optional[float]] = mapped_column(Double(53))
    active_stock_ratio_5d: Mapped[Optional[float]] = mapped_column(Double(53))
    event_heat: Mapped[Optional[float]] = mapped_column(Double(53), server_default=text('0.0'))
    industry_trend: Mapped[Optional[float]] = mapped_column(Double(53), server_default=text('0.0'))
    capital_preference: Mapped[Optional[float]] = mapped_column(Double(53), server_default=text('0.0'))
    heat_score: Mapped[Optional[float]] = mapped_column(Double(53))
    short_heat_score: Mapped[Optional[float]] = mapped_column(Double(53))
    swing_heat_score: Mapped[Optional[float]] = mapped_column(Double(53))
    style_bias: Mapped[str] = mapped_column(String(16))
    volume_trend: Mapped[str] = mapped_column(String(8))
    status: Mapped[str] = mapped_column(String(12))
    comment: Mapped[str] = mapped_column(Text, server_default=text("''::text"))
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('CURRENT_TIMESTAMP'))
    vol_ratio_5: Mapped[Optional[float]] = mapped_column(Double(53))
    vol_ratio_20: Mapped[Optional[float]] = mapped_column(Double(53))
    volume_trend_short: Mapped[str] = mapped_column(String(8))


class FactSectorLeaderSnapshot(Base):
    __tablename__ = 'fact_sector_leader_snapshot'
    __table_args__ = (
        PrimaryKeyConstraint('window_id', 'sector_code', 'ts_code', name='fact_sector_leader_snapshot_pkey'),
        Index('idx_sector_leader_sector', 'sector_code'),
    )

    window_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    sector_code: Mapped[str] = mapped_column(String(32), primary_key=True)
    ts_code: Mapped[str] = mapped_column(String(16), primary_key=True)
    stock_name: Mapped[str] = mapped_column(String(64), nullable=False)
    leader_type: Mapped[str] = mapped_column(String(16), nullable=False)
    leader_rank: Mapped[int] = mapped_column(Integer, nullable=False)
    period_return_pct: Mapped[Optional[float]] = mapped_column(Double(53))
    period_amount: Mapped[Optional[float]] = mapped_column(Double(53))
    period_turnover: Mapped[Optional[float]] = mapped_column(Double(53))
    market_cap: Mapped[Optional[float]] = mapped_column(Double(53))
    change_pct_1d: Mapped[Optional[float]] = mapped_column(Double(53), server_default=text('0.0'))
    change_pct_5d: Mapped[Optional[float]] = mapped_column(Double(53), server_default=text('0.0'))
    limit_up_days: Mapped[Optional[int]] = mapped_column(Integer, server_default=text('0'))
    continuous_limit: Mapped[Optional[int]] = mapped_column(Integer, server_default=text('0'))
    score: Mapped[Optional[float]] = mapped_column(Double(53), server_default=text('0.0'))
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('CURRENT_TIMESTAMP'))
    last_price: Mapped[Optional[float]] = mapped_column(Double(53))
    last_volume: Mapped[Optional[float]] = mapped_column(Double(53))
    last_amount: Mapped[Optional[float]] = mapped_column(Double(53))
    volume_price_pattern: Mapped[str] = mapped_column(String(32))
    vp_advice: Mapped[str] = mapped_column(String(16))
    vp_comment: Mapped[str] = mapped_column(String(256))


class FactSoldStock(Base):
    __tablename__ = 'fact_sold_stock'
    __table_args__ = (
        Index('idx_sold_stock_change_10d', 'change_10d_after_sell'),
        Index('idx_sold_stock_change_5d', 'change_5d_after_sell'),
        Index('idx_sold_stock_sell_date', 'sell_date'),
        Index('idx_sold_stock_ts_code', 'ts_code'),
    )

    id: Mapped[Optional[int]] = mapped_column(BigInteger, primary_key=True, server_default=text("nextval('fact_sold_stock_id_seq'::regclass)"))
    ts_code: Mapped[str] = mapped_column(String(20), nullable=False, comment='股票代码（Tushare格式）')
    stock_name: Mapped[str] = mapped_column(String(50), comment='股票名称（冗余存储，方便查询）')
    sell_date: Mapped[datetime.date] = mapped_column(Date, nullable=False, comment='卖出日期')
    change_5d_after_sell: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(8, 4), comment='卖出后5日涨幅（卖出后5个交易日的涨幅，单位：%）')
    change_10d_after_sell: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(8, 4), comment='卖出后10日涨幅（卖出后10个交易日的涨幅，单位：%）')
    is_above_ma10: Mapped[Optional[bool]] = mapped_column(Boolean, comment='是否站稳10日线（卖出后是否在10日线上方）')
    is_above_ma20: Mapped[Optional[bool]] = mapped_column(Boolean, comment='是否站稳20日线（卖出后是否在20日线上方）')
    is_above_ma30: Mapped[Optional[bool]] = mapped_column(Boolean, comment='是否站稳30日线（卖出后是否在30日线上方）')
    notes: Mapped[str] = mapped_column(Text, comment='备注信息')
    created_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('CURRENT_TIMESTAMP'))
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('CURRENT_TIMESTAMP'))


class FactStockSector(Base):
    __tablename__ = 'fact_stock_sector'
    __table_args__ = (
        PrimaryKeyConstraint('ts_code', 'sector_id', 'start_date', name='fact_stock_sector_pkey'),
        Index('ix_fact_stock_sector_sector_id', 'sector_id'),
        Index('ix_fact_stock_sector_ts_code', 'ts_code'),
    )

    ts_code: Mapped[str] = mapped_column(String(20), primary_key=True, comment='股票代码')
    sector_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment='板块ID')
    start_date: Mapped[Optional[datetime.date]] = mapped_column(Date, primary_key=True, comment='开始日期')
    end_date: Mapped[Optional[datetime.date]] = mapped_column(Date, comment='结束日期（null 表示当前仍有效）')
    is_primary: Mapped[Optional[bool]] = mapped_column(Boolean, comment='是否主行业（vs 概念、辅行业）')
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('now()'), comment='更新时间')


class FactStockSnapshot(Base):
    __tablename__ = 'fact_stock_snapshot'
    __table_args__ = (
        PrimaryKeyConstraint('ts_code', 'trade_date', 'snapshot_time', name='fact_stock_snapshot_pkey'),
    )

    ts_code: Mapped[str] = mapped_column(String(20), primary_key=True, comment='股票代码（Tushare格式）')
    trade_date: Mapped[Optional[datetime.date]] = mapped_column(Date, primary_key=True, comment='交易日期')
    snapshot_time: Mapped[str] = mapped_column(String(255), primary_key=True, comment='快照时间点（09:15/11:30/13:00/15:00）')
    pre_close: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(12, 4), comment='昨收价')
    open: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(12, 4), comment='今开价')
    high: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(12, 4), comment='最高价（到快照时刻）')
    low: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(12, 4), comment='最低价（到快照时刻）')
    close: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(12, 4), comment='当前价（快照时刻）')
    change_pct: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(8, 4), comment='涨跌幅（%）')
    vol: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(20, 4), comment='成交量（手，到快照时刻）')
    amount: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(20, 4), comment='成交额（元，到快照时刻）')
    turnover_rate: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(8, 4), comment='换手率（%，到快照时刻）')
    historical_data: Mapped[Optional[dict]] = mapped_column(JSON, comment='历史数据（MA、斜率等）')
    financial_data: Mapped[Optional[dict]] = mapped_column(JSON, comment='财务指标数据')
    sector_name: Mapped[str] = mapped_column(String(100), comment='所属行业')
    sector_id: Mapped[str] = mapped_column(String(50), comment='行业ID')
    concept_tags: Mapped[Optional[dict]] = mapped_column(JSON, comment='概念标签数组')
    created_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('now()'), comment='创建时间')
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('now()'), comment='更新时间')


class FactStockStartupCandidate(Base):
    __tablename__ = 'fact_stock_startup_candidate'
    __table_args__ = (
        UniqueConstraint('ts_code', 'golden_cross_date', name='fact_stock_startup_candidate_ts_code_golden_cross_date_key'),
        Index('idx_startup_candidate_broken_ma10', 'is_broken_ma10', 'trade_date'),
        Index('idx_startup_candidate_code_cross_date', 'ts_code', 'golden_cross_date'),
        Index('idx_startup_candidate_date', 'trade_date'),
        Index('idx_startup_candidate_diagnosis_date', 'last_diagnosis_date'),
        Index('idx_startup_candidate_exited', 'is_exited', 'exit_date'),
        Index('idx_startup_candidate_golden_cross_date', 'golden_cross_date'),
        Index('idx_startup_candidate_risk', 'risk_passed', 'score'),
        Index('idx_startup_candidate_score', 'score'),
        Index('idx_startup_candidate_stage', 'stage', 'trade_date'),
        Index('idx_startup_candidate_trade_date', 'trade_date'),
        Index('idx_startup_candidate_watch_date', 'watch_start_date'),
        Index('idx_startup_candidate_watching', 'is_watching'),
    )

    id: Mapped[Optional[int]] = mapped_column(BigInteger, primary_key=True, server_default=text("nextval('fact_stock_startup_candidate_id_seq1'::regclass)"))
    ts_code: Mapped[str] = mapped_column(String(20), nullable=False)
    trade_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    is_started: Mapped[Optional[bool]] = mapped_column(Boolean, server_default=text('false'))
    basic_passed: Mapped[Optional[bool]] = mapped_column(Boolean, server_default=text('false'))
    core_passed: Mapped[Optional[bool]] = mapped_column(Boolean, server_default=text('false'))
    assist_count: Mapped[Optional[int]] = mapped_column(Integer, server_default=text('0'))
    risk_passed: Mapped[Optional[bool]] = mapped_column(Boolean, server_default=text('false'))
    passed_signals: Mapped[Optional[list]] = mapped_column(ARRAY(String()))
    risk_reasons: Mapped[Optional[list]] = mapped_column(ARRAY(String()))
    indicators: Mapped[Optional[dict]] = mapped_column(JSON)
    created_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('now()'))
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('now()'))
    latest_price: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2))
    ma10: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2))
    is_broken_ma10: Mapped[Optional[bool]] = mapped_column(Boolean, server_default=text('false'))
    last_check_date: Mapped[Optional[datetime.date]] = mapped_column(Date)
    stage: Mapped[str] = mapped_column(String(20), server_default=text("'golden_cross'::character varying"))
    golden_cross_date: Mapped[Optional[datetime.date]] = mapped_column(Date)
    days_since_cross: Mapped[Optional[int]] = mapped_column(Integer)
    is_recommended: Mapped[Optional[bool]] = mapped_column(Boolean, server_default=text('false'))
    recommend_date: Mapped[Optional[datetime.date]] = mapped_column(Date)
    recommend_id: Mapped[Optional[int]] = mapped_column(Integer)
    diagnosis_result: Mapped[Optional[dict]] = mapped_column(JSON)
    last_diagnosis_date: Mapped[Optional[datetime.date]] = mapped_column(Date)
    is_watching: Mapped[Optional[bool]] = mapped_column(Boolean, server_default=text('false'))
    missing_conditions: Mapped[Optional[list]] = mapped_column(ARRAY(String()))
    watch_start_date: Mapped[Optional[datetime.date]] = mapped_column(Date)
    last_check_time: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)
    check_count: Mapped[Optional[int]] = mapped_column(Integer, server_default=text('0'))
    alert_sent: Mapped[Optional[bool]] = mapped_column(Boolean, server_default=text('false'))
    is_exited: Mapped[Optional[bool]] = mapped_column(Boolean, server_default=text('false'))
    exit_date: Mapped[Optional[datetime.date]] = mapped_column(Date)
    exit_reason: Mapped[str] = mapped_column(String(100))
    change_5d: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2))
    change_5d_days: Mapped[Optional[int]] = mapped_column(Integer)
    change_10d: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2))
    change_10d_days: Mapped[Optional[int]] = mapped_column(Integer)
    change_20d: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2))
    change_20d_days: Mapped[Optional[int]] = mapped_column(Integer)
    change_60d: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2))
    change_60d_days: Mapped[Optional[int]] = mapped_column(Integer)
    performance_calculated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)
    core_confirmed_date: Mapped[Optional[datetime.date]] = mapped_column(Date)
    assist_confirmed_date: Mapped[Optional[datetime.date]] = mapped_column(Date)
    risk_passed_date: Mapped[Optional[datetime.date]] = mapped_column(Date)
    financial_check_result: Mapped[Optional[dict]] = mapped_column(JSON)
    last_financial_check_date: Mapped[Optional[datetime.date]] = mapped_column(Date)


class FactStockStartupCandidateBak(Base):
    __tablename__ = 'fact_stock_startup_candidate_bak'
    __table_args__ = (
        UniqueConstraint('ts_code', 'golden_cross_date', name='fact_stock_startup_candidate_ts_code_golden_cross_date_key1'),
        Index('idx_startup_candidate_broken_ma101', 'is_broken_ma10', 'trade_date'),
        Index('idx_startup_candidate_code_cross_date1', 'ts_code', 'golden_cross_date'),
        Index('idx_startup_candidate_date1', 'trade_date'),
        Index('idx_startup_candidate_diagnosis_date1', 'last_diagnosis_date'),
        Index('idx_startup_candidate_exited1', 'is_exited', 'exit_date'),
        Index('idx_startup_candidate_golden_cross_date1', 'golden_cross_date'),
        Index('idx_startup_candidate_risk1', 'risk_passed', 'score'),
        Index('idx_startup_candidate_score1', 'score'),
        Index('idx_startup_candidate_stage1', 'stage', 'trade_date'),
        Index('idx_startup_candidate_trade_date1', 'trade_date'),
        Index('idx_startup_candidate_watch_date1', 'watch_start_date'),
        Index('idx_startup_candidate_watching1', 'is_watching'),
    )

    id: Mapped[Optional[int]] = mapped_column(BigInteger, primary_key=True, server_default=text("nextval('fact_stock_startup_candidate_id_seq'::regclass)"))
    ts_code: Mapped[str] = mapped_column(String(20), nullable=False)
    trade_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    is_started: Mapped[Optional[bool]] = mapped_column(Boolean, server_default=text('false'))
    basic_passed: Mapped[Optional[bool]] = mapped_column(Boolean, server_default=text('false'))
    core_passed: Mapped[Optional[bool]] = mapped_column(Boolean, server_default=text('false'))
    assist_count: Mapped[Optional[int]] = mapped_column(Integer, server_default=text('0'))
    risk_passed: Mapped[Optional[bool]] = mapped_column(Boolean, server_default=text('false'))
    passed_signals: Mapped[Optional[list]] = mapped_column(ARRAY(String()))
    risk_reasons: Mapped[Optional[list]] = mapped_column(ARRAY(String()))
    indicators: Mapped[Optional[dict]] = mapped_column(JSON)
    created_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('now()'))
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('now()'))
    latest_price: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2), comment='最新价格')
    ma10: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2), comment='10日均线')
    is_broken_ma10: Mapped[Optional[bool]] = mapped_column(Boolean, server_default=text('false'), comment='是否破10日线')
    last_check_date: Mapped[Optional[datetime.date]] = mapped_column(Date, comment='最后检查日期')
    stage: Mapped[str] = mapped_column(String(20), server_default=text("'golden_cross'::character varying"), comment='阶段：golden_cross(金叉候选) / confirmed(启动确认)')
    golden_cross_date: Mapped[Optional[datetime.date]] = mapped_column(Date, comment='5日金叉10日发生的日期')
    days_since_cross: Mapped[Optional[int]] = mapped_column(Integer, comment='距离金叉发生的天数')
    is_recommended: Mapped[Optional[bool]] = mapped_column(Boolean, server_default=text('false'), comment='是否已加入推荐池')
    recommend_date: Mapped[Optional[datetime.date]] = mapped_column(Date, comment='推荐日期')
    recommend_id: Mapped[Optional[int]] = mapped_column(Integer, comment='推荐记录ID')
    diagnosis_result: Mapped[Optional[dict]] = mapped_column(JSON, comment='批量诊断结果（JSON）：{core_checks, passed_count, advice, distance_from_high等}')
    last_diagnosis_date: Mapped[Optional[datetime.date]] = mapped_column(Date, comment='最后诊断日期')
    is_watching: Mapped[Optional[bool]] = mapped_column(Boolean, server_default=text('false'), comment='是否加入待候选监控（2/3条件）')
    missing_conditions: Mapped[Optional[list]] = mapped_column(ARRAY(String()), comment='缺少的核心条件列表')
    watch_start_date: Mapped[Optional[datetime.date]] = mapped_column(Date, comment='开始监控日期')
    last_check_time: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, comment='最后检查时间')
    check_count: Mapped[Optional[int]] = mapped_column(Integer, server_default=text('0'), comment='已检查次数')
    alert_sent: Mapped[Optional[bool]] = mapped_column(Boolean, server_default=text('false'), comment='是否已发送语音提醒')
    is_exited: Mapped[Optional[bool]] = mapped_column(Boolean, server_default=text('false'), comment='是否已退出启动')
    exit_date: Mapped[Optional[datetime.date]] = mapped_column(Date, comment='退出日期')
    exit_reason: Mapped[str] = mapped_column(String(100), comment='退出原因')
    change_5d: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2), comment='后5日涨幅（百分比）')
    change_5d_days: Mapped[Optional[int]] = mapped_column(Integer, comment='后5日涨幅实际交易日数')
    change_10d: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2), comment='后10日涨幅（百分比）')
    change_10d_days: Mapped[Optional[int]] = mapped_column(Integer, comment='后10日涨幅实际交易日数')
    change_20d: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2), comment='后20日涨幅（百分比）')
    change_20d_days: Mapped[Optional[int]] = mapped_column(Integer, comment='后20日涨幅实际交易日数')
    change_60d: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2), comment='后60日涨幅（百分比）')
    change_60d_days: Mapped[Optional[int]] = mapped_column(Integer, comment='后60日涨幅实际交易日数')
    performance_calculated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, comment='表现数据计算时间')
    core_confirmed_date: Mapped[Optional[datetime.date]] = mapped_column(Date, comment='核心确认日期（核心条件全部通过的日期）')
    assist_confirmed_date: Mapped[Optional[datetime.date]] = mapped_column(Date, comment='辅助确认日期（辅助条件至少满足1个的日期）')
    risk_passed_date: Mapped[Optional[datetime.date]] = mapped_column(Date, comment='风险排除日期（风险排除条件全部通过的日期）')
    financial_check_result: Mapped[Optional[dict]] = mapped_column(JSON, comment='财务检测结果（JSON）：{is_passed, failure_reasons, industry, sector, check_date等}')
    last_financial_check_date: Mapped[Optional[datetime.date]] = mapped_column(Date, comment='最后财务检测日期')


class FactStockWatchlist(Base):
    __tablename__ = 'fact_stock_watchlist'
    __table_args__ = (
        UniqueConstraint('ts_code', name='ix_fact_stock_watchlist_ts_code'),
    )

    id: Mapped[Optional[int]] = mapped_column(Integer, primary_key=True, server_default=text("nextval('fact_stock_watchlist_id_seq'::regclass)"), comment='自增ID')
    ts_code: Mapped[str] = mapped_column(String(20), nullable=False, comment='股票代码')
    note: Mapped[str] = mapped_column(Text, comment='备注')
    added_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('now()'), comment='添加时间')


class FactTonghuashunLimitUp(Base):
    __tablename__ = 'fact_tonghuashun_limit_up'
    __table_args__ = (
        Index('idx_tonghuashun_limit_up_status', 'up_and_down_status'),
        Index('idx_tonghuashun_limit_up_trade_date', 'trade_date'),
        Index('idx_tonghuashun_limit_up_ts_code', 'ts_code'),
        UniqueConstraint('ts_code', 'trade_date', name='uk_tonghuashun_limit_up_code_date'),
    )

    id: Mapped[Optional[int]] = mapped_column(BigInteger, primary_key=True, server_default=text("nextval('fact_tonghuashun_limit_up_id_seq'::regclass)"))
    ts_code: Mapped[str] = mapped_column(String(20), nullable=False, comment='股票代码（Tushare格式）')
    trade_date: Mapped[datetime.date] = mapped_column(Date, nullable=False, comment='交易日期')
    up_and_down_status: Mapped[str] = mapped_column(String(50), comment='涨跌停状态（同花顺返回的状态值）')
    volume_ratio: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 4), comment='量比')
    stock_name: Mapped[str] = mapped_column(String(100))
    close_price: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(12, 4))
    amount: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(20, 4))
    change_pct: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(8, 4))
    created_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('CURRENT_TIMESTAMP'))
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('CURRENT_TIMESTAMP'))


class FactUserHolding(Base):
    __tablename__ = 'fact_user_holding'
    __table_args__ = (
        Index('idx_holding_status', 'status', 'user_id'),
        Index('idx_updated_at', 'updated_at'),
        Index('idx_user_symbol', 'user_id', 'symbol'),
    )

    id: Mapped[Optional[int]] = mapped_column(Integer, primary_key=True, server_default=text("nextval('fact_user_holding_id_seq'::regclass)"), comment='自增ID')
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, comment='用户ID（预留多用户，默认1）')
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, comment='股票代码（6位数字，不含前缀）')
    name: Mapped[str] = mapped_column(String(100), nullable=False, comment='股票名称')
    board_type: Mapped[str] = mapped_column(String(20), comment='分类：darwin/swing/short/other')
    total_quantity: Mapped[decimal.Decimal] = mapped_column(Numeric(12, 2), nullable=False, comment='当前总持仓（股）')
    avg_cost_price: Mapped[decimal.Decimal] = mapped_column(Numeric(12, 4), nullable=False, comment='加权平均成本价')
    current_price: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(12, 4), comment='最新价')
    market_value: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(20, 4), comment='市值（total_quantity * current_price）')
    profit_amount: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(20, 4), comment='浮动盈亏金额')
    profit_rate: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(8, 4), comment='浮动盈亏幅度（%）')
    chase_risk_level: Mapped[str] = mapped_column(String(20), comment='追高风险等级：low/medium/high')
    chase_risk_score: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(5, 2), comment='追高风险评分（0-100）')
    chase_risk_reason: Mapped[str] = mapped_column(Text, comment='追高风险原因说明')
    today_action: Mapped[str] = mapped_column(String(20), comment='今日操作建议：buy/add/hold/reduce/close/skip')
    today_action_reason: Mapped[str] = mapped_column(Text, comment='操作建议原因说明')
    created_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('now()'), comment='创建时间')
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('now()'), comment='更新时间')
    buy_date: Mapped[Optional[datetime.date]] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), server_default=text("'holding'::character varying"))
    close_date: Mapped[Optional[datetime.date]] = mapped_column(Date)
    close_price: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(12, 4))
    realized_profit: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(20, 4))


class RawDailyPrice(Base):
    __tablename__ = 'raw_daily_price'
    __table_args__ = (
        Index('ix_raw_daily_price_trade_date', 'trade_date'),
        UniqueConstraint('ts_code', 'trade_date', 'source', name='uq_raw_daily_price'),
    )

    id: Mapped[Optional[int]] = mapped_column(BigInteger, primary_key=True, server_default=text("nextval('raw_daily_price_id_seq'::regclass)"))
    ts_code: Mapped[str] = mapped_column(String(20), nullable=False, comment='股票代码')
    trade_date: Mapped[datetime.date] = mapped_column(Date, nullable=False, comment='交易日期')
    open: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(12, 4), comment='开盘价')
    high: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(12, 4), comment='最高价')
    low: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(12, 4), comment='最低价')
    close: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(12, 4), comment='收盘价')
    pre_close: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(12, 4), comment='昨收价')
    vol: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(20, 4), comment='成交量（手）')
    amount: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(20, 4), comment='成交额（元）')
    turnover_rate: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(8, 4), comment='换手率（%）')
    source: Mapped[str] = mapped_column(String(20), nullable=False, comment='数据源：tushare/akshare/eastmoney')
    raw_payload: Mapped[Optional[dict]] = mapped_column(JSON, comment='原始返回数据（JSON）')
    created_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('now()'), comment='创建时间')


class RawFundamental(Base):
    __tablename__ = 'raw_fundamental'
    __table_args__ = (
        Index('ix_raw_fundamental_end_date', 'end_date'),
        UniqueConstraint('ts_code', 'end_date', 'report_type', 'source', name='uq_raw_fundamental'),
    )

    id: Mapped[Optional[int]] = mapped_column(BigInteger, primary_key=True, server_default=text("nextval('raw_fundamental_id_seq'::regclass)"))
    ts_code: Mapped[str] = mapped_column(String(20), nullable=False, comment='股票代码')
    end_date: Mapped[datetime.date] = mapped_column(Date, nullable=False, comment='报告期')
    report_type: Mapped[str] = mapped_column(String(20), nullable=False, comment='报告类型：annual/q1/q2/q3')
    roe: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(12, 4), comment='ROE（%）')
    net_margin: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(12, 4), comment='净利率（%）')
    gross_margin: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(12, 4), comment='毛利率（%）')
    op_cf: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(20, 4), comment='经营现金流（元）')
    total_debt: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(20, 4), comment='总负债（元）')
    total_asset: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(20, 4), comment='总资产（元）')
    debt_ratio: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(8, 4), comment='负债率（%）')
    profit_volatility: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(12, 4), comment='盈利波动率')
    source: Mapped[str] = mapped_column(String(20), nullable=False, comment='数据源：tushare/akshare')
    raw_payload: Mapped[Optional[dict]] = mapped_column(JSON, comment='原始返回数据（JSON）')
    created_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('now()'), comment='创建时间')


class TaskExecutionLog(Base):
    __tablename__ = 'task_execution_log'
    __table_args__ = (
        Index('idx_status_started', 'status', 'started_at'),
        Index('idx_task_name_started', 'task_name', 'started_at'),
    )

    id: Mapped[Optional[int]] = mapped_column(Integer, primary_key=True, server_default=text("nextval('task_execution_log_id_seq'::regclass)"))
    task_name: Mapped[str] = mapped_column(String(50), nullable=False)
    task_type: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'scheduled'::character varying"))
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    started_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    finished_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)
    duration_seconds: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2))
    error_message: Mapped[str] = mapped_column(Text)
    records_processed: Mapped[Optional[int]] = mapped_column(Integer, server_default=text('0'))
    created_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('CURRENT_TIMESTAMP'))


class ShortTermSignalTracking(Base):
    __tablename__ = 'short_term_signal_tracking'

    id: Mapped[Optional[int]] = mapped_column(Integer, primary_key=True, server_default=text("nextval('short_term_signal_tracking_id_seq'::regclass)"))
    signal_id: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, comment='信号唯一标识')
    ts_code: Mapped[str] = mapped_column(String(20), nullable=False, comment='股票代码')
    signal_date: Mapped[datetime.date] = mapped_column(Date, nullable=False, comment='信号日期')
    signal_type: Mapped[str] = mapped_column(String(20), nullable=False, comment='信号类型：leader / limit_up / startup')
    buy_point_type: Mapped[Optional[str]] = mapped_column(String(50), comment='买点类型')
    entry_price: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2), comment='建议买入价')
    day1_high: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2), comment='次日最高价')
    day1_close: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2), comment='次日收盘价')
    day3_max: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2), comment='3日内最高价')
    day3_close: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2), comment='第3日收盘价')
    day5_max: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2), comment='5日内最高价')
    day5_close: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2), comment='第5日收盘价')
    exit_price: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2), comment='实际退出价')
    exit_date: Mapped[Optional[datetime.date]] = mapped_column(Date, comment='实际退出日期')
    exit_reason: Mapped[Optional[str]] = mapped_column(String(20), comment='退出原因')
    total_return: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(8, 4), comment='总收益率')
    max_drawdown: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(8, 4), comment='最大回撤')
    holding_days: Mapped[Optional[int]] = mapped_column(Integer, comment='实际持仓天数')
    lstm_mab_score: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(6, 2), comment='AI评分')
    grade: Mapped[Optional[str]] = mapped_column(String(2), comment='等级')
    emotion_cycle: Mapped[Optional[str]] = mapped_column(String(20), comment='情绪周期')
    prediction_id: Mapped[Optional[int]] = mapped_column(Integer, comment='关联的 LSTM-MAB 预测记录 ID')
    actual_entry_price: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2), comment='实际成交买入价')
    actual_quantity: Mapped[Optional[int]] = mapped_column(Integer, comment='实际成交数量')
    created_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('CURRENT_TIMESTAMP'))
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('CURRENT_TIMESTAMP'), onupdate=text('CURRENT_TIMESTAMP'))


class FactValuationPercentile(Base):
    __tablename__ = 'fact_valuation_percentile'
    __table_args__ = (
        UniqueConstraint('ts_code', 'trade_date', name='uq_valuation_percentile_ts_date'),
        Index('idx_val_percentile_date', 'trade_date'),
    )

    id: Mapped[Optional[int]] = mapped_column(Integer, primary_key=True, server_default=text("nextval('fact_valuation_percentile_id_seq'::regclass)"), comment='自增ID')
    ts_code: Mapped[str] = mapped_column(String(20), nullable=False, comment='股票代码')
    trade_date: Mapped[datetime.date] = mapped_column(Date, nullable=False, comment='交易日期')
    pe_ttm: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(12, 4), comment='PE(TTM)')
    pe_percentile_5y: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(5, 4), comment='PE 5年分位数')
    pe_percentile_10y: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(5, 4), comment='PE 10年分位数')
    pb: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 4), comment='PB')
    pb_percentile_5y: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(5, 4), comment='PB 5年分位数')
    pb_percentile_10y: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(5, 4), comment='PB 10年分位数')
    peg: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 4), comment='PEG')
    created_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('now()'), comment='创建时间')


class FactLongTermHolding(Base):
    __tablename__ = 'fact_long_term_holding'
    __table_args__ = (
        Index('idx_ltholding_status', 'status'),
    )

    id: Mapped[Optional[int]] = mapped_column(Integer, primary_key=True, server_default=text("nextval('fact_long_term_holding_id_seq'::regclass)"), comment='自增ID')
    ts_code: Mapped[str] = mapped_column(String(20), nullable=False, comment='股票代码')
    name: Mapped[Optional[str]] = mapped_column(String(50), comment='股票名称')
    industry: Mapped[Optional[str]] = mapped_column(String(50), comment='所属行业')
    first_buy_date: Mapped[datetime.date] = mapped_column(Date, nullable=False, comment='首次买入日期')
    avg_cost: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(12, 4), comment='平均成本')
    total_shares: Mapped[Optional[int]] = mapped_column(BigInteger, comment='总持股数')
    current_weight: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(5, 4), comment='当前仓位权重')
    target_weight: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(5, 4), comment='目标仓位权重')
    darwin_score: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(6, 4), comment='达尔文评分')
    pe_percentile_5y: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(5, 4), comment='PE 5年分位数')
    pb_percentile_5y: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(5, 4), comment='PB 5年分位数')
    status: Mapped[Optional[str]] = mapped_column(String(20), server_default=text("'holding'::character varying"), comment='状态：holding/reducing/exited')
    exit_date: Mapped[Optional[datetime.date]] = mapped_column(Date, comment='退出日期')
    exit_price: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(12, 4), comment='退出价格')
    return_pct: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(8, 4), comment='收益率(%)')
    created_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('now()'), comment='创建时间')
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('now()'), comment='更新时间')


class FactLongTermJournal(Base):
    __tablename__ = 'fact_long_term_journal'
    __table_args__ = (
        Index('idx_ltjournal_ts_code', 'ts_code'),
        Index('idx_ltjournal_date', 'trade_date'),
    )

    id: Mapped[Optional[int]] = mapped_column(Integer, primary_key=True, server_default=text("nextval('fact_long_term_journal_id_seq'::regclass)"), comment='自增ID')
    ts_code: Mapped[str] = mapped_column(String(20), nullable=False, comment='股票代码')
    action: Mapped[Optional[str]] = mapped_column(String(20), comment='操作：buy/add/reduce/sell/hold_review')
    trade_date: Mapped[datetime.date] = mapped_column(Date, nullable=False, comment='交易日期')
    price: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 4), comment='成交价格')
    shares: Mapped[Optional[int]] = mapped_column(Integer, comment='成交股数')
    weight_change: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(5, 4), comment='权重变动')
    reason: Mapped[Optional[str]] = mapped_column(Text, comment='投资逻辑/卖出理由')
    darwin_score: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(6, 4), comment='达尔文评分')
    pe_percentile: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(5, 4), comment='PE分位数')
    pb_percentile: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(5, 4), comment='PB分位数')
    market_trend: Mapped[Optional[str]] = mapped_column(String(20), comment='市场环境')
    emotion_cycle: Mapped[Optional[str]] = mapped_column(String(20), comment='情绪周期')
    created_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('now()'), comment='创建时间')


class FactLongTermAlert(Base):
    __tablename__ = 'fact_long_term_alert'
    __table_args__ = (
        Index('idx_ltalert_unresolved', 'is_resolved', 'created_at'),
        Index('idx_ltalert_ts_code', 'ts_code'),
    )

    id: Mapped[Optional[int]] = mapped_column(Integer, primary_key=True, server_default=text("nextval('fact_long_term_alert_id_seq'::regclass)"), comment='自增ID')
    ts_code: Mapped[str] = mapped_column(String(20), nullable=False, comment='股票代码')
    alert_type: Mapped[Optional[str]] = mapped_column(String(50), comment='告警类型')
    level: Mapped[Optional[str]] = mapped_column(String(20), comment='级别：CRITICAL/WARNING/NOTICE')
    message: Mapped[Optional[str]] = mapped_column(Text, comment='告警内容')
    metric_value: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 4), comment='触发时指标值')
    threshold_value: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 4), comment='阈值')
    is_resolved: Mapped[Optional[bool]] = mapped_column(Boolean, server_default=text('false'), comment='是否已解决')
    resolved_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, comment='解决时间')
    created_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('now()'), comment='创建时间')