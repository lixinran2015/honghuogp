"""
财务数据获取器
优先使用Tushare Pro获取财务数据，失败则使用akshare
"""

import logging
from typing import Dict, List, Optional
import pandas as pd
import time

logger = logging.getLogger(__name__)


class FinancialDataFetcher:
    """财务数据获取器类"""
    
    def __init__(self):
        """初始化财务数据获取器（复用 TushareService 单例，避免重复初始化）"""
        self.tushare_service = None
        self.tushare_available = False
        try:
            from backend.services.service_manager import get_service_manager
            self.tushare_service = get_service_manager().get_tushare_service()
            self.tushare_available = self.tushare_service.available
            if self.tushare_available:
                logger.info("✅ 财务数据获取器：优先使用Tushare Pro")
        except Exception as e:
            try:
                from backend.services.tushare_service import TushareService
                self.tushare_service = TushareService()
                self.tushare_available = self.tushare_service.available
                if self.tushare_available:
                    logger.info("✅ 财务数据获取器：优先使用Tushare Pro")
            except Exception as e2:
                logger.warning(f"⚠️ Tushare服务不可用: {e2}")
        
        # akshare作为备选
        try:
            import akshare as ak
            self.ak = ak
            self.akshare_available = True
            if not self.tushare_available:
                logger.info("✅ 财务数据获取器：使用akshare（备选）")
        except ImportError:
            logger.warning("⚠️ akshare未安装，财务数据获取可能受限")
            self.akshare_available = False
            self.ak = None
    
    def get_stock_financial_data(self, stock_code: str) -> Optional[Dict]:
        """
        获取单只股票的财务数据
        优先使用Tushare Pro，失败则使用akshare
        
        Args:
            stock_code: 股票代码（如 '000001', 'sh000001'）
        
        Returns:
            dict: 财务数据，包含：
                - roe_ttm: ROE（TTM）
                - gross_margin: 毛利率
                - net_margin: 净利率
                - operating_cashflow: 经营现金流
                - debt_ratio: 负债率
                - profit_volatility: 盈利波动率（需要计算）
        """
        # 优先使用Tushare Pro
        if self.tushare_available and self.tushare_service:
            try:
                financial_data = self.tushare_service.get_financial_data(stock_code)
                if financial_data:
                    logger.debug(f"✅ 使用Tushare获取财务数据: {stock_code}")
                    return financial_data
            except Exception as e:
                logger.debug(f"⚠️ Tushare获取财务数据失败 {stock_code}: {e}，尝试akshare...")
        
        # 如果Tushare失败，使用akshare（备选）
        if not self.akshare_available:
            return None
        
        try:
            # 标准化股票代码（去掉前缀，只保留6位数字）
            code = self._normalize_code(stock_code)
            
            # 过滤掉北交所股票（bj开头）和其他非A股代码
            if code.startswith('bj') or len(code) != 6 or not code.isdigit():
                logger.debug(f"⚠️ 跳过非A股代码: {stock_code} -> {code}")
                return None
            
            # 获取财务分析指标
            # 注意：akshare的财务接口可能不稳定，暂时返回默认值
            # 后续可以接入更稳定的数据源（如Tushare Pro）
            try:
                # 尝试获取财务数据，如果失败则返回默认值
                df = None
                error_msg = None
                try:
                    # 尝试多个财务接口
                    try:
                        df = self.ak.stock_financial_analysis_indicator_em(symbol=code)
                        if df is not None and not df.empty:
                            logger.debug(f"✅ 使用 stock_financial_analysis_indicator_em 获取 {code} 财务数据")
                    except Exception as e1:
                        error_msg = str(e1)
                        logger.debug(f"⚠️ stock_financial_analysis_indicator_em 失败 {code}: {e1}")
                        # 尝试备用接口
                        try:
                            df = self.ak.stock_financial_analysis_indicator(symbol=code)
                            if df is not None and not df.empty:
                                logger.debug(f"✅ 使用 stock_financial_analysis_indicator 获取 {code} 财务数据")
                        except Exception as e2:
                            logger.debug(f"⚠️ stock_financial_analysis_indicator 也失败 {code}: {e2}")
                except Exception as e:
                    error_msg = str(e)
                    logger.debug(f"⚠️ 财务接口调用异常 {code}: {e}")
                
                if df is None or (hasattr(df, 'empty') and df.empty):
                    # 尝试使用 stock_financial_abstract_ths（这个接口更可靠）
                    logger.debug(f"⚠️ 股票 {code} 主要财务接口失败，尝试 stock_financial_abstract_ths...")
                    try:
                        df = self.ak.stock_financial_abstract_ths(symbol=code)
                        if df is not None and not df.empty:
                            logger.debug(f"✅ 使用 stock_financial_abstract_ths 获取 {code} 财务数据")
                        else:
                            logger.debug(f"⚠️ stock_financial_abstract_ths 返回空数据 {code}")
                            return None
                    except Exception as e3:
                        logger.debug(f"⚠️ stock_financial_abstract_ths 也失败 {code}: {e3}")
                        # 如果所有接口都失败，返回None而不是全0，让调用方知道获取失败
                        logger.warning(f"⚠️ 股票 {code} 无法获取财务数据，所有接口均失败")
                        return None
                
                # 获取最新一期数据（通常是第一行）
                latest = df.iloc[0]
                
                # 检查是否是 stock_financial_abstract_ths 接口返回的数据
                is_abstract_ths = '净资产收益率-摊薄' in df.columns or '销售净利率' in df.columns
                
                # 安全获取字段值（尝试多个可能的列名）
                roe = 0
                if is_abstract_ths:
                    # stock_financial_abstract_ths 接口
                    if '净资产收益率-摊薄' in latest.index:
                        roe_str = str(latest['净资产收益率-摊薄'])
                        # 去除%符号并转换
                        roe = self._safe_float(roe_str.replace('%', ''))
                    elif '净资产收益率' in latest.index:
                        roe_str = str(latest['净资产收益率'])
                        roe = self._safe_float(roe_str.replace('%', ''))
                else:
                    # 其他接口
                    if '净资产收益率-摊薄' in latest.index:
                        roe = latest['净资产收益率-摊薄']
                    elif '净资产收益率' in latest.index:
                        roe = latest['净资产收益率']
                    elif 'ROE' in latest.index:
                        roe = latest['ROE']
                
                # 获取毛利率（stock_financial_abstract_ths 没有毛利率，需要从其他接口获取）
                gross_margin = 0
                if not is_abstract_ths:
                    if '销售毛利率' in latest.index:
                        gross_margin = latest['销售毛利率']
                    elif '毛利率' in latest.index:
                        gross_margin = latest['毛利率']
                else:
                    # stock_financial_abstract_ths 没有毛利率，尝试从多个接口获取
                    # 方法1: 尝试从 stock_financial_analysis_indicator_em 获取
                    try:
                        gross_df = self.ak.stock_financial_analysis_indicator_em(symbol=code)
                        if gross_df is not None and not gross_df.empty:
                            gross_latest = gross_df.iloc[0]
                            if '销售毛利率' in gross_latest.index:
                                gross_margin = self._safe_float(gross_latest['销售毛利率'])
                            elif '毛利率' in gross_latest.index:
                                gross_margin = self._safe_float(gross_latest['毛利率'])
                    except Exception as e:
                        logger.debug("获取毛利率失败 %s: %s", code, e)

                    # 方法2: 如果方法1失败，尝试从利润表计算毛利率
                    if gross_margin == 0:
                        # 尝试多个利润表接口
                        income_interfaces = [
                            ('stock_profit_sheet_by_report_em', ['营业收入', '营业总收入'], ['营业成本', '营业总成本']),
                            ('stock_profit_forecast_em', ['毛利率'], None),
                        ]
                        
                        for interface_name, revenue_fields, cost_fields in income_interfaces:
                            if gross_margin > 0:
                                break
                            try:
                                if hasattr(self.ak, interface_name):
                                    interface_func = getattr(self.ak, interface_name)
                                    income_df = interface_func(symbol=code)
                                    if income_df is not None and not income_df.empty:
                                        income_latest = income_df.iloc[0]
                                        
                                        # 如果是毛利率字段，直接获取
                                        if cost_fields is None:
                                            # 直接获取毛利率
                                            for field in revenue_fields:
                                                if field in income_latest.index:
                                                    gross_margin = self._safe_float(income_latest[field])
                                                    if gross_margin > 0:
                                                        logger.debug(f"从{interface_name}获取毛利率 {code}: {gross_margin:.2f}%")
                                                        break
                                        else:
                                            # 计算毛利率
                                            revenue = 0
                                            cost = 0
                                            for field in revenue_fields:
                                                if field in income_latest.index:
                                                    revenue = self._safe_float(income_latest[field])
                                                    break
                                            for field in cost_fields:
                                                if field in income_latest.index:
                                                    cost = self._safe_float(income_latest[field])
                                                    break
                                            
                                            # 毛利率 = (营业收入 - 营业成本) / 营业收入 * 100
                                            if revenue > 0:
                                                gross_margin = ((revenue - cost) / revenue) * 100
                                                logger.debug(f"从{interface_name}计算毛利率 {code}: {gross_margin:.2f}%")
                            except Exception as e:
                                logger.debug(f"从{interface_name}获取毛利率失败 {code}: {e}")
                                continue
                
                # 获取净利率
                net_margin = 0
                if is_abstract_ths:
                    if '销售净利率' in latest.index:
                        net_margin_str = str(latest['销售净利率'])
                        net_margin = self._safe_float(net_margin_str.replace('%', ''))
                else:
                    if '销售净利率' in latest.index:
                        net_margin = latest['销售净利率']
                    elif '净利率' in latest.index:
                        net_margin = latest['净利率']
                
                # 获取负债率
                debt_ratio = 0
                total_debt = 0
                total_asset = 0
                
                if is_abstract_ths:
                    if '资产负债率' in latest.index:
                        debt_str = str(latest['资产负债率'])
                        debt_ratio = self._safe_float(debt_str.replace('%', ''))
                    # 尝试从资产负债表获取总负债和总资产来计算负债率
                    try:
                        balance_df = self.ak.stock_balance_sheet_by_report_em(symbol=code)
                        if balance_df is not None and not balance_df.empty:
                            balance_latest = balance_df.iloc[0]
                            if '负债合计' in balance_latest.index:
                                total_debt = self._safe_float(balance_latest['负债合计'])
                            if '资产总计' in balance_latest.index:
                                total_asset = self._safe_float(balance_latest['资产总计'])
                            # 如果负债率为0但总负债和总资产都有值，则计算负债率
                            if debt_ratio == 0 and total_asset > 0:
                                debt_ratio = (total_debt / total_asset) * 100
                    except Exception as e:
                        logger.debug("获取负债率失败 %s: %s", code, e)
                else:
                    if '资产负债率' in latest.index:
                        debt_ratio = latest['资产负债率']
                    elif '负债率' in latest.index:
                        debt_ratio = latest['负债率']
                
                # 获取经营现金流（stock_financial_abstract_ths 有每股经营现金流）
                operating_cashflow = 0.0
                if is_abstract_ths:
                    # 方法1: 从 stock_financial_cash_ths 获取
                    try:
                        cashflow_df = self.ak.stock_financial_cash_ths(symbol=code)
                        if cashflow_df is not None and not cashflow_df.empty:
                            latest_cashflow = cashflow_df.iloc[0]
                            # 尝试多个可能的字段名
                            possible_keys = [
                                '*经营活动产生的现金流量净额',
                                '经营活动产生的现金流量净额',
                                '经营活动现金流量净额',
                                '经营现金流',
                                '经营活动现金流',
                                'n_cashflow_act'
                            ]
                            for key in possible_keys:
                                if key in latest_cashflow.index:
                                    operating_cashflow = self._safe_float(latest_cashflow[key])
                                    if operating_cashflow != 0:
                                        logger.debug(f"从stock_financial_cash_ths获取经营现金流 {code}: {operating_cashflow}")
                                        break
                    except Exception as e:
                        logger.debug(f"获取现金流数据失败 {code}: {e}")
                    
                    # 方法2: 如果方法1失败，尝试从其他接口获取
                    if operating_cashflow == 0:
                        # 尝试多个现金流量表接口
                        cashflow_interfaces = [
                            'stock_cash_flow_sheet_by_report_em',
                            'stock_financial_cash_flow_ths',
                        ]
                        
                        for interface_name in cashflow_interfaces:
                            if operating_cashflow != 0:
                                break
                            try:
                                if hasattr(self.ak, interface_name):
                                    interface_func = getattr(self.ak, interface_name)
                                    cashflow_df = interface_func(symbol=code)
                                    if cashflow_df is not None and not cashflow_df.empty:
                                        latest_cashflow = cashflow_df.iloc[0]
                                        possible_keys = [
                                            '*经营活动产生的现金流量净额',
                                            '经营活动产生的现金流量净额',
                                            '经营活动现金流量净额',
                                            '经营现金流',
                                            '经营活动现金流',
                                            'n_cashflow_act'
                                        ]
                                        for key in possible_keys:
                                            if key in latest_cashflow.index:
                                                operating_cashflow = self._safe_float(latest_cashflow[key])
                                                if operating_cashflow != 0:
                                                    logger.debug(f"从{interface_name}获取经营现金流 {code}: {operating_cashflow}")
                                                    break
                            except Exception as e:
                                logger.debug(f"从{interface_name}获取现金流数据失败 {code}: {e}")
                                continue
                else:
                    # 非abstract_ths接口，尝试从现金流量表获取
                    try:
                        cashflow_df = self.ak.stock_financial_cash_ths(symbol=code)
                        if cashflow_df is not None and not cashflow_df.empty:
                            latest_cashflow = cashflow_df.iloc[0]
                            possible_keys = [
                                '*经营活动产生的现金流量净额',
                                '经营活动产生的现金流量净额',
                                '经营活动现金流量净额',
                                '经营现金流',
                                '经营活动现金流'
                            ]
                            for key in possible_keys:
                                if key in latest_cashflow.index:
                                    operating_cashflow = self._safe_float(latest_cashflow[key])
                                    if operating_cashflow != 0:
                                        break
                    except Exception as e:
                        logger.debug("获取经营现金流失败 %s: %s", code, e)

                # 获取营业收入 revenue、营收同比增长 yoy_sales（行业周期采集依赖）
                revenue = 0.0
                yoy_sales = 0.0
                try:
                    profit_df = self.ak.stock_profit_sheet_by_report_em(symbol=code)
                    if profit_df is not None and not profit_df.empty and len(profit_df) >= 2:
                        latest_row = profit_df.iloc[0]
                        for col in profit_df.columns:
                            if col == '营业收入' or col == '营业总收入':
                                val = self._safe_float(latest_row.get(col, 0))
                                if val > 0:
                                    revenue = val  # 元
                                    break
                            if '营业收入' in str(col) and ('同比' in str(col) or '增长' in str(col)):
                                val = self._safe_float(latest_row.get(col, 0))
                                if val != 0:
                                    yoy_sales = val
                                    break
                        if yoy_sales == 0:
                            for col in profit_df.columns:
                                if '营业总收入' in str(col) and ('同比' in str(col) or '增长' in str(col)):
                                    val = self._safe_float(latest_row.get(col, 0))
                                    if val != 0:
                                        yoy_sales = val
                                        break
                except Exception as e:
                    logger.debug(f"获取营收/同比失败 {code}: {e}")
                
                # 转换百分比（如果值>1，认为是百分比，需要除以100）
                roe_val = self._safe_float(roe)
                gross_margin_val = self._safe_float(gross_margin)
                net_margin_val = self._safe_float(net_margin)
                debt_ratio_val = self._safe_float(debt_ratio)
                
                # 经营现金流单位标准化为元（akshare 部分接口可能返回万元）
                op_cf_yuan = operating_cashflow
                if revenue and abs(operating_cashflow) > 0 and abs(revenue) > 1e7:
                    if abs(operating_cashflow / revenue) < 1e-6:
                        op_cf_yuan = operating_cashflow * 1e4  # 万元→元
                        logger.debug(f"op_cf 单位矫正（万元→元）: {code} {operating_cashflow} -> {op_cf_yuan:,.0f}")

                financial_data = {
                    'roe_ttm': roe_val / 100 if roe_val > 1 else roe_val,  # ROE转换为小数
                    'gross_margin': gross_margin_val / 100 if gross_margin_val > 1 else gross_margin_val,
                    'net_margin': net_margin_val / 100 if net_margin_val > 1 else net_margin_val,
                    'debt_ratio': debt_ratio_val / 100 if debt_ratio_val > 1 else debt_ratio_val,
                    'operating_cashflow': op_cf_yuan,
                    'total_debt': total_debt,
                    'total_asset': total_asset,
                    'profit_volatility': 0.0,  # 需要计算
                    'yoy_sales': yoy_sales,  # 营收同比增长（%）
                    'revenue': revenue if revenue > 0 else None,  # 营业收入（元）
                }
                
                # 如果负债率为0但总负债和总资产都有值，则计算负债率
                if financial_data['debt_ratio'] == 0 and total_asset > 0:
                    financial_data['debt_ratio'] = total_debt / total_asset
                
                # 计算盈利波动率（基于最近3年的净利润）
                try:
                    profit_df = self.ak.stock_financial_benefit_ths(symbol=code)
                    if not profit_df.empty and len(profit_df) >= 3:
                        # 获取最近3年的净利润
                        profits = []
                        for _, row in profit_df.head(3).iterrows():
                            profit = self._safe_float(row.get('净利润', 0))
                            if profit > 0:
                                profits.append(profit)
                        
                        if len(profits) >= 2:
                            # 计算波动率（标准差/均值）
                            import numpy as np
                            profits_array = np.array(profits)
                            mean_profit = profits_array.mean()
                            if mean_profit > 0:
                                std_profit = profits_array.std()
                                financial_data['profit_volatility'] = std_profit / mean_profit
                except Exception as e:
                    logger.debug(f"计算盈利波动率失败 {code}: {e}")
                
                return financial_data
                
            except Exception as e:
                logger.warning(f"⚠️ 获取股票 {code} 财务数据失败: {e}")
                return None
                
        except Exception as e:
            logger.error(f"❌ 获取财务数据异常 {stock_code}: {e}", exc_info=True)
            return None
    
    def batch_get_financial_data(self, stock_codes: List[str], delay: float = 0.1) -> Dict[str, Dict]:
        """
        批量获取财务数据（优先使用 Tushare 批量接口）
        
        Args:
            stock_codes: 股票代码列表
            delay: 每次请求之间的延迟（秒）
        
        Returns:
            dict: {stock_code: financial_data}
        """
        results = {}
        total = len(stock_codes)
        
        # 优先使用 Tushare 批量接口
        if self.tushare_available and self.tushare_service:
            try:
                logger.info(f"📥 使用 Tushare Pro 批量获取财务数据: {total} 只股票")
                tushare_results = self.tushare_service.batch_get_financial_data(stock_codes, delay=delay)
                if tushare_results:
                    # 标准化代码
                    for code, data in tushare_results.items():
                        normalized_code = self._normalize_code(code)
                        results[normalized_code] = data
                    logger.info(f"✅ Tushare 批量获取完成: {len(results)}/{total} 只股票")
                    return results
            except Exception as e:
                logger.warning(f"⚠️ Tushare 批量获取失败: {e}，降级为逐只获取")
        
        # 降级：逐只获取
        logger.info(f"📥 逐只获取财务数据: {total} 只股票")
        for idx, code in enumerate(stock_codes, 1):
            try:
                financial_data = self.get_stock_financial_data(code)
                normalized_code = self._normalize_code(code)
                
                if financial_data is not None:
                    results[normalized_code] = financial_data
                else:
                    results[normalized_code] = {
                        'roe_ttm': 0.0, 'gross_margin': 0.0, 'net_margin': 0.0,
                        'operating_cashflow': 0.0, 'debt_ratio': 0.0, 'profit_volatility': 0.0
                    }
                
                if idx % 20 == 0 or idx == total:
                    logger.info(f"📊 财务数据获取进度: {idx}/{total} ({idx*100//total}%)")
                
                if idx < total:
                    time.sleep(delay)
                    
            except Exception as e:
                logger.warning(f"⚠️ 获取股票 {code} 财务数据失败: {e}")
                continue
        
        logger.info(f"✅ 批量获取财务数据完成: {len(results)}/{total} 只股票")
        return results
    
    def _normalize_code(self, code: str) -> str:
        """
        标准化股票代码格式（去掉前缀，只保留6位数字）
        
        Args:
            code: 股票代码（可能是 '000001', 'sh000001', 'sz000001' 等格式）
        
        Returns:
            str: 标准化后的代码（6位数字）
        """
        code = str(code).strip()
        
        # 如果包含sh或sz前缀，去掉
        if code.startswith('sh') or code.startswith('sz'):
            code = code[2:]
        
        # 确保是6位数字
        if code.isdigit() and len(code) == 6:
            return code
        
        return code
    
    def _safe_float(self, value) -> float:
        """安全转换为float"""
        try:
            if pd.isna(value) or value == '' or value is None:
                return 0.0
            return float(value)
        except (ValueError, TypeError):
            return 0.0

