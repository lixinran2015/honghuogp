"""
数据初始化服务
用于初始化数据仓库，拉取近半年的历史数据
"""

import logging
from datetime import datetime, timedelta
from typing import List
import pandas as pd

from backend.services.data.data_warehouse import DataWarehouse
from backend.services.data.financial_data_fetcher import FinancialDataFetcher

# 初始化logger
logger = logging.getLogger(__name__)

# 导入akshare_safe_wrapper（位于项目根目录，与 backend 同级）
import sys
from pathlib import Path
_backend_dir = Path(__file__).resolve().parent.parent.parent  # backend/
_repo_root = _backend_dir.parent  # 项目根目录（akshare_safe_wrapper.py 所在）
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

try:
    from akshare_safe_wrapper import fetch_today_closing_data_akshare
except ImportError:
    try:
        archive_path = _repo_root / "archive" / "utils_20251124"
        if archive_path.exists():
            sys.path.insert(0, str(archive_path))
            from akshare_safe_wrapper import fetch_today_closing_data_akshare
            logger.info("✅ 从归档目录导入 akshare_safe_wrapper")
        else:
            raise ImportError("归档目录不存在")
    except ImportError:
        logger.warning("⚠️ 无法导入 akshare_safe_wrapper，数据更新功能可能受限（文件在项目根目录 akshare_safe_wrapper.py）")
        fetch_today_closing_data_akshare = None


