"""
已卖出股票模型
记录已卖出股票的表现分析
"""
from sqlalchemy import Column, String, Date, DateTime, Text, BigInteger, Numeric, Boolean, func
from data_warehouse.models.base import Base


class FactSoldStock(Base):
    """已卖出股票表"""
    __tablename__ = 'fact_sold_stock'
    
    # 主键
    id = Column(BigInteger, primary_key=True, autoincrement=True, comment='主键ID')
    
    # 股票基本信息
    ts_code = Column(String(20), nullable=False, index=True, comment='股票代码（Tushare格式）')
    stock_name = Column(String(50), comment='股票名称（冗余存储，方便查询）')
    
    # 卖出信息
    sell_date = Column(Date, nullable=False, index=True, comment='卖出日期')
    
    # 卖出后表现分析
    change_5d_after_sell = Column(Numeric(8, 4), index=True, comment='卖出后5日涨幅（卖出后5个交易日的涨幅，单位：%）')
    change_10d_after_sell = Column(Numeric(8, 4), index=True, comment='卖出后10日涨幅（卖出后10个交易日的涨幅，单位：%）')
    is_above_ma10 = Column(Boolean, comment='是否站稳10日线（卖出后是否在10日线上方）')
    is_above_ma20 = Column(Boolean, comment='是否站稳20日线（卖出后是否在20日线上方）')
    is_above_ma30 = Column(Boolean, comment='是否站稳30日线（卖出后是否在30日线上方）')
    
    # 其他信息
    notes = Column(Text, comment='备注信息')
    
    # 时间戳
    created_at = Column(DateTime, server_default=func.now(), comment='创建时间')
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment='更新时间')
    
    def __repr__(self):
        return f"<FactSoldStock(id={self.id}, ts_code={self.ts_code}, sell_date={self.sell_date}, change_5d={self.change_5d_after_sell}, change_10d={self.change_10d_after_sell})>"
