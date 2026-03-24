# -*- coding: utf-8 -*-
"""日线行情原始表模型"""

from sqlalchemy import Column, BigInteger, String, Date, Numeric, JSON, DateTime, func, UniqueConstraint
from .base import Base


class RawDailyPrice(Base):
    """日线行情原始表（多数据源）"""
    __tablename__ = 'raw_daily_price'
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    ts_code = Column(String(20), nullable=False, index=True, comment='股票代码')
    trade_date = Column(Date, nullable=False, index=True, comment='交易日期')
    open = Column(Numeric(12, 4), comment='开盘价')
    high = Column(Numeric(12, 4), comment='最高价')
    low = Column(Numeric(12, 4), comment='最低价')
    close = Column(Numeric(12, 4), comment='收盘价')
    pre_close = Column(Numeric(12, 4), comment='昨收价')
    vol = Column(Numeric(20, 4), comment='成交量（手）')
    amount = Column(Numeric(20, 4), comment='成交额（元）')
    turnover_rate = Column(Numeric(8, 4), comment='换手率')
    source = Column(String(20), nullable=False, index=True, comment='数据源：tushare/akshare/eastmoney')
    raw_payload = Column(JSON, comment='原始返回数据（JSON）')
    created_at = Column(DateTime, server_default=func.now(), comment='创建时间')
    
    __table_args__ = (
        UniqueConstraint('ts_code', 'trade_date', 'source', name='uq_raw_daily_price'),
    )
    
    def __repr__(self):
        return f"<RawDailyPrice(ts_code={self.ts_code}, trade_date={self.trade_date}, source={self.source})>"
