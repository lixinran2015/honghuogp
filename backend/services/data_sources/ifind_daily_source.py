"""
iFinDPy 日线数据源实现
使用 THS_HistoryQuotes 或 THS_DS 获取日线数据
"""
import logging
import threading
from typing import List, Optional
import pandas as pd
from datetime import datetime, date

from .base import DailyDataSource

logger = logging.getLogger(__name__)

# 使用统一的 iFinD 登录管理器
from backend.services.data_sources.ifind_login_manager import ensure_ifind_login


def ts_code_to_ifind_code(ts_code: str) -> str:
    """
    将 ts_code 转换为 iFinD 格式
    600519.SH -> 600519.SH
    000001.SZ -> 000001.SZ
    """
    # iFinD 格式与 ts_code 格式相同
    return ts_code


def code_to_ifind_code(code: str) -> str:
    """
    将6位数字代码转换为 iFinD 格式
    600519 -> 600519.SH
    000001 -> 000001.SZ
    """
    code = str(code).strip()
    
    # 如果已经是 ts_code 格式，直接返回
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


class IfindDailySource(DailyDataSource):
    """
    使用 iFinDPy 获取日线数据
    """
    
    _instance = None
    _instance_lock = threading.Lock()
    
    def __new__(cls):
        """单例模式，避免多次登录"""
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super(IfindDailySource, cls).__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """初始化 iFinDPy 数据源"""
        if hasattr(self, '_initialized') and self._initialized:
            return
        
        if not ensure_ifind_login():
            self.available = False
            self._initialized = True
            return
        
        self.available = True
        self._initialized = True
    
    def get_daily_snapshot(
        self,
        date: Optional[str] = None,
        codes: Optional[List[str]] = None
    ) -> pd.DataFrame:
        """
        获取当日基础快照数据
        
        Args:
            date: 日期，格式 YYYYMMDD 或 YYYY-MM-DD，如果为None则使用今天
            codes: 股票代码列表（6位数字格式），可选。不传则返回空DataFrame
            
        Returns:
            DataFrame: 标准化的快照数据，包含 code, name, close, open, high, low, vol, amount, turnover_rate, pct_chg
        """
        if not self.available:
            logger.error("❌ IfindDailySource 不可用")
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
            logger.warning("⚠️ get_daily_snapshot 未传 codes，返回空DataFrame")
            return pd.DataFrame()
        
        logger.info(f"📥 从 iFinDPy 获取日线数据: date={date}, codes={len(codes)}")
        
        try:
            from iFinDPy import THS_HQ
            
            all_data = []
            success_count = 0
            failed_count = 0
            
            # 优化批量处理：先尝试大批次，失败则自动减小批次重试
            # iFinDPy 支持一次请求多只股票，批次大小可以更大
            initial_batch_size = 500  # 初始批次大小（参考 Tushare 的500只限制）
            min_batch_size = 50  # 最小批次大小（避免太小）
            
            batch_size = initial_batch_size
            batch_idx = 0
            batch_num = 0
            
            while batch_idx < len(codes):
                batch_num += 1
                batch_codes = codes[batch_idx:batch_idx + batch_size]
                
                # 转换为 iFinD 格式
                ifind_codes = [code_to_ifind_code(code) for code in batch_codes]
                
                try:
                    # 使用 THS_HQ 获取日线数据（支持 format='format:dataframe'）
                    # pricetype:1 表示前复权
                    jsonparam = 'pricetype:1'
                    
                    # 构建股票代码字符串（逗号分隔）
                    thscode_str = ','.join(ifind_codes)
                    
                    # 获取指定日期的数据
                    result = THS_HQ(
                        thscode_str,
                        'open;high;low;close;volume;amount;turnoverRate;pctChg',
                        jsonparam,
                        date,
                        date,
                        format='format:dataframe'
                    )
                    
                    # 检查返回类型（可能是字典或对象）
                    if isinstance(result, dict):
                        errorcode = result.get('errorcode', -1)
                        errmsg = result.get('errmsg', '未知错误')
                        data = result.get('data')
                    else:
                        errorcode = getattr(result, 'errorcode', -1)
                        errmsg = getattr(result, 'errmsg', '未知错误')
                        data = getattr(result, 'data', None)
                    
                    if errorcode != 0:
                        # ✅ 检测使用量限制错误：如果达到使用量限制，立即停止尝试
                        errmsg_lower = errmsg.lower()
                        is_quota_exceeded = (
                            'exceeded' in errmsg_lower and 
                            ('150 million' in errmsg_lower or '150m' in errmsg_lower or 'usage' in errmsg_lower)
                        )
                        
                        if is_quota_exceeded:
                            logger.error(f"❌ iFinDPy 使用量已超限（每周1.5亿条），停止所有批次请求: {errmsg}")
                            # 标记所有剩余股票为失败
                            failed_count += len(codes) - batch_idx
                            break  # 立即退出循环，不再尝试
                        
                        # 如果批次太大导致失败，尝试减小批次重试
                        if batch_size > min_batch_size and len(batch_codes) == batch_size:
                            logger.warning(f"⚠️ 批次 {batch_num} ({len(batch_codes)}只) 获取失败，减小批次重试: {errmsg}")
                            batch_size = max(min_batch_size, batch_size // 2)  # 减半批次大小
                            continue  # 不移动 batch_idx，重试当前批次
                        else:
                            logger.warning(f"⚠️ 批次 {batch_num} ({len(batch_codes)}只) 获取失败: {errmsg}")
                            failed_count += len(batch_codes)
                            batch_idx += len(batch_codes)  # 跳过这批，继续下一批
                            continue
                    
                    # 解析返回数据
                    # THS_HQ 返回的 data 是 DataFrame（当 format='format:dataframe' 时）
                    if data is not None:
                        # 如果是 DataFrame，直接处理
                        if isinstance(data, pd.DataFrame):
                            df_batch = data.copy()
                            # 确保列名是小写
                            df_batch.columns = [col.lower() for col in df_batch.columns]
                            
                            # 检查必需的列
                            required_cols = ['thscode', 'time', 'open', 'high', 'low', 'close', 'volume', 'amount']
                            if not all(col in df_batch.columns for col in required_cols[:7]):  # 至少前7个必需
                                logger.warning(f"⚠️ 批次 {batch_num} 数据列不完整: {df_batch.columns.tolist()}")
                                failed_count += len(batch_codes)
                                batch_idx += len(batch_codes)
                                continue
                            
                            # 处理每行数据
                            for _, row in df_batch.iterrows():
                                thscode = str(row.get('thscode', '')).strip()
                                if not thscode:
                                    continue
                                
                                open_price = float(row.get('open', 0) or 0)
                                high = float(row.get('high', 0) or 0)
                                low = float(row.get('low', 0) or 0)
                                close = float(row.get('close', 0) or 0)
                                volume = float(row.get('volume', 0) or 0)
                                amount = float(row.get('amount', 0) or 0)
                                turnover_rate = float(row.get('turnoverrate', row.get('turnover_rate', 0)) or 0)
                                pct_chg = float(row.get('pctchg', row.get('pct_chg', 0)) or 0)
                                
                                # 提取6位代码
                                code = thscode.replace('.SH', '').replace('.SZ', '').replace('.BJ', '')
                                
                                if close > 0:  # 只保存有效数据
                                    all_data.append({
                                        'code': code,
                                        'open': open_price,
                                        'high': high,
                                        'low': low,
                                        'close': close,
                                        'volume': volume,
                                        'amount': amount,
                                        'turnover_rate': turnover_rate,
                                        'pct_chg': pct_chg,
                                        'pre_close': close / (1 + pct_chg / 100) if pct_chg != 0 else close,  # 计算前收盘价
                                    })
                                    success_count += 1
                        else:
                            # 如果不是 DataFrame，尝试按原逻辑处理（二维数组）
                            if isinstance(data, (list, tuple)) and len(data) > 0:
                                for row in data:
                                    if len(row) < 10:
                                        continue
                                    
                                    thscode = str(row[0]).strip()
                                    trade_time = str(row[1]).strip()
                                    open_price = float(row[2]) if row[2] else 0
                                    high = float(row[3]) if row[3] else 0
                                    low = float(row[4]) if row[4] else 0
                                    close = float(row[5]) if row[5] else 0
                                    volume = float(row[6]) if row[6] else 0
                                    amount = float(row[7]) if row[7] else 0
                                    turnover_rate = float(row[8]) if row[8] else 0
                                    pct_chg = float(row[9]) if row[9] else 0
                                    
                                    # 提取6位代码
                                    code = thscode.replace('.SH', '').replace('.SZ', '').replace('.BJ', '')
                                    
                                    if close > 0:  # 只保存有效数据
                                        all_data.append({
                                            'code': code,
                                            'open': open_price,
                                            'high': high,
                                            'low': low,
                                            'close': close,
                                            'volume': volume,
                                            'amount': amount,
                                            'turnover_rate': turnover_rate,
                                            'pct_chg': pct_chg,
                                            'pre_close': close / (1 + pct_chg / 100) if pct_chg != 0 else close,  # 计算前收盘价
                                        })
                                        success_count += 1
                            else:
                                logger.warning(f"⚠️ 批次 {batch_num} 数据格式不支持: {type(data)}")
                                failed_count += len(batch_codes)
                                batch_idx += len(batch_codes)
                                continue
                    else:
                        logger.warning(f"⚠️ 批次 {batch_num} 无数据返回")
                        failed_count += len(batch_codes)
                        batch_idx += len(batch_codes)
                        continue
                    
                    # 成功获取数据后，重置批次大小（为下一批使用初始大小）
                    if batch_size < initial_batch_size:
                        batch_size = initial_batch_size
                    
                    batch_success_count = len([r for r in all_data if r.get('code') in [c.replace('.SH', '').replace('.SZ', '').replace('.BJ', '') for c in ifind_codes]])
                    logger.info(f"  ✅ 批次 {batch_num} ({len(batch_codes)}只) 获取到 {batch_success_count} 条数据")
                    batch_idx += len(batch_codes)  # 成功，移动到下一批
                    
                except Exception as e:
                    # 如果批次太大导致异常，尝试减小批次重试
                    if batch_size > min_batch_size and len(batch_codes) == batch_size:
                        logger.warning(f"⚠️ 批次 {batch_num} ({len(batch_codes)}只) 处理异常，减小批次重试: {e}")
                        batch_size = max(min_batch_size, batch_size // 2)  # 减半批次大小
                        continue  # 不移动 batch_idx，重试当前批次
                    else:
                        logger.error(f"  ❌ 批次 {batch_num} ({len(batch_codes)}只) 处理失败: {e}")
                        failed_count += len(batch_codes)
                        batch_idx += len(batch_codes)  # 跳过这批，继续下一批
                        continue
            
            if all_data:
                df = pd.DataFrame(all_data)
                logger.info(f"✅ iFinDPy 获取到 {len(df)} 条有效数据 (成功: {success_count}, 失败: {failed_count})")
                return df
            else:
                logger.warning(f"⚠️ iFinDPy 未获取到有效数据 (成功: {success_count}, 失败: {failed_count})")
                return pd.DataFrame()
                
        except ImportError:
            logger.error("❌ iFinDPy 模块未安装")
            return pd.DataFrame()
        except Exception as e:
            logger.error(f"❌ iFinDPy 获取日线数据失败: {e}", exc_info=True)
            return pd.DataFrame()
    
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
            start_date: 开始日期，格式 YYYYMMDD
            end_date: 结束日期，格式 YYYYMMDD
            freq: 频率，默认 "D"（日线）
            
        Returns:
            DataFrame: 包含 code, trade_date, open, high, low, close, vol, amount
        """
        if not self.available:
            logger.error("❌ IfindDailySource 不可用")
            return pd.DataFrame()
        
        if freq != "D":
            logger.warning(f"⚠️ iFinDPy 目前只支持日线数据，freq={freq} 将被忽略")
        
        # 转换日期格式
        start_date_str = f"{start_date[:4]}-{start_date[4:6]}-{start_date[6:8]}"
        end_date_str = f"{end_date[:4]}-{end_date[4:6]}-{end_date[6:8]}"
        
        logger.info(f"📥 从 iFinDPy 获取历史K线: codes={len(codes)}, {start_date_str} ~ {end_date_str}")
        
        try:
            from iFinDPy import THS_HQ
            
            all_data = []
            
            # 批量处理
            batch_size = 50  # 历史数据批量小一些
            for batch_idx in range(0, len(codes), batch_size):
                batch_codes = codes[batch_idx:batch_idx + batch_size]
                
                # 转换为 iFinD 格式
                ifind_codes = [code_to_ifind_code(code) for code in batch_codes]
                thscode_str = ','.join(ifind_codes)
                
                try:
                    jsonparam = 'pricetype:1'  # 前复权
                    
                    result = THS_HQ(
                        thscode_str,
                        'open;high;low;close;volume;amount',
                        jsonparam,
                        start_date_str,
                        end_date_str,
                        format='format:dataframe'
                    )
                    
                    # 检查返回类型
                    if isinstance(result, dict):
                        errorcode = result.get('errorcode', -1)
                        errmsg = result.get('errmsg', '未知错误')
                        data = result.get('data')
                    else:
                        errorcode = getattr(result, 'errorcode', -1)
                        errmsg = getattr(result, 'errmsg', '未知错误')
                        data = getattr(result, 'data', None)
                    
                    if errorcode != 0:
                        logger.warning(f"⚠️ 批次获取失败: {errmsg}")
                        continue
                    
                    # 解析数据（DataFrame格式）
                    if data is not None and isinstance(data, pd.DataFrame):
                        df_batch = data.copy()
                        df_batch.columns = [col.lower() for col in df_batch.columns]
                        
                        # 检查必需的列
                        if 'thscode' not in df_batch.columns or 'time' not in df_batch.columns:
                            logger.warning(f"⚠️ 批次数据列不完整: {df_batch.columns.tolist()}")
                            continue
                        
                        for _, row in df_batch.iterrows():
                            thscode = str(row.get('thscode', '')).strip()
                            if not thscode:
                                continue
                            
                            trade_time = str(row.get('time', ''))
                            open_price = float(row.get('open', 0) or 0)
                            high = float(row.get('high', 0) or 0)
                            low = float(row.get('low', 0) or 0)
                            close = float(row.get('close', 0) or 0)
                            volume = float(row.get('volume', 0) or 0)
                            amount = float(row.get('amount', 0) or 0)
                            
                            # 提取6位代码
                            code = thscode.replace('.SH', '').replace('.SZ', '').replace('.BJ', '')
                            
                            # 解析日期
                            if trade_time:
                                trade_date = pd.to_datetime(trade_time, errors='coerce')
                                if pd.notna(trade_date):
                                    trade_date = trade_date.strftime('%Y%m%d')
                                else:
                                    trade_date = start_date  # 降级使用开始日期
                            else:
                                trade_date = start_date
                            
                            if close > 0:
                                all_data.append({
                                    'code': code,
                                    'trade_date': trade_date,
                                    'open': open_price,
                                    'high': high,
                                    'low': low,
                                    'close': close,
                                    'vol': volume,
                                    'amount': amount,
                                })
                
                except Exception as e:
                    logger.error(f"❌ 批次处理失败: {e}")
                    continue
            
            if all_data:
                df = pd.DataFrame(all_data)
                logger.info(f"✅ iFinDPy 获取到 {len(df)} 条历史K线数据")
                return df
            else:
                logger.warning("⚠️ iFinDPy 未获取到历史K线数据")
                return pd.DataFrame()
                
        except ImportError:
            logger.error("❌ iFinDPy 模块未安装")
            return pd.DataFrame()
        except Exception as e:
            logger.error(f"❌ iFinDPy 获取历史K线失败: {e}", exc_info=True)
            return pd.DataFrame()

