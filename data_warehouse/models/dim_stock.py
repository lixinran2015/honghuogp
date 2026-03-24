# -*- coding: utf-8 -*-
"""股票维表模型"""

from sqlalchemy import Column, String, Date, ARRAY, DateTime, func
from .base import Base


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
    
    def __repr__(self):
        return f"<DimStock(ts_code={self.ts_code}, name={self.name})>"
