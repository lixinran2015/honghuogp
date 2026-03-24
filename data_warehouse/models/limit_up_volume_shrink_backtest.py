"""
涨停缩量回测结果模型
"""
from sqlalchemy import Column, String, Date, DateTime, BigInteger, Numeric, Integer, func, Index
from data_warehouse.models.base import Base


class FactLimitUpVolumeShrinkBacktest(Base):
    """涨停缩量回测结果表"""
    __tablename__ = 'fact_limit_up_volume_shrink_backtest'
    __table_args__ = (
        Index('idx_backtest_signal_date', 'signal_date'),
        Index('idx_backtest_ts_code', 'ts_code'),
        Index('idx_backtest_buy_date', 'buy_date'),
        Index('idx_backtest_exit_reason', 'exit_reason'),
    )
    
    # 主键
    id = Column(BigInteger, primary_key=True, autoincrement=True, comment='主键ID')
    
    # 信号信息
    signal_date = Column(Date, nullable=False, index=True, comment='信号日期（找到股票的日期）')
    ts_code = Column(String(20), nullable=False, index=True, comment='股票代码')
    stock_name = Column(String(100), comment='股票名称')
    
    # 交易信息
    buy_date = Column(Date, nullable=False, index=True, comment='买入日期')
    buy_price = Column(Numeric(12, 4), nullable=False, comment='买入价格')
    sell_date = Column(Date, comment='卖出日期')
    sell_price = Column(Numeric(12, 4), comment='卖出价格')
    
    # 收益信息
    return_pct = Column(Numeric(8, 4), comment='收益率（小数，如0.15表示15%）')
    hold_days = Column(Integer, comment='持有天数（交易日）')
    exit_reason = Column(String(50), index=True, comment='退出原因：profit_target(止盈), stop_loss(止损), time_limit(时间限制)')
    
    # 资金管理信息
    buy_amount = Column(Numeric(20, 2), comment='买入金额（元）')
    buy_quantity = Column(Integer, comment='买入数量（股）')
    sell_amount = Column(Numeric(20, 2), comment='卖出金额（元）')
    profit_loss = Column(Numeric(20, 2), comment='盈亏金额（元）')
    profit_loss_pct = Column(Numeric(8, 4), comment='盈亏比例（%，如-8.17表示-8.17%）')
    
    # 回测参数
    profit_target = Column(Numeric(8, 4), comment='目标收益率')
    stop_loss = Column(Numeric(8, 4), comment='止损比例')
    max_hold_days = Column(Integer, comment='最大持有天数')
    sell_strategy = Column(String(50), comment='卖出策略：profit_stop, ma5_loss, ma5_loss_5pct')
    strategy_type = Column(String(50), nullable=False, default='mainboard_limit_up', index=True, comment='策略类型：mainboard_limit_up(主板涨停缩量), cyb_rise_shrink(创业板科创板涨幅缩量)')
    
    # 时间戳
    created_at = Column(DateTime, server_default=func.now(), comment='创建时间')
    
    def __repr__(self):
        return f"<FactLimitUpVolumeShrinkBacktest(id={self.id}, ts_code={self.ts_code}, signal_date={self.signal_date}, return_pct={self.return_pct})>"
