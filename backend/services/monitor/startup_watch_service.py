"""
股票启动监控服务
对满足3/4核心条件的股票进行实时监控，满足4/4时语音提醒
"""
import logging
import time
import threading
from collections import Counter
from datetime import datetime, time as dt_time, timedelta, date
from typing import Optional, Dict, List, Tuple
from apscheduler.schedulers.background import BackgroundScheduler
import pyttsx3
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError

# Windows 特有的模块（可选导入）
try:
    import winsound
    WINSOUND_AVAILABLE = True
except ImportError:
    WINSOUND_AVAILABLE = False

logger = logging.getLogger(__name__)

# ==================== 常量定义 ====================
# 监控配置
CHECK_INTERVAL_MINUTES = 5
SLOW_CHECK_THRESHOLD_SECONDS = 3
SLOW_DATA_FETCH_THRESHOLD_SECONDS = 2
PROGRESS_LOG_INTERVAL = 10
# 事务管理：批量提交大小（每N只股票提交一次，避免大事务）
BATCH_COMMIT_SIZE = 10
# 性能优化：单股票检查超时时间（秒），超过此时间跳过该股票
SINGLE_CHECK_TIMEOUT_SECONDS = 30
# 性能优化：数据获取超时时间（秒）
DATA_FETCH_TIMEOUT_SECONDS = 10

# 特殊关注的股票（用于调试）
DEBUG_STOCKS = ['002837.SZ']  # 英维克

# 核心条件名称（共4个）
CORE_CONDITIONS = {
    'breakthrough_90d': '突破90日高点',
    'volume_amplified': '量能放大(量比≥1.5)',
    'bullish_alignment': '均线多头排列(5>10>20>60)',
    'has_limit_up': '近6个交易日有涨停'
}

# 高级阶段（已启动，不需要监控）
ADVANCED_STAGES = ['confirmed', 'started']

# 监控配置：golden_cross 阶段股票的最大监控交易日数（与金叉候选观察期7日保持一致）
MAX_MONITOR_TRADING_DAYS = 7


