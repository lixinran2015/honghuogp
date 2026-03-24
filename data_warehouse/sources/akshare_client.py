"""
AkShare 数据源客户端
"""

import logging
from typing import List, Dict, Optional
from datetime import date, datetime
from .base_client import BaseClient

logger = logging.getLogger(__name__)


class AkShareClient(BaseClient):
    """AkShare 客户端"""
    
    def __init__(self):
        """初始化AkShare客户端"""
        super().__init__('akshare')
        
        try:
            import akshare as ak
            self.ak = ak
            self.available = True
            logger.debug("✅ AkShare客户端已初始化")  # 改为DEBUG级别，减少日志输出
        except ImportError:
            logger.error("❌ akshare未安装，请运行: pip install akshare")
            self.available = False
            self.ak = None
        except Exception as e:
            logger.error(f"❌ AkShare客户端初始化失败: {e}", exc_info=True)
            self.available = False
            self.ak = None
    
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
            logger.warning("⚠️ AkShare客户端不可用")
            return []
        
        try:
            # 转换代码格式（Tushare格式 -> AkShare格式）
            # 600519.SH -> 600519
            symbol = ts_code.split('.')[0]
            
            # 转换日期格式
            start_str = start_date.strftime('%Y%m%d')
            end_str = end_date.strftime('%Y%m%d')
            
            # 调用AkShare API
            # 注意：AkShare的接口可能需要调整，这里使用通用接口
            df = self.ak.stock_zh_a_hist(
                symbol=symbol,
                period="daily",
                start_date=start_str,
                end_date=end_str,
                adjust="qfq"  # 前复权
            )
            
            if df is None or df.empty:
                logger.debug(f"AkShare未返回数据: {ts_code} ({start_date} to {end_date})")
                return []
            
            # 转换为标准格式
            import pandas as pd
            results = []
            
            # AkShare返回的列名可能是中文，需要适配
            date_col = None
            for col in df.columns:
                if '日期' in str(col) or 'date' in str(col).lower():
                    date_col = col
                    break
            
            if date_col is None:
                logger.warning(f"AkShare数据中未找到日期列: {ts_code}")
                return []
            
            for _, row in df.iterrows():
                try:
                    # 解析日期
                    date_str = str(row[date_col])
                    trade_date = self.parse_date(date_str)
                    
                    # 获取价格数据（列名可能是中文或英文）
                    open_val = self._get_value(row, ['开盘', 'open', 'Open'])
                    high_val = self._get_value(row, ['最高', 'high', 'High'])
                    low_val = self._get_value(row, ['最低', 'low', 'Low'])
                    close_val = self._get_value(row, ['收盘', 'close', 'Close'])
                    pre_close_val = self._get_value(row, ['昨收', 'pre_close', 'PreClose'])
                    vol_val = self._get_value(row, ['成交量', 'volume', 'Volume', 'vol'])
                    amount_val = self._get_value(row, ['成交额', 'amount', 'Amount'])
                    turnover_val = self._get_value(row, ['换手率', 'turnover', 'Turnover', 'turnover_rate'])
                    
                    results.append({
                        'ts_code': ts_code,
                        'trade_date': trade_date,
                        'open': float(open_val) if open_val is not None and pd.notna(open_val) else None,
                        'high': float(high_val) if high_val is not None and pd.notna(high_val) else None,
                        'low': float(low_val) if low_val is not None and pd.notna(low_val) else None,
                        'close': float(close_val) if close_val is not None and pd.notna(close_val) else None,
                        'pre_close': float(pre_close_val) if pre_close_val is not None and pd.notna(pre_close_val) else None,
                        'vol': float(vol_val) if vol_val is not None and pd.notna(vol_val) else None,  # 手
                        'amount': float(amount_val) if amount_val is not None and pd.notna(amount_val) else None,  # 元
                        'turnover_rate': float(turnover_val) if turnover_val is not None and pd.notna(turnover_val) else None
                    })
                except Exception as e:
                    logger.debug(f"解析AkShare数据行失败: {e}")
                    continue
            
            logger.debug(f"✅ AkShare获取日线数据: {ts_code} ({len(results)} 条)")
            return results
            
        except Exception as e:
            logger.error(f"❌ AkShare获取日线数据失败 {ts_code}: {e}", exc_info=True)
            return []
    
    def _get_value(self, row, possible_keys):
        """从行数据中获取值，尝试多个可能的键名"""
        import pandas as pd
        for key in possible_keys:
            if key in row.index:
                val = row[key]
                if pd.notna(val):
                    return val
        return None
    
    def get_fundamental(self, ts_code: str, end_date: Optional[date] = None) -> Optional[Dict]:
        """
        获取财务数据（使用更可靠的接口，带重试机制）
        
        Args:
            ts_code: 股票代码（Tushare格式）
            end_date: 报告期，如果为None则获取最新一期
        
        Returns:
            Dict: 财务数据
        """
        if not self.available:
            logger.warning("⚠️ AkShare客户端不可用")
            return None
        
        # 跳过北交所股票（AkShare可能不支持）
        if ts_code.endswith('.BJ'):
            logger.debug(f"跳过北交所股票: {ts_code}")
            return None
        
        try:
            # 转换代码格式
            symbol = ts_code.split('.')[0]
            import pandas as pd
            import time
            
            # 使用更可靠的接口：stock_financial_abstract
            roe = None
            end_date_obj = None
            report_type = 'annual'
            
            # 添加重试机制（最多2次，增加延迟避免限流）
            abstract_df = None
            for retry in range(2):
                try:
                    abstract_df = self.ak.stock_financial_abstract(symbol=symbol)
                    if abstract_df is not None and not abstract_df.empty:
                        break
                    if retry < 1:
                        time.sleep(1.0)  # 等待1秒后重试
                except Exception as e:
                    error_str = str(e)
                    # 如果是JSON解析错误或限流错误，增加延迟
                    if 'JSON' in error_str or 'Expecting value' in error_str or '456' in error_str:
                        if retry < 1:
                            logger.debug(f"AkShare stock_financial_abstract 失败 {ts_code} (尝试 {retry+1}/2，可能是限流): {e}")
                            time.sleep(2.0)  # 限流时等待更长时间
                        else:
                            logger.debug(f"AkShare stock_financial_abstract 最终失败 {ts_code} (可能是接口限流): {e}")
                    else:
                        if retry < 1:
                            logger.debug(f"AkShare stock_financial_abstract 失败 {ts_code} (尝试 {retry+1}/2): {e}")
                            time.sleep(1.0)
                        else:
                            logger.debug(f"AkShare stock_financial_abstract 最终失败 {ts_code}: {e}")
            
            if abstract_df is not None and not abstract_df.empty:
                # 查找ROE行
                for idx, row in abstract_df.iterrows():
                    indicator = str(row.get('指标', ''))
                    if '净资产收益率' in indicator and 'ROE' in indicator:
                        # 获取所有日期列（不限于2024/2025）
                        date_cols = []
                        for col in abstract_df.columns:
                            col_str = str(col)
                            # 匹配日期格式：YYYY-MM-DD, YYYYMMDD, YYYY年MM月等
                            if any(char.isdigit() for char in col_str[:4]) and len(col_str) >= 4:
                                try:
                                    # 尝试解析为日期
                                    if col_str[:4].isdigit() and int(col_str[:4]) >= 2020:
                                        date_cols.append(col)
                                except:
                                    pass
                        
                        if date_cols:
                            # 按列名排序，取最新的
                            date_cols = sorted(date_cols, reverse=True, key=lambda x: str(x))
                            latest_col = date_cols[0]
                            if latest_col in row.index and pd.notna(row[latest_col]):
                                try:
                                    roe_val = float(row[latest_col])
                                    roe = roe_val / 100 if roe_val > 1 else roe_val
                                    
                                    # 解析报告期
                                    col_str = str(latest_col)
                                    end_date_obj = self.parse_date(col_str)
                                    if end_date_obj:
                                        month = end_date_obj.month
                                        if month == 12:
                                            report_type = 'annual'
                                        elif month == 3:
                                            report_type = 'q1'
                                        elif month == 6:
                                            report_type = 'q2'
                                        elif month == 9:
                                            report_type = 'q3'
                                except Exception as e:
                                    logger.debug(f"解析ROE值失败 {ts_code}: {e}")
                        break
            
            # 获取利润表数据（毛利率、净利率）
            net_margin = None
            gross_margin = None
            
            # 转换代码格式为 AkShare 格式（sh600519 或 sz000001）
            ak_symbol = f"sh{symbol}" if ts_code.endswith('.SH') else f"sz{symbol}"
            
            # 添加重试机制（最多2次，增加延迟避免限流）
            profit_df = None
            for retry in range(2):
                try:
                    profit_df = self.ak.stock_financial_report_sina(stock=ak_symbol, symbol='利润表')
                    if profit_df is not None and not profit_df.empty:
                        break
                    if retry < 1:
                        time.sleep(1.0)
                except Exception as e:
                    error_str = str(e)
                    # 如果是JSON解析错误或限流错误，增加延迟
                    if 'JSON' in error_str or 'Expecting value' in error_str or '456' in error_str:
                        if retry < 1:
                            logger.debug(f"AkShare stock_financial_report_sina 失败 {ts_code} (尝试 {retry+1}/2，可能是限流): {e}")
                            time.sleep(2.0)  # 限流时等待更长时间
                        else:
                            logger.debug(f"AkShare stock_financial_report_sina 最终失败 {ts_code} (可能是接口限流): {e}")
                    else:
                        if retry < 1:
                            logger.debug(f"AkShare stock_financial_report_sina 失败 {ts_code} (尝试 {retry+1}/2): {e}")
                            time.sleep(1.0)
                        else:
                            logger.debug(f"AkShare stock_financial_report_sina 最终失败 {ts_code}: {e}")
            
            if profit_df is not None and not profit_df.empty:
                # 查找相关行
                revenue = None
                cost = None
                net_profit = None
                
                # 获取所有日期列
                date_cols = []
                for col in profit_df.columns:
                    col_str = str(col)
                    if any(char.isdigit() for char in col_str[:4]) and len(col_str) >= 4:
                        try:
                            if col_str[:4].isdigit() and int(col_str[:4]) >= 2020:
                                date_cols.append(col)
                        except:
                            pass
                
                if date_cols:
                    latest_col = sorted(date_cols, reverse=True, key=lambda x: str(x))[0]
                    
                    for idx, row in profit_df.iterrows():
                        item = str(row.get('项目', ''))
                        if ('营业总收入' in item or '营业收入' in item) and revenue is None:
                            if latest_col in row.index and pd.notna(row[latest_col]):
                                try:
                                    revenue = float(row[latest_col])
                                except:
                                    pass
                        elif '营业成本' in item and cost is None:
                            if latest_col in row.index and pd.notna(row[latest_col]):
                                try:
                                    cost = float(row[latest_col])
                                except:
                                    pass
                        elif '净利润' in item and ('归母' in item or '归属于母公司' in item) and net_profit is None:
                            if latest_col in row.index and pd.notna(row[latest_col]):
                                try:
                                    net_profit = float(row[latest_col])
                                except:
                                    pass
                    
                    # 计算毛利率和净利率
                    if revenue and revenue > 0:
                        if cost is not None:
                            gross_margin = (revenue - cost) / revenue
                        if net_profit is not None:
                            net_margin = net_profit / revenue
            
            # 如果至少获取到ROE或利润率，就返回数据
            if roe is not None or net_margin is not None or gross_margin is not None:
                if end_date_obj is None:
                    end_date_obj = date.today()
                
                result = {
                    'ts_code': ts_code,
                    'end_date': end_date_obj,
                    'report_type': report_type,
                    'roe': roe,
                    'net_margin': net_margin,
                    'gross_margin': gross_margin,
                    'op_cf': None,  # 需要从现金流量表获取
                    'total_debt': None,
                    'total_asset': None,
                    'debt_ratio': None,
                    'profit_volatility': None
                }
                
                logger.debug(f"✅ AkShare获取财务数据: {ts_code} (ROE={roe}, 净利率={net_margin}, 毛利率={gross_margin})")
                return result
            else:
                logger.debug(f"AkShare未获取到财务数据: {ts_code} (ROE={roe}, 净利率={net_margin}, 毛利率={gross_margin})")
                return None
            
        except Exception as e:
            logger.error(f"❌ AkShare获取财务数据失败 {ts_code}: {e}", exc_info=True)
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
            logger.warning("⚠️ AkShare客户端不可用")
            return []
        
        try:
            import pandas as pd
            
            # 获取A股股票基本信息
            df = self.ak.stock_info_a_code_name()
            
            if df is None or df.empty:
                logger.debug("AkShare未返回股票列表")
                return []
            
            results = []
            for _, row in df.iterrows():
                try:
                    code = str(row['code']).strip()
                    name = str(row['name']).strip()
                    
                    # 判断交易所
                    if code.startswith('6'):
                        exchange_code = 'SSE'
                        ts_code = f"{code}.SH"
                    elif code.startswith('0') or code.startswith('3'):
                        exchange_code = 'SZSE'
                        ts_code = f"{code}.SZ"
                    elif code.startswith('8') or code.startswith('4') or code.startswith('9'):
                        exchange_code = 'BSE'
                        ts_code = f"{code}.BJ"
                    else:
                        continue  # 跳过无法识别的代码
                    
                    # 如果指定了交易所，过滤
                    if exchange and exchange_code != exchange:
                        continue
                    
                    results.append({
                        'ts_code': ts_code,
                        'exchange': exchange_code,
                        'symbol': code,
                        'name': name,
                        'list_date': None,  # AkShare不提供上市日期
                        'delist_date': None,
                        'industry': None  # AkShare不提供行业信息
                    })
                except Exception as e:
                    logger.debug(f"解析AkShare股票信息失败: {e}")
                    continue
            
            logger.info(f"✅ AkShare获取股票列表: {len(results)} 只")
            return results
            
        except Exception as e:
            logger.error(f"❌ AkShare获取股票列表失败: {e}", exc_info=True)
            return []

