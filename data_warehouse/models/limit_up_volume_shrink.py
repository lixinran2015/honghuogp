"""
涨停缩量模型
记录每日计算的"最近5天有涨停且量能缩小（量比<0.6）"的股票结果
"""
from sqlalchemy import Column, String, Date, DateTime, BigInteger, Numeric, Integer, func
from data_warehouse.models.base import Base


class FactLimitUpVolumeShrink(Base):
    """涨停缩量表"""
    __tablename__ = 'fact_limit_up_volume_shrink'
    
    # 主键
    id = Column(BigInteger, primary_key=True, autoincrement=True, comment='主键ID')
    
    # 计算日期和股票信息
    trade_date = Column(Date, nullable=False, index=True, comment='计算日期')
    ts_code = Column(String(20), nullable=False, index=True, comment='股票代码（Tushare格式）')
    stock_name = Column(String(100), comment='股票名称（冗余存储，方便查询）')
    
    # 策略类型
    strategy_type = Column(String(50), nullable=False, default='mainboard_limit_up', index=True, comment='策略类型：mainboard_limit_up(主板涨停缩量), cyb_rise_shrink(创业板科创板涨幅缩量)')
    
    # 涨停信息（对于主板策略是涨停日期，对于创业板科创板策略是涨幅>=10%的日期）
    limit_up_date = Column(Date, index=True, comment='最近一次涨停日期（主板）或涨幅>=10%的日期（创业板科创板）')
    limit_up_days_ago = Column(Integer, comment='距离涨停天数（主板）或距离涨幅>=10%的天数（创业板科创板）')
    
    # 当前数据
    volume_ratio = Column(Numeric(8, 4), index=True, comment='当前量比')
    today_close = Column(Numeric(10, 2), comment='今日收盘价')
    today_change_pct = Column(Numeric(8, 4), comment='今日涨幅（%）')
    today_amount = Column(Numeric(20, 2), comment='今日成交额（元）')
    
    # 时间戳
    created_at = Column(DateTime, server_default=func.now(), comment='创建时间')
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment='更新时间')
    
    def __repr__(self):
        return f"<FactLimitUpVolumeShrink(id={self.id}, trade_date={self.trade_date}, ts_code={self.ts_code}, limit_up_date={self.limit_up_date}, volume_ratio={self.volume_ratio})>"
