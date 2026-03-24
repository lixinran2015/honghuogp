"""
龙头跟踪池（持久化）与同步日志表

目标：
1) 只要股票曾被判定为“空间龙头 / 刚启动”，就永久保留在跟踪池中
2) 每天将当天新出现的候选增量写入池中
3) 前端基于跟踪池成员进行“震荡/退潮风险/强势”的日线计算展示
"""

from __future__ import annotations

from sqlalchemy import Column, String, Boolean, Date, DateTime, Integer
from sqlalchemy import func, text
from sqlalchemy.dialects.postgresql import JSONB

from data_warehouse.models.base import Base


class FactLeaderTrackingPool(Base):
    """龙头跟踪池：成员持久化（去重：ts_code 唯一）"""

    __tablename__ = "fact_leader_tracking_pool"
    __table_args__ = {}

    ts_code = Column(String(20), primary_key=True, comment="股票代码（Tushare格式）")
    name = Column(String(128), nullable=False, comment="股票名称")

    # 类型标记：一旦曾满足则长期保留（标记可能随时间从 false -> true）
    is_space = Column(Boolean, nullable=False, server_default="false", comment="是否为空间龙头（出现过即可）")
    is_new = Column(Boolean, nullable=False, server_default="false", comment="是否为刚启动龙头（出现过即可）")

    # 首次出现日期（仅在第一次从 false -> true 时写入）
    first_space_date = Column(Date, nullable=True, comment="首次出现为空间龙头的交易日")
    first_new_date = Column(Date, nullable=True, comment="首次出现为刚启动龙头的交易日")

    # 最近一次出现的交易日（空间/刚启动任一条件命中）
    last_seen_date = Column(Date, nullable=False, comment="最近一次进入/命中的交易日")

    # 展示用：股票曾关联到的主线/板块名称（冗余存储，便于前端展示）
    # - 对应 LeaderTrackingView.vue 中 row.sectors 的值：与 sector-strength 返回的 sector_name 对齐
    sectors = Column(
        JSONB,
        nullable=False,
        server_default=text("'[]'::jsonb"),
        comment="关联主线/板块名称列表",
    )

    # 连板高度（从 fact_sector_leader_snapshot 的 continuous_limit 取到的最大值）
    continuous_limit = Column(Integer, nullable=True, comment="连板高度（取历史最大）")

    created_at = Column(DateTime, server_default=func.now(), nullable=True, comment="创建时间")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=True, comment="更新时间")


class FactLeaderTrackingPoolSyncLog(Base):
    """每日同步日志：避免重复跑重计算"""

    __tablename__ = "fact_leader_tracking_pool_sync_log"

    trade_date = Column(Date, primary_key=True, comment="交易日")
    synced_at = Column(DateTime, server_default=func.now(), nullable=True, comment="同步完成时间")

