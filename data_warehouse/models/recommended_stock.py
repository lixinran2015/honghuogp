"""
推荐股票表 ORM 模型
"""
from sqlalchemy import Column, String, Integer, Boolean, Date, DateTime, Text, Numeric, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from data_warehouse.models.base import Base


class FactRecommendedStock(Base):
    """推荐股票事实表"""
    
    __tablename__ = 'fact_recommended_stocks'
    
    # 主键
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # 股票信息
    ts_code = Column(String(10), nullable=False, index=True, comment='股票代码')
    recommend_date = Column(Date, nullable=False, index=True, comment='推荐日期')
    entry_price = Column(Numeric(10, 2), comment='入选价格')
    current_price = Column(Numeric(10, 2), comment='当前价格')
    
    # 推荐原因
    recommend_reason = Column(Text, comment='推荐原因（完整描述）')
    recommend_tags = Column(ARRAY(String), comment='推荐标签')
    
    # 信号强度
    startup_score = Column(Integer, comment='启动得分（60-100）')
    signal_strength = Column(String(20), comment='信号强度：强/中/弱')
    
    # 技术指标状态
    macd_status = Column(String(20), comment='MACD状态')
    kdj_status = Column(String(20), comment='KDJ状态')
    volume_ratio = Column(Numeric(10, 2), comment='量比')
    
    # 市场表现
    change_5d = Column(Numeric(10, 2), comment='5日涨幅')
    change_10d = Column(Numeric(10, 2), comment='10日涨幅')
    amount = Column(Numeric(20, 2), comment='成交额')
    
    # 风险提示
    risk_level = Column(String(20), comment='风险等级：低/中/高')
    risk_note = Column(Text, comment='风险提示')
    
    # 状态管理
    status = Column(String(20), default='active', comment='状态：active/closed/stopped')
    stop_loss_price = Column(Numeric(10, 2), comment='止损价')
    take_profit_price = Column(Numeric(10, 2), comment='止盈价')
    
    # 追踪数据
    max_gain = Column(Numeric(10, 2), comment='最大涨幅')
    max_drawdown = Column(Numeric(10, 2), comment='最大回撤')
    
    # 七维细分得分（JSON：{technical: 85, leader: 70, ...}）
    dimension_scores = Column(JSONB, comment='七维细分得分')
    
    # 时间戳
    created_at = Column(DateTime, default=func.now(), comment='创建时间')
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), comment='更新时间')
    
    def __repr__(self):
        return f"<FactRecommendedStock(ts_code={self.ts_code}, recommend_date={self.recommend_date}, score={self.startup_score})>"

