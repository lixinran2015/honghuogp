"""
原始数据层（Raw Layer）
负责存储多数据源的原始数据
"""

import logging
from typing import List, Dict, Optional
from datetime import date
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import IntegrityError

from data_warehouse.config import DATABASE_URL
from data_warehouse.db import get_shared_engine
from data_warehouse.models import RawDailyPrice
from data_warehouse.models import RawFundamental
from data_warehouse.models import ETLLog
from data_warehouse.models import DimStock

logger = logging.getLogger(__name__)


class RawDataLayer:
    """原始数据层"""
    
    def __init__(self, database_url: Optional[str] = None):
        """
        初始化原始数据层
        
        Args:
            database_url: 数据库连接URL，如果为None则从config读取
        """
        self.database_url = database_url or DATABASE_URL
        self.engine = get_shared_engine()
        self.SessionLocal = sessionmaker(bind=self.engine)
        logger.debug("✅ RawDataLayer已初始化")
    
    def get_session(self) -> Session:
        """获取数据库会话"""
        return self.SessionLocal()
    
    def _serialize_payload(self, payload: Optional[Dict]) -> Optional[Dict]:
        """
        序列化payload，将date对象转换为字符串，处理NaN值
        
        Args:
            payload: 原始数据字典
        
        Returns:
            Dict: 序列化后的字典
        """
        if payload is None:
            return None
        
        import json
        import math
        from datetime import date, datetime
        
        def clean_value(v):
            """清理值，将NaN/Inf转为None"""
            if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                return None
            return v
        
        def default_serializer(obj):
            if isinstance(obj, (date, datetime)):
                return obj.isoformat()
            if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
                return None
            raise TypeError(f"Type {type(obj)} not serializable")
        
        # 先清理NaN值
        cleaned_payload = {}
        for key, value in payload.items():
            cleaned_payload[key] = clean_value(value)
        
        # 转换为JSON字符串再解析回来，确保所有对象都被序列化
        try:
            json_str = json.dumps(cleaned_payload, default=default_serializer)
            return json.loads(json_str)
        except Exception as e:
            logger.debug(f"序列化payload失败: {e}")
            # 如果序列化失败，尝试手动转换
            serialized = {}
            for key, value in cleaned_payload.items():
                if isinstance(value, (date, datetime)):
                    serialized[key] = value.isoformat()
                else:
                    serialized[key] = value
            return serialized
    
    def save_daily_price(
        self,
        ts_code: str,
        trade_date: date,
        data: Dict,
        source: str,
        raw_payload: Optional[Dict] = None
    ) -> bool:
        """
        保存日线行情原始数据
        
        Args:
            ts_code: 股票代码（Tushare格式）
            trade_date: 交易日期
            data: 日线数据字典，包含 open, high, low, close, pre_close, vol, amount, turnover_rate
            source: 数据源名称（'tushare', 'akshare'等）
            raw_payload: 原始返回数据（JSON格式，可选）
        
        Returns:
            bool: 是否保存成功
        """
        session = self.get_session()
        try:
            # 序列化payload
            serialized_payload = self._serialize_payload(raw_payload)
            
            # 检查是否已存在
            existing = session.query(RawDailyPrice).filter(
                RawDailyPrice.ts_code == ts_code,
                RawDailyPrice.trade_date == trade_date,
                RawDailyPrice.source == source
            ).first()
            
            if existing:
                # 更新现有记录
                existing.open = data.get('open')
                existing.high = data.get('high')
                existing.low = data.get('low')
                existing.close = data.get('close')
                existing.pre_close = data.get('pre_close')
                existing.vol = data.get('vol')
                existing.amount = data.get('amount')
                existing.turnover_rate = data.get('turnover_rate')
                if serialized_payload:
                    existing.raw_payload = serialized_payload
                logger.debug(f"更新Raw日线数据: {ts_code} {trade_date} {source}")
            else:
                # 创建新记录
                raw_price = RawDailyPrice(
                    ts_code=ts_code,
                    trade_date=trade_date,
                    open=data.get('open'),
                    high=data.get('high'),
                    low=data.get('low'),
                    close=data.get('close'),
                    pre_close=data.get('pre_close'),
                    vol=data.get('vol'),
                    amount=data.get('amount'),
                    turnover_rate=data.get('turnover_rate'),
                    source=source,
                    raw_payload=serialized_payload
                )
                session.add(raw_price)
                logger.debug(f"新增Raw日线数据: {ts_code} {trade_date} {source}")
            
            session.commit()
            
            # 记录ETL日志
            self._log_etl(ts_code, trade_date, source, 'daily_price', 'success', 1)
            
            return True
            
        except IntegrityError as e:
            session.rollback()
            logger.warning(f"Raw日线数据已存在（唯一约束）: {ts_code} {trade_date} {source}")
            self._log_etl(ts_code, trade_date, source, 'daily_price', 'skipped', 0, str(e)[:200])
            return False
        except Exception as e:
            session.rollback()
            logger.error(f"保存Raw日线数据失败: {ts_code} {trade_date} {source}: {e}", exc_info=True)
            self._log_etl(ts_code, trade_date, source, 'daily_price', 'failed', 0, str(e)[:200])
            return False
        finally:
            session.close()
    
    def save_fundamental(
        self,
        ts_code: str,
        end_date: date,
        report_type: str,
        data: Dict,
        source: str,
        raw_payload: Optional[Dict] = None
    ) -> bool:
        """
        保存财务数据原始数据
        
        Args:
            ts_code: 股票代码（Tushare格式）
            end_date: 报告期
            report_type: 报告类型（'annual', 'q1', 'q2', 'q3'）
            data: 财务数据字典
            source: 数据源名称
            raw_payload: 原始返回数据（可选）
        
        Returns:
            bool: 是否保存成功
        """
        session = self.get_session()
        try:
            # 序列化payload
            serialized_payload = self._serialize_payload(raw_payload)
            
            # 检查是否已存在
            existing = session.query(RawFundamental).filter(
                RawFundamental.ts_code == ts_code,
                RawFundamental.end_date == end_date,
                RawFundamental.report_type == report_type,
                RawFundamental.source == source
            ).first()
            
            if existing:
                # 更新现有记录
                existing.roe = data.get('roe')
                existing.net_margin = data.get('net_margin')
                existing.gross_margin = data.get('gross_margin')
                existing.op_cf = data.get('op_cf')
                existing.total_debt = data.get('total_debt')
                existing.total_asset = data.get('total_asset')
                existing.debt_ratio = data.get('debt_ratio')
                existing.profit_volatility = data.get('profit_volatility')
                if serialized_payload:
                    existing.raw_payload = serialized_payload
                logger.debug(f"更新Raw财务数据: {ts_code} {end_date} {source}")
            else:
                # 创建新记录
                raw_fundamental = RawFundamental(
                    ts_code=ts_code,
                    end_date=end_date,
                    report_type=report_type,
                    roe=data.get('roe'),
                    net_margin=data.get('net_margin'),
                    gross_margin=data.get('gross_margin'),
                    op_cf=data.get('op_cf'),
                    total_debt=data.get('total_debt'),
                    total_asset=data.get('total_asset'),
                    debt_ratio=data.get('debt_ratio'),
                    profit_volatility=data.get('profit_volatility'),
                    source=source,
                    raw_payload=serialized_payload
                )
                session.add(raw_fundamental)
                logger.debug(f"新增Raw财务数据: {ts_code} {end_date} {source}")
            
            session.commit()
            return True
            
        except IntegrityError as e:
            session.rollback()
            logger.warning(f"Raw财务数据已存在（唯一约束）: {ts_code} {end_date} {source}")
            return False
        except Exception as e:
            session.rollback()
            logger.error(f"保存Raw财务数据失败: {ts_code} {end_date} {source}: {e}", exc_info=True)
            return False
        finally:
            session.close()
    
    def save_stock_info(
        self,
        ts_code: str,
        exchange: str,
        symbol: str,
        name: str,
        list_date: Optional[date] = None,
        delist_date: Optional[date] = None,
        industry: Optional[str] = None,
        concept_tags: Optional[List[str]] = None
    ) -> bool:
        """
        保存股票基本信息到维表
        
        Args:
            ts_code: 股票代码（Tushare格式）
            exchange: 交易所（'SSE', 'SZSE', 'BSE'）
            symbol: 股票代码（6位数字）
            name: 股票名称
            list_date: 上市日期
            delist_date: 退市日期
            industry: 行业
            concept_tags: 概念标签列表
        
        Returns:
            bool: 是否保存成功
        """
        session = self.get_session()
        try:
            # 检查是否已存在
            existing = session.query(DimStock).filter(
                DimStock.ts_code == ts_code
            ).first()
            
            if existing:
                # 更新现有记录
                existing.exchange = exchange
                existing.symbol = symbol
                existing.name = name
                if list_date:
                    existing.list_date = list_date
                if delist_date:
                    existing.delist_date = delist_date
                if industry:
                    existing.industry = industry
                if concept_tags:
                    existing.concept_tags = concept_tags
                logger.debug(f"更新股票维表: {ts_code} {name}")
            else:
                # 创建新记录
                stock = DimStock(
                    ts_code=ts_code,
                    exchange=exchange,
                    symbol=symbol,
                    name=name,
                    list_date=list_date,
                    delist_date=delist_date,
                    industry=industry,
                    concept_tags=concept_tags or []
                )
                session.add(stock)
                logger.debug(f"新增股票维表: {ts_code} {name}")
            
            session.commit()
            return True
            
        except IntegrityError as e:
            session.rollback()
            logger.warning(f"股票维表数据已存在: {ts_code}")
            return False
        except Exception as e:
            session.rollback()
            logger.error(f"保存股票维表失败: {ts_code}: {e}", exc_info=True)
            return False
        finally:
            session.close()
    
    def get_raw_daily_price(
        self,
        ts_code: str,
        trade_date: date,
        source: Optional[str] = None
    ) -> List[RawDailyPrice]:
        """
        获取原始日线数据
        
        Args:
            ts_code: 股票代码
            trade_date: 交易日期
            source: 数据源，如果为None则返回所有数据源
        
        Returns:
            List[RawDailyPrice]: 原始日线数据列表
        """
        session = self.get_session()
        try:
            query = session.query(RawDailyPrice).filter(
                RawDailyPrice.ts_code == ts_code,
                RawDailyPrice.trade_date == trade_date
            )
            
            if source:
                query = query.filter(RawDailyPrice.source == source)
            
            return query.all()
        finally:
            session.close()
    
    def get_raw_fundamental(
        self,
        ts_code: str,
        end_date: date,
        report_type: Optional[str] = None,
        source: Optional[str] = None
    ) -> List[RawFundamental]:
        """
        获取原始财务数据
        
        Args:
            ts_code: 股票代码
            end_date: 报告期
            report_type: 报告类型，如果为None则返回所有类型
            source: 数据源，如果为None则返回所有数据源
        
        Returns:
            List[RawFundamental]: 原始财务数据列表
        """
        session = self.get_session()
        try:
            query = session.query(RawFundamental).filter(
                RawFundamental.ts_code == ts_code,
                RawFundamental.end_date == end_date
            )
            
            if report_type:
                query = query.filter(RawFundamental.report_type == report_type)
            
            if source:
                query = query.filter(RawFundamental.source == source)
            
            return query.all()
        finally:
            session.close()
    
    def _log_etl(
        self,
        ts_code: str,
        trade_date: date,
        source: str,
        data_type: str,
        status: str,
        records_count: int = 0,
        error_message: Optional[str] = None
    ):
        """记录ETL日志"""
        session = self.get_session()
        try:
            log = ETLLog(
                ts_code=ts_code,
                trade_date=trade_date,
                source=source,
                data_type=data_type,
                status=status,
                records_count=records_count,
                error_message=error_message
            )
            session.add(log)
            session.commit()
        except Exception as e:
            logger.debug(f"记录ETL日志失败: {e}")
        finally:
            session.close()

