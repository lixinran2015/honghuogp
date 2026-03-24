"""
数据仓库服务层
提供统一的查询接口给策略和前端使用
"""

import logging
from typing import List, Dict, Optional
from datetime import date, datetime
from sqlalchemy.orm import Session

from data_warehouse.db import get_shared_engine, get_session as _get_db_session
from data_warehouse.models import FactDailyPrice
from data_warehouse.models import FactDailyPriceQfq
from data_warehouse.models import FactFundamental
from data_warehouse.models import DimStock
from sqlalchemy import func

logger = logging.getLogger(__name__)


class WarehouseService:
    """数据仓库服务类"""
    
    def __init__(self, database_url: Optional[str] = None):
        """
        初始化数据仓库服务
        
        Args:
            database_url: 数据库连接URL（保留兼容，实际使用共享引擎）
        """
        self.engine = get_shared_engine()
        logger.debug("✅ WarehouseService已初始化")
    
    def get_session(self) -> Session:
        """获取数据库会话（使用共享连接池）"""
        return _get_db_session()
    
    def get_daily_ohlc(
        self,
        ts_code: str,
        start: date,
        end: date
    ) -> List[Dict]:
        """
        从 fact_daily_price 读取日线数据
        
        Args:
            ts_code: 股票代码（Tushare格式）
            start: 开始日期
            end: 结束日期
        
        Returns:
            List[Dict]: 日线数据列表
        """
        session = self.get_session()
        try:
            results = session.query(FactDailyPrice).filter(
                FactDailyPrice.ts_code == ts_code,
                FactDailyPrice.trade_date >= start,
                FactDailyPrice.trade_date <= end
            ).order_by(FactDailyPrice.trade_date).all()
            
            # 转换为字典列表
            data_list = []
            for r in results:
                data_list.append({
                    'ts_code': r.ts_code,
                    'trade_date': r.trade_date,
                    'open': float(r.open) if r.open else None,
                    'high': float(r.high) if r.high else None,
                    'low': float(r.low) if r.low else None,
                    'close': float(r.close) if r.close else None,
                    'pre_close': float(r.pre_close) if r.pre_close else None,
                    'vol': float(r.vol) if r.vol else None,
                    'amount': float(r.amount) if r.amount else None,
                    'turnover_rate': float(r.turnover_rate) if r.turnover_rate else None,
                    'data_quality': r.data_quality,
                    'sources_used': r.sources_used or []
                })
            
            logger.debug(f"查询日线数据: {ts_code} ({start} to {end}), 返回 {len(data_list)} 条")
            return data_list
            
        except Exception as e:
            logger.error(f"查询日线数据失败: {ts_code}: {e}", exc_info=True)
            return []
        finally:
            session.close()
    
    def get_latest_daily(self, ts_code: str) -> Optional[Dict]:
        """
        读取最近一个交易日的日线
        
        Args:
            ts_code: 股票代码
        
        Returns:
            Dict: 最新日线数据，如果不存在返回None
        """
        session = self.get_session()
        try:
            result = session.query(FactDailyPrice).filter(
                FactDailyPrice.ts_code == ts_code
            ).order_by(FactDailyPrice.trade_date.desc()).first()
            
            if result:
                return {
                    'ts_code': result.ts_code,
                    'trade_date': result.trade_date,
                    'open': float(result.open) if result.open else None,
                    'high': float(result.high) if result.high else None,
                    'low': float(result.low) if result.low else None,
                    'close': float(result.close) if result.close else None,
                    'pre_close': float(result.pre_close) if result.pre_close else None,
                    'vol': float(result.vol) if result.vol else None,
                    'amount': float(result.amount) if result.amount else None,
                    'turnover_rate': float(result.turnover_rate) if result.turnover_rate else None,
                    'data_quality': result.data_quality,
                    'sources_used': result.sources_used or []
                }
            return None
            
        except Exception as e:
            logger.error(f"查询最新日线数据失败: {ts_code}: {e}", exc_info=True)
            return None
        finally:
            session.close()

    def get_latest_trade_date(self) -> Optional[date]:
        """
        获取「最新有数据的交易日」：fact_daily_price_qfq 中最大的 trade_date。
        用于主线雷达等按交易日窗口计算，避免跨自然日 0 点后窗口变化。
        """
        session = self.get_session()
        try:
            row = (
                session.query(func.max(FactDailyPriceQfq.trade_date))
                .scalar()
            )
            return row
        except Exception as e:
            logger.warning("查询最新交易日失败: %s", e)
            return None
        finally:
            session.close()
    
    def get_fundamental(
        self,
        ts_code: str,
        end_date: Optional[date] = None
    ) -> Optional[Dict]:
        """
        读取指定报告期的财务数据
        
        Args:
            ts_code: 股票代码
            end_date: 报告期，如果为None则获取最新一期
        
        Returns:
            Dict: 财务数据，如果不存在返回None
        """
        session = self.get_session()
        try:
            query = session.query(FactFundamental).filter(
                FactFundamental.ts_code == ts_code
            )
            
            if end_date:
                query = query.filter(FactFundamental.end_date == end_date)
            else:
                # 获取最新一期
                query = query.order_by(FactFundamental.end_date.desc())
            
            result = query.first()
            
            if result:
                return {
                    'ts_code': result.ts_code,
                    'end_date': result.end_date,
                    'report_type': result.report_type,
                    'roe': float(result.roe) if result.roe else None,
                    'net_margin': float(result.net_margin) if result.net_margin else None,
                    'gross_margin': float(result.gross_margin) if result.gross_margin else None,
                    'op_cf': float(result.op_cf) if result.op_cf else None,
                    'total_debt': float(result.total_debt) if result.total_debt else None,
                    'total_asset': float(result.total_asset) if result.total_asset else None,
                    'debt_ratio': float(result.debt_ratio) if result.debt_ratio else None,
                    'profit_volatility': float(result.profit_volatility) if result.profit_volatility else None,
                    'data_quality': result.data_quality,
                    'sources_used': result.sources_used or []
                }
            return None
            
        except Exception as e:
            logger.error(f"查询财务数据失败: {ts_code}: {e}", exc_info=True)
            return None
        finally:
            session.close()
    
    def get_stock_list(self, exchange: Optional[str] = None) -> List[Dict]:
        """
        获取股票列表
        
        Args:
            exchange: 交易所（'SSE', 'SZSE', 'BSE'），如果为None则返回所有
        
        Returns:
            List[Dict]: 股票列表
        """
        session = self.get_session()
        try:
            query = session.query(DimStock)
            
            if exchange:
                query = query.filter(DimStock.exchange == exchange)
            
            results = query.all()
            
            stock_list = []
            for r in results:
                stock_list.append({
                    'ts_code': r.ts_code,
                    'exchange': r.exchange,
                    'symbol': r.symbol,
                    'name': r.name,
                    'list_date': r.list_date.isoformat() if r.list_date else None,
                    'delist_date': r.delist_date.isoformat() if r.delist_date else None,
                    'industry': r.industry,
                    'concept_tags': r.concept_tags or []
                })
            
            logger.debug(f"查询股票列表: exchange={exchange}, 返回 {len(stock_list)} 只")
            return stock_list
            
        except Exception as e:
            logger.error(f"查询股票列表失败: {e}", exc_info=True)
            return []
        finally:
            session.close()

