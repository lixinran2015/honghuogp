"""
股票跟踪池断板监控模型
用于跟踪2连板以上龙头股票的断板状态和价格监控
"""

from __future__ import annotations

from sqlalchemy import Column, String, Boolean, Date, DateTime, Integer, Numeric
from sqlalchemy import func, text, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB

from data_warehouse.models.base import Base


class FactStockWatchlistBreakBoard(Base):
    """
    股票跟踪池断板监控表

    功能：
    1. 记录2连板以上股票的断板状态
    2. 监控断板后价格变化，上涨2%时触发提醒
    3. 区分龙头类型（空间龙头/刚启动龙头）
    """

    __tablename__ = "fact_stock_watchlist_break_board"
    __table_args__ = (
        UniqueConstraint('ts_code', name='uk_watchlist_break_board_ts_code'),
        Index('idx_break_board_status', 'break_status'),
        Index('idx_break_board_alert', 'alert_triggered', 'break_status'),
        {'comment': '股票跟踪池断板监控表'}
    )

    # 主键和基本信息
    id = Column(Integer, primary_key=True, autoincrement=True, comment="自增ID")
    ts_code = Column(String(20), nullable=False, comment="股票代码（Tushare格式）")
    name = Column(String(100), nullable=False, comment="股票名称")

    # 龙头标记
    is_leader = Column(Boolean, nullable=False, server_default="false",
                       comment="是否为龙头（2连板以上）")
    leader_type = Column(String(20), nullable=True,
                        comment="龙头类型：space(空间龙头)/new(刚启动龙头)/both(两者皆是)")

    # 连板信息
    consecutive_limit_up = Column(Integer, nullable=True,
                                 comment="连板天数（最高连板数）")
    max_limit_up_date = Column(Date, nullable=True,
                              comment="最高连板日期")

    # 断板信息
    break_status = Column(String(20), nullable=False, server_default="none",
                         comment="断板状态：none(未断板)/broken(断板调整)/rebound(断板反弹)/recovered(已恢复)")
    break_date = Column(Date, nullable=True,
                       comment="断板日期（首次未涨停的日期）")
    break_base_price = Column(Numeric(12, 4), nullable=True,
                             comment="断板基准价（断板当天收盘价）")

    # 价格监控
    current_price = Column(Numeric(12, 4), nullable=True,
                          comment="当前价格")
    price_change_pct = Column(Numeric(8, 4), nullable=True,
                             comment="断板后涨幅（%）")
    alert_threshold = Column(Numeric(8, 4), nullable=False,
                            server_default="2.0",
                            comment="提醒阈值（%，默认2%）")
    alert_triggered = Column(Boolean, nullable=False, server_default="false",
                            comment="是否已触发提醒")
    alert_triggered_at = Column(DateTime, nullable=True,
                               comment="提醒触发时间")

    # 关联信息
    sectors = Column(JSONB, nullable=False,
                    server_default=text("'[]'::jsonb"),
                    comment="关联板块列表")

    # 时间戳
    created_at = Column(DateTime, server_default=func.now(), nullable=True,
                       comment="创建时间")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(),
                       nullable=True, comment="更新时间")


class FactBreakBoardPriceAlert(Base):
    """
    断板价格提醒记录表

    记录每次断板股票上涨达到阈值的提醒历史
    """

    __tablename__ = "fact_break_board_price_alert"
    __table_args__ = (
        Index('idx_alert_ts_code', 'ts_code'),
        Index('idx_alert_date', 'alert_date'),
        {'comment': '断板价格提醒记录表'}
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment="自增ID")
    ts_code = Column(String(20), nullable=False, comment="股票代码")
    name = Column(String(100), nullable=False, comment="股票名称")

    # 提醒时的价格信息
    break_base_price = Column(Numeric(12, 4), nullable=False, comment="断板基准价")
    alert_price = Column(Numeric(12, 4), nullable=False, comment="提醒时价格")
    price_change_pct = Column(Numeric(8, 4), nullable=False, comment="涨幅（%）")

    # 提醒信息
    alert_date = Column(Date, nullable=False, comment="提醒日期")
    alert_time = Column(DateTime, nullable=False, comment="提醒时间")
    alert_message = Column(String(500), nullable=True, comment="提醒消息内容")

    # 是否已播报
    announced = Column(Boolean, nullable=False, server_default="false",
                      comment="是否已语音播报")
    announced_at = Column(DateTime, nullable=True, comment="播报时间")

    created_at = Column(DateTime, server_default=func.now(), nullable=True,
                       comment="创建时间")


class FactBreakBoardMonitorLog(Base):
    """
    断板监控运行日志

    记录断板识别和价格监控服务的运行状态
    """

    __tablename__ = "fact_break_board_monitor_log"
    __table_args__ = (
        Index('idx_monitor_log_date', 'trade_date'),
        {'comment': '断板监控运行日志'}
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment="自增ID")
    trade_date = Column(Date, nullable=False, comment="交易日")

    # 运行状态
    monitor_type = Column(String(20), nullable=False,
                         comment="监控类型：detect(断板识别)/price(价格监控)")
    status = Column(String(20), nullable=False,
                   comment="状态：running/success/failed")

    # 统计信息
    stocks_checked = Column(Integer, nullable=True,
                           comment="检查股票数量")
    stocks_updated = Column(Integer, nullable=True,
                           comment="更新股票数量")
    alerts_triggered = Column(Integer, nullable=True,
                             comment="触发提醒数量")

    # 错误信息
    error_message = Column(String(1000), nullable=True, comment="错误信息")

    started_at = Column(DateTime, nullable=True, comment="开始时间")
    completed_at = Column(DateTime, nullable=True, comment="完成时间")
    created_at = Column(DateTime, server_default=func.now(), nullable=True,
                       comment="创建时间")
