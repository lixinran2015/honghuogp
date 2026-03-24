"""
股吧人气榜模型
"""

from sqlalchemy import Column, String, Integer, Numeric, Date, DateTime, Index, func
from sqlalchemy.dialects.postgresql import JSONB
from data_warehouse.models.base import Base


class FactGubaPopularityRank(Base):
    """股吧人气榜表"""
    __tablename__ = 'fact_guba_popularity_rank'
    
    # 主键
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # 爬取时间
    crawl_date = Column(Date, nullable=False, index=True, comment='爬取日期')
    crawl_time = Column(DateTime, nullable=False, server_default=func.now(), comment='爬取时间')
    
    # 排名信息
    rank_position = Column(Integer, nullable=False, comment='当前排名')
    rank_change = Column(Integer, default=0, comment='排名较昨日变动（正数=上升，负数=下降）')
    
    # 股票信息
    ts_code = Column(String(20), nullable=False, index=True, comment='股票代码')
    stock_name = Column(String(100), nullable=False, comment='股票名称')
    
    # 价格信息
    latest_price = Column(Numeric(10, 2), comment='最新价')
    change_amount = Column(Numeric(10, 2), comment='涨跌额')
    change_pct = Column(Numeric(8, 2), comment='涨跌幅(%)')
    
    # 粉丝信息
    new_fans = Column(Numeric(6, 2), comment='新晋粉丝百分比')
    loyal_fans = Column(Numeric(6, 2), comment='铁杆粉丝百分比')
    
    # 创建唯一索引，避免同一日期同一股票的重复记录
    __table_args__ = (
        Index('idx_guba_rank_date_code', 'crawl_date', 'ts_code', unique=True),
        Index('idx_guba_rank_date_position', 'crawl_date', 'rank_position'),
    )


class FactGubaRankHistory(Base):
    """股吧人气榜历史趋势表"""
    __tablename__ = 'fact_guba_rank_history'
    
    # 主键
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # 股票信息
    ts_code = Column(String(20), nullable=False, index=True, comment='股票代码')
    
    # 日期和排名
    trade_date = Column(Date, nullable=False, index=True, comment='交易日期')
    rank_position = Column(Integer, nullable=False, comment='排名位置')
    
    # 创建时间
    created_at = Column(DateTime, nullable=False, server_default=func.now(), comment='创建时间')
    
    # 创建唯一索引，确保每天每只股票只有一条记录
    __table_args__ = (
        Index('idx_guba_history_code_date', 'ts_code', 'trade_date', unique=True),
    )
