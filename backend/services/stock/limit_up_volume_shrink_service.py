"""
涨停缩量计算服务
查找最近5个交易日内有涨停记录，且当前量比<0.55的主板股票
"""
import logging
from typing import List, Dict, Optional
from datetime import date, datetime, timedelta
from sqlalchemy import and_, func, text, or_
from sqlalchemy.orm import Session
import pandas as pd

from data_warehouse.service.warehouse_service import WarehouseService
from data_warehouse.models.generated_models import FactDailyPriceQfq, DimTradeCalendar
from data_warehouse.models.orm_classes import DimStock
from data_warehouse.models.limit_up_volume_shrink import FactLimitUpVolumeShrink
from data_warehouse.models.tonghuashun_limit_up import FactTonghuashunLimitUp
from backend.services.stock.stock_universe_service import StockUniverseService
from data_warehouse.sources.tonghuashun_client import TonghuashunClient

logger = logging.getLogger(__name__)


# 策略常量配置
class StrategyConfig:
    """策略配置常量"""
    # 主板策略配置
    MAINBOARD_VOLUME_RATIO_THRESHOLD = 0.55  # 主板量比阈值
    
    # 创业板/科创板策略配置
    CYB_VOLUME_RATIO_THRESHOLD = 0.7  # 创业板/科创板量比阈值（用于批量计算）
    CYB_VOLUME_RATIO_THRESHOLD_REALTIME = 0.7  # 创业板/科创板量比阈值（用于实时计算）
    CYB_DECLINE_THRESHOLD = -10.0  # 跌幅阈值（跌幅不能大于10%）
    CYB_RISE_THRESHOLD = 8.0  # 涨幅阈值（涨幅>=8%）
    CYB_30D_HIGH_THRESHOLD = 0.95  # 30日最高价阈值（收盘价 >= 30日最高收盘价的95%）
    CYB_30D_DAYS = 30  # 30日最高价计算天数
    
    # 同花顺接口调用开关
    ENABLE_TONGHUASHUN_API_CALL = False  # 是否启用同花顺接口调用（False=暂停调用）


