"""
长线跟踪池模型
"""
from datetime import datetime, date
from decimal import Decimal
from typing import Optional

from sqlalchemy import String, Date, DateTime, Numeric, Text, JSON, Integer
from sqlalchemy.orm import Mapped, mapped_column

from data_warehouse.models.base import Base


class FactLongTermTrackingPool(Base):
    """长线跟踪池"""
    __tablename__ = "fact_long_term_tracking_pool"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts_code: Mapped[str] = mapped_column(String(20), nullable=False, comment="股票代码")
    name: Mapped[Optional[str]] = mapped_column(String(50), comment="股票名称")
    industry: Mapped[Optional[str]] = mapped_column(String(50), comment="所属行业")
    sector_type: Mapped[Optional[str]] = mapped_column(String(50), comment="行业类型")
    track_date: Mapped[date] = mapped_column(Date, nullable=False, comment="入选日期")
    source: Mapped[Optional[str]] = mapped_column(
        String(50), default="four_step_selection", comment="来源"
    )
    status: Mapped[Optional[str]] = mapped_column(
        String(20), default="watching", comment="状态: watching/promoted/dropped"
    )
    composite_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2), comment="综合评分")
    darwin_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2), comment="Darwin评分")
    financial_health: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(6, 4), comment="财务健康系数"
    )
    pe_ttm: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4), comment="PE_TTM")
    pb: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4), comment="PB")
    roe_ttm: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4), comment="ROE_TTM")
    amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 4), comment="入选时成交额")
    close_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4), comment="入选时收盘价")
    check_result: Mapped[Optional[dict]] = mapped_column(JSON, comment="最近一次检查结果")
    drop_reason: Mapped[Optional[str]] = mapped_column(Text, comment="剔除理由")
    note: Mapped[Optional[str]] = mapped_column(Text, comment="备注")
    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, default=datetime.now, comment="创建时间"
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间"
    )
