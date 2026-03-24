"""
Tushare Pro 数据源客户端
"""

import logging
import threading
import time
from typing import List, Dict, Optional
from datetime import date, datetime
from .base_client import BaseClient

logger = logging.getLogger(__name__)

# 全局速率限制器（Tushare 限制：每分钟最多 200 次，单只股票 get_fundamental 会调用 4 次 API）
_TUSHARE_RATE_LIMITER = None
_RATE_LIMITER_LOCK = threading.Lock()


def _get_rate_limiter():
    """获取全局 Tushare 速率限制器，每分钟最多 480 次（留缓冲避免边界触发）"""
    global _TUSHARE_RATE_LIMITER
    with _RATE_LIMITER_LOCK:
        if _TUSHARE_RATE_LIMITER is None:
            _TUSHARE_RATE_LIMITER = _TushareRateLimiter(max_calls=480, period=60.0)
        return _TUSHARE_RATE_LIMITER


class _TushareRateLimiter:
    """Tushare API 速率限制器（每分钟 N 次）"""
    def __init__(self, max_calls: int = 480, period: float = 60.0):
        self.max_calls = max_calls
        self.period = period
        self.calls = []
        self.lock = threading.Lock()

    def wait_if_needed(self):
        with self.lock:
            now = time.time()
            self.calls = [t for t in self.calls if now - t < self.period]
            if len(self.calls) >= self.max_calls:
                oldest = min(self.calls)
                wait_time = self.period - (now - oldest) + 0.2
                if wait_time > 0:
                    logger.info(f"⏳ Tushare 速率限制：等待 {wait_time:.1f}s（{len(self.calls)}/{self.max_calls} 次/分钟）")
                    time.sleep(wait_time)
                    now = time.time()
                    self.calls = [t for t in self.calls if now - t < self.period]
            self.calls.append(time.time())


