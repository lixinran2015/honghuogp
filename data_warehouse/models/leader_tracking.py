"""
龙头跟踪池（持久化）与同步日志表

目标：
1) 只要股票曾被判定为"空间龙头 / 刚启动"，就永久保留在跟踪池中
2) 每天将当天新出现的候选增量写入池中
3) 前端基于跟踪池成员进行"震荡/退潮风险/强势"的日线计算展示
4) 支持多因子评分和买点检测（Phase 1升级）
"""

from __future__ import annotations

from sqlalchemy import Column, String, Boolean, Date, DateTime, Integer, Numeric, Text
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

    # 封单比（涨停时的封单量/成交量）
    block_ratio = Column(Numeric(5, 2), nullable=True, comment="封单比")

    # ========== Phase 1 升级：多因子评分相关字段 ==========
    # 综合评分 0-100
    score = Column(Numeric(5, 2), nullable=True, comment="综合评分 0-100")
    # 评级 S/A/B/C
    grade = Column(String(2), nullable=True, comment="评级 S/A/B/C")
    # 当前买点信号
    buy_signal = Column(String(50), nullable=True, comment="当前买点信号")
    # 风险等级 高/中/低
    risk_level = Column(String(10), nullable=True, comment="风险等级 高/中/低")
    # 入池时情绪周期
    emotion_cycle = Column(String(20), nullable=True, comment="入池时情绪周期")
    # 板块强度
    sector_strength = Column(Numeric(5, 2), nullable=True, comment="板块强度")
    # 评分明细
    score_breakdown = Column(JSONB, nullable=True, comment="评分明细")
    # 入池原因
    entry_reason = Column(Text, nullable=True, comment="入池原因")
    # 关联的失败案例ID
    failed_case_id = Column(Integer, nullable=True, comment="关联的失败案例ID")

    # ========== 主线雷达相关字段 ==========
    # 主线雷达状态
    startup_is_started = Column(Boolean, nullable=True, comment="主线雷达-是否已启动")
    startup_core_passed = Column(Boolean, nullable=True, comment="主线雷达-核心条件通过")
    startup_assist_count = Column(Integer, nullable=True, comment="主线雷达-辅助条件满足数")
    startup_risk_passed = Column(Boolean, nullable=True, comment="主线雷达-风险排除通过")
    startup_stage = Column(String(20), nullable=True, comment="主线雷达-阶段")
    startup_score = Column(Integer, nullable=True, comment="主线雷达-启动得分")
    # 主线雷达技术指标
    startup_indicators = Column(JSONB, nullable=True, comment="主线雷达-技术指标数据")

    created_at = Column(DateTime, server_default=func.now(), nullable=True, comment="创建时间")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=True, comment="更新时间")


class FactLeaderTrackingPoolSyncLog(Base):
    """每日同步日志：避免重复跑重计算"""

    __tablename__ = "fact_leader_tracking_pool_sync_log"

    trade_date = Column(Date, primary_key=True, comment="交易日")
    synced_at = Column(DateTime, server_default=func.now(), nullable=True, comment="同步完成时间")


class FactLeaderTrackingFailed(Base):
    """龙头跟踪失败案例（缓解幸存者偏差）"""

    __tablename__ = "fact_leader_tracking_failed"
    __table_args__ = {}

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键ID")
    ts_code = Column(String(20), nullable=False, comment="股票代码")
    name = Column(String(128), nullable=False, comment="股票名称")
    trade_date = Column(Date, nullable=False, comment="交易日")
    reason = Column(String(50), nullable=False, comment="失败原因: score_too_low/炸板/冲高回落/其他")

    # 当时评分数据
    score = Column(Numeric(5, 2), nullable=True, comment="当时评分")
    score_breakdown = Column(JSONB, nullable=True, comment="评分明细")
    period_return_pct = Column(Numeric(8, 2), nullable=True, comment="当时区间涨幅")
    continuous_limit = Column(Integer, nullable=True, comment="当时连板数")
    sector_name = Column(String(100), nullable=True, comment="所属板块")

    # 后续表现（用于复盘分析）
    day_1_return = Column(Numeric(8, 2), nullable=True, comment="第1日表现")
    day_3_return = Column(Numeric(8, 2), nullable=True, comment="第3日表现")
    day_5_return = Column(Numeric(8, 2), nullable=True, comment="第5日表现")
    subsequent_performance = Column(JSONB, nullable=True, comment="详细后续表现数据")

    created_at = Column(DateTime, server_default=func.now(), nullable=True, comment="创建时间")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=True, comment="更新时间")


class FactLeaderScoreHistory(Base):
    """龙头评分历史（用于模型监控和回测）"""

    __tablename__ = "fact_leader_score_history"
    __table_args__ = {}

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键ID")
    ts_code = Column(String(20), nullable=False, comment="股票代码")
    trade_date = Column(Date, nullable=False, comment="交易日")

    # 综合评分
    total_score = Column(Numeric(5, 2), nullable=False, comment="综合评分 0-100")
    grade = Column(String(2), nullable=True, comment="评级 S/A/B/C")

    # 因子评分明细
    leader_position_score = Column(Numeric(5, 2), nullable=True, comment="龙头地位评分 30%")
    technical_score = Column(Numeric(5, 2), nullable=True, comment="技术形态评分 25%")
    money_flow_score = Column(Numeric(5, 2), nullable=True, comment="资金流向评分 25%")
    sentiment_score = Column(Numeric(5, 2), nullable=True, comment="情绪热度评分 20%")

    # 因子原始数据（用于归因分析）
    leader_position_data = Column(JSONB, nullable=True, comment="龙头地位因子数据")
    technical_data = Column(JSONB, nullable=True, comment="技术形态因子数据")
    money_flow_data = Column(JSONB, nullable=True, comment="资金流向因子数据")
    sentiment_data = Column(JSONB, nullable=True, comment="情绪热度因子数据")

    # 市场环境
    emotion_cycle = Column(String(20), nullable=True, comment="情绪周期")
    market_status = Column(String(20), nullable=True, comment="市场状态")

    created_at = Column(DateTime, server_default=func.now(), nullable=True, comment="创建时间")


class FactLeaderBuySignal(Base):
    """龙头买点信号检测记录"""

    __tablename__ = "fact_leader_buy_signal"
    __table_args__ = {}

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键ID")
    ts_code = Column(String(20), nullable=False, comment="股票代码")
    trade_date = Column(Date, nullable=False, comment="交易日")
    signal_type = Column(String(30), nullable=False, comment="买点类型: 首板放量/二板缩量/三板换手/断板反包/龙头首阴/其他")

    # 信号强度
    strength_score = Column(Numeric(5, 2), nullable=True, comment="信号强度评分 0-100")
    confidence_level = Column(String(10), nullable=True, comment="置信度: high/medium/low")

    # 触发条件详情
    trigger_conditions = Column(JSONB, nullable=True, comment="触发条件详情")
    technical_indicators = Column(JSONB, nullable=True, comment="技术指标数据")

    # 信号结果（后续回填）
    is_valid = Column(Boolean, nullable=True, comment="是否有效信号")
    actual_return_1d = Column(Numeric(8, 2), nullable=True, comment="1日后实际收益")
    actual_return_3d = Column(Numeric(8, 2), nullable=True, comment="3日后实际收益")
    actual_return_5d = Column(Numeric(8, 2), nullable=True, comment="5日后实际收益")

    created_at = Column(DateTime, server_default=func.now(), nullable=True, comment="创建时间")
