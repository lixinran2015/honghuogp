"""
市场数据服务
封装市场数据获取逻辑，提供统一的接口
优先从PostgreSQL数据仓库读取数据，如果数据仓库没有数据才实时查询
"""

import sys
from pathlib import Path
import pandas as pd
from typing import Dict, Optional, List
import logging
from datetime import date, datetime

from backend.models.stock_data import StockData
from backend.utils.data_sources import fetch_history_for_codes

# 初始化logger（需要在导入之前）
logger = logging.getLogger(__name__)

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# 导入实时数据获取器
try:
    from backend.services.data.realtime_fetcher import fetch_realtime_a_stock, fetch_index_data_safe
except ImportError as e:
    logger.warning(f"⚠️ 无法导入 realtime_fetcher: {e}")
    fetch_realtime_a_stock = None
    fetch_index_data_safe = None


class MarketDataService:
    """市场数据服务类"""
    
    def __init__(self):
        """初始化市场数据服务"""
        # 尝试初始化PostgreSQL数据仓库（延迟初始化，避免启动时阻塞）
        self.pg_warehouse = None
        try:
            from backend.services.data.postgres_warehouse import PostgresWarehouse
            self.pg_warehouse = PostgresWarehouse()
            # 测试连接（如果初始化成功）
            if self.pg_warehouse._initialized:
                latest_date = self.pg_warehouse.get_latest_stocks_date()
                if latest_date:
                    logger.info(f"✅ MarketDataService: PostgreSQL数据仓库可用（最新数据日期: {latest_date}）")
                else:
                    logger.debug("MarketDataService: PostgreSQL数据仓库无数据")
            else:
                logger.debug("MarketDataService: PostgreSQL数据仓库初始化失败，将使用实时查询")
                self.pg_warehouse = None
        except Exception as e:
            logger.debug(f"PostgreSQL数据仓库不可用: {e}，将使用实时查询")
            self.pg_warehouse = None
    
    def get_realtime_stocks(self, force_refresh: bool = False, use_warehouse: bool = True) -> pd.DataFrame:
        """
        获取实时股票数据
        优先从PostgreSQL数据仓库读取，如果数据仓库没有数据或force_refresh=True，则实时查询
        
        Args:
            force_refresh: 是否强制刷新（忽略数据仓库，直接实时查询）
            use_warehouse: 是否优先使用数据仓库（默认True）
            
        Returns:
            DataFrame: 实时股票数据，包含代码、名称、最新价、涨跌幅等字段
        """
        # 优先从数据仓库读取（PostgreSQL优先，文件数据仓库作为备选）
        warehouse_backup = None
        if use_warehouse and not force_refresh:
            # 1. 优先尝试PostgreSQL数据仓库
            if self.pg_warehouse and self.pg_warehouse._initialized:
                try:
                    latest_date = self.pg_warehouse.get_latest_stocks_date()
                    if latest_date:
                        target_date = latest_date
                        from datetime import timedelta
                        latest_date_obj = date.fromisoformat(latest_date)
                        days_diff = (date.today() - latest_date_obj).days
                        
                        if days_diff <= 3:  # 3天内的数据都可以用
                            logger.info(f"📦 从PostgreSQL数据仓库读取股票数据: {target_date}（{days_diff}天前）")
                            stock_data = self.pg_warehouse.load_stocks_data(target_date)
                            
                            if stock_data is not None and not stock_data.empty:
                                if len(stock_data) < 50:
                                    logger.warning(f"⚠️ PostgreSQL数据仓库只有 {len(stock_data)} 只股票，尝试文件数据仓库或实时查询")
                                    warehouse_backup = stock_data
                                else:
                                    logger.info(f"✅ 从PostgreSQL数据仓库获取到 {len(stock_data)} 只股票数据")
                                    if days_diff > 1:
                                        logger.warning(f"⚠️ 注意：使用的是 {days_diff} 天前的数据，建议运行增量更新")
                                    return stock_data
                except Exception as e:
                    logger.debug(f"PostgreSQL数据仓库读取失败: {e}，尝试文件数据仓库")
            
            # 2. 如果PostgreSQL不可用，尝试文件数据仓库
            try:
                from backend.services.data.data_warehouse import DataWarehouse
                file_warehouse = DataWarehouse()
                latest_date = file_warehouse.get_latest_stocks_date()
                if latest_date:
                    target_date = latest_date
                    from datetime import timedelta
                    latest_date_obj = date.fromisoformat(latest_date)
                    days_diff = (date.today() - latest_date_obj).days
                    
                    if days_diff <= 3:  # 3天内的数据都可以用
                        logger.info(f"📦 从文件数据仓库读取股票数据: {target_date}（{days_diff}天前）")
                        stock_data = file_warehouse.load_stocks_data(target_date)
                        
                        if stock_data is not None and not stock_data.empty:
                            logger.info(f"✅ 从文件数据仓库获取到 {len(stock_data)} 只股票数据")
                            if days_diff > 1:
                                logger.warning(f"⚠️ 注意：使用的是 {days_diff} 天前的数据，建议运行增量更新")
                            return stock_data
            except Exception as e:
                logger.debug(f"文件数据仓库读取失败: {e}，尝试实时查询")
        
        # 如果数据仓库没有数据或force_refresh=True，则实时查询
        try:
            if fetch_realtime_a_stock is None:
                logger.error("akshare_safe_wrapper 未安装或不可用")
                return pd.DataFrame()
            
            logger.info(f"📡 实时查询股票数据（force_refresh={force_refresh}）...")
            # 如果force_refresh=True，禁用缓存以确保获取最新数据
            stock_data = fetch_realtime_a_stock(cache=not force_refresh, force_refresh=force_refresh)
            
            if stock_data.empty:
                logger.warning("获取到的股票数据为空")
                # 如果实时查询失败，再次尝试从数据仓库读取（即使数据较旧）
                # 1. 优先尝试PostgreSQL数据仓库
                if use_warehouse and self.pg_warehouse and self.pg_warehouse._initialized:
                    try:
                        latest_date = self.pg_warehouse.get_latest_stocks_date()
                        if latest_date:
                            logger.info(f"📦 实时查询失败，尝试从PostgreSQL数据仓库读取: {latest_date}")
                            stock_data = self.pg_warehouse.load_stocks_data(latest_date)
                            if stock_data is not None and not stock_data.empty:
                                logger.info(f"✅ 从PostgreSQL数据仓库获取到 {len(stock_data)} 只股票数据（备用）")
                                return stock_data
                    except Exception as e:
                        logger.debug(f"从PostgreSQL数据仓库读取备用数据也失败: {e}")
                
                # 2. 如果PostgreSQL不可用，尝试文件数据仓库
                if use_warehouse:
                    try:
                        from backend.services.data.data_warehouse import DataWarehouse
                        file_warehouse = DataWarehouse()
                        latest_date = file_warehouse.get_latest_stocks_date()
                        if latest_date:
                            logger.info(f"📦 实时查询失败，尝试从文件数据仓库读取: {latest_date}")
                            stock_data = file_warehouse.load_stocks_data(latest_date)
                            if stock_data is not None and not stock_data.empty:
                                logger.info(f"✅ 从文件数据仓库获取到 {len(stock_data)} 只股票数据（备用）")
                                return stock_data
                    except Exception as e:
                        logger.debug(f"从文件数据仓库读取备用数据也失败: {e}")
                
                # 3. 如果之前保存了数据仓库的备用数据，使用它
                if 'warehouse_backup' in locals() and warehouse_backup is not None and not warehouse_backup.empty:
                    logger.info(f"✅ 使用数据仓库备用数据: {len(warehouse_backup)} 只股票")
                    return warehouse_backup
                
                return pd.DataFrame()
            
            logger.info(f"✅ 实时查询成功：{len(stock_data)} 只股票")
            
            # 数据质量检查：检查换手率字段
            if not stock_data.empty:
                turnover_cols = ['换手率', 'turnover_rate', 'turnover']
                has_valid_turnover = False
                for col in turnover_cols:
                    if col in stock_data.columns:
                        max_turnover = stock_data[col].max()
                        valid_count = (pd.to_numeric(stock_data[col], errors='coerce') > 0).sum()
                        if max_turnover > 0 and valid_count > len(stock_data) * 0.1:
                            has_valid_turnover = True
                            logger.info(f"✅ 换手率字段 '{col}' 有效（最大值: {max_turnover:.2f}%，有效数据: {valid_count}/{len(stock_data)}）")
                            break
                
                if not has_valid_turnover:
                    logger.warning("⚠️ 换手率数据无效，所有换手率字段的最大值都为0或有效数据不足10%")
            
            return stock_data
            
        except Exception as e:
            logger.error(f"获取实时股票数据失败: {type(e).__name__}: {str(e)}", exc_info=True)
            
            # 如果实时查询失败，尝试从数据仓库读取（备用）
            # 1. 优先尝试PostgreSQL数据仓库
            if use_warehouse and self.pg_warehouse and self.pg_warehouse._initialized:
                try:
                    latest_date = self.pg_warehouse.get_latest_stocks_date()
                    if latest_date:
                        logger.info(f"📦 实时查询异常，尝试从PostgreSQL数据仓库读取: {latest_date}")
                        stock_data = self.pg_warehouse.load_stocks_data(latest_date)
                        if stock_data is not None and not stock_data.empty:
                            logger.info(f"✅ 从PostgreSQL数据仓库获取到 {len(stock_data)} 只股票数据（备用）")
                            return stock_data
                except Exception as e2:
                    logger.debug(f"从PostgreSQL数据仓库读取备用数据也失败: {e2}")
            
            # 2. 如果PostgreSQL不可用，尝试文件数据仓库
            if use_warehouse:
                try:
                    from backend.services.data.data_warehouse import DataWarehouse
                    file_warehouse = DataWarehouse()
                    latest_date = file_warehouse.get_latest_stocks_date()
                    if latest_date:
                        logger.info(f"📦 实时查询异常，尝试从文件数据仓库读取: {latest_date}")
                        stock_data = file_warehouse.load_stocks_data(latest_date)
                        if stock_data is not None and not stock_data.empty:
                            logger.info(f"✅ 从文件数据仓库获取到 {len(stock_data)} 只股票数据（备用）")
                            return stock_data
                except Exception as e2:
                    logger.debug(f"从文件数据仓库读取备用数据也失败: {e2}")
            
            # 3. 如果之前保存了数据仓库的备用数据，使用它
            if 'warehouse_backup' in locals() and warehouse_backup is not None and not warehouse_backup.empty:
                logger.info(f"✅ 使用数据仓库备用数据: {len(warehouse_backup)} 只股票")
                return warehouse_backup
            
            return pd.DataFrame()

    def get_historical_kline(
        self,
        codes: List[str],
        days: int = 120,
        max_codes: int = 80,
        use_warehouse: bool = True,
        use_cache: bool = True,
    ) -> pd.DataFrame:
        """
        批量获取多只股票近期K线
        优先从PostgreSQL数据仓库读取，如果数据仓库没有数据才实时查询
        
        Args:
            codes: 股票代码列表
            days: 获取最近N天的数据
            max_codes: 最大股票数量
            use_warehouse: 是否优先使用数据仓库（默认True）
            use_cache: 是否使用缓存（默认True）
        """
        if not codes:
            return pd.DataFrame()
        
        unique_codes = []
        seen = set()
        for code in codes:
            norm = code.strip()
            if norm and norm not in seen:
                unique_codes.append(norm)
                seen.add(norm)
        
        codes_to_fetch = unique_codes[:max_codes]
        
        # 尝试从缓存获取
        if use_cache:
            try:
                from backend.services.service_manager import get_service_manager
                manager = get_service_manager()
                cached_df = manager.get_cached_kline(codes_to_fetch, days)
                if cached_df is not None:
                    logger.info(f"✅ K线缓存命中: {len(codes_to_fetch)} 只股票, {days} 天")
                    return cached_df
            except Exception as e:
                logger.debug(f"缓存查询失败: {e}")
        
        logger.info(f"📚 正在获取 {len(codes_to_fetch)} 只股票的历史K线数据（近 {days} 日）")
        
        # 优先从PostgreSQL数据仓库读取
        if use_warehouse and self.pg_warehouse and self.pg_warehouse._initialized:
            try:
                from sqlalchemy import text
                from datetime import datetime, timedelta
                
                session = self.pg_warehouse.warehouse_service.get_session()
                try:
                    # 先查询数据库中的最新日期
                    max_date_query = text("SELECT MAX(trade_date) FROM fact_daily_price_qfq")
                    max_date_result = session.execute(max_date_query)
                    max_date_in_db = max_date_result.scalar()
                    
                    if max_date_in_db is None:
                        logger.warning("⚠️ 数据库中无历史K线数据")
                        session.close()
                        # 继续尝试实时查询
                    else:
                        # 使用数据库中的最新日期作为end_date
                        end_date = min(datetime.now().date(), max_date_in_db)
                        start_date = end_date - timedelta(days=days + 30)  # 多取一些，确保有足够数据
                        
                        logger.info(f"🔍 数据库最新日期: {max_date_in_db}, 查询日期范围: {start_date} 到 {end_date}")
                    
                    # 转换股票代码格式（6位数字 -> ts_code格式）
                    ts_codes = []
                    for code in codes_to_fetch:
                        code_str = str(code).strip()
                        if code_str.startswith('6'):
                            ts_codes.append(f"{code_str}.SH")
                        elif code_str.startswith(('0', '3')):
                            ts_codes.append(f"{code_str}.SZ")
                        else:
                            ts_codes.append(code_str)
                    
                    # 从fact_daily_price_qfq表批量查询
                    query = text("""
                        SELECT 
                            ts_code,
                            trade_date,
                            open,
                            high,
                            low,
                            close,
                            vol,
                            amount,
                            change_pct,
                            turnover_rate
                        FROM fact_daily_price_qfq
                        WHERE ts_code = ANY(:ts_codes)
                            AND trade_date >= :start_date
                            AND trade_date <= :end_date
                        ORDER BY ts_code, trade_date DESC
                    """)
                    
                    if max_date_in_db is None:
                        raise ValueError("数据库中无历史K线数据")
                    
                    logger.info(f"🔍 执行历史K线SQL查询:")
                    logger.info(f"   - ts_codes数量: {len(ts_codes)}")
                    logger.info(f"   - ts_codes示例: {ts_codes[:5]}")
                    logger.info(f"   - start_date: {start_date}")
                    logger.info(f"   - end_date: {end_date}")
                    
                    result = session.execute(query, {
                        'ts_codes': ts_codes,
                        'start_date': start_date,
                        'end_date': end_date
                    })
                    
                    rows = []
                    row_count = 0
                    for row in result:
                        row_count += 1
                        # 转换ts_code为code格式（去掉.SH/.SZ）
                        code = row[0].replace('.SH', '').replace('.SZ', '').replace('.BJ', '')
                        rows.append({
                            'code': code,
                            'trade_date': row[1].strftime('%Y-%m-%d') if row[1] else None,
                            'open': float(row[2]) if row[2] else None,
                            'high': float(row[3]) if row[3] else None,
                            'low': float(row[4]) if row[4] else None,
                            'close': float(row[5]) if row[5] else None,
                            'volume': float(row[6]) if row[6] else None,  # vol -> volume
                            'amount': float(row[7]) if row[7] else None,
                            'pct_chg': float(row[8]) if row[8] else None,  # change_pct -> pct_chg
                            'turnover': float(row[9]) if row[9] else None,  # turnover_rate -> turnover
                            'source': 'warehouse'
                        })
                    
                    logger.info(f"🔍 SQL查询返回行数: {row_count}")
                    
                    if rows:
                        history_df = pd.DataFrame(rows)
                        logger.info(f"🔍 转换DataFrame后: {len(history_df)} 行, 列: {history_df.columns.tolist()}")
                        logger.info(f"🔍 数据示例（前3行）:\n{history_df.head(3)}")
                        # 只取最近days天的数据
                        history_df = history_df.groupby('code').head(days)
                        logger.info(f"✅ 从PostgreSQL数据仓库获取到 {len(history_df)} 条历史K线数据（{len(history_df['code'].unique())} 只股票）")
                        
                        # 存入缓存
                        if use_cache:
                            try:
                                from backend.services.service_manager import get_service_manager
                                manager = get_service_manager()
                                manager.set_cached_kline(codes_to_fetch, days, history_df)
                            except Exception as cache_err:
                                logger.debug(f"缓存存储失败: {cache_err}")
                        
                        return history_df
                    else:
                        logger.warning("⚠️ PostgreSQL数据仓库没有历史K线数据")
                finally:
                    session.close()
            except Exception as e:
                logger.error(f"❌ 从PostgreSQL数据仓库读取历史K线数据失败: {e}", exc_info=True)
        
        # 休市时间：如果数据仓库没有数据，不尝试实时查询
        from datetime import time as dt_time
        now = datetime.now()
        current_time = now.time()
        weekday = now.weekday()
        is_trading = (weekday < 5 and 
                     ((dt_time(9, 30) <= current_time <= dt_time(11, 30)) or 
                      (dt_time(13, 0) <= current_time <= dt_time(15, 0))))
        
        if not is_trading:
            logger.info("🔵 休市时间，数据仓库没有历史K线数据，不尝试实时查询")
            return pd.DataFrame()
        
        # 交易时间：如果数据仓库没有数据，使用实时查询
        try:
            logger.info(f"🔍 调用实时API获取历史K线: codes={len(codes_to_fetch)}, days={days}, max_codes={max_codes}")
            logger.info(f"🔍 股票代码示例: {codes_to_fetch[:5]}")
            history_df = fetch_history_for_codes(codes_to_fetch, limit=days, max_codes=max_codes)
            if history_df.empty:
                logger.warning("⚠️ 实时API返回的历史K线数据为空")
            else:
                logger.info(f"✅ 从实时API获取到 {len(history_df)} 条历史K线数据")
                logger.info(f"🔍 数据列: {history_df.columns.tolist()}")
                logger.info(f"🔍 数据示例（前3行）:\n{history_df.head(3)}")
            return history_df
        except Exception as exc:
            logger.error(f"❌ 获取历史K线数据失败: {exc}", exc_info=True)
            return pd.DataFrame()
    
    def get_market_summary(self) -> Dict[str, Dict[str, any]]:
        """
        获取市场概况（指数数据）
        
        Returns:
            dict: 包含上证指数、深证成指、创业板指的数据
            格式：
            {
                "sse": {"name": "上证指数", "value": float, "changePct": float},
                "szse": {"name": "深证成指", "value": float, "changePct": float},
                "cyb": {"name": "创业板指", "value": float, "changePct": float}  # 可选
            }
        """
        try:
            # 优先尝试使用 akshare 直接获取
            try:
                import akshare as ak
                logger.info("📡 尝试从 akshare 直接获取指数数据...")
                index_data = ak.stock_zh_index_spot_sina()
                if index_data is not None and not index_data.empty:
                    logger.info(f"✅ 从 akshare 获取到 {len(index_data)} 个指数数据")
                else:
                    raise ValueError("akshare 返回数据为空")
            except Exception as e:
                logger.warning(f"⚠️ 从 akshare 直接获取失败: {e}，尝试使用安全包装器...")
                # 如果直接获取失败，使用安全包装器
                if fetch_index_data_safe is None:
                    logger.error("akshare_safe_wrapper 未安装或不可用")
                    return {
                        "sse": {"name": "上证指数", "value": 0.0, "changePct": 0.0},
                        "szse": {"name": "深证成指", "value": 0.0, "changePct": 0.0}
                    }
                
                logger.info("📡 使用安全包装器获取指数数据...")
                index_data = fetch_index_data_safe()
            
            if index_data.empty:
                logger.warning("获取到的指数数据为空")
                return {
                    "sse": {"name": "上证指数", "value": 0.0, "changePct": 0.0},
                    "szse": {"name": "深证成指", "value": 0.0, "changePct": 0.0}
                }
            
            result = {}
            
            # 提取上证指数
            sh_index = index_data[index_data['名称'].str.contains('上证', na=False)]
            if not sh_index.empty:
                result['sse'] = {
                    "name": "上证指数",
                    "value": float(sh_index.iloc[0]['最新价']) if '最新价' in sh_index.columns else 0.0,
                    "changePct": float(sh_index.iloc[0]['涨跌幅']) if '涨跌幅' in sh_index.columns else 0.0
                }
            else:
                result['sse'] = {"name": "上证指数", "value": 0.0, "changePct": 0.0}
            
            # 提取深证成指
            sz_index = index_data[index_data['名称'].str.contains('深证', na=False)]
            if not sz_index.empty:
                result['szse'] = {
                    "name": "深证成指",
                    "value": float(sz_index.iloc[0]['最新价']) if '最新价' in sz_index.columns else 0.0,
                    "changePct": float(sz_index.iloc[0]['涨跌幅']) if '涨跌幅' in sz_index.columns else 0.0
                }
            else:
                result['szse'] = {"name": "深证成指", "value": 0.0, "changePct": 0.0}
            
            # 提取创业板指（可选）
            cyb_index = index_data[index_data['名称'].str.contains('创业板', na=False)]
            if not cyb_index.empty:
                result['cyb'] = {
                    "name": "创业板指",
                    "value": float(cyb_index.iloc[0]['最新价']) if '最新价' in cyb_index.columns else 0.0,
                    "changePct": float(cyb_index.iloc[0]['涨跌幅']) if '涨跌幅' in cyb_index.columns else 0.0
                }
            
            logger.info(f"成功获取指数数据：{len(result)} 个指数")
            return result
            
        except Exception as e:
            logger.error(f"获取市场概况失败: {type(e).__name__}: {str(e)}", exc_info=True)
            return {
                "sse": {"name": "上证指数", "value": 0.0, "changePct": 0.0},
                "szse": {"name": "深证成指", "value": 0.0, "changePct": 0.0}
            }
    
    def get_realtime_stocks_as_models(self, force_refresh: bool = False, use_warehouse: bool = True) -> List[StockData]:
        """
        获取实时股票数据（返回StockData模型列表）
        优先从PostgreSQL数据仓库读取，如果数据仓库没有数据或force_refresh=True，则实时查询
        
        Args:
            force_refresh: 是否强制刷新（忽略数据仓库，直接实时查询）
            use_warehouse: 是否优先使用数据仓库（默认True）
            
        Returns:
            List[StockData]: 股票数据模型列表
        """
        # 先获取DataFrame
        df = self.get_realtime_stocks(force_refresh=force_refresh, use_warehouse=use_warehouse)
        
        # 转换为StockData模型列表
        if df.empty:
            return []
        
        return StockData.from_dataframe(df)

