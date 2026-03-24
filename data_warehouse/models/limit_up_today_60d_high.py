"""
今日涨停且60日新高模型
记录每日计算的"今日涨停且60日新高"股票结果
"""
from sqlalchemy import Column, String, Date, DateTime, BigInteger, Numeric, Boolean, Integer, func
from data_warehouse.models.base import Base


class FactLimitUpToday60dHigh(Base):
    """今日涨停且60日新高表"""
    __tablename__ = 'fact_limit_up_today_60d_high'
    
    # 主键
    id = Column(BigInteger, primary_key=True, autoincrement=True, comment='主键ID')
    
    # 计算日期和股票信息
    trade_date = Column(Date, nullable=False, index=True, comment='计算日期')
    ts_code = Column(String(20), nullable=False, index=True, comment='股票代码（Tushare格式）')
    stock_name = Column(String(100), comment='股票名称（冗余存储，方便查询）')
    
    # 人气榜信息
    rank_position = Column(Integer, index=True, comment='人气榜排名')
    rank_change = Column(Integer, comment='排名变动（正数=上升，负数=下降）')
    max_rank = Column(Integer, comment='计算时使用的人气榜范围（前N名）')
    
    # 价格和涨幅信息
    today_close = Column(Numeric(10, 2), comment='今日收盘价')
    change_pct = Column(Numeric(8, 4), comment='今日涨幅（%）')
    change_5d = Column(Numeric(8, 4), index=True, comment='近5日涨幅（%）')
    change_10d = Column(Numeric(8, 4), index=True, comment='近10日涨幅（%）')
    amount = Column(Numeric(20, 2), comment='成交额（元）')
    
    # 判断结果
    is_60d_high = Column(Boolean, index=True, comment='是否60日新高')
    
    # 时间戳
    created_at = Column(DateTime, server_default=func.now(), comment='创建时间')
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment='更新时间')
    
    def __repr__(self):
        return f"<FactLimitUpToday60dHigh(id={self.id}, trade_date={self.trade_date}, ts_code={self.ts_code}, rank={self.rank_position}, change_5d={self.change_5d})>"