class TushareClient(BaseClient):
    """Tushare Pro 客户端"""
    
    def __init__(self, token: Optional[str] = None):
        """
        初始化Tushare客户端
        
        Args:
            token: Tushare Pro token，如果为None则从config读取
        """
        super().__init__('tushare')
        
        try:
            import tushare as ts
            from data_warehouse.config import TUSHARE_TOKEN
            
            # 使用传入的token或从config读取
            token = token or TUSHARE_TOKEN
            
            if token:
                ts.set_token(token)
                self.pro = ts.pro_api()
                self.available = True
                logger.debug("✅ Tushare客户端已初始化")  # 改为DEBUG级别，减少日志输出
            else:
                logger.warning("⚠️ Tushare token未配置，客户端不可用")
                self.available = False
                self.pro = None
        except ImportError:
            logger.error("❌ tushare未安装，请运行: pip install tushare")
            self.available = False
            self.pro = None
        except Exception as e:
            logger.error(f"❌ Tushare客户端初始化失败: {e}", exc_info=True)
            self.available = False
            self.pro = None
    
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
            logger.warning("⚠️ Tushare客户端不可用")
            return []
        
        try:
            # 转换日期格式
            start_str = start_date.strftime('%Y%m%d')
            end_str = end_date.strftime('%Y%m%d')

            _get_rate_limiter().wait_if_needed()
            # 调用Tushare API
            df = self.pro.daily(
                ts_code=ts_code,
                start_date=start_str,
                end_date=end_str,
                fields='ts_code,trade_date,open,high,low,close,pre_close,vol,amount'
            )
            
            if df is None or df.empty:
                logger.debug(f"Tushare未返回数据: {ts_code} ({start_date} to {end_date})")
                return []
            
            # 转换为标准格式
            import pandas as pd
            results = []
            for _, row in df.iterrows():
                try:
                    trade_date = self.parse_date(str(row['trade_date']))
                    results.append({
                        'ts_code': row['ts_code'],
                        'trade_date': trade_date,
                        'open': float(row['open']) if pd.notna(row['open']) else None,
                        'high': float(row['high']) if pd.notna(row['high']) else None,
                        'low': float(row['low']) if pd.notna(row['low']) else None,
                        'close': float(row['close']) if pd.notna(row['close']) else None,
                        'pre_close': float(row['pre_close']) if pd.notna(row['pre_close']) else None,
                        'vol': float(row['vol']) if pd.notna(row['vol']) else None,  # 手
                        'amount': float(row['amount']) if pd.notna(row['amount']) else None,  # 元
                        'turnover_rate': None  # Tushare日线接口不包含换手率
                    })
                except Exception as e:
                    logger.debug(f"解析Tushare数据行失败: {e}")
                    continue
            
            logger.debug(f"✅ Tushare获取日线数据: {ts_code} ({len(results)} 条)")
            return results
            
        except Exception as e:
            logger.error(f"❌ Tushare获取日线数据失败 {ts_code}: {e}", exc_info=True)
            return []
    
    def get_fundamental(self, ts_code: str, end_date: Optional[date] = None) -> Optional[Dict]:
        """
        获取财务数据（单只股票）
        
        Args:
            ts_code: 股票代码（Tushare格式）
            end_date: 报告期，如果为None则获取最新一期
        
        Returns:
            Dict: 财务数据
        """
        if not self.available:
            logger.warning("⚠️ Tushare客户端不可用")
            return None
        
        try:
            import pandas as pd
            import math
            
            # 安全转换为float的辅助函数
            def safe_float(value, default=0.0):
                """安全转换为float，处理NaN、inf和None"""
                if value is None or (isinstance(value, float) and (math.isnan(value) or math.isinf(value))):
                    return default
                try:
                    val = float(value)
                    if math.isnan(val) or math.isinf(val):
                        return default
                    return val
                except (ValueError, TypeError):
                    return default
            
            # 获取财务指标
            period = end_date.strftime('%Y%m%d') if end_date else ''
            limiter = _get_rate_limiter()

            # 尝试批量获取（如果支持多个ts_code）
            limiter.wait_if_needed()
            df = self.pro.fina_indicator(
                ts_code=ts_code,
                period=period,
                fields='ts_code,end_date,roe,netprofit_margin,grossprofit_margin,debt_to_assets,ocf_to_revenue,or_yoy,tr_yoy,profit_dedt,dtprofit_to_profit'
            )
            
            if df is None or df.empty:
                logger.debug(f"Tushare未返回财务数据: {ts_code}")
                return None
            
            # 如果没有指定报告期，需要按end_date排序取最新一期
            if not end_date:
                # 确保end_date是日期格式，然后按降序排序
                df['end_date_parsed'] = pd.to_datetime(df['end_date'], format='%Y%m%d', errors='coerce')
                df = df.sort_values('end_date_parsed', ascending=False)
                df = df.drop('end_date_parsed', axis=1)
            
            # 获取最新一期数据
            latest = df.iloc[0]
            end_date_obj = self.parse_date(str(latest['end_date']))
            
            # 判断报告类型（简化处理，根据end_date判断）
            month = end_date_obj.month
            if month == 12:
                report_type = 'annual'
            elif month == 3:
                report_type = 'q1'
            elif month == 6:
                report_type = 'q2'
            elif month == 9:
                report_type = 'q3'
            else:
                report_type = 'annual'  # 默认
            
            # 从fina_indicator中提取营收同比（or_yoy=营业收入同比, tr_yoy=营业总收入同比）
            revenue_growth = safe_float(latest.get('or_yoy'), 0.0)
            if revenue_growth == 0.0:
                revenue_growth = safe_float(latest.get('tr_yoy'), 0.0)
            cashflow_to_revenue_val = safe_float(latest.get('ocf_to_revenue'), 0.0)
            # 如果值>1，认为是百分比，需要除以100
            cashflow_to_revenue = cashflow_to_revenue_val / 100 if cashflow_to_revenue_val > 1 else cashflow_to_revenue_val
            
            # 使用确定的报告期查询其他表
            target_period = end_date_obj.strftime('%Y%m%d')
            
            # 获取现金流量表数据（n_cashflow_act 单位：元）
            op_cf = 0.0
            try:
                limiter.wait_if_needed()
                cashflow_df = self.pro.cashflow(
                    ts_code=ts_code,
                    period=target_period,
                    fields='ts_code,end_date,n_cashflow_act'
                )
                if cashflow_df is not None and not cashflow_df.empty:
                    op_cf = safe_float(cashflow_df.iloc[0].get('n_cashflow_act'), 0.0)
            except Exception as e:
                logger.debug(f"获取现金流量表数据失败: {e}")
            
            # 获取利润表数据（净利润、营业收入、营业利润、财务费用）
            net_profit = 0.0
            revenue = 0.0
            operate_profit = None
            fin_exp_val = None
            try:
                limiter.wait_if_needed()
                income_df = self.pro.income(
                    ts_code=ts_code,
                    period=target_period,
                    fields='ts_code,end_date,n_income,revenue,total_revenue,operate_profit,fin_exp'
                )
                if income_df is not None and not income_df.empty:
                    row = income_df.iloc[0]
                    net_profit = safe_float(row.get('n_income'), 0.0)
                    revenue = safe_float(row.get('revenue'), 0.0)
                    if revenue == 0.0:
                        revenue = safe_float(row.get('total_revenue'), 0.0)
                    if 'operate_profit' in row and pd.notna(row.get('operate_profit')):
                        operate_profit = safe_float(row.get('operate_profit'), 0.0)
                    if 'fin_exp' in row and pd.notna(row.get('fin_exp')):
                        fin_exp_val = safe_float(row.get('fin_exp'), 0.0)
            except Exception as e:
                logger.debug(f"获取利润表数据失败: {e}")
            
            # 获取资产负债表数据（Tushare 字段名：total_assets/total_liab/goodwill/total_hldr_eqy_exc_min_int）
            total_debt = 0.0
            total_asset = 0.0
            goodwill = None
            total_equity = None
            try:
                limiter.wait_if_needed()
                balance_df = self.pro.balancesheet(
                    ts_code=ts_code,
                    period=target_period,
                    fields='ts_code,end_date,total_liab,total_assets,goodwill,total_hldr_eqy_exc_min_int'
                )
                if balance_df is not None and not balance_df.empty:
                    row = balance_df.iloc[0]
                    total_debt = safe_float(row.get('total_liab'), 0.0)
                    total_asset = safe_float(row.get('total_assets'), 0.0)
                    if 'goodwill' in row and pd.notna(row.get('goodwill')):
                        goodwill = safe_float(row.get('goodwill'), 0.0)
                    if 'total_hldr_eqy_exc_min_int' in row and pd.notna(row.get('total_hldr_eqy_exc_min_int')):
                        total_equity = safe_float(row.get('total_hldr_eqy_exc_min_int'), 0.0)
            except Exception as e:
                logger.debug(f"获取资产负债表数据失败: {e}")

            # 获取审计意见（Tushare fina_audit）
            audit_result = None
            try:
                limiter.wait_if_needed()
                audit_df = self.pro.fina_audit(
                    ts_code=ts_code,
                    period=target_period,
                    fields='ts_code,end_date,audit_result'
                )
                if audit_df is not None and not audit_df.empty:
                    val = audit_df.iloc[0].get('audit_result')
                    if val is not None and (isinstance(val, str) or pd.notna(val)):
                        audit_result = str(val).strip() if val else None
            except Exception as e:
                logger.debug(f"获取审计意见失败: {e}")
            
            # Tushare返回的财务指标可能是百分比或小数，需要判断
            roe_val = safe_float(latest.get('roe'), 0.0)
            net_margin_val = safe_float(latest.get('netprofit_margin'), 0.0)
            gross_margin_val = safe_float(latest.get('grossprofit_margin'), 0.0)
            debt_ratio_val = safe_float(latest.get('debt_to_assets'), 0.0)
            dtprofit_to_profit_val = safe_float(latest.get('dtprofit_to_profit'), None)

            # 扣非净利率：优先 扣非净利润/营业收入，否则 净利率×扣非利润占比
            deduct_net_margin_val = None
            if revenue and revenue > 0:
                profit_dedt_val = safe_float(latest.get('profit_dedt'), None)
                if profit_dedt_val is not None:
                    deduct_net_margin_val = profit_dedt_val / revenue
                    deduct_net_margin_val = deduct_net_margin_val / 100 if deduct_net_margin_val > 1 else deduct_net_margin_val
            if deduct_net_margin_val is None and dtprofit_to_profit_val is not None and net_margin_val is not None:
                net_margin_pct = net_margin_val / 100 if net_margin_val > 1 else net_margin_val
                dt_ratio = dtprofit_to_profit_val / 100 if abs(dtprofit_to_profit_val) > 1 else dtprofit_to_profit_val
                deduct_net_margin_val = net_margin_pct * dt_ratio

            # 如果值>1，认为是百分比，需要除以100
            result = {
                'ts_code': ts_code,
                'end_date': end_date_obj,
                'report_type': report_type,
                'roe': roe_val / 100 if roe_val > 1 else roe_val,
                'net_margin': net_margin_val / 100 if net_margin_val > 1 else net_margin_val,
                'deduct_net_margin': deduct_net_margin_val,
                'gross_margin': gross_margin_val / 100 if gross_margin_val > 1 else gross_margin_val,
                'op_cf': op_cf,
                'total_debt': total_debt,
                'total_asset': total_asset,
                'debt_ratio': debt_ratio_val / 100 if debt_ratio_val > 1 else debt_ratio_val,
                'profit_volatility': None,  # 需要计算
                'revenue': revenue if revenue > 0 else None,  # 营收（元），来自 income 表
                'yoy_sales': revenue_growth,  # 营收同比（%），来自 fina_indicator.or_yoy/tr_yoy
                'net_profit': net_profit,  # 净利润（元）
                'ocf_to_revenue': cashflow_to_revenue,  # 经营现金流/营收
                'operate_profit': operate_profit,  # 营业利润（元），利息偿付用
                'fin_exp': fin_exp_val,  # 财务费用（元）
                'goodwill': goodwill,  # 商誉（元）
                'total_equity': total_equity,  # 归属母公司净资产（元）
                'audit_result': audit_result  # 审计意见
            }
            
            logger.debug(f"✅ Tushare获取财务数据: {ts_code}")
            return result
            
        except Exception as e:
            logger.error(f"❌ Tushare获取财务数据失败 {ts_code}: {e}", exc_info=True)
            return None
    
    def batch_get_fundamental(self, ts_codes: List[str], end_date: Optional[date] = None, max_workers: int = 3) -> Dict[str, Optional[Dict]]:
        """
        批量获取财务数据（优化版：使用并发处理+速率限制）
        
        注意：Tushare的fina_indicator接口必须提供ts_code参数，不支持真正的批量查询。
        此方法通过并发处理（多线程）+ 速率限制来提升性能，同时避免触发API限制。
        
        Args:
            ts_codes: 股票代码列表（Tushare格式）
            end_date: 报告期，如果为None则获取最新一期
            max_workers: 最大并发线程数（默认3，避免触发API限制）
        
        Returns:
            Dict[str, Optional[Dict]]: {ts_code: 财务数据}，如果获取失败则为None
        """
        if not self.available:
            logger.warning("⚠️ Tushare客户端不可用")
            return {code: None for code in ts_codes}
        
        result = {}
        from concurrent.futures import ThreadPoolExecutor, as_completed
        result_lock = threading.Lock()

        logger.info(f"📥 批量获取财务数据: {len(ts_codes)} 只股票（并发 {max_workers} 线程，限速 480 次/分钟）")

        def fetch_single(ts_code: str) -> tuple:
            """获取单只股票的财务数据（get_fundamental 内部已做 API 级限速）"""
            try:
                fundamental_data = self.get_fundamental(ts_code, end_date)
                return (ts_code, fundamental_data)
            except Exception as e:
                error_msg = str(e)
                if "每分钟最多访问" in error_msg or "200次" in error_msg:
                    logger.warning(f"  ⚠️ 触发限速，等待 65s 后重试 {ts_code}")
                    time.sleep(65)
                    try:
                        fundamental_data = self.get_fundamental(ts_code, end_date)
                        return (ts_code, fundamental_data)
                    except Exception as retry_error:
                        logger.debug(f"获取 {ts_code} 失败（重试后）: {retry_error}")
                        return (ts_code, None)
                else:
                    logger.debug(f"获取 {ts_code} 失败: {e}")
                    return (ts_code, None)
        
        # 使用线程池并发处理
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 提交所有任务
            future_to_code = {executor.submit(fetch_single, ts_code): ts_code for ts_code in ts_codes}
            
            # 收集结果
            completed = 0
            for future in as_completed(future_to_code):
                ts_code, data = future.result()
                with result_lock:
                    result[ts_code] = data
                    completed += 1
                    # 每50只股票输出一次进度
                    if completed % 50 == 0:
                        logger.debug(f"  进度: {completed}/{len(ts_codes)} ({completed*100//len(ts_codes)}%)")
        
        success_count = len([r for r in result.values() if r is not None])
        logger.info(f"✅ 批量获取完成: {success_count}/{len(ts_codes)} 只股票")
        return result
    
    def get_stock_list(self, exchange: Optional[str] = None) -> List[Dict]:
        """
        获取股票列表（基本信息）
        
        Args:
            exchange: 交易所（'SSE', 'SZSE', 'BSE'），如果为None则返回所有
        
        Returns:
            List[Dict]: 股票列表
        """
        if not self.available:
            logger.warning("⚠️ Tushare客户端不可用")
            return []
        
        try:
            import pandas as pd
            
            # 转换交易所代码
            exchange_map = {
                'SSE': 'SSE',
                'SZSE': 'SZSE',
                'BSE': 'BSE'
            }
            tushare_exchange = exchange_map.get(exchange, '') if exchange else ''
            
            _get_rate_limiter().wait_if_needed()
            # 获取股票基本信息
            df = self.pro.stock_basic(
                exchange=tushare_exchange,
                list_status='L',  # 只获取上市股票
                fields='ts_code,symbol,name,area,industry,list_date'
            )
            
            if df is None or df.empty:
                logger.debug("Tushare未返回股票列表")
                return []
            
            results = []
            for _, row in df.iterrows():
                try:
                    ts_code = str(row['ts_code']).strip()
                    symbol = str(row['symbol']).strip()
                    name = str(row['name']).strip()
                    industry = str(row.get('industry', '')).strip() if pd.notna(row.get('industry')) else None
                    list_date_str = str(row.get('list_date', ''))
                    
                    # 判断交易所
                    if ts_code.endswith('.SH'):
                        exchange_code = 'SSE'
                    elif ts_code.endswith('.SZ'):
                        exchange_code = 'SZSE'
                    elif ts_code.endswith('.BJ'):
                        exchange_code = 'BSE'
                    else:
                        continue  # 跳过无法识别的代码
                    
                    # 如果指定了交易所，过滤
                    if exchange and exchange_code != exchange:
                        continue
                    
                    # 解析上市日期
                    list_date = None
                    if list_date_str and len(list_date_str) == 8:
                        list_date = self.parse_date(list_date_str)
                    
                    results.append({
                        'ts_code': ts_code,
                        'exchange': exchange_code,
                        'symbol': symbol,
                        'name': name,
                        'list_date': list_date,
                        'delist_date': None,
                        'industry': industry
                    })
                except Exception as e:
                    logger.debug(f"解析Tushare股票信息失败: {e}")
                    continue
            
            logger.info(f"✅ Tushare获取股票列表: {len(results)} 只")
            return results
            
        except Exception as e:
            logger.error(f"❌ Tushare获取股票列表失败: {e}", exc_info=True)
            return []

