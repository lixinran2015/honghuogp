"""
Tushare 数据源实现（非实时主源）
用于获取历史K线和日线快照数据
"""
import os
import logging
from typing import List, Optional
import pandas as pd
from datetime import datetime

from .base import DailyDataSource

logger = logging.getLogger(__name__)


class TushareDailySource(DailyDataSource):
    """Tushare 日线数据源"""
    
    def __init__(self, token: Optional[str] = None):
        """
        初始化 Tushare 数据源
        
        Args:
            token: Tushare token，如果为None则从config读取
        """
        try:
            import tushare as ts
            
            # 从环境变量或config读取token
            if not token:
                from data_warehouse.config import TUSHARE_TOKEN
                token = TUSHARE_TOKEN
            
            if not token:
                raise RuntimeError("TUSHARE_TOKEN 未配置，请设置环境变量或config.json")
            
            ts.set_token(token)
            self.pro = ts.pro_api()
            self.available = True
            logger.info("✅ TushareDailySource 初始化成功")
            
        except ImportError:
            logger.error("❌ tushare 未安装，请运行: pip install tushare")
            self.available = False
            self.pro = None
        except Exception as e:
            logger.error(f"❌ TushareDailySource 初始化失败: {e}")
            self.available = False
            self.pro = None
    
    def get_daily_snapshot(
        self,
        date: Optional[str] = None,
        codes: Optional[List[str]] = None
    ) -> pd.DataFrame:
        """
        获取当日基础快照数据
        
        Args:
            date: 日期，格式 YYYYMMDD，如果为None则使用今天
            codes: 股票代码列表，如果为None则获取全市场
            
        Returns:
            DataFrame: 标准化的快照数据
        """
        if not self.available:
            logger.error("❌ TushareDailySource 不可用")
            return pd.DataFrame()
        
        try:
            # 1. 确定日期
            if date is None:
                date = datetime.now().strftime("%Y%m%d")
            
            # 2. 转换代码格式
            ts_codes = None
            if codes:
                ts_codes = [self._norm_to_ts_code(c) for c in codes]
            
            # 3. 获取当日行情
            logger.info(f"📥 从Tushare获取日线数据: date={date}, codes={len(ts_codes) if ts_codes else 'all'}")
            
            if ts_codes:
                # 批量查询（Tushare支持逗号分隔）
                df_daily = self.pro.daily(
                    trade_date=date,
                    ts_code=",".join(ts_codes[:500])  # Tushare单次最多500只
                )
            else:
                df_daily = self.pro.daily(trade_date=date)
            
            if df_daily.empty:
                logger.warning(f"⚠️ Tushare daily 无数据: date={date}")
                return df_daily
            
            # 4. 获取基础信息（换手率等）
            try:
                df_basic = self.pro.daily_basic(trade_date=date)
                if not df_basic.empty:
                    # 合并数据
                    df_daily = pd.merge(
                        df_daily, 
                        df_basic[['ts_code', 'turnover_rate', 'volume_ratio', 'pe', 'pb']],
                        on='ts_code',
                        how='left'
                    )
            except Exception as e:
                logger.warning(f"⚠️ 获取daily_basic失败: {e}")
            
            # 5. 标准化字段名
            df_daily.rename(columns={
                'ts_code': 'code',
                'trade_date': 'trade_date',
                'close': 'close',
                'open': 'open',
                'high': 'high',
                'low': 'low',
                'pre_close': 'pre_close',
                'vol': 'volume',
                'amount': 'amount',
                'pct_chg': 'pct_chg',
                'change': 'change',
            }, inplace=True)
            
            # 6. 转换代码格式（去掉.SH/.SZ后缀）
            if 'code' in df_daily.columns:
                df_daily['code'] = df_daily['code'].str.replace('.SH', '').str.replace('.SZ', '').str.replace('.BJ', '')
            
            # 7. 转换日期格式
            if 'trade_date' in df_daily.columns:
                df_daily['trade_date'] = pd.to_datetime(df_daily['trade_date'], format='%Y%m%d')
            
            logger.info(f"✅ 从Tushare获取到 {len(df_daily)} 条日线数据")
            return df_daily
            
        except Exception as e:
            logger.error(f"❌ Tushare获取日线数据失败: {e}", exc_info=True)
            return pd.DataFrame()
    
    def get_history_kline(
        self,
        codes: List[str],
        start_date: str,
        end_date: str,
        freq: str = "D"
    ) -> pd.DataFrame:
        """
        获取多只股票的历史K线数据（按日期批量获取，速度快）
        
        Args:
            codes: 股票代码列表（6位数字格式）
            start_date: 开始日期，格式 YYYYMMDD
            end_date: 结束日期，格式 YYYYMMDD
            freq: 频率，默认 "D"（日线）
            
        Returns:
            DataFrame: 包含 code, trade_date, open, high, low, close, vol, amount
        """
        if not self.available:
            logger.error("❌ TushareDailySource 不可用")
            return pd.DataFrame()
        
        try:
            import time
            from datetime import datetime, timedelta
            
            # 转换代码为ts_code格式用于筛选
            ts_codes_set = set()
            code_map = {}  # ts_code -> 6位code
            for code in codes:
                ts_code = self._norm_to_ts_code(code)
                ts_codes_set.add(ts_code)
                code_map[ts_code] = code
            
            # 按日期批量获取（每天一次请求，获取全市场数据）
            frames = []
            start_dt = datetime.strptime(start_date, '%Y%m%d')
            end_dt = datetime.strptime(end_date, '%Y%m%d')
            current = start_dt
            
            total_days = (end_dt - start_dt).days + 1
            day_count = 0
            
            logger.info(f"📥 Tushare批量获取K线: {len(codes)} 只股票, {total_days} 天")
            
            while current <= end_dt:
                trade_date = current.strftime('%Y%m%d')
                day_count += 1
                
                # 跳过周末
                if current.weekday() >= 5:
                    current += timedelta(days=1)
                    continue
                
                try:
                    # 一次获取全市场当天数据
                    df = self.pro.daily(trade_date=trade_date)
                    
                    if df is not None and not df.empty:
                        # 筛选目标股票
                        df = df[df['ts_code'].isin(ts_codes_set)]
                        if not df.empty:
                            # 添加6位code
                            df['code'] = df['ts_code'].map(code_map)
                            frames.append(df)
                    
                    # 进度提示（每10天显示一次）
                    if day_count % 10 == 0:
                        logger.info(f"📊 Tushare K线获取进度: {day_count}/{total_days} 天")
                    
                    # 限速
                    time.sleep(0.05)
                    
                except Exception as e:
                    logger.debug(f"⚠️ 获取 {trade_date} 数据失败: {e}")
                
                current += timedelta(days=1)
            
            if not frames:
                logger.warning("⚠️ Tushare未获取到K线数据")
                return pd.DataFrame()
            
            # 合并所有数据
            df_all = pd.concat(frames, ignore_index=True)
            
            # 标准化字段名
            df_all.rename(columns={
                'vol': 'volume',
            }, inplace=True)
            
            # 转换日期格式
            if 'trade_date' in df_all.columns:
                df_all['trade_date'] = pd.to_datetime(df_all['trade_date'], format='%Y%m%d')
            
            logger.info(f"✅ Tushare获取到 {len(df_all)} 条K线数据")
            
            logger.info(f"✅ 从Tushare获取到 {len(df_all)} 条历史K线数据（{len(codes)} 只股票）")
            return df_all
            
        except Exception as e:
            logger.error(f"❌ Tushare获取历史K线失败: {e}", exc_info=True)
            return pd.DataFrame()
    
    @staticmethod
    def _norm_to_ts_code(code: str) -> str:
        """
        将6位数字代码转换为Tushare格式
        
        Args:
            code: 6位数字代码，如 '000001' 或 '600519'
            
        Returns:
            str: Tushare格式代码，如 '000001.SZ' 或 '600519.SH'
        """
        code = str(code).strip()
        
        # 如果已经是ts_code格式，直接返回
        if '.' in code:
            return code
        
        # 根据首位数字判断交易所
        if code.startswith('6'):
            return f"{code}.SH"
        elif code.startswith(('0', '3')):
            return f"{code}.SZ"
        elif code.startswith(('8', '4')):
            return f"{code}.BJ"
        else:
            # 默认深交所
            return f"{code}.SZ"

