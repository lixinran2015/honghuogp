"""
Baostock 数据源实现（日线 & 历史K线主源）
免费、稳定、无权限门槛
"""
import logging
import threading
from typing import List, Optional
import pandas as pd
from datetime import datetime

from .base import DailyDataSource

logger = logging.getLogger(__name__)

try:
    import baostock as bs
    HAS_BAOSTOCK = True
except ImportError:
    HAS_BAOSTOCK = False
    logger.warning("⚠️ baostock 未安装，请运行: pip install baostock")

# 全局锁，保护 Baostock 连接（不支持并发）
_baostock_lock = threading.Lock()
_baostock_logged_in = False


class BaostockDailySource(DailyDataSource):
    """
    使用 Baostock 获取日线 & 历史 K 线
    
    注意：Baostock 的 code 格式为 sh.600000 / sz.000001
    注意：Baostock 不支持并发，使用全局锁保护
    """
    
    _instance = None
    _instance_lock = threading.Lock()
    
    def __new__(cls):
        """单例模式，避免多次登录"""
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super(BaostockDailySource, cls).__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """初始化 Baostock 数据源"""
        if self._initialized:
            return
        
        if not HAS_BAOSTOCK:
            raise RuntimeError("需要安装 baostock: pip install baostock")
        
        global _baostock_logged_in
        with _baostock_lock:
            if not _baostock_logged_in:
                lg = bs.login()
                if lg.error_code != "0":
                    raise RuntimeError(f"Baostock 登录失败: {lg.error_msg}")
                _baostock_logged_in = True
                logger.info("✅ Baostock 登录成功")
        
        self.available = True
        self._initialized = True
    
    def __del__(self):
        """析构时登出"""
        try:
            if HAS_BAOSTOCK and self.available:
                try:
                    import sys
                    import io
                    # 抑制 stderr 输出，避免显示 "Bad file descriptor" 等错误
                    old_stderr = sys.stderr
                    sys.stderr = io.StringIO()
                    bs.logout()
                    sys.stderr = old_stderr
                except Exception:
                    # 忽略登出时的所有错误
                    if 'sys' in locals():
                        sys.stderr = old_stderr
                    pass
        except Exception:
            pass
    
    def get_daily_snapshot(
        self,
        date: Optional[str] = None,
        codes: Optional[List[str]] = None
    ) -> pd.DataFrame:
        """
        获取当日基础快照数据
        
        Args:
            date: 日期，格式 YYYY-MM-DD 或 YYYYMMDD，如果为None则使用今天
            codes: 股票代码列表（6位数字格式），可选。不传则返回空DataFrame
            
        Returns:
            DataFrame: 标准化的快照数据
        """
        if not self.available:
            logger.error("❌ BaostockDailySource 不可用")
            return pd.DataFrame()
        
        # 确定日期
        if date is None:
            date = datetime.today().strftime("%Y-%m-%d")
        else:
            # 统一格式为 YYYY-MM-DD
            date = date.replace('-', '')
            if len(date) == 8:
                date = f"{date[:4]}-{date[4:6]}-{date[6:8]}"
        
        if not codes:
            logger.warning("⚠️ get_daily_snapshot 未传 codes，建议通过股票池先过滤一轮")
            return pd.DataFrame()
        
        logger.info(f"📥 从Baostock获取日线数据: date={date}, codes={len(codes)}")
        
        fields = (
            "date,code,open,high,low,close,preclose,volume,amount,"
            "turn,pctChg,isST"
        )
        
        frames = []
        success_count = 0
        failed_count = 0
        
        # 使用全局锁保护 Baostock 调用（不支持并发）
        with _baostock_lock:
            for idx, code in enumerate(codes, 1):
                try:
                    bs_code = self._to_bs_code(code)
                    
                    rs = bs.query_history_k_data_plus(
                        bs_code,
                        fields,
                        start_date=date,
                        end_date=date,
                        frequency="d",
                        adjustflag="2"  # 前复权
                    )
                    
                    if rs.error_code != "0":
                        logger.debug(f"⚠️ {code} 获取失败: {rs.error_msg}")
                        failed_count += 1
                        continue
                    
                    rows = []
                    while rs.next():
                        rows.append(rs.get_row_data())
                    
                    if not rows:
                        continue
                    
                    df = pd.DataFrame(rows, columns=rs.fields)
                    frames.append(df)
                    success_count += 1
                    
                    # 进度提示
                    if idx % 100 == 0 or idx == len(codes):
                        logger.info(f"📊 Baostock日线获取进度: {idx}/{len(codes)} ({idx*100//len(codes)}%)")
                    
                    # 限速（避免请求过快）
                    if idx < len(codes):
                        import time
                        time.sleep(0.05)  # 50ms延迟
                        
                except Exception as e:
                    logger.warning(f"⚠️ 获取 {code} 日线数据失败: {e}")
                    failed_count += 1
                    continue
        
        if not frames:
            logger.warning(f"⚠️ Baostock 当日快照无数据: date={date}, codes={len(codes)}")
            return pd.DataFrame()
        
        # 合并所有数据
        df_all = pd.concat(frames, ignore_index=True)
        
        # 标准化列名
        df_all.rename(columns={
            "date": "trade_date",
            "code": "bs_code",  # 暂存原始 baostock 代码
            "open": "open",
            "high": "high",
            "low": "low",
            "close": "close",
            "preclose": "pre_close",
            "volume": "volume",
            "amount": "amount",
            "turn": "turnover_rate",  # Baostock 的 turn 本身就是换手率(%)
            "pctChg": "pct_chg",
        }, inplace=True)
        
        # 加一个统一的 code 字段（6位数字格式）
        df_all["code"] = df_all["bs_code"].apply(self._from_bs_code)
        
        # 转换数据类型
        numeric_cols = ['open', 'high', 'low', 'close', 'pre_close', 'volume', 'amount', 'pct_chg', 'turnover_rate']
        for col in numeric_cols:
            if col in df_all.columns:
                df_all[col] = pd.to_numeric(df_all[col], errors='coerce').fillna(0)
        
        # 转换日期格式
        if 'trade_date' in df_all.columns:
            df_all['trade_date'] = pd.to_datetime(df_all['trade_date'])
        
        logger.info(f"✅ 从Baostock获取到 {len(df_all)} 条日线数据 (成功: {success_count}, 失败: {failed_count})")
        return df_all
    
    def get_history_kline(
        self,
        codes: List[str],
        start_date: str,
        end_date: str,
        freq: str = "D"
    ) -> pd.DataFrame:
        """
        获取多只股票的历史K线数据
        
        Args:
            codes: 股票代码列表（6位数字格式）
            start_date: 开始日期，格式 YYYYMMDD 或 YYYY-MM-DD
            end_date: 结束日期，格式 YYYYMMDD 或 YYYY-MM-DD
            freq: 频率，默认 "D"（日线），其他频率暂不支持
            
        Returns:
            DataFrame: 包含 code, trade_date, open, high, low, close, volume, amount
        """
        if not self.available:
            logger.error("❌ BaostockDailySource 不可用")
            return pd.DataFrame()
        
        # 统一日期格式为 YYYY-MM-DD
        if len(start_date) == 8:
            start_date = f"{start_date[:4]}-{start_date[4:6]}-{start_date[6:8]}"
        if len(end_date) == 8:
            end_date = f"{end_date[:4]}-{end_date[4:6]}-{end_date[6:8]}"
        
        fields = (
            "date,code,open,high,low,close,preclose,volume,amount,"
            "turn,pctChg,isST"
        )
        
        frames = []
        total = len(codes)
        success_count = 0
        failed_count = 0
        
        # 使用全局锁保护 Baostock 调用（不支持并发）
        with _baostock_lock:
            for idx, code in enumerate(codes, 1):
                try:
                    bs_code = self._to_bs_code(code)
                    
                    rs = bs.query_history_k_data_plus(
                        bs_code,
                        fields,
                        start_date=start_date,
                        end_date=end_date,
                        frequency="d",
                        adjustflag="2"  # 前复权
                    )
                    
                    if rs.error_code != "0":
                        logger.debug(f"⚠️ {code} 历史K线获取失败: {rs.error_msg}")
                        failed_count += 1
                        continue
                    
                    rows = []
                    while rs.next():
                        rows.append(rs.get_row_data())
                    
                    if not rows:
                        continue
                    
                    df = pd.DataFrame(rows, columns=rs.fields)
                    df['code'] = code  # 添加6位数字格式的code
                    frames.append(df)
                    success_count += 1
                    
                    # 进度提示
                    if idx % 50 == 0 or idx == total:
                        logger.info(f"📊 Baostock历史K线获取进度: {idx}/{total} ({idx*100//total}%)")
                    
                    # 限速
                    if idx < total:
                        import time
                        time.sleep(0.05)  # 50ms延迟
                        
                except Exception as e:
                    logger.warning(f"⚠️ 获取 {code} 历史K线失败: {e}")
                    failed_count += 1
                    continue
        
        if not frames:
            logger.warning(f"⚠️ Baostock 历史K线无数据: {start_date} ~ {end_date}")
            return pd.DataFrame()
        
        # 合并所有数据
        df_all = pd.concat(frames, ignore_index=True)
        
        # 标准化列名
        df_all.rename(columns={
            "date": "trade_date",
            "code": "bs_code",
            "open": "open",
            "high": "high",
            "low": "low",
            "close": "close",
            "preclose": "pre_close",
            "volume": "volume",
            "amount": "amount",
            "turn": "turnover_rate",
            "pctChg": "pct_chg",
        }, inplace=True)
        
        # 确保有统一的 code 字段（6位数字格式）
        if 'code' not in df_all.columns or df_all['code'].isna().any():
            df_all['code'] = df_all['bs_code'].apply(self._from_bs_code)
        
        # 转换数据类型
        numeric_cols = ['open', 'high', 'low', 'close', 'pre_close', 'volume', 'amount', 'pct_chg', 'turnover_rate']
        for col in numeric_cols:
            if col in df_all.columns:
                df_all[col] = pd.to_numeric(df_all[col], errors='coerce').fillna(0)
        
        # 转换日期格式
        if 'trade_date' in df_all.columns:
            df_all['trade_date'] = pd.to_datetime(df_all['trade_date'])
        
        logger.info(f"✅ 从Baostock获取到 {len(df_all)} 条历史K线数据 (成功: {success_count}, 失败: {failed_count})")
        return df_all
    
    # ------- 代码格式转换 -------
    
    @staticmethod
    def _to_bs_code(code: str) -> str:
        """
        将6位数字代码转换为Baostock格式
        
        Args:
            code: 6位数字代码，如 '600000' 或 '000001'
            
        Returns:
            str: Baostock格式代码，如 'sh.600000' 或 'sz.000001'
        """
        code = str(code).strip()
        
        # 如果已经是baostock格式，直接返回
        if '.' in code:
            return code
        
        # 根据首位数字判断交易所
        if code.startswith('6'):
            return f"sh.{code}"
        elif code.startswith(('0', '3')):
            return f"sz.{code}"
        elif code.startswith(('8', '4')):
            return f"bj.{code}"  # 北交所
        else:
            # 默认深交所
            return f"sz.{code}"
    
    @staticmethod
    def _from_bs_code(bs_code: str) -> str:
        """
        从Baostock格式还原成6位数字代码
        
        Args:
            bs_code: Baostock格式代码，如 'sh.600000' 或 'sz.000001'
            
        Returns:
            str: 6位数字代码，如 '600000' 或 '000001'
        """
        if '.' in bs_code:
            return bs_code.split(".")[1]
        return bs_code

