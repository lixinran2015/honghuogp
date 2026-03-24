"""
9:40未破分时监控服务
监控距离30日新高5%内的股票，在指定时间点筛选未破分时均线且涨幅>=3%的股票
"""

import logging
import threading
import time
from datetime import datetime, date, timedelta
from typing import List, Dict, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd

from backend.services.stock.stock_universe_service import StockUniverseService
from backend.services.data.intraday_service import fetch_intraday_from_ifind, fetch_intraday_from_tencent, fetch_intraday_from_eastmoney
from backend.services.data_sources.realtime_source import SinaRealtimeSource
from backend.services.data.postgres_warehouse import PostgresWarehouse
from data_warehouse.models import FactMonitorNear5940
from data_warehouse.models import DimStock
from data_warehouse.models import FactDailyPriceQfq
from data_warehouse.models import DimTradeCalendar

logger = logging.getLogger(__name__)

# 监控时间点列表
MONITOR_TIME_POINTS = [
    "09:40:00", "09:50:00", "10:00:00", "10:10:00", "10:20:00",
    "10:30:00", "10:40:00", "10:50:00", "11:00:00"
]

# monitor_near5 服务配置
class MonitorNear5Config:
    """monitor_near5 服务配置"""
    # 是否自动将监控结果添加到watchlist（默认False，避免watchlist股票数量激增）
    ENABLE_AUTO_ADD_TO_WATCHLIST = False
    # 自动添加到watchlist的最大数量（如果启用自动添加）
    MAX_WATCHLIST_ADD_COUNT = 10
    # 添加阈值：只添加涨幅>=此值的股票（如果启用自动添加）
    MIN_CHANGE_PCT_FOR_WATCHLIST = 5.0
    # S1股票池最大数量阈值（超过此值将停止监控并告警）
    MAX_S1_STOCKS = 200
    # 合并后监控股票总数最大阈值（超过此值将停止监控并告警）
    MAX_TOTAL_STOCKS = 300


