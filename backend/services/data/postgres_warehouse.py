"""
PostgreSQL数据仓库适配器
提供与文件数据仓库相同的接口，方便逐步迁移
"""

import logging
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional
import pandas as pd

from backend.services.data.query_optimizations import (
    QueryProfiler,
    cached_query,
    log_slow_queries,
    with_retry,
)
from data_warehouse.db import SessionContext, get_pool_status

logger = logging.getLogger(__name__)

# 延迟导入，避免启动时数据库连接问题
def _get_warehouse_service():
    """延迟导入WarehouseService"""
    try:
        from data_warehouse.service.warehouse_service import WarehouseService
        return WarehouseService()
    except Exception as e:
        logger.error(f"❌ 无法初始化WarehouseService: {e}", exc_info=True)
        return None

def _get_raw_layer():
    """延迟导入RawDataLayer"""
    try:
        from data_warehouse.layers.raw_layer import RawDataLayer
        return RawDataLayer()
    except Exception as e:
        logger.error(f"❌ 无法初始化RawDataLayer: {e}", exc_info=True)
        return None


class PostgresWarehouse:
    """
    PostgreSQL数据仓库适配器
    提供与文件数据仓库（DataWarehouse）相同的接口
    """
    
    def __init__(self):
        """初始化PostgreSQL数据仓库适配器"""
        self.warehouse_service = None
        self.raw_layer = None
        self.tushare_client = None
        self.akshare_client = None
        self._initialized = False
        self._init()
    
    def _init(self):
        """延迟初始化（避免启动时数据库连接失败导致整个应用无法启动）"""
        try:
            self.warehouse_service = _get_warehouse_service()
            self.raw_layer = _get_raw_layer()
            
            try:
                from data_warehouse.sources.tushare_client import TushareClient
                self.tushare_client = TushareClient()
            except Exception as e:
                logger.debug(f"TushareClient初始化失败: {e}")
            
            try:
                from data_warehouse.sources.akshare_client import AkShareClient
                self.akshare_client = AkShareClient()
            except Exception as e:
                logger.debug(f"AkShareClient初始化失败: {e}")
            
            if self.warehouse_service:
                logger.debug("✅ PostgresWarehouse已初始化")  # 改为DEBUG级别，减少日志输出
                self._initialized = True
            else:
                logger.warning("⚠️ PostgresWarehouse初始化失败，将无法使用PostgreSQL数据仓库")
        except Exception as e:
            logger.error(f"❌ PostgresWarehouse初始化异常: {e}", exc_info=True)
            self._initialized = False
    
    def get_pool_status(self) -> dict:
        """获取数据库连接池状态"""
        return get_pool_status()

    @cached_query(ttl=60)
    def get_latest_stocks_date(self) -> Optional[str]:
        """
        获取最新股票数据日期（带缓存）

        Returns:
            str: 日期字符串（YYYY-MM-DD），如果没有数据返回None
        """
        if not self._initialized:
            return None

        try:
            from data_warehouse.models import FactDailyPriceQfq
            from sqlalchemy import func

            with SessionContext(autocommit=False) as session:
                result = session.query(func.max(FactDailyPriceQfq.trade_date)).scalar()
                if result:
                    return result.isoformat()
                return None

        except Exception as e:
            logger.error(f"获取最新股票数据日期失败: {e}", exc_info=True)
            return None
    
    def load_stocks_data(self, date_str: str, stock_codes: Optional[List[str]] = None) -> Optional[pd.DataFrame]:
        """
        加载指定日期的股票数据
        
        优先级：
        1. fact_base_universe_daily（基础股票池专用表，最快）
        2. fact_daily_price_qfq（前复权表，数据完整）
        3. fact_daily_price（标准表）
        
        Args:
            date_str: 日期字符串（YYYY-MM-DD）
            stock_codes: 可选的股票代码列表（ts_code格式），如果提供则只加载这些股票的数据
        
        Returns:
            DataFrame: 股票数据，如果不存在返回None
        """
        if not self._initialized or not self.warehouse_service:
            return None
        
        try:
            trade_date = date.fromisoformat(date_str)
            
            session = self.warehouse_service.get_session()
            try:
                # 导入必要的模型和函数
                from sqlalchemy import text, func
                from data_warehouse.models import DimStock, FactDailyPriceQfq
                from data_warehouse.models import FactLimitUpDaily

                # 状态标志：明确初始化，避免在循环体内使用 locals() 判断
                use_base_universe = False
                use_qfq = False
                qfq_slope_ma20_data: dict = {}

                # 方法1: 优先从物化视图读取（基础股票池，最快）
                base_universe_query = text("""
                    SELECT 
                        b.ts_code,
                        b.trade_date,
                        b.open,
                        b.high,
                        b.low,
                        b.close,
                        b.pre_close,
                        b.vol,
                        b.amount,
                        b.turnover_rate,
                        b.change_pct,
                        b.pe_ttm,
                        b.pb,
                        b.ps_ttm,
                        b.pcf_ttm,
                        b.is_suspended,
                        b.is_st,
                        b.ma5,
                        b.ma10,
                        b.ma20,
                        b.ma60,
                        b.avg_volume_5,
                        b.volume_ratio,
                        b.slope_ma20
                    FROM mv_base_universe_daily b
                    WHERE b.trade_date = :trade_date
                """)
                
                params = {'trade_date': trade_date}
                if stock_codes:
                    base_universe_query = text("""
                        SELECT 
                            b.ts_code,
                            b.trade_date,
                            b.open,
                            b.high,
                            b.low,
                            b.close,
                            b.pre_close,
                            b.vol,
                            b.amount,
                            b.turnover_rate,
                            b.change_pct,
                            b.pe_ttm,
                            b.pb,
                            b.ps_ttm,
                            b.pcf_ttm,
                            b.is_suspended,
                            b.is_st,
                            b.ma5,
                            b.ma10,
                            b.ma20,
                            b.ma60,
                            b.avg_volume_5,
                            b.volume_ratio,
                            b.slope_ma20
                        FROM mv_base_universe_daily b
                        WHERE b.trade_date = :trade_date
                          AND b.ts_code = ANY(:stock_codes)
                    """)
                    params['stock_codes'] = stock_codes
                
                base_universe_results = session.execute(base_universe_query, params).fetchall()
                
                if base_universe_results and len(base_universe_results) > 0:
                    logger.info(f"✅ 从物化视图mv_base_universe_daily读取数据: {len(base_universe_results)} 条记录")
                    use_base_universe = True
                    results = base_universe_results
                    
                    # 物化视图已包含slope_ma20，无需额外查询
                    qfq_slope_ma20_data = {}
                    qfq_latest_date = session.query(func.max(FactDailyPriceQfq.trade_date)).scalar()
                    if qfq_latest_date:
                        qfq_slope_query = text("""
                            SELECT ts_code, slope_ma20
                            FROM fact_daily_price_qfq
                            WHERE trade_date = :date
                              AND slope_ma20 IS NOT NULL
                        """)
                        qfq_slope_results = session.execute(qfq_slope_query, {'date': qfq_latest_date}).fetchall()
                        qfq_slope_ma20_data = {r[0]: r[1] for r in qfq_slope_results}
                        logger.debug(f"📊 从qfq表获取slope_ma20补充数据（日期:{qfq_latest_date}），共{len(qfq_slope_ma20_data)}只")
                else:
                    use_base_universe = False
                    results = None
                
                # 方法2: 如果物化视图没有数据，从fact_daily_price_qfq读取
                if not use_base_universe:
                    logger.debug("⚠️ 物化视图mv_base_universe_daily无数据，尝试从fact_daily_price_qfq读取")
                    from data_warehouse.models import FactDailyPriceQfq
                    from data_warehouse.models import FactDailyPrice
                    from sqlalchemy.orm import joinedload
                    
                    # 先尝试从qfq表读取
                    query = session.query(FactDailyPriceQfq).join(
                        DimStock, FactDailyPriceQfq.ts_code == DimStock.ts_code
                    ).filter(
                        FactDailyPriceQfq.trade_date == trade_date
                    )
                    
                    # 如果指定了股票代码列表，只加载这些股票
                    if stock_codes:
                        query = query.filter(FactDailyPriceQfq.ts_code.in_(stock_codes))
                    
                    results = query.all()
                    
                    use_qfq = True
                
                # 获取涨停数据（用于S3过滤）
                # 优先使用当日数据，如果没有则使用最新可用日期
                limit_up_data = {}  # 存储涨停数据（用于S3过滤）
                limit_up_query_date = trade_date
                limit_up_date_check = session.query(func.max(FactLimitUpDaily.trade_date)).scalar()
                if limit_up_date_check and limit_up_date_check < trade_date:
                    # 如果最新涨停数据日期早于请求日期，使用最新可用日期
                    limit_up_query_date = limit_up_date_check
                
                if limit_up_query_date:
                    limit_up_query = text("""
                        SELECT ts_code, continuous_days, change_pct
                        FROM fact_limit_up_daily
                        WHERE trade_date = :date
                    """)
                    limit_up_results = session.execute(limit_up_query, {'date': limit_up_query_date}).fetchall()
                    for row in limit_up_results:
                        ts_code = row[0]
                        continuous_days = row[1] if row[1] is not None else 0
                        change_pct = float(row[2]) if row[2] is not None else 0.0
                        # is_today_limit_up: 如果change_pct >= 9.5或continuous_days > 0，则为True
                        is_today_limit_up = change_pct >= 9.5 or continuous_days > 0
                        limit_up_data[ts_code] = {
                            'is_today_limit_up': is_today_limit_up,
                            'continuous_days': continuous_days,
                            'change_pct': change_pct
                        }
                    if limit_up_results:
                        logger.debug(f"📊 从fact_limit_up_daily获取涨停数据（日期:{limit_up_query_date}），共{len(limit_up_data)}只")
                
                if not results:
                    logger.debug(f"⚠️ {date_str} 的股票数据不存在")
                    return None
                
                # 如果数据量很少（比如只有3只），说明是样本数据
                if len(results) < 10:
                    logger.info(f"📦 数据仓库中有 {len(results)} 只股票的数据（可能是样本数据）")
                
                # 转换为DataFrame
                data_list = []
                for r in results:
                    # 获取股票基本信息
                    ts_code = r[0] if isinstance(r, tuple) else r.ts_code
                    stock = session.query(DimStock).filter(
                        DimStock.ts_code == ts_code
                    ).first()
                    
                    # 统一从dim_stock表的名称判断是否ST股票
                    is_st = stock and stock.name and ('ST' in stock.name.upper())
                    
                    # 根据使用的表类型，提取字段
                    if use_base_universe:
                        # fact_base_universe_daily表字段（与qfq表结构相同）
                        # r是tuple: (ts_code, trade_date, open, high, low, close, pre_close, vol, amount, turnover_rate, change_pct, pe_ttm, pb, ps_ttm, pcf_ttm, is_suspended, is_st, ma5, ma10, ma20, ma60, avg_volume_5, volume_ratio)
                        change_pct = float(r[10]) if r[10] else 0.0
                        # is_st 已在上面从dim_stock判断
                        avg_volume_5 = float(r[22]) if r[22] else 0.0
                        turnover_rate = float(r[9]) if r[9] else 0.0
                        ma20 = float(r[20]) if r[20] is not None else None
                        close = float(r[5]) if r[5] else 0.0
                        pre_close = float(r[6]) if r[6] else 0.0
                        open = float(r[2]) if r[2] else 0.0
                        high = float(r[3]) if r[3] else 0.0
                        low = float(r[4]) if r[4] else 0.0
                        vol = float(r[7]) if r[7] else 0.0
                        amount = float(r[8]) if r[8] else 0.0
                        pe_ttm = float(r[11]) if r[11] else None
                        pb = float(r[12]) if r[12] else None
                        # fact_base_universe_daily表没有slope_ma20，需要从fact_daily_price_qfq读取
                        slope_ma20 = qfq_slope_ma20_data.get(ts_code)
                    elif use_qfq:
                        # qfq表字段
                        change_pct = float(r.change_pct) if hasattr(r, 'change_pct') and r.change_pct else 0.0
                        # is_st 已在上面从dim_stock判断
                        avg_volume_5 = 0.0  # qfq表没有此字段
                        turnover_rate = float(r.turnover_rate) if r.turnover_rate else 0.0
                        # 尝试从qfq表获取MA20（如果模型有该字段）
                        ma20 = None
                        if hasattr(r, 'ma20') and r.ma20 is not None:
                            ma20 = float(r.ma20)
                        
                        # 尝试从qfq表获取slope_ma20（如果模型有该字段）
                        slope_ma20 = None
                        if hasattr(r, 'slope_ma20') and r.slope_ma20 is not None:
                            slope_ma20 = float(r.slope_ma20)
                        elif r.ts_code in qfq_slope_ma20_data:
                            slope_ma20 = qfq_slope_ma20_data[r.ts_code]
                        # 获取PE和PB
                        pe_ttm = float(r.pe_ttm) if hasattr(r, 'pe_ttm') and r.pe_ttm else None
                        pb = float(r.pb) if hasattr(r, 'pb') and r.pb else None
                        # 获取价格和成交量字段
                        close = float(r.close) if r.close else 0.0
                        pre_close = float(r.pre_close) if r.pre_close else 0.0
                        open = float(r.open) if r.open else 0.0
                        high = float(r.high) if r.high else 0.0
                        low = float(r.low) if r.low else 0.0
                        vol = float(r.vol) if r.vol else 0.0
                        amount = float(r.amount) if r.amount else 0.0
                    
                    # 获取涨停数据
                    limit_up_info = limit_up_data.get(ts_code, {})
                    is_today_limit_up = limit_up_info.get('is_today_limit_up', False)
                    continuous_days = limit_up_info.get('continuous_days', 0)
                    
                    # 统一处理ts_code
                    if use_base_universe:
                        ts_code_str = ts_code
                    else:
                        ts_code_str = r.ts_code if hasattr(r, 'ts_code') else ts_code
                    
                    data_list.append({
                        '代码': ts_code_str.replace('.SH', '').replace('.SZ', '').replace('.BJ', ''),
                        '股票名称': stock.name if stock else ts_code_str,
                        '当前价': close,
                        '涨跌幅': ((close - pre_close) / pre_close * 100) if pre_close and pre_close > 0 else 0.0,
                        '涨跌额': (close - pre_close) if pre_close else 0.0,
                        '成交量': vol,
                        '成交额': amount,
                        '换手率': turnover_rate,
                        '开盘': open,
                        '最高': high,
                        '最低': low,
                        '昨收': pre_close,
                        # 添加兼容字段
                        'code': ts_code_str.replace('.SH', '').replace('.SZ', '').replace('.BJ', ''),
                        'name': stock.name if stock else ts_code_str,
                        'lastPrice': close,
                        'pct_chg': change_pct,
                        'amount': amount,
                        'turnover_rate': turnover_rate,
                        'avgVolume5': avg_volume_5,
                        'volume': vol,
                        # 添加通用字段
                        'change_pct': change_pct,
                        'is_st': is_st,
                        'close': close,  # 添加close字段（用于过滤）
                        'ma20': float(ma20) if ma20 is not None else None,  # 添加MA20字段（用于S2过滤）
                        'slope_ma20': float(slope_ma20) if slope_ma20 is not None else None,  # 添加MA20斜率字段（用于S2过滤）
                        'is_today_limit_up': is_today_limit_up,  # 添加涨停字段（用于S3过滤）
                        'continuous_days': continuous_days,  # 添加连板天数（用于S3过滤）
                        'pe_ttm': pe_ttm,  # 添加PE字段（用于达尔文评分2.0）
                        'pb': pb,  # 添加PB字段（用于达尔文评分2.0）
                    })
                
                df = pd.DataFrame(data_list)
                logger.info(f"✅ 从PostgreSQL加载股票数据: {date_str} ({len(df)} 只股票)")
                return df
                
            finally:
                session.close()
                
        except Exception as e:
            logger.error(f"❌ 加载股票数据失败: {e}", exc_info=True)
            return None
    
    def load_stocks_data_as_models(self, date_str: str) -> Optional[List['StockData']]:
        """
        加载指定日期的股票数据（返回StockData模型列表）
        
        Args:
            date_str: 日期字符串（YYYY-MM-DD）
        
        Returns:
            List[StockData]: 股票数据模型列表，如果不存在返回None
        """
        from backend.models.stock_data import StockData
        
        # 先获取DataFrame
        df = self.load_stocks_data(date_str)
        
        if df is None or df.empty:
            return None
        
        # 转换为StockData模型列表
        return StockData.from_dataframe(df)
    
    def get_stock_financial_data(self, stock_code: str) -> Optional[Dict]:
        """
        获取单只股票的财务数据（最新一期）
        
        Args:
            stock_code: 股票代码（6位数字或带前缀）
        
        Returns:
            dict: 财务数据，如果不存在返回None
        """
        if not self._initialized or not self.warehouse_service:
            return None
        
        try:
            # 标准化股票代码
            if '.' not in stock_code:
                if stock_code.startswith('6'):
                    ts_code = f"{stock_code}.SH"
                elif stock_code.startswith('0') or stock_code.startswith('3'):
                    ts_code = f"{stock_code}.SZ"
                else:
                    ts_code = stock_code
            else:
                ts_code = stock_code
            
            # 从fact_fundamental获取最新财务数据
            fundamental = self.warehouse_service.get_fundamental(ts_code)
            
            if fundamental:
                # 返回兼容文件数据仓库的格式
                return {
                    'roe_ttm': float(fundamental.get('roe', 0) or 0) * 100,  # 转换为百分比
                    'net_margin': float(fundamental.get('net_margin', 0) or 0),
                    'gross_margin': float(fundamental.get('gross_margin', 0) or 0),
                    'operating_cashflow': float(fundamental.get('op_cf', 0) or 0),
                    'total_debt': float(fundamental.get('total_debt', 0) or 0),
                    'total_asset': float(fundamental.get('total_asset', 0) or 0),
                    'debt_ratio': float(fundamental.get('debt_ratio', 0) or 0),
                    'profit_volatility': float(fundamental.get('profit_volatility', 0) or 0) if fundamental.get('profit_volatility') else None
                }
            
            return None
            
        except Exception as e:
            logger.error(f"❌ 获取财务数据失败 {stock_code}: {e}", exc_info=True)
            return None
    
    def load_financial_data(self, date_str: str) -> Optional[Dict[str, Dict]]:
        """
        加载指定日期的财务数据
        
        Args:
            date_str: 日期字符串（YYYY-MM-DD）
        
        Returns:
            dict: 财务数据字典，格式：{stock_code: {财务指标...}}
        """
        if not self._initialized or not self.warehouse_service:
            return None
        
        try:
            # 从fact_fundamental获取指定日期附近的财务数据
            # 注意：财务数据是按报告期的，不是按交易日的
            # 这里返回最近一期的财务数据
            
            session = self.warehouse_service.get_session()
            try:
                from data_warehouse.models import FactFundamental
                from data_warehouse.models import DimStock
                from sqlalchemy import func
                
                # 获取所有股票的最新财务数据
                # 使用子查询获取每个股票的最新报告期
                subquery = session.query(
                    FactFundamental.ts_code,
                    func.max(FactFundamental.end_date).label('max_date')
                ).group_by(FactFundamental.ts_code).subquery()
                
                results = session.query(FactFundamental).join(
                    subquery,
                    (FactFundamental.ts_code == subquery.c.ts_code) &
                    (FactFundamental.end_date == subquery.c.max_date)
                ).all()
                
                financial_dict = {}
                for r in results:
                    # 获取股票名称
                    stock = session.query(DimStock).filter(
                        DimStock.ts_code == r.ts_code
                    ).first()
                    stock_name = stock.name if stock else ''
                    
                    # 转换为6位数字代码
                    code = r.ts_code.replace('.SH', '').replace('.SZ', '').replace('.BJ', '')
                    # 数据库中存储的格式（从refresh_financial_data.py保存时）：
                    # roe: 百分比（如39.82表示39.82%），存储时已经乘以100或保持百分比格式
                    # net_margin, gross_margin: 小数格式（如0.1492表示14.92%），但存储时可能已经转换为百分比
                    # debt_ratio: 百分比（如97.57表示97.57%），存储时已经乘以100
                    # 需要统一转换为前端期望的格式：ROE和负债率为百分比，净利率和毛利率为小数
                    roe_val = float(r.roe) if r.roe else 0.0
                    net_margin_val = float(r.net_margin) if r.net_margin else 0.0
                    gross_margin_val = float(r.gross_margin) if r.gross_margin else 0.0
                    debt_ratio_val = float(r.debt_ratio) if r.debt_ratio else 0.0
                    
                    # 转换格式：
                    # ROE: 如果>1，说明是百分比格式，直接使用；如果<=1，说明是小数格式，乘以100
                    # 净利率、毛利率: 如果>1，说明是百分比格式，除以100；如果<=1，说明是小数格式，直接使用
                    # 负债率: 如果>1，说明是百分比格式，除以100转换为小数（前端会乘以100显示）；如果<=1，说明是小数格式，直接使用
                    financial_dict[code] = {
                        'stock_name': stock_name,  # 添加股票名称
                        'roe_ttm': roe_val if roe_val > 1 else roe_val * 100,  # ROE转换为百分比
                        'net_margin': net_margin_val / 100 if net_margin_val > 1 else net_margin_val,  # 净利率转换为小数格式
                        'gross_margin': gross_margin_val / 100 if gross_margin_val > 1 else gross_margin_val,  # 毛利率转换为小数格式
                        'operating_cashflow': float(r.op_cf) if r.op_cf else 0.0,
                        'total_debt': float(r.total_debt) if r.total_debt else 0.0,
                        'total_asset': float(r.total_asset) if r.total_asset else 0.0,
                        'debt_ratio': debt_ratio_val / 100 if debt_ratio_val > 1 else debt_ratio_val,  # 负债率转换为小数格式（前端会乘以100显示）
                        'profit_volatility': float(r.profit_volatility) if r.profit_volatility else None
                    }
                
                logger.info(f"✅ 从PostgreSQL加载财务数据: {len(financial_dict)} 只股票")
                return financial_dict
                
            finally:
                session.close()
                
        except Exception as e:
            logger.error(f"❌ 加载财务数据失败: {e}", exc_info=True)
            return None
    
    def get_date_range(self) -> tuple:
        """
        获取数据仓库中的日期范围
        
        Returns:
            tuple: (最早日期, 最新日期)，格式：(date, date)
        """
        if not self._initialized or not self.warehouse_service:
            return (None, None)
        
        try:
            session = self.warehouse_service.get_session()
            try:
                from data_warehouse.models import FactDailyPrice
                from sqlalchemy import func
                
                min_date = session.query(func.min(FactDailyPrice.trade_date)).scalar()
                max_date = session.query(func.max(FactDailyPrice.trade_date)).scalar()
                
                return (min_date, max_date) if min_date and max_date else (None, None)
            finally:
                session.close()
        except Exception as e:
            logger.error(f"获取日期范围失败: {e}", exc_info=True)
            return (None, None)
    
    def load_history_kline_batch(
        self,
        codes: List[str],
        start_date: str,
        end_date: str
    ) -> Optional[pd.DataFrame]:
        """
        批量获取历史K线数据（一条SQL查询，高效）
        
        Args:
            codes: 股票代码列表（6位数字格式，如 ['000001', '600000']）
            start_date: 开始日期 YYYY-MM-DD
            end_date: 结束日期 YYYY-MM-DD
            
        Returns:
            DataFrame: 包含 code, trade_date, open, high, low, close, volume, amount, pct_chg
        """
        if not self._initialized or not self.warehouse_service:
            return None
        
        try:
            session = self.warehouse_service.get_session()
            try:
                from sqlalchemy import text
                
                # 将6位代码转换为ts_code格式用于查询
                ts_codes = []
                for code in codes:
                    code = str(code).replace('sh', '').replace('sz', '').replace('.SH', '').replace('.SZ', '')
                    if code.startswith('6'):
                        ts_codes.append(f"{code}.SH")
                    elif code.startswith('0') or code.startswith('3'):
                        ts_codes.append(f"{code}.SZ")
                    elif code.startswith('8') or code.startswith('4'):
                        ts_codes.append(f"{code}.BJ")
                    else:
                        ts_codes.append(code)
                
                if not ts_codes:
                    return None
                
                # 一条SQL批量查询所有数据
                query = text("""
                    SELECT 
                        ts_code,
                        trade_date,
                        open,
                        high,
                        low,
                        close,
                        vol as volume,
                        amount,
                        COALESCE(change_pct, 0) as pct_chg
                    FROM fact_daily_price_qfq
                    WHERE ts_code = ANY(:codes)
                      AND trade_date >= :start_date
                      AND trade_date <= :end_date
                    ORDER BY ts_code, trade_date
                """)
                
                result = session.execute(query, {
                    'codes': ts_codes,
                    'start_date': start_date,
                    'end_date': end_date
                })
                
                rows = result.fetchall()
                if not rows:
                    logger.debug(f"PostgreSQL K线批量查询无数据: {len(codes)} 只股票, {start_date} ~ {end_date}")
                    return None
                
                # 转换为DataFrame
                df = pd.DataFrame(rows, columns=['ts_code', 'trade_date', 'open', 'high', 'low', 'close', 'volume', 'amount', 'pct_chg'])
                
                # 标准化代码格式（去除后缀）
                df['code'] = df['ts_code'].str.replace('.SH', '').str.replace('.SZ', '').str.replace('.BJ', '')
                df['trade_date'] = df['trade_date'].astype(str)
                
                logger.info(f"✅ PostgreSQL批量获取K线: {len(df)} 条, {len(df['code'].unique())} 只股票")
                return df
                
            finally:
                session.close()
                
        except Exception as e:
            logger.error(f"❌ PostgreSQL批量K线查询失败: {e}")
            return None

