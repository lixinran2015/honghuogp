"""
热门板块模型
存储用户自定义的热门板块信息及板块-股票关联
"""
from sqlalchemy import Column, String, DateTime, Text, BigInteger, Integer, ForeignKey, func, UniqueConstraint
from data_warehouse.models.base import Base


class DimHotSector(Base):
    """热门板块表"""
    __tablename__ = 'dim_hot_sector'
    
    # 主键
    id = Column(BigInteger, primary_key=True, autoincrement=True, comment='板块ID')
    
    # 板块基本信息
    name = Column(String(100), nullable=False, comment='板块名称')
    description = Column(Text, comment='板块描述')
    sort_order = Column(Integer, default=0, comment='排序序号')
    status = Column(String(20), default='active', comment='状态：active/inactive')
    notes = Column(Text, comment='备注信息')
    
    # 时间戳
    created_at = Column(DateTime, server_default=func.now(), comment='创建时间')
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment='更新时间')
    created_by = Column(String(50), comment='创建人（预留）')
    
    def __repr__(self):
        return f"<DimHotSector(id={self.id}, name={self.name}, status={self.status})>"


class FactHotSectorStock(Base):
    """热门板块-股票关联表"""
    __tablename__ = 'fact_hot_sector_stock'
    __table_args__ = (
        UniqueConstraint('sector_id', 'ts_code', name='uq_sector_stock'),
    )
    
    # 主键
    id = Column(BigInteger, primary_key=True, autoincrement=True, comment='关联ID')
    
    # 关联信息
    sector_id = Column(BigInteger, ForeignKey('dim_hot_sector.id', ondelete='CASCADE'), nullable=False, index=True, comment='板块ID')
    ts_code = Column(String(20), nullable=False, index=True, comment='股票代码（Tushare格式）')
    stock_name = Column(String(100), comment='股票名称（冗余存储）')
    
    # 其他信息
    added_at = Column(DateTime, server_default=func.now(), comment='添加时间')
    added_by = Column(String(50), comment='添加人（预留）')
    notes = Column(Text, comment='备注')
    
    def __repr__(self):
        return f"<FactHotSectorStock(id={self.id}, sector_id={self.sector_id}, ts_code={self.ts_code})>"
