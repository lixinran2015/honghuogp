"""
AkShare 日线数据源（降级方案）
当 Tushare 不可用时使用
"""
import logging
from typing import List, Optional
import pandas as pd
from datetime import datetime, timedelta

from .base import DailyDataSource

logger = logging.getLogger(__name__)


class AkshareDailySource(DailyDataSource):
    """AkShare 日线数据源（降级方案）"""
    
    def __init__(self):
        """初始化 AkShare 数据源"""
        try:
            import akshare as ak
            self.ak = ak
            self.available = True
            logger.info("✅ AkshareDailySource 初始化成功")
        except ImportError:
            logger.error("❌ akshare 未安装，请运行: pip install akshare")
            self.available = False
            self.ak = None
        except Exception as e:
            logger.error(f"❌ AkshareDailySource 初始化失败: {e}")
            self.available = False
            self.ak = None
    
    def get_daily_snapshot(
        self,
        date: Optional[str] = None,
        codes: Optional[List[str]] = None
    ) -> pd.DataFrame:
        """
        获取当日基础快照数据（使用 AkShare）
        
        Args:
            date: 日期，格式 YYYYMMDD，如果为None则使用今天
            codes: 股票代码列表，如果为None则获取全市场
            
        Returns:
            DataFrame: 标准化的快照数据
        """
        if not self.available:
            logger.error("❌ AkshareDailySource 不可用")
            return pd.DataFrame()
        
        try:
            # 1. 确定日期
            if date is None:
                date = datetime.now().strftime("%Y%m%d")
            
            # 2. 休市时间检查：如果codes为None（全市场），不尝试获取实时数据
            from datetime import time as dt_time
            now = datetime.now()
            current_time = now.time()
            weekday = now.weekday()
            is_trading = (weekday < 5 and 
                         ((dt_time(9, 30) <= current_time <= dt_time(11, 30)) or 
                          (dt_time(13, 0) <= current_time <= dt_time(15, 0))))
            
            if not is_trading and codes is None:
                logger.info("🔵 休市时间，不尝试获取全市场实时数据")
                return pd.DataFrame()
            
            # 3. 如果指定了代码，批量获取
            if codes:
                frames = []
                total = len(codes)
                
                for idx, code in enumerate(codes, 1):
                    try:
                        # 使用 AkShare 获取日线数据
                        df = self.ak.stock_zh_a_hist(
                            symbol=code,
                            period="daily",
                            start_date=date,
                            end_date=date,
                            adjust="qfq"  # 前复权
                        )
                        
                        if df.empty:
                            continue
                        
                        # 标准化字段
                        df['code'] = code
                        df.rename(columns={
                            '日期': 'trade_date',
                            '开盘': 'open',
                            '收盘': 'close',
                            '最高': 'high',
                            '最低': 'low',
                            '成交量': 'volume',
                            '成交额': 'amount',
                            '涨跌幅': 'pct_chg',
                            '换手率': 'turnover_rate',
                        }, inplace=True)
                        
                        frames.append(df)
                        
                        # 进度提示
                        if idx % 50 == 0 or idx == total:
                            logger.info(f"📊 AkShare日线获取进度: {idx}/{total} ({idx*100//total}%)")
                        
                        # 限速
                        if idx < total:
                            import time
                            time.sleep(0.1)
                            
                    except Exception as e:
                        logger.warning(f"⚠️ 获取 {code} 日线数据失败: {e}")
                        continue
                
                if not frames:
                    return pd.DataFrame()
                
                df_all = pd.concat(frames, ignore_index=True)
                logger.info(f"✅ 从AkShare获取到 {len(df_all)} 条日线数据")
                return df_all
            else:
                # 全市场：使用实时行情接口
                logger.info("📥 从AkShare获取全市场实时行情...")
                df = self.ak.stock_zh_a_spot_em()
                
                if df.empty:
                    logger.warning("⚠️ AkShare 全市场数据为空")
                    return df
                
                # 标准化字段
                df.rename(columns={
                    '代码': 'code',
                    '名称': 'name',
                    '最新价': 'close',
                    '今开': 'open',
                    '最高': 'high',
                    '最低': 'low',
                    '成交量': 'volume',
                    '成交额': 'amount',
                    '涨跌幅': 'pct_chg',
                    '换手率': 'turnover_rate',
                }, inplace=True)
                
                # 添加 trade_date
                df['trade_date'] = pd.to_datetime(date, format='%Y%m%d')
                
                logger.info(f"✅ 从AkShare获取到 {len(df)} 条全市场数据")
                return df
                
        except Exception as e:
            logger.error(f"❌ AkShare获取日线数据失败: {e}", exc_info=True)
            return pd.DataFrame()
    
    def get_history_kline(
        self,
        codes: List[str],
        start_date: str,
        end_date: str,
        freq: str = "D"
    ) -> pd.DataFrame:
        """
        获取多只股票的历史K线数据（使用 AkShare）
        
        Args:
            codes: 股票代码列表（6位数字格式）
            start_date: 开始日期，格式 YYYYMMDD
            end_date: 结束日期，格式 YYYYMMDD
            freq: 频率，默认 "D"（日线）
            
        Returns:
            DataFrame: 包含 code, trade_date, open, high, low, close, vol, amount
        """
        if not self.available:
            logger.error("❌ AkshareDailySource 不可用")
            return pd.DataFrame()
        
        try:
            frames = []
            total = len(codes)
            
            for idx, code in enumerate(codes, 1):
                try:
                    # 使用 AkShare 获取历史数据
                    df = self.ak.stock_zh_a_hist(
                        symbol=code,
                        period="daily",
                        start_date=start_date,
                        end_date=end_date,
                        adjust="qfq"  # 前复权
                    )
                    
                    if df.empty:
                        continue
                    
                    # 标准化字段
                    df['code'] = code
                    df.rename(columns={
                        '日期': 'trade_date',
                        '开盘': 'open',
                        '收盘': 'close',
                        '最高': 'high',
                        '最低': 'low',
                        '成交量': 'volume',
                        '成交额': 'amount',
                        '涨跌幅': 'pct_chg',
                    }, inplace=True)
                    
                    # 转换日期格式
                    if 'trade_date' in df.columns:
                        df['trade_date'] = pd.to_datetime(df['trade_date'])
                    
                    frames.append(df)
                    
                    # 进度提示
                    if idx % 50 == 0 or idx == total:
                        logger.info(f"📊 AkShare历史K线获取进度: {idx}/{total} ({idx*100//total}%)")
                    
                    # 限速
                    if idx < total:
                        import time
                        time.sleep(0.1)
                        
                except Exception as e:
                    logger.warning(f"⚠️ 获取 {code} 历史K线失败: {e}")
                    continue
            
            if not frames:
                return pd.DataFrame()
            
            # 合并所有数据
            df_all = pd.concat(frames, ignore_index=True)
            
            logger.info(f"✅ 从AkShare获取到 {len(df_all)} 条历史K线数据（{len(codes)} 只股票）")
            return df_all
            
        except Exception as e:
            logger.error(f"❌ AkShare获取历史K线失败: {e}", exc_info=True)
            return pd.DataFrame()

