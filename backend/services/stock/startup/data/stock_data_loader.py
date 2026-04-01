"""
股票数据加载器
负责从数据库加载股票数据
"""

import logging
import pandas as pd
from typing import Dict, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class StockDataLoader:
    """股票数据加载器"""
    
    # 类级别的实时数据源缓存（避免重复初始化）
    _realtime_source = None
    _realtime_source_lock = None
    
    def __init__(self, warehouse_service):
        """
        初始化数据加载器
        
        Args:
            warehouse_service: 数据仓库服务实例
        """
        self.warehouse = warehouse_service
        
        # 初始化锁（如果还没有）
        if StockDataLoader._realtime_source_lock is None:
            import threading
            StockDataLoader._realtime_source_lock = threading.Lock()
    
    def _get_realtime_source(self):
        """
        获取实时数据源实例（单例模式，避免重复初始化）
        
        Returns:
            SinaRealtimeSource实例，如果初始化失败返回None
        """
        if StockDataLoader._realtime_source is None:
            with StockDataLoader._realtime_source_lock:
                # 双重检查锁定
                if StockDataLoader._realtime_source is None:
                    try:
                        from backend.services.data_sources.realtime_source import SinaRealtimeSource
                        StockDataLoader._realtime_source = SinaRealtimeSource()
                        logger.debug("实时数据源实例已创建并缓存")
                    except Exception as e:
                        logger.debug(f"实时数据源初始化失败: {e}")
                        return None
        return StockDataLoader._realtime_source
    
    def load_stock_data(self, ts_code: str, trade_date: Optional[str] = None, force_realtime: bool = False, fallback_to_latest_if_no_data: bool = False) -> Optional[Dict]:
        """
        加载单只股票的完整数据（包含所有指标）
        
        Args:
            ts_code: 股票代码
            trade_date: 交易日期（None=最新）
            force_realtime: 是否强制使用实时数据
            fallback_to_latest_if_no_data: 仅用于龙头诊断。请求日无K线时是否用数据库中该股最新可用数据（默认False）
        
        Returns:
            包含所有指标的字典，如果失败返回None
        """
        try:
            from data_warehouse.models.generated_models import FactDailyPriceQfq
            from data_warehouse.models.orm_classes import DimStock
            from sqlalchemy import and_
            
            session = self.warehouse.get_session()
            
            try:
                # 确定目标日期（如果没有指定或不是交易日，则使用最近的交易日）
                from backend.utils.trade_date_utils import get_trade_date_or_latest
                
                if not trade_date:
                    # 未指定日期，查找最近的交易日
                    latest_trade_date = get_trade_date_or_latest(self.warehouse, None)
                    if latest_trade_date:
                        target_date = latest_trade_date
                        trade_date = latest_trade_date.strftime('%Y-%m-%d')
                        # 只在第一次调用时记录，避免日志过多
                        if not hasattr(self, '_logged_target_date'):
                            logger.info(f"📅 批量扫描使用目标日期: {trade_date}")
                            self._logged_target_date = True
                    else:
                        # 如果找不到交易日，使用今天（降级）
                        target_date = datetime.now().date()
                        trade_date = target_date.strftime('%Y-%m-%d')
                        logger.warning(f"⚠️ 未找到最近交易日，使用今天: {trade_date}（可能数据未更新）")
                else:
                    target_date = datetime.strptime(trade_date, '%Y-%m-%d').date()
                    # 检查指定日期是否为交易日，如果不是则查找最近的交易日
                    latest_trade_date = get_trade_date_or_latest(self.warehouse, trade_date)
                    if latest_trade_date and latest_trade_date != target_date:
                        logger.debug(f"指定日期 {trade_date} 不是交易日，使用最近交易日: {latest_trade_date}")
                        target_date = latest_trade_date
                        trade_date = latest_trade_date.strftime('%Y-%m-%d')
                
                # 1. 获取基本信息
                stock_info = session.query(DimStock).filter(
                    DimStock.ts_code == ts_code
                ).first()
                
                if not stock_info:
                    # ✅ 优化：将警告改为 debug 级别，因为这是正常情况（某些股票可能已退市或数据缺失）
                    logger.debug(f"{ts_code}: 未找到股票基本信息（可能已退市或数据缺失）")
                    return None
                
                # 2. 获取当日数据
                today_data = session.query(FactDailyPriceQfq).filter(
                    and_(
                        FactDailyPriceQfq.ts_code == ts_code,
                        FactDailyPriceQfq.trade_date == target_date
                    )
                ).first()
                
                # 如果目标日期没有数据：仅当 fallback_to_latest_if_no_data=True（龙头诊断）时用该股最新数据，否则返回 None
                prev_data = None
                if not today_data:
                    today = datetime.now().date()
                    is_historical_backfill = target_date < today
                    
                    if is_historical_backfill:
                        logger.debug(f"{ts_code}: 历史回填场景，目标日期 {target_date} 无数据，跳过该股票")
                        return None
                    
                    if fallback_to_latest_if_no_data:
                        # 仅龙头诊断：请求日无K线时用数据库中该股最新可用数据
                        latest_available = session.query(FactDailyPriceQfq).filter(
                            and_(
                                FactDailyPriceQfq.ts_code == ts_code,
                                FactDailyPriceQfq.trade_date <= target_date
                            )
                        ).order_by(FactDailyPriceQfq.trade_date.desc()).first()
                        if latest_available:
                            requested_date_str = trade_date
                            today_data = latest_available
                            target_date = latest_available.trade_date
                            trade_date = target_date.strftime('%Y-%m-%d')
                            logger.info(f"{ts_code}: 龙头诊断-请求日 {requested_date_str} 无K线，使用数据库中最新数据 {trade_date}")
                        else:
                            logger.debug(f"{ts_code}: 目标日期无数据且无历史数据")
                            return None
                    elif force_realtime:
                        prev_data = session.query(FactDailyPriceQfq).filter(
                            and_(
                                FactDailyPriceQfq.ts_code == ts_code,
                                FactDailyPriceQfq.trade_date < target_date
                            )
                        ).order_by(FactDailyPriceQfq.trade_date.desc()).first()
                        if prev_data:
                            logger.debug(f"⚠️ 目标日期无数据，强制实时模式将用实时数据补今日")
                        else:
                            logger.debug(f"{ts_code}: 无任何历史数据")
                            return None
                    else:
                        logger.debug(f"{ts_code}: 目标日期 {target_date} 无数据，跳过")
                        return None
                
                # 3. 获取历史K线数据（近150天，用于计算各种指标，包括120日均线）
                kline = session.query(FactDailyPriceQfq).filter(
                    and_(
                        FactDailyPriceQfq.ts_code == ts_code,
                        FactDailyPriceQfq.trade_date <= target_date
                    )
                ).order_by(FactDailyPriceQfq.trade_date.desc()).limit(150).all()
                
                # 需要至少120条数据才能计算120日均线
                if len(kline) < 120:
                    logger.debug(f"{ts_code}: K线数据不足({len(kline)}条，需要至少120条以计算120日均线)")
                    return None
                
                # 转换为DataFrame，方便计算
                kline_df = pd.DataFrame([{
                    'trade_date': k.trade_date,
                    'open': float(k.open) if k.open else 0,
                    'high': float(k.high) if k.high else 0,
                    'low': float(k.low) if k.low else 0,
                    'close': float(k.close) if k.close else 0,
                    'volume': float(k.vol) if k.vol else 0,
                    'amount': float(k.amount) if k.amount else 0,
                    'turnover_rate': float(k.turnover_rate) if k.turnover_rate else 0,
                    'float_share': float(k.float_share) if k.float_share else 0
                } for k in kline])
                
                kline_df = kline_df.sort_values('trade_date').reset_index(drop=True)
                
                # 3.5. 如果日期是今天，尝试获取实时价格更新数据（15点前才获取实时数据）
                today = datetime.now().date()
                current_time = datetime.now().time()
                from datetime import time as dt_time
                
                # ✅ 监控场景：强制使用实时数据（即使数据库中今天的数据还没有）
                # 15点之后优先使用数据库数据，不获取实时价格
                # 但如果 force_realtime=True，则强制使用实时数据（即使 target_date != today）
                if force_realtime:
                    use_realtime = current_time < dt_time(15, 0)
                    if use_realtime:
                        logger.debug(f"{ts_code}: 监控场景，强制使用实时数据重新计算")
                else:
                    use_realtime = target_date == today and current_time < dt_time(15, 0)
                
                if use_realtime:
                    try:
                        # 使用缓存的实时数据源实例（避免重复初始化）
                        realtime_source = self._get_realtime_source()
                        
                        if realtime_source:
                            # 转换股票代码格式（去掉.SH/.SZ后缀，只保留6位数字）
                            code_6digit = ts_code.replace('.SH', '').replace('.SZ', '').replace('.BJ', '')
                            if len(code_6digit) == 6:
                                quotes = realtime_source.get_realtime_quotes([code_6digit])
                                
                                if code_6digit in quotes and quotes[code_6digit]:
                                    quote = quotes[code_6digit]
                                    realtime_price = quote.get('price', 0)
                                    realtime_pct_chg = quote.get('pct_chg', 0)
                                    realtime_amount = quote.get('amount', 0)
                                    realtime_volume = quote.get('volume', 0)  # 成交量（手）
                                    realtime_turnover_rate = quote.get('turnover_rate', 0)
                                    
                                    if realtime_price > 0:
                                        # ✅ 如果强制实时数据且数据库中今天没有数据，需要创建或更新 today_data
                                        if not today_data and force_realtime:
                                            # 使用上一个交易日的数据作为基础，创建今天的临时数据
                                            if prev_data:
                                                from data_warehouse.models.generated_models import FactDailyPriceQfq
                                                today_data = FactDailyPriceQfq()
                                                today_data.ts_code = ts_code
                                                today_data.trade_date = today
                                                today_data.close = realtime_price
                                                today_data.change_pct = realtime_pct_chg
                                                today_data.amount = realtime_amount if realtime_amount > 0 else prev_data.amount
                                                today_data.vol = realtime_volume * 100 if realtime_volume > 0 else prev_data.vol
                                                today_data.turnover_rate = realtime_turnover_rate if realtime_turnover_rate > 0 else prev_data.turnover_rate
                                                today_data.float_share = prev_data.float_share  # 添加流通股数字段
                                                today_data.open = realtime_price  # 临时使用实时价格作为开盘价
                                                today_data.high = realtime_price
                                                today_data.low = realtime_price
                                                logger.debug(f"{ts_code}: 创建临时今日数据（强制实时模式）")
                                        
                                        # 更新 today_data 对象（如果存在）
                                        if today_data:
                                            # 更新收盘价为实时价格
                                            today_data.close = realtime_price
                                            # 更新涨跌幅
                                            today_data.change_pct = realtime_pct_chg
                                            # 更新成交额（如果实时数据有效）
                                            if realtime_amount > 0:
                                                today_data.amount = realtime_amount
                                            # 更新成交量（转换为股数：手 * 100）
                                            if realtime_volume > 0:
                                                today_data.vol = realtime_volume * 100
                                            # 更新换手率
                                            if realtime_turnover_rate > 0:
                                                today_data.turnover_rate = realtime_turnover_rate
                                        
                                        # 更新 kline_df 的最后一行（今天的数据）
                                        if not kline_df.empty and len(kline_df) > 0:
                                            last_idx = len(kline_df) - 1
                                            kline_df.at[last_idx, 'close'] = realtime_price
                                            if realtime_amount > 0:
                                                kline_df.at[last_idx, 'amount'] = realtime_amount
                                            if realtime_volume > 0:
                                                kline_df.at[last_idx, 'volume'] = realtime_volume * 100
                                            if realtime_turnover_rate > 0:
                                                kline_df.at[last_idx, 'turnover_rate'] = realtime_turnover_rate
                                            
                                            # 更新最高价（如果实时价格更高）
                                            if realtime_price > kline_df.at[last_idx, 'high']:
                                                kline_df.at[last_idx, 'high'] = realtime_price
                                            
                                            logger.debug(f"{ts_code}: 已更新实时价格 {realtime_price:.2f} (涨跌幅: {realtime_pct_chg:.2f}%)")
                                        elif force_realtime and prev_data:
                                            # ✅ 如果强制实时数据且 kline_df 中没有今天的数据，添加一行
                                            # 使用 prev_data 的 float_share（流通股数不会频繁变化）
                                            prev_float_share = float(prev_data.float_share) if prev_data.float_share else 0
                                            new_row = pd.DataFrame([{
                                                'trade_date': today,
                                                'open': realtime_price,
                                                'high': realtime_price,
                                                'low': realtime_price,
                                                'close': realtime_price,
                                                'volume': realtime_volume * 100 if realtime_volume > 0 else 0,
                                                'amount': realtime_amount if realtime_amount > 0 else 0,
                                                'turnover_rate': realtime_turnover_rate if realtime_turnover_rate > 0 else 0,
                                                'float_share': prev_float_share
                                            }])
                                            kline_df = pd.concat([kline_df, new_row], ignore_index=True)
                                            logger.debug(f"{ts_code}: 添加今日实时数据到K线（强制实时模式）")
                    except Exception as e:
                        # 实时价格获取失败不影响主流程，只记录日志
                        logger.debug(f"{ts_code}: 获取实时价格失败: {e}")
                
                # 4. 查询股吧人气排行榜排名（使用最新日期或指定日期）
                # 注意：这个查询失败不应该影响主流程，所以放在独立的try-except中
                guba_rank_position = None
                try:
                    from data_warehouse.models.guba_popularity import FactGubaPopularityRank
                    
                    # 先尝试使用指定日期查询
                    guba_rank = session.query(FactGubaPopularityRank).filter(
                        FactGubaPopularityRank.ts_code == ts_code,
                        FactGubaPopularityRank.crawl_date == target_date
                    ).first()
                    
                    # 如果指定日期没有数据，查询最新日期的数据
                    if not guba_rank:
                        latest_rank = session.query(FactGubaPopularityRank).filter(
                            FactGubaPopularityRank.ts_code == ts_code
                        ).order_by(
                            FactGubaPopularityRank.crawl_date.desc()
                        ).first()
                        
                        if latest_rank:
                            guba_rank = latest_rank
                    
                    if guba_rank:
                        guba_rank_position = guba_rank.rank_position
                        logger.debug(f"{ts_code}: 股吧人气榜排名 {guba_rank_position}")
                except ImportError:
                    # 模型导入失败（可能表不存在），静默处理
                    pass
                except Exception as e:
                    # 其他查询失败，不影响主流程，只记录debug日志
                    logger.debug(f"{ts_code}: 查询股吧人气榜排名失败: {e}")
                
                return {
                    'stock_info': stock_info,
                    'today_data': today_data,
                    'kline_df': kline_df,
                    'ts_code': ts_code,
                    'trade_date': trade_date,
                    'target_date': target_date,
                    'guba_rank_position': guba_rank_position  # 添加人气排行榜排名
                }
                
            finally:
                session.close()
                
        except Exception as e:
            logger.error(f"加载 {ts_code} 数据失败: {e}", exc_info=True)
            return None
    
    def load_kline_data(self, ts_code: str, trade_date: str, days: int = 100) -> Optional[pd.DataFrame]:
        """
        加载K线数据
        
        Args:
            ts_code: 股票代码
            trade_date: 交易日期
            days: 加载天数
        
        Returns:
            K线数据DataFrame（从旧到新排序），如果失败返回None
        """
        try:
            from data_warehouse.models.generated_models import FactDailyPriceQfq
            from sqlalchemy import and_
            
            session = self.warehouse.get_session()
            
            try:
                target_date = datetime.strptime(trade_date, '%Y-%m-%d').date()
                
                kline = session.query(FactDailyPriceQfq).filter(
                    and_(
                        FactDailyPriceQfq.ts_code == ts_code,
                        FactDailyPriceQfq.trade_date <= target_date
                    )
                ).order_by(FactDailyPriceQfq.trade_date.desc()).limit(days).all()
                
                if len(kline) == 0:
                    return None
                
                # 转换为DataFrame
                kline_df = pd.DataFrame([{
                    'trade_date': k.trade_date,
                    'open': float(k.open) if k.open else 0,
                    'high': float(k.high) if k.high else 0,
                    'low': float(k.low) if k.low else 0,
                    'close': float(k.close) if k.close else 0,
                    'volume': float(k.vol) if k.vol else 0,
                    'amount': float(k.amount) if k.amount else 0,
                    'turnover_rate': float(k.turnover_rate) if k.turnover_rate else 0,
                    'float_share': float(k.float_share) if k.float_share else 0
                } for k in kline])
                
                kline_df = kline_df.sort_values('trade_date').reset_index(drop=True)
                
                return kline_df
                
            finally:
                session.close()
                
        except Exception as e:
            logger.error(f"加载 {ts_code} K线数据失败: {e}", exc_info=True)
            return None
    
    def load_stock_info(self, ts_code: str):
        """
        加载股票基本信息
        
        Args:
            ts_code: 股票代码
        
        Returns:
            DimStock对象，如果失败返回None
        """
        try:
            from data_warehouse.models.orm_classes import DimStock
            
            session = self.warehouse.get_session()
            
            try:
                stock_info = session.query(DimStock).filter(
                    DimStock.ts_code == ts_code
                ).first()
                
                return stock_info
                
            finally:
                session.close()
                
        except Exception as e:
            logger.error(f"加载 {ts_code} 基本信息失败: {e}", exc_info=True)
            return None

