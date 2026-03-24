# -*- coding: utf-8 -*-
"""
ORM类定义（将Table对象转换为ORM类以支持属性访问）
"""

from sqlalchemy import Column, String, Date, DateTime, Integer, Boolean, Text, ARRAY, BigInteger, Numeric, JSON, func, text, PrimaryKeyConstraint
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class DimStock(Base):
    """股票维表"""
    __tablename__ = 'dim_stock'
    
    ts_code = Column(String(20), primary_key=True, comment='股票代码（Tushare格式）')
    exchange = Column(String(10), nullable=False, comment='交易所：SSE/SZSE/BSE')
    symbol = Column(String(10), nullable=False, comment='股票代码（6位数字）')
    name = Column(String(50), nullable=False, comment='股票名称')
    list_date = Column(Date, comment='上市日期')
    delist_date = Column(Date, comment='退市日期')
    industry = Column(String(100), comment='行业')
    concept_tags = Column(ARRAY(String), comment='概念标签数组')
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment='更新时间')
    created_at = Column(DateTime, server_default=func.now(), comment='创建时间')


class DimStockUniverse(Base):
    """股票池维表"""
    __tablename__ = 'dim_stock_universe'
    
    ts_code = Column(String(20), primary_key=True)
    universe_type = Column(String(20), primary_key=True)
    trade_date = Column(Date, primary_key=True)
    is_active = Column(Boolean, server_default=text('true'))
    filter_reason = Column(Text)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class DimSector(Base):
    """板块维表"""
    __tablename__ = 'dim_sector'
    
    sector_id = Column(String(50), primary_key=True, comment='板块ID')
    sector_type = Column(String(20), nullable=False, comment='板块类型：industry / concept / index')
    name = Column(String(100), nullable=False, comment='板块名称')
    level = Column(Integer, comment='行业级别：1=一级行业; 2=二级; null=概念')
    provider = Column(String(20), comment='数据提供商：sw / citic / eastmoney 等')
    updated_at = Column(DateTime, server_default=func.now(), comment='更新时间')


class DimSectorRotationConfig(Base):
    """板块轮动配置表"""
    __tablename__ = 'dim_sector_rotation_config'
    
    config_id = Column(BigInteger, primary_key=True)
    month = Column(Integer, nullable=False)
    sector_id = Column(String(50), nullable=False)
    sector_name = Column(String(100))
    rotation_type = Column(String(20))
    priority = Column(Integer)
    start_date = Column(Date)
    end_date = Column(Date)
    is_active = Column(Boolean, server_default=text('true'))
    updated_at = Column(DateTime, server_default=func.now())


class DimHotspotWindow(Base):
    """热点时间窗口维表"""
    __tablename__ = 'dim_hotspot_window'
    
    id = Column(String(64), primary_key=True)
    window_type = Column(String(32), nullable=False)
    label = Column(String(128))
    start_date = Column(Date)
    end_date = Column(Date)
    tags = Column(ARRAY(Text))
    is_current = Column(Boolean, server_default=text('false'))
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now())


class ETLLog(Base):
    """ETL日志表"""
    __tablename__ = 'etl_log'
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    task_name = Column(String(100), nullable=False)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime)
    status = Column(String(20), nullable=False)
    records_processed = Column(Integer)
    error_message = Column(Text)
    source = Column(String(50))
    target_table = Column(String(100))
    extra_info = Column(JSON)


class FactDailyFundamental(Base):
    """每日基本面数据表（主键 ts_code + trade_date，与 schema.sql 一致，无 id 列）"""
    __tablename__ = 'fact_daily_fundamental'
    __table_args__ = (PrimaryKeyConstraint('ts_code', 'trade_date', name='fact_daily_fundamental_pkey'),)

    ts_code = Column(String(20), nullable=False, index=True)
    trade_date = Column(Date, nullable=False, index=True)
    pe_ttm = Column(Numeric(20, 4), comment='市盈率TTM')
    pb_lyr = Column(Numeric(20, 4), comment='市净率LYR')
    pb_mrq = Column(Numeric(20, 4), comment='市净率MRQ')
    roe_ttm = Column(Numeric(10, 4), comment='ROE TTM')
    roe_lyr = Column(Numeric(10, 4), comment='ROE LYR')
    net_margin_ttm = Column(Numeric(10, 4), comment='净利率TTM')
    gross_margin_ttm = Column(Numeric(10, 4), comment='毛利率TTM')
    op_cf_ttm = Column(Numeric(20, 4), comment='经营现金流TTM')
    debt_ratio = Column(Numeric(10, 4), comment='负债率')
    revenue_growth_yoy = Column(Numeric(8, 4), comment='营收同比增长率(%)')
    profit_growth_yoy = Column(Numeric(8, 4), comment='净利润同比增长率(%)')
    source = Column(String(20), server_default=text("'fundamental_csv'"))
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

