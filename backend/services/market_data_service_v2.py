"""
市场数据服务（重构版）
统一数据访问入口，上层只和这个服务打交道
"""
from typing import List, Optional, Dict
import logging
import pandas as pd
from datetime import datetime, date, time as dt_time

from .data_sources.baostock_source import BaostockDailySource
from .data_sources.akshare_daily_source import AkshareDailySource
from .data_sources.realtime_source import SinaRealtimeSource
from backend.models.stock_data import StockData

logger = logging.getLogger(__name__)


def is_trading_time() -> bool:
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
    
    # 交易时间段：9:30-11:30, 13:00-15:00
    trading_start_am = dt_time(9, 30)
    trading_end_am = dt_time(11, 30)
    trading_start_pm = dt_time(13, 0)
    trading_end_pm = dt_time(15, 0)
    
    # 检查是否在交易时间段内
    is_am = trading_start_am <= current_time <= trading_end_am
    is_pm = trading_start_pm <= current_time <= trading_end_pm
    
    return is_am or is_pm


class MarketDataService:
    """
    市场数据服务（统一入口）
    
    职责：
    - 非实时数据：通过 BaostockDailySource 获取（快照+历史），降级到 AkshareDailySource
    - 实时数据：通过 SinaRealtimeSource 获取（仅用于补丁）
    """
    
    def __init__(self):
        """初始化服务"""
        # 主数据源：Baostock（免费、稳定、无权限门槛）
        self.daily_source = None
        try:
            baostock_source = BaostockDailySource()
            if baostock_source.available:
                self.daily_source = baostock_source
                logger.info("✅ 使用 BaostockDailySource 作为主数据源")
            else:
                raise Exception("BaostockDailySource 不可用")
        except Exception as e:
            logger.warning(f"⚠️ BaostockDailySource 不可用: {e}，尝试降级方案")
            # 降级方案：AkShare
            try:
                akshare_source = AkshareDailySource()
                if akshare_source.available:
                    self.daily_source = akshare_source
                    logger.info("✅ 使用 AkshareDailySource 作为降级数据源")
                else:
                    logger.error("❌ 所有数据源都不可用")
            except Exception as e2:
                logger.error(f"❌ AkshareDailySource 初始化失败: {e2}")
                self.daily_source = None
        
        # 数据仓库：用于获取最新交易日收盘价
        self.pg_warehouse = None
        try:
            from backend.services.data.postgres_warehouse import PostgresWarehouse
            self.pg_warehouse = PostgresWarehouse()
            if self.pg_warehouse._initialized:
                latest_date = self.pg_warehouse.get_latest_stocks_date()
                if latest_date:
                    logger.info(f"✅ PostgreSQL数据仓库可用（最新数据日期: {latest_date}）")
                else:
                    logger.debug("PostgreSQL数据仓库无数据")
            else:
                logger.debug("PostgreSQL数据仓库初始化失败")
                self.pg_warehouse = None
        except Exception as e:
            logger.debug(f"PostgreSQL数据仓库不可用: {e}")
            self.pg_warehouse = None
        
        # 实时源：新浪 + 腾讯 fallback
        try:
            self.realtime_source = SinaRealtimeSource()
            if not self.realtime_source.available:
                logger.warning("⚠️ SinaRealtimeSource 不可用，将无法获取实时数据")
        except Exception as e:
            logger.warning(f"⚠️ SinaRealtimeSource 初始化失败: {e}，实时补丁功能将不可用")
            self.realtime_source = None
    
    # ========== 非实时数据接口（给定时任务+策略用） ==========
    
    def get_daily_snapshot_df(
        self,
        date: Optional[str] = None,
        codes: Optional[List[str]] = None
    ) -> pd.DataFrame:
        """
        获取当日基础快照数据（用于策略计算）
        
        Args:
            date: 日期，格式 YYYYMMDD 或 YYYY-MM-DD，如果为None则使用今天
            codes: 股票代码列表（6位数字格式），如果为None则获取全市场
            
        Returns:
            DataFrame: 标准化的快照数据，包含 code, name, close, open, high, low, 
                      volume, amount, turnover_rate, pct_chg 等字段
        """
        # 统一日期格式为 YYYYMMDD
        if date:
            date = date.replace('-', '')
        else:
            date = datetime.now().strftime("%Y%m%d")
        
        # 休市时间：优先使用数据仓库，不尝试实时数据源
        if not is_trading_time():
            if self.pg_warehouse and self.pg_warehouse._initialized:
                try:
                    # 从数据仓库获取最新交易日数据
                    latest_date = self.pg_warehouse.get_latest_stocks_date()
                    if latest_date:
                        logger.info(f"🔵 休市时间，从数据仓库获取快照数据: {latest_date}")
                        df = self.pg_warehouse.load_stocks_data(latest_date, stock_codes=codes)
                        if df is not None and not df.empty:
                            # 标准化列名
                            if '代码' in df.columns and 'code' not in df.columns:
                                df['code'] = df['代码']
                            if '当前价' in df.columns and 'close' not in df.columns:
                                df['close'] = df['当前价']
                            logger.info(f"✅ 从数据仓库获取到 {len(df)} 条快照数据")
                            return df
                except Exception as e:
                    logger.warning(f"⚠️ 从数据仓库获取快照数据失败: {e}")
            
            # 如果数据仓库不可用，返回空（休市时间不尝试实时数据源）
            logger.info("🔵 休市时间，数据仓库不可用，返回空数据")
            return pd.DataFrame()
        
        # 交易时间：使用日线数据源
        if not self.daily_source or not self.daily_source.available:
            logger.error("❌ 日线数据源不可用")
            return pd.DataFrame()
        
        # 使用主数据源（Baostock）
        df = self.daily_source.get_daily_snapshot(date=date, codes=codes)
        
        # 如果失败，尝试降级方案（已在初始化时处理，这里只记录日志）
        if df.empty:
            logger.warning("⚠️ 主数据源获取失败，数据为空")
        
        # 数据清洗和验证
        if not df.empty:
            # 填充缺失值
            numeric_cols = ['close', 'open', 'high', 'low', 'volume', 'amount', 'pct_chg', 'turnover_rate']
            for col in numeric_cols:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
            
            # 过滤无效数据
            df = df[df['close'] > 0]
        
        return df
    
    def _get_kline_from_postgres(
        self,
        codes: List[str],
        start_date: str,
        end_date: str
    ) -> pd.DataFrame:
        """
        从 PostgreSQL 数据库获取历史K线数据（批量查询，高效）
        
        Args:
            codes: 股票代码列表
            start_date: 开始日期 YYYYMMDD
            end_date: 结束日期 YYYYMMDD
            
        Returns:
            DataFrame: K线数据
        """
        if not self.pg_warehouse or not self.pg_warehouse._initialized:
            return pd.DataFrame()
        
        try:
            # 格式化日期为 YYYY-MM-DD
            start_fmt = f"{start_date[:4]}-{start_date[4:6]}-{start_date[6:8]}"
            end_fmt = f"{end_date[:4]}-{end_date[4:6]}-{end_date[6:8]}"
            
            # 使用批量查询方法（一条SQL）
            df = self.pg_warehouse.load_history_kline_batch(codes, start_fmt, end_fmt)
            if df is not None and not df.empty:
                return df
            
        except Exception as e:
            logger.debug(f"PostgreSQL K线查询异常: {e}")
        
        return pd.DataFrame()
    
    def get_history_kline_df(
        self,
        codes: List[str],
        start_date: str,
        end_date: str,
        use_cache: bool = True
    ) -> pd.DataFrame:
        """
        获取多只股票的历史K线数据（用于策略计算）
        
        Args:
            codes: 股票代码列表（6位数字格式）
            start_date: 开始日期，格式 YYYYMMDD 或 YYYY-MM-DD
            end_date: 结束日期，格式 YYYYMMDD 或 YYYY-MM-DD
            use_cache: 是否使用缓存（默认True）
            
        Returns:
            DataFrame: 包含 code, trade_date, open, high, low, close, volume, amount
        """
        # 计算天数（用于缓存键）
        try:
            from datetime import datetime
            start_dt = datetime.strptime(start_date.replace('-', ''), '%Y%m%d')
            end_dt = datetime.strptime(end_date.replace('-', ''), '%Y%m%d')
            days = (end_dt - start_dt).days
        except:
            days = 120
        
        # 尝试从缓存获取
        if use_cache:
            try:
                from backend.services.service_manager import get_service_manager
                manager = get_service_manager()
                cached_df = manager.get_cached_kline(codes, days)
                if cached_df is not None:
                    logger.info(f"✅ K线缓存命中: {len(codes)} 只股票, {days} 天")
                    return cached_df
            except Exception as e:
                logger.debug(f"缓存查询失败: {e}")
        
        # 统一日期格式为 YYYYMMDD
        start_date = start_date.replace('-', '')
        end_date = end_date.replace('-', '')
        
        # 优先从 PostgreSQL 数据库获取历史K线
        df = pd.DataFrame()
        if self.pg_warehouse and self.pg_warehouse._initialized:
            try:
                df = self._get_kline_from_postgres(codes, start_date, end_date)
                if not df.empty:
                    logger.info(f"✅ 从PostgreSQL获取K线: {len(df)} 条记录, {len(codes)} 只股票")
            except Exception as e:
                logger.debug(f"PostgreSQL K线查询失败: {e}")
        
        # 如果数据库没有足够数据，优先使用 Tushare 批量接口，降级到 Baostock
        if df.empty or len(df) < len(codes) * 10:  # 至少每只股票10条记录
            # 1. 优先使用 Tushare 批量接口（速度快）
            try:
                from backend.services.data_sources.tushare_source import TushareDailySource
                tushare = TushareDailySource()
                if tushare.available:
                    logger.info(f"📥 从Tushare补充K线数据: {len(codes)} 只股票")
                    tushare_df = tushare.get_history_kline(codes, start_date, end_date)
                    if not tushare_df.empty:
                        df = pd.concat([df, tushare_df], ignore_index=True).drop_duplicates(subset=['code', 'trade_date'])
                        logger.info(f"✅ Tushare补充了 {len(tushare_df)} 条K线数据")
            except Exception as e:
                logger.debug(f"Tushare K线获取失败: {e}")
            
            # 2. 如果仍然不足，降级到 Baostock（慢但稳定）
            if df.empty or len(df) < len(codes) * 10:
                if not self.daily_source or not self.daily_source.available:
                    logger.warning("⚠️ Baostock 不可用，返回已有数据")
                    return df if not df.empty else pd.DataFrame()
                
                logger.info(f"📥 从Baostock补充K线数据: {len(codes)} 只股票")
                baostock_df = self.daily_source.get_history_kline(codes, start_date, end_date)
                if not baostock_df.empty:
                    df = pd.concat([df, baostock_df], ignore_index=True).drop_duplicates(subset=['code', 'trade_date'])
        
        # 存入缓存
        if use_cache and not df.empty:
            try:
                from backend.services.service_manager import get_service_manager
                manager = get_service_manager()
                manager.set_cached_kline(codes, days, df)
            except Exception as e:
                logger.debug(f"缓存存储失败: {e}")
        
        # 数据清洗
        if not df.empty:
            numeric_cols = ['open', 'high', 'low', 'close', 'volume', 'amount', 'pct_chg']
            for col in numeric_cols:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        
        return df
    
    # ========== 实时数据接口（给推荐接口补丁用） ==========
    
    def patch_realtime_to_recommendations(
        self,
        recommendations: List[Dict]
    ) -> List[Dict]:
        """
        给推荐结果补上最新交易日的收盘价数据
        
        优先使用日线数据源获取最新交易日收盘价，如果不可用则使用实时行情接口
        
        Args:
            recommendations: 推荐列表，每个元素包含 'code' 字段
            
        Returns:
            List[Dict]: 补充最新数据后的推荐列表
        """
        if not recommendations:
            return recommendations
        
        # 提取股票代码
        codes = []
        for rec in recommendations:
            code = rec.get('code', '')
            if code:
                # 确保是6位数字格式
                code = str(code).strip().replace('.SH', '').replace('.SZ', '').replace('.BJ', '')
                if len(code) == 6:
                    codes.append(code)
        
        if not codes:
            logger.warning("⚠️ 没有有效的股票代码，跳过数据补丁")
            return recommendations
        
        logger.debug(f"🔍 数据补丁：提取到 {len(codes)} 只股票代码: {codes[:5]}")
        
        # 优先方案1：从数据仓库获取最新交易日收盘价
        # 交易时间：优先使用实时数据，数据仓库作为备用
        # 休市时间：使用数据仓库
        data_map = {}
        use_warehouse = False
        trading_now = is_trading_time()
        
        # 交易时间优先使用实时数据
        if trading_now:
            logger.info(f"🔴 交易时间，优先使用实时数据接口")
        
        try:
            if not trading_now and self.pg_warehouse and self.pg_warehouse._initialized:
                latest_date = self.pg_warehouse.get_latest_stocks_date()
                if latest_date:
                    from datetime import date, timedelta
                    try:
                        latest_date_obj = date.fromisoformat(latest_date)
                        days_diff = (date.today() - latest_date_obj).days
                        
                        # 休市时间：使用数据仓库
                        if days_diff <= 5:
                            use_warehouse = True
                            if not is_trading_time():
                                logger.info(f"🔵 休市时间，从数据仓库获取最新交易日收盘价: {latest_date}（{days_diff}天前）, {len(codes)} 只股票")
                            else:
                                logger.info(f"📦 从数据仓库获取最新交易日收盘价: {latest_date}（{days_diff}天前）, {len(codes)} 只股票")
                            # 转换codes为ts_code格式（用于查询数据仓库）
                            ts_codes = []
                            for code in codes:
                                code_str = str(code).strip()
                                if code_str.startswith('6'):
                                    ts_codes.append(f"{code_str}.SH")
                                elif code_str.startswith(('0', '3')):
                                    ts_codes.append(f"{code_str}.SZ")
                                else:
                                    ts_codes.append(code_str)
                            
                            df = self.pg_warehouse.load_stocks_data(latest_date, stock_codes=ts_codes)
                            
                            if df is not None and not df.empty:
                                # 检查列名（可能是code或ts_code）
                                code_col = 'code' if 'code' in df.columns else 'ts_code' if 'ts_code' in df.columns else None
                                
                                if code_col:
                                    logger.debug(f"🔍 数据补丁：从数据仓库获取到 {len(df)} 行数据，使用列: {code_col}")
                                    matched_count = 0
                                    for _, row in df.iterrows():
                                        code = str(row.get(code_col, '')).strip()
                                        # 处理 ts_code 格式（如 600499.SH）转换为 6 位数字
                                        if '.' in code:
                                            code = code.split('.')[0]
                                        
                                        if code and len(code) == 6 and code in codes:
                                            # 使用收盘价作为当前价
                                            close_price = float(row.get('close', 0) or row.get('最新价', 0) or 0)
                                            if close_price > 0:
                                                data_map[code] = {
                                                    'price': close_price,
                                                    'pct_chg': float(row.get('pct_chg', 0) or row.get('change_pct', 0) or row.get('涨跌幅', 0) or 0),
                                                    'turnover_rate': float(row.get('turnover_rate', 0) or row.get('换手率', 0) or 0),
                                                    'amount': float(row.get('amount', 0) or row.get('成交额', 0) or 0),
                                                    'volume': float(row.get('volume', 0) or row.get('vol', 0) or row.get('成交量', 0) or 0),
                                                }
                                                matched_count += 1
                                    logger.debug(f"🔍 数据补丁：匹配到 {matched_count} 只股票的数据")
                                else:
                                    logger.warning(f"⚠️ 数据仓库返回的DataFrame没有code列，列名: {list(df.columns)}")
                                
                                if data_map:
                                    logger.info(f"✅ 从数据仓库获取到 {len(data_map)} 只股票的最新收盘价（日期: {latest_date}）")
                        else:
                            logger.info(f"⚠️ 数据仓库数据过旧（{days_diff}天前），跳过数据仓库，使用日线数据源")
                    except Exception as date_err:
                        logger.warning(f"⚠️ 解析数据仓库日期失败: {date_err}，跳过数据仓库")
        except Exception as e:
            logger.warning(f"⚠️ 从数据仓库获取数据失败: {e}")
        
        # 优先方案2：如果数据仓库不可用或数据过旧，从日线数据源获取
        # 注意：休市时间直接使用数据仓库，不尝试日线数据源（避免网络请求）
        if not data_map or not use_warehouse:
            # 休市时间：只使用数据仓库，不尝试其他数据源
            if not is_trading_time():
                if not data_map:
                    logger.info("🔵 休市时间，仅使用数据仓库数据，不尝试其他数据源")
            else:
                # 交易时间：可以尝试日线数据源
                try:
                    if self.daily_source and self.daily_source.available:
                        logger.info(f"📥 从日线数据源获取最新交易日收盘价: {len(codes)} 只股票")
                        # 获取最新交易日数据（不指定日期，让数据源自动获取最新交易日）
                        df = self.get_daily_snapshot_df(codes=codes)
                        
                        if not df.empty and 'code' in df.columns:
                            for _, row in df.iterrows():
                                code = str(row.get('code', '')).strip()
                                if code and len(code) == 6:
                                    # 使用收盘价作为当前价
                                    close_price = float(row.get('close', 0) or 0)
                                    if close_price > 0:
                                        data_map[code] = {
                                            'price': close_price,
                                            'pct_chg': float(row.get('pct_chg', 0) or 0),
                                            'turnover_rate': float(row.get('turnover_rate', 0) or 0),
                                            'amount': float(row.get('amount', 0) or 0),
                                            'volume': float(row.get('volume', 0) or 0),
                                        }
                            
                            if data_map:
                                logger.info(f"✅ 从日线数据源获取到 {len(data_map)} 只股票的最新收盘价")
                except Exception as e:
                    logger.warning(f"⚠️ 从日线数据源获取数据失败: {e}")
        
        # 降级方案3：交易时间且数据仓库不可用时，尝试实时行情接口
        # 休市时间不尝试实时行情接口
        if not data_map and is_trading_time() and self.realtime_source and self.realtime_source.available:
            try:
                logger.info(f"📡 交易时间，日线数据不可用，尝试从实时行情接口获取: {len(codes)} 只股票")
                rt_map = self.realtime_source.get_realtime_quotes(codes)
                
                if rt_map:
                    for code, rt in rt_map.items():
                        data_map[code] = {
                            'price': rt.get('price', 0),
                            'pct_chg': rt.get('pct_chg', 0),
                            'turnover_rate': rt.get('turnover_rate', 0),
                            'amount': rt.get('amount', 0),
                            'volume': rt.get('volume', 0),
                        }
                    logger.info(f"✅ 从实时行情接口获取到 {len(data_map)} 只股票数据")
            except Exception as e:
                logger.warning(f"⚠️ 实时行情接口获取失败: {e}")
        
        # 更新推荐数据
        updated_count = 0
        for rec in recommendations:
            code = str(rec.get('code', '')).strip().replace('.SH', '').replace('.SZ', '').replace('.BJ', '')
            data = data_map.get(code)
            
            if data:
                # 更新字段
                rec['currentPrice'] = data.get('price', rec.get('currentPrice', 0))
                rec['changePct'] = data.get('pct_chg', rec.get('changePct', 0))
                rec['turnoverRate'] = f"{data.get('turnover_rate', 0):.2f}%"
                rec['amount'] = data.get('amount', rec.get('amount', 0))
                rec['volume'] = data.get('volume', rec.get('volume', 0))
                updated_count += 1
        
        if updated_count > 0:
            logger.info(f"✅ 数据补丁完成: {updated_count}/{len(recommendations)} 只股票")
        else:
            logger.warning(f"⚠️ 数据补丁失败: 未能更新任何股票数据")
        
        return recommendations
    
    # ========== 兼容旧接口（逐步废弃） ==========
    
    def get_realtime_stocks(self, force_refresh: bool = False, use_warehouse: bool = True) -> pd.DataFrame:
        """
        获取实时股票数据（兼容旧接口）
        
        注意：此方法已废弃，建议使用 get_daily_snapshot_df + patch_realtime_to_recommendations
        """
        logger.warning("⚠️ get_realtime_stocks 已废弃，建议使用 get_daily_snapshot_df")
        
        # 降级：使用日线快照数据
        return self.get_daily_snapshot_df()
    
    def get_historical_kline(
        self,
        codes: List[str],
        days: int = 120,
        max_codes: int = 100,
        use_warehouse: bool = True,
    ) -> pd.DataFrame:
        """
        获取历史K线数据（兼容旧接口）
        
        注意：此方法已废弃，建议使用 get_history_kline_df
        """
        logger.warning("⚠️ get_historical_kline 已废弃，建议使用 get_history_kline_df")
        
        # 计算日期范围
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - pd.Timedelta(days=days)).strftime("%Y%m%d")
        
        # 限制数量
        codes = codes[:max_codes]
        
        return self.get_history_kline_df(codes, start_date, end_date)
    
    def get_realtime_stocks_as_models(self, force_refresh: bool = False, use_warehouse: bool = True) -> List[StockData]:
        """
        获取实时股票数据（返回StockData模型列表）
        兼容旧接口，用于推荐API
        
        Args:
            force_refresh: 是否强制刷新（忽略数据仓库，直接实时查询）- 当前版本忽略此参数
            use_warehouse: 是否优先使用数据仓库（默认True）- 当前版本忽略此参数
            
        Returns:
            List[StockData]: 股票数据模型列表
        """
        # 获取日线快照数据（作为实时数据的替代）
        df = self.get_daily_snapshot_df()
        
        # 转换为StockData模型列表
        if df.empty:
            return []
        
        return StockData.from_dataframe(df)

