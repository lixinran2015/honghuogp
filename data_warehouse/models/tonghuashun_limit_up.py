"""
同花顺涨跌停数据模型
存储从同花顺 THS_BD 接口获取的涨跌停状态和量比数据
"""
from sqlalchemy import Column, String, Date, DateTime, BigInteger, Numeric, func
from data_warehouse.models.base import Base


class FactTonghuashunLimitUp(Base):
    """同花顺涨跌停表"""
    __tablename__ = 'fact_tonghuashun_limit_up'
    
    # 主键
    id = Column(BigInteger, primary_key=True, autoincrement=True, comment='主键ID')
    
    # 股票信息和日期
    ts_code = Column(String(20), nullable=False, index=True, comment='股票代码（Tushare格式）')
    trade_date = Column(Date, nullable=False, index=True, comment='交易日期')
    
    # 涨跌停状态
    up_and_down_status = Column(String(50), index=True, comment='涨跌停状态（同花顺返回的状态值）')
    
    # 量比
    volume_ratio = Column(Numeric(10, 4), comment='量比')
    
    # 股票简称
    stock_name = Column(String(100), comment='股票简称')
    
    # 收盘价
    close_price = Column(Numeric(12, 4), comment='收盘价')
    
    # 成交额
    amount = Column(Numeric(20, 4), comment='成交额（元）')
    
    # 涨跌幅
    change_pct = Column(Numeric(8, 4), comment='涨跌幅（%）')
    
    # 时间戳
    created_at = Column(DateTime, server_default=func.now(), comment='创建时间')
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment='更新时间')
    
    def __repr__(self):
        return f"<FactTonghuashunLimitUp(id={self.id}, ts_code={self.ts_code}, trade_date={self.trade_date}, status={self.up_and_down_status}, volume_ratio={self.volume_ratio})>"
