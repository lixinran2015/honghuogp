"""
股票启动候选模型
"""

from sqlalchemy import Column, String, Integer, Boolean, Date, DateTime, Text, BigInteger, Numeric, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from data_warehouse.models.base import Base


class FactStockStartupCandidate(Base):
    """股票启动候选表"""
    __tablename__ = 'fact_stock_startup_candidate'
    __mapper_args__ = {"confirm_deleted_rows": False}

    # 主键
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    
    # 股票基本信息
    ts_code = Column(String(20), nullable=False, index=True, comment='股票代码')
    trade_date = Column(Date, nullable=False, index=True, comment='交易日期')
    
    # 启动判断结果
    score = Column(Integer, nullable=False, comment='启动得分(0-100)')
    is_started = Column(Boolean, default=False, comment='是否判定为启动')
    
    # 通过的层级
    basic_passed = Column(Boolean, default=False, comment='基础过滤是否通过')
    core_passed = Column(Boolean, default=False, comment='核心判定是否通过')
    assist_count = Column(Integer, default=0, comment='辅助确认满足数量')
    risk_passed = Column(Boolean, default=False, comment='风险排除是否通过')
    
    # 确认日期字段
    core_confirmed_date = Column(Date, comment='核心确认日期（核心条件全部通过的日期）')
    assist_confirmed_date = Column(Date, comment='辅助确认日期（辅助条件至少满足1个的日期）')
    risk_passed_date = Column(Date, comment='风险排除日期（风险排除条件全部通过的日期）')
    
    # 满足的信号
    passed_signals = Column(ARRAY(Text), comment='通过的信号列表')
    
    # 风险原因
    risk_reasons = Column(ARRAY(Text), comment='风险原因列表')
    
    # 详细指标数据
    indicators = Column(JSONB, comment='详细指标数据(JSON)')
    
    # MA10相关字段
    latest_price = Column(Numeric(10, 2), comment='最新价格')
    ma10 = Column(Numeric(10, 2), comment='10日均线')
    is_broken_ma10 = Column(Boolean, default=False, comment='是否破10日线')
    last_check_date = Column(Date, comment='最后检查日期')
    
    # 两阶段筛选字段
    stage = Column(String(20), default='golden_cross', comment='阶段：golden_cross(金叉候选)/confirmed(启动确认)')
    golden_cross_date = Column(Date, comment='5日金叉10日发生的日期')
    days_since_cross = Column(Integer, comment='距离金叉发生的天数')
    
    # 推荐相关字段
    is_recommended = Column(Boolean, default=False, comment='是否已加入推荐池')
    recommend_date = Column(Date, comment='推荐日期')
    recommend_id = Column(Integer, comment='推荐记录ID')
    
    # 批量诊断结果（持久化）
    diagnosis_result = Column(JSONB, comment='批量诊断结果（JSON）：{core_checks, passed_count, advice, distance_from_high等}')
    last_diagnosis_date = Column(Date, comment='最后诊断日期')
    
    # 财务检测结果（持久化）
    financial_check_result = Column(JSONB, comment='财务检测结果（JSON）：{is_passed, failure_reasons, industry, sector, check_date等}')
    last_financial_check_date = Column(Date, comment='最后财务检测日期')
    
    # 待候选监控字段
    is_watching = Column(Boolean, default=False, comment='是否加入待候选监控（2/3条件）')
    missing_conditions = Column(ARRAY(String), comment='缺少的核心条件列表')
    watch_start_date = Column(Date, comment='开始监控日期')
    last_check_time = Column(DateTime, comment='最后检查时间')
    check_count = Column(Integer, default=0, comment='已检查次数')
    alert_sent = Column(Boolean, default=False, comment='是否已发送语音提醒')
    
    # 退出相关字段
    is_exited = Column(Boolean, default=False, comment='是否已退出启动')
    exit_date = Column(Date, comment='退出日期')
    exit_reason = Column(String(100), comment='退出原因')
    
    # 表现数据字段
    change_5d = Column(Numeric(10, 2), comment='后5日涨幅（百分比）')
    change_5d_days = Column(Integer, comment='后5日涨幅实际交易日数')
    change_10d = Column(Numeric(10, 2), comment='后10日涨幅（百分比）')
    change_10d_days = Column(Integer, comment='后10日涨幅实际交易日数')
    change_20d = Column(Numeric(10, 2), comment='后20日涨幅（百分比）')
    change_20d_days = Column(Integer, comment='后20日涨幅实际交易日数')
    change_60d = Column(Numeric(10, 2), comment='后60日涨幅（百分比）')
    change_60d_days = Column(Integer, comment='后60日涨幅实际交易日数')
    performance_calculated_at = Column(DateTime, comment='表现数据计算时间')
    
    # 元数据
    created_at = Column(DateTime, server_default=func.now(), comment='创建时间')
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment='更新时间')