class LimitUpVolumeShrinkService:
    """涨停缩量计算服务"""
    
    def __init__(self):
        self.warehouse = WarehouseService()
        self.universe_service = StockUniverseService()
        self.ths_client = TonghuashunClient()
        self.config = StrategyConfig()
    
    def _get_cyb_stock_codes(self, session: Session) -> List[str]:
        """
        从基础池获取创业板和科创板股票代码列表
        
        Args:
            session: 数据库会话
        
        Returns:
            List[str]: 股票代码列表（格式：300001.SZ, 688001.SH）
        """
        try:
            # 从基础池获取股票代码
            base_codes = self.universe_service.get_universe_stocks(
                universe_type='base',
                trade_date=None,  # 使用最新的基础池
                active_only=True
            )
            
            if not base_codes:
                logger.warning("⚠️ 基础池为空，请先刷新基础池")
                return []
            
            logger.info(f"从基础池获取到 {len(base_codes)} 只股票")
            
            # 从基础池中筛选出创业板和科创板股票（300开头或688开头）
            cyb_codes = [
                code for code in base_codes 
                if code.startswith('300') or code.startswith('688')
            ]
            
            logger.info(f"从基础池筛选出 {len(cyb_codes)} 只创业板/科创板股票")
            return cyb_codes
        except Exception as e:
            logger.error(f"从基础池获取创业板/科创板股票代码失败: {e}", exc_info=True)
            return []
    
    def _get_next_trading_dates(self, session: Session, start_date: date, count: int) -> List[date]:
        """
        获取从指定日期开始的后续N个交易日
        
        Args:
            session: 数据库会话
            start_date: 起始日期
            count: 需要获取的交易日数量
        
        Returns:
            List[date]: 交易日列表（按时间顺序）
        """
        try:
            # 优先使用交易日历
            query = session.query(DimTradeCalendar.trade_date).filter(
                DimTradeCalendar.trade_date > start_date,
                DimTradeCalendar.is_open == True
            ).order_by(
                DimTradeCalendar.trade_date.asc()
            ).limit(count)
            
            results = query.all()
            if results:
                dates = [row[0] for row in results]
                if len(dates) == count:
                    return dates
            
            # 降级：从价格表获取
            query = session.query(
                func.distinct(FactDailyPriceQfq.trade_date)
            ).filter(
                FactDailyPriceQfq.trade_date > start_date
            ).order_by(
                FactDailyPriceQfq.trade_date.asc()
            ).limit(count)
            
            results = query.all()
            dates = [row[0] for row in results]
            return dates
        except Exception as e:
            logger.error(f"获取后续交易日失败: {e}", exc_info=True)
            # 降级：简单计算（跳过周末）
            dates = []
            current = start_date
            while len(dates) < count:
                current += timedelta(days=1)
                if current.weekday() < 5:  # 周一到周五
                    dates.append(current)
                if (current - start_date).days > count + 5:  # 最多往后找count+5天
                    break
            return dates[:count]
    
    def _check_volume_ratio(self, session: Session, ts_code: str, check_date: date) -> Optional[float]:
        """
        检查指定日期的量比数据
        
        Args:
            session: 数据库会话
            ts_code: 股票代码
            check_date: 检查日期
        
        Returns:
            Optional[float]: 量比值，如果不存在则返回None
        """
        try:
            # 优先从同花顺数据获取
            ths_query = session.query(
                FactTonghuashunLimitUp.volume_ratio
            ).filter(
                FactTonghuashunLimitUp.ts_code == ts_code,
                FactTonghuashunLimitUp.trade_date == check_date
            ).first()
            
            if ths_query and ths_query.volume_ratio is not None:
                return float(ths_query.volume_ratio)
            
            # 降级：从价格表获取
            price_query = session.query(
                FactDailyPriceQfq.volume_ratio
            ).filter(
                FactDailyPriceQfq.ts_code == ts_code,
                FactDailyPriceQfq.trade_date == check_date
            ).first()
            
            if price_query and price_query.volume_ratio is not None:
                return float(price_query.volume_ratio)
            
            return None
        except Exception as e:
            logger.warning(f"查询量比数据失败 {ts_code} {check_date}: {e}")
            return None
    
    def _get_change_pct(self, session: Session, ts_code: str, check_date: date) -> Optional[float]:
        """
        获取指定日期的涨跌幅数据
        
        Args:
            session: 数据库会话
            ts_code: 股票代码
            check_date: 检查日期
        
        Returns:
            Optional[float]: 涨跌幅（%），如果不存在则返回None
        """
        try:
            # 优先从同花顺数据获取
            ths_query = session.query(
                FactTonghuashunLimitUp.change_pct
            ).filter(
                FactTonghuashunLimitUp.ts_code == ts_code,
                FactTonghuashunLimitUp.trade_date == check_date
            ).first()
            
            if ths_query and ths_query.change_pct is not None:
                return float(ths_query.change_pct)
            
            # 降级：从价格表获取
            price_query = session.query(
                FactDailyPriceQfq.change_pct
            ).filter(
                FactDailyPriceQfq.ts_code == ts_code,
                FactDailyPriceQfq.trade_date == check_date
            ).first()
            
            if price_query and price_query.change_pct is not None:
                return float(price_query.change_pct)
            
            return None
        except Exception as e:
            logger.warning(f"查询涨跌幅数据失败 {ts_code} {check_date}: {e}")
            return None
    
    def get_recent_trading_dates(self, session: Session, end_date: date, count: int = 5) -> List[date]:
        """获取最近N个交易日"""
        try:
            # 优先使用交易日历
            query = session.query(DimTradeCalendar.trade_date).filter(
                DimTradeCalendar.trade_date <= end_date,
                DimTradeCalendar.is_open == True
            ).order_by(
                DimTradeCalendar.trade_date.desc()
            ).limit(count)
            
            results = query.all()
            if results:
                dates = sorted([row[0] for row in results])
                return dates
            
            # 降级：从价格表获取
            query = session.query(
                func.distinct(FactDailyPriceQfq.trade_date)
            ).filter(
                FactDailyPriceQfq.trade_date <= end_date
            ).order_by(
                FactDailyPriceQfq.trade_date.desc()
            ).limit(count)
            
            results = query.all()
            dates = sorted([row[0] for row in results])
            return dates
        except Exception as e:
            logger.error(f"获取交易日失败: {e}", exc_info=True)
            # 降级：简单计算（跳过周末）
            dates = []
            current = end_date
            while len(dates) < count:
                if current.weekday() < 5:  # 周一到周五
                    dates.append(current)
                current -= timedelta(days=1)
                if (end_date - current).days > 10:  # 最多往前10天
                    break
            return sorted(dates)
    
    def _fetch_and_save_tonghuashun_data(
        self,
        session: Session,
        ts_codes: List[str],
        trade_date: date,
        completeness_threshold: float = 0.90
    ) -> int:
        """
        从同花顺接口获取涨跌停数据并保存到数据库
        
        Args:
            session: 数据库会话
            ts_codes: 股票代码列表
            trade_date: 交易日期
            completeness_threshold: 数据完整性阈值（0-1之间），默认0.90表示90%
                                   如果完整数据比例达到此阈值，则认为数据完整，不重新获取
        
        Returns:
            int: 保存的记录数
        """
        try:
            # 检查是否已有数据，并且关键字段是否有值
            existing_count = session.query(func.count(FactTonghuashunLimitUp.ts_code)).filter(
                FactTonghuashunLimitUp.trade_date == trade_date,
                FactTonghuashunLimitUp.ts_code.in_(ts_codes)
            ).scalar()
            
            # 检查已有数据的完整性：检查量比字段是否有值
            complete_count = session.query(func.count(FactTonghuashunLimitUp.ts_code)).filter(
                FactTonghuashunLimitUp.trade_date == trade_date,
                FactTonghuashunLimitUp.ts_code.in_(ts_codes),
                FactTonghuashunLimitUp.volume_ratio.isnot(None)  # 量比不为空
            ).scalar()
            
            total_codes = len(ts_codes)
            completeness_ratio = complete_count / total_codes if total_codes > 0 else 0.0
            
            logger.info(f"{trade_date} 数据完整性检查: 已有记录数={existing_count}/{total_codes}, "
                       f"完整记录数（量比不为空）={complete_count}/{total_codes}, "
                       f"完整性比例={completeness_ratio:.2%}, 阈值={completeness_threshold:.2%}")
            
            # 如果记录数完整且完整性比例达到阈值，跳过获取
            if existing_count == total_codes and completeness_ratio >= completeness_threshold:
                logger.info(f"{trade_date} 的同花顺数据已存在且完整（完整性={completeness_ratio:.2%} >= {completeness_threshold:.2%}），跳过获取")
                return existing_count
            
            # 如果记录存在但完整性不足，需要重新获取
            if existing_count > 0:
                logger.info(f"{trade_date} 的同花顺数据不完整（完整性={completeness_ratio:.2%} < {completeness_threshold:.2%}），将重新获取")
            
            # ✅ 检查同花顺接口调用开关
            if not self.config.ENABLE_TONGHUASHUN_API_CALL:
                logger.info(f"⏸️ 同花顺接口调用已暂停（ENABLE_TONGHUASHUN_API_CALL=False），跳过获取 {trade_date} 的数据")
                return existing_count  # 返回已有记录数
            
            # 从同花顺接口获取数据
            trade_date_str = trade_date.strftime('%Y-%m-%d')
            logger.info(f"📥 开始从同花顺获取数据: {len(ts_codes)} 只股票，日期: {trade_date_str}")
            df = self.ths_client.get_limit_up_status_and_volume_ratio(ts_codes, trade_date_str)
            
            if df.empty:
                logger.warning(f"{trade_date} 未获取到同花顺数据")
                return 0
            
            # 检查获取到的字段
            logger.info(f"📊 同花顺返回数据: {len(df)} 条记录，字段: {df.columns.tolist()}")
            if not df.empty:
                # 检查关键字段是否有数据
                sample_row = df.iloc[0]
                logger.info(f"示例数据 - 股票代码: {sample_row.get('ts_code')}, "
                          f"量比: {sample_row.get('volume_ratio')}, "
                          f"股票简称: {sample_row.get('stock_name')}, "
                          f"收盘价: {sample_row.get('close_price')}, "
                          f"涨跌幅: {sample_row.get('change_pct')}")
            
            # 保存到数据库
            logger.info(f"💾 开始保存数据到数据库，共 {len(df)} 条记录")
            saved_count = 0
            skipped_count = 0
            for idx, row in df.iterrows():
                ts_code = row.get('ts_code')
                if not ts_code:
                    skipped_count += 1
                    if skipped_count <= 3:
                        logger.warning(f"  ⚠️ 跳过空股票代码的记录（索引: {idx}）")
                    continue
                
                # 检查是否已存在
                existing = session.query(FactTonghuashunLimitUp).filter(
                    FactTonghuashunLimitUp.ts_code == ts_code,
                    FactTonghuashunLimitUp.trade_date == trade_date
                ).first()
                
                up_and_down_status = str(row.get('up_and_down_status', '')) if pd.notna(row.get('up_and_down_status')) else None
                # 量比：转换为float，如果为NaN则设为None
                volume_ratio_val = row.get('volume_ratio')
                volume_ratio = float(volume_ratio_val) if pd.notna(volume_ratio_val) else None
                
                stock_name = str(row.get('stock_name', '')) if pd.notna(row.get('stock_name')) and str(row.get('stock_name', '')).strip() else None
                # 价格、涨跌幅：如果为NaN则设为None，否则转换为float（允许0值）
                close_price_val = row.get('close_price')
                close_price = float(close_price_val) if pd.notna(close_price_val) else None
                
                change_pct_val = row.get('change_pct')
                change_pct = float(change_pct_val) if pd.notna(change_pct_val) else None
                
                # 调试日志：记录前几条数据的保存情况
                if saved_count < 5:
                    logger.info(f"💾 保存数据 - 股票: {ts_code}, 量比: {volume_ratio}, "
                               f"股票简称: {stock_name}, 收盘价: {close_price}, "
                               f"涨跌幅: {change_pct}")
                
                if existing:
                    # 更新（即使字段已有值也更新，确保数据最新）
                    existing.up_and_down_status = up_and_down_status
                    existing.volume_ratio = volume_ratio
                    existing.stock_name = stock_name
                    existing.close_price = close_price
                    existing.change_pct = change_pct
                    # 记录更新操作
                    if saved_count < 5:
                        logger.info(f"🔄 更新记录 - 股票: {ts_code}, 量比: {volume_ratio}, 收盘价: {close_price}")
                else:
                    # 新增
                    new_record = FactTonghuashunLimitUp(
                        ts_code=ts_code,
                        trade_date=trade_date,
                        up_and_down_status=up_and_down_status,
                        volume_ratio=volume_ratio,
                        stock_name=stock_name,
                        close_price=close_price,
                        change_pct=change_pct
                    )
                    session.add(new_record)
                
                saved_count += 1
            
            session.commit()
            logger.info(f"✅ {trade_date} 保存了 {saved_count} 条同花顺涨跌停数据")
            if skipped_count > 0:
                logger.warning(f"⚠️ {trade_date} 跳过了 {skipped_count} 条空股票代码的记录")
            return saved_count
            
        except Exception as e:
            session.rollback()
            logger.error(f"保存同花顺数据失败 {trade_date}: {e}", exc_info=True)
            return 0
    
    def calculate_limit_up_volume_shrink(self, trade_date: Optional[date] = None) -> List[Dict]:
        """
        计算涨停缩量股票
        
        Args:
            trade_date: 计算日期，如果为None则使用最新交易日
        
        Returns:
            List[Dict]: 符合条件的股票列表
        """
        if trade_date is None:
            trade_date = date.today()
        
        session = self.warehouse.get_session()
        try:
            # 获取最近5个交易日
            recent_dates = self.get_recent_trading_dates(session, trade_date, count=5)
            if not recent_dates:
                logger.warning(f"未找到交易日数据")
                return []
            
            start_date = recent_dates[0]  # 最早的一个交易日
            end_date = recent_dates[-1]  # 最新的一个交易日
            logger.info(f"计算日期: {trade_date}, 最近5个交易日范围: {start_date} 至 {end_date}")
            
            # 1. 从主板池获取股票代码列表
            mainboard_codes = self.universe_service.get_universe_stocks(
                universe_type='mainboard',
                trade_date=None,  # 使用最新的主板池
                active_only=True
            )
            
            if not mainboard_codes:
                logger.warning("⚠️ 主板池为空，请先刷新主板池")
                return []
            
            logger.info(f"从主板池获取到 {len(mainboard_codes)} 只股票代码")
            
            # 2. 从同花顺接口获取最近5个交易日的涨跌停数据并保存到数据库
            # 优化：只主动获取最新一天的数据，前4天的数据应该已经存在（避免重复获取）
            logger.info(f"需要的数据范围：最近5个交易日 {start_date} 至 {end_date}，共 {len(recent_dates)} 个交易日")
            
            # 只主动获取最新一天的数据（end_date），前4天应该已经存在
            # 如果前4天数据不完整（完整性<90%），会在完整性检查时发现并重新获取
            latest_date = end_date
            logger.info(f"📥 主动获取最新一天的数据: {latest_date}")
            saved_count = self._fetch_and_save_tonghuashun_data(session, mainboard_codes, latest_date)
            logger.info(f"✅ {latest_date} 同花顺数据获取完成: {saved_count} 条记录")
            
            # 检查前4天的数据完整性（如果完整性不足90%，会重新获取）
            if len(recent_dates) > 1:
                logger.info(f"🔍 检查前 {len(recent_dates) - 1} 天的数据完整性（如果完整性<90%会自动补充）")
            for trade_date_item in recent_dates[:-1]:  # 排除最新一天
                self._fetch_and_save_tonghuashun_data(session, mainboard_codes, trade_date_item)
            
            # 3. 从数据库查询最近5个交易日内有涨停的主板股票（仅限主板池内的股票）
            # 同花顺的涨跌停状态字段值需要根据实际返回调整（可能是"涨停"、"跌停"等）
            limit_up_query = session.query(
                FactTonghuashunLimitUp.ts_code,
                func.max(FactTonghuashunLimitUp.trade_date).label('limit_up_date')
            ).filter(
                FactTonghuashunLimitUp.trade_date >= start_date,
                FactTonghuashunLimitUp.trade_date <= end_date,
                FactTonghuashunLimitUp.ts_code.in_(mainboard_codes),
                # 过滤涨停股票（状态值需要根据同花顺实际返回调整）
                or_(
                    FactTonghuashunLimitUp.up_and_down_status.like('%涨停%'),
                    FactTonghuashunLimitUp.up_and_down_status == '涨停',
                    FactTonghuashunLimitUp.up_and_down_status == '1'  # 可能需要根据实际值调整
                )
            ).group_by(
                FactTonghuashunLimitUp.ts_code
            )
            
            limit_up_stocks = limit_up_query.all()
            logger.info(f"找到 {len(limit_up_stocks)} 只主板涨停股票（最近5个交易日，主板池范围内）")
            
            # 如果找到股票，打印前几只的代码
            if limit_up_stocks:
                sample_codes = [s.ts_code for s in limit_up_stocks[:5]]
                logger.info(f"示例股票代码: {sample_codes}")
            
            if not limit_up_stocks:
                return []
            
            # 2. 获取这些股票的最新价格和量比数据
            ts_codes = [stock.ts_code for stock in limit_up_stocks]
            
            # 使用计算日期（end_date）来查询同花顺数据，这是最新交易日
            query_trade_date = end_date
            
            logger.info(f"查询量比数据，使用日期: {query_trade_date}")
            
            # 查询最新价格和量比数据
            # 优先使用同花顺的数据（量比、收盘价、成交额、涨跌幅），如果没有则使用价格表的数据
            price_query = session.query(
                FactTonghuashunLimitUp.ts_code,
                FactTonghuashunLimitUp.close_price.label('ths_close'),
                FactTonghuashunLimitUp.change_pct.label('ths_change_pct'),
                FactTonghuashunLimitUp.amount.label('ths_amount'),
                FactTonghuashunLimitUp.volume_ratio.label('ths_volume_ratio'),
                FactDailyPriceQfq.close,
                FactDailyPriceQfq.change_pct,
                FactDailyPriceQfq.amount,
                FactDailyPriceQfq.volume_ratio
            ).outerjoin(
                FactDailyPriceQfq,
                and_(
                    FactTonghuashunLimitUp.ts_code == FactDailyPriceQfq.ts_code,
                    FactDailyPriceQfq.trade_date == query_trade_date
                )
            ).filter(
                FactTonghuashunLimitUp.ts_code.in_(ts_codes),
                FactTonghuashunLimitUp.trade_date == query_trade_date
            )
            
            price_data_raw = price_query.all()
            logger.info(f"查询到 {len(price_data_raw)} 条价格和量比数据（日期: {query_trade_date}）")
            
            # 处理数据：优先使用同花顺的数据，否则使用价格表的数据
            price_data = {}
            skipped_count = 0
            for row in price_data_raw:
                ts_code = row.ts_code
                
                # 优先使用同花顺的量比
                volume_ratio = float(row.ths_volume_ratio) if row.ths_volume_ratio is not None else (
                    float(row.volume_ratio) if row.volume_ratio is not None else None
                )
                
                # 调试日志：记录前几只股票的量比数据
                if len(price_data) < 5:
                    logger.debug(f"股票 {ts_code}: 同花顺量比={row.ths_volume_ratio}, 价格表量比={row.volume_ratio}, 最终量比={volume_ratio}")
                
                # 过滤量比 < 阈值
                if volume_ratio is None or volume_ratio >= self.config.MAINBOARD_VOLUME_RATIO_THRESHOLD:
                    skipped_count += 1
                    continue
                
                # 优先使用同花顺的数据
                close_price = float(row.ths_close) if row.ths_close is not None else (
                    float(row.close) if row.close else 0
                )
                change_pct = float(row.ths_change_pct) if row.ths_change_pct is not None else (
                    float(row.change_pct) if row.change_pct else 0
                )
                # 成交额只从价格表获取（不再从同花顺获取）
                amount = float(row.amount) if row.amount else 0
                
                price_data[ts_code] = {
                    'close': close_price,
                    'change_pct': change_pct,
                    'amount': amount,
                    'volume_ratio': volume_ratio
                }
            
            logger.info(f"找到 {len(price_data)} 只股票量比 < {self.config.MAINBOARD_VOLUME_RATIO_THRESHOLD}（跳过了 {skipped_count} 只量比 >= {self.config.MAINBOARD_VOLUME_RATIO_THRESHOLD} 或为空的股票）")
            
            # 3. 获取股票名称（优先使用同花顺的股票简称，如果没有则从dim_stock获取）
            stock_names = {}
            
            # 先从同花顺数据获取股票名称
            ths_name_query = session.query(
                FactTonghuashunLimitUp.ts_code,
                FactTonghuashunLimitUp.stock_name
            ).filter(
                FactTonghuashunLimitUp.ts_code.in_(ts_codes),
                FactTonghuashunLimitUp.trade_date == query_trade_date,
                FactTonghuashunLimitUp.stock_name.isnot(None)
            )
            for row in ths_name_query.all():
                stock_names[row.ts_code] = row.stock_name
            
            # 如果同花顺没有名称，从dim_stock获取
            missing_codes = [code for code in ts_codes if code not in stock_names]
            if missing_codes:
                stock_query = session.query(
                    DimStock.ts_code,
                    DimStock.name
                ).filter(
                    DimStock.ts_code.in_(missing_codes)
                )
                for row in stock_query.all():
                    if row.ts_code not in stock_names:
                        stock_names[row.ts_code] = row.name
            
            # 4. 组装结果
            results = []
            excluded_limit_down_count = 0
            
            for limit_up_stock in limit_up_stocks:
                ts_code = limit_up_stock.ts_code
                limit_up_date = limit_up_stock.limit_up_date
                
                if ts_code not in price_data:
                    continue
                
                price_info = price_data[ts_code]
                
                # 计算距离涨停天数
                limit_up_days_ago = None
                if limit_up_date and query_trade_date:
                    # 计算交易日差
                    trade_dates_between = session.query(
                        func.count(DimTradeCalendar.trade_date)
                    ).filter(
                        DimTradeCalendar.trade_date > limit_up_date,
                        DimTradeCalendar.trade_date <= query_trade_date,
                        DimTradeCalendar.is_open == True
                    ).scalar()
                    
                    limit_up_days_ago = trade_dates_between if trade_dates_between is not None else 0
                
                # 排除当天涨停且缩量的股票（limit_up_days_ago == 0）
                if limit_up_days_ago == 0:
                    continue
                
                # 检查信号日期（量比日期）当天是否是跌停
                is_signal_date_limit_down = False
                if query_trade_date:
                    # 方法1：通过同花顺的 up_and_down_status 检查信号日期当天是否跌停
                    signal_date_limit_down_query = session.query(
                        FactTonghuashunLimitUp.up_and_down_status,
                        FactTonghuashunLimitUp.change_pct
                    ).filter(
                        FactTonghuashunLimitUp.ts_code == ts_code,
                        FactTonghuashunLimitUp.trade_date == query_trade_date
                    ).first()
                    
                    if signal_date_limit_down_query:
                        # 查询到了数据，检查是否是跌停
                        status = signal_date_limit_down_query.up_and_down_status
                        change_pct_val = signal_date_limit_down_query.change_pct
                        
                        # 优先使用状态字段判断
                        if status:
                            status_str = str(status).strip()
                            # 明确判断：只有状态值完全等于"跌停"或"-1"时才判断为跌停
                            # 注意："非涨跌停"包含"跌停"关键词，但不应该被判断为跌停
                            if status_str == '跌停' or status_str == '-1':
                                is_signal_date_limit_down = True
                            # 如果状态值以"跌停"开头或结尾（排除"非涨跌停"这种情况）
                            elif status_str.startswith('跌停') or status_str.endswith('跌停'):
                                # 但要排除"非涨跌停"这种情况
                                if '非涨跌停' not in status_str and '非跌停' not in status_str:
                                    is_signal_date_limit_down = True
                        
                        # 如果状态字段没有明确标识跌停，再通过涨跌幅判断
                        if not is_signal_date_limit_down and change_pct_val is not None:
                            try:
                                change_pct_float = float(change_pct_val)
                                code_part = ts_code.split('.')[0] if '.' in ts_code else ts_code
                                is_cyb = code_part.startswith('300') or code_part.startswith('688')
                                limit_down_threshold = -19.5 if is_cyb else -9.5
                                if change_pct_float <= limit_down_threshold:
                                    is_signal_date_limit_down = True
                            except (ValueError, TypeError):
                                # 如果转换失败，忽略（不排除）
                                pass
                    # 如果查询不到数据（signal_date_limit_down_query 为 None），不排除（保守策略）
                    
                    # 如果信号日期当天是跌停，排除这个信号
                    if is_signal_date_limit_down:
                        excluded_limit_down_count += 1
                        logger.debug(f"排除股票（信号日期当天跌停）: {ts_code} {stock_names.get(ts_code, '')} "
                                   f"(信号日期: {query_trade_date}, 状态: {signal_date_limit_down_query.up_and_down_status if signal_date_limit_down_query else 'N/A'}, "
                                   f"涨跌幅: {signal_date_limit_down_query.change_pct if signal_date_limit_down_query else 'N/A'}%)")
                        continue
                
                # 检查涨停日期到量比日期之间是否有跌停
                # 【已注释】去掉涨停后到量比0.6之间的跌停限制
                # has_limit_down = False
                # if limit_up_date and query_trade_date and limit_up_date < query_trade_date:
                #     # 查询涨停日期之后到量比日期之间的交易日
                #     trading_dates_between = session.query(
                #         DimTradeCalendar.trade_date
                #     ).filter(
                #         DimTradeCalendar.trade_date > limit_up_date,
                #         DimTradeCalendar.trade_date < query_trade_date,  # 不包括量比日期当天
                #         DimTradeCalendar.is_open == True
                #     ).order_by(DimTradeCalendar.trade_date).all()
                #     
                #     if trading_dates_between:
                #         check_dates = [row[0] for row in trading_dates_between]
                #         
                #         # 方法1：通过同花顺的 up_and_down_status 检查跌停
                #         limit_down_query = session.query(
                #             FactTonghuashunLimitUp.trade_date
                #         ).filter(
                #             FactTonghuashunLimitUp.ts_code == ts_code,
                #             FactTonghuashunLimitUp.trade_date.in_(check_dates),
                #             or_(
                #                 FactTonghuashunLimitUp.up_and_down_status.like('%跌停%'),
                #                 FactTonghuashunLimitUp.up_and_down_status == '跌停',
                #                 FactTonghuashunLimitUp.up_and_down_status == '-1'  # 可能需要根据实际值调整
                #             )
                #         ).first()
                #         
                #         if limit_down_query:
                #             has_limit_down = True
                #             excluded_limit_down_count += 1
                #             logger.debug(f"排除股票（中间有跌停）: {ts_code} {stock_names.get(ts_code, '')} "
                #                        f"(涨停日期: {limit_up_date}, 跌停日期: {limit_down_query.trade_date})")
                #         else:
                #             # 方法2：通过 change_pct 检查跌停（如果同花顺状态数据缺失）
                #             # 判断是否创业板/科创板（300开头或688开头）
                #             code_part = ts_code.split('.')[0] if '.' in ts_code else ts_code
                #             is_cyb = code_part.startswith('300') or code_part.startswith('688')
                #             limit_down_threshold = -19.5 if is_cyb else -9.5  # 创业板/科创板 -19.5%，主板 -9.5%
                #             
                #             limit_down_by_pct_query = session.query(
                #                 FactTonghuashunLimitUp.trade_date,
                #                 FactTonghuashunLimitUp.change_pct
                #             ).filter(
                #                 FactTonghuashunLimitUp.ts_code == ts_code,
                #                 FactTonghuashunLimitUp.trade_date.in_(check_dates),
                #                 FactTonghuashunLimitUp.change_pct.isnot(None),
                #                 FactTonghuashunLimitUp.change_pct <= limit_down_threshold
                #             ).first()
                #             
                #             if limit_down_by_pct_query:
                #                 has_limit_down = True
                #                 excluded_limit_down_count += 1
                #                 logger.debug(f"排除股票（中间有跌停，通过涨跌幅判断）: {ts_code} {stock_names.get(ts_code, '')} "
                #                            f"(涨停日期: {limit_up_date}, 跌停日期: {limit_down_by_pct_query.trade_date}, "
                #                            f"涨跌幅: {limit_down_by_pct_query.change_pct}%)")
                # 
                # # 如果中间有跌停，排除这个信号
                # if has_limit_down:
                #     continue
                
                results.append({
                    'ts_code': ts_code,
                    'stock_name': stock_names.get(ts_code, ''),
                    'limit_up_date': limit_up_date.isoformat() if limit_up_date else None,
                    'limit_up_days_ago': limit_up_days_ago,
                    'volume_ratio': price_info['volume_ratio'],
                    'today_close': price_info['close'],
                    'today_change_pct': price_info['change_pct'],
                    'today_amount': price_info['amount']
                })
            
            # 【已注释】去掉涨停后到量比0.6之间的跌停限制
            # if excluded_limit_down_count > 0:
            #     logger.info(f"排除 {excluded_limit_down_count} 只股票（涨停后到量比日期之间有跌停）")
            
            logger.info(f"✅ 计算完成，共找到 {len(results)} 只符合条件的股票")
            return results
            
        except Exception as e:
            logger.error(f"计算涨停缩量股票失败: {e}", exc_info=True)
            return []
        finally:
            session.close()
    
    def save_results(self, trade_date: date, results: List[Dict]) -> int:
        """
        保存计算结果到数据库
        
        Args:
            trade_date: 计算日期
            results: 计算结果列表
        
        Returns:
            int: 保存的记录数
        """
        session = self.warehouse.get_session()
        try:
            saved_count = 0
            
            for result in results:
                # 检查是否已存在（仅限主板策略）
                existing = session.query(FactLimitUpVolumeShrink).filter(
                    FactLimitUpVolumeShrink.trade_date == trade_date,
                    FactLimitUpVolumeShrink.ts_code == result['ts_code'],
                    FactLimitUpVolumeShrink.strategy_type == 'mainboard_limit_up'
                ).first()
                
                limit_up_date = datetime.strptime(result['limit_up_date'], '%Y-%m-%d').date() if result.get('limit_up_date') else None
                
                if existing:
                    # 更新
                    existing.stock_name = result.get('stock_name', '')
                    existing.limit_up_date = limit_up_date
                    existing.limit_up_days_ago = result.get('limit_up_days_ago')
                    existing.volume_ratio = result.get('volume_ratio')
                    existing.today_close = result.get('today_close')
                    existing.today_change_pct = result.get('today_change_pct')
                    existing.today_amount = result.get('today_amount')
                    # 确保策略类型正确
                    if not existing.strategy_type:
                        existing.strategy_type = 'mainboard_limit_up'
                else:
                    # 新增
                    new_record = FactLimitUpVolumeShrink(
                        trade_date=trade_date,
                        ts_code=result['ts_code'],
                        stock_name=result.get('stock_name', ''),
                        strategy_type='mainboard_limit_up',
                        limit_up_date=limit_up_date,
                        limit_up_days_ago=result.get('limit_up_days_ago'),
                        volume_ratio=result.get('volume_ratio'),
                        today_close=result.get('today_close'),
                        today_change_pct=result.get('today_change_pct'),
                        today_amount=result.get('today_amount')
                    )
                    session.add(new_record)
                
                saved_count += 1
            
            session.commit()
            logger.info(f"✅ 保存了 {saved_count} 条记录到数据库")
            return saved_count
            
        except Exception as e:
            session.rollback()
            logger.error(f"保存计算结果失败: {e}", exc_info=True)
            return 0
        finally:
            session.close()
    
    def calculate_cyb_rise_shrink(self, trade_date: Optional[date] = None) -> List[Dict]:
        """
        计算创业板科创板涨幅缩量股票
        查找涨幅>=8%的股票，然后查找该股票第二天或第三天量比<0.7的股票（任意一天满足即可）
        
        Args:
            trade_date: 计算日期，如果为None则使用最新交易日
        
        Returns:
            List[Dict]: 符合条件的股票列表
        """
        if trade_date is None:
            trade_date = date.today()
        
        session = self.warehouse.get_session()
        try:
            # 获取最近5个交易日
            recent_dates = self.get_recent_trading_dates(session, trade_date, count=5)
            if not recent_dates:
                logger.warning(f"未找到交易日数据")
                return []
            
            start_date = recent_dates[0]  # 最早的一个交易日
            end_date = recent_dates[-1]  # 最新的一个交易日
            logger.info(f"计算日期: {trade_date}, 最近5个交易日范围: {start_date} 至 {end_date}")
            
            # 1. 获取创业板和科创板股票代码列表
            cyb_codes = self._get_cyb_stock_codes(session)
            if not cyb_codes:
                logger.warning("⚠️ 创业板/科创板股票池为空")
                return []
            
            logger.info(f"从股票池获取到 {len(cyb_codes)} 只创业板/科创板股票代码")
            
            # 2. 先从同花顺API获取最近5个交易日的数据（类似主板策略）
            logger.info("📥 开始从同花顺获取创业板/科创板数据...")
            logger.info(f"📋 股票代码样本（前10只）: {cyb_codes[:10]}")
            logger.info(f"📋 总共需要获取 {len(cyb_codes)} 只股票的数据")
            for trade_date_item in recent_dates:
                logger.info(f"📅 开始获取日期 {trade_date_item} 的数据...")
                saved_count = self._fetch_and_save_tonghuashun_data(session, cyb_codes, trade_date_item)
                logger.info(f"  ✅ {trade_date_item}: 保存了 {saved_count} 条记录")
                if saved_count == 0:
                    logger.warning(f"  ⚠️ {trade_date_item}: 未保存任何数据，请检查同花顺API返回")
            
            # 3. 从 FactTonghuashunLimitUp 表查找最近5个交易日内涨幅>=8%的股票
            logger.info("🔍 从同花顺数据表查询涨幅>=8%的股票...")
            rise_query = session.query(
                FactTonghuashunLimitUp.ts_code,
                FactTonghuashunLimitUp.trade_date.label('rise_date'),
                FactTonghuashunLimitUp.change_pct,
                FactTonghuashunLimitUp.close_price
            ).filter(
                FactTonghuashunLimitUp.trade_date >= start_date,
                FactTonghuashunLimitUp.trade_date <= end_date,
                FactTonghuashunLimitUp.ts_code.in_(cyb_codes),
                FactTonghuashunLimitUp.change_pct.isnot(None),  # 排除NULL值
                FactTonghuashunLimitUp.change_pct >= self.config.CYB_RISE_THRESHOLD  # 涨幅>=8%
            ).order_by(
                FactTonghuashunLimitUp.ts_code,
                FactTonghuashunLimitUp.trade_date.desc()
            )
            
            rise_stocks_raw = rise_query.all()
            logger.info(f"找到 {len(rise_stocks_raw)} 只创业板/科创板股票涨幅>=8%（最近5个交易日）")
            
            # 3.1. 筛选：检查涨幅>=8%的股票是否满足"当前收盘价 >= 30日最高收盘价的95%"
            logger.info("🔍 检查涨幅>=8%的股票是否满足30日最高价条件...")
            rise_stocks = []
            filtered_by_30d_high_count = 0
            
            for rise_stock in rise_stocks_raw:
                ts_code = rise_stock.ts_code
                rise_date = rise_stock.rise_date
                current_close = float(rise_stock.close_price) if rise_stock.close_price else None
                
                if current_close is None or current_close <= 0:
                    filtered_by_30d_high_count += 1
                    if filtered_by_30d_high_count <= 5:
                        logger.debug(f"  ⚠️ {ts_code} {rise_date} 收盘价无效，跳过")
                    continue
                
                # 计算30日最高收盘价（从rise_date往前推30个交易日）
                # 查询30个交易日前的日期
                trade_dates_query = session.query(
                    FactDailyPriceQfq.trade_date
                ).filter(
                    FactDailyPriceQfq.ts_code == ts_code,
                    FactDailyPriceQfq.trade_date <= rise_date
                ).order_by(
                    FactDailyPriceQfq.trade_date.desc()
                ).limit(self.config.CYB_30D_DAYS)
                
                trade_dates_list = [row[0] for row in trade_dates_query.all()]
                if len(trade_dates_list) < self.config.CYB_30D_DAYS:
                    # 如果不足30个交易日，使用所有可用数据
                    if len(trade_dates_list) == 0:
                        filtered_by_30d_high_count += 1
                        if filtered_by_30d_high_count <= 5:
                            logger.debug(f"  ⚠️ {ts_code} {rise_date} 无历史数据，跳过")
                        continue
                    date_range_start = trade_dates_list[-1]
                else:
                    date_range_start = trade_dates_list[-1]
                
                # 查询30日内的最高收盘价
                max_close_30d = session.query(
                    func.max(FactDailyPriceQfq.close)
                ).filter(
                    FactDailyPriceQfq.ts_code == ts_code,
                    FactDailyPriceQfq.trade_date >= date_range_start,
                    FactDailyPriceQfq.trade_date <= rise_date,
                    FactDailyPriceQfq.close.isnot(None),
                    FactDailyPriceQfq.close > 0
                ).scalar()
                
                if max_close_30d is None or max_close_30d <= 0:
                    filtered_by_30d_high_count += 1
                    if filtered_by_30d_high_count <= 5:
                        logger.debug(f"  ⚠️ {ts_code} {rise_date} 无法获取30日最高收盘价，跳过")
                    continue
                
                max_close_30d = float(max_close_30d)
                threshold_95pct = max_close_30d * self.config.CYB_30D_HIGH_THRESHOLD
                
                # 检查当前收盘价是否 >= 30日最高收盘价的95%
                if current_close < threshold_95pct:
                    filtered_by_30d_high_count += 1
                    if filtered_by_30d_high_count <= 5:
                        logger.debug(f"  ⚠️ {ts_code} {rise_date} 收盘价({current_close:.2f}) < 30日最高价95%({threshold_95pct:.2f}, 最高价={max_close_30d:.2f})，跳过")
                    continue
                
                # 满足条件，保留
                rise_stocks.append(rise_stock)
                if len(rise_stocks) <= 5:
                    logger.info(f"  ✅ {ts_code} {rise_date} 收盘价({current_close:.2f}) >= 30日最高价95%({threshold_95pct:.2f}, 最高价={max_close_30d:.2f})，符合条件")
            
            logger.info(f"📊 30日最高价筛选：原始 {len(rise_stocks_raw)} 只，过滤后剩余 {len(rise_stocks)} 只（排除了 {filtered_by_30d_high_count} 只）")
            
            # 如果找到股票，打印前几条作为调试信息
            if rise_stocks:
                logger.info("前5条满足30日最高价条件的股票:")
                for i, stock in enumerate(rise_stocks[:5]):
                    logger.info(f"  {i+1}. {stock.ts_code}, 日期: {stock.rise_date}, 涨幅: {stock.change_pct}%")
            
            if not rise_stocks:
                logger.info("未找到满足30日最高价条件的股票")
                return []
            
            # 4. 收集所有需要检查量比的日期（第2天和第3天），并提前获取数据
            dates_to_fetch = set()
            for rise_stock in rise_stocks:
                rise_date = rise_stock.rise_date
                next_dates = self._get_next_trading_dates(session, rise_date, count=3)
                if len(next_dates) >= 1:
                    day2_date = next_dates[0]  # 第2个交易日（第二天）
                    if day2_date and day2_date <= end_date:
                        dates_to_fetch.add(day2_date)
                if len(next_dates) >= 2:
                    day3_date = next_dates[1]  # 第3个交易日（第三天）
                    if day3_date and day3_date <= end_date:
                        dates_to_fetch.add(day3_date)
            
            # 获取这些日期的同花顺数据（如果还没有获取）
            dates_to_fetch = dates_to_fetch - set(recent_dates)  # 排除已经获取的日期
            if dates_to_fetch:
                logger.info(f"📥 需要额外获取 {len(dates_to_fetch)} 个日期的数据: {sorted(dates_to_fetch)}")
                for fetch_date in dates_to_fetch:
                    saved_count = self._fetch_and_save_tonghuashun_data(session, cyb_codes, fetch_date)
                    logger.info(f"  {fetch_date}: 保存了 {saved_count} 条记录")
            
            # 5. 对每个涨幅>=8%的股票，检查第2天或第3天的量比和跌幅（任意一天满足条件即可）
            results = []
            signal_date_to_rise_map = {}  # 用于去重：信号日期 -> (ts_code, rise_date)
            
            checked_count = 0
            excluded_by_decline_count = 0  # 因跌幅过大被排除的数量
            excluded_by_missing_change_pct_count = 0  # 因涨跌幅数据缺失被排除的数量
            qualified_stocks = []  # 记录所有符合条件的股票，用于最后打印
            
            for rise_stock in rise_stocks:
                ts_code = rise_stock.ts_code
                rise_date = rise_stock.rise_date  # 使用查询中label的字段名
                
                # 获取第2个和第3个交易日
                next_dates = self._get_next_trading_dates(session, rise_date, count=3)
                if len(next_dates) < 1:
                    continue  # 如果后续交易日不足1天，跳过
                
                day2_date = next_dates[0] if len(next_dates) > 0 else None  # 第2个交易日（第二天）
                day3_date = next_dates[1] if len(next_dates) > 1 else None  # 第3个交易日（第三天）
                
                # 检查第2天或第3天的量比和跌幅
                signal_date = None
                rise_days_ago = None
                volume_ratio = None
                day2_volume_ratio = None
                day2_change_pct = None
                
                # 先检查第2天
                if day2_date and day2_date <= end_date:
                    day2_volume_ratio = self._check_volume_ratio(session, ts_code, day2_date)
                    # 获取第2天的涨跌幅
                    day2_change_pct = self._get_change_pct(session, ts_code, day2_date)
                    # 检查量比和跌幅条件：量比<阈值 且 跌幅不能大于10%（即 change_pct >= -10）
                    # 注意：如果涨跌幅数据缺失（None），则排除该股票
                    if day2_volume_ratio is not None:
                        checked_count += 1
                        if day2_volume_ratio < self.config.CYB_VOLUME_RATIO_THRESHOLD_REALTIME:
                            if day2_change_pct is not None and day2_change_pct >= self.config.CYB_DECLINE_THRESHOLD:
                                # 第2天满足量比和跌幅条件，直接标记为符合条件，不再检查第3天
                                signal_date = day2_date
                                rise_days_ago = 2
                                volume_ratio = day2_volume_ratio
                                qualified_stocks.append((ts_code, rise_date, day2_date, day2_volume_ratio, day2_change_pct, 2))
                                if checked_count <= 5:
                                    logger.info(f"  ✅ {ts_code} {rise_date} 第2天({day2_date})量比={day2_volume_ratio:.2f} < 0.7，涨跌幅={day2_change_pct:.2f}%，符合条件")
                            else:
                                if day2_change_pct is None:
                                    excluded_by_missing_change_pct_count += 1
                                    if checked_count <= 5:
                                        logger.debug(f"  ⚠️ {ts_code} {rise_date} 第2天({day2_date})量比={day2_volume_ratio:.2f} < 0.7，但涨跌幅数据缺失，排除")
                                else:
                                    excluded_by_decline_count += 1
                                    if checked_count <= 5:
                                        logger.debug(f"  ⚠️ {ts_code} {rise_date} 第2天({day2_date})量比={day2_volume_ratio:.2f} < 0.7，但跌幅={day2_change_pct:.2f}% > 10%，排除")
                        else:
                            # 量比>=0.7，不满足条件，但也打印信息
                            if checked_count <= 5:
                                day2_change_pct_str = f"{day2_change_pct:.2f}%" if day2_change_pct is not None else "数据缺失"
                                logger.info(f"  ⚠️ {ts_code} {rise_date} 第2天({day2_date})量比={day2_volume_ratio:.2f} >= {self.config.CYB_VOLUME_RATIO_THRESHOLD_REALTIME}，涨跌幅={day2_change_pct_str}，不满足条件")
                
                # 如果第2天不满足条件，才检查第3天
                if signal_date is None and day3_date and day3_date <= end_date:
                    day3_volume_ratio = self._check_volume_ratio(session, ts_code, day3_date)
                    # 获取第3天的涨跌幅
                    day3_change_pct = self._get_change_pct(session, ts_code, day3_date)
                    
                    if day3_volume_ratio is not None:
                        # 如果第2天没有检查（没有量比数据），这里才增加计数
                        if day2_volume_ratio is None:
                            checked_count += 1
                        if day3_volume_ratio < self.config.CYB_VOLUME_RATIO_THRESHOLD_REALTIME:
                            if day3_change_pct is not None and day3_change_pct >= self.config.CYB_DECLINE_THRESHOLD:
                                # 第3天满足量比和跌幅条件，但还要检查第2天的跌幅
                                # 如果第2天跌幅>10%，也要排除
                                if day2_change_pct is not None and day2_change_pct < self.config.CYB_DECLINE_THRESHOLD:
                                    excluded_by_decline_count += 1
                                    if checked_count <= 5:
                                        logger.debug(f"  ⚠️ {ts_code} {rise_date} 第3天({day3_date})量比={day3_volume_ratio:.2f} < 0.7，涨跌幅={day3_change_pct:.2f}%，但第2天({day2_date})跌幅={day2_change_pct:.2f}% > 10%，排除")
                                else:
                                    # 第2天跌幅<=10%（或数据缺失），第3天满足条件，符合要求
                                    signal_date = day3_date
                                    rise_days_ago = 3
                                    volume_ratio = day3_volume_ratio
                                    qualified_stocks.append((ts_code, rise_date, day3_date, day3_volume_ratio, day3_change_pct, 3))
                                    # 显示所有符合条件的股票（不限制数量）
                                    logger.info(f"  ✅ {ts_code} {rise_date} 第3天({day3_date})量比={day3_volume_ratio:.2f} < 0.7，涨跌幅={day3_change_pct:.2f}%，符合条件")
                            else:
                                if day3_change_pct is None:
                                    excluded_by_missing_change_pct_count += 1
                                    if checked_count <= 5:
                                        logger.debug(f"  ⚠️ {ts_code} {rise_date} 第3天({day3_date})量比={day3_volume_ratio:.2f} < 0.7，但涨跌幅数据缺失，排除")
                                else:
                                    excluded_by_decline_count += 1
                                    if checked_count <= 5:
                                        logger.debug(f"  ⚠️ {ts_code} {rise_date} 第3天({day3_date})量比={day3_volume_ratio:.2f} < 0.7，但跌幅={day3_change_pct:.2f}% > 10%，排除")
                        elif checked_count <= 5:
                            # 量比>=0.7，不满足条件，但也打印信息
                            day3_change_pct_str = f"{day3_change_pct:.2f}%" if day3_change_pct is not None else "数据缺失"
                            logger.info(f"  ⚠️ {ts_code} {rise_date} 第3天({day3_date})量比={day3_volume_ratio:.2f} >= {self.config.CYB_VOLUME_RATIO_THRESHOLD_REALTIME}，涨跌幅={day3_change_pct_str}，不满足条件")
                
                # 如果找到信号，记录
                if signal_date is not None:
                    # 去重：同一只股票在同一信号日期只记录一次（取最近的涨幅日期）
                    signal_key = (signal_date, ts_code)
                    if signal_key not in signal_date_to_rise_map:
                        signal_date_to_rise_map[signal_key] = (ts_code, rise_date, rise_days_ago, volume_ratio)
                    else:
                        # 如果已存在，比较涨幅日期，保留最近的
                        existing_rise_date = signal_date_to_rise_map[signal_key][1]
                        if rise_date > existing_rise_date:
                            signal_date_to_rise_map[signal_key] = (ts_code, rise_date, rise_days_ago, volume_ratio)
            
            # 输出统计信息
            logger.info(f"📊 量比和跌幅检查统计: 总涨幅>=8%股票={len(rise_stocks)}, "
                       f"已检查量比={checked_count}, "
                       f"因跌幅>10%排除={excluded_by_decline_count}, "
                       f"因涨跌幅数据缺失排除={excluded_by_missing_change_pct_count}, "
                       f"符合条件的股票={len(signal_date_to_rise_map)}")
            
            # 打印所有符合条件的股票详情
            if qualified_stocks:
                logger.info(f"📋 所有符合条件的股票详情（共{len(qualified_stocks)}只）:")
                for ts_code, rise_date, signal_date, vol_ratio, change_pct, days_ago in qualified_stocks:
                    logger.info(f"  ✅ {ts_code} 涨幅日期={rise_date}, 信号日期={signal_date}, 第{days_ago}天, 量比={vol_ratio:.2f}, 涨跌幅={change_pct:.2f}%")
            
            # 5. 获取信号日期的价格和股票名称数据
            if not signal_date_to_rise_map:
                logger.info(f"未找到符合条件的股票（第2天或第3天量比<{self.config.CYB_VOLUME_RATIO_THRESHOLD_REALTIME}且跌幅<={abs(self.config.CYB_DECLINE_THRESHOLD)}%）")
                return []
            
            # 获取所有信号日期和股票代码
            signal_dates = list(set([key[0] for key in signal_date_to_rise_map.keys()]))
            signal_ts_codes = list(set([value[0] for value in signal_date_to_rise_map.values()]))
            
            # 批量查询价格数据
            price_data = {}
            for signal_date_item in signal_dates:
                price_query = session.query(
                    FactTonghuashunLimitUp.ts_code,
                    FactTonghuashunLimitUp.close_price.label('ths_close'),
                    FactTonghuashunLimitUp.change_pct.label('ths_change_pct'),
                    FactDailyPriceQfq.close,
                    FactDailyPriceQfq.change_pct,
                    FactDailyPriceQfq.amount
                ).outerjoin(
                    FactDailyPriceQfq,
                    and_(
                        FactTonghuashunLimitUp.ts_code == FactDailyPriceQfq.ts_code,
                        FactDailyPriceQfq.trade_date == signal_date_item
                    )
                ).filter(
                    FactTonghuashunLimitUp.ts_code.in_(signal_ts_codes),
                    FactTonghuashunLimitUp.trade_date == signal_date_item
                )
                
                for row in price_query.all():
                    ts_code = row.ts_code
                    if ts_code not in price_data:
                        price_data[ts_code] = {}
                    
                    close_price = float(row.ths_close) if row.ths_close is not None else (
                        float(row.close) if row.close else 0
                    )
                    change_pct = float(row.ths_change_pct) if row.ths_change_pct is not None else (
                        float(row.change_pct) if row.change_pct else 0
                    )
                    amount = float(row.amount) if row.amount else 0
                    
                    price_data[ts_code][signal_date_item] = {
                        'close': close_price,
                        'change_pct': change_pct,
                        'amount': amount
                    }
            
            # 获取股票名称
            stock_names = {}
            name_query = session.query(
                DimStock.ts_code,
                DimStock.name
            ).filter(
                DimStock.ts_code.in_(signal_ts_codes)
            )
            
            for row in name_query.all():
                stock_names[row.ts_code] = row.name if row.name else ''
            
            # 6. 构建结果列表
            for (signal_date_item, ts_code), (_, rise_date, rise_days_ago, volume_ratio) in signal_date_to_rise_map.items():
                price_info = price_data.get(ts_code, {}).get(signal_date_item, {})
                
                results.append({
                    'ts_code': ts_code,
                    'stock_name': stock_names.get(ts_code, ''),
                    'limit_up_date': rise_date.isoformat() if rise_date else None,  # 存储涨幅>=8%的日期
                    'limit_up_days_ago': rise_days_ago,  # 距离涨幅>=10%的天数（2或3）
                    'volume_ratio': volume_ratio,
                    'today_close': price_info.get('close', 0),
                    'today_change_pct': price_info.get('change_pct', 0),
                    'today_amount': price_info.get('amount', 0),
                    'signal_date': signal_date_item.isoformat()  # 信号日期（量比<0.6的日期）
                })
            
            logger.info(f"✅ 计算完成，共找到 {len(results)} 只符合条件的股票")
            return results
            
        except Exception as e:
            logger.error(f"计算创业板科创板涨幅缩量股票失败: {e}", exc_info=True)
            return []
        finally:
            session.close()
    
    def calculate_cyb_rise_shrink_from_qfq(self, start_date: date, end_date: date) -> int:
        """
        从 fact_daily_price_qfq 表计算创业板科创板涨幅缩量股票（批量计算）
        查找涨幅>=8%的股票，然后查找该股票第二天或第三天量比<0.7的股票（任意一天满足即可）
        
        Args:
            start_date: 开始日期
            end_date: 结束日期
        
        Returns:
            int: 保存的记录数
        """
        session = self.warehouse.get_session()
        try:
            # 1. 获取创业板和科创板股票代码列表
            cyb_codes = self._get_cyb_stock_codes(session)
            if not cyb_codes:
                logger.warning("⚠️ 创业板/科创板股票池为空")
                return 0
            
            logger.info(f"📊 开始批量计算创业板/科创板涨幅缩量数据：{start_date} 至 {end_date}")
            logger.info(f"从股票池获取到 {len(cyb_codes)} 只创业板/科创板股票代码")
            
            # 2. 从 fact_daily_price_qfq 表查找日期范围内涨幅>=8%的股票
            logger.info("🔍 从 fact_daily_price_qfq 表查询涨幅>=8%的股票...")
            rise_query = session.query(
                FactDailyPriceQfq.ts_code,
                FactDailyPriceQfq.trade_date.label('rise_date'),
                FactDailyPriceQfq.change_pct,
                FactDailyPriceQfq.close
            ).filter(
                FactDailyPriceQfq.trade_date >= start_date,
                FactDailyPriceQfq.trade_date <= end_date,
                FactDailyPriceQfq.ts_code.in_(cyb_codes),
                FactDailyPriceQfq.change_pct.isnot(None),
                FactDailyPriceQfq.change_pct >= self.config.CYB_RISE_THRESHOLD
            ).order_by(
                FactDailyPriceQfq.ts_code,
                FactDailyPriceQfq.trade_date.desc()
            )
            
            rise_stocks_raw = rise_query.all()
            logger.info(f"找到 {len(rise_stocks_raw)} 只创业板/科创板股票涨幅>=8%")
            
            if not rise_stocks_raw:
                logger.info("未找到涨幅>=8%的股票")
                return 0
            
            # 2.1. 筛选：检查涨幅>=8%的股票是否满足"当前收盘价 >= 30日最高收盘价的95%"
            logger.info("🔍 检查涨幅>=8%的股票是否满足30日最高价条件...")
            from sqlalchemy import func
            rise_stocks = []
            filtered_by_30d_high_count = 0
            
            for rise_stock in rise_stocks_raw:
                ts_code = rise_stock.ts_code
                rise_date = rise_stock.rise_date
                current_close = float(rise_stock.close) if rise_stock.close else None
                
                if current_close is None or current_close <= 0:
                    filtered_by_30d_high_count += 1
                    if filtered_by_30d_high_count <= 5:
                        logger.debug(f"  ⚠️ {ts_code} {rise_date} 收盘价无效，跳过")
                    continue
                
                # 计算30日最高收盘价（从rise_date往前推30个交易日）
                # 获取30个交易日前的日期
                thirty_days_ago_date = None
                # 查询30个交易日前的日期
                trade_dates_query = session.query(
                    FactDailyPriceQfq.trade_date
                ).filter(
                    FactDailyPriceQfq.ts_code == ts_code,
                    FactDailyPriceQfq.trade_date <= rise_date
                ).order_by(
                    FactDailyPriceQfq.trade_date.desc()
                ).limit(self.config.CYB_30D_DAYS)
                
                trade_dates_list = [row[0] for row in trade_dates_query.all()]
                if len(trade_dates_list) < self.config.CYB_30D_DAYS:
                    # 如果不足30个交易日，使用所有可用数据
                    if len(trade_dates_list) == 0:
                        filtered_by_30d_high_count += 1
                        if filtered_by_30d_high_count <= 5:
                            logger.debug(f"  ⚠️ {ts_code} {rise_date} 无历史数据，跳过")
                        continue
                    date_range_start = trade_dates_list[-1]
                else:
                    date_range_start = trade_dates_list[-1]
                
                # 查询30日内的最高收盘价
                max_close_30d = session.query(
                    func.max(FactDailyPriceQfq.close)
                ).filter(
                    FactDailyPriceQfq.ts_code == ts_code,
                    FactDailyPriceQfq.trade_date >= date_range_start,
                    FactDailyPriceQfq.trade_date <= rise_date,
                    FactDailyPriceQfq.close.isnot(None),
                    FactDailyPriceQfq.close > 0
                ).scalar()
                
                if max_close_30d is None or max_close_30d <= 0:
                    filtered_by_30d_high_count += 1
                    if filtered_by_30d_high_count <= 5:
                        logger.debug(f"  ⚠️ {ts_code} {rise_date} 无法获取30日最高收盘价，跳过")
                    continue
                
                max_close_30d = float(max_close_30d)
                threshold_95pct = max_close_30d * 0.95
                
                # 检查当前收盘价是否 >= 30日最高收盘价的95%
                if current_close < threshold_95pct:
                    filtered_by_30d_high_count += 1
                    if filtered_by_30d_high_count <= 5:
                        logger.debug(f"  ⚠️ {ts_code} {rise_date} 收盘价({current_close:.2f}) < 30日最高价95%({threshold_95pct:.2f}, 最高价={max_close_30d:.2f})，跳过")
                    continue
                
                # 满足条件，保留
                rise_stocks.append(rise_stock)
                if len(rise_stocks) <= 5:
                    logger.info(f"  ✅ {ts_code} {rise_date} 收盘价({current_close:.2f}) >= 30日最高价95%({threshold_95pct:.2f}, 最高价={max_close_30d:.2f})，符合条件")
            
            logger.info(f"📊 30日最高价筛选：原始 {len(rise_stocks_raw)} 只，过滤后剩余 {len(rise_stocks)} 只（排除了 {filtered_by_30d_high_count} 只）")
            
            if not rise_stocks:
                logger.info("未找到满足30日最高价条件的股票")
                return 0
            
            # 3. 收集所有需要检查量比的日期和股票代码（第2天和第3天）
            dates_to_check = {}  # {date: set(ts_codes)}
            for rise_stock in rise_stocks:
                ts_code = rise_stock.ts_code
                rise_date = rise_stock.rise_date
                
                # 获取第2个和第3个交易日
                next_dates = self._get_next_trading_dates(session, rise_date, count=3)
                if len(next_dates) < 1:
                    continue
                
                day2_date = next_dates[0] if len(next_dates) > 0 else None  # 第2个交易日（第二天）
                day3_date = next_dates[1] if len(next_dates) > 1 else None  # 第3个交易日（第三天）
                
                if day2_date and day2_date <= end_date:
                    if day2_date not in dates_to_check:
                        dates_to_check[day2_date] = set()
                    dates_to_check[day2_date].add(ts_code)
                
                if day3_date and day3_date <= end_date:
                    if day3_date not in dates_to_check:
                        dates_to_check[day3_date] = set()
                    dates_to_check[day3_date].add(ts_code)
            
            # 4. 批量从同花顺API获取量比数据（如果qfq表中没有）并保存到数据库
            ths_volume_ratio_cache = {}  # {(ts_code, date): volume_ratio}
            if dates_to_check and self.ths_client.available:
                logger.info(f"📥 开始从同花顺API批量获取量比数据，共 {len(dates_to_check)} 个日期")
                for check_date, ts_codes_list in dates_to_check.items():
                    ts_codes = list(ts_codes_list)
                    if not ts_codes:
                        continue
                    
                    # 先检查qfq表中哪些股票没有量比数据
                    qfq_query = session.query(
                        FactDailyPriceQfq.ts_code,
                        FactDailyPriceQfq.volume_ratio,
                        FactDailyPriceQfq.vol,
                        FactDailyPriceQfq.avg_volume_5
                    ).filter(
                        FactDailyPriceQfq.ts_code.in_(ts_codes),
                        FactDailyPriceQfq.trade_date == check_date
                    ).all()
                    
                    # 找出需要从API获取量比的股票（qfq表中量比为NULL且无法计算）
                    need_api_codes = []
                    for qfq_row in qfq_query:
                        ts_code = qfq_row.ts_code
                        if qfq_row.volume_ratio is None:
                            # 尝试计算
                            if qfq_row.vol is None or qfq_row.avg_volume_5 is None or qfq_row.avg_volume_5 <= 0:
                                need_api_codes.append(ts_code)
                    
                    # 如果qfq表中没有数据的股票，也需要从API获取
                    qfq_has_codes = {row.ts_code for row in qfq_query}
                    missing_codes = set(ts_codes) - qfq_has_codes
                    need_api_codes.extend(missing_codes)
                    
                    if need_api_codes:
                        logger.info(f"  📅 {check_date}: 需要从API获取 {len(need_api_codes)} 只股票的量比数据")
                        try:
                            # 使用 _fetch_and_save_tonghuashun_data 方法获取并保存到数据库
                            # 设置 completeness_threshold=0.0 确保即使已有记录但量比为NULL也会重新获取
                            saved_count = self._fetch_and_save_tonghuashun_data(
                                session, 
                                need_api_codes, 
                                check_date, 
                                completeness_threshold=0.0
                            )
                            logger.info(f"  ✅ {check_date}: 从API获取并保存了 {saved_count} 条记录到数据库")
                            
                            # 同时更新缓存，以便后续查询使用
                            ths_query = session.query(
                                FactTonghuashunLimitUp.ts_code,
                                FactTonghuashunLimitUp.volume_ratio
                            ).filter(
                                FactTonghuashunLimitUp.ts_code.in_(need_api_codes),
                                FactTonghuashunLimitUp.trade_date == check_date,
                                FactTonghuashunLimitUp.volume_ratio.isnot(None)
                            ).all()
                            
                            for ths_row in ths_query:
                                ths_volume_ratio_cache[(ths_row.ts_code, check_date)] = float(ths_row.volume_ratio)
                            
                            if ths_query:
                                logger.info(f"  ✅ {check_date}: 更新缓存，共 {len(ths_query)} 条量比数据")
                        except Exception as e:
                            logger.warning(f"  ⚠️ {check_date}: 从同花顺API获取量比失败: {e}")
            
            # 5. 对每个涨幅>=8%的股票，检查第2天或第3天的量比（任意一天<0.7即可）
            results = []
            signal_date_to_rise_map = {}  # 用于去重：信号日期 -> (ts_code, rise_date)
            
            checked_count = 0
            no_next_date_count = 0
            no_data_count = 0
            no_volume_ratio_count = 0
            volume_ratio_too_high_count = 0
            from_api_count = 0  # 从同花顺API获取量比的数量
            
            def get_volume_ratio(ts_code: str, check_date: date) -> tuple:
                """
                获取指定日期的量比数据
                返回: (volume_ratio, day_query) 或 (None, None)
                """
                nonlocal from_api_count  # 必须在函数开始处声明
                
                day_query = session.query(
                    FactDailyPriceQfq.volume_ratio,
                    FactDailyPriceQfq.vol,
                    FactDailyPriceQfq.avg_volume_5,
                    FactDailyPriceQfq.close,
                    FactDailyPriceQfq.change_pct,
                    FactDailyPriceQfq.amount
                ).filter(
                    FactDailyPriceQfq.ts_code == ts_code,
                    FactDailyPriceQfq.trade_date == check_date
                ).first()
                
                if not day_query:
                    return None, None
                
                # 获取量比：优先qfq表，其次计算，最后同花顺数据库表
                volume_ratio = None
                if day_query.volume_ratio is not None:
                    volume_ratio = float(day_query.volume_ratio)
                elif day_query.vol is not None and day_query.avg_volume_5 is not None and day_query.avg_volume_5 > 0:
                    # 实时计算量比：当前成交量 / 5日平均成交量
                    volume_ratio = float(day_query.vol) / float(day_query.avg_volume_5)
                else:
                    # 从同花顺数据库表获取（优先）或缓存获取
                    ths_query = session.query(
                        FactTonghuashunLimitUp.volume_ratio
                    ).filter(
                        FactTonghuashunLimitUp.ts_code == ts_code,
                        FactTonghuashunLimitUp.trade_date == check_date,
                        FactTonghuashunLimitUp.volume_ratio.isnot(None)
                    ).first()
                    
                    if ths_query and ths_query.volume_ratio is not None:
                        volume_ratio = float(ths_query.volume_ratio)
                        from_api_count += 1
                    else:
                        # 降级：从缓存获取（如果缓存中有）
                        api_key = (ts_code, check_date)
                        if api_key in ths_volume_ratio_cache:
                            volume_ratio = ths_volume_ratio_cache[api_key]
                            from_api_count += 1
                
                return volume_ratio, day_query
            
            for rise_stock in rise_stocks:
                ts_code = rise_stock.ts_code
                rise_date = rise_stock.rise_date
                
                # 获取第2个和第3个交易日
                next_dates = self._get_next_trading_dates(session, rise_date, count=3)
                if len(next_dates) < 1:
                    no_next_date_count += 1
                    continue
                
                day2_date = next_dates[0] if len(next_dates) > 0 else None  # 第2个交易日（第二天）
                day3_date = next_dates[1] if len(next_dates) > 1 else None  # 第3个交易日（第三天）
                
                signal_date = None
                signal_volume_ratio = None
                signal_day_query = None
                rise_days_ago = None
                
                # 先检查第2天
                if day2_date and day2_date <= end_date:
                    day2_volume_ratio, day2_query = get_volume_ratio(ts_code, day2_date)
                    if day2_query is None:
                        no_data_count += 1
                        if checked_count < 5:
                            logger.debug(f"  ⚠️ {ts_code} {rise_date} 第2天({day2_date})无数据")
                    elif day2_volume_ratio is None:
                        no_volume_ratio_count += 1
                        if checked_count < 5:
                            logger.debug(f"  ⚠️ {ts_code} {rise_date} 第2天({day2_date})量比为NULL且无法获取")
                    else:
                        checked_count += 1
                        # 检查量比和跌幅条件：量比<阈值 且 跌幅不能大于10%（即 change_pct >= -10）
                        # 注意：如果涨跌幅数据缺失（None），则排除该股票
                        day2_change_pct = float(day2_query.change_pct) if day2_query.change_pct is not None else None
                        if day2_volume_ratio < self.config.CYB_VOLUME_RATIO_THRESHOLD:
                            if day2_change_pct is not None and day2_change_pct >= self.config.CYB_DECLINE_THRESHOLD:
                                # 第2天满足条件
                                signal_date = day2_date
                                signal_volume_ratio = day2_volume_ratio
                                signal_day_query = day2_query
                                rise_days_ago = 2
                                if checked_count <= 5:
                                    logger.info(f"  ✅ {ts_code} {rise_date} 第2天({day2_date})量比={day2_volume_ratio:.2f} < {self.config.CYB_VOLUME_RATIO_THRESHOLD}，涨跌幅={day2_change_pct:.2f}%，符合条件")
                            elif checked_count <= 5:
                                if day2_change_pct is None:
                                    logger.debug(f"  ⚠️ {ts_code} {rise_date} 第2天({day2_date})量比={day2_volume_ratio:.2f} < 0.6，但涨跌幅数据缺失，排除")
                                else:
                                    logger.debug(f"  ⚠️ {ts_code} {rise_date} 第2天({day2_date})量比={day2_volume_ratio:.2f} < 0.6，但跌幅={day2_change_pct:.2f}% > 10%，排除")
                        elif checked_count <= 5:
                            logger.debug(f"  ⚠️ {ts_code} {rise_date} 第2天({day2_date})量比={day2_volume_ratio:.2f} >= {self.config.CYB_VOLUME_RATIO_THRESHOLD}")
                
                # 如果第2天不满足条件，才检查第3天
                if signal_date is None and day3_date and day3_date <= end_date:
                    day3_volume_ratio, day3_query = get_volume_ratio(ts_code, day3_date)
                    if day3_query is None:
                        if checked_count < 5:
                            logger.debug(f"  ⚠️ {ts_code} {rise_date} 第3天({day3_date})无数据")
                    elif day3_volume_ratio is None:
                        if checked_count < 5:
                            logger.debug(f"  ⚠️ {ts_code} {rise_date} 第3天({day3_date})量比为NULL且无法获取")
                    else:
                        day3_change_pct = float(day3_query.change_pct) if day3_query.change_pct is not None else None
                        
                        # 检查第3天是否满足条件
                        if day3_volume_ratio is not None:
                            # 检查量比和跌幅条件：量比<阈值 且 跌幅不能大于10%（即 change_pct >= -10）
                            # 注意：如果涨跌幅数据缺失（None），则排除该股票
                            # 重要：即使第3天满足条件，也要检查第2天的跌幅，如果第2天跌幅>10%，也要排除
                            if day3_volume_ratio < self.config.CYB_VOLUME_RATIO_THRESHOLD:
                                if day3_change_pct is not None and day3_change_pct >= self.config.CYB_DECLINE_THRESHOLD:
                                    # 第3天满足量比和跌幅条件，但还要检查第2天的跌幅
                                    # 如果第2天跌幅>10%，也要排除
                                    day2_change_pct = None
                                    if day2_query and day2_query.change_pct is not None:
                                        day2_change_pct = float(day2_query.change_pct)
                                    
                                    if day2_change_pct is not None and day2_change_pct < self.config.CYB_DECLINE_THRESHOLD:
                                        volume_ratio_too_high_count += 1
                                        if checked_count <= 5:
                                            logger.debug(f"  ⚠️ {ts_code} {rise_date} 第3天({day3_date})量比={day3_volume_ratio:.2f} < 0.6，涨跌幅={day3_change_pct:.2f}%，但第2天({day2_date})跌幅={day2_change_pct:.2f}% > 10%，排除")
                                    else:
                                        # 第2天跌幅<=10%（或数据缺失），第3天满足条件，符合要求
                                        signal_date = day3_date
                                        signal_volume_ratio = day3_volume_ratio
                                        signal_day_query = day3_query
                                        rise_days_ago = 3
                                        if checked_count <= 5:
                                            logger.info(f"  ✅ {ts_code} {rise_date} 第3天({day3_date})量比={day3_volume_ratio:.2f} < {self.config.CYB_VOLUME_RATIO_THRESHOLD}，涨跌幅={day3_change_pct:.2f}%，符合条件")
                                elif checked_count <= 5:
                                    if day3_change_pct is None:
                                        logger.debug(f"  ⚠️ {ts_code} {rise_date} 第3天({day3_date})量比={day3_volume_ratio:.2f} < 0.6，但涨跌幅数据缺失，排除")
                                    else:
                                        logger.debug(f"  ⚠️ {ts_code} {rise_date} 第3天({day3_date})量比={day3_volume_ratio:.2f} < 0.6，但跌幅={day3_change_pct:.2f}% > 10%，排除")
                            elif checked_count <= 5:
                                logger.debug(f"  ⚠️ {ts_code} {rise_date} 第3天({day3_date})量比={day3_volume_ratio:.2f} >= {self.config.CYB_VOLUME_RATIO_THRESHOLD}")
                
                # 如果找到符合条件的股票，记录
                if signal_date is not None and signal_day_query is not None:
                    signal_key = (signal_date, ts_code)
                    if signal_key not in signal_date_to_rise_map:
                        signal_date_to_rise_map[signal_key] = {
                            'ts_code': ts_code,
                            'rise_date': rise_date,
                            'signal_date': signal_date,
                            'rise_days_ago': rise_days_ago,
                            'volume_ratio': signal_volume_ratio,
                            'close': float(signal_day_query.close) if signal_day_query.close else 0,
                            'change_pct': float(signal_day_query.change_pct) if signal_day_query.change_pct else 0,
                            'amount': float(signal_day_query.amount) if signal_day_query.amount else 0
                        }
                        if len(signal_date_to_rise_map) <= 5:
                            logger.info(f"  ✅ 找到符合条件的股票: {ts_code}, 涨幅日期: {rise_date}, 信号日期: {signal_date}, 量比: {signal_volume_ratio:.2f}")
                    else:
                        # 如果已存在，比较涨幅日期，保留最近的，并更新所有相关字段
                        existing_rise_date = signal_date_to_rise_map[signal_key]['rise_date']
                        if rise_date > existing_rise_date:
                            # 更新所有字段，确保数据完整
                            signal_date_to_rise_map[signal_key] = {
                                'ts_code': ts_code,
                                'rise_date': rise_date,
                                'signal_date': signal_date,
                                'rise_days_ago': rise_days_ago,
                                'volume_ratio': signal_volume_ratio,
                                'close': float(signal_day_query.close) if signal_day_query.close else 0,
                                'change_pct': float(signal_day_query.change_pct) if signal_day_query.change_pct else 0,
                                'amount': float(signal_day_query.amount) if signal_day_query.amount else 0
                            }
                            if len(signal_date_to_rise_map) <= 5:
                                logger.info(f"  🔄 更新记录: {ts_code}, 涨幅日期: {rise_date} (之前: {existing_rise_date}), 信号日期: {signal_date}, 量比: {signal_volume_ratio:.2f}")
                else:
                    # 如果第2天和第3天都不满足条件
                    if signal_date is None:
                        volume_ratio_too_high_count += 1
            
            logger.info(f"📊 检查统计: 总涨幅>=8%股票={len(rise_stocks)}, "
                       f"无后续交易日={no_next_date_count}, "
                       f"第2天无数据={no_data_count}, "
                       f"第2天量比为NULL={no_volume_ratio_count}, "
                       f"从同花顺API获取量比={from_api_count}, "
                       f"第2天量比>={self.config.CYB_VOLUME_RATIO_THRESHOLD}={volume_ratio_too_high_count}, "
                       f"已检查量比={checked_count}, "
                       f"符合条件的股票={len(signal_date_to_rise_map)}")
            
            if not signal_date_to_rise_map:
                logger.info(f"未找到符合条件的股票（第2天或第3天量比<{self.config.CYB_VOLUME_RATIO_THRESHOLD}）")
                return 0
            
            # 4. 获取股票名称
            stock_names = {}
            signal_ts_codes = list(set([v['ts_code'] for v in signal_date_to_rise_map.values()]))
            name_query = session.query(DimStock.ts_code, DimStock.name).filter(
                DimStock.ts_code.in_(signal_ts_codes)
            )
            for row in name_query.all():
                stock_names[row.ts_code] = row.name if row.name else ''
            
            # 5. 构建结果列表
            for signal_key, data in signal_date_to_rise_map.items():
                results.append({
                    'ts_code': data['ts_code'],
                    'stock_name': stock_names.get(data['ts_code'], ''),
                    'limit_up_date': data['rise_date'].isoformat(),
                    'limit_up_days_ago': data['rise_days_ago'],
                    'volume_ratio': data['volume_ratio'],
                    'today_close': data['close'],
                    'today_change_pct': data['change_pct'],
                    'today_amount': data['amount'],
                    'signal_date': data['signal_date'].isoformat()
                })
            
            logger.info(f"✅ 计算完成，共找到 {len(results)} 只符合条件的股票")
            
            # 6. 保存结果到数据库（包括从同花顺API获取的量比数据）
            saved_count = 0
            api_volume_ratio_count = 0  # 统计从API获取的量比数量
            for result in results:
                signal_date = datetime.strptime(result['signal_date'], '%Y-%m-%d').date()
                
                # 检查是否已存在
                existing = session.query(FactLimitUpVolumeShrink).filter(
                    FactLimitUpVolumeShrink.trade_date == signal_date,
                    FactLimitUpVolumeShrink.ts_code == result['ts_code'],
                    FactLimitUpVolumeShrink.strategy_type == 'cyb_rise_shrink'
                ).first()
                
                limit_up_date = datetime.strptime(result['limit_up_date'], '%Y-%m-%d').date() if result.get('limit_up_date') else None
                volume_ratio_value = result.get('volume_ratio')
                
                # 检查量比是否来自API（通过检查是否在缓存中）
                signal_date_key = (result['ts_code'], signal_date)
                if signal_date_key in ths_volume_ratio_cache:
                    api_volume_ratio_count += 1
                
                if existing:
                    # 更新（包括从同花顺API获取的量比数据）
                    existing.stock_name = result.get('stock_name', '')
                    existing.limit_up_date = limit_up_date
                    existing.limit_up_days_ago = result.get('limit_up_days_ago')
                    existing.volume_ratio = volume_ratio_value  # 保存量比（可能来自同花顺API）
                    existing.today_close = result.get('today_close')
                    existing.today_change_pct = result.get('today_change_pct')
                    existing.today_amount = result.get('today_amount')
                    if saved_count < 5:
                        logger.info(f"  💾 更新记录: {result['ts_code']}, 信号日期: {signal_date}, 量比: {volume_ratio_value}")
                else:
                    # 新增（包括从同花顺API获取的量比数据）
                    new_record = FactLimitUpVolumeShrink(
                        trade_date=signal_date,
                        ts_code=result['ts_code'],
                        stock_name=result.get('stock_name', ''),
                        strategy_type='cyb_rise_shrink',
                        limit_up_date=limit_up_date,
                        limit_up_days_ago=result.get('limit_up_days_ago'),
                        volume_ratio=volume_ratio_value,  # 保存量比（可能来自同花顺API）
                        today_close=result.get('today_close'),
                        today_change_pct=result.get('today_change_pct'),
                        today_amount=result.get('today_amount')
                    )
                    session.add(new_record)
                    if saved_count < 5:
                        logger.info(f"  💾 新增记录: {result['ts_code']}, 信号日期: {signal_date}, 量比: {volume_ratio_value}")
                
                saved_count += 1
            
            session.commit()
            logger.info(f"✅ 保存了 {saved_count} 条创业板科创板涨幅缩量记录到数据库（其中 {api_volume_ratio_count} 条使用了从同花顺API获取的量比数据）")
            return saved_count
            
        except Exception as e:
            session.rollback()
            logger.error(f"从 fact_daily_price_qfq 计算创业板科创板涨幅缩量失败: {e}", exc_info=True)
            return 0
        finally:
            session.close()
    
    def save_cyb_results(self, trade_date: date, results: List[Dict]) -> int:
        """
        保存创业板科创板涨幅缩量计算结果到数据库
        
        Args:
            trade_date: 计算日期
            results: 计算结果列表
        
        Returns:
            int: 保存的记录数
        """
        session = self.warehouse.get_session()
        try:
            saved_count = 0
            
            for result in results:
                signal_date = datetime.strptime(result['signal_date'], '%Y-%m-%d').date() if result.get('signal_date') else trade_date
                
                # 检查是否已存在（基于信号日期和股票代码）
                existing = session.query(FactLimitUpVolumeShrink).filter(
                    FactLimitUpVolumeShrink.trade_date == signal_date,
                    FactLimitUpVolumeShrink.ts_code == result['ts_code'],
                    FactLimitUpVolumeShrink.strategy_type == 'cyb_rise_shrink'
                ).first()
                
                limit_up_date = datetime.strptime(result['limit_up_date'], '%Y-%m-%d').date() if result.get('limit_up_date') else None
                
                if existing:
                    # 更新
                    existing.stock_name = result.get('stock_name', '')
                    existing.limit_up_date = limit_up_date
                    existing.limit_up_days_ago = result.get('limit_up_days_ago')
                    existing.volume_ratio = result.get('volume_ratio')
                    existing.today_close = result.get('today_close')
                    existing.today_change_pct = result.get('today_change_pct')
                    existing.today_amount = result.get('today_amount')
                else:
                    # 新增
                    new_record = FactLimitUpVolumeShrink(
                        trade_date=signal_date,
                        ts_code=result['ts_code'],
                        stock_name=result.get('stock_name', ''),
                        strategy_type='cyb_rise_shrink',
                        limit_up_date=limit_up_date,
                        limit_up_days_ago=result.get('limit_up_days_ago'),
                        volume_ratio=result.get('volume_ratio'),
                        today_close=result.get('today_close'),
                        today_change_pct=result.get('today_change_pct'),
                        today_amount=result.get('today_amount')
                    )
                    session.add(new_record)
                
                saved_count += 1
            
            session.commit()
            logger.info(f"✅ 保存了 {saved_count} 条创业板科创板涨幅缩量记录到数据库")
            return saved_count
            
        except Exception as e:
            session.rollback()
            logger.error(f"保存创业板科创板涨幅缩量计算结果失败: {e}", exc_info=True)
            return 0
        finally:
            session.close()
    
    def check_single_stock(self, ts_code: str, check_date: date) -> Dict:
        """
        单票检测功能：排查指定股票在指定日期为什么不符合条件
        
        Args:
            ts_code: 股票代码（如：688656.SH）
            check_date: 检查日期（涨幅>=8%的日期）
        
        Returns:
            Dict: 详细的检测结果
        """
        session = self.warehouse.get_session()
        result = {
            'ts_code': ts_code,
            'check_date': check_date.isoformat(),
            'qualified': False,
            'steps': [],
            'errors': []
        }
        
        try:
            # 步骤1：检查是否是创业板/科创板股票
            code_part = ts_code.split('.')[0] if '.' in ts_code else ts_code
            is_cyb = code_part.startswith('300') or code_part.startswith('688')
            result['steps'].append({
                'step': 1,
                'name': '检查股票类型',
                'status': 'pass' if is_cyb else 'fail',
                'message': f'股票代码: {ts_code}, 是否为创业板/科创板: {is_cyb}'
            })
            
            if not is_cyb:
                result['errors'].append('该股票不是创业板或科创板股票')
                return result
            
            # 步骤2：检查指定日期是否涨幅>=8%
            rise_query = session.query(
                FactDailyPriceQfq.change_pct,
                FactDailyPriceQfq.close
            ).filter(
                FactDailyPriceQfq.ts_code == ts_code,
                FactDailyPriceQfq.trade_date == check_date
            ).first()
            
            if not rise_query:
                result['steps'].append({
                    'step': 2,
                    'name': '检查涨幅>=8%',
                    'status': 'fail',
                    'message': f'未找到 {check_date} 的价格数据'
                })
                result['errors'].append(f'未找到 {check_date} 的价格数据')
                return result
            
            change_pct = float(rise_query.change_pct) if rise_query.change_pct is not None else None
            close_price = float(rise_query.close) if rise_query.close else None
            
            if change_pct is None:
                result['steps'].append({
                    'step': 2,
                    'name': '检查涨幅>=8%',
                    'status': 'fail',
                    'message': f'涨幅数据缺失'
                })
                result['errors'].append('涨幅数据缺失')
                return result
            
            if change_pct < self.config.CYB_RISE_THRESHOLD:
                result['steps'].append({
                    'step': 2,
                    'name': '检查涨幅>=8%',
                    'status': 'fail',
                    'message': f'涨幅={change_pct:.2f}% < {self.config.CYB_RISE_THRESHOLD}%，不符合条件'
                })
                result['errors'].append(f'涨幅={change_pct:.2f}% < 10%，不符合条件')
                return result
            
            result['steps'].append({
                'step': 2,
                'name': '检查涨幅>=10%',
                'status': 'pass',
                'message': f'涨幅={change_pct:.2f}% >= {self.config.CYB_RISE_THRESHOLD}%，符合条件'
            })
            
            # 步骤3：检查30日最高价条件
            trade_dates_query = session.query(
                FactDailyPriceQfq.trade_date
            ).filter(
                FactDailyPriceQfq.ts_code == ts_code,
                FactDailyPriceQfq.trade_date <= check_date
            ).order_by(
                FactDailyPriceQfq.trade_date.desc()
            ).limit(self.config.CYB_30D_DAYS)
            
            trade_dates_list = [row[0] for row in trade_dates_query.all()]
            if len(trade_dates_list) < self.config.CYB_30D_DAYS:
                if len(trade_dates_list) == 0:
                    result['steps'].append({
                        'step': 3,
                        'name': '检查30日最高价条件',
                        'status': 'fail',
                        'message': '无历史数据'
                    })
                    result['errors'].append('无历史数据，无法计算30日最高价')
                    return result
                date_range_start = trade_dates_list[-1]
            else:
                date_range_start = trade_dates_list[-1]
            
            max_close_30d = session.query(
                func.max(FactDailyPriceQfq.close)
            ).filter(
                FactDailyPriceQfq.ts_code == ts_code,
                FactDailyPriceQfq.trade_date >= date_range_start,
                FactDailyPriceQfq.trade_date <= check_date,
                FactDailyPriceQfq.close.isnot(None),
                FactDailyPriceQfq.close > 0
            ).scalar()
            
            if max_close_30d is None or max_close_30d <= 0:
                result['steps'].append({
                    'step': 3,
                    'name': '检查30日最高价条件',
                    'status': 'fail',
                    'message': '无法获取30日最高收盘价'
                })
                result['errors'].append('无法获取30日最高收盘价')
                return result
            
            max_close_30d = float(max_close_30d)
            threshold_95pct = max_close_30d * self.config.CYB_30D_HIGH_THRESHOLD
            
            if close_price < threshold_95pct:
                result['steps'].append({
                    'step': 3,
                    'name': '检查30日最高价条件',
                    'status': 'fail',
                    'message': f'收盘价({close_price:.2f}) < 30日最高价95%({threshold_95pct:.2f}, 最高价={max_close_30d:.2f})，不符合条件'
                })
                result['errors'].append(f'收盘价({close_price:.2f}) < 30日最高价95%({threshold_95pct:.2f})')
                return result
            
            result['steps'].append({
                'step': 3,
                'name': '检查30日最高价条件',
                'status': 'pass',
                'message': f'收盘价({close_price:.2f}) >= 30日最高价95%({threshold_95pct:.2f}, 最高价={max_close_30d:.2f})，符合条件'
            })
            
            # 步骤4：检查第2天和第3天的量比和跌幅
            next_dates = self._get_next_trading_dates(session, check_date, count=3)
            if len(next_dates) < 1:
                result['steps'].append({
                    'step': 4,
                    'name': '检查第2天和第3天',
                    'status': 'fail',
                    'message': '无后续交易日'
                })
                result['errors'].append('无后续交易日')
                return result
            
            day2_date = next_dates[0] if len(next_dates) > 0 else None
            day3_date = next_dates[1] if len(next_dates) > 1 else None
            
            result['steps'].append({
                'step': 4,
                'name': '获取后续交易日',
                'status': 'pass',
                'message': f'第2天={day2_date}, 第3天={day3_date}'
            })
            
            # 检查第2天
            day2_info = {'date': day2_date, 'has_data': False, 'volume_ratio': None, 'change_pct': None, 'qualified': False, 'reason': ''}
            if day2_date:
                day2_volume_ratio = self._check_volume_ratio(session, ts_code, day2_date)
                day2_change_pct = self._get_change_pct(session, ts_code, day2_date)
                
                # 如果量比数据缺失，尝试从同花顺接口获取
                if day2_volume_ratio is None and self.ths_client.available:
                    logger.info(f"📥 第2天({day2_date})量比数据缺失，尝试从同花顺接口获取: {ts_code}")
                    try:
                        self._fetch_and_save_tonghuashun_data(session, [ts_code], day2_date, completeness_threshold=0.0)
                        # 重新查询量比数据
                        day2_volume_ratio = self._check_volume_ratio(session, ts_code, day2_date)
                        if day2_volume_ratio is not None:
                            logger.info(f"✅ 成功从同花顺接口获取第2天({day2_date})量比数据: {ts_code}, 量比={day2_volume_ratio:.4f}")
                        else:
                            logger.warning(f"⚠️ 从同花顺接口获取后，第2天({day2_date})量比数据仍为空: {ts_code}")
                    except Exception as e:
                        logger.warning(f"⚠️ 从同花顺接口获取第2天({day2_date})量比数据失败: {ts_code}, 错误: {e}")
                
                day2_info['has_data'] = True
                day2_info['volume_ratio'] = day2_volume_ratio
                day2_info['change_pct'] = day2_change_pct
                
                if day2_volume_ratio is None:
                    day2_info['reason'] = '量比数据缺失'
                elif day2_volume_ratio >= self.config.CYB_VOLUME_RATIO_THRESHOLD_REALTIME:
                    day2_info['reason'] = f'量比={day2_volume_ratio:.4f} >= {self.config.CYB_VOLUME_RATIO_THRESHOLD_REALTIME}'
                elif day2_change_pct is None:
                    day2_info['reason'] = '涨跌幅数据缺失'
                elif day2_change_pct < self.config.CYB_DECLINE_THRESHOLD:
                    day2_info['reason'] = f'跌幅={day2_change_pct:.2f}% > {abs(self.config.CYB_DECLINE_THRESHOLD)}%'
                else:
                    day2_info['qualified'] = True
                    result['qualified'] = True
            
            result['day2'] = day2_info
            result['steps'].append({
                'step': 5,
                'name': '检查第2天',
                'status': 'pass' if day2_info['qualified'] else 'fail',
                'message': f"第2天({day2_date}): 量比={day2_info['volume_ratio']}, 涨跌幅={day2_info['change_pct']}, {'符合条件' if day2_info['qualified'] else '不符合条件: ' + day2_info['reason']}"
            })
            
            # 检查第3天（如果第2天不符合）
            day3_info = {'date': day3_date, 'has_data': False, 'volume_ratio': None, 'change_pct': None, 'qualified': False, 'reason': ''}
            if not day2_info['qualified'] and day3_date:
                day3_volume_ratio = self._check_volume_ratio(session, ts_code, day3_date)
                day3_change_pct = self._get_change_pct(session, ts_code, day3_date)
                
                # 如果量比数据缺失，尝试从同花顺接口获取
                if day3_volume_ratio is None and self.ths_client.available:
                    logger.info(f"📥 第3天({day3_date})量比数据缺失，尝试从同花顺接口获取: {ts_code}")
                    try:
                        self._fetch_and_save_tonghuashun_data(session, [ts_code], day3_date, completeness_threshold=0.0)
                        # 重新查询量比数据
                        day3_volume_ratio = self._check_volume_ratio(session, ts_code, day3_date)
                        if day3_volume_ratio is not None:
                            logger.info(f"✅ 成功从同花顺接口获取第3天({day3_date})量比数据: {ts_code}, 量比={day3_volume_ratio:.4f}")
                        else:
                            logger.warning(f"⚠️ 从同花顺接口获取后，第3天({day3_date})量比数据仍为空: {ts_code}")
                    except Exception as e:
                        logger.warning(f"⚠️ 从同花顺接口获取第3天({day3_date})量比数据失败: {ts_code}, 错误: {e}")
                
                day3_info['has_data'] = True
                day3_info['volume_ratio'] = day3_volume_ratio
                day3_info['change_pct'] = day3_change_pct
                
                if day3_volume_ratio is None:
                    day3_info['reason'] = '量比数据缺失'
                elif day3_volume_ratio >= self.config.CYB_VOLUME_RATIO_THRESHOLD_REALTIME:
                    day3_info['reason'] = f'量比={day3_volume_ratio:.4f} >= {self.config.CYB_VOLUME_RATIO_THRESHOLD_REALTIME}'
                elif day3_change_pct is None:
                    day3_info['reason'] = '涨跌幅数据缺失'
                elif day3_change_pct < self.config.CYB_DECLINE_THRESHOLD:
                    day3_info['reason'] = f'跌幅={day3_change_pct:.2f}% > {abs(self.config.CYB_DECLINE_THRESHOLD)}%'
                elif day2_info['change_pct'] is not None and day2_info['change_pct'] < self.config.CYB_DECLINE_THRESHOLD:
                    day3_info['reason'] = f'第2天跌幅={day2_info["change_pct"]:.2f}% > {abs(self.config.CYB_DECLINE_THRESHOLD)}%'
                else:
                    day3_info['qualified'] = True
                    result['qualified'] = True
            
            result['day3'] = day3_info
            result['steps'].append({
                'step': 6,
                'name': '检查第3天',
                'status': 'pass' if day3_info['qualified'] else 'fail',
                'message': f"第3天({day3_date}): 量比={day3_info['volume_ratio']}, 涨跌幅={day3_info['change_pct']}, {'符合条件' if day3_info['qualified'] else '不符合条件: ' + day3_info['reason']}"
            })
            
            return result
            
        except Exception as e:
            logger.error(f"单票检测失败 {ts_code} {check_date}: {e}", exc_info=True)
            result['errors'].append('检测过程出错，请稍后重试')
            return result
        finally:
            session.close()
