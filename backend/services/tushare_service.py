"""
Tushare Pro 数据服务
用于获取财务数据、资金流向、板块数据等
"""

import logging
import json
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import pandas as pd
import time

logger = logging.getLogger(__name__)


class TushareService:
    """Tushare Pro 数据服务类"""
    
    def __init__(self, token: Optional[str] = None):
        """
        初始化Tushare服务
        
        Args:
            token: Tushare Pro token，如果为None则从config.json读取
        """
        try:
            import tushare as ts
            self.ts = ts
            
            # 从全局配置读取 token
            if token is None:
                try:
                    from utils.config_manager import config_manager
                    tushare_cfg = config_manager.get_api_config("tushare")
                    token = tushare_cfg.get("token") if tushare_cfg else None
                except Exception:
                    token = None
            
            if token:
                ts.set_token(token)
                self.pro = ts.pro_api()
                self.available = True
                logger.info("✅ Tushare Pro 服务已初始化")
            else:
                logger.warning("⚠️ Tushare token 未配置，Tushare服务不可用")
                self.available = False
                self.pro = None
                
        except ImportError:
            logger.error("❌ tushare未安装，请运行: pip install tushare")
            self.available = False
            self.pro = None
        except Exception as e:
            logger.error(f"❌ Tushare服务初始化失败: {e}", exc_info=True)
            self.available = False
            self.pro = None
    
    def _normalize_code(self, stock_code: str) -> str:
        """
        标准化股票代码为Tushare格式（如：000001.SZ）
        
        Args:
            stock_code: 股票代码（如 '000001', 'sh000001', 'sz000001'）
        
        Returns:
            str: Tushare格式的股票代码（如 '000001.SZ'）
        """
        code = str(stock_code).strip()
        
        # 去掉前缀
        if code.startswith('sh'):
            code = code[2:]
        elif code.startswith('sz'):
            code = code[2:]
        elif code.startswith('bj'):
            # 北交所股票，Tushare格式为 8xxxxx.BJ
            if len(code) >= 6:
                code = code[-6:]
            return f"{code}.BJ"
        
        # 确保是6位数字
        if len(code) == 6 and code.isdigit():
            # 判断交易所
            if code.startswith('6'):
                return f"{code}.SH"
            elif code.startswith('0') or code.startswith('3'):
                return f"{code}.SZ"
        
        return code
    
    def get_financial_data(self, stock_code: str) -> Optional[Dict]:
        """
        获取股票财务数据
        
        Args:
            stock_code: 股票代码
        
        Returns:
            dict: 财务数据，包含：
                - roe_ttm: ROE（TTM）
                - gross_margin: 毛利率
                - net_margin: 净利率
                - operating_cashflow: 经营现金流
                - debt_ratio: 负债率
                - profit_volatility: 盈利波动率
        """
        if not self.available:
            return None
        
        try:
            ts_code = self._normalize_code(stock_code)
            
            # 获取最新财务指标数据（共享 Tushare 限速 480次/分钟）
            try:
                from data_warehouse.sources.tushare_client import _get_rate_limiter
                limiter = _get_rate_limiter()

                # 获取财务指标（最新一期）
                limiter.wait_if_needed()
                df = self.pro.fina_indicator(
                    ts_code=ts_code,
                    period='',  # 空字符串表示最新
                    fields='ts_code,end_date,roe,netprofit_margin,grossprofit_margin,debt_to_assets,ocf_to_revenue,or_yoy,tr_yoy'
                )
                
                if df is None or df.empty:
                    logger.debug(f"⚠️ Tushare未返回财务指标数据: {ts_code}")
                    return None
                
                # 获取最新一期数据
                latest = df.iloc[0]
                
                # 获取利润表数据（净利润、营业收入、盈利波动率）
                profit_df = None
                revenue_val = 0.0
                try:
                    limiter.wait_if_needed()
                    profit_df = self.pro.income(
                        ts_code=ts_code,
                        period='',
                        fields='ts_code,end_date,n_income,revenue,total_revenue'
                    )
                    if profit_df is not None and not profit_df.empty:
                        row = profit_df.iloc[0]
                        revenue_val = float(row.get('revenue', 0) or row.get('total_revenue', 0) or 0)
                except Exception as e:
                    logger.debug(f"获取利润表数据失败 {ts_code}: {e}")
                
                # 计算盈利波动率（基于最近3年的净利润）
                profit_volatility = 0.0
                if profit_df is not None and not profit_df.empty and len(profit_df) >= 3:
                    profits = profit_df.head(3)['n_income'].tolist() if 'n_income' in profit_df.columns else profit_df.head(3)['net_profit'].tolist()
                    profits = [float(p) for p in profits if p and float(p) > 0]
                    if len(profits) >= 2:
                        # 计算标准差/均值
                        import numpy as np
                        profits_array = np.array(profits)
                        if profits_array.mean() > 0:
                            profit_volatility = float(profits_array.std() / profits_array.mean())
                
                # 获取现金流量表数据
                operating_cashflow = 0.0
                try:
                    limiter.wait_if_needed()
                    cashflow_df = self.pro.cashflow(
                        ts_code=ts_code,
                        period='',
                        fields='ts_code,end_date,n_cashflow_act'
                    )
                    if cashflow_df is not None and not cashflow_df.empty:
                        operating_cashflow = float(cashflow_df.iloc[0]['n_cashflow_act'] or 0)
                except Exception as e:
                    logger.debug(f"获取现金流量表数据失败 {ts_code}: {e}")
                
                # Tushare返回的财务指标可能是百分比或小数，需要判断
                roe_val = float(latest.get('roe', 0) or 0)
                gross_margin_val = float(latest.get('grossprofit_margin', 0) or 0)
                net_margin_val = float(latest.get('netprofit_margin', 0) or 0)
                debt_ratio_val = float(latest.get('debt_to_assets', 0) or 0)
                
                yoy_sales_val = float(latest.get('or_yoy', 0) or latest.get('tr_yoy', 0) or 0)  # 营收同比（%）
                total_debt_val = 0.0
                total_asset_val = 0.0
                try:
                    limiter.wait_if_needed()
                    balance_df = self.pro.balancesheet(ts_code=ts_code, period=latest.get('end_date', ''), fields='ts_code,end_date,total_liab,total_assets')
                    if balance_df is not None and not balance_df.empty:
                        total_debt_val = float(balance_df.iloc[0].get('total_liab', 0) or 0)
                        total_asset_val = float(balance_df.iloc[0].get('total_assets', 0) or 0)
                except Exception as e:
                    logger.debug("获取资产负债表失败 %s: %s", ts_code, e)
                # 如果值>1，认为是百分比，需要除以100
                financial_data = {
                    'roe_ttm': roe_val / 100 if roe_val > 1 else roe_val,
                    'gross_margin': gross_margin_val / 100 if gross_margin_val > 1 else gross_margin_val,
                    'net_margin': net_margin_val / 100 if net_margin_val > 1 else net_margin_val,
                    'debt_ratio': debt_ratio_val / 100 if debt_ratio_val > 1 else debt_ratio_val,
                    'operating_cashflow': operating_cashflow,
                    'profit_volatility': profit_volatility,
                    'total_debt': total_debt_val,
                    'total_asset': total_asset_val,
                    'yoy_sales': yoy_sales_val,
                    'revenue': revenue_val if revenue_val > 0 else None,  # 来自 income 表
                }
                
                logger.debug(f"✅ 成功获取Tushare财务数据: {ts_code}")
                return financial_data
                
            except Exception as e:
                logger.debug(f"⚠️ 获取财务数据失败 {ts_code}: {e}")
                return None
                
        except Exception as e:
            logger.error(f"❌ 获取财务数据异常 {stock_code}: {e}", exc_info=True)
            return None
    
    def batch_get_financial_data(self, stock_codes: List[str], delay: float = 0.2) -> Dict[str, Dict]:
        """
        批量获取财务数据（优化版：优先从数据库缓存读取）
        
        Args:
            stock_codes: 股票代码列表
            delay: 每次请求之间的延迟（秒）
        
        Returns:
            dict: {股票代码: 财务数据}
        """
        result = {}
        total = len(stock_codes)
        
        # 1. 先从数据库缓存读取
        try:
            from sqlalchemy import text
            from data_warehouse.db import get_shared_engine
            
            engine = get_shared_engine()
            with engine.connect() as conn:
                # 转换代码格式
                ts_codes = [self._normalize_code(code) for code in stock_codes]
                
                # 查询数据库中的财务数据
                query = text("""
                    SELECT ts_code, roe, gross_margin, net_margin, debt_ratio, op_cf, profit_volatility
                    FROM fact_fundamental
                    WHERE ts_code = ANY(:ts_codes)
                    AND end_date = (
                        SELECT MAX(end_date) FROM fact_fundamental f2 
                        WHERE f2.ts_code = fact_fundamental.ts_code
                    )
                """)
                db_result = conn.execute(query, {'ts_codes': ts_codes}).fetchall()
                
                for row in db_result:
                    ts_code = row[0]
                    original_code = ts_code.split('.')[0]
                    result[original_code] = {
                        'roe_ttm': float(row[1]) if row[1] else 0.0,
                        'gross_margin': float(row[2]) if row[2] else 0.0,
                        'net_margin': float(row[3]) if row[3] else 0.0,
                        'debt_ratio': float(row[4]) if row[4] else 0.0,
                        'operating_cashflow': float(row[5]) if row[5] else 0.0,
                        'profit_volatility': float(row[6]) if row[6] else 0.0
                    }
                
                if result:
                    logger.info(f"✅ 从数据库缓存获取财务数据: {len(result)}/{total}")
                    
        except Exception as e:
            logger.debug(f"从数据库读取财务数据失败: {e}")
        
        # 2. 对于缓存中没有的股票，从Tushare获取并保存到数据库
        missing_codes = [code for code in stock_codes if code.split('.')[0] not in result and code not in result]
        
        if missing_codes and self.available:
            logger.info(f"📥 从Tushare获取 {len(missing_codes)} 只股票的财务数据...")
            
            for i, code in enumerate(missing_codes):
                try:
                    financial_data = self.get_financial_data(code)
                    if financial_data:
                        result[code] = financial_data
                        # 保存到数据库
                        self._save_financial_to_db(code, financial_data)
                    
                    if i < len(missing_codes) - 1:
                        time.sleep(delay)
                        
                    if (i + 1) % 50 == 0:
                        logger.info(f"📊 已获取 {i + 1}/{len(missing_codes)} 只股票的财务数据")
                        
                except Exception as e:
                    logger.debug(f"⚠️ 获取 {code} 财务数据失败: {e}")
                    continue
        
        logger.info(f"✅ 批量获取财务数据完成: {len(result)}/{total}")
        return result
    
    def _save_financial_to_db(self, stock_code: str, financial_data: Dict):
        """保存财务数据到数据库"""
        try:
            from sqlalchemy import text
            from data_warehouse.db import get_shared_engine
            from datetime import date
            
            ts_code = self._normalize_code(stock_code)
            today = date.today()
            # 使用当前季度作为end_date
            _q_month = ((today.month - 1) // 3) * 3 + 3  # 3, 6, 9, or 12
            _q_day = 31 if _q_month == 12 else 30
            quarter_end = date(today.year, _q_month, _q_day)
            
            engine = get_shared_engine()
            with engine.connect() as conn:
                # 使用UPSERT
                query = text("""
                    INSERT INTO fact_fundamental (ts_code, end_date, report_type, roe, gross_margin, net_margin, debt_ratio, op_cf, profit_volatility, data_quality, sources_used)
                    VALUES (:ts_code, :end_date, 'latest', :roe, :gross_margin, :net_margin, :debt_ratio, :op_cf, :profit_volatility, 'B', ARRAY['tushare'])
                    ON CONFLICT (ts_code, end_date, report_type) DO UPDATE SET
                        roe = EXCLUDED.roe,
                        gross_margin = EXCLUDED.gross_margin,
                        net_margin = EXCLUDED.net_margin,
                        debt_ratio = EXCLUDED.debt_ratio,
                        op_cf = EXCLUDED.op_cf,
                        profit_volatility = EXCLUDED.profit_volatility,
                        updated_at = NOW()
                """)
                conn.execute(query, {
                    'ts_code': ts_code,
                    'end_date': quarter_end,
                    'roe': financial_data.get('roe_ttm', 0),
                    'gross_margin': financial_data.get('gross_margin', 0),
                    'net_margin': financial_data.get('net_margin', 0),
                    'debt_ratio': financial_data.get('debt_ratio', 0),
                    'op_cf': financial_data.get('operating_cashflow', 0),
                    'profit_volatility': financial_data.get('profit_volatility', 0)
                })
                conn.commit()
        except Exception as e:
            logger.debug(f"保存财务数据到数据库失败 {stock_code}: {e}")
    
    def get_sector_moneyflow(self, trade_date: Optional[str] = None) -> Optional[pd.DataFrame]:
        """
        获取板块资金流向数据
        
        Args:
            trade_date: 交易日期，格式：YYYYMMDD，如果为None则使用最新交易日
        
        Returns:
            DataFrame: 板块资金流向数据
        """
        if not self.available:
            return None
        
        try:
            if trade_date is None:
                # 获取最新交易日
                today = datetime.now()
                trade_date = today.strftime('%Y%m%d')
            
            # 获取板块资金流向（同花顺）
            try:
                df = self.pro.moneyflow_hsgt(
                    trade_date=trade_date,
                    fields='trade_date,ggt_ss,ggt_sz,hgt,hk_hold_amount,ggt_ss_amount,ggt_sz_amount'
                )
                if df is not None and not df.empty:
                    return df
            except Exception as e:
                logger.debug(f"获取沪深港通资金流向失败: {e}")
            
            # 获取行业资金流向（同花顺）使用 moneyflow_ind_ths，非个股 moneyflow_ths
            try:
                df = self.pro.moneyflow_ind_ths(
                    trade_date=trade_date,
                    fields='trade_date,ts_code,industry,net_amount'
                )
                if df is not None and not df.empty:
                    return df
            except Exception as e:
                logger.debug(f"获取行业资金流向失败: {e}")
            
            return None
            
        except Exception as e:
            logger.error(f"❌ 获取板块资金流向失败: {e}", exc_info=True)
            return None
    
    def get_concept_sectors(self, trade_date: Optional[str] = None) -> Optional[pd.DataFrame]:
        """
        获取概念板块数据
        
        Args:
            trade_date: 交易日期，格式：YYYYMMDD，如果为None则使用最新交易日
        
        Returns:
            DataFrame: 概念板块数据
        """
        if not self.available:
            return None
        
        try:
            if trade_date is None:
                today = datetime.now()
                trade_date = today.strftime('%Y%m%d')
            
            # 获取同花顺概念板块
            try:
                df = self.pro.concept_detail(
                    trade_date=trade_date,
                    fields='trade_date,concept_name,concept_code'
                )
                if df is not None and not df.empty:
                    return df
            except Exception as e:
                logger.debug(f"获取概念板块失败: {e}")
            
            return None
            
        except Exception as e:
            logger.error(f"❌ 获取概念板块失败: {e}", exc_info=True)
            return None
    
    def get_industry_performance(self, trade_date: Optional[str] = None) -> Optional[pd.DataFrame]:
        """
        获取行业表现数据
        
        Args:
            trade_date: 交易日期，格式：YYYYMMDD，如果为None则使用最新交易日
        
        Returns:
            DataFrame: 行业表现数据
        """
        if not self.available:
            return None
        
        try:
            if trade_date is None:
                today = datetime.now()
                trade_date = today.strftime('%Y%m%d')
            
            # 获取申万行业分类数据
            try:
                df = self.pro.index_classify(
                    level='L1',
                    src='SW2021'
                )
                if df is not None and not df.empty:
                    return df
            except Exception as e:
                logger.debug(f"获取行业分类失败: {e}")
            
            return None
            
        except Exception as e:
            logger.error(f"❌ 获取行业表现失败: {e}", exc_info=True)
            return None
    
    def get_express(self, stock_code: Optional[str] = None, start_date: Optional[str] = None, end_date: Optional[str] = None) -> Optional[pd.DataFrame]:
        """
        获取上市公司业绩快报
        
        Args:
            stock_code: 股票代码（如 '000001.SZ'），如果为None则获取所有股票
            start_date: 开始日期，格式：YYYYMMDD
            end_date: 结束日期，格式：YYYYMMDD
        
        Returns:
            DataFrame: 业绩快报数据，包含：
                - ts_code: 股票代码
                - ann_date: 公告日期
                - end_date: 报告期
                - revenue: 营业收入（元）
                - operate_profit: 营业利润（元）
                - total_profit: 利润总额（元）
                - n_income: 净利润（元）**关键字段：>0表示盈利，<0表示亏损**
                - total_assets: 总资产（元）
                - total_equity: 净资产（元）
                - eps: 每股收益（元）
                - bps: 每股净资产（元）
                - yoy_sales: 营业收入同比增长率（%）
                - yoy_op: 营业利润同比增长率（%）
                - yoy_tp: 利润总额同比增长率（%）
                - yoy_dedu_np: 净利润同比增长率（%）
        """
        if not self.available:
            return None
        
        try:
            params = {}
            
            if stock_code:
                ts_code = self._normalize_code(stock_code)
                params['ts_code'] = ts_code
            
            if start_date:
                # 转换日期格式：YYYY-MM-DD -> YYYYMMDD
                if '-' in start_date:
                    start_date = start_date.replace('-', '')
                params['start_date'] = start_date
            
            if end_date:
                # 转换日期格式：YYYY-MM-DD -> YYYYMMDD
                if '-' in end_date:
                    end_date = end_date.replace('-', '')
                params['end_date'] = end_date
            
            # 调用业绩快报接口
            df = self.pro.express(**params)
            
            if df is None or df.empty:
                logger.debug(f"⚠️ 未获取到业绩快报数据: {params}")
                return None
            
            logger.debug(f"✅ 成功获取业绩快报数据: {len(df)} 条记录")
            return df
            
        except Exception as e:
            logger.error(f"❌ 获取业绩快报失败: {e}", exc_info=True)
            return None
    
    def get_latest_quarter_profit_status(self, stock_code: str) -> Optional[Dict]:
        """
        获取最新季度的盈亏状态
        
        Args:
            stock_code: 股票代码（如 '000001' 或 '000001.SZ'）
        
        Returns:
            dict: 包含以下字段：
                - is_profit: bool, True表示盈利，False表示亏损
                - net_profit: float, 净利润（元）
                - end_date: str, 报告期（YYYYMMDD）
                - ann_date: str, 公告日期（YYYYMMDD）
                - revenue: float, 营业收入（元）
                - eps: float, 每股收益（元）
                - yoy_sales: float, 营业收入同比增长率（%）
                - yoy_dedu_np: float, 净利润同比增长率（%）
            如果获取失败返回None
        """
        if not self.available:
            return None
        
        try:
            ts_code = self._normalize_code(stock_code)
            
            # 获取业绩快报（不指定日期，获取最新）
            df = self.get_express(stock_code=ts_code)
            
            if df is None or df.empty:
                logger.debug(f"⚠️ 未获取到 {ts_code} 的业绩快报数据")
                return None
            
            # 按报告期排序，获取最新一期
            df_sorted = df.sort_values('end_date', ascending=False)
            latest = df_sorted.iloc[0]
            
            # 获取净利润
            net_profit = float(latest.get('n_income', 0) or 0)
            
            result = {
                'is_profit': net_profit > 0,  # 净利润>0表示盈利
                'net_profit': net_profit,
                'end_date': str(latest.get('end_date', '')),
                'ann_date': str(latest.get('ann_date', '')),
                'revenue': float(latest.get('revenue', 0) or 0),
                'eps': float(latest.get('eps', 0) or 0),
                'yoy_sales': float(latest.get('yoy_sales', 0) or 0),
                'yoy_dedu_np': float(latest.get('yoy_dedu_np', 0) or 0),
            }
            
            logger.debug(f"✅ {ts_code} 最新季度业绩: {'盈利' if result['is_profit'] else '亏损'}, 净利润: {net_profit:,.0f}元")
            return result
            
        except Exception as e:
            logger.error(f"❌ 获取最新季度盈亏状态失败 {stock_code}: {e}", exc_info=True)
            return None