class MonitorNear5Service:
    """9:40未破分时监控服务"""
    
    # 类变量：任务状态
    _task_running = False
    _task_progress = 0
    _task_total = len(MONITOR_TIME_POINTS)
    _task_message = ""
    _task_results = []
    _task_error = None
    _lock = threading.Lock()
    
    def __init__(self):
        self.universe_service = StockUniverseService()
        self.warehouse = PostgresWarehouse()
        self.realtime_source = None
        self._broken_ma_stocks_lock = threading.Lock()  # 保护_broken_ma_stocks的线程锁
        try:
            self.realtime_source = SinaRealtimeSource()
        except Exception as e:
            logger.warning(f"实时数据源初始化失败: {e}")
    
    @classmethod
    def get_status(cls) -> Dict:
        """获取任务状态"""
        with cls._lock:
            return {
                "running": cls._task_running,
                "progress": cls._task_progress,
                "total": cls._task_total,
                "message": cls._task_message,
                "results": cls._task_results.copy(),
                "error": cls._task_error
            }
    
    @classmethod
    def _update_status(cls, running: bool = None, progress: int = None, 
                       message: str = None, results: List = None, error: str = None):
        """更新任务状态"""
        with cls._lock:
            if running is not None:
                cls._task_running = running
            if progress is not None:
                cls._task_progress = progress
            if message is not None:
                cls._task_message = message
            if results is not None:
                cls._task_results = results
            if error is not None:
                cls._task_error = error
    
    def get_s1_stocks(self, trade_date: str = None) -> List[str]:
        """获取监控股票列表（S1新高策略 + 30日新高）"""
        try:
            monitor_codes = set()  # 使用set自动去重
            
            # 1. 获取S1股票池
            s1_codes = self.universe_service.get_universe_stocks("s1", trade_date)
            
            # ✅ 数据验证：S1股票池数量异常告警
            if len(s1_codes) > MonitorNear5Config.MAX_S1_STOCKS:
                logger.error("=" * 80)
                logger.error("🚨 【严重告警】S1股票池数量异常！")
                logger.error(f"   当前数量: {len(s1_codes)} 只")
                logger.error(f"   预期范围: 100-300 只")
                logger.error(f"   阈值限制: {MonitorNear5Config.MAX_S1_STOCKS} 只")
                logger.error(f"   交易日期: {trade_date}")
                logger.error("   可能原因:")
                logger.error("     1. S1股票池更新时筛选条件未正确应用")
                logger.error("     2. 实时数据获取失败，降级返回了基础池所有股票")
                logger.error("     3. 数据库中的数据异常")
                logger.error("   处理措施: 停止监控，请检查S1股票池数据")
                logger.error("=" * 80)
                # 返回空列表，阻止后续监控
                return []
            
            monitor_codes.update(s1_codes)
            logger.info(f"获取到 {len(s1_codes)} 只S1股票")
            
            # 2. 获取30日新高筛选结果
            try:
                from backend.services.data.data_management_service import DataManagementService
                data_mgmt_service = DataManagementService()
                metrics = data_mgmt_service.get_data_quality_metrics()
                new_high_stocks = metrics.get('data_dimensions', {}).get('new_high_strategy', {}).get('valid_stocks', [])
                
                if new_high_stocks:
                    new_added = len(set(new_high_stocks) - monitor_codes)
                    monitor_codes.update(new_high_stocks)
                    logger.info(f"获取到 {len(new_high_stocks)} 只30日新高股票（新增 {new_added} 只）")
                else:
                    logger.warning("30日新高筛选结果为空")
            except Exception as e:
                logger.warning(f"获取30日新高筛选失败: {e}，仅使用S1股票池")
            
            codes = list(monitor_codes)
            
            # ✅ 数据验证：合并后总数也进行验证（双重保险）
            if len(codes) > MonitorNear5Config.MAX_TOTAL_STOCKS:
                logger.error("=" * 80)
                logger.error("🚨 【严重告警】监控股票总数异常！")
                logger.error(f"   当前总数: {len(codes)} 只")
                logger.error(f"   阈值限制: {MonitorNear5Config.MAX_TOTAL_STOCKS} 只")
                logger.error(f"   交易日期: {trade_date}")
                logger.error(f"   S1股票: {len(s1_codes)} 只")
                logger.error(f"   30日新高股票: {len(codes) - len(s1_codes)} 只")
                logger.error("   处理措施: 停止监控，请检查股票池数据")
                logger.error("=" * 80)
                # 返回空列表，阻止后续监控
                return []
            
            logger.info(f"✅ 合并后监控股票总数: {len(codes)} 只（S1 + 30日新高）")
            return codes
        except Exception as e:
            logger.error(f"获取监控股票失败: {e}")
            return []
    
    def is_trading_day(self, check_date: str) -> bool:
        """
        检查指定日期是否为交易日
        
        Args:
            check_date: 日期字符串（如 2025-11-28）
        
        Returns:
            bool: 是否为交易日
        """
        try:
            check_date_obj = datetime.strptime(check_date, "%Y-%m-%d").date()
            
            if not self.warehouse.warehouse_service:
                # 如果数据库服务未初始化，使用简单判断（跳过周末）
                weekday = check_date_obj.weekday()
                return weekday < 5  # 周一到周五
            
            session = self.warehouse.warehouse_service.get_session()
            try:
                calendar = session.query(DimTradeCalendar).filter(
                    DimTradeCalendar.trade_date == check_date_obj
                ).first()
                
                if calendar:
                    return bool(calendar.is_open)
                else:
                    # 如果交易日历中没有该日期，使用简单判断（跳过周末）
                    weekday = check_date_obj.weekday()
                    return weekday < 5
            finally:
                session.close()
                
        except Exception as e:
            logger.debug(f"检查交易日失败: {e}")
            # 降级：使用简单判断（跳过周末）
            check_date_obj = datetime.strptime(check_date, "%Y-%m-%d").date()
            weekday = check_date_obj.weekday()
            return weekday < 5
    
    def get_latest_trading_day(self, max_days_back: int = 10) -> Optional[str]:
        """
        获取最近的交易日
        
        Args:
            max_days_back: 最多往前查找多少天
        
        Returns:
            str: 最近的交易日（YYYY-MM-DD格式），如果找不到返回None
        """
        try:
            today = datetime.now().date()
            
            if not self.warehouse.warehouse_service:
                # 如果数据库服务未初始化，使用简单判断
                for i in range(max_days_back):
                    check_date = today - timedelta(days=i)
                    if check_date.weekday() < 5:  # 周一到周五
                        return check_date.strftime("%Y-%m-%d")
                return None
            
            session = self.warehouse.warehouse_service.get_session()
            try:
                # 查询今天或之前最近的交易日
                result = session.query(DimTradeCalendar.trade_date).filter(
                    DimTradeCalendar.trade_date <= today,
                    DimTradeCalendar.is_open == True
                ).order_by(DimTradeCalendar.trade_date.desc()).first()
                
                if result:
                    return result[0].strftime("%Y-%m-%d")
                
                # 如果交易日历中没有数据，使用简单判断
                for i in range(max_days_back):
                    check_date = today - timedelta(days=i)
                    if check_date.weekday() < 5:  # 周一到周五
                        return check_date.strftime("%Y-%m-%d")
                return None
            finally:
                session.close()
                
        except Exception as e:
            logger.debug(f"获取最近交易日失败: {e}")
            # 降级：使用简单判断
            today = datetime.now().date()
            for i in range(max_days_back):
                check_date = today - timedelta(days=i)
                if check_date.weekday() < 5:  # 周一到周五
                    return check_date.strftime("%Y-%m-%d")
            return None
    
    def get_previous_close(self, ts_code: str, trade_date: str) -> Optional[float]:
        """
        获取前日收盘价（前一个交易日的收盘价）
        
        逻辑：
        - 如果 trade_date 是今天，获取昨天（前一个交易日）的收盘价
        - 如果 trade_date 是历史日期，获取该日期前一个交易日的收盘价
        
        Args:
            ts_code: 股票代码（如 300001.SZ）
            trade_date: 交易日期（如 2025-11-28）
        
        Returns:
            float: 前日收盘价，如果获取失败返回None
        """
        try:
            trade_date_obj = datetime.strptime(trade_date, "%Y-%m-%d").date()
            today = datetime.now().date()
            
            if not self.warehouse.warehouse_service:
                logger.warning(f"  {ts_code}: 数据库服务未初始化")
                return None
            
            session = self.warehouse.warehouse_service.get_session()
            try:
                # 优先方法：直接查询前一个交易日的收盘价（最准确）
                # 这是最直接的方法，无论是指定日期还是今天，都获取前一个交易日的收盘价
                prev_data = session.query(FactDailyPriceQfq).filter(
                    FactDailyPriceQfq.ts_code == ts_code,
                    FactDailyPriceQfq.trade_date < trade_date_obj
                ).order_by(FactDailyPriceQfq.trade_date.desc()).first()
                
                if prev_data and prev_data.close:
                    logger.info(f"  {ts_code}: 从前一交易日 {prev_data.trade_date} 获取收盘价: {float(prev_data.close):.2f}（用于计算 {trade_date} 的涨幅）")
                    return float(prev_data.close)
                
                # 降级方法1：如果指定日期有数据，尝试使用 pre_close 字段
                # 注意：pre_close 字段通常就是前一个交易日的收盘价
                today_data = session.query(FactDailyPriceQfq).filter(
                    FactDailyPriceQfq.ts_code == ts_code,
                    FactDailyPriceQfq.trade_date == trade_date_obj
                ).first()
                
                if today_data and today_data.pre_close:
                    logger.info(f"  {ts_code}: 从当日数据的pre_close字段获取前日收盘价: {float(today_data.pre_close):.2f}")
                    return float(today_data.pre_close)
                
                # 降级方法2：如果指定日期没有数据，尝试获取该股票的最新日期数据
                if not today_data:
                    latest_data = session.query(FactDailyPriceQfq).filter(
                        FactDailyPriceQfq.ts_code == ts_code,
                        FactDailyPriceQfq.trade_date <= trade_date_obj
                    ).order_by(FactDailyPriceQfq.trade_date.desc()).first()
                    
                    if latest_data:
                        # 如果最新数据早于指定日期，使用其收盘价作为前日收盘价
                        if latest_data.trade_date < trade_date_obj and latest_data.close:
                            logger.info(f"  {ts_code}: 使用最新数据日期 {latest_data.trade_date} 的收盘价作为前日收盘价: {float(latest_data.close):.2f}")
                            return float(latest_data.close)
                
                logger.info(f"  {ts_code}: 无法获取前日收盘价（数据库中无该股票数据，可能是新股或停牌）")
                return None
            finally:
                session.close()
                
        except Exception as e:
            logger.warning(f"获取 {ts_code} 前日收盘价失败: {e}", exc_info=True)
            return None
    
    def get_5d_10d_change_pct(self, ts_code: str, trade_date: str, current_price: Optional[float] = None) -> Tuple[Optional[float], Optional[float]]:
        """
        计算5日涨幅和10日涨幅
        
        Args:
            ts_code: 股票代码（如 300001.SZ）
            trade_date: 交易日期（如 2025-11-28）
            current_price: 当前价格（可选，如果提供则使用此价格，否则使用当日收盘价）
        
        Returns:
            Tuple[Optional[float], Optional[float]]: (5日涨幅, 10日涨幅)，如果获取失败返回(None, None)
        """
        try:
            trade_date_obj = datetime.strptime(trade_date, "%Y-%m-%d").date()
            
            if not self.warehouse.warehouse_service:
                logger.debug(f"  {ts_code}: 数据库服务未初始化，无法计算5日/10日涨幅")
                return None, None
            
            session = self.warehouse.warehouse_service.get_session()
            try:
                # 如果提供了当前价格，使用它；否则获取当日收盘价
                if current_price is not None and current_price > 0:
                    current_close = current_price
                else:
                    # 获取当日收盘价（使用当日数据的收盘价，如果没有则使用前一日收盘价）
                    today_data = session.query(FactDailyPriceQfq).filter(
                        FactDailyPriceQfq.ts_code == ts_code,
                        FactDailyPriceQfq.trade_date == trade_date_obj
                    ).first()
                    
                    if not today_data or not today_data.close:
                        # 如果没有当日数据，使用前一日收盘价
                        prev_data = session.query(FactDailyPriceQfq).filter(
                            FactDailyPriceQfq.ts_code == ts_code,
                            FactDailyPriceQfq.trade_date < trade_date_obj
                        ).order_by(FactDailyPriceQfq.trade_date.desc()).first()
                        
                        if not prev_data or not prev_data.close:
                            logger.debug(f"  {ts_code}: 无法获取当日或前日收盘价")
                            return None, None
                        
                        current_close = float(prev_data.close)
                    else:
                        current_close = float(today_data.close)
                
                # 计算5日涨幅：获取5个交易日前的收盘价
                prices_5d = session.query(FactDailyPriceQfq).filter(
                    FactDailyPriceQfq.ts_code == ts_code,
                    FactDailyPriceQfq.trade_date < trade_date_obj
                ).order_by(FactDailyPriceQfq.trade_date.desc()).limit(5).all()
                
                pct_5d = None
                if len(prices_5d) >= 5:
                    # 取第5个交易日前的收盘价（即第5条记录）
                    start_5d = float(prices_5d[4].close) if prices_5d[4].close else None
                    if start_5d and start_5d > 0:
                        pct_5d = (current_close / start_5d - 1) * 100
                
                # 计算10日涨幅：获取10个交易日前的收盘价
                prices_10d = session.query(FactDailyPriceQfq).filter(
                    FactDailyPriceQfq.ts_code == ts_code,
                    FactDailyPriceQfq.trade_date < trade_date_obj
                ).order_by(FactDailyPriceQfq.trade_date.desc()).limit(10).all()
                
                pct_10d = None
                if len(prices_10d) >= 10:
                    # 取第10个交易日前的收盘价（即第10条记录）
                    start_10d = float(prices_10d[9].close) if prices_10d[9].close else None
                    if start_10d and start_10d > 0:
                        pct_10d = (current_close / start_10d - 1) * 100
                
                logger.debug(f"  {ts_code}: 5日涨幅={pct_5d:.2f}%, 10日涨幅={pct_10d:.2f}%" if pct_5d and pct_10d else f"  {ts_code}: 5日涨幅={pct_5d}, 10日涨幅={pct_10d}")
                return pct_5d, pct_10d
                
            finally:
                session.close()
                
        except Exception as e:
            logger.warning(f"计算 {ts_code} 5日/10日涨幅失败: {e}", exc_info=True)
            return None, None
    
    def get_30day_high(self, ts_code: str, trade_date: str) -> Optional[float]:
        """
        获取30日最高价（前复权）
        
        计算逻辑：
        - 查询 trade_date 之前（不含当日）的30个交易日的最高价
        - 返回这30个交易日中的最高价
        
        Args:
            ts_code: 股票代码（如 300001.SZ）
            trade_date: 交易日期（如 2025-11-28）
        
        Returns:
            float: 30日最高价，如果获取失败返回None
        """
        try:
            trade_date_obj = datetime.strptime(trade_date, "%Y-%m-%d").date()
            
            if not self.warehouse.warehouse_service:
                logger.debug(f"  {ts_code}: 数据库服务未初始化，无法获取30日最高价")
                return None
            
            session = self.warehouse.warehouse_service.get_session()
            try:
                # 查询 trade_date 之前（不含当日）的30个交易日的最高价
                # 使用 high 字段（最高价）
                historical_data = session.query(FactDailyPriceQfq.high).filter(
                    FactDailyPriceQfq.ts_code == ts_code,
                    FactDailyPriceQfq.trade_date < trade_date_obj
                ).order_by(FactDailyPriceQfq.trade_date.desc()).limit(30).all()
                
                if not historical_data:
                    logger.debug(f"  {ts_code}: 无法获取30日历史数据")
                    return None
                
                # 提取最高价并计算30日最高价
                highs = [float(row[0]) for row in historical_data if row[0] is not None]
                if not highs:
                    logger.debug(f"  {ts_code}: 30日历史数据中无有效最高价")
                    return None
                
                max_high = max(highs)
                logger.debug(f"  {ts_code}: 30日最高价={max_high:.2f}（基于{len(highs)}个交易日）")
                return max_high
                
            finally:
                session.close()
                
        except Exception as e:
            logger.warning(f"获取 {ts_code} 30日最高价失败: {e}", exc_info=True)
            return None
    
    def get_intraday_data(self, ts_code: str, trade_date: str) -> Optional[pd.DataFrame]:
        """
        获取股票分时数据
        
        Args:
            ts_code: 股票代码（如 300001.SZ）
            trade_date: 交易日期（如 2025-11-27）
        
        Returns:
            DataFrame: 分时数据 [trade_time, open, high, low, close, volume, amount]
        """
        try:
            # 先检查指定日期是否为交易日
            is_trading = self.is_trading_day(trade_date)
            if not is_trading:
                latest_trading_day = self.get_latest_trading_day()
                logger.info(f"  {ts_code}: 日期 {trade_date} 不是交易日，最近交易日: {latest_trading_day}")
                if latest_trading_day:
                    logger.info(f"  {ts_code}: 建议使用最近交易日 {latest_trading_day} 进行测试")
                return None
            
            # 优先使用 iFinDPy（最准确）
            # 注意：iFinDPy 需要传入 cutoff_time，但这里先获取全天数据，后续在 check_never_break_ma 中会过滤
            df = fetch_intraday_from_ifind(ts_code, trade_date, cutoff_time=None)
            source = "ifind"
            
            if df is None or df.empty:
                # 降级到东财接口（获取更多天数，以便查看可用日期）
                df = fetch_intraday_from_eastmoney(ts_code, ndays=5)
                source = "eastmoney"
                
                if df is None or df.empty:
                    # 最后兜底使用腾讯
                    df = fetch_intraday_from_tencent(ts_code, ndays=5)
                    source = "tencent"
            
            if df is None or df.empty:
                logger.info(f"  {ts_code}: 东财和腾讯接口都返回空数据（可能是停牌或数据源问题）")
                return None
            
            # 过滤指定日期的数据
            target_date = datetime.strptime(trade_date, "%Y-%m-%d").date()
            available_dates = sorted(df['trade_date'].unique().tolist()) if 'trade_date' in df.columns else []
            available_dates_str = [str(d) for d in available_dates]
            
            df = df[df['trade_date'] == target_date].copy()
            
            if df.empty:
                logger.info(f"  {ts_code}: 日期 {trade_date} 无分时数据，可用日期: {available_dates_str}（数据源: {source}）")
                if available_dates_str:
                    latest_available = available_dates_str[-1]
                    logger.info(f"  {ts_code}: 建议使用可用日期 {latest_available} 进行测试")
                return None
            
            # 按时间排序
            df = df.sort_values('trade_time').reset_index(drop=True)
            logger.info(f"  {ts_code}: 获取到 {len(df)} 条分时数据（数据源: {source}）")
            return df
            
        except Exception as e:
            logger.warning(f"获取 {ts_code} 分时数据失败: {e}", exc_info=True)
            return None
    
    def check_never_break_ma(self, df: pd.DataFrame, cutoff_time: str, 
                              min_change_pct: float = 3.0, tolerance_pct: float = 0.1,
                              ts_code: str = None, debug: bool = False, 
                              pre_close: Optional[float] = None) -> Tuple[bool, float, str]:
        """
        检查分时是否未破均线
        
        Args:
            df: 分时数据DataFrame
            cutoff_time: 截止时间（如 09:40:00）
            min_change_pct: 最小涨幅阈值（%）
            tolerance_pct: 容忍度百分比（默认0.1%）
            ts_code: 股票代码（用于日志）
            debug: 是否输出详细日志
            pre_close: 前日收盘价
        
        Returns:
            Tuple[bool, float, str]: (是否满足条件, 当前涨幅, 不符合原因)
        """
        if df is None or len(df) < 2:
            reason = "分时数据不足（<2条）"
            if ts_code:
                logger.debug(f"  {ts_code}: {reason}")
            return False, 0.0, reason
        
        # 解析截止时间
        cutoff_dt = datetime.strptime(cutoff_time, "%H:%M:%S").time()
        
        # 排除9点35之前的数据（集合竞价阶段，波动大）
        start_time = datetime.strptime("09:35:00", "%H:%M:%S").time()
        
        # 先获取截止时间点的价格（用于计算涨幅）
        # 参考 monitor_near5_940.py：选取 >= cutoff_time 的第一根K线，否则取 <= cutoff_time 的最后一根
        cutoff_datetime = None
        if len(df) > 0 and 'trade_time' in df.columns:
            trade_date_str = df['trade_time'].iloc[0].strftime("%Y-%m-%d") if hasattr(df['trade_time'].iloc[0], 'strftime') else str(df['trade_time'].iloc[0])[:10]
            cutoff_datetime = datetime.strptime(f"{trade_date_str} {cutoff_time}", "%Y-%m-%d %H:%M:%S")
            
            # 选取 >= cutoff_time 的第一根K线
            ref_rows = df[df['trade_time'] >= cutoff_datetime].head(1)
            if not ref_rows.empty:
                ref_price_row = ref_rows.iloc[0]
            else:
                # 如果没有 >= cutoff_time 的数据，使用 <= cutoff_time 的最后一根
                ref_price_row = df[df['trade_time'] <= cutoff_datetime].iloc[-1] if len(df[df['trade_time'] <= cutoff_datetime]) > 0 else df.iloc[-1]
        else:
            ref_price_row = df.iloc[-1] if len(df) > 0 else None
        
        # 参考 monitor_near5_940.py：均线计算使用从9:30开始的全部数据
        # 但检查破均线时，只检查9:35之后的数据
        # 先过滤到截止时间的数据（用于计算均线）
        df_for_ma = df[df['trade_time'].apply(lambda x: x.time() <= cutoff_dt)].copy()
        
        if len(df_for_ma) < 2:
            reason = f"截止时间 {cutoff_time} 前数据不足（{len(df_for_ma)}条）"
            if ts_code:
                logger.info(f"  {ts_code}: {reason}（原始数据{len(df)}条）")
                if len(df) > 0:
                    logger.info(f"    原始数据时间范围: {df['trade_time'].min()} ~ {df['trade_time'].max()}")
            return False, 0.0, reason
        
        # 计算分时均线（累计成交额 / 累计成交量）
        # 参考 monitor_near5_940.py：使用从9:30开始的全部数据计算均线
        # 直接使用 volume.cumsum()，不乘以100
        df_for_ma['cum_amount'] = df_for_ma['amount'].cumsum()
        df_for_ma['cum_volume'] = df_for_ma['volume'].cumsum()  # 参考 monitor_near5_940.py，不乘以100
        df_for_ma['ma'] = df_for_ma['cum_amount'] / df_for_ma['cum_volume']
        
        # 如果均线值异常（太小），可能是单位问题，尝试乘以100重新计算
        if len(df_for_ma) > 0:
            last_ma = df_for_ma['ma'].iloc[-1]
            last_price = df_for_ma['close'].iloc[-1]
            # 如果均线值 < 价格的1%，说明单位可能错了，尝试乘以100
            if last_ma > 0 and last_price > 0 and last_ma < last_price * 0.01:
                logger.debug(f"  {ts_code}: 均线值异常（{last_ma:.2f}），尝试转换单位重新计算")
                df_for_ma['cum_volume'] = (df_for_ma['volume'] * 100).cumsum()  # 转换为"股"
                df_for_ma['ma'] = df_for_ma['cum_amount'] / df_for_ma['cum_volume']
        
        # 过滤：只保留9点35到截止时间之间的数据（用于检查破均线）
        # 注意：均线已经用全部数据计算好了，这里只用于检查
        df_filtered = df_for_ma[
            df_for_ma['trade_time'].apply(lambda x: x.time() >= start_time)
        ].copy()
        
        if len(df_filtered) < 2:
            reason = f"9:35到截止时间 {cutoff_time} 前数据不足（{len(df_filtered)}条）"
            if ts_code:
                logger.info(f"  {ts_code}: {reason}（用于计算均线的数据{len(df_for_ma)}条，用于检查的数据{len(df_filtered)}条）")
            return False, 0.0, reason
        
        # 调试：输出关键数据（仅在debug模式下输出详细信息）
        if ts_code and debug and len(df_filtered) > 0:
            first_row = df_filtered.iloc[0]
            last_row = df_filtered.iloc[-1]
            logger.info(f"  {ts_code}: 数据样本 - 价格={first_row['close']:.2f}, 成交量={first_row['volume']:.0f}手, 成交额={first_row['amount']:.2f}元")
            logger.info(f"  {ts_code}: 最后时刻 - 价格={last_row['close']:.2f}, 均线={last_row['ma']:.2f}, 数据条数={len(df_filtered)}")
        
        # 计算差值
        df_filtered['diff'] = df_filtered['low'] - df_filtered['ma']
        
        # 使用百分比容忍度
        df_filtered['tolerance'] = df_filtered['ma'] * (tolerance_pct / 100)
        
        # 排除第一条数据（开盘波动大），从第二条开始检查
        if len(df_filtered) <= 1:
            reason = f"过滤后数据不足（{len(df_filtered)}条）"
            if ts_code:
                logger.debug(f"  {ts_code}: {reason}")
            return False, 0.0, reason
        
        df_check = df_filtered.iloc[1:]
        
        # 检查是否有破均线
        # 参考 monitor_near5_940.py：判断条件是 low < (ma - tol)
        # 其中 tol = ma * (tolerance_pct / 100.0)
        tol = df_check['ma'] * (tolerance_pct / 100.0)
        broke_mask = df_check['low'] < (df_check['ma'] - tol)
        
        if broke_mask.any():
            broke_count = broke_mask.sum()
            last_row = df_filtered.iloc[-1]
            # 找出第一次破均线的时间和价格
            first_broke_indices = df_check.index[broke_mask]
            if len(first_broke_indices) > 0:
                first_broke_idx = first_broke_indices[0]
                broke_row = df_check.loc[first_broke_idx]
                broke_time = broke_row['trade_time'].strftime('%H:%M:%S') if hasattr(broke_row['trade_time'], 'strftime') else str(broke_row['trade_time'])
                broke_tol = broke_row['ma'] * (tolerance_pct / 100.0)
                broke_diff = broke_row['low'] - broke_row['ma']
                reason = f"破均线（{broke_count}次，首次{broke_time}），当前价={last_row['close']:.2f}, 均线={last_row['ma']:.2f}, 破线时最低价={broke_row['low']:.2f}, 破线时均线={broke_row['ma']:.2f}, 差值={broke_diff:.4f}, 容忍度={broke_tol:.4f}"
            else:
                reason = f"破均线（{broke_count}次），当前价={last_row['close']:.2f}, 均线={last_row['ma']:.2f}"
            if ts_code and debug:
                # 在debug模式下输出详细信息
                logger.info(f"  {ts_code}: {reason}")
                # 输出所有破均线的数据点（最多5个）
                for idx in first_broke_indices[:5]:
                    row = df_check.loc[idx]
                    row_tol = row['ma'] * (tolerance_pct / 100.0)
                    row_diff = row['low'] - row['ma']
                    logger.info(f"    {ts_code}: 破均线点 - 时间={row['trade_time']}, 最低价={row['low']:.2f}, 均线={row['ma']:.2f}, 差值={row_diff:.4f}, 容忍度={row_tol:.4f}")
            elif ts_code:
                logger.debug(f"  {ts_code}: {reason}")
            return False, 0.0, reason
        
        # 检查当前价是否>=均线
        last_row = df_filtered.iloc[-1]
        if last_row['close'] < (last_row['ma'] - last_row['tolerance']):
            reason = f"当前价低于均线，当前价={last_row['close']:.2f}, 均线={last_row['ma']:.2f}"
            if ts_code:
                logger.debug(f"  {ts_code}: {reason}")
            return False, 0.0, reason
        
        # 计算涨幅（使用前日收盘价作为基准，而不是今日开盘价）
        # 使用截止时间点的价格（参考 monitor_near5_940.py 的逻辑）
        if ref_price_row is not None:
            last_close = ref_price_row['close']
            ref_time = ref_price_row['trade_time'] if 'trade_time' in ref_price_row else None
        else:
            last_close = last_row['close']
            ref_time = last_row['trade_time'] if 'trade_time' in last_row else None
        
        # 使用传入的前日收盘价，如果没有则使用第一根K线的开盘价作为fallback
        if pre_close is None or pre_close <= 0:
            # Fallback：使用第一根K线的开盘价（不理想，但兼容旧逻辑）
            first_open = df_filtered.iloc[0]['open']
            if first_open <= 0:
                reason = f"开盘价无效（{first_open}），且无法获取前日收盘价"
                if ts_code:
                    logger.debug(f"  {ts_code}: {reason}")
                return False, 0.0, reason
            pre_close = first_open
            logger.debug(f"  {ts_code}: 使用开盘价作为基准（未获取到前日收盘价）")
        
        if pre_close <= 0:
            reason = f"前日收盘价无效（{pre_close}）"
            if ts_code:
                logger.debug(f"  {ts_code}: {reason}")
            return False, 0.0, reason
        
        change_pct = (last_close - pre_close) / pre_close * 100
        
        # 检查涨幅是否>=阈值
        if change_pct < min_change_pct:
            reason = f"涨幅不足，当前涨幅={change_pct:.2f}%, 要求>={min_change_pct}%（前日收盘={pre_close:.2f}, 当前价={last_close:.2f}）"
            if ts_code:
                logger.info(f"  {ts_code}: {reason}")
            return False, change_pct, reason
        
        if ts_code:
            logger.info(f"  ✅ {ts_code}: 符合条件，涨幅={change_pct:.2f}%, 当前价={last_close:.2f}, 均线={last_row['ma']:.2f}")
        return True, change_pct, "符合条件"
    
    def process_single_stock(self, ts_code: str, trade_date: str, 
                              cutoff_time: str, min_change_pct: float) -> Optional[Dict]:
        """
        处理单只股票
        
        Returns:
            Dict: 满足条件的股票信息，不满足返回None
            如果返回None且reason包含"破均线"，则说明该股票已破均线
        """
        try:
            # 先获取前日收盘价
            pre_close = self.get_previous_close(ts_code, trade_date)
            if pre_close is None:
                logger.debug(f"  {ts_code}: 无法获取前日收盘价，跳过")
                return None
            
            # 获取分时数据
            df = self.get_intraday_data(ts_code, trade_date)
            if df is None:
                # get_intraday_data 已经输出了详细日志，这里不需要再输出
                return None
            
            # 将前日收盘价作为参数传入check_never_break_ma
            # 开启debug模式，输出详细信息
            is_valid, change_pct, reason = self.check_never_break_ma(
                df, cutoff_time, min_change_pct, ts_code=ts_code, debug=True, pre_close=pre_close
            )
            
            # 如果破均线，标记到实例变量中（供run_monitor_at_time使用）
            if not is_valid and "破均线" in reason:
                # 线程安全地添加破均线股票
                with self._broken_ma_stocks_lock:
                    if not hasattr(self, '_broken_ma_stocks'):
                        self._broken_ma_stocks = set()
                    self._broken_ma_stocks.add(ts_code)
            
            if is_valid:
                # 获取成交额
                amount = df['amount'].sum() if 'amount' in df.columns else 0
                
                # 获取截止时间点的当前价格（用于计算30日新高）
                cutoff_dt = datetime.strptime(cutoff_time, "%H:%M:%S").time()
                df_for_ma = df[df['trade_time'].apply(lambda x: x.time() <= cutoff_dt)].copy()
                if len(df_for_ma) > 0:
                    current_price = df_for_ma.iloc[-1]['close']
                else:
                    current_price = df.iloc[-1]['close'] if len(df) > 0 else None
                
                # 计算是否30日新高（不作为筛选条件，只用于显示）
                is_30d_high = False
                high_30d = None
                if current_price is not None:
                    high_30d = self.get_30day_high(ts_code, trade_date)
                    if high_30d is not None:
                        is_30d_high = current_price >= high_30d
                        if ts_code:
                            if is_30d_high:
                                logger.info(f"  {ts_code}: ✅ 达到30日新高，当前价={current_price:.2f}, 30日最高价={high_30d:.2f}")
                            else:
                                logger.debug(f"  {ts_code}: 未达到30日新高，当前价={current_price:.2f}, 30日最高价={high_30d:.2f}, 差距={((high_30d - current_price) / high_30d * 100):.2f}%")
                
                # 计算5日涨幅和10日涨幅（使用监控时间点的价格）
                pct_5d, pct_10d = self.get_5d_10d_change_pct(ts_code, trade_date, current_price=float(current_price) if current_price is not None else None)
                
                logger.info(f"  ✅ {ts_code}: 符合条件，涨幅={change_pct:.2f}%, 成交额={amount/1e8:.2f}亿")
                return {
                    'ts_code': ts_code,
                    'code': ts_code.split('.')[0],
                    'change_pct': change_pct,
                    'pct_5d': pct_5d,
                    'pct_10d': pct_10d,
                    'amount': amount,
                    'is_30d_high': is_30d_high,
                    'current_price': current_price,
                    'high_30d': high_30d
                }
            
            return None
            
        except Exception as e:
            logger.warning(f"处理 {ts_code} 失败: {e}")
            return None
    
    def run_monitor_at_time(self, stock_codes: List[str], trade_date: str, 
                            cutoff_time: str, min_change_pct: float = 3.0,
                            max_workers: int = 20) -> Tuple[List[Dict], List[str]]:
        """
        在指定时间点运行监控
        
        Args:
            stock_codes: 候选股票代码列表（ts_code格式）
            trade_date: 交易日期
            cutoff_time: 截止时间
            min_change_pct: 最小涨幅阈值
            max_workers: 并发线程数（默认20，提高并发以加快处理速度）
        
        Returns:
            Tuple[List[Dict], List[str]]: (满足条件的股票列表, 破均线股票列表)
        """
        # 初始化破均线股票集合（每次调用时重置，使用锁保证线程安全）
        with self._broken_ma_stocks_lock:
            self._broken_ma_stocks = set()
        
        logger.info(f"📊 时间点 {cutoff_time}: 开始检查 {len(stock_codes)} 只股票（并发数: {max_workers}）...")
        results = []
        processed = 0
        total = len(stock_codes)
        
        # 统计信息
        stats = {
            'no_pre_close': 0,
            'no_intraday_data': 0,
            'insufficient_data': 0,
            'broke_ma': 0,
            'below_ma': 0,
            'low_change': 0,
            'success': 0
        }
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(self.process_single_stock, code, trade_date, cutoff_time, min_change_pct): code
                for code in stock_codes
            }
            
            for future in as_completed(futures):
                result = future.result()
                processed += 1
                
                # 每处理10%更新一次进度
                if processed % max(1, total // 10) == 0 or processed == total:
                    progress_pct = int(processed * 100 / total)
                    self._update_status(message=f"执行 {cutoff_time}... ({progress_pct}%)")
                
                if result:
                    results.append(result)
                    stats['success'] += 1
        
        # 按涨幅排序
        results.sort(key=lambda x: x['change_pct'], reverse=True)
        
        # 线程安全地获取破均线股票列表
        with self._broken_ma_stocks_lock:
            broken_ma_stocks = list(self._broken_ma_stocks) if hasattr(self, '_broken_ma_stocks') and self._broken_ma_stocks else []
        
        logger.info(f"📊 时间点 {cutoff_time}: 从 {len(stock_codes)} 只股票中筛选出 {len(results)} 只")
        if len(broken_ma_stocks) > 0:
            logger.info(f"   ⚠️ 发现 {len(broken_ma_stocks)} 只股票破均线，后续时间点将跳过这些股票")
        if len(results) > 0:
            logger.info(f"   涨幅范围: {results[-1]['change_pct']:.2f}% ~ {results[0]['change_pct']:.2f}%")
        else:
            logger.info(f"   ⚠️ 没有符合条件的股票")
            logger.info(f"   筛选条件：")
            logger.info(f"     1. 9:35-{cutoff_time}期间未破分时均线")
            logger.info(f"     2. 当前价 >= 分时均线")
            logger.info(f"     3. 涨幅（相对前日收盘价）>= {min_change_pct}%")
            logger.info(f"   提示: 请查看上方DEBUG日志了解每只股票不符合的原因")
            logger.info(f"   如需查看详细日志，请将日志级别设置为DEBUG")
        
        return results, broken_ma_stocks
    
    def save_results_to_db(self, results: List[Dict], trade_date: str, monitor_time: str):
        """保存结果到数据库"""
        if not results:
            logger.info(f"时间点 {monitor_time} 没有监控结果，跳过保存")
            return
        
        logger.info(f"🔍 开始保存 {len(results)} 条结果到数据库: {trade_date} {monitor_time}")
        
        try:
            if not self.warehouse:
                logger.error("❌ warehouse 对象不存在")
                return
                
            if not self.warehouse.warehouse_service:
                logger.error("❌ 数据库服务未初始化，无法保存监控结果")
                return
            
            logger.info(f"🔍 数据库服务已初始化，准备获取session...")
            session = self.warehouse.warehouse_service.get_session()
            
            try:
                logger.info(f"🔍 Session获取成功，开始处理 {len(results)} 条结果...")
                
                # 获取股票名称
                codes = [r['ts_code'] for r in results]
                logger.info(f"🔍 需要查询的股票代码: {codes[:5]}..." if len(codes) > 5 else f"🔍 需要查询的股票代码: {codes}")
                
                stock_names = {}
                stocks = session.query(DimStock).filter(DimStock.ts_code.in_(codes)).all()
                logger.info(f"🔍 从数据库查询到 {len(stocks)} 只股票的名称信息")
                
                for s in stocks:
                    stock_names[s.ts_code] = s.name
                
                # 插入或更新记录
                monitor_time_obj = datetime.strptime(monitor_time, "%H:%M:%S").time()
                trade_date_obj = datetime.strptime(trade_date, "%Y-%m-%d").date()
                
                logger.info(f"🔍 开始遍历结果，准备插入/更新记录...")
                saved_count = 0
                updated_count = 0
                error_count = 0
                
                for idx, r in enumerate(results):
                    try:
                        stock_code = r.get('code', '')
                        ts_code = r.get('ts_code', '')
                        
                        if not stock_code:
                            logger.warning(f"⚠️ 第 {idx+1} 条结果缺少 code 字段: {r}")
                            error_count += 1
                            continue
                        
                        # 确保数值类型转换为 Python 原生类型（避免 np.float64 等 numpy 类型）
                        change_pct = r.get('change_pct', 0)
                        pct_5d = r.get('pct_5d', None)
                        pct_10d = r.get('pct_10d', None)
                        amount = r.get('amount', 0)
                        
                        # 转换为 Python 原生类型
                        if change_pct is not None:
                            change_pct = float(change_pct)
                        else:
                            change_pct = 0.0
                        
                        if pct_5d is not None:
                            pct_5d = float(pct_5d)
                        else:
                            pct_5d = None
                        
                        if pct_10d is not None:
                            pct_10d = float(pct_10d)
                        else:
                            pct_10d = None
                            
                        if amount is not None:
                            amount = float(amount)
                        else:
                            amount = 0.0
                        
                        existing = session.query(FactMonitorNear5940).filter(
                            FactMonitorNear5940.trade_date == trade_date_obj,
                            FactMonitorNear5940.monitor_time == monitor_time_obj,
                            FactMonitorNear5940.stock_code == stock_code
                        ).first()
                        
                        if existing:
                            existing.pct_today = change_pct
                            existing.pct_5d = pct_5d
                            existing.pct_10d = pct_10d
                            existing.amount = amount
                            existing.stock_name = stock_names.get(ts_code, '')
                            updated_count += 1
                            logger.debug(f"  更新记录: {stock_code}")
                        else:
                            record = FactMonitorNear5940(
                                trade_date=trade_date_obj,
                                monitor_time=monitor_time_obj,
                                stock_code=stock_code,
                                stock_name=stock_names.get(ts_code, ''),
                                pct_today=change_pct,
                                pct_5d=pct_5d,
                                pct_10d=pct_10d,
                                amount=amount
                            )
                            session.add(record)
                            saved_count += 1
                            logger.debug(f"  新增记录: {stock_code}")
                    except Exception as record_error:
                        logger.error(f"❌ 处理第 {idx+1} 条结果失败: {record_error}", exc_info=True)
                        error_count += 1
                        continue
                
                logger.info(f"🔍 准备提交事务: 新增 {saved_count} 条, 更新 {updated_count} 条, 错误 {error_count} 条")
                session.commit()
                logger.info(f"✅ 保存监控结果到数据库成功: {trade_date} {monitor_time}, 新增 {saved_count} 条, 更新 {updated_count} 条, 错误 {error_count} 条, 共 {len(results)} 条")
            except Exception as inner_error:
                logger.error(f"❌ 保存过程中发生错误: {inner_error}", exc_info=True)
                session.rollback()
                raise
            finally:
                session.close()
                logger.info(f"🔍 Session已关闭")
        
        except Exception as e:
            logger.error(f"❌ 保存监控结果失败: {e}", exc_info=True)
            raise  # 重新抛出异常，让调用者知道保存失败
    
    def get_results_from_db(self, trade_date: str, monitor_time: str) -> List[Dict]:
        """从数据库获取监控结果，并计算是否30日新高"""
        try:
            if not self.warehouse.warehouse_service:
                logger.warning("数据库服务未初始化，无法获取监控结果")
                return []
            
            session = self.warehouse.warehouse_service.get_session()
            try:
                monitor_time_obj = datetime.strptime(monitor_time, "%H:%M:%S").time()
                trade_date_obj = datetime.strptime(trade_date, "%Y-%m-%d").date()
                
                records = session.query(FactMonitorNear5940).filter(
                    FactMonitorNear5940.trade_date == trade_date_obj,
                    FactMonitorNear5940.monitor_time == monitor_time_obj
                ).order_by(FactMonitorNear5940.pct_today.desc()).all()
                
                results = []
                for r in records:
                    # 构建ts_code（从stock_code转换为ts_code格式）
                    stock_code = r.stock_code
                    if stock_code.startswith('6'):
                        ts_code = f"{stock_code}.SH"
                    elif stock_code.startswith(('0', '3')):
                        ts_code = f"{stock_code}.SZ"
                    else:
                        ts_code = f"{stock_code}.BJ"
                    
                    # 如果数据库中没有5日/10日涨幅，重新计算
                    pct_5d = float(r.pct_5d) if r.pct_5d else None
                    pct_10d = float(r.pct_10d) if r.pct_10d else None
                    
                    # 计算是否30日新高，并获取监控时间点的价格
                    is_30d_high = False
                    current_price = None
                    high_30d = None
                    
                    try:
                        # 获取分时数据，找到监控时间点的价格
                        df = self.get_intraday_data(ts_code, trade_date)
                        if df is not None and len(df) > 0:
                            cutoff_dt = datetime.strptime(monitor_time, "%H:%M:%S").time()
                            df_for_time = df[df['trade_time'].apply(lambda x: x.time() <= cutoff_dt)].copy()
                            if len(df_for_time) > 0:
                                current_price = float(df_for_time.iloc[-1]['close'])
                                
                                # 获取30日最高价
                                high_30d = self.get_30day_high(ts_code, trade_date)
                                if high_30d is not None and current_price is not None:
                                    is_30d_high = current_price >= high_30d
                    except Exception as e:
                        logger.debug(f"计算 {ts_code} 30日新高失败: {e}")
                    
                    # 如果数据库中没有5日/10日涨幅，使用监控时间点的价格重新计算
                    if (pct_5d is None or pct_10d is None) and current_price is not None:
                        logger.debug(f"  {ts_code}: 数据库中没有5日/10日涨幅，使用监控时间点价格重新计算...")
                        pct_5d_calc, pct_10d_calc = self.get_5d_10d_change_pct(ts_code, trade_date, current_price=current_price)
                        if pct_5d is None:
                            pct_5d = pct_5d_calc
                        if pct_10d is None:
                            pct_10d = pct_10d_calc
                    
                    results.append({
                        'code': r.stock_code,
                        'name': r.stock_name,
                        'pct_today': float(r.pct_today) if r.pct_today else 0,
                        'pct_5d': pct_5d,
                        'pct_10d': pct_10d,
                        'amount': float(r.amount) if r.amount else 0,
                        'is_30d_high': is_30d_high,
                        'current_price': current_price,
                        'high_30d': high_30d
                    })
                
                return results
            finally:
                session.close()
                
        except Exception as e:
            logger.error(f"获取监控结果失败: {e}")
            return []
    
    def add_to_watchlist(self, results: List[Dict], trade_date: str, time_point: str):
        """
        将监控结果添加到股票跟踪表
        
        Args:
            results: 监控结果列表
            trade_date: 交易日期
            time_point: 时间点（如 09:40:00）
        """
        try:
            from data_warehouse.models import FactStockWatchlist
            from data_warehouse.service.warehouse_service import WarehouseService
            
            ws = WarehouseService()
            session = ws.get_session()
            
            try:
                # 格式化备注：如 "2025-11-28 9点40"
                time_label = time_point[:5].replace(":", "点").lstrip("0")  # 09:40:00 -> 9点40
                note = f"{trade_date} {time_label}"
                
                added_count = 0
                for r in results:
                    ts_code = r.get('ts_code', '')
                    if not ts_code:
                        continue
                    
                    # 检查是否已存在
                    existing = session.query(FactStockWatchlist).filter(
                        FactStockWatchlist.ts_code == ts_code
                    ).first()
                    
                    if not existing:
                        watchlist_item = FactStockWatchlist(
                            ts_code=ts_code,
                            note=note,
                            added_at=datetime.now()
                        )
                        session.add(watchlist_item)
                        added_count += 1
                
                session.commit()
                logger.info(f"✅ 将 {added_count} 只股票添加到跟踪列表，备注: {note}")
                
            finally:
                session.close()
                
        except Exception as e:
            logger.error(f"添加到跟踪列表失败: {e}")
    
    def start_chain_monitor(self, trade_date: str = None, min_change_pct: float = 3.0,
                            max_workers: int = 20):
        """
        启动链式监控任务（后台线程）
        
        Args:
            trade_date: 交易日期，默认今天
            min_change_pct: 最小涨幅阈值
            max_workers: 并发线程数
        """
        if self._task_running:
            logger.warning("监控任务已在运行中")
            return False
        
        # 重置状态
        self._update_status(
            running=True,
            progress=0,
            message="初始化...",
            results=[],
            error=None
        )
        
        # 启动后台线程
        thread = threading.Thread(
            target=self._run_chain_monitor,
            args=(trade_date, min_change_pct, max_workers),
            daemon=True
        )
        thread.start()
        
        return True
    
    def _run_chain_monitor(self, trade_date: str, min_change_pct: float, max_workers: int):
        """链式监控任务执行"""
        try:
            if not trade_date:
                trade_date = datetime.now().strftime("%Y-%m-%d")
            
            # 获取S1股票列表
            self._update_status(message="获取S1股票列表...")
            s1_stocks = self.get_s1_stocks(trade_date)
            
            if not s1_stocks:
                error_msg = "未获取到S1股票（可能因数据验证失败）"
                logger.warning(f"⚠️ {error_msg}")
                self._update_status(running=False, error=error_msg)
                return
            
            # ✅ 双重验证：在开始监控前再次检查（防止get_s1_stocks返回异常数据）
            if len(s1_stocks) > MonitorNear5Config.MAX_TOTAL_STOCKS:
                error_msg = f"S1股票池数量异常（{len(s1_stocks)}只），超过阈值（{MonitorNear5Config.MAX_TOTAL_STOCKS}只），停止监控"
                logger.error("=" * 80)
                logger.error(f"🚨 【严重告警】{error_msg}")
                logger.error(f"   交易日期: {trade_date}")
                logger.error("   处理措施: 请检查S1股票池数据并手动刷新")
                logger.error("=" * 80)
                self._update_status(running=False, error=error_msg)
                return
            
            logger.info(f"开始链式监控，候选股票: {len(s1_stocks)} 只")
            
            # 转换为ts_code格式
            current_stocks = []
            for code in s1_stocks:
                code = str(code).strip()
                if '.' not in code:
                    if code.startswith('6'):
                        code = f"{code}.SH"
                    elif code.startswith(('0', '3')):
                        code = f"{code}.SZ"
                    else:
                        code = f"{code}.BJ"
                current_stocks.append(code)
            
            is_today = trade_date == datetime.now().strftime("%Y-%m-%d")
            all_results = []
            broken_ma_stocks_set = set()  # 维护已破均线股票集合
            
            for i, time_point in enumerate(MONITOR_TIME_POINTS):
                self._update_status(
                    progress=i,
                    message=f"执行 {time_point}..."
                )
                
                # 排除已破均线的股票
                stocks_to_check = [code for code in current_stocks if code not in broken_ma_stocks_set]
                if len(stocks_to_check) < len(current_stocks):
                    skipped_count = len(current_stocks) - len(stocks_to_check)
                    logger.info(f"⏭️  时间点 {time_point}: 跳过 {skipped_count} 只已破均线的股票（之前时间点已破均线）")
                
                if not stocks_to_check:
                    logger.info(f"⏭️  时间点 {time_point}: 所有候选股票都已破均线，跳过此时间点")
                    # 继续下一个时间点
                    continue
                
                # 如果是今天，需要等待到目标时间
                if is_today:
                    target_time = datetime.strptime(f"{trade_date} {time_point}", "%Y-%m-%d %H:%M:%S")
                    now = datetime.now()
                    
                    if now < target_time:
                        wait_seconds = (target_time - now).total_seconds()
                        self._update_status(message=f"等待到 {time_point}（还需 {int(wait_seconds)} 秒）...")
                        
                        # 分段等待，每10秒检查一次
                        while wait_seconds > 0:
                            sleep_time = min(10, wait_seconds)
                            time.sleep(sleep_time)
                            wait_seconds -= sleep_time
                            
                            now = datetime.now()
                            wait_seconds = (target_time - now).total_seconds()
                            if wait_seconds > 0:
                                self._update_status(message=f"等待到 {time_point}（还需 {int(wait_seconds)} 秒）...")
                
                # 执行监控
                results, new_broken_ma_stocks = self.run_monitor_at_time(
                    stocks_to_check, trade_date, time_point, min_change_pct, max_workers
                )
                
                # 更新已破均线股票集合
                broken_ma_stocks_set.update(new_broken_ma_stocks)
                
                logger.info(f"📊 时间点 {time_point} 监控完成，获得 {len(results)} 条结果，准备保存到数据库...")
                
                # 保存结果到数据库（无论结果是否为空都会调用，函数内部会判断）
                try:
                    self.save_results_to_db(results, trade_date, time_point)
                    logger.info(f"✅ 时间点 {time_point} 保存数据库操作完成")
                except Exception as save_error:
                    logger.error(f"❌ 时间点 {time_point} 保存数据库失败: {save_error}", exc_info=True)
                
                # 9:40监控结果存入股票跟踪（可选，默认关闭）
                if time_point == "09:40:00" and results:
                    if MonitorNear5Config.ENABLE_AUTO_ADD_TO_WATCHLIST:
                        try:
                            # 筛选：只添加涨幅>=阈值的股票
                            filtered_results = [
                                r for r in results 
                                if r.get('pct_today', 0) >= MonitorNear5Config.MIN_CHANGE_PCT_FOR_WATCHLIST
                            ]
                            
                            # 按涨幅降序排序，只取前N只
                            filtered_results.sort(key=lambda x: x.get('pct_today', 0), reverse=True)
                            top_results = filtered_results[:MonitorNear5Config.MAX_WATCHLIST_ADD_COUNT]
                            
                            if top_results:
                                logger.info(f"📊 准备添加 {len(top_results)} 只股票到watchlist（从 {len(results)} 只中筛选，"
                                          f"涨幅阈值>={MonitorNear5Config.MIN_CHANGE_PCT_FOR_WATCHLIST}%，"
                                          f"最多{MonitorNear5Config.MAX_WATCHLIST_ADD_COUNT}只）")
                                self.add_to_watchlist(top_results, trade_date, time_point)
                            else:
                                logger.info(f"📊 未找到符合条件的股票添加到watchlist（涨幅阈值>={MonitorNear5Config.MIN_CHANGE_PCT_FOR_WATCHLIST}%）")
                        except Exception as watchlist_error:
                            logger.error(f"❌ 添加到跟踪列表失败: {watchlist_error}", exc_info=True)
                    else:
                        logger.debug(f"⏸️ 自动添加到watchlist功能已关闭（ENABLE_AUTO_ADD_TO_WATCHLIST=False），跳过添加")
                
                # 更新结果
                result_codes = [r['code'] for r in results] if results else []
                all_results = result_codes
                self._update_status(results=result_codes)
                
                logger.info(f"时间点 {time_point} 完成，筛选出 {len(results)} 只股票")
                
                # 链式：下一轮使用本轮结果作为输入
                if results:
                    # 有结果，更新候选股票列表为本次筛选出的股票
                    current_stocks = [r['ts_code'] for r in results]
                    logger.info(f"  下一轮将监控这 {len(current_stocks)} 只股票")
                else:
                    # 没有结果，提前结束链式监控（因为后续时间点也没有股票可以监控了）
                    logger.info(f"  时间点 {time_point} 没有符合条件的股票，链式监控提前结束")
                    remaining_points = len(MONITOR_TIME_POINTS) - i - 1
                    if remaining_points > 0:
                        logger.info(f"  跳过后续 {remaining_points} 个时间点（{MONITOR_TIME_POINTS[i+1:]}）")
                    break
            
            self._update_status(
                running=False,
                progress=len(MONITOR_TIME_POINTS),
                message=f"监控完成，最终筛选出 {len(all_results)} 只股票",
                results=all_results
            )
            
        except Exception as e:
            logger.error(f"链式监控任务失败: {e}", exc_info=True)
            self._update_status(running=False, error="监控任务失败")


# 单例
_service_instance = None

def get_monitor_service() -> MonitorNear5Service:
    """获取监控服务单例"""
    global _service_instance
    if _service_instance is None:
        _service_instance = MonitorNear5Service()
    return _service_instance

