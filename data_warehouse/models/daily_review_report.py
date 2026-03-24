# -*- coding: utf-8 -*-
"""
每日复盘报告模型
"""

from datetime import datetime, date
from typing import Optional, Dict, Any

from sqlalchemy import BigInteger, Boolean, Column, Date, DateTime, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .generated_models import Base


class FactDailyReviewReport(Base):
    """每日复盘报告表"""
    __tablename__ = 'fact_daily_review_report'
    __table_args__ = (
        {'comment': '每日复盘报告存储表'}
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, server_default=text("nextval('fact_daily_review_report_id_seq'::regclass)"))
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('1'), comment='用户ID')
    review_date: Mapped[date] = mapped_column(Date, nullable=False, comment='复盘日期')
    report_type: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'daily'::character varying"), comment='报告类型：daily/pattern')
    report_content: Mapped[str] = mapped_column(Text, nullable=False, comment='报告内容')
    raw_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, comment='原始数据')
    is_prev_day_review: Mapped[bool] = mapped_column(Boolean, server_default=text('false'), comment='是否为复盘前一交易日')
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, server_default=text('CURRENT_TIMESTAMP'), comment='创建时间')
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, server_default=text('CURRENT_TIMESTAMP'), comment='更新时间')