class DataInitializer:
    """数据初始化服务类"""
    
    def __init__(self, warehouse: DataWarehouse = None):
        """
        初始化数据初始化服务
        
        Args:
            warehouse: 数据仓库实例
        """
        self.warehouse = warehouse or DataWarehouse()
        self.financial_fetcher = FinancialDataFetcher()
    
    def initialize_stocks_data(self, days: int = 180) -> int:
        """
        初始化股票数据（先获取今日数据，历史数据后续由调度服务自动补充）
        
        Args:
            days: 拉取天数（暂时只获取今日数据，历史数据由调度服务自动补充）
        
        Returns:
            int: 成功拉取的天数
        """
        try:
            logger.info(f"🚀 开始初始化股票数据...")
            
            # 先获取今日数据
            today = datetime.now().strftime("%Y-%m-%d")
            
            # 检查今日数据是否已存在
            existing_data = self.warehouse.load_stocks_data(today)
            if existing_data is not None and not existing_data.empty:
                logger.info(f"✅ 今日数据已存在: {today} ({len(existing_data)} 只股票)")
                return 1
            
            # 获取今日股票数据
            logger.info(f"📥 拉取今日股票数据: {today}...")
            
            # 导入数据获取函数（akshare_safe_wrapper 在项目根，已在模块顶部加入 repo_root）
            try:
                try:
                    from akshare_safe_wrapper import fetch_realtime_a_stock
                except ImportError:
                    _archive = _repo_root / "archive" / "utils_20251124"
                    if _archive.exists():
                        sys.path.insert(0, str(_archive))
                        from akshare_safe_wrapper import fetch_realtime_a_stock
                    else:
                        fetch_realtime_a_stock = None
                
                from backend.services.market_data_service import MarketDataService
                
                # 尝试获取今日数据
                market_service = MarketDataService()
                stock_data = market_service.get_realtime_stocks(force_refresh=True)
                
                if stock_data.empty:
                    # 如果实时数据为空，尝试使用akshare的收盘数据接口
                    logger.info("   实时数据为空，尝试获取收盘数据...")
                    if fetch_realtime_a_stock:
                        stock_data = fetch_realtime_a_stock(cache=True, force_refresh=False)
                
                if not stock_data.empty:
                    # 保存到数据仓库
                    success = self.warehouse.save_stocks_data(today, stock_data)
                    if success:
                        logger.info(f"✅ 成功保存今日股票数据: {today} ({len(stock_data)} 只股票)")
                        return 1
                    else:
                        logger.warning(f"⚠️ 保存今日股票数据失败: {today}")
                        return 0
                else:
                    logger.warning(f"⚠️ 无法获取今日股票数据: {today}")
                    return 0
                    
            except Exception as e:
                logger.error(f"❌ 获取今日股票数据失败: {e}", exc_info=True)
                return 0
            
        except Exception as e:
            logger.error(f"❌ 初始化股票数据失败: {e}", exc_info=True)
            return 0
    
    def initialize_financial_data(self, stock_codes: List[str] = None, limit: int = 200) -> int:
        """
        初始化财务数据
        
        Args:
            stock_codes: 股票代码列表，如果为None则从最新股票数据中获取
            limit: 限制拉取的股票数量，避免请求过多（默认200只）
        
        Returns:
            int: 成功拉取的股票数量
        """
        try:
            logger.info("🚀 开始初始化财务数据...")
            
            # 如果未提供股票代码，从最新股票数据中获取
            if stock_codes is None:
                latest_date = self.warehouse.get_latest_stocks_date()
                if latest_date is None:
                    logger.warning("⚠️ 没有股票数据，尝试先获取今日股票数据...")
                    # 先初始化股票数据
                    stocks_count = self.initialize_stocks_data(days=1)
                    if stocks_count == 0:
                        logger.warning("⚠️ 无法获取股票数据，无法初始化财务数据")
                        return 0
                    latest_date = self.warehouse.get_latest_stocks_date()
                
                stock_data = self.warehouse.load_stocks_data(latest_date)
                if stock_data is None or stock_data.empty:
                    logger.warning(f"⚠️ {latest_date} 的股票数据为空")
                    return 0
                
                # 提取股票代码（限制数量，避免请求过多）
                # 过滤掉北交所股票（bj开头）和非A股代码
                stock_codes = []
                for _, row in stock_data.iterrows():
                    code = row.get('代码', row.get('code', ''))
                    # 处理pandas Series的情况
                    if isinstance(code, pd.Series):
                        code = code.iloc[0] if len(code) > 0 else ''
                    if code and str(code) != 'nan' and str(code).strip():
                        # 只保留A股代码（sh/sz开头，或6位数字）
                        code_str = str(code)
                        if code_str.startswith('bj'):
                            continue  # 跳过北交所
                        if code_str.startswith('sh') or code_str.startswith('sz'):
                            stock_codes.append(code)
                        elif code_str.isdigit() and len(code_str) == 6:
                            # 6位数字代码，添加前缀
                            if code_str.startswith('6'):
                                stock_codes.append(f'sh{code_str}')
                            elif code_str.startswith('0') or code_str.startswith('3'):
                                stock_codes.append(f'sz{code_str}')
                    
                    if len(stock_codes) >= limit:
                        break
            
            if not stock_codes:
                logger.warning("⚠️ 没有股票代码，无法初始化财务数据")
                return 0
            
            logger.info(f"📊 准备拉取 {len(stock_codes)} 只股票的财务数据（限制{limit}只）...")
            
            # 获取今日日期
            today = datetime.now().strftime("%Y-%m-%d")
            
            # 检查今日财务数据是否已存在
            existing_financial = self.warehouse.load_financial_data(today)
            if existing_financial and len(existing_financial) >= min(len(stock_codes), limit) * 0.8:
                logger.info(f"✅ 今日财务数据已存在（{len(existing_financial)} 只），跳过初始化")
                return len(existing_financial)
            
            # 批量获取财务数据（延迟0.3秒，避免请求过快被限流）
            logger.info("   开始批量获取财务数据，这可能需要几分钟...")
            financial_data = self.financial_fetcher.batch_get_financial_data(
                stock_codes, 
                delay=0.3  # 每次请求延迟0.3秒，避免请求过快
            )
            
            if not financial_data:
                logger.warning("⚠️ 获取财务数据为空")
                return 0
            
            # 保存到数据仓库
            success = self.warehouse.save_financial_data(today, financial_data)
            
            if success:
                logger.info(f"✅ 财务数据初始化完成: {len(financial_data)} 只股票")
                return len(financial_data)
            else:
                logger.warning("⚠️ 保存财务数据失败")
                return 0
                
        except Exception as e:
            logger.error(f"❌ 初始化财务数据失败: {e}", exc_info=True)
            return 0
    
    def initialize_all(self, days: int = 180, financial_limit: int = 200) -> dict:
        """
        初始化所有数据
        
        Args:
            days: 拉取股票数据的天数（暂时只获取今日）
            financial_limit: 财务数据拉取数量限制
        
        Returns:
            dict: 初始化结果统计
        """
        logger.info("🚀 开始初始化数据仓库...")
        
        # 1. 初始化股票数据（先获取今日数据）
        stocks_count = self.initialize_stocks_data(days)
        
        # 2. 初始化财务数据（基于今日股票数据）
        financial_count = self.initialize_financial_data(limit=financial_limit)
        
        result = {
            'stocks_days': stocks_count,
            'financial_stocks': financial_count,
            'success': stocks_count > 0 or financial_count > 0
        }
        
        logger.info(f"✅ 数据仓库初始化完成: {result}")
        return result

