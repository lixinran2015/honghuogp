"""
Baostock 数据源客户端
用于获取日线和财务数据
"""

import logging
from typing import List, Dict, Optional
from datetime import date, datetime
from .base_client import BaseClient

logger = logging.getLogger(__name__)

try:
    import baostock as bs
    HAS_BAOSTOCK = True
except ImportError:
    HAS_BAOSTOCK = False
    logger.warning("⚠️ baostock 未安装，请运行: pip install baostock")


class BaostockClient(BaseClient):
    """Baostock 客户端"""
    
    def __init__(self):
        """初始化Baostock客户端"""
        super().__init__('baostock')
        
        if not HAS_BAOSTOCK:
            logger.error("❌ baostock未安装，请运行: pip install baostock")
            self.available = False
            return
        
        try:
            # 登录
            lg = bs.login()
            if lg.error_code != "0":
                logger.error(f"❌ Baostock登录失败: {lg.error_msg}")
                self.available = False
            else:
                self.available = True
                logger.info("✅ Baostock客户端已初始化并登录成功")
        except Exception as e:
            logger.error(f"❌ Baostock客户端初始化失败: {e}", exc_info=True)
            self.available = False
    
    def __del__(self):
        """析构时登出"""
        try:
            if HAS_BAOSTOCK and self.available:
                try:
                    import sys
                    import io
                    old_stderr = sys.stderr
                    sys.stderr = io.StringIO()
                    bs.logout()
                    sys.stderr = old_stderr
                except Exception:
                    if 'sys' in locals():
                        sys.stderr = old_stderr
                    pass
        except Exception:
            pass
    
    def _to_bs_code(self, ts_code: str) -> str:
        """转换Tushare格式到Baostock格式"""
        code = ts_code.split('.')[0]
        if ts_code.endswith('.SH'):
            return f"sh.{code}"
        elif ts_code.endswith('.SZ'):
            return f"sz.{code}"
        elif ts_code.endswith('.BJ'):
            return f"bj.{code}"
        else:
            # 根据代码判断
            if code.startswith('6'):
                return f"sh.{code}"
            else:
                return f"sz.{code}"
    
    def get_daily_price(self, ts_code: str, start_date: date, end_date: date) -> List[Dict]:
        """
        获取日线行情数据
        
        Args:
            ts_code: 股票代码（Tushare格式，如 '600519.SH'）
            start_date: 开始日期
            end_date: 结束日期
        
        Returns:
            List[Dict]: 日线数据列表
        """
        if not self.available:
            logger.warning("⚠️ Baostock客户端不可用")
            return []
        
        try:
            bs_code = self._to_bs_code(ts_code)
            start_str = start_date.strftime('%Y-%m-%d')
            end_str = end_date.strftime('%Y-%m-%d')
            
            fields = "date,code,open,high,low,close,preclose,volume,amount,turn,pctChg"
            rs = bs.query_history_k_data_plus(
                bs_code,
                fields,
                start_date=start_str,
                end_date=end_str,
                frequency="d",
                adjustflag="2"  # 前复权
            )
            
            if rs.error_code != "0":
                logger.debug(f"Baostock获取日线数据失败 {ts_code}: {rs.error_msg}")
                return []
            
            results = []
            while rs.next():
                row = rs.get_row_data()
                try:
                    trade_date = self.parse_date(row[0])
                    results.append({
                        'ts_code': ts_code,
                        'trade_date': trade_date,
                        'open': float(row[2]) if row[2] else None,
                        'high': float(row[3]) if row[3] else None,
                        'low': float(row[4]) if row[4] else None,
                        'close': float(row[5]) if row[5] else None,
                        'pre_close': float(row[6]) if row[6] else None,
                        'vol': float(row[7]) if row[7] else None,  # 手
                        'amount': float(row[8]) if row[8] else None,  # 元
                        'turnover_rate': float(row[9]) if row[9] else None  # 换手率(%)
                    })
                except Exception as e:
                    logger.debug(f"解析Baostock日线数据行失败: {e}")
                    continue
            
            logger.debug(f"✅ Baostock获取日线数据: {ts_code} ({len(results)} 条)")
            return results
            
        except Exception as e:
            logger.error(f"❌ Baostock获取日线数据失败 {ts_code}: {e}", exc_info=True)
            return []
    
    def get_fundamental(self, ts_code: str, end_date: Optional[date] = None) -> Optional[Dict]:
        """
        获取财务数据
        
        Args:
            ts_code: 股票代码（Tushare格式）
            end_date: 报告期，如果为None则获取最新一期
        
        Returns:
            Dict: 财务数据
        """
        if not self.available:
            logger.warning("⚠️ Baostock客户端不可用")
            return None
        
        try:
            bs_code = self._to_bs_code(ts_code)
            
            # Baostock 财务数据接口
            # 注意：Baostock 的财务数据接口可能有限，这里尝试获取主要财务指标
            # 如果 end_date 为 None，获取最新一期
            
            # 尝试获取财务指标（季度数据）
            # Baostock 的财务数据接口：query_profit_data, query_balance_data, query_cash_flow_data
            # 但需要指定报告期，这里我们获取最新一期的数据
            
            # 由于 Baostock 的财务数据接口需要指定报告期，且可能不完整
            # 这里返回 None，表示 Baostock 不支持直接获取最新财务数据
            # 如果需要，可以结合其他数据源
            
            logger.debug(f"⚠️ Baostock 暂不支持直接获取最新财务数据（需要指定报告期）: {ts_code}")
            return None
            
        except Exception as e:
            logger.error(f"❌ Baostock获取财务数据失败 {ts_code}: {e}", exc_info=True)
            return None
    
    def get_stock_list(self, exchange: Optional[str] = None) -> List[Dict]:
        """
        获取股票列表（基本信息）
        
        Args:
            exchange: 交易所（'SSE', 'SZSE', 'BSE'），如果为None则返回所有
        
        Returns:
            List[Dict]: 股票列表
        """
        if not self.available:
            logger.warning("⚠️ Baostock客户端不可用")
            return []
        
        try:
            # Baostock 获取股票列表
            rs = bs.query_all_stock(day=datetime.today().strftime('%Y-%m-%d'))
            
            if rs.error_code != "0":
                logger.debug(f"Baostock获取股票列表失败: {rs.error_msg}")
                return []
            
            results = []
            while rs.next():
                row = rs.get_row_data()
                try:
                    bs_code = row[0]  # sh.600000
                    name = row[1]  # 股票名称
                    code = row[2]  # 600000
                    type_name = row[3]  # 类型
                    
                    # 转换为Tushare格式
                    if bs_code.startswith('sh.'):
                        ts_code = f"{code}.SH"
                        exchange_code = 'SSE'
                    elif bs_code.startswith('sz.'):
                        ts_code = f"{code}.SZ"
                        exchange_code = 'SZSE'
                    elif bs_code.startswith('bj.'):
                        ts_code = f"{code}.BJ"
                        exchange_code = 'BSE'
                    else:
                        continue
                    
                    # 如果指定了交易所，过滤
                    if exchange and exchange_code != exchange:
                        continue
                    
                    results.append({
                        'ts_code': ts_code,
                        'exchange': exchange_code,
                        'symbol': code,
                        'name': name,
                        'list_date': None,  # Baostock不提供上市日期
                        'delist_date': None,
                        'industry': None
                    })
                except Exception as e:
                    logger.debug(f"解析Baostock股票信息失败: {e}")
                    continue
            
            logger.info(f"✅ Baostock获取股票列表: {len(results)} 只")
            return results
            
        except Exception as e:
            logger.error(f"❌ Baostock获取股票列表失败: {e}", exc_info=True)
            return []