class StartupWatchService:
    """股票启动监控服务"""
    
    def __init__(self, warehouse_service):
        """
        初始化监控服务
        
        Args:
            warehouse_service: 数据仓库服务实例
        """
        self.ws = warehouse_service
        self.scheduler = BackgroundScheduler()
        self.is_running = False
        self.next_check_time = None
        
        # 缓存 filter_service 实例（性能优化）
        self._filter_service = None
        
        # 初始化TTS引擎
        self._init_tts_engine()
    
    def _init_tts_engine(self):
        """初始化TTS引擎"""
        try:
            self.tts_engine = pyttsx3.init()
            self.tts_available = True
            logger.info("✅ 语音引擎初始化成功")
        except Exception as e:
            self.tts_available = False
            logger.warning(f"⚠️ 语音引擎初始化失败: {e}")
    
    def start(self):
        """启动监控服务（每5分钟检查一次）"""
        if self.is_running:
            logger.info("监控服务已在运行")
            return False
        
        try:
            self.scheduler.add_job(
                self.check_watch_list,
                'interval',
                minutes=CHECK_INTERVAL_MINUTES,
                id='startup_watch',
                next_run_time=datetime.now()  # 立即执行一次
            )
            self.scheduler.start()
            self.is_running = True
            
            logger.info(f"✅ 启动监控服务已启动（每{CHECK_INTERVAL_MINUTES}分钟检查一次）")
            return True
            
        except Exception as e:
            logger.error(f"❌ 启动监控服务失败: {e}")
            return False
    
    def stop(self):
        """停止监控服务"""
        if not self.is_running:
            logger.info("监控服务未运行")
            return False
        
        try:
            self.scheduler.remove_job('startup_watch')
            self.scheduler.shutdown(wait=False)
            self.is_running = False
            
            logger.info("✅ 启动监控服务已停止")
            return True
            
        except Exception as e:
            logger.error(f"❌ 停止监控服务失败: {e}")
            return False
    
    def get_status(self):
        """获取监控状态"""
        watch_count = self._get_watch_count()
        
        return {
            'is_running': self.is_running,
            'next_check': self.next_check_time.isoformat() if self.next_check_time else None,
            'watch_count': watch_count,
            'tts_available': self.tts_available
        }
    
    def check_watch_list(self):
        """检查待监控列表（定时任务）"""
        try:
            # 1. 判断是否交易时间
            if not self._is_trading_time():
                logger.debug("⏰ 非交易时间，跳过检查")
                return
            
            logger.info("🔍 开始检查待监控股票...")
            
            # 2. 查询待监控股票（使用统一的session）
            session = self.ws.get_session()
            alert_count = 0
            
            try:
                from data_warehouse.models.startup_candidate import FactStockStartupCandidate
                from data_warehouse.models.generated_models import FactDailyPriceQfq
                from sqlalchemy import func, distinct
                
                # ✅ 计算最近7个交易日的日期范围
                today = date.today()
                trading_dates_query = session.query(
                    distinct(FactDailyPriceQfq.trade_date)
                ).filter(
                    FactDailyPriceQfq.trade_date <= today
                ).order_by(
                    FactDailyPriceQfq.trade_date.desc()
                ).limit(7).all()
                
                trading_dates_7d = [row[0] for row in trading_dates_query]
                if trading_dates_7d:
                    min_date_7d = min(trading_dates_7d)  # 最近7个交易日的最早日期
                else:
                    min_date_7d = today - timedelta(days=10)  # 备用方案（考虑周末）
                
                # ✅ 修复：排除已启动的股票（stage 为 confirmed 或 started）
                # ✅ 只监控近7个交易日内的股票
                candidates = session.query(FactStockStartupCandidate).filter(
                    FactStockStartupCandidate.is_watching == True,
                    FactStockStartupCandidate.alert_sent == False,
                    ~FactStockStartupCandidate.stage.in_(ADVANCED_STAGES),  # ✅ 排除已启动的股票
                    # ✅ 只查询近7个交易日内的记录（使用 watch_start_date 或 trade_date）
                    (
                        (FactStockStartupCandidate.watch_start_date >= min_date_7d) |
                        (FactStockStartupCandidate.watch_start_date.is_(None) & (FactStockStartupCandidate.trade_date >= min_date_7d))
                    )
                ).all()
                
                if not candidates:
                    logger.info("📭 暂无待监控股票")
                    return
                
                logger.info(f"📊 待监控股票: {len(candidates)} 条记录")
                
                # ✅ 添加详细统计：去重后的股票数量
                unique_stocks = set(c.ts_code for c in candidates)
                logger.info(f"📊 去重后股票数: {len(unique_stocks)} 只（共 {len(candidates)} 条记录）")
                
                # ✅ 统计：有多少只股票有多条记录
                stock_counts = Counter(c.ts_code for c in candidates)
                multi_record_stocks = {ts_code: count for ts_code, count in stock_counts.items() if count > 1}
                if multi_record_stocks:
                    logger.info(f"📊 有多条记录的股票: {len(multi_record_stocks)} 只（共 {sum(multi_record_stocks.values())} 条记录）")
                    for ts_code, count in list(multi_record_stocks.items())[:5]:
                        logger.debug(f"    {ts_code}: {count} 条记录")
                
                # ✅ 添加详细日志：列出所有待监控股票的代码
                ts_codes_list = [c.ts_code for c in candidates]
                logger.debug(f"  待监控股票列表: {', '.join(ts_codes_list[:10])}{'...' if len(ts_codes_list) > 10 else ''}")
                
                # ✅ 特别检查调试股票是否在列表中
                self._log_debug_stocks(candidates)
                
                # 3. 逐个检查（使用批量提交优化事务管理）
                logger.info(f"📋 开始逐个检查 {len(candidates)} 条记录（批量提交大小: {BATCH_COMMIT_SIZE}）...")
                total_start_time = time.time()
                success_count = 0
                failed_count = 0
                last_commit_idx = 0
                
                # ✅ 检测数据库是否支持 savepoint（只检测一次）
                supports_savepoint = self._check_savepoint_support(session)
                if not supports_savepoint:
                    logger.warning("  ⚠️ 数据库不支持 savepoint，将使用批量提交模式（单个股票失败可能影响当前批次）")
                
                for idx, candidate in enumerate(candidates, 1):
                    # ✅ 使用 savepoint 隔离每个股票的操作，单个失败不影响其他股票
                    savepoint = None
                    try:
                        # 如果支持 savepoint，为每个股票创建独立的 savepoint
                        if supports_savepoint:
                            savepoint = session.begin_nested()
                        
                        # ✅ 添加详细日志：记录每只股票的检查情况
                        # 统一使用 DEBUG_STOCKS 常量
                        is_debug = candidate.ts_code in DEBUG_STOCKS
                        log_level = logger.info if is_debug else logger.debug
                        logger.info(f"  🔍 [{idx}/{len(candidates)}] 开始检查 {candidate.ts_code}: stage={candidate.stage}, score={candidate.score}, is_watching={candidate.is_watching}, alert_sent={candidate.alert_sent}")
                        
                        check_start_time = time.time()
                        
                        # ✅ 性能优化：添加超时检查机制，防止单个股票检查卡住整个流程
                        # 注意：不能使用线程池，因为 SQLAlchemy session 不是线程安全的
                        # 使用时间检查 + 详细日志来定位卡住的位置
                        try:
                            logger.debug(f"  → [{idx}/{len(candidates)}] {candidate.ts_code}: 开始检查（超时阈值: {SINGLE_CHECK_TIMEOUT_SECONDS}秒）")
                            
                            # 直接调用，但在方法内部添加详细日志和超时检查
                            result = self._check_single_candidate(candidate, session)
                            
                            check_elapsed = time.time() - check_start_time
                            
                            # 检查是否超时（虽然已经完成，但记录超时情况）
                            if check_elapsed > SINGLE_CHECK_TIMEOUT_SECONDS:
                                logger.error(f"  ⚠️ [{idx}/{len(candidates)}] {candidate.ts_code}: 检查耗时过长 {check_elapsed:.2f} 秒（超过阈值 {SINGLE_CHECK_TIMEOUT_SECONDS}秒）")
                            
                            if result:
                                alert_count += 1
                            success_count += 1
                            
                            if check_elapsed > SLOW_CHECK_THRESHOLD_SECONDS:
                                logger.warning(f"  ⚠️ [{idx}/{len(candidates)}] {candidate.ts_code} 检查耗时 {check_elapsed:.2f} 秒")
                            logger.info(f"  ✅ [{idx}/{len(candidates)}] {candidate.ts_code} 检查完成 (耗时 {check_elapsed:.2f} 秒)")
                            
                            # ✅ 添加日志：显示即将处理下一只股票
                            if idx < len(candidates):
                                logger.debug(f"  → 准备检查下一只股票 [{idx+1}/{len(candidates)}]...")
                        except Exception as check_error:
                            check_elapsed = time.time() - check_start_time
                            logger.error(f"  ❌ [{idx}/{len(candidates)}] {candidate.ts_code}: 检查异常 (耗时 {check_elapsed:.2f} 秒) - {check_error}", exc_info=True)
                            failed_count += 1
                            # 继续处理下一个，不中断整个流程
                            continue
                        
                        # ✅ 提交 savepoint（该股票的操作）
                        if supports_savepoint and savepoint is not None:
                            try:
                                savepoint.commit()
                                logger.debug(f"  💾 [{idx}/{len(candidates)}] {candidate.ts_code}: savepoint 已提交")
                            except Exception as savepoint_error:
                                logger.error(f"  ❌ [{idx}/{len(candidates)}] {candidate.ts_code}: savepoint 提交失败 - {savepoint_error}", exc_info=True)
                                # savepoint 提交失败，回滚 savepoint，但继续处理下一个
                                try:
                                    savepoint.rollback()
                                except:
                                    pass
                        
                        # ✅ 批量提交：每N只股票提交一次主事务，避免大事务
                        if idx % BATCH_COMMIT_SIZE == 0:
                            try:
                                session.commit()
                                elapsed_total = time.time() - total_start_time
                                logger.info(f"  💾 批量提交: {last_commit_idx+1}-{idx} 只股票已提交（共 {idx}/{len(candidates)}，总耗时 {elapsed_total:.2f} 秒）")
                                last_commit_idx = idx
                            except Exception as commit_error:
                                # 提交失败，回滚当前批次
                                session.rollback()
                                logger.error(f"  ❌ 批量提交失败（{last_commit_idx+1}-{idx}）: {commit_error}", exc_info=True)
                                # 继续处理下一批，不中断整个流程
                                last_commit_idx = idx
                        
                        # ✅ 每检查N只股票输出一次进度（或每5只股票输出一次，更频繁的进度更新）
                        if idx % min(PROGRESS_LOG_INTERVAL, 5) == 0:
                            elapsed_total = time.time() - total_start_time
                            avg_time_per_stock = elapsed_total / idx if idx > 0 else 0
                            remaining_stocks = len(candidates) - idx
                            estimated_remaining_time = avg_time_per_stock * remaining_stocks
                            logger.info(f"  📊 检查进度: {idx}/{len(candidates)} ({idx*100//len(candidates)}%)，总耗时 {elapsed_total:.2f} 秒，平均 {avg_time_per_stock:.2f} 秒/只，预计剩余 {estimated_remaining_time:.1f} 秒")
                    except Exception as e:
                        failed_count += 1
                        logger.error(f"  ❌ [{idx}/{len(candidates)}] {candidate.ts_code}: 检查失败 - {str(e)}", exc_info=True)
                        # ✅ 单个股票失败时，只回滚该股票的 savepoint，不影响其他股票
                        try:
                            if supports_savepoint and savepoint is not None:
                                savepoint.rollback()
                                logger.debug(f"  ↻ {candidate.ts_code}: 已回滚该股票的操作（savepoint）")
                            else:
                                # 如果不支持 savepoint，回滚当前批次（只影响当前批次，不影响已提交的批次）
                                # 注意：这会影响当前批次中该股票之后的其他股票
                                session.rollback()
                                logger.warning(f"  ↻ {candidate.ts_code}: 已回滚当前批次（不支持 savepoint，可能影响当前批次的其他股票）")
                                # 重置 last_commit_idx，因为当前批次已回滚
                                last_commit_idx = (idx // BATCH_COMMIT_SIZE) * BATCH_COMMIT_SIZE
                        except Exception as rollback_error:
                            logger.error(f"  ❌ 回滚失败: {rollback_error}")
                        # 继续检查下一个
                        continue
                
                # ✅ 提交剩余的更新（最后一批）
                if last_commit_idx < len(candidates):
                    try:
                        session.commit()
                        logger.info(f"  💾 最终提交: {last_commit_idx+1}-{len(candidates)} 只股票的更新已提交")
                    except Exception as commit_error:
                        session.rollback()
                        logger.error(f"  ❌ 最终提交失败: {commit_error}", exc_info=True)
                
                logger.info(f"✅ 检查完成: {len(candidates)}只，成功: {success_count}只，失败: {failed_count}只，触发提醒: {alert_count}只")
                
            except Exception as e:
                session.rollback()
                logger.error(f"检查待监控列表失败: {e}", exc_info=True)
            finally:
                session.close()
            
            # 更新下次检查时间
            self.next_check_time = datetime.now() + timedelta(minutes=CHECK_INTERVAL_MINUTES)
            
        except Exception as e:
            logger.error(f"❌ 检查待监控列表失败: {e}", exc_info=True)
    
    def _log_debug_stocks(self, candidates: List):
        """记录调试股票的详细信息"""
        ts_codes_list = [c.ts_code for c in candidates]
        
        for debug_stock in DEBUG_STOCKS:
            if debug_stock in ts_codes_list:
                debug_records = [c for c in candidates if c.ts_code == debug_stock]
                logger.info(f"  🔍 发现{debug_stock}在监控池中: {len(debug_records)} 条记录")
                for record in debug_records:
                    logger.info(f"    - {record.trade_date}: stage={record.stage}, score={record.score}, alert_sent={record.alert_sent}")
            else:
                logger.warning(f"  ⚠️ {debug_stock}不在监控池中！可能原因：is_watching=False 或 alert_sent=True")
    
    def _is_trading_time(self) -> bool:
        """判断是否交易时间（9:30-11:30, 13:00-15:00，周一到周五）"""
        now = datetime.now()
        
        # 周末不交易
        if now.weekday() >= 5:
            return False
        
        # 检查时间（上午和下午两个时间段）
        current_time = now.time()
        trading_start_am = dt_time(9, 30)
        trading_end_am = dt_time(11, 30)
        trading_start_pm = dt_time(13, 0)
        trading_end_pm = dt_time(15, 0)
        
        is_am = trading_start_am <= current_time <= trading_end_am
        is_pm = trading_start_pm <= current_time <= trading_end_pm
        
        return is_am or is_pm
    
    def _get_filter_service(self):
        """获取 filter_service（单例，性能优化）"""
        if self._filter_service is None:
            from backend.services.stock.stock_startup_filter import StockStartupFilter
            self._filter_service = StockStartupFilter(warehouse_service=self.ws)
        return self._filter_service
    
    def _validate_stock_data(self, stock_data: Dict, ts_code: str, trade_date: date) -> Tuple[bool, Optional[str]]:
        """
        验证股票数据的完整性和有效性
        
        Args:
            stock_data: 股票数据字典
            ts_code: 股票代码（用于日志）
            trade_date: 交易日期（用于验证数据时效性）
        
        Returns:
            Tuple[bool, Optional[str]]: (是否有效, 错误信息)
        """
        if not stock_data:
            return False, "股票数据为空"
        
        # 必需字段列表（用于核心条件检查）
        required_fields = {
            'close': '收盘价',
            'ma5': '5日均线',
            'ma10': '10日均线',
            'ma20': '20日均线',
            'ma60': '60日均线',
            'high_120d': '120日高点'
        }
        
        # 检查必需字段是否存在
        missing_fields = []
        for field, field_name in required_fields.items():
            if field not in stock_data:
                missing_fields.append(f"{field_name}({field})")
        
        if missing_fields:
            return False, f"缺少必需字段: {', '.join(missing_fields)}"
        
        # 检查数值字段的有效性（必须大于0）
        numeric_fields = {
            'close': '收盘价',
            'ma5': '5日均线',
            'ma10': '10日均线',
            'ma20': '20日均线',
            'ma60': '60日均线',
            'high_120d': '120日高点'
        }
        
        invalid_fields = []
        for field, field_name in numeric_fields.items():
            value = stock_data.get(field)
            if value is None:
                invalid_fields.append(f"{field_name}({field})=None")
            elif isinstance(value, (int, float)) and value <= 0:
                invalid_fields.append(f"{field_name}({field})={value} <= 0")
        
        if invalid_fields:
            return False, f"字段值无效: {', '.join(invalid_fields)}"
        
        # 检查成交量数据（至少需要 amount 或 avg_turnover_20d/avg_amount_20d 之一）
        amount = stock_data.get('amount', 0)
        avg_turnover_20d = stock_data.get('avg_turnover_20d', 0)
        avg_amount_20d = stock_data.get('avg_amount_20d', 0)
        
        if amount <= 0 and avg_turnover_20d <= 0 and avg_amount_20d <= 0:
            return False, "成交量数据无效（amount、avg_turnover_20d、avg_amount_20d 都无效）"
        
        # 检查数据时效性（如果数据中包含 trade_date 字段）
        if 'trade_date' in stock_data:
            data_date = stock_data['trade_date']
            if isinstance(data_date, str):
                try:
                    data_date = datetime.fromisoformat(data_date).date()
                except (ValueError, AttributeError):
                    logger.warning(f"  ⚠️ {ts_code}: 无法解析数据日期: {data_date}")
                    data_date = None
            elif isinstance(data_date, date):
                pass
            else:
                logger.warning(f"  ⚠️ {ts_code}: 数据日期格式未知: {type(data_date)}")
                data_date = None
            
            if isinstance(data_date, date) and data_date != trade_date:
                # 数据日期不匹配，但不一定是错误（可能是历史数据）
                logger.debug(f"  ⚠️ {ts_code}: 数据日期不匹配 - 期望: {trade_date}, 实际: {data_date}")
        
        # 检查均线数据的逻辑合理性（ma5 > ma10 > ma20 > ma60 是正常的多头排列）
        # 但这里只检查数据是否存在，不检查逻辑关系（逻辑关系在条件检查中验证）
        ma5 = stock_data.get('ma5', 0)
        ma10 = stock_data.get('ma10', 0)
        ma20 = stock_data.get('ma20', 0)
        ma60 = stock_data.get('ma60', 0)
        
        # 检查均线数据是否合理（均线应该接近收盘价，不应该相差太大）
        close = stock_data.get('close', 0)
        if close > 0:
            # 均线应该在收盘价的合理范围内（例如：0.5倍到2倍之间）
            # 这个检查比较宽松，主要是为了发现明显错误的数据
            for ma_name, ma_value in [('ma5', ma5), ('ma10', ma10), ('ma20', ma20), ('ma60', ma60)]:
                if ma_value > 0:
                    ratio = ma_value / close
                    if ratio < 0.1 or ratio > 10:
                        logger.warning(f"  ⚠️ {ts_code}: {ma_name} 值异常 - {ma_value}，收盘价: {close}，比例: {ratio:.2f}")
        
        return True, None
    
    def _get_today_record(self, ts_code: str, trade_date: date, session):
        """
        获取指定股票今天的记录（避免重复查询）
        
        Args:
            ts_code: 股票代码
            trade_date: 交易日期
            session: 数据库会话
        
        Returns:
            FactStockStartupCandidate: 今天的记录，如果不存在则返回 None
        """
        from data_warehouse.models.startup_candidate import FactStockStartupCandidate
        from sqlalchemy import and_
        
        return session.query(FactStockStartupCandidate).filter(
            and_(
                FactStockStartupCandidate.ts_code == ts_code,
                FactStockStartupCandidate.trade_date == trade_date
            )
        ).first()
    
    def _check_savepoint_support(self, session) -> bool:
        """
        检查数据库是否支持 savepoint（嵌套事务）
        
        Args:
            session: 数据库会话
        
        Returns:
            bool: 是否支持 savepoint
        """
        try:
            # 尝试创建 savepoint 来检测支持
            savepoint = session.begin_nested()
            savepoint.rollback()  # 立即回滚测试 savepoint
            return True
        except Exception:
            # 如果创建失败，说明不支持 savepoint
            return False
    
    def _remove_from_watching(self, ts_code: str, session, reason: str = ""):
        """
        从监控池移除股票（清除所有历史记录的 is_watching 标记）
        
        Args:
            ts_code: 股票代码
            session: 数据库会话
            reason: 移除原因（用于日志）
        """
        from data_warehouse.models.startup_candidate import FactStockStartupCandidate
        
        start_time = time.time()
        try:
            logger.debug(f"  → {ts_code}: 开始移出监控池...")
            
            # ✅ 优化：直接使用批量更新，避免先查询再更新（减少数据库操作次数）
            # 使用 synchronize_session=False 避免加载对象到内存，提高性能
            try:
                result = session.query(FactStockStartupCandidate).filter(
                    FactStockStartupCandidate.ts_code == ts_code,
                    FactStockStartupCandidate.is_watching == True
                ).update({
                    'is_watching': False,
                    'missing_conditions': None
                }, synchronize_session=False)
                
                # ✅ 重要：不在这里 flush 或 commit，由外层统一管理事务
                # 这样可以避免锁冲突和性能问题
                
            except Exception as update_error:
                # 如果批量更新失败（可能是锁冲突），尝试更温和的方式
                logger.warning(f"  ⚠️ {ts_code}: 批量更新失败，尝试查询后更新 - {update_error}")
                try:
                    # 只更新当前记录，不更新所有历史记录（避免锁冲突）
                    records = session.query(FactStockStartupCandidate).filter(
                        FactStockStartupCandidate.ts_code == ts_code,
                        FactStockStartupCandidate.is_watching == True
                    ).limit(100).all()  # 限制最多更新100条，避免卡住
                    
                    result = 0
                    for record in records:
                        record.is_watching = False
                        record.missing_conditions = None
                        result += 1
                    
                    if result < len(records):
                        logger.warning(f"  ⚠️ {ts_code}: 只更新了部分记录（{result}/{len(records)}），可能还有其他记录需要更新")
                except Exception as fallback_error:
                    logger.error(f"  ❌ {ts_code}: 查询后更新也失败 - {fallback_error}", exc_info=True)
                    result = 0
            
            elapsed = time.time() - start_time
            
            if result > 0:
                logger.info(f"  ✅ {ts_code}: {reason}，已移出监控池（更新了 {result} 条记录，耗时 {elapsed:.2f} 秒）")
            else:
                logger.debug(f"  {ts_code}: 没有记录被更新（可能已经移出）")
                
            if elapsed > 1.0:
                logger.warning(f"  ⚠️ {ts_code}: 移出监控池耗时较长 {elapsed:.2f} 秒")
                
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"  ❌ {ts_code}: 移出监控池时出错 (耗时 {elapsed:.2f} 秒) - {e}", exc_info=True)
            # ✅ 重要：不抛出异常，避免影响主流程
            # 移出监控池失败不应该阻止股票检查继续
            logger.warning(f"  ⚠️ {ts_code}: 移出监控池失败，但继续处理（不影响主流程）")
    
    def _get_watch_count(self) -> int:
        """获取待监控股票数量"""
        from data_warehouse.models.startup_candidate import FactStockStartupCandidate
        
        session = self.ws.get_session()
        
        try:
            count = session.query(FactStockStartupCandidate).filter(
                FactStockStartupCandidate.is_watching == True,
                FactStockStartupCandidate.alert_sent == False
            ).count()
            
            return count
            
        except Exception as e:
            logger.error(f"查询待监控数量失败: {e}")
            return 0
        finally:
            session.close()
    
    def _save_or_update_startup_record(self, candidate, stock_data: Dict, trade_date: date,
                                       stage: str, score: int, signals: List[str],
                                       assist_checks: Dict, risk_checks: Dict,
                                       session, log_level):
        """
        保存或更新启动记录到数据库
        
        Args:
            candidate: 候选股票对象
            stock_data: 股票数据
            trade_date: 交易日期
            stage: 阶段
            score: 得分
            signals: 信号列表
            assist_checks: 辅助条件检查结果
            risk_checks: 风险条件检查结果
            session: 数据库会话
            log_level: 日志级别函数
        
        Returns:
            FactStockStartupCandidate: 保存或更新后的记录对象（用于避免重复查询）
        """
        from data_warehouse.models.startup_candidate import FactStockStartupCandidate
        from sqlalchemy import and_
        
        log_level(f"    → {candidate.ts_code}: 开始保存记录到数据库...")
        
        # 检查今天是否已有记录
        existing = session.query(FactStockStartupCandidate).filter(
            and_(
                FactStockStartupCandidate.ts_code == candidate.ts_code,
                FactStockStartupCandidate.trade_date == trade_date
            )
        ).first()
        
        if existing:
            # 更新现有记录
            existing.score = score
            existing.stage = stage
            existing.is_started = score >= 100
            existing.core_passed = True
            existing.assist_count = assist_checks['count']
            existing.risk_passed = risk_checks['passed']
            existing.passed_signals = signals
            existing.risk_reasons = risk_checks.get('risks', [])
            existing.basic_passed = True
            log_level(f"    → {candidate.ts_code}: 更新现有记录")
            record = existing
        else:
            # 创建新记录
            new_record = FactStockStartupCandidate(
                ts_code=candidate.ts_code,
                trade_date=trade_date,
                score=score,
                is_started=score >= 100,
                stage=stage,
                basic_passed=True,
                core_passed=True,
                assist_count=assist_checks['count'],
                risk_passed=risk_checks['passed'],
                passed_signals=signals,
                risk_reasons=risk_checks.get('risks', []),
                latest_price=float(stock_data.get('close', 0)),
                ma10=float(stock_data.get('ma10', 0))
            )
            session.add(new_record)
            log_level(f"    → {candidate.ts_code}: 创建新记录")
            record = new_record
        
        # 注意：不在这里 commit，由外层统一 commit
        log_level(f"    → {candidate.ts_code}: 记录保存完成（待提交）")
        log_level(f"  📊 {candidate.ts_code}: 已保存新记录到数据库 - stage={stage}, score={score}, assist_count={assist_checks['count']}, risk_passed={risk_checks['passed']}")
        
        return record
    
    def _check_core_conditions_in_signals(self, signals_list: List[str]) -> Dict[str, bool]:
        """
        检查核心条件是否在信号列表中（共4个核心条件）
        
        Args:
            signals_list: 信号列表
        
        Returns:
            Dict[str, bool]: 核心条件检查结果
        """
        return {
            'breakthrough_90d': any(CORE_CONDITIONS['breakthrough_90d'] in signal for signal in signals_list),
            'volume_amplified': any(CORE_CONDITIONS['volume_amplified'] in signal for signal in signals_list),
            'bullish_alignment': any(CORE_CONDITIONS['bullish_alignment'] in signal for signal in signals_list),
            'has_limit_up': any(CORE_CONDITIONS['has_limit_up'] in signal for signal in signals_list)
        }
    
    def _calculate_trading_days_diff(
        self,
        session,
        golden_cross_date: date,
        check_date: date
    ) -> int:
        """
        计算两个日期之间的交易日差（简化版，用于监控服务）
        
        Args:
            session: 数据库会话
            golden_cross_date: 金叉日期
            check_date: 检查日期
        
        Returns:
            int: 交易日差（如果计算失败，返回估算值）
        """
        if golden_cross_date > check_date:
            return -1
        
        try:
            from data_warehouse.models.trade_calendar import DimTradeCalendar
            from sqlalchemy import func
            
            # 查询两个日期之间的交易日数量
            count = session.query(func.count(DimTradeCalendar.trade_date)).filter(
                DimTradeCalendar.trade_date > golden_cross_date,
                DimTradeCalendar.trade_date <= check_date,
                DimTradeCalendar.is_open == True
            ).scalar()
            
            return count if count is not None else -1
        except Exception as e:
            logger.debug(f"计算交易日差失败: {e}，使用估算值")
            # 降级：使用简单估算（每5个自然日约等于3个交易日）
            days_diff = (check_date - golden_cross_date).days
            estimated_trading_days = int(days_diff * 3 / 5)
            return estimated_trading_days
    
    def _check_single_condition(self, condition_name: str, stock_data: Dict) -> bool:
        """
        检查单个核心条件
        
        Args:
            condition_name: 条件名称（如 '突破90日高点', '量能放大(量比≥1.5)', '均线多头排列(5>10>20>60)'）
            stock_data: 股票数据
        
        Returns:
            bool: 是否满足该条件
        """
        from backend.services.stock.startup.conditions.core_condition_checker import CoreConditionChecker
        
        checker = CoreConditionChecker()
        
        if CORE_CONDITIONS['breakthrough_90d'] in condition_name or '突破90日高点' in condition_name or '突破60日高点' in condition_name:
            high_90d = stock_data.get('high_90d', 0) or stock_data.get('high_120d', 0)
            close = stock_data.get('close', 0)
            return high_90d > 0 and close > high_90d
        
        # 检查量能放大
        elif CORE_CONDITIONS['volume_amplified'] in condition_name:
            avg_turnover_20d = stock_data.get('avg_turnover_20d', 0) or stock_data.get('avg_amount_20d', 0)
            amount = stock_data.get('amount', 0)
            
            # ✅ 特殊规则：如果当日涨停，量比条件可以放宽（涨停时量能放大条件自动满足）
            change_pct = stock_data.get('change_pct', 0) or stock_data.get('pct_chg', 0) or 0
            ts_code = stock_data.get('ts_code', '')
            is_cyb = stock_data.get('is_cyb', False)
            if not is_cyb and ts_code:
                # 提取前6位数字代码
                code_part = ts_code.split('.')[0] if '.' in ts_code else ts_code
                is_cyb = code_part.startswith('30') or code_part.startswith('68')
            # 涨停阈值：创业板/科创板20%（19.5%），主板10%（9.5%）
            limit_up_threshold = 19.5 if is_cyb else 9.5
            is_limit_up_today = change_pct >= limit_up_threshold
            
            # 如果当日涨停，自动满足量能放大条件
            if is_limit_up_today:
                return True
            
            return avg_turnover_20d > 0 and amount >= avg_turnover_20d * checker.volume_ratio_threshold
        
        # 检查均线多头排列
        elif CORE_CONDITIONS['bullish_alignment'] in condition_name:
            ma5 = stock_data.get('ma5', 0)
            ma10 = stock_data.get('ma10', 0)
            ma20 = stock_data.get('ma20', 0)
            ma60 = stock_data.get('ma60', 0)
            return ma5 > ma10 > ma20 > ma60
        
        # 检查近6个交易日有涨停
        elif CORE_CONDITIONS['has_limit_up'] in condition_name or '近6个交易日有涨停' in condition_name:
            has_limit_up_6d = stock_data.get('has_limit_up_6d', 0)
            return has_limit_up_6d == 1
        
        return False
    
    def _check_single_candidate(self, candidate, session) -> bool:
        """
        检查单只待监控股票
        
        Args:
            candidate: 候选股票对象（已与session关联）
            session: 数据库会话
        
        Returns:
            bool: 是否触发了提醒
        """
        from backend.services.stock.stock_startup_filter import StockStartupFilter
        from data_warehouse.models.startup_candidate import FactStockStartupCandidate
        
        # ✅ 统一定义：是否为调试股票（用于特殊日志处理）
        is_debug = candidate.ts_code in DEBUG_STOCKS
        log_level = logger.info if is_debug else logger.debug
        
        try:
            # 使用缓存的 filter_service 实例（性能优化）
            filter_service = self._get_filter_service()
            
            # 获取最新交易日数据（监控时强制使用实时数据）
            today = datetime.now().date()
            current_time = datetime.now().time()
            
            # ✅ 监控时：如果在交易时间内（15点前），强制使用实时数据重新计算
            # 即使数据库中今天的数据还没有，也要尝试获取实时数据
            force_realtime = current_time < dt_time(15, 0)
            
            log_level(f"    → {candidate.ts_code}: 开始获取股票数据 (force_realtime={force_realtime}, 超时阈值: {DATA_FETCH_TIMEOUT_SECONDS}秒)...")
            start_time = time.time()
            stock_data = None
            
            try:
                # ✅ 性能优化：添加数据获取超时机制（使用线程池，因为数据获取不涉及数据库操作）
                with ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(
                        filter_service._get_stock_indicators,
                        candidate.ts_code,
                        today.isoformat(),
                        force_realtime=force_realtime
                    )
                    try:
                        stock_data = future.result(timeout=DATA_FETCH_TIMEOUT_SECONDS)
                    except FutureTimeoutError:
                        elapsed = time.time() - start_time
                        logger.error(f"  ❌ {candidate.ts_code}: 数据获取超时（>{DATA_FETCH_TIMEOUT_SECONDS}秒），跳过该股票")
                        return False
                
                elapsed = time.time() - start_time
                if elapsed > SLOW_DATA_FETCH_THRESHOLD_SECONDS:
                    logger.warning(f"  ⚠️ {candidate.ts_code}: 数据获取耗时 {elapsed:.2f} 秒")
                log_level(f"    → {candidate.ts_code}: 数据获取完成 (耗时 {elapsed:.2f} 秒)")
            except Exception as e:
                elapsed = time.time() - start_time
                logger.error(f"  ❌ {candidate.ts_code}: 获取数据异常 (耗时 {elapsed:.2f} 秒) - {str(e)}", exc_info=is_debug)
                return False
            
            if not stock_data:
                # 使用 DEBUG 级别，避免日志噪音（可能是停牌、退市或数据未更新）
                logger.debug(f"  {candidate.ts_code}: 无法获取数据（可能停牌、退市或数据未更新）")
                return False
            
            # ✅ 数据验证：验证股票数据的完整性和有效性
            is_valid, error_msg = self._validate_stock_data(stock_data, candidate.ts_code, today)
            if not is_valid:
                logger.warning(f"  ⚠️ {candidate.ts_code}: 数据验证失败 - {error_msg}")
                # 数据无效时，更新检查计数但不移出监控池（可能是临时数据问题）
                candidate.check_count += 1
                candidate.last_check_time = datetime.now()
                candidate.diagnosis_result = {
                    'error': error_msg,
                    'checked_at': datetime.now().isoformat(),
                    'stage': candidate.stage,
                    'score': candidate.score
                }
                return False
            
            # ✅ 修复：如果股票已经是 confirmed 或 started 状态，自动移出监控池
            # 因为已经进入更高阶段，不需要再监控
            if candidate.stage in ADVANCED_STAGES:
                candidate.is_watching = False
                candidate.missing_conditions = None
                self._remove_from_watching(candidate.ts_code, session, f"已是 {candidate.stage} 状态")
                logger.info(f"  ✅ {candidate.ts_code} 已是 {candidate.stage} 状态，已清除所有历史记录的监控标记")
                return False
            
            # ✅ 对于 golden_cross 阶段的股票，检查金叉日期限制（只检查后5个交易日）
            if candidate.stage == 'golden_cross':
                if candidate.golden_cross_date:
                    trading_days_diff = self._calculate_trading_days_diff(
                        session,
                        candidate.golden_cross_date,
                        today
                    )
                    
                    if trading_days_diff < 0 or trading_days_diff > MAX_MONITOR_TRADING_DAYS:
                        logger.debug(f"  ⏭️ {candidate.ts_code}: golden_cross 阶段，距离金叉日期 {trading_days_diff} 个交易日（超过 {MAX_MONITOR_TRADING_DAYS} 天），跳过检查")
                        # 移出监控池（超过5个交易日，不再监控）
                        candidate.is_watching = False
                        self._remove_from_watching(candidate.ts_code, session, f"golden_cross 阶段超过 {MAX_MONITOR_TRADING_DAYS} 个交易日")
                        return False
                else:
                    # 没有金叉日期，跳过检查
                    logger.debug(f"  ⏭️ {candidate.ts_code}: golden_cross 阶段但没有金叉日期，跳过检查")
                    candidate.is_watching = False
                    self._remove_from_watching(candidate.ts_code, session, "golden_cross 阶段但没有金叉日期")
                    return False
            
            # ✅ 性能优化：添加步骤日志，定位卡住位置
            log_level(f"    → {candidate.ts_code}: 步骤1/5 - 数据验证完成，开始条件检查...")
            
            # ✅ 优化：如果已在监控池中，只检查未满足的条件
            missing_conditions = candidate.missing_conditions or []
            
            # ✅ 添加详细日志：显示检查的条件类型
            stock_name = stock_data.get('name', candidate.ts_code)
            if missing_conditions:
                # 只检查缺少的条件
                logger.info(f"  📋 {candidate.ts_code} ({stock_name}): 已在监控池中，本次只检查缺少的核心条件: {missing_conditions}")
                logger.info(f"  📋 {candidate.ts_code} ({stock_name}): 所有核心条件包括（共4个）: {', '.join(CORE_CONDITIONS.values())}")
            else:
                # 重新检查所有条件
                logger.info(f"  📋 {candidate.ts_code} ({stock_name}): missing_conditions 为空，将进行完整诊断")
                logger.info(f"  📋 {candidate.ts_code} ({stock_name}): 核心条件（共4个）: {', '.join(CORE_CONDITIONS.values())}")
                logger.info(f"  📋 {candidate.ts_code} ({stock_name}): 辅助条件（共3个，至少满足1个）: MACD金叉（DIF上穿DEA）、KDJ金叉（J值50-70）、大单净流入（占比≥5%）")
                logger.info(f"  📋 {candidate.ts_code} ({stock_name}): 风险条件: RSI超买（RSI > 70）、KDJ超买（J值 > 85）")
            
            if missing_conditions:
                # ✅ 兼容性处理：将旧的条件名称转换为新的条件名称
                normalized_missing = []
                for condition in missing_conditions:
                    if '突破60日高点' in condition or '突破90日高点' in condition:
                        # 旧的条件名称，转换为新的（突破N日高点统一用 breakthrough_90d）
                        normalized_condition = CORE_CONDITIONS['breakthrough_90d']
                        logger.info(f"  🔄 {candidate.ts_code} ({stock_name}): 检测到旧的条件名称 '{condition}'，已转换为 '{normalized_condition}'")
                        normalized_missing.append(normalized_condition)
                    else:
                        normalized_missing.append(condition)
                missing_conditions = normalized_missing
                
                # 只检查缺少的条件
                log_level(f"  🔍 {candidate.ts_code}: 已在监控池中，只检查缺少的条件: {missing_conditions}")
                
                newly_passed = []
                still_missing = []
                
                for condition in missing_conditions:
                    if self._check_single_condition(condition, stock_data):
                        newly_passed.append(condition)
                        log_level(f"  ✅ {candidate.ts_code}: 条件已满足 - {condition}")
                    else:
                        still_missing.append(condition)
                        log_level(f"  ⏳ {candidate.ts_code}: 条件未满足 - {condition}")
                
                # 如果所有缺少的条件都满足了，则满足4/4条件
                if not still_missing:
                    # 所有条件都满足了，触发提醒
                    log_level(f"  🎉 {candidate.ts_code}: 所有缺少的条件已满足，满足4/4核心条件！")
                    
                    # ✅ 重要：既然已经满足4/4核心条件，直接检查辅助和风险条件，然后保存记录
                    # 避免重新检查基础条件（可能已经不满足金叉）
                    from backend.services.stock.startup.conditions.assist_condition_checker import AssistConditionChecker
                    from backend.services.stock.startup.conditions.risk_condition_checker import RiskConditionChecker
                    from backend.services.stock.startup.state.state_manager import StartupStateManager
                    
                    # 检查辅助条件
                    log_level(f"    → {candidate.ts_code}: 步骤3/5 - 检查辅助条件...")
                    assist_checker = AssistConditionChecker()
                    assist_checks = assist_checker.check(stock_data)
                    logger.info(f"  📊 {candidate.ts_code} ({stock_name}): 辅助条件检查结果 - 满足 {assist_checks['count']} 个: {', '.join(assist_checks.get('passed_signals', [])) if assist_checks.get('passed_signals') else '无'}")
                    
                    # 检查风险条件
                    log_level(f"    → {candidate.ts_code}: 步骤4/5 - 检查风险条件...")
                    risk_checker = RiskConditionChecker()
                    risk_checks = risk_checker.check(stock_data)
                    if risk_checks['risks']:
                        logger.warning(f"  ⚠️ {candidate.ts_code} ({stock_name}): 风险条件检查 - 发现 {len(risk_checks['risks'])} 个风险: {', '.join(risk_checks['risks'])}")
                    else:
                        logger.info(f"  ✅ {candidate.ts_code} ({stock_name}): 风险条件检查 - 无风险")
                    
                    # 确定阶段和得分
                    state_manager = StartupStateManager()
                    result_stage, _ = state_manager.determine_state(
                        basic_passed=True,  # 假设基础条件通过（因为之前满足3/4条件）
                        core_passed=True,  # 4/4核心条件已满足
                        assist_count=assist_checks['count'],
                        risk_passed=risk_checks['passed']
                    )
                    result_score = state_manager.calculate_score(
                        basic_passed=True,
                        core_passed=True,
                        assist_count=assist_checks['count'],
                        risk_passed=risk_checks['passed']
                    )
                    
                    # 构建信号列表（4个核心条件都已满足）
                    signals = list(CORE_CONDITIONS.values())
                    signals.extend(assist_checks.get('passed_signals', []))
                    
                    # 保存记录到数据库（使用传入的 session，避免创建新 session 导致死锁）
                    logger.info(f"  💾 {candidate.ts_code} ({stock_name}): 开始保存记录到数据库 - stage={result_stage}, score={result_score}")
                    saved_record = self._save_or_update_startup_record(
                        candidate, stock_data, today, result_stage, result_score, signals,
                        assist_checks, risk_checks, session, log_level
                    )
                    logger.info(f"  💾 {candidate.ts_code} ({stock_name}): 已入库 - stage={saved_record.stage}, score={saved_record.score}, is_started={saved_record.is_started}")
                    
                    # ✅ 优化：使用保存方法返回的记录，避免重复查询
                    # 同步保存记录的状态到当前候选记录
                    candidate.stage = saved_record.stage
                    candidate.score = saved_record.score
                    candidate.is_started = saved_record.is_started
                    candidate.core_passed = saved_record.core_passed
                    candidate.assist_count = saved_record.assist_count
                    candidate.risk_passed = saved_record.risk_passed
                    candidate.passed_signals = saved_record.passed_signals
                    candidate.risk_reasons = saved_record.risk_reasons
                    
                    # 更新旧记录的 missing_conditions 为空
                    candidate.missing_conditions = None
                    
                    # ✅ 修复：检查 result 中的 stage，如果已经是 confirmed 或 started，也应该移出监控池
                    if result_stage in ADVANCED_STAGES:
                        candidate.is_watching = False
                        logger.info(f"  → {candidate.ts_code}: 步骤5/5 - 移出监控池...")
                        # ✅ 优化：移出监控池操作不阻塞，即使失败也继续
                        self._remove_from_watching(candidate.ts_code, session, f"检查后状态为 {result_stage}")
                        logger.info(f"  ✅ {candidate.ts_code} 检查后状态为 {result_stage}，已清除所有历史记录的监控标记")
                    
                    # 触发提醒
                    if not candidate.alert_sent:
                        stock_name = stock_data.get('name', candidate.ts_code)
                        logger.info(f"  → {candidate.ts_code}: 准备发送提醒...")
                        try:
                            self._send_alert(candidate.ts_code, stock_name)
                            logger.info(f"  ✅ {candidate.ts_code}: 提醒发送成功")
                        except Exception as alert_error:
                            logger.error(f"  ❌ {candidate.ts_code}: 提醒发送失败 - {alert_error}", exc_info=is_debug)
                        candidate.alert_sent = True
                        candidate.is_watching = False  # 已满足3/3条件，移出监控池
                        logger.info(f"  ✅ {candidate.ts_code}: 已发送提醒并移出监控池")
                        return True
                    else:
                        logger.info(f"  ⚠️ {candidate.ts_code}: 已满足3/3条件，但已发送提醒（alert_sent=True），跳过")
                        return False
                else:
                    # 还有条件未满足，更新 missing_conditions
                    candidate.missing_conditions = still_missing
                    logger.info(f"  📊 {candidate.ts_code} ({stock_name}): 仍有 {len(still_missing)} 个条件未满足: {still_missing}")
                    logger.info(f"  📊 {candidate.ts_code} ({stock_name}): 本次新满足的条件: {newly_passed if newly_passed else '无'}")
                    logger.info(f"  📊 {candidate.ts_code} ({stock_name}): 未入库（未满足3/3核心条件），继续监控")
                    
                    # 更新检查记录
                    candidate.check_count += 1
                    candidate.last_check_time = datetime.now()
                    
                    # ✅ 更新诊断结果
                    candidate.diagnosis_result = {
                        'missing_conditions': still_missing,
                        'newly_passed': newly_passed,
                        'latest_price': float(stock_data.get('close', 0)),
                        'checked_at': datetime.now().isoformat(),
                        'stage': candidate.stage,
                        'score': candidate.score
                    }
                    
                    return False
            else:
                # ✅ 如果没有 missing_conditions，说明是新加入的或需要重新检查所有条件
                # 重新检查完整条件（会自动更新数据库中的stage和score）
                stock_name = stock_data.get('name', candidate.ts_code)
                log_level(f"  🔍 {candidate.ts_code}: missing_conditions 为空，重新检查所有核心条件")
                logger.info(f"  📋 {candidate.ts_code} ({stock_name}): 开始完整诊断 - 将检查核心条件、辅助条件、风险条件")
                log_level(f"    → {candidate.ts_code}: 步骤3/5 - 调用 is_just_started 进行完整诊断...")
                is_just_started_start = time.time()
                try:
                    result = filter_service.is_just_started(stock_data, today.isoformat())
                    is_just_started_elapsed = time.time() - is_just_started_start
                    log_level(f"    → {candidate.ts_code}: is_just_started 完成 (耗时 {is_just_started_elapsed:.2f} 秒)")
                    if is_just_started_elapsed > 5:
                        logger.warning(f"  ⚠️ {candidate.ts_code}: is_just_started 耗时过长 {is_just_started_elapsed:.2f} 秒")
                except Exception as e:
                    is_just_started_elapsed = time.time() - is_just_started_start
                    logger.error(f"  ❌ {candidate.ts_code}: is_just_started 异常 (耗时 {is_just_started_elapsed:.2f} 秒) - {str(e)}", exc_info=is_debug)
                    return False
                
                # ✅ 修复：检查 result 中的 stage，如果已经是 confirmed 或 started，也应该移出监控池
                result_stage = result.get('stage')
                if result_stage in ADVANCED_STAGES:
                    candidate.stage = result_stage
                    candidate.score = result.get('score', candidate.score)
                    candidate.is_watching = False
                    candidate.missing_conditions = None
                    self._remove_from_watching(candidate.ts_code, session, f"检查后状态为 {result_stage}")
                    logger.info(f"  ✅ {candidate.ts_code} 检查后状态为 {result_stage}，已清除所有历史记录的监控标记")
                    return False
                
                # 提取核心条件检查结果（已更新为120日高点）
                signals_list = result.get('signals', [])
                core_checks = self._check_core_conditions_in_signals(signals_list)
                
                passed_count = sum(core_checks.values())
                
                    # ✅ 添加详细日志：记录核心条件检查结果
                core_status = []
                if core_checks['breakthrough_90d']:
                    core_status.append("✅突破90日高点")
                else:
                    core_status.append("❌突破90日高点")
                if core_checks['volume_amplified']:
                    core_status.append("✅量能放大")
                else:
                    core_status.append("❌量能放大")
                if core_checks['bullish_alignment']:
                    core_status.append("✅均线多头排列")
                else:
                    core_status.append("❌均线多头排列")
                if core_checks.get('has_limit_up', False):
                    core_status.append("✅近6个交易日有涨停")
                else:
                    core_status.append("❌近6个交易日有涨停")
                
                logger.info(f"  📊 {candidate.ts_code} ({stock_name}): 核心条件检查结果 - {', '.join(core_status)} (通过 {passed_count}/4)")
                
                # ✅ 添加详细日志：显示辅助条件和风险条件检查结果
                assist_checks_result = result.get('assist_checks', {})
                assist_count = assist_checks_result.get('count', 0)
                assist_signals = assist_checks_result.get('passed_signals', [])
                logger.info(f"  📊 {candidate.ts_code} ({stock_name}): 辅助条件检查结果 - 满足 {assist_count} 个: {', '.join(assist_signals) if assist_signals else '无'}")
                
                risk_checks_result = result.get('risk_checks', {})
                risk_passed = risk_checks_result.get('passed', True)
                risk_reasons = risk_checks_result.get('risks', [])
                if risk_reasons:
                    logger.warning(f"  ⚠️ {candidate.ts_code} ({stock_name}): 风险条件检查 - 发现 {len(risk_reasons)} 个风险: {', '.join(risk_reasons)}")
                else:
                    logger.info(f"  ✅ {candidate.ts_code} ({stock_name}): 风险条件检查 - 无风险")
                
                # ✅ 添加详细日志：输出实际返回的 signals 列表（特别关注调试股票）
                if is_debug:
                    logger.info(f"  🔍 {candidate.ts_code}: 实际返回的 signals={signals_list}, stage={result.get('stage')}, score={result.get('score')}")
                
                # 更新检查记录
                candidate.check_count += 1
                candidate.last_check_time = datetime.now()
                
                # ✅ 更新诊断结果（包含完整的状态信息）
                candidate.diagnosis_result = {
                    'core_checks': core_checks,
                    'passed_count': passed_count,
                    'latest_price': float(stock_data.get('close', 0)),
                    'checked_at': datetime.now().isoformat(),
                    'stage': result.get('stage'),  # ✅ 记录最新阶段
                    'score': result.get('score'),  # ✅ 记录最新得分
                    'is_started': result.get('is_started')  # ✅ 记录是否启动
                }
                
                # ✅ 标准逻辑：满足4/4核心条件 → 已启动
                # 3/4条件 → 保持在golden_cross阶段，标记为待监控
                # 4/4条件 → 进入confirmed阶段
                should_start = passed_count == 4 and not candidate.alert_sent
                
                # ✅ 添加详细日志：记录是否满足启动条件
                if passed_count == 4:
                    if candidate.alert_sent:
                        log_level(f"  ⚠️ {candidate.ts_code}: 满足4/4条件，但已发送提醒（alert_sent=True），跳过")
                    else:
                        logger.info(f"  ✅ {candidate.ts_code} ({stock_name}): 满足4/4核心条件，准备发送提醒")
                elif passed_count == 3:
                    logger.info(f"  📊 {candidate.ts_code} ({stock_name}): 满足3/4核心条件，保持在golden_cross阶段，继续监控")
                else:
                    # 计算缺少的条件
                    missing = []
                    if not core_checks['breakthrough_90d']:
                        missing.append('突破90日高点')
                    if not core_checks['volume_amplified']:
                        missing.append('量能放大(量比≥1.5)')
                    if not core_checks['bullish_alignment']:
                        missing.append('均线多头排列(5>10>20>60)')
                    if not core_checks.get('has_limit_up', False):
                        missing.append('近6个交易日有涨停')
                    logger.info(f"  📊 {candidate.ts_code} ({stock_name}): 核心条件={passed_count}/4，缺少: {', '.join(missing) if missing else '无'}，继续监控")
                    
                    # 更新 missing_conditions，方便下次只检查缺少的条件
                    # 如果满足3/4条件，标记为待监控
                    if passed_count == 3:
                        candidate.is_watching = True
                        candidate.missing_conditions = missing
                    else:
                        candidate.missing_conditions = missing
                
                if should_start:
                    stock_name = stock_data.get('name', candidate.ts_code)
                    
                    # ✅ 优化：is_just_started 方法应该已经保存了记录到数据库
                    # 查询今天的最新记录，同步状态到当前候选记录（只查询一次）
                    # 注意：这里查询是因为 is_just_started 方法内部保存了记录，我们需要获取保存后的状态
                    log_level(f"    → {candidate.ts_code}: 步骤4/5 - 查询今天的最新记录...")
                    latest_record = self._get_today_record(candidate.ts_code, today, session)
                    
                    if latest_record:
                        # ✅ 同步最新记录的状态到当前候选记录
                        logger.info(f"  💾 {candidate.ts_code} ({stock_name}): 已入库 - stage={latest_record.stage}, score={latest_record.score}, is_started={latest_record.is_started}")
                        candidate.stage = latest_record.stage
                        candidate.score = latest_record.score
                        candidate.is_started = latest_record.is_started
                        candidate.core_passed = latest_record.core_passed
                        candidate.assist_count = latest_record.assist_count
                        candidate.risk_passed = latest_record.risk_passed
                        candidate.passed_signals = latest_record.passed_signals
                        candidate.risk_reasons = latest_record.risk_reasons
                        
                        logger.info(f"✅ {candidate.ts_code}: 状态已更新 - stage={latest_record.stage}, score={latest_record.score}, is_started={latest_record.is_started}")
                    else:
                        # 如果没有今天的记录，使用result中的状态
                        candidate.stage = result.get('stage', candidate.stage)
                        candidate.score = result.get('score', candidate.score)
                        candidate.is_started = result.get('is_started', False)
                        logger.warning(f"⚠️ {candidate.ts_code}: 未找到今天的记录，使用result中的状态")
                    
                    # 发送提醒
                    self._send_alert(candidate.ts_code, stock_name)
                    
                    candidate.alert_sent = True
                    candidate.is_watching = False  # 移出监控池
                    
                    reason = "满足4/4核心条件"
                    logger.info(f"🔔 {candidate.ts_code} {stock_name}: {reason}，状态已更新为 {candidate.stage}，已提醒")
                    
                    return True
                else:
                    logger.debug(f"  {candidate.ts_code}: 核心条件={passed_count}/4，继续监控")
                    return False
                
        except Exception as e:
            logger.error(f"检查股票 {candidate.ts_code} 失败: {e}", exc_info=True)
            return False
    
    def _send_alert(self, ts_code: str, stock_name: str):
        """
        发送语音提醒
        
        Args:
            ts_code: 股票代码
            stock_name: 股票名称
        """
        try:
            # 方案1：语音播报（使用非阻塞方式）
            if self.tts_available:
                message = f"启动信号，{stock_name}，代码{ts_code}"
                try:
                    # ✅ 优化：使用非阻塞方式，避免阻塞整个流程
                    self.tts_engine.say(message)
                    
                    def run_tts():
                        """在后台线程中运行TTS，避免阻塞主流程"""
                        try:
                            self.tts_engine.runAndWait()
                        except Exception as e:
                            logger.error(f"语音播放异常: {e}")
                    
                    # 在后台线程中运行，避免阻塞
                    tts_thread = threading.Thread(target=run_tts, daemon=True)
                    tts_thread.start()
                    logger.info(f"🔊 语音提醒已启动: {message}（后台播放）")
                except Exception as tts_error:
                    logger.error(f"语音提醒启动失败: {tts_error}")
                    # 降级到蜂鸣音
                    if WINSOUND_AVAILABLE:
                        try:
                            for _ in range(3):
                                winsound.Beep(1000, 300)
                            logger.info(f"🔔 蜂鸣提醒: {stock_name}({ts_code})")
                        except Exception as beep_error:
                            logger.warning(f"蜂鸣提醒失败: {beep_error}")
                    else:
                        logger.warning("winsound 模块不可用，无法播放蜂鸣音")
            else:
                # 方案2：系统蜂鸣音（备选）
                if WINSOUND_AVAILABLE:
                    try:
                        # 播放3次蜂鸣
                        for _ in range(3):
                            winsound.Beep(1000, 300)  # 1000Hz, 300ms
                        logger.info(f"🔔 蜂鸣提醒: {stock_name}({ts_code})")
                    except Exception as beep_error:
                        logger.warning(f"蜂鸣提醒失败: {beep_error}")
                else:
                    logger.warning("winsound 模块不可用，无法播放蜂鸣音")
            
            # 记录提醒日志
            logger.info(f"🎯 启动提醒: {stock_name}({ts_code}) 满足3/3核心条件")
            
        except Exception as e:
            logger.error(f"发送提醒失败: {e}", exc_info=True)


# 全局监控服务实例（单例）
_watch_service_instance = None

def get_watch_service(warehouse_service=None):
    """获取监控服务实例（单例模式）"""
    global _watch_service_instance
    
    if _watch_service_instance is None and warehouse_service:
        _watch_service_instance = StartupWatchService(warehouse_service)
    
    return _watch_service_instance

