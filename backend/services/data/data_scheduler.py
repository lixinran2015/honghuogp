"""
数据调度服务
负责定时更新数据仓库中的数据
- 开市时间段：每10分钟更新一次
- 闭市时间段：使用15点闭市的数据
"""

import logging
import threading
import time
from datetime import datetime, time as dt_time, timedelta
from typing import Optional, List
import pandas as pd

from backend.services.data.data_warehouse import DataWarehouse
from backend.services.market_data_service import MarketDataService
from backend.services.data.financial_data_fetcher import FinancialDataFetcher

# 初始化logger（需要在导入akshare_safe_wrapper之前）
logger = logging.getLogger(__name__)

# 导入实时数据获取器
try:
    from backend.services.data.realtime_fetcher import fetch_realtime_a_stock
    logger.info("✅ 导入 realtime_fetcher 成功")
except ImportError as e:
    logger.warning(f"⚠️ 无法导入 realtime_fetcher: {e}")
    fetch_realtime_a_stock = None


class DataScheduler:
    """数据调度服务类"""
    
    def __init__(self, warehouse: Optional[DataWarehouse] = None):
        """
        初始化数据调度服务（复用 ServiceManager 单例，避免重复初始化）
        
        Args:
            warehouse: 数据仓库实例，如果为None则创建新实例
        """
        self.warehouse = warehouse or DataWarehouse()
        try:
            from backend.services.service_manager import get_service_manager
            self.market_service = get_service_manager().get_market_data_service()
            self.financial_fetcher = FinancialDataFetcher()
        except Exception:
            self.market_service = MarketDataService()
            self.financial_fetcher = FinancialDataFetcher()
        
        self.running = False
        self.scheduler_thread: Optional[threading.Thread] = None
        self.task_check_thread: Optional[threading.Thread] = None
        self._start_lock = threading.Lock()
        # 行业周期采集：同一时间只允许一次（手动点击与定时任务共用）
        self._industry_cycle_collect_lock = threading.Lock()
        self._industry_cycle_collect_running = False

        # 交易时间：9:30-11:30, 13:00-15:00
        self.trading_start_am = dt_time(9, 30)
        self.trading_end_am = dt_time(11, 30)
        self.trading_start_pm = dt_time(13, 0)
        self.trading_end_pm = dt_time(15, 0)
        
        logger.info("📅 数据调度服务初始化完成")
    
    def is_trading_time(self) -> bool:
        """
        判断当前是否为交易时间
        
        Returns:
            bool: 是否为交易时间
        """
        now = datetime.now()
        current_time = now.time()
        weekday = now.weekday()
        
        # 周末不是交易时间
        if weekday >= 5:
            return False
        
        # 检查是否在交易时间段内
        is_am = self.trading_start_am <= current_time <= self.trading_end_am
        is_pm = self.trading_start_pm <= current_time <= self.trading_end_pm
        
        return is_am or is_pm
    
    def should_use_closing_data(self) -> bool:
        """
        判断是否应该使用收盘数据（闭市后使用15点数据）
        
        Returns:
            bool: 是否应该使用收盘数据
        """
        now = datetime.now()
        current_time = now.time()
        weekday = now.weekday()
        
        # 周末使用收盘数据
        if weekday >= 5:
            return True
        
        # 15点后使用收盘数据
        if current_time >= self.trading_end_pm:
            return True
        
        # 11:30-13:00之间使用上午收盘数据（暂时也用15点数据）
        if self.trading_end_am < current_time < self.trading_start_pm:
            return True
        
        return False
    
    def update_stocks_data(self) -> bool:
        """
        更新股票行情数据
        
        Returns:
            bool: 是否更新成功
        """
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            
            # 如果是闭市时间，尝试使用15点数据
            if self.should_use_closing_data():
                # 检查今天15点的数据是否已存在
                existing_data = self.warehouse.load_stocks_data(today)
                if existing_data is not None and not existing_data.empty:
                    logger.info(f"✅ 使用今日收盘数据（已存在）: {today}")
                    return True
                
                # 尝试获取今日收盘数据
                logger.info(f"📥 获取今日收盘数据: {today}")
                if fetch_realtime_a_stock is None:
                    logger.warning("⚠️ fetch_realtime_a_stock 不可用，跳过更新")
                    return False
                stock_data = fetch_realtime_a_stock(cache=True, force_refresh=False)
            else:
                # 交易时间，获取实时数据
                logger.info(f"📥 获取实时股票数据: {today}")
                stock_data = self.market_service.get_realtime_stocks(force_refresh=True)
            
            if stock_data.empty:
                logger.warning(f"⚠️ 获取股票数据为空: {today}")
                return False
            
            # 保存到数据仓库
            success = self.warehouse.save_stocks_data(today, stock_data)
            return success
            
        except Exception as e:
            logger.error(f"❌ 更新股票数据失败: {e}", exc_info=True)
            return False
    
    def update_financial_data(self, stock_codes: Optional[List[str]] = None, limit: int = 200, force: bool = False) -> bool:
        """
        更新财务数据（每天只更新一次，异步不阻塞）
        
        Args:
            stock_codes: 股票代码列表，如果为None则从今日股票数据中获取
            limit: 限制更新的股票数量，避免请求过多
            force: 是否强制更新（忽略今日已更新检查）
        
        Returns:
            bool: 是否更新成功
        """
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            
            # 检查今日财务数据是否已存在（避免重复下载）
            if not force:
                existing_financial = self.warehouse.load_financial_data(today)
                if existing_financial and len(existing_financial) >= 100:
                    logger.info(f"✅ 今日财务数据已更新（{len(existing_financial)} 只），跳过重复获取")
                    return True
            
            # 如果未提供股票代码列表，从今日股票数据中获取
            if stock_codes is None:
                stock_data = self.warehouse.load_stocks_data(today)
                if stock_data is None or stock_data.empty:
                    # 尝试获取最近的股票数据
                    for i in range(1, 5):
                        prev_date = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
                        stock_data = self.warehouse.load_stocks_data(prev_date)
                        if stock_data is not None and not stock_data.empty:
                            break
                    
                    if stock_data is None or stock_data.empty:
                        logger.warning(f"⚠️ 无法获取股票数据，跳过财务数据更新")
                        return False
                
                # 提取股票代码（只取A股，过滤北交所）
                stock_codes = []
                for _, row in stock_data.iterrows():
                    code = row.get('代码', row.get('code', ''))
                    if isinstance(code, pd.Series):
                        code = code.iloc[0] if len(code) > 0 else ''
                    if code and str(code) != 'nan' and str(code).strip():
                        code_str = str(code)
                        if code_str.startswith('bj'):
                            continue
                        if code_str.startswith('sh') or code_str.startswith('sz'):
                            stock_codes.append(code)
                        elif code_str.isdigit() and len(code_str) == 6:
                            if code_str.startswith('6'):
                                stock_codes.append(f'sh{code_str}')
                            elif code_str.startswith('0') or code_str.startswith('3'):
                                stock_codes.append(f'sz{code_str}')
                    
                    if len(stock_codes) >= limit:
                        break
            
            if not stock_codes:
                logger.warning("⚠️ 没有股票代码，无法更新财务数据")
                return False
            
            # 使用 Tushare 批量接口获取（减少延迟）
            logger.info(f"📥 批量获取财务数据: {len(stock_codes)} 只股票")
            financial_data = self.financial_fetcher.batch_get_financial_data(stock_codes, delay=0.1)
            
            if not financial_data:
                logger.warning("⚠️ 获取财务数据为空")
                return False
            
            # 保存到数据仓库
            success = self.warehouse.save_financial_data(today, financial_data)
            return success
            
        except Exception as e:
            logger.error(f"❌ 更新财务数据失败: {e}", exc_info=True)
            return False
    
    def update_moneyflow_data(self) -> bool:
        """
        更新资金流向数据（用于月度热点统计）。
        使用「最近一个交易日」拉取，避免非交易日 Tushare 无数据导致空结果。
        """
        logger.info("📥 [资金流向] 开始执行 update_moneyflow_data")
        
        try:
            from datetime import date as date_type
            today_date = date_type.today()
            # 使用最近交易日（非交易日则用前一交易日）
            trade_date = None
            try:
                from backend.utils.trade_date_utils import get_latest_trade_date
                from data_warehouse.service.warehouse_service import WarehouseService
                ws = WarehouseService()
                trade_date = get_latest_trade_date(ws, 10, today_date)
            except Exception as e:
                logger.debug(f"从交易日历获取最近交易日失败: {e}，使用降级逻辑")
            if trade_date is None:
                for i in range(10):
                    d = today_date - timedelta(days=i)
                    if d.weekday() < 5:
                        trade_date = d
                        break
            if trade_date is None:
                trade_date = today_date - timedelta(days=1)
            trade_date_str = trade_date.strftime("%Y-%m-%d")

            try:
                from backend.services.moneyflow_service import MoneyflowService
                moneyflow_service = MoneyflowService()

                if not moneyflow_service.available:
                    logger.warning("⚠️ 资金流向服务不可用，跳过更新")
                    return False

                logger.info(f"📥 获取资金流向数据: {trade_date_str}（最近交易日）")

                sector_moneyflow = moneyflow_service.get_sector_moneyflow(trade_date_str)
                industry_moneyflow = moneyflow_service.get_industry_moneyflow(trade_date_str)
                concept_performance = moneyflow_service.get_concept_performance(trade_date_str)

                moneyflow_data = {
                    'date': trade_date_str,
                    'sector_moneyflow': sector_moneyflow.to_dict('records') if sector_moneyflow is not None and not sector_moneyflow.empty else [],
                    'industry_moneyflow': industry_moneyflow.to_dict('records') if industry_moneyflow is not None and not industry_moneyflow.empty else [],
                    'concept_performance': concept_performance.to_dict('records') if concept_performance is not None and not concept_performance.empty else []
                }

                success = self.warehouse.save_moneyflow_data(trade_date_str, moneyflow_data)
                n_ind = len(moneyflow_data.get("industry_moneyflow") or [])
                n_sec = len(moneyflow_data.get("sector_moneyflow") or [])
                if success:
                    logger.info(f"✅ 资金流向数据更新成功: {trade_date_str} (行业 {n_ind} 条, 板块 {n_sec} 条)")
                    if n_ind == 0:
                        logger.warning(f"⚠️ 行业资金流向为空，请确认 Tushare 积分≥5000、接口 moneyflow_ind_ths 可用，或该日数据已发布")
                else:
                    logger.warning(f"⚠️ 资金流向数据更新失败: {trade_date_str}")
                return success

            except ImportError:
                logger.warning("⚠️ MoneyflowService 不可用，跳过资金流向数据更新")
                return False

        except Exception as e:
            logger.error(f"❌ 更新资金流向数据失败: {e}", exc_info=True)
            return False
    
    def update_industry_cycle_data(self, use_subprocess: bool = False) -> bool:
        """
        采集行业周期数据（industry_index、revenue_yoy、net_cash_dist、money_flow）
        供行业周期规则引擎使用，每日闭市后自动执行一次
        执行前先同步 dim_stock.industry 为申万一级行业，保证行业体系统一
        同一时间只允许一次执行（手动点击与定时任务共用锁，避免双跑）。

        use_subprocess: 为 True 时用子进程执行采集脚本（定时任务推荐），避免与主进程线程/锁相互影响导致卡住。
        """
        with self._industry_cycle_collect_lock:
            if self._industry_cycle_collect_running:
                logger.info("行业周期采集已在执行中（手动或定时触发），跳过本次")
                return False
            self._industry_cycle_collect_running = True
        try:
            import sys
            from pathlib import Path
            project_root = Path(__file__).resolve().parents[3]
            # 1. 先同步申万行业到 dim_stock（统一行业来源）
            try:
                from backend.scripts.data_update.sync_industry_from_sw import sync_industry_from_sw
                n = sync_industry_from_sw()
                if n >= 0:
                    logger.info(f"申万行业同步完成，更新 {n} 只股票")
                else:
                    logger.warning("申万行业同步跳过（可能无 token），继续采集")
            except Exception as e:
                logger.warning(f"申万行业同步失败，继续采集: {e}")
            # 2. 采集行业周期数据
            script_path = project_root / "scripts" / "tools" / "collect_industry_cycle_data.py"
            if not script_path.exists():
                logger.warning(f"⚠️ 行业周期采集脚本不存在: {script_path}")
                return False
            if use_subprocess:
                # 定时任务：子进程执行，避免主进程线程/锁导致卡住
                import subprocess
                logger.info("行业周期采集（子进程）: %s", script_path)
                try:
                    proc = subprocess.run(
                        [sys.executable, str(script_path)],
                        cwd=str(project_root),
                        timeout=900,
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                    )
                    if proc.returncode != 0:
                        logger.warning("行业周期采集子进程退出码 %s，stderr: %s", proc.returncode, (proc.stderr or "")[-500:])
                        return False
                    # 检查是否生成了当日文件
                    ic_dir = project_root / "data_warehouse" / "industry_cycle"
                    today_str = datetime.now().strftime("%Y%m%d")
                    out_file = ic_dir / f"cycle_data_{today_str}.json"
                    if out_file.exists():
                        logger.info("行业周期数据已写入（子进程）: %s", out_file)
                        return True
                    logger.warning("行业周期采集子进程完成但未找到当日文件: %s", out_file)
                    return False
                except subprocess.TimeoutExpired:
                    logger.error("行业周期采集子进程超时（900s）")
                    return False
                except Exception as e:
                    logger.error("行业周期采集子进程异常: %s", e, exc_info=True)
                    return False
            # 手动触发：当前进程内执行，便于 API 等待结果
            # 安全校验：确保脚本路径在项目目录内，防止路径穿越
            resolved_script = script_path.resolve()
            resolved_root = project_root.resolve()
            if not str(resolved_script).startswith(str(resolved_root)):
                logger.error("拒绝加载项目目录外的脚本: %s", resolved_script)
                return False
            import importlib.util
            spec = importlib.util.spec_from_file_location("collect_ic", resolved_script)
            mod = importlib.util.module_from_spec(spec)
            _path_inserted = False
            if str(project_root) not in sys.path:
                sys.path.insert(0, str(project_root))
                _path_inserted = True
            try:
                spec.loader.exec_module(mod)
            finally:
                if _path_inserted and str(project_root) in sys.path:
                    sys.path.remove(str(project_root))
            logger.info("开始执行行业周期采集脚本: %s", script_path)
            path = mod.main()
            logger.info("行业周期采集脚本执行完毕，返回路径: %s", path)
            if path is not None:
                logger.info("行业周期数据已写入: %s", path)
                return True
            logger.warning("行业周期采集脚本 main() 未返回写入路径")
            return False
        except Exception as e:
            logger.error(f"❌ 行业周期数据采集失败: {e}", exc_info=True)
            return False
        finally:
            with self._industry_cycle_collect_lock:
                self._industry_cycle_collect_running = False
    
    def _update_stock_universe(self, trade_date: str) -> bool:
        """
        更新股票池数据（base池和S1池）
        
        Args:
            trade_date: 交易日期
            
        Returns:
            bool: 是否更新成功
        """
        try:
            from backend.services.stock.stock_universe_service import StockUniverseService
            universe_service = StockUniverseService()
            
            logger.info(f"📥 开始更新股票池: {trade_date}")
            results = universe_service.update_all_universes(trade_date)
            
            success_count = sum(1 for r in results.values() if r.get('success', False))
            logger.info(f"✅ 股票池更新完成: {success_count}/{len(results)} 成功")
            
            return success_count > 0
        except Exception as e:
            logger.error(f"❌ 更新股票池失败: {e}", exc_info=True)
            return False
    
    def batch_update_qfq_data(self, start_date: str, end_date: str = None) -> dict:
        """
        批量更新前复权K线数据（补充缺失日期）
        
        使用统一的更新脚本 update_daily_prices_from_snapshot()，支持：
        - 多数据源降级策略（iFinDPy → Tushare）
        - 分层架构（Raw → Clean → Fact）
        - 任务执行日志
        - 物化视图自动刷新
        
        Args:
            start_date: 开始日期 YYYY-MM-DD
            end_date: 结束日期 YYYY-MM-DD，默认今天
            
        Returns:
            dict: {success: [], failed: []}
        """
        from backend.scripts.data_update.update_daily_from_snapshot import update_daily_prices_from_snapshot
        from datetime import date as date_type
        
        result = {"success": [], "failed": []}
        
        if end_date is None:
            end_date = datetime.now().strftime("%Y-%m-%d")
        
        logger.info(f"📥 开始批量更新前复权数据: {start_date} ~ {end_date}")
        
        # 获取主板池和基础池的股票代码（只更新这些股票）
        stock_codes = self._get_focus_stock_codes()
        if stock_codes:
            logger.info(f"📊 将更新 {len(stock_codes)} 只股票（主板池 + 基础池）")
        else:
            logger.warning("⚠️ 无法获取股票池，将更新全市场股票")
        
        # 生成日期列表
        from datetime import datetime, timedelta
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        
        current = start_dt
        while current <= end_dt:
            # 跳过周末
            if current.weekday() >= 5:
                current += timedelta(days=1)
                continue
            
            date_str = current.strftime("%Y-%m-%d")
            try:
                target_date = date_type.fromisoformat(date_str)
                success = update_daily_prices_from_snapshot(
                    target_date=target_date,
                    stock_codes=stock_codes,  # 传入股票代码列表
                    task_type='backfill'
                )
                if success:
                    result["success"].append(date_str)
                else:
                    result["failed"].append(date_str)
                
                # 限速，避免请求过快
                time.sleep(1)
                
            except Exception as e:
                logger.error(f"❌ 更新 {date_str} 前复权数据失败: {e}")
                result["failed"].append(date_str)
            
            current += timedelta(days=1)
        
        logger.info(f"📊 批量更新完成: 成功 {len(result['success'])} 天, 失败 {len(result['failed'])} 天")
        return result
    
    def _get_focus_stock_codes(self) -> Optional[List[str]]:
        """
        获取关注的股票代码列表（主板池 + 基础池）
        
        Returns:
            List[str]: 股票代码列表（6位数字格式），如果获取失败返回None
        """
        try:
            from backend.services.stock.stock_universe_service import StockUniverseService
            
            universe_service = StockUniverseService()
            stock_codes_set = set()
            
            # 1. 获取主板池
            try:
                mainboard_codes = universe_service.get_universe_stocks(
                    universe_type='mainboard',
                    trade_date=None,  # 使用最新日期
                    active_only=True
                )
                if mainboard_codes:
                    # 转换为6位数字格式
                    for code in mainboard_codes:
                        clean_code = code.replace('.SH', '').replace('.SZ', '').replace('.BJ', '')
                        if len(clean_code) == 6:
                            stock_codes_set.add(clean_code)
                    logger.info(f"  ✅ 主板池: {len(mainboard_codes)} 只")
            except Exception as e:
                logger.warning(f"  ⚠️ 获取主板池失败: {e}")
            
            # 2. 获取基础池
            try:
                base_codes = universe_service.get_universe_stocks(
                    universe_type='base',
                    trade_date=None,  # 使用最新日期
                    active_only=True
                )
                if base_codes:
                    # 转换为6位数字格式
                    for code in base_codes:
                        clean_code = code.replace('.SH', '').replace('.SZ', '').replace('.BJ', '')
                        if len(clean_code) == 6:
                            stock_codes_set.add(clean_code)
                    logger.info(f"  ✅ 基础池: {len(base_codes)} 只")
            except Exception as e:
                logger.warning(f"  ⚠️ 获取基础池失败: {e}")
            
            # 合并去重后的结果
            if stock_codes_set:
                stock_codes = sorted(list(stock_codes_set))
                logger.info(f"📊 合并后股票总数: {len(stock_codes)} 只（主板池 + 基础池去重）")
                return stock_codes
            else:
                logger.warning("⚠️ 未获取到任何股票池数据")
                return None
                
        except Exception as e:
            logger.error(f"❌ 获取关注股票列表失败: {e}", exc_info=True)
            return None
    
    def check_missing_data(self, days: int = 5) -> List[str]:
        """
        检查最近N天内缺失的交易日数据
        
        Args:
            days: 检查最近N天
            
        Returns:
            List[str]: 缺失数据的日期列表
        """
        missing_dates = []
        today = datetime.now().date()
        
        # 优先使用PostgreSQL仓库检查
        try:
            from backend.services.data.postgres_warehouse import PostgresWarehouse
            pg_warehouse = PostgresWarehouse()
            if pg_warehouse._initialized:
                latest_date_str = pg_warehouse.get_latest_stocks_date()
                if latest_date_str:
                    latest_date = datetime.strptime(latest_date_str, "%Y-%m-%d").date()
                    logger.info(f"📊 PostgreSQL最新数据日期: {latest_date_str}")
                    
                    # 检查从最新日期到今天之间的工作日
                    for i in range(days):
                        check_date = today - timedelta(days=i)
                        # 跳过周末
                        if check_date.weekday() >= 5:
                            continue
                        # 跳过今天（可能还没收盘）
                        if check_date == today:
                            continue
                        # 如果检查日期晚于最新数据日期，则缺失
                        if check_date > latest_date:
                            missing_dates.append(check_date.strftime("%Y-%m-%d"))
                    
                    return missing_dates
        except Exception as e:
            logger.warning(f"⚠️ PostgreSQL检查失败，使用文件仓库: {e}")
        
        # 降级：使用文件仓库检查
        for i in range(days):
            check_date = today - timedelta(days=i)
            # 跳过周末
            if check_date.weekday() >= 5:
                continue
            
            date_str = check_date.strftime("%Y-%m-%d")
            existing_data = self.warehouse.load_stocks_data(date_str)
            if existing_data is None or existing_data.empty:
                missing_dates.append(date_str)
        
        return missing_dates
    
    def update_missing_dates(self, days: int = 5, force: bool = False) -> dict:
        """
        增量更新缺失日期的数据（只更新缺失的日期，不重复获取）
        
        使用统一的更新脚本（Tushare优先 + 分层处理）
        
        Args:
            days: 检查最近N天
            force: 是否强制更新（不检查是否缺失，直接更新最近N天的所有交易日）
            
        Returns:
            dict: 更新结果 {success: [], failed: [], skipped: []}
        """
        result = {"success": [], "failed": [], "skipped": []}
        
        if force:
            # 强制更新模式：不检查缺失，直接获取最近N天的所有交易日
            logger.info(f"🔄 强制更新模式：将更新最近 {days} 天的所有交易日数据")
            today = datetime.now().date()
            update_dates = []
            
            for i in range(days):
                check_date = today - timedelta(days=i)
                # 跳过周末
                if check_date.weekday() >= 5:
                    continue
                # 跳过今天（可能还没收盘）
                if check_date == today:
                    continue
                update_dates.append(check_date.strftime("%Y-%m-%d"))
            
            # 从旧到新排序
            update_dates.sort()
            logger.info(f"📥 将强制更新以下日期: {update_dates}")
        else:
            # 正常模式：只更新缺失的日期
            update_dates = self.check_missing_data(days=days)
            
            if not update_dates:
                logger.info("✅ 数据完整，无需增量更新")
                return result
            
            logger.info(f"📥 开始增量更新 {len(update_dates)} 个缺失日期: {update_dates}")
        
        # 获取主板池和基础池的股票代码（只更新这些股票）
        stock_codes = self._get_focus_stock_codes()
        if stock_codes:
            logger.info(f"📊 将更新 {len(stock_codes)} 只股票（主板池 + 基础池）")
        else:
            logger.warning("⚠️ 无法获取股票池，将更新全市场股票")
        
        # 使用统一的更新脚本
        from backend.scripts.data_update.update_daily_from_snapshot import update_daily_prices_from_snapshot
        from datetime import date as date_type
        
        for date_str in update_dates:
            try:
                target_date = date_type.fromisoformat(date_str)
                success = update_daily_prices_from_snapshot(
                    target_date=target_date,
                    stock_codes=stock_codes,  # 传入股票代码列表
                    task_type='backfill'
                )
                if success:
                    result["success"].append(date_str)
                    logger.info(f"✅ 已更新 {date_str} 的日数据")
                else:
                    result["failed"].append(date_str)
                    logger.warning(f"⚠️ 更新 {date_str} 失败")
                    
                # 限速，避免请求过快
                time.sleep(1)
                
            except Exception as e:
                logger.error(f"❌ 更新 {date_str} 异常: {e}")
                result["failed"].append(date_str)
        
        logger.info(f"📊 增量更新完成: 成功 {len(result['success'])}, 失败 {len(result['failed'])}")
        return result
    
    def start_scheduler(self):
        """启动调度服务"""
        with self._start_lock:
            if self.running:
                logger.warning("⚠️ 调度服务已在运行")
                return

            # 启动时检查数据完整性并自动补充
            missing_dates = self.check_missing_data(days=5)
            if missing_dates:
                logger.warning("=" * 60)
                logger.warning("⚠️ 检测到最近交易日数据缺失！")
                logger.warning(f"   缺失日期: {', '.join(missing_dates)}")
                logger.warning("   正在自动补充缺失数据...")
                logger.warning("=" * 60)

                # 在后台线程自动补充缺失数据
                self._update_thread = threading.Thread(
                    target=self.update_missing_dates,
                    args=(5,),
                    daemon=True
                )
                self._update_thread.start()
            else:
                logger.info("✅ 数据完整性检查通过，最近5个交易日数据完整")

            self.running = True
            self.scheduler_thread = threading.Thread(target=self._scheduler_loop, daemon=True)
            self.scheduler_thread.start()

            # 启动定时任务检查线程（每分钟检查一次）
            self.task_check_thread = threading.Thread(target=self._task_check_loop, daemon=True)
            self.task_check_thread.start()

            logger.info("🚀 数据调度服务已启动")
    
    def stop_scheduler(self):
        """停止调度服务"""
        self.running = False
        if self.scheduler_thread:
            self.scheduler_thread.join(timeout=5)
        if self.task_check_thread:
            self.task_check_thread.join(timeout=5)
        logger.info("🛑 数据调度服务已停止")
    
    def _task_check_loop(self):
        """定时任务检查循环（每分钟检查一次）"""
        while self.running:
            try:
                self._check_and_run_scheduled_tasks()
                # 等待60秒后再次检查
                time.sleep(60)
            except Exception as e:
                logger.error(f"定时任务检查循环异常: {e}", exc_info=True)
                time.sleep(60)
    
    def _check_and_run_scheduled_tasks(self):
        """检查并执行定时任务"""
        try:
            from data_warehouse.service.warehouse_service import WarehouseService
            from data_warehouse.models.scheduled_task import DimScheduledTask
            
            ws = WarehouseService()
            session = ws.get_session()
            
            try:
                # 获取所有启用的任务
                tasks = session.query(DimScheduledTask).filter(
                    DimScheduledTask.is_enabled == True
                ).all()
                
                now = datetime.now()
                current_time = now.time()
                # Python的weekday(): 0=周一, 1=周二, ..., 6=周日
                # schedule_days使用: 1=周一, 2=周二, ..., 7=周日
                current_weekday = now.weekday() + 1
                
                for task in tasks:
                    # 跳过正在运行的任务
                    if task.is_running:
                        continue
                    
                    # 检查时间是否匹配
                    if not task.schedule_time:
                        continue
                    
                    try:
                        # 解析时间（格式：HH:MM）
                        schedule_hour, schedule_minute = map(int, task.schedule_time.split(':'))
                        schedule_time = dt_time(schedule_hour, schedule_minute)
                        
                        # 检查是否在指定时间的同一分钟内
                        if current_time.hour != schedule_time.hour or current_time.minute != schedule_time.minute:
                            continue
                    except Exception as e:
                        logger.warning(f"解析任务时间失败 {task.task_name}: {e}")
                        continue
                    
                    # 检查日期是否匹配
                    if task.schedule_days:
                        should_run = False
                        try:
                            # 解析日期配置（如：1-5 或 1,3,5）
                            if '-' in task.schedule_days:
                                # 范围格式：1-5
                                start_day, end_day = map(int, task.schedule_days.split('-'))
                                should_run = start_day <= current_weekday <= end_day
                            elif ',' in task.schedule_days:
                                # 列表格式：1,3,5
                                days = [int(d.strip()) for d in task.schedule_days.split(',')]
                                should_run = current_weekday in days
                            else:
                                # 单个日期
                                should_run = current_weekday == int(task.schedule_days)
                        except Exception as e:
                            logger.warning(f"解析任务日期失败 {task.task_name}: {e}")
                            should_run = False
                        
                        if not should_run:
                            continue
                    
                    # 检查是否今天已经执行过（避免重复执行）
                    if task.last_run_at:
                        last_run_date = task.last_run_at.date()
                        today = now.date()
                        if last_run_date == today:
                            continue
                    
                    # ✅ 验证任务类型配置（防止配置错误）
                    EXPECTED_TASK_TYPES = {
                        'daily_update': 'daily_update',
                        'fundamental_update': 'fundamental_update',
                        'refresh_snapshot': 'refresh_snapshot',
                        'sector_heat_update': 'sector_heat_update',
                        'sector_leaders_update': 'sector_leaders_update',
                        'sync_stock': 'sync_stock',
                        'sync_trade_calendar': 'sync_trade_calendar',
                        'guba_popularity_crawl_morning': 'guba_popularity_crawl',
                        'guba_popularity_crawl_noon': 'guba_popularity_crawl',
                        'limit_up_volume_shrink': 'limit_up_volume_shrink',
                        'recommendation_daily_track': 'recommendation_daily_track',
                        'recommendation_auto_close': 'recommendation_auto_close',
                        's1_universe_update': 's1_universe_update',
                        'industry_cycle_collect': 'industry_cycle_collect',
                        'industry_cycle_suggest': 'industry_cycle_suggest',
                        'pe_pb_update': 'pe_pb_update',
                        'abnormal_analysis_scan': 'abnormal_analysis_scan',
                        'limit_up_emotion_update': 'limit_up_emotion_update',
                    }
                    
                    expected_type = EXPECTED_TASK_TYPES.get(task.task_name)
                    if expected_type and task.task_type != expected_type:
                        logger.error(f"⚠️  任务类型配置错误: {task.task_name}")
                        logger.error(f"   任务名称: {task.task_display_name} ({task.task_name})")
                        logger.error(f"   期望类型: {expected_type}")
                        logger.error(f"   实际类型: {task.task_type}")
                        logger.error(f"   跳过执行，请运行修复脚本: python backend/scripts/data_update/fix_scheduled_task_config.py")
                        continue
                    
                    # 执行任务：先提取所需字段（避免后台线程访问 ORM 对象导致 DetachedInstanceError）
                    task_name_val = str(task.task_name or "")
                    task_display_name_val = str(task.task_display_name or task_name_val)
                    task_type_val = str(task.task_type or "").strip()
                    logger.info(f"⏰ 执行定时任务: {task_display_name_val} ({task_name_val})")
                    logger.debug(f"   任务类型: {task_type_val}, 调度时间: {task.schedule_time}")
                    task.is_running = True
                    task.last_run_at = now
                    session.commit()
                    
                    # 在后台线程中执行任务（传入原始值，不传 ORM 对象，避免 DetachedInstanceError）
                    import threading
                    def run_task(task_name: str, task_display_name: str, task_type: str):
                        try:
                            if task_type == 'guba_popularity_crawl':
                                import sys
                                from pathlib import Path
                                project_root = Path(__file__).parent.parent.parent.parent
                                if str(project_root) not in sys.path:
                                    sys.path.insert(0, str(project_root))
                                from backend.scripts.crawler.guba_popularity_crawler import GubaPopularityCrawler
                                crawler = GubaPopularityCrawler(skip_api=True)
                                data = crawler.crawl(limit=100)
                                if data:
                                    crawler.save_to_database(data)
                                logger.info(f"✅ 任务执行完成: {task_display_name}")
                            elif task_type == 'sync_trade_calendar':
                                import sys
                                from pathlib import Path
                                project_root = Path(__file__).parent.parent.parent.parent
                                if str(project_root) not in sys.path:
                                    sys.path.insert(0, str(project_root))
                                from backend.scripts.data_update.sync_trade_calendar import sync_trade_calendar
                                sync_trade_calendar()
                                logger.info(f"✅ 任务执行完成: {task_display_name}")
                            elif task_type == 'abnormal_analysis_scan':
                                from backend.services.news.abnormal_analysis_service import AbnormalAnalysisService
                                abnormal_svc = AbnormalAnalysisService()
                                result = abnormal_svc.run_daily_scan(max_stocks=30)
                                logger.info(f"✅ 任务执行完成: {task_display_name}, 分析 {result.get('analyzed', 0)} 只, 保存 {result.get('saved', 0)} 只")
                            elif task_type == 'recommendation_daily_track':
                                from backend.services.recommendation.recommendation_tracker import RecommendationTracker
                                tracker = RecommendationTracker()
                                result = tracker.track_daily()
                                logger.info(f"✅ 任务执行完成: {task_display_name}, 追踪 {result.get('tracked', 0)} 只")
                            elif task_type == 'recommendation_auto_close':
                                from backend.services.recommendation.recommendation_tracker import RecommendationTracker
                                tracker = RecommendationTracker()
                                result = tracker.auto_close()
                                logger.info(f"✅ 任务执行完成: {task_display_name}, 平仓 {result.get('closed', 0)} 只")
                            else:
                                from backend.services.data.data_management_service import DataManagementService
                                data_management_service = DataManagementService()
                                data_management_service.trigger_data_update(task_type)
                                logger.info(f"✅ 任务执行完成: {task_display_name}")
                        except Exception as e:
                            logger.error(f"❌ 任务执行失败 {task_display_name}: {e}", exc_info=True)
                        finally:
                            try:
                                ws2 = WarehouseService()
                                session2 = ws2.get_session()
                                try:
                                    task2 = session2.query(DimScheduledTask).filter(
                                        DimScheduledTask.task_name == task_name
                                    ).first()
                                    if task2:
                                        task2.is_running = False
                                        session2.commit()
                                finally:
                                    session2.close()
                            except Exception as e:
                                logger.error(f"更新任务状态失败: {e}")
                    
                    thread = threading.Thread(
                        target=run_task,
                        args=(task_name_val, task_display_name_val, task_type_val),
                        daemon=True,
                    )
                    thread.start()
                    
            finally:
                session.close()
        except Exception as e:
            logger.error(f"检查定时任务失败: {e}", exc_info=True)
    
    def _scheduler_loop(self):
        """调度循环"""
        # 初始化推荐计算调度器
        try:
            from backend.services.recommendation.recommendation_scheduler import RecommendationScheduler
            recommendation_scheduler = RecommendationScheduler()
        except Exception as e:
            logger.warning(f"⚠️ 推荐计算调度器初始化失败: {e}，将跳过推荐计算")
            recommendation_scheduler = None
        
        # 初始化9:40监控调度器
        monitor_started_today = False
        try:
            from backend.services.monitor.monitor_near5_service import get_monitor_service
            monitor_service = get_monitor_service()
            logger.info("✅ 9:40监控服务初始化成功")
        except Exception as e:
            logger.warning(f"⚠️ 9:40监控服务初始化失败: {e}")
            monitor_service = None
        
        while self.running:
            try:
                # 检查是否到达推荐计算时间点
                current_time = datetime.now().time()
                snapshot_times = [
                    (dt_time(9, 15), "09:15"),
                    (dt_time(11, 30), "11:30"),
                    (dt_time(13, 0), "13:00"),
                    (dt_time(15, 0), "15:00")
                ]
                
                should_run_recommendation = False
                snapshot_time_str = None
                
                for snapshot_time, snapshot_time_str_val in snapshot_times:
                    # 检查是否在时间点前后5分钟内
                    time_diff = abs((current_time.hour * 60 + current_time.minute) - 
                                  (snapshot_time.hour * 60 + snapshot_time.minute))
                    if time_diff <= 5:  # 5分钟内
                        should_run_recommendation = True
                        snapshot_time_str = snapshot_time_str_val
                        break
                
                if should_run_recommendation and recommendation_scheduler:
                    try:
                        logger.info(f"⏰ 到达推荐计算时间点: {snapshot_time_str}")
                        recommendation_scheduler.run_recommendation_calculation(snapshot_time=snapshot_time_str)
                    except Exception as e:
                        logger.error(f"❌ 推荐计算失败: {e}", exc_info=True)
                
                # 9:35自动启动9:40监控
                if monitor_service:
                    now = datetime.now()
                    # 工作日9:35-9:39之间自动启动（只启动一次）
                    if (now.weekday() < 5 and 
                        now.hour == 9 and 35 <= now.minute <= 39 and 
                        not monitor_started_today):
                        status = monitor_service.get_status()
                        if not status['running']:
                            logger.info("⏰ 9:35 自动启动9:40未破分时监控...")
                            monitor_service.start_chain_monitor()
                            monitor_started_today = True
                    # 每天0点重置标记
                    if now.hour == 0 and now.minute < 5:
                        monitor_started_today = False
                
                if self.is_trading_time():
                    # 交易时间：每10分钟更新一次股票数据（优先easyquotation，包含换手率）
                    # ✅ 已禁用实时股票数据更新
                    # logger.info("📊 交易时间，更新股票数据（优先easyquotation，包含换手率）...")
                    # self.update_stocks_data()
                    
                    # 财务数据每天更新一次即可（实时性要求不高），在收盘后更新
                    # 这里不更新财务数据，避免阻塞
                    
                    # 等待10分钟
                    time.sleep(600)  # 10分钟 = 600秒
                else:
                    # 非交易时间：检查是否需要更新收盘数据
                    # ✅ 已禁用实时股票数据更新
                    # if self.should_use_closing_data():
                    #     today = datetime.now().strftime("%Y-%m-%d")
                    #     existing_data = self.warehouse.load_stocks_data(today)
                    #     if existing_data is None or existing_data.empty:
                    #         logger.info("📊 闭市时间，更新收盘数据...")
                    #         self.update_stocks_data()
                    
                    today = datetime.now().strftime("%Y-%m-%d")
                    
                    # 财务数据每月1号更新一次（财报每季度更新，每月检查一次足够）
                    current_day = datetime.now().day
                    current_hour = datetime.now().hour
                    if current_day == 1 and current_hour == 20:  # 每月1号晚上8点
                        if not hasattr(self, '_financial_updated_month') or self._financial_updated_month != datetime.now().month:
                            logger.info("📊 每月1号，更新财务数据（Tushare Pro）...")
                            self._financial_updated_month = datetime.now().month  # 标记本月已更新
                            financial_thread = threading.Thread(
                                target=self.update_financial_data,
                                args=(None, 500),  # 更新更多股票
                                daemon=True
                            )
                            financial_thread.start()
                    
                    # 更新资金流向数据（用于月度热点统计）
                    existing_moneyflow = self.warehouse.load_moneyflow_data(today)
                    if existing_moneyflow is None:
                        logger.info("📊 闭市时间，异步更新资金流向数据（Tushare Pro，用于月度热点统计）...")
                        moneyflow_thread = threading.Thread(
                            target=self.update_moneyflow_data,
                            daemon=True
                        )
                        moneyflow_thread.start()
                    
                    # 行业周期数据采集（每日 15:00 后执行一次，生成 cycle_data_YYYYMMDD.json）
                    if current_hour >= 15 and now.weekday() < 5 and (
                        not getattr(self, '_industry_cycle_collected_date', None) or
                        self._industry_cycle_collected_date != today
                    ):
                        logger.info("📊 闭市后，异步采集行业周期数据（子进程执行，用于规则引擎）...")
                        self._industry_cycle_collected_date = today
                        ic_thread = threading.Thread(
                            target=lambda: self.update_industry_cycle_data(use_subprocess=True),
                            daemon=True
                        )
                        ic_thread.start()
                    
                    # 板块日线每日更新（用于板块轮动/长期主题监控）；仅更新已收盘日
                    try:
                        from datetime import date as date_type
                        from data_warehouse.service.warehouse_service import WarehouseService
                        from backend.utils.trade_date_utils import get_latest_trade_date, is_trade_date
                        from backend.services.sector.sector_service import update_sector_daily_tushare
                        now = datetime.now()
                        today_date = date_type.fromisoformat(today)
                        ws = WarehouseService()
                        try:
                            # 15:00 后且当日为交易日则更新当日，否则更新上一交易日
                            if now.time() >= dt_time(15, 0) and is_trade_date(ws, today_date):
                                target_date = today_date
                            else:
                                target_date = get_latest_trade_date(ws, 10, today_date - timedelta(days=1)) or (today_date - timedelta(days=1))
                        finally:
                            ws.get_session().close()
                        target_str = target_date.strftime("%Y-%m-%d")
                        if not hasattr(self, '_sector_daily_updated_trade_date') or self._sector_daily_updated_trade_date != target_str:
                            logger.info("📊 闭市时间，异步更新板块日线（Tushare 申万行业，用于板块轮动）日期=%s...", target_str)
                            self._sector_daily_updated_trade_date = target_str
                            def _run_sector_daily():
                                try:
                                    update_sector_daily_tushare(target_date)
                                except Exception as e:
                                    logger.warning("板块日线更新失败: %s", e)
                            sector_daily_thread = threading.Thread(target=_run_sector_daily, daemon=True)
                            sector_daily_thread.start()
                    except ImportError as e:
                        logger.debug("板块日线更新不可用: %s", e)
                    
                    # 板块/主题新闻拉取与打标（方案第六步）；收盘后拉取当日/近1日新闻写入 fact_sector_event
                    try:
                        from datetime import date as date_type
                        from data_warehouse.service.warehouse_service import WarehouseService
                        from backend.utils.trade_date_utils import get_latest_trade_date, is_trade_date
                        from backend.services.sector.sector_news_service import fetch_sector_news_for_date
                        now = datetime.now()
                        today_date = date_type.fromisoformat(today)
                        ws = WarehouseService()
                        try:
                            if now.time() >= dt_time(15, 0) and is_trade_date(ws, today_date):
                                news_target_date = today_date
                            else:
                                news_target_date = get_latest_trade_date(ws, 10, today_date - timedelta(days=1)) or (today_date - timedelta(days=1))
                        finally:
                            ws.get_session().close()
                        news_target_str = news_target_date.strftime("%Y-%m-%d")
                        if not hasattr(self, '_sector_news_updated_trade_date') or self._sector_news_updated_trade_date != news_target_str:
                            logger.info("📊 闭市时间，异步拉取板块/主题新闻并打标（fact_sector_event）日期=%s...", news_target_str)
                            self._sector_news_updated_trade_date = news_target_str
                            def _run_sector_news():
                                try:
                                    fetch_sector_news_for_date(news_target_date, days_window=2)
                                except Exception as e:
                                    logger.warning("板块新闻拉取与打标失败: %s", e)
                            sector_news_thread = threading.Thread(target=_run_sector_news, daemon=True)
                            sector_news_thread.start()
                    except ImportError as e:
                        logger.debug("板块新闻拉取不可用: %s", e)
                    
                    # 每日更新股票池（收盘后更新一次）- 暂时禁用，手动触发
                    # if not hasattr(self, '_universe_updated_today') or self._universe_updated_today != today:
                    #     logger.info("📊 闭市时间，更新股票池...")
                    #     self._update_stock_universe(today)
                    #     self._universe_updated_today = today
                    pass  # 股票池更新暂时禁用，通过前端手动触发
                
                # 等待5分钟再检查
                time.sleep(300)  # 5分钟 = 300秒
                    
            except Exception as e:
                logger.error(f"❌ 调度循环异常: {e}", exc_info=True)
                time.sleep(60)  # 出错后等待1分钟再继续

