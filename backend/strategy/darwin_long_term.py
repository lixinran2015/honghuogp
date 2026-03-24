"""
达尔文公司长期筛选器
找出可以长期拿、穿越周期的公司，作为"长期资产池"
"""

from typing import List, Dict, Optional
import logging
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from backend.models.stock_data import StockData
from backend.models.strategy_result import StrategyResult

logger = logging.getLogger(__name__)


class DarwinLongTermFilter:
    """达尔文公司长期筛选器"""
    
    def __init__(self):
        """初始化达尔文长期筛选器"""
        # 初始化服务类
        from backend.services.industry.industry_cycle_service import IndustryCycleService
        from backend.services.financial.multi_period_financial_service import MultiPeriodFinancialService
        from backend.services.financial.industry_percentile_service import IndustryPercentileService
        from backend.services.tushare_service import TushareService
        
        self.industry_cycle_service = IndustryCycleService()
        self.tushare_service = TushareService()
        self.multi_period_service = MultiPeriodFinancialService(self.tushare_service)
        self.industry_percentile_service = IndustryPercentileService(self.tushare_service)
    
    def filter_darwin_companies(
        self,
        stock_data: List[StockData],
        financial_data: Optional[Dict[str, Dict]] = None,
        limit: int = 20,
        min_samples: int = 3
    ) -> StrategyResult:
        """
        筛选达尔文公司（长期持仓候选）
        
        Args:
            stock_data: 股票数据模型列表
            financial_data: 财务数据字典 {stock_code: {财务指标...}}
            limit: 返回数量限制
            min_samples: 最小样本数
        
        Returns:
            StrategyResult: 策略筛选结果（包含darwin_core和darwin_watch）
        """
        try:
            if not stock_data:
                return StrategyResult(
                    darwin_core=[],
                    darwin_watch=[],
                    warning="输入数据为空",
                    filter_steps={}
                )
            
            # 快速检查：如果没有财务数据，提前返回（长期策略需要财务数据）
            if not financial_data:
                logger.info("⚡ 长期策略：缺少财务数据，跳过（需要财务数据进行筛选）")
                return StrategyResult(
                    darwin_core=[],
                    darwin_watch=[],
                    warning="缺少财务数据，长期策略需要财务数据进行筛选",
                    filter_steps={"skipped": "no_financial_data"}
                )
            
            # 转换为DataFrame以便使用现有逻辑（临时方案）
            stock_dicts = [stock.to_dict() for stock in stock_data]
            df = pd.DataFrame(stock_dicts)
            
            filter_steps = {}
            
            # Step 0: 数据清洗和次新股过滤
            df = self._clean_financial_data(df)
            filter_steps["after_clean"] = len(df)
            logger.info(f"✅ Step 0: 数据清洗后剩余 {len(df)} 只股票")
            
            df = self._filter_new_stocks(df, min_listing_years=1.0)
            filter_steps["after_new_stock_filter"] = len(df)
            logger.info(f"✅ Step 0: 次新股过滤后剩余 {len(df)} 只股票")
            
            if df.empty:
                return StrategyResult(
                    darwin_core=[],
                    darwin_watch=[],
                    warning="数据清洗或次新股过滤后无股票",
                    filter_steps=filter_steps
                )
            
            # Step 1: 第一层级 - 财务健康过滤（排雷指标）
            healthy_stocks = self._filter_financial_health(df, financial_data)
            filter_steps["healthy_stocks"] = len(healthy_stocks)
            logger.info(f"✅ Step 1: 财务健康筛选（排雷）后剩余 {len(healthy_stocks)} 只股票")
            
            if healthy_stocks.empty:
                return StrategyResult(
                    darwin_core=[],
                    darwin_watch=[],
                    warning="未找到财务健康的股票",
                    filter_steps=filter_steps
                )
            
            # Step 2: 第二层级 - 核心指标检查
            core_stocks = self._filter_core_indicators(healthy_stocks, financial_data)
            filter_steps["core_stocks"] = len(core_stocks)
            logger.info(f"✅ Step 2: 核心指标筛选后剩余 {len(core_stocks)} 只股票")
            
            if core_stocks.empty:
                return StrategyResult(
                    darwin_core=[],
                    darwin_watch=[],
                    warning="未找到满足核心指标的股票",
                    filter_steps=filter_steps
                )
            
            # Step 3: 第三层级 - 交叉验证
            validated_stocks = self._cross_validation(core_stocks, financial_data)
            filter_steps["validated_stocks"] = len(validated_stocks)
            logger.info(f"✅ Step 3: 交叉验证后剩余 {len(validated_stocks)} 只股票")
            
            if validated_stocks.empty:
                return StrategyResult(
                    darwin_core=[],
                    darwin_watch=[],
                    warning="未通过交叉验证的股票",
                    filter_steps=filter_steps
                )
            
            # Step 4: 盈利质量（历史趋势）
            quality_stocks = self._filter_profit_quality(validated_stocks, financial_data)
            filter_steps["quality_stocks"] = len(quality_stocks)
            logger.info(f"✅ Step 4: 盈利质量筛选后剩余 {len(quality_stocks)} 只股票")
            
            # Step 5: 行业与地位
            industry_stocks = self._filter_industry_position(quality_stocks)
            filter_steps["industry_stocks"] = len(industry_stocks)
            logger.info(f"✅ Step 5: 行业地位筛选后剩余 {len(industry_stocks)} 只股票")
            
            # Step 6: 估值合理性
            darwin_core_dicts, darwin_watch_dicts = self._filter_valuation(industry_stocks, financial_data, limit=limit)
            filter_steps["darwin_core"] = len(darwin_core_dicts)
            filter_steps["darwin_watch"] = len(darwin_watch_dicts)
            
            # 将字典列表转换为StockData列表，并设置longTermTag和评分
            darwin_core = []
            for core_dict in darwin_core_dicts:
                try:
                    stock = StockData.from_dict(core_dict)
                    # 设置核心持仓标签
                    stock.extra['longTermTag'] = '核心持仓'
                    stock.extra['long_term_tag'] = '核心持仓'
                    # 计算并设置达尔文评分（如果有财务数据）
                    fin_data = None
                    if financial_data:
                        code = stock.code
                        clean_code = str(code).replace('sh', '').replace('sz', '').replace('SH', '').replace('SZ', '').strip()
                        for fin_code, fin_info in financial_data.items():
                            fin_clean = str(fin_code).replace('sh', '').replace('sz', '').replace('SH', '').replace('SZ', '').strip()
                            if fin_clean == clean_code:
                                fin_data = fin_info
                                break
                    
                    if fin_data:
                        # 使用完整的达尔文评分逻辑
                        from backend.services.darwin.darwin_scorer import DarwinScorer
                        darwin_scorer = DarwinScorer()
                        
                        # 将stock转换为字典格式
                        stock_dict = stock.to_dict()
                        
                        # 计算达尔文评分
                        darwin_score = darwin_scorer.calculate_darwin_score(
                            stock_data=stock_dict,
                            financial_data=fin_data,
                            commodity_data=None
                        )
                        
                        # 计算财务健康系数
                        financial_health = darwin_scorer.calculate_financial_health(fin_data)
                        
                        stock.extra['darwinScore'] = darwin_score
                        stock.extra['financialHealth'] = financial_health
                        # 最终得分 = 达尔文评分（财务健康度已作为15%权重包含在评分中，不再相乘）
                        stock.extra['finalScore'] = darwin_score
                    else:
                        # 没有财务数据，使用默认评分
                        stock.extra['darwinScore'] = 50
                        stock.extra['financialHealth'] = 0.7
                        stock.extra['finalScore'] = 35
                    darwin_core.append(stock)
                except Exception as e:
                    logger.warning(f"转换核心持仓股票失败: {e}")
                    continue
            
            darwin_watch = []
            for watch_dict in darwin_watch_dicts:
                try:
                    stock = StockData.from_dict(watch_dict)
                    # 设置观察标签
                    stock.extra['longTermTag'] = '观察'
                    stock.extra['long_term_tag'] = '观察'
                    # 计算并设置达尔文评分（如果有财务数据）
                    fin_data = None
                    if financial_data:
                        code = stock.code
                        clean_code = str(code).replace('sh', '').replace('sz', '').replace('SH', '').replace('SZ', '').strip()
                        for fin_code, fin_info in financial_data.items():
                            fin_clean = str(fin_code).replace('sh', '').replace('sz', '').replace('SH', '').replace('SZ', '').strip()
                            if fin_clean == clean_code:
                                fin_data = fin_info
                                break
                    
                    if fin_data:
                        # 使用完整的达尔文评分逻辑
                        from backend.services.darwin.darwin_scorer import DarwinScorer
                        darwin_scorer = DarwinScorer()
                        
                        # 将stock转换为字典格式
                        stock_dict = stock.to_dict()
                        
                        # 计算达尔文评分
                        darwin_score = darwin_scorer.calculate_darwin_score(
                            stock_data=stock_dict,
                            financial_data=fin_data,
                            commodity_data=None
                        )
                        
                        # 计算财务健康系数
                        financial_health = darwin_scorer.calculate_financial_health(fin_data)
                        
                        stock.extra['darwinScore'] = darwin_score
                        stock.extra['financialHealth'] = financial_health
                        # 最终得分 = 达尔文评分（财务健康度已作为15%权重包含在评分中，不再相乘）
                        stock.extra['finalScore'] = darwin_score
                    else:
                        # 没有财务数据，使用默认评分
                        stock.extra['darwinScore'] = 50
                        stock.extra['financialHealth'] = 0.7
                        stock.extra['finalScore'] = 35
                    darwin_watch.append(stock)
                except Exception as e:
                    logger.warning(f"转换观察池股票失败: {e}")
                    continue
            
            # 检查样本数
            warning = None
            if len(darwin_core) < min_samples:
                warning = f"核心持仓池标的过少（{len(darwin_core)}只），策略可能过严或数据不足"
            
            return StrategyResult(
                darwin_core=darwin_core,
                darwin_watch=darwin_watch,
                warning=warning,
                filter_steps=filter_steps
            )
            
        except Exception as e:
            logger.error(f"达尔文筛选失败: {e}", exc_info=True)
            return StrategyResult(
                darwin_core=[],
                darwin_watch=[],
                warning=f"筛选过程出错: {str(e)}",
                filter_steps={}
            )
    
    def _filter_financial_health(
        self,
        df: pd.DataFrame,
        financial_data: Optional[Dict[str, Dict]],
        return_failed_reasons: bool = False,
        st_delisting_cache: Optional[Dict[str, bool]] = None
    ):
        """
        第一层级：财务健康过滤（排雷指标）
        
        实现9项排雷指标（一票否决）：
        1. ST/退市风险
        2. 资不抵债风险
        3. 持续亏损风险（连续2年扣非净利润≤0）
        4. 现金流断裂风险（区分行业周期）
        5. 利息偿付风险
        6-9. 商誉/关联交易/质押/审计
        
        Args:
            return_failed_reasons: 为 True 时返回 (passed_df, failed_reasons_dict)
            st_delisting_cache: 预取的 ST/退市 判定缓存 {ts_code: True/False}，减少 Tushare 调用
        """
        try:
            if financial_data is None or not financial_data:
                logger.warning("缺少财务数据，跳过财务健康筛选（保留所有股票）")
                return (df, {}) if return_failed_reasons else df
            
            candidates = []
            failed_reasons_dict = {} if return_failed_reasons else None
            code_col = 'code' if 'code' in df.columns else '代码'
            
            logger.info(f"开始财务健康筛选（排雷）：从 {len(df)} 只股票中筛选")
            
            for _, row in df.iterrows():
                code = row.get(code_col, '')
                if not code:
                    continue
                
                # 清理代码格式
                clean_code = str(code).replace('sh', '').replace('sz', '').replace('SH', '').replace('SZ', '').strip()
                
                # 转换为ts_code格式
                ts_code = self._normalize_to_ts_code(clean_code)
                
                # 查找财务数据
                fin_data = None
                for fin_code, fin_info in financial_data.items():
                    fin_clean = str(fin_code).replace('sh', '').replace('sz', '').replace('SH', '').replace('SZ', '').strip()
                    if fin_clean == clean_code:
                        fin_data = fin_info
                        break
                
                def _fail(reason: str):
                    if failed_reasons_dict is not None:
                        failed_reasons_dict[clean_code] = [reason]
                    logger.info(f"{clean_code} 排雷：{reason}")

                if not fin_data:
                    _fail("缺少财务数据（缺 fact_daily_fundamental，含ROE/毛利/净利等）")
                    continue

                # 0. 亏损股检查（有数据但 ROE/净利率 为负）
                roe_val = fin_data.get('roe_ttm') or fin_data.get('roe') or 0
                net_val = fin_data.get('net_margin_ttm') or fin_data.get('net_margin') or 0
                try:
                    roe_f = float(roe_val) if roe_val is not None else 0
                    net_f = float(net_val) if net_val is not None else 0
                except (TypeError, ValueError):
                    roe_f, net_f = 0, 0
                if roe_f < 0 or net_f < 0:
                    _fail("亏损股")
                    continue

                logger.debug(f"{clean_code} 开始排雷检查，财务数据字段: {list(fin_data.keys()) if fin_data else 'None'}")

                # 1. ST/退市风险检查（优先使用预取缓存）
                is_st = st_delisting_cache.get(ts_code) if st_delisting_cache is not None else None
                if is_st is None:
                    is_st = self._is_st_or_delisting(ts_code)
                if is_st:
                    _fail("ST/退市风险")
                    continue

                # 2. 资不抵债风险检查
                is_insolvent = self._is_insolvent(fin_data)
                if is_insolvent:
                    _fail("资不抵债风险")
                    continue

                # 3. 持续亏损风险检查（需要多期数据）
                has_loss = self._has_continuous_loss(ts_code, fin_data)
                if has_loss:
                    _fail("持续亏损风险")
                    continue
                
                # 4. 现金流断裂风险检查（区分行业周期）
                industry_name = row.get('industry', '') or (fin_data.get('industry', '') if fin_data else '') or row.get('sector', '')
                
                # 如果行业信息为空或者是"未知"，尝试从Tushare获取
                if not industry_name or industry_name == "未知" or industry_name.strip() == "":
                    try:
                        if self.tushare_service.available:
                            stock_basic = self.tushare_service.pro.stock_basic(
                                ts_code=ts_code,
                                fields='ts_code,industry'
                            )
                            if stock_basic is not None and not stock_basic.empty:
                                industry_name = stock_basic.iloc[0]['industry']
                                logger.debug(f"{clean_code} 从Tushare获取行业信息（排雷检查）：{industry_name}")
                    except Exception as e:
                        logger.debug(f"{clean_code} 从Tushare获取行业信息失败（排雷检查）：{e}")
                
                # 如果仍然没有行业信息，使用"未知"
                if not industry_name or industry_name.strip() == "":
                    industry_name = "未知"
                
                revenue_growth = fin_data.get('revenue_yoy', 0) if fin_data else 0
                has_cashflow_risk = self._has_cashflow_breakdown_risk(ts_code, industry_name, revenue_growth)
                if has_cashflow_risk:
                    _fail(f"现金流断裂风险（行业：{industry_name}，营收增长：{revenue_growth:.1f}%）")
                    continue

                # 5. 利息偿付风险检查
                has_interest_risk = self._has_interest_payment_risk(ts_code, fin_data)
                if has_interest_risk:
                    _fail("利息偿付风险")
                    continue

                # 6. 商誉减值风险检查
                has_goodwill_risk = self._has_goodwill_risk(ts_code, fin_data)
                if has_goodwill_risk:
                    _fail("商誉减值风险")
                    continue

                # 7. 关联交易风险检查
                has_related_risk = self._has_related_party_transaction_risk(ts_code, fin_data)
                if has_related_risk:
                    _fail("关联交易风险")
                    continue

                # 8. 大股东质押风险检查
                has_pledge_risk = self._has_major_shareholder_pledge_risk(ts_code)
                if has_pledge_risk:
                    _fail("大股东质押风险")
                    continue

                # 9. 审计意见风险检查
                has_audit_risk = self._has_audit_opinion_risk(ts_code)
                if has_audit_risk:
                    _fail("审计意见风险")
                    continue
                
                # 所有排雷指标通过
                logger.info(f"{clean_code} ✅ 通过所有排雷检查")
                row_dict = row.to_dict()
                if fin_data:
                    row_dict.update({
                        'roe': fin_data.get('roe', fin_data.get('roe_ttm', 0)),
                        'op_cf': fin_data.get('op_cf', fin_data.get('operating_cashflow', 0)),
                        'debt_ratio': fin_data.get('debt_ratio', 0)
                    })
                candidates.append(row_dict)
            
            logger.info(f"✅ 财务健康筛选（排雷）：从 {len(df)} 只股票中筛选出 {len(candidates)} 只")
            passed_df = pd.DataFrame(candidates) if candidates else pd.DataFrame()
            if return_failed_reasons:
                return passed_df, failed_reasons_dict or {}
            return passed_df

        except Exception as e:
            logger.error(f"财务健康筛选失败: {e}", exc_info=True)
            return (df, {}) if return_failed_reasons else df
    
    def _normalize_to_ts_code(self, code: str) -> str:
        """标准化股票代码为Tushare格式"""
        if len(code) == 6 and code.isdigit():
            if code.startswith('6'):
                return f"{code}.SH"
            elif code.startswith('0') or code.startswith('3'):
                return f"{code}.SZ"
        return code
    
    def _fetch_st_delisting_cache(self, ts_codes: list) -> Dict[str, bool]:
        """批量获取 ST/退市 判定，返回 {ts_code: True=有风险}"""
        cache = {}
        if not ts_codes or not self.tushare_service.available:
            return cache
        try:
            # Tushare stock_basic 支持逗号分隔的 ts_code 批量查询
            ts_str = ','.join(ts_codes[:100])  # 单次最多约100只
            df = self.tushare_service.pro.stock_basic(
                ts_code=ts_str,
                fields='ts_code,name,list_status'
            )
            if df is not None and not df.empty:
                for _, r in df.iterrows():
                    tc = r.get('ts_code', '')
                    is_risk = (
                        str(r.get('list_status', '')).strip() != 'L'
                        or 'ST' in str(r.get('name', ''))
                        or '*ST' in str(r.get('name', ''))
                    )
                    cache[tc] = bool(is_risk)
        except Exception as e:
            logger.debug(f"批量获取 ST/退市 失败: {e}，将逐只查询")
        return cache

    def _is_st_or_delisting(self, ts_code: str) -> bool:
        """检查ST/退市风险"""
        if not self.tushare_service.available:
            return False
        try:
            stock_basic = self.tushare_service.pro.stock_basic(
                ts_code=ts_code,
                fields='ts_code,name,list_status'
            )
            if stock_basic is not None and not stock_basic.empty:
                list_status = stock_basic.iloc[0]['list_status']
                if list_status != 'L':
                    return True
                name = stock_basic.iloc[0]['name']
                if 'ST' in name or '*ST' in name:
                    return True
        except Exception as e:
            logger.debug(f"检查ST/退市风险失败 {ts_code}: {e}")
        return False
    
    def _is_insolvent(self, fin_data: Optional[Dict]) -> bool:
        """检查资不抵债风险（净资产≤0）"""
        if not fin_data:
            return False
        
        # 尝试从多个字段获取净资产
        net_assets = fin_data.get('net_assets') or fin_data.get('total_equity') or fin_data.get('净资产') or fin_data.get('所有者权益合计')
        
        # 如果仍然没有，尝试从total_assets和total_liab计算
        if net_assets is None:
            total_assets = fin_data.get('total_assets') or fin_data.get('总资产')
            total_liab = fin_data.get('total_liab') or fin_data.get('total_debt') or fin_data.get('总负债')
            if total_assets is not None and total_liab is not None:
                try:
                    net_assets = float(total_assets) - float(total_liab)
                except (ValueError, TypeError):
                    net_assets = None
        
        # 如果没有净资产数据，不剔除（数据缺失，不认为是资不抵债）
        if net_assets is None:
            logger.debug(f"资不抵债检查：缺少净资产数据，跳过此检查")
            return False
        
        # 转换为数值类型并检查
        try:
            net_assets = float(net_assets)
            # 如果净资产≤0，认为资不抵债
            if net_assets <= 0:
                logger.debug(f"资不抵债检查：净资产={net_assets:,.0f} ≤ 0")
                return True
        except (ValueError, TypeError):
            logger.debug(f"资不抵债检查：无法转换净资产值 {net_assets} 为数字")
            # 如果无法转换，不剔除（数据问题）
            return False
        
        return False
    
    def _has_continuous_loss(self, ts_code: str, fin_data: Optional[Dict]) -> bool:
        """检查持续亏损风险（连续2个会计年度扣非归母净利润≤0，优先本地 fact_fundamental）"""
        try:
            # 获取年度数据（最近2年）
            annual_data = self.multi_period_service.get_multi_period_data(ts_code, periods=2, freq='Y')
            
            if annual_data is None or len(annual_data) < 2:
                # 数据不足，无法判断，不剔除
                logger.debug(f"{ts_code} 持续亏损检查：年度数据不足（获取到{len(annual_data) if annual_data is not None else 0}期），无法判断")
                return False
            
            # 检查扣非归母净利润
            if 'n_income_attr_p' not in annual_data.columns:
                logger.debug(f"{ts_code} 持续亏损检查：缺少n_income_attr_p字段，无法判断")
                return False
            
            # 检查最近2年是否都≤0
            recent_2_years = annual_data.head(2)['n_income_attr_p'].values
            if len(recent_2_years) < 2:
                logger.debug(f"{ts_code} 持续亏损检查：数据不足2年，无法判断")
                return False
            
            # 获取报告期信息
            report_dates = annual_data.head(2)['end_date'].tolist() if 'end_date' in annual_data.columns else []
            n_income_values = recent_2_years.tolist()
            
            # 详细日志：显示具体数值（仅DEBUG级别）
            logger.debug(f"{ts_code} 持续亏损检查：最近2年数据 - 报告期：{report_dates}，归属母公司净利润（n_income_attr_p）：{n_income_values}")
            
            is_continuous_loss = bool((recent_2_years <= 0).all())
            
            if is_continuous_loss:
                logger.info(f"{ts_code} ⚠️ 持续亏损风险：最近2年归属母公司净利润均≤0")
            else:
                logger.debug(f"{ts_code} ✅ 未发现持续亏损风险：最近2年归属母公司净利润至少1年>0")
            
            return is_continuous_loss
        except Exception as e:
            logger.warning(f"{ts_code} 检查持续亏损风险失败: {e}", exc_info=True)
            return False
    
    def _has_cashflow_breakdown_risk(self, ts_code: str, industry_name: str, revenue_growth: float) -> bool:
        """检查现金流断裂风险（区分行业周期，优先本地 fact_fundamental）"""
        try:
            # 获取季度数据（最近3期）
            quarterly_data = self.multi_period_service.get_multi_period_data(ts_code, periods=3, freq='Q')
            
            if quarterly_data is None or len(quarterly_data) < 2:
                # 数据不足，无法判断，不剔除
                return False
            
            if 'ocf' not in quarterly_data.columns:
                return False
            
            # 判断行业周期
            is_rising = self.industry_cycle_service.is_rising_industry(industry_name)
            
            # 计算连续负现金流期数
            negative_periods = (quarterly_data['ocf'] <= 0).sum()
            
            if is_rising:
                # 上升期行业：连续3期≤0 且 营收增长<10% 才剔除
                if negative_periods >= 3 and revenue_growth < 10:
                    return True
            else:
                # 其他行业：连续2期≤0 就剔除
                if negative_periods >= 2:
                    return True
            
            return False
        except Exception as e:
            logger.debug(f"检查现金流断裂风险失败 {ts_code}: {e}")
            return False
    
    def _has_interest_payment_risk(self, ts_code: str, fin_data: Optional[Dict]) -> bool:
        """检查利息偿付风险（利息保障倍数<2 且 连续2期下降）"""
        if not self.tushare_service.available:
            return False
        
        try:
            # 获取季度数据（最近2期）
            quarterly_data = self.multi_period_service.get_multi_period_data(ts_code, periods=2, freq='Q')
            
            if quarterly_data is None or len(quarterly_data) < 2:
                # 数据不足，无法判断，不剔除
                return False
            
            # 计算利息保障倍数 = EBIT / 利息费用
            # EBIT = 营业利润 + 财务费用（或从fina_indicator获取ebit）
            # 利息费用 = 财务费用（fin_exp）
            
            if 'ebit' in quarterly_data.columns and 'fin_exp' in quarterly_data.columns:
                # 计算利息保障倍数
                interest_coverage_ratios = []
                for idx in range(min(2, len(quarterly_data))):
                    ebit = quarterly_data.iloc[idx]['ebit']
                    fin_exp = abs(quarterly_data.iloc[idx]['fin_exp'])  # 财务费用通常是负数，取绝对值
                    
                    if pd.isna(ebit) or pd.isna(fin_exp) or fin_exp == 0:
                        continue
                    
                    ratio = ebit / fin_exp
                    interest_coverage_ratios.append(ratio)
                
                if len(interest_coverage_ratios) < 2:
                    return False
                
                # 检查是否<2且连续2期下降
                latest_ratio = interest_coverage_ratios[0]
                prev_ratio = interest_coverage_ratios[1]
                
                if latest_ratio < 2 and latest_ratio < prev_ratio:
                    return True
            
            # 如果没有ebit数据，尝试从operate_profit和fin_exp计算
            elif 'operate_profit' in quarterly_data.columns and 'fin_exp' in quarterly_data.columns:
                interest_coverage_ratios = []
                for idx in range(min(2, len(quarterly_data))):
                    operate_profit = quarterly_data.iloc[idx]['operate_profit']
                    fin_exp = abs(quarterly_data.iloc[idx]['fin_exp'])
                    
                    if pd.isna(operate_profit) or pd.isna(fin_exp) or fin_exp == 0:
                        continue
                    
                    ebit = operate_profit + fin_exp  # EBIT = 营业利润 + 财务费用
                    ratio = ebit / fin_exp
                    interest_coverage_ratios.append(ratio)
                
                if len(interest_coverage_ratios) < 2:
                    return False
                
                latest_ratio = interest_coverage_ratios[0]
                prev_ratio = interest_coverage_ratios[1]
                
                if latest_ratio < 2 and latest_ratio < prev_ratio:
                    return True
            
            return False
            
        except Exception as e:
            logger.debug(f"检查利息偿付风险失败 {ts_code}: {e}")
            return False
    
    def _filter_core_indicators(
        self,
        df: pd.DataFrame,
        financial_data: Optional[Dict[str, Dict]]
    ) -> pd.DataFrame:
        """
        第二层级：核心优质量化指标
        要求：连续3期达标，且≥行业中位数
        """
        try:
            if financial_data is None or not financial_data:
                return df
            
            candidates = []
            code_col = 'code' if 'code' in df.columns else '代码'
            
            for _, row in df.iterrows():
                code = row.get(code_col, '')
                if not code:
                    continue
                
                clean_code = str(code).replace('sh', '').replace('sz', '').replace('SH', '').replace('SZ', '').strip()
                ts_code = self._normalize_to_ts_code(clean_code)
                
                # 查找财务数据
                fin_data = None
                for fin_code, fin_info in financial_data.items():
                    fin_clean = str(fin_code).replace('sh', '').replace('sz', '').replace('SH', '').replace('SZ', '').strip()
                    if fin_clean == clean_code:
                        fin_data = fin_info
                        break
                
                if not fin_data:
                    continue
                
                # 获取行业名称
                industry_name = row.get('industry', '') or row.get('sector', '') or fin_data.get('industry', '')
                
                # 如果行业信息为空或者是"未知"，尝试从Tushare获取
                if not industry_name or industry_name == "未知" or industry_name.strip() == "":
                    try:
                        if self.tushare_service.available:
                            stock_basic = self.tushare_service.pro.stock_basic(
                                ts_code=ts_code,
                                fields='ts_code,industry'
                            )
                            if stock_basic is not None and not stock_basic.empty:
                                industry_name = stock_basic.iloc[0]['industry']
                                logger.debug(f"{clean_code} 从Tushare获取行业信息：{industry_name}")
                    except Exception as e:
                        logger.debug(f"{clean_code} 从Tushare获取行业信息失败：{e}")
                
                if not industry_name or industry_name == "未知" or industry_name.strip() == "":
                    logger.warning(f"{clean_code} ⚠️ 无法获取行业信息，将使用默认阈值")
                    industry_name = "未知"
                
                # 获取多期财务数据（季度数据，最近3期）
                quarterly_data = self.multi_period_service.get_multi_period_data(ts_code, periods=3, freq='Q')
                
                if quarterly_data is None or len(quarterly_data) < 3:
                    # 数据不足3期，剔除
                    logger.info(f"{clean_code} 核心指标筛选：数据不足3期（实际：{len(quarterly_data) if quarterly_data is not None else 0}期）")
                    continue
                
                # 1. 经营活动现金流（连续3期>0）
                ocf_values = quarterly_data['ocf'].head(3).tolist() if 'ocf' in quarterly_data.columns else []
                if not self.multi_period_service.check_continuous_compliance(
                    quarterly_data, 'ocf', 0, periods=3, comparison='>='
                ):
                    logger.info(f"{clean_code} 核心指标筛选失败：经营活动现金流（连续3期>0）- 最近3期值：{ocf_values}")
                    continue
                
                # 2. 净现比（动态阈值，连续3期达标，但允许最近3期中1期不达标，只要最近2期达标即可）
                revenue_growth = fin_data.get('revenue_yoy', fin_data.get('revenue_growth', 0))
                net_cash_ratio_threshold = self.industry_cycle_service.get_net_cash_ratio_threshold(
                    industry_name, revenue_growth
                )
                
                # 详细日志（仅DEBUG级别）
                logger.debug(f"{clean_code} 季度数据可用字段：{quarterly_data.columns.tolist()}")
                
                if 'n_income_attr_p' in quarterly_data.columns and 'ocf' in quarterly_data.columns:
                    n_income_values = quarterly_data['n_income_attr_p'].head(3).tolist()
                    ocf_values = quarterly_data['ocf'].head(3).tolist()
                    # 计算净现比用于验证
                    calculated_ratios = [ocf / n_income if n_income != 0 else 0 for ocf, n_income in zip(ocf_values, n_income_values)]
                    logger.debug(f"{clean_code} 净现比计算数据：ocf={ocf_values}, n_income_attr_p={n_income_values}, 行业={industry_name}, 阈值={net_cash_ratio_threshold:.4f}")
                    logger.debug(f"{clean_code} 净现比计算验证：手动计算={calculated_ratios}")
                    
                # 检查是否有其他可用的净利润字段（仅DEBUG级别）
                if 'net_profit' not in quarterly_data.columns:
                    logger.debug(f"{clean_code} 季度数据中缺少net_profit字段")
                
                # 计算净现比（合理区间 0.01~2.0，超出视为数据异常）
                if 'n_income_attr_p' in quarterly_data.columns:
                    valid_n_income = quarterly_data['n_income_attr_p'].replace(0, np.nan)
                    if valid_n_income.notna().sum() > 0:
                        # 分母过小（<1万）易产生异常值，暂置 nan
                        valid_n_income = valid_n_income.where(np.abs(valid_n_income) >= 10000, np.nan)
                        quarterly_data['net_cash_ratio'] = quarterly_data['ocf'] / valid_n_income
                    elif 'net_profit' in quarterly_data.columns:
                        logger.warning(f"{clean_code} n_income_attr_p无效，使用net_profit计算净现比")
                        valid_net_profit = quarterly_data['net_profit'].replace(0, np.nan)
                        valid_net_profit = valid_net_profit.where(np.abs(valid_net_profit) >= 10000, np.nan)
                        quarterly_data['net_cash_ratio'] = quarterly_data['ocf'] / valid_net_profit
                    else:
                        quarterly_data['net_cash_ratio'] = np.nan
                else:
                    quarterly_data['net_cash_ratio'] = np.nan
                # 净现比超出 0.01~2.0 视为异常，置 nan 避免误判（单位混用等）
                if 'net_cash_ratio' in quarterly_data.columns:
                    ncr = quarterly_data['net_cash_ratio']
                    quarterly_data['net_cash_ratio'] = np.where(
                        (ncr < 0.01) | (ncr > 2.0) | np.isinf(ncr),
                        np.nan,
                        ncr
                    )
                
                net_cash_ratios = quarterly_data['net_cash_ratio'].head(3).tolist() if 'net_cash_ratio' in quarterly_data.columns else []
                
                # 检查：最近3期中至少2期达标，且最近2期必须达标
                recent_3_periods = quarterly_data.head(3)
                if 'net_cash_ratio' not in recent_3_periods.columns:
                    logger.info(f"{clean_code} 核心指标筛选失败：净现比（无法计算）- 行业：{industry_name}")
                    continue
                
                net_cash_values = recent_3_periods['net_cash_ratio'].values
                # 检查是否有NaN或无效值
                if np.any(pd.isna(net_cash_values)) or np.any(np.isinf(net_cash_values)):
                    logger.info(f"{clean_code} 核心指标筛选失败：净现比（数据无效）- 最近3期值：{net_cash_ratios}，行业：{industry_name}")
                    continue
                
                # 最近2期必须达标（允许小的精度误差，0.01的容差）
                tolerance = 0.01  # 允许0.01的容差
                recent_2_passed = ((net_cash_values[:2] + tolerance) >= net_cash_ratio_threshold).all()
                # 最近3期中至少2期达标
                recent_3_passed_count = ((net_cash_values + tolerance) >= net_cash_ratio_threshold).sum()
                
                if not recent_2_passed or recent_3_passed_count < 2:
                    logger.info(f"{clean_code} 核心指标筛选失败：净现比（最近2期必须≥{net_cash_ratio_threshold:.2f}，且最近3期中至少2期达标，行业：{industry_name}）- 最近3期值：{net_cash_ratios}，达标数：{recent_3_passed_count}/3，阈值：{net_cash_ratio_threshold:.4f}")
                    continue
                

                # 3. 收现比（动态阈值，连续3期达标，但允许最近3期中1期不达标，只要最近2期达标即可）
                cash_receipt_ratio_threshold = self.industry_cycle_service.get_cash_receipt_ratio_threshold(
                    industry_name
                )
                quarterly_data['cash_receipt_ratio'] = quarterly_data['ocf'] / quarterly_data['revenue'].replace(0, np.nan)
                cash_receipt_ratios = quarterly_data['cash_receipt_ratio'].head(3).tolist() if 'cash_receipt_ratio' in quarterly_data.columns else []
                
                # 检查：最近3期中至少2期达标，且最近2期必须达标（允许小的精度误差）
                recent_3_periods = quarterly_data.head(3)
                if 'cash_receipt_ratio' not in recent_3_periods.columns:
                    logger.info(f"{clean_code} 核心指标筛选失败：收现比（无法计算）- 行业：{industry_name}")
                    continue
                
                cash_receipt_values = recent_3_periods['cash_receipt_ratio'].values
                # 检查是否有NaN或无效值
                if np.any(pd.isna(cash_receipt_values)) or np.any(np.isinf(cash_receipt_values)):
                    logger.info(f"{clean_code} 核心指标筛选失败：收现比（数据无效）- 最近3期值：{cash_receipt_ratios}，行业：{industry_name}")
                    continue
                
                # 调试日志（仅DEBUG级别）
                logger.debug(f"{clean_code} 收现比检查：收现比={cash_receipt_ratios}, 阈值={cash_receipt_ratio_threshold:.4f}")
                
                # 最近2期必须达标（允许小的精度误差，0.01的容差）
                tolerance = 0.01  # 允许0.01的容差
                recent_2_passed = ((cash_receipt_values[:2] + tolerance) >= cash_receipt_ratio_threshold).all()
                # 最近3期中至少2期达标
                recent_3_passed_count = ((cash_receipt_values + tolerance) >= cash_receipt_ratio_threshold).sum()
                
                if not recent_2_passed or recent_3_passed_count < 2:
                    logger.info(f"{clean_code} 核心指标筛选失败：收现比（最近2期必须≥{cash_receipt_ratio_threshold:.2f}，且最近3期中至少2期达标，行业：{industry_name}）- 最近3期值：{cash_receipt_ratios}，达标数：{recent_3_passed_count}/3")
                    continue
                
                # 4. 扣非利润占比（连续3期≥0.8且不下降）
                # 注意：如果net_profit字段不存在，使用n_income_attr_p作为替代（n_income_attr_p本身就是归属母公司净利润）
                if 'net_profit' in quarterly_data.columns:
                    quarterly_data['non_oper_ratio'] = quarterly_data['n_income_attr_p'] / quarterly_data['net_profit'].replace(0, np.nan)
                else:
                    # 如果net_profit不存在，假设n_income_attr_p就是扣非净利润，占比设为1.0
                    logger.debug(f"{clean_code} ⚠️ 缺少net_profit字段，使用n_income_attr_p作为替代，扣非利润占比设为1.0")
                    quarterly_data['non_oper_ratio'] = 1.0  # 假设全部都是扣非利润
                
                non_oper_ratios = quarterly_data['non_oper_ratio'].head(3).tolist() if 'non_oper_ratio' in quarterly_data.columns else []
                if not self.multi_period_service.check_continuous_compliance_and_trend(
                    quarterly_data, 'non_oper_ratio', 0.8, periods=3, allow_decline=False
                ):
                    logger.info(f"{clean_code} 核心指标筛选失败：扣非利润占比（连续3期≥0.8且不下降）- 最近3期值：{non_oper_ratios}")
                    continue
                
                # 5. 扣非ROE（≥行业中位数，连续3期）
                industry_roe_median = self.industry_percentile_service.get_percentile(
                    industry_name, 'roe', percentile=0.5
                )
                roe_values = quarterly_data['roe'].head(3).tolist() if 'roe' in quarterly_data.columns else []
                if not self.multi_period_service.check_continuous_compliance(
                    quarterly_data, 'roe', industry_roe_median, periods=3
                ):
                    logger.info(f"{clean_code} 核心指标筛选失败：扣非ROE（连续3期≥行业中位数{industry_roe_median:.2f}%，行业：{industry_name}）- 最近3期值：{roe_values}")
                    continue
                
                # 6. 销售毛利率（≥行业中位数，连续3期不下降）
                industry_gross_margin_median = self.industry_percentile_service.get_percentile(
                    industry_name, 'grossprofit_margin', percentile=0.5
                )
                gross_margin_values = quarterly_data['grossprofit_margin'].head(3).tolist() if 'grossprofit_margin' in quarterly_data.columns else []
                if not self.multi_period_service.check_continuous_compliance_and_trend(
                    quarterly_data, 'grossprofit_margin', industry_gross_margin_median, periods=3, allow_decline=False
                ):
                    logger.info(f"{clean_code} 核心指标筛选失败：销售毛利率（连续3期≥行业中位数{industry_gross_margin_median:.2f}%且不下降，行业：{industry_name}）- 最近3期值：{gross_margin_values}")
                    continue
                
                # 7. 营收同比增长率（≥0且≥行业中位数）
                revenue_yoy = fin_data.get('revenue_yoy', fin_data.get('revenue_growth', 0))
                if revenue_yoy < 0:
                    logger.info(f"{clean_code} 核心指标筛选失败：营收同比增长率（要求≥0）- 实际值：{revenue_yoy:.2f}%")
                    continue
                
                industry_revenue_yoy_median = self.industry_percentile_service.get_percentile(
                    industry_name, 'revenue_yoy', percentile=0.5
                )
                if revenue_yoy < industry_revenue_yoy_median:
                    logger.info(f"{clean_code} 核心指标筛选失败：营收同比增长率（要求≥行业中位数{industry_revenue_yoy_median:.2f}%，行业：{industry_name}）- 实际值：{revenue_yoy:.2f}%")
                    continue
                
                # 所有核心指标通过
                logger.info(f"{clean_code} ✅ 通过所有核心指标检查（行业：{industry_name}）")
                row_dict = row.to_dict()
                row_dict.update({
                    'industry': industry_name,
                    'revenue_yoy': revenue_yoy,
                    'net_cash_ratio': quarterly_data.iloc[0]['net_cash_ratio'] if 'net_cash_ratio' in quarterly_data.columns else 0,
                    'cash_receipt_ratio': quarterly_data.iloc[0]['cash_receipt_ratio'] if 'cash_receipt_ratio' in quarterly_data.columns else 0,
                })
                candidates.append(row_dict)
            
            logger.info(f"✅ 核心指标筛选：从 {len(df)} 只股票中筛选出 {len(candidates)} 只")
            if len(candidates) == 0 and len(df) > 0:
                logger.info(f"⚠️ 提示：所有股票都在核心指标筛选中被过滤，请查看上面的详细日志了解具体原因")
            return pd.DataFrame(candidates) if candidates else pd.DataFrame()
            
        except Exception as e:
            logger.error(f"核心指标筛选失败: {e}", exc_info=True)
            return df
    
    def _cross_validation(
        self,
        df: pd.DataFrame,
        financial_data: Optional[Dict[str, Dict]]
    ) -> pd.DataFrame:
        """
        第三层级：量化交叉验证（避免单一指标失真）
        """
        try:
            if financial_data is None or not financial_data:
                return df
            
            candidates = []
            code_col = 'code' if 'code' in df.columns else '代码'
            
            for _, row in df.iterrows():
                code = row.get(code_col, '')
                if not code:
                    continue
                
                clean_code = str(code).replace('sh', '').replace('sz', '').replace('SH', '').replace('SZ', '').strip()
                ts_code = self._normalize_to_ts_code(clean_code)
                
                # 查找财务数据
                fin_data = None
                for fin_code, fin_info in financial_data.items():
                    fin_clean = str(fin_code).replace('sh', '').replace('sz', '').replace('SH', '').replace('SZ', '').strip()
                    if fin_clean == clean_code:
                        fin_data = fin_info
                        break
                
                if not fin_data:
                    continue
                
                # 获取行业名称
                industry_name = row.get('industry', '') or row.get('sector', '')
                
                # 获取多期数据（用于交叉验证）
                quarterly_data = self.multi_period_service.get_multi_period_data(ts_code, periods=2, freq='Q')
                
                if quarterly_data is None or len(quarterly_data) < 2:
                    # 数据不足，保留（不剔除）
                    candidates.append(row.to_dict())
                    continue
                
                # 规则1: 营收同比≥20% 但 收现比<动态阈值 → 剔除
                revenue_yoy = fin_data.get('revenue_yoy', fin_data.get('revenue_growth', 0))
                cash_receipt_ratio = row.get('cash_receipt_ratio', 0)
                if cash_receipt_ratio == 0 and 'revenue' in quarterly_data.columns and 'ocf' in quarterly_data.columns:
                    cash_receipt_ratio = quarterly_data.iloc[0]['ocf'] / quarterly_data.iloc[0]['revenue'] if quarterly_data.iloc[0]['revenue'] != 0 else 0
                
                cash_receipt_threshold = self.industry_cycle_service.get_cash_receipt_ratio_threshold(industry_name)
                if revenue_yoy >= 20 and cash_receipt_ratio < cash_receipt_threshold:
                    logger.debug(f"{clean_code} 交叉验证失败：营收虚增（营收同比{revenue_yoy:.1f}%，收现比{cash_receipt_ratio:.2f}<{cash_receipt_threshold:.2f}）")
                    continue
                
                # 规则2: 扣非ROE≥15% 但 净现比<动态阈值 → 剔除
                roe = fin_data.get('roe', fin_data.get('roe_ttm', 0))
                net_cash_ratio = row.get('net_cash_ratio', 0)
                if net_cash_ratio == 0 and 'ocf' in quarterly_data.columns and 'n_income_attr_p' in quarterly_data.columns:
                    net_cash_ratio = quarterly_data.iloc[0]['ocf'] / quarterly_data.iloc[0]['n_income_attr_p'] if quarterly_data.iloc[0]['n_income_attr_p'] != 0 else 0
                
                net_cash_threshold = self.industry_cycle_service.get_net_cash_ratio_threshold(
                    industry_name, revenue_yoy
                )
                if roe >= 15 and net_cash_ratio < net_cash_threshold:
                    logger.debug(f"{clean_code} 交叉验证失败：利润造假嫌疑（ROE{roe:.1f}%，净现比{net_cash_ratio:.2f}<{net_cash_threshold:.2f}）")
                    continue
                
                # 规则3: 主动加杠杆 但 营收同比<5% → 剔除
                if self._is_active_leverage_increase(quarterly_data) and revenue_yoy < 5:
                    logger.debug(f"{clean_code} 交叉验证失败：盲目举债（主动加杠杆但营收增长{revenue_yoy:.1f}%<5%）")
                    continue
                
                # 规则4: 毛利率同比下降≥10% 但 营收同比<10% → 剔除
                if self._is_gross_margin_decline(quarterly_data, threshold=10) and revenue_yoy < 10:
                    logger.debug(f"{clean_code} 交叉验证失败：盈利壁垒丧失（毛利率下降≥10%但营收增长{revenue_yoy:.1f}%<10%）")
                    continue
                
                # 规则5: 被动库存积压 → 剔除
                if self._is_passive_inventory_accumulation(quarterly_data):
                    logger.debug(f"{clean_code} 交叉验证失败：被动库存积压")
                    continue
                
                # 所有交叉验证规则通过
                candidates.append(row.to_dict())
            
            logger.info(f"✅ 交叉验证：从 {len(df)} 只股票中筛选出 {len(candidates)} 只")
            return pd.DataFrame(candidates) if candidates else pd.DataFrame()
            
        except Exception as e:
            logger.error(f"交叉验证失败: {e}", exc_info=True)
            return df
    
    def _is_active_leverage_increase(self, quarterly_data: pd.DataFrame) -> bool:
        """
        判断是否主动加杠杆
        条件：资产负债率同比提升≥10% 且 有息负债增速>营收增速
        注意：如果资产负债率提升是由于权益融资导致，不触发此规则
        """
        if quarterly_data is None or len(quarterly_data) < 2:
            return False
        
        try:
            # 计算资产负债率变化
            if 'debt_to_assets' not in quarterly_data.columns:
                return False
            
            latest_debt_ratio = quarterly_data.iloc[0]['debt_to_assets']
            prev_debt_ratio = quarterly_data.iloc[1]['debt_to_assets']
            
            if pd.isna(latest_debt_ratio) or pd.isna(prev_debt_ratio) or prev_debt_ratio == 0:
                return False
            
            debt_ratio_change = latest_debt_ratio - prev_debt_ratio
            
            if debt_ratio_change < 0.1:  # 提升<10%
                return False
            
            # 计算营收增速
            if 'revenue' not in quarterly_data.columns:
                return False
            
            latest_revenue = quarterly_data.iloc[0]['revenue']
            prev_revenue = quarterly_data.iloc[1]['revenue']
            
            if prev_revenue == 0 or pd.isna(latest_revenue) or pd.isna(prev_revenue):
                return False
            
            revenue_growth = (latest_revenue - prev_revenue) / prev_revenue
            
            # 简化处理：如果无法获取有息负债数据，使用总资产增速作为近似
            # 如果资产增速远大于负债增速，可能是权益融资
            if 'total_assets' in quarterly_data.columns:
                latest_assets = quarterly_data.iloc[0]['total_assets']
                prev_assets = quarterly_data.iloc[1]['total_assets']
                if prev_assets > 0 and not pd.isna(latest_assets) and not pd.isna(prev_assets):
                    asset_growth = (latest_assets - prev_assets) / prev_assets
                    # 如果资产增速远大于负债增速，可能是权益融资
                    if asset_growth > debt_ratio_change * 1.5:
                        return False  # 不触发规则
            
            # 简化处理：如果资产负债率提升≥10%且营收增长<0，认为是主动加杠杆
            return revenue_growth < 0
            
        except Exception as e:
            logger.debug(f"判断主动加杠杆失败: {e}")
            return False
    
    def _is_gross_margin_decline(self, quarterly_data: pd.DataFrame, threshold: float = 10.0) -> bool:
        """判断毛利率是否同比下降≥threshold%"""
        if quarterly_data is None or len(quarterly_data) < 2:
            return False
        
        try:
            if 'grossprofit_margin' not in quarterly_data.columns:
                return False
            
            latest_gross_margin = quarterly_data.iloc[0]['grossprofit_margin']
            prev_gross_margin = quarterly_data.iloc[1]['grossprofit_margin']
            
            if pd.isna(latest_gross_margin) or pd.isna(prev_gross_margin) or prev_gross_margin == 0:
                return False
            
            decline_pct = (prev_gross_margin - latest_gross_margin) / prev_gross_margin * 100
            
            return decline_pct >= threshold
        except Exception as e:
            logger.debug(f"判断毛利率下降失败: {e}")
            return False
    
    def _is_passive_inventory_accumulation(self, quarterly_data: pd.DataFrame) -> bool:
        """
        判断是否被动库存积压
        条件：存货周转率同比下降≥20% 且 存货同比增速≥30% 且 营收同比增长率<5%
        注意：如果存货增长伴随营收增长>10%，可能是主动备货，不触发此规则
        """
        if quarterly_data is None or len(quarterly_data) < 2:
            return False
        
        try:
            # 计算营收同比增长率
            if 'revenue' not in quarterly_data.columns:
                return False
            
            latest_revenue = quarterly_data.iloc[0]['revenue']
            prev_revenue = quarterly_data.iloc[1]['revenue']
            
            if prev_revenue == 0 or pd.isna(latest_revenue) or pd.isna(prev_revenue):
                return False
            
            revenue_yoy = (latest_revenue - prev_revenue) / prev_revenue * 100
            
            # 如果营收增长>10%，可能是主动备货，不触发规则
            if revenue_yoy > 10:
                return False
            
            # 计算存货周转率变化
            # 存货周转率 = 营业成本 / 平均存货余额
            # 简化处理：如果没有存货周转率数据，使用存货和营收数据计算
            if 'inventory' not in quarterly_data.columns:
                return False
            
            latest_inventory = quarterly_data.iloc[0]['inventory']
            prev_inventory = quarterly_data.iloc[1]['inventory']
            
            if pd.isna(latest_inventory) or pd.isna(prev_inventory) or prev_inventory == 0:
                return False
            
            # 计算存货增速
            inventory_growth = (latest_inventory - prev_inventory) / prev_inventory * 100
            
            # 计算存货周转率（简化：使用营收/存货作为近似）
            latest_turnover = latest_revenue / latest_inventory if latest_inventory > 0 else 0
            prev_turnover = prev_revenue / prev_inventory if prev_inventory > 0 else 0
            
            if prev_turnover == 0:
                return False
            
            turnover_decline = (prev_turnover - latest_turnover) / prev_turnover * 100
            
            # 判断是否被动库存积压
            return (turnover_decline >= 20 and 
                    inventory_growth >= 30 and 
                    revenue_yoy < 5)
            
        except Exception as e:
            logger.debug(f"判断被动库存积压失败: {e}")
            return False
    
    def _has_goodwill_risk(self, ts_code: str, fin_data: Optional[Dict]) -> bool:
        """检查商誉减值风险（商誉/净资产>30%）"""
        try:
            # 1. 优先从本地 fact_fundamental 读取
            local_data = self.multi_period_service.get_goodwill_equity_from_local(ts_code)
            if local_data is not None:
                goodwill, total_equity = local_data
                if total_equity > 0:
                    return (goodwill / total_equity) > 0.3
                return False

            # 2. 本地无数据时回退到 Tushare
            if not self.tushare_service.available:
                return False
            balance_sheet = self.tushare_service.pro.balancesheet(
                ts_code=ts_code, period='',
                fields='ts_code,end_date,goodwill,total_equity'
            )
            if balance_sheet is None or balance_sheet.empty:
                return False
            latest = balance_sheet.iloc[0]
            goodwill = float(latest.get('goodwill', 0) or 0)
            total_equity = float(latest.get('total_equity', 0) or 0)
            if total_equity <= 0:
                return False
            return (goodwill / total_equity) > 0.3
        except Exception as e:
            logger.debug(f"检查商誉减值风险失败 {ts_code}: {e}")
            return False
    
    def _has_related_party_transaction_risk(self, ts_code: str, fin_data: Optional[Dict]) -> bool:
        """检查关联交易风险（关联交易/营收>20%）"""
        if not self.tushare_service.available:
            return False
        
        try:
            # Tushare可能没有直接的关联交易接口
            # 简化处理：暂时跳过此检查
            # 如果需要实现，可能需要从年报或其他数据源获取
            return False
            
        except Exception as e:
            logger.debug(f"检查关联交易风险失败 {ts_code}: {e}")
            return False
    
    def _has_major_shareholder_pledge_risk(self, ts_code: str) -> bool:
        """检查大股东质押风险（质押率>60%）"""
        if not self.tushare_service.available:
            return False
        
        try:
            # 获取股东质押数据
            # Tushare可能有stk_holdernumber或pledge接口
            # 简化处理：暂时跳过此检查
            # 如果需要实现，需要确认Tushare的具体接口
            return False
            
        except Exception as e:
            logger.debug(f"检查大股东质押风险失败 {ts_code}: {e}")
            return False
    
    def _has_audit_opinion_risk(self, ts_code: str) -> bool:
        """检查审计意见风险（非标准无保留意见）"""
        standard_keywords = ['标准无保留', '无保留意见', '标准审计意见']
        try:
            # 1. 优先从本地 fact_fundamental 读取
            audit_result = self.multi_period_service.get_audit_result_from_local(ts_code)
            if audit_result:
                return not any(kw in audit_result for kw in standard_keywords)

            # 2. 本地无数据时回退到 Tushare
            if not self.tushare_service.available:
                return False
            audit_data = self.tushare_service.pro.fina_audit(
                ts_code=ts_code, period='',
                fields='ts_code,end_date,audit_result'
            )
            if audit_data is None or audit_data.empty:
                return False
            audit_result = str(audit_data.iloc[0].get('audit_result', '')).strip()
            if audit_result and not any(kw in audit_result for kw in standard_keywords):
                return True
            return False
        except Exception as e:
            logger.debug(f"检查审计意见风险失败 {ts_code}: {e}")
            return False
    
    def _filter_profit_quality(
        self,
        df: pd.DataFrame,
        financial_data: Optional[Dict[str, Dict]]
    ) -> pd.DataFrame:
        """
        盈利质量：检查3-5年净利润趋势和毛利率稳定性
        
        条件：
        - 最近3~5年净利润趋势：稳步增长或小幅波动（波动率<30%）
        - 毛利率保持稳定或略有提升（单期下降≤5%）
        """
        try:
            if financial_data is None or not financial_data:
                return df
            
            candidates = []
            code_col = 'code' if 'code' in df.columns else '代码'
            
            for _, row in df.iterrows():
                code = row.get(code_col, '')
                if not code:
                    continue
                
                clean_code = str(code).replace('sh', '').replace('sz', '').replace('SH', '').replace('SZ', '').strip()
                ts_code = self._normalize_to_ts_code(clean_code)
                
                # 获取年度数据（至少3年）
                annual_data = self.multi_period_service.get_multi_period_data(ts_code, periods=5, freq='Y')
                
                if annual_data is None or len(annual_data) < 3:
                    # 数据不足，保留（不剔除）
                    candidates.append(row.to_dict())
                    continue
                
                # 1. 检查净利润趋势（波动率<30%）
                # 如果net_profit不存在，使用n_income_attr_p作为替代
                if 'net_profit' in annual_data.columns:
                    net_profit_values = annual_data.head(3)['net_profit'].values
                elif 'n_income_attr_p' in annual_data.columns:
                    logger.debug(f"{clean_code} ⚠️ 缺少net_profit字段，使用n_income_attr_p作为替代进行盈利质量检查")
                    net_profit_values = annual_data.head(3)['n_income_attr_p'].values
                else:
                    # 如果两个字段都不存在，跳过盈利质量检查
                    logger.warning(f"{clean_code} ⚠️ 缺少net_profit和n_income_attr_p字段，跳过盈利质量检查")
                    candidates.append(row.to_dict())
                    continue
                net_profit_values = net_profit_values[~pd.isna(net_profit_values)]
                
                if len(net_profit_values) < 3:
                    candidates.append(row.to_dict())
                    continue
                
                # 计算波动率（标准差/均值）
                mean_profit = np.mean(net_profit_values)
                if mean_profit == 0:
                    # 平均净利润为0，剔除
                    continue
                
                volatility = np.std(net_profit_values) / abs(mean_profit)
                if volatility > 0.3:  # 波动率>30%，剔除
                    logger.debug(f"{clean_code} 盈利质量筛选失败：净利润波动率{volatility:.2f}>30%")
                    continue
                
                # 2. 检查毛利率稳定性（单期下降≤5%）
                if 'grossprofit_margin' not in annual_data.columns:
                    candidates.append(row.to_dict())
                    continue
                
                gross_margin_values = annual_data.head(3)['grossprofit_margin'].values
                gross_margin_values = gross_margin_values[~pd.isna(gross_margin_values)]
                
                if len(gross_margin_values) < 2:
                    candidates.append(row.to_dict())
                    continue
                
                # 检查单期最大下降幅度
                max_decline = 0
                for i in range(1, len(gross_margin_values)):
                    if gross_margin_values[i-1] > 0:
                        decline = (gross_margin_values[i-1] - gross_margin_values[i]) / gross_margin_values[i-1] * 100
                        max_decline = max(max_decline, decline)
                
                if max_decline > 5:  # 单期下降>5%，剔除
                    logger.debug(f"{clean_code} 盈利质量筛选失败：毛利率单期最大下降{max_decline:.1f}%>5%")
                    continue
                
                # 所有盈利质量检查通过
                candidates.append(row.to_dict())
            
            logger.info(f"✅ 盈利质量筛选：从 {len(df)} 只股票中筛选出 {len(candidates)} 只")
            return pd.DataFrame(candidates) if candidates else df
            
        except Exception as e:
            logger.error(f"盈利质量筛选失败: {e}", exc_info=True)
            return df
    
    def _filter_industry_position(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        行业与地位
        
        条件：
        - 行业本身不是长期衰退行业（使用行业周期判断服务）
        - 公司市值或营收规模处于行业中上（市值排名前30%）
        """
        try:
            if df.empty:
                return df
            
            # 1. 排除长期衰退行业
            candidates = []
            for _, row in df.iterrows():
                industry_name = row.get('industry', '') or row.get('sector', '')
                if industry_name and self.industry_cycle_service.is_declining_industry(industry_name):
                    logger.debug(f"{row.get('code', '')} 行业地位筛选失败：下滑期行业 {industry_name}")
                    continue  # 排除下滑期行业
                candidates.append(row)
            
            if not candidates:
                return pd.DataFrame()
            
            df_filtered = pd.DataFrame(candidates)
            
            # 2. 按行业分组，计算市值/营收排名（前30%）
            # 确定行业字段
            industry_field = None
            for field_name in ['industry', 'sector', '行业', '所属行业']:
                if field_name in df_filtered.columns:
                    industry_field = field_name
                    break
            
            if not industry_field:
                # 没有行业字段，返回所有股票
                logger.warning("没有行业字段，无法进行行业地位筛选")
                return df_filtered
            
            industry_groups = df_filtered.groupby(industry_field)
            
            final_candidates = []
            for industry_name, group_df in industry_groups:
                if len(group_df) == 0:
                    continue
                
                # 计算市值或营收（优先使用市值）
                rank_col = None
                if 'market_cap' in group_df.columns:
                    rank_col = 'market_cap'
                elif 'amount' in group_df.columns:
                    # 使用成交额作为市值近似（如果没有市值数据）
                    rank_col = 'amount'
                elif 'revenue' in group_df.columns:
                    rank_col = 'revenue'
                else:
                    # 如果没有市值和营收数据，保留所有股票
                    final_candidates.extend(group_df.to_dict('records'))
                    continue
                
                # 计算排名（前30%）
                group_df = group_df.copy()
                group_df['rank_pct'] = group_df[rank_col].rank(pct=True, ascending=False)
                top_30_pct = group_df[group_df['rank_pct'] <= 0.3]
                
                final_candidates.extend(top_30_pct.to_dict('records'))
            
            logger.info(f"✅ 行业地位筛选：从 {len(df)} 只股票中筛选出 {len(final_candidates)} 只（市值/营收排名前30%）")
            return pd.DataFrame(final_candidates) if final_candidates else pd.DataFrame()
            
        except Exception as e:
            logger.error(f"行业地位筛选失败: {e}", exc_info=True)
            return df
    
    def _filter_valuation(
        self,
        df: pd.DataFrame,
        financial_data: Optional[Dict[str, Dict]],
        limit: int = 20
    ) -> tuple[List[Dict], List[Dict]]:
        """
        估值合理性：使用5年历史分位数
        
        条件：
        - 当前 PE 在 5年历史分位数 10%~70% 区间内 → darwin_core
        - 太高估（>80%分位数）→ darwin_watch（观察池）
        """
        try:
            darwin_core = []
            darwin_watch = []
            
            if financial_data is None or not financial_data:
                # 没有财务数据，按市值排序（返回全部）
                df_sorted = df.sort_values(
                    by=['amount' if 'amount' in df.columns else '成交额'],
                    ascending=False
                )
                return df_sorted.to_dict('records'), []
            
            code_col = 'code' if 'code' in df.columns else '代码'
            
            for _, row in df.iterrows():
                code = row.get(code_col, '')
                if not code:
                    continue
                
                clean_code = str(code).replace('sh', '').replace('sz', '').replace('SH', '').replace('SZ', '').strip()
                ts_code = self._normalize_to_ts_code(clean_code)
                
                fin_data = None
                for fin_code, fin_info in financial_data.items():
                    fin_clean = str(fin_code).replace('sh', '').replace('sz', '').replace('SH', '').replace('SZ', '').strip()
                    if fin_clean == clean_code:
                        fin_data = fin_info
                        break
                
                if not fin_data:
                    continue
                
                # 获取当前PE
                current_pe = fin_data.get('pe', fin_data.get('PE', 0))
                
                row_dict = row.to_dict()
                row_dict['pe'] = current_pe
                row_dict['pb'] = fin_data.get('pb', fin_data.get('PB', 0))
                
                if current_pe <= 0:
                    # 没有PE数据，默认加入核心池
                    darwin_core.append(row_dict)
                    continue
                
                # 获取5年历史PE数据
                historical_pe = self._get_historical_pe(ts_code, years=5)
                
                if historical_pe is None or len(historical_pe) == 0:
                    # 没有历史数据，使用当前PE简单判断
                    if current_pe < 50:
                        darwin_core.append(row_dict)
                    else:
                        darwin_watch.append(row_dict)
                    continue
                
                # 计算历史分位数
                pe_10th = np.percentile(historical_pe, 10)
                pe_70th = np.percentile(historical_pe, 70)
                pe_80th = np.percentile(historical_pe, 80)
                
                # 判断估值合理性
                if pe_10th <= current_pe <= pe_70th:
                    darwin_core.append(row_dict)
                elif current_pe > pe_80th:
                    darwin_watch.append(row_dict)
                else:
                    # 在70%-80%之间，也加入核心池（估值略高但可接受）
                    darwin_core.append(row_dict)
            
            # 按ROE和市值排序
            darwin_core.sort(key=lambda x: (
                x.get('roe', 0),
                x.get('amount', x.get('成交额', 0))
            ), reverse=True)
            
            darwin_watch.sort(key=lambda x: (
                x.get('roe', 0),
                x.get('amount', x.get('成交额', 0))
            ), reverse=True)
            
            logger.info(f"✅ 估值筛选：核心池 {len(darwin_core)} 只，观察池 {len(darwin_watch)} 只")
            return darwin_core, darwin_watch
            
        except Exception as e:
            logger.error(f"估值筛选失败: {e}", exc_info=True)
            return df.head(limit).to_dict('records'), []
    
    def _get_historical_pe(self, ts_code: str, years: int = 5) -> Optional[List[float]]:
        """获取历史PE数据"""
        if not self.tushare_service.available:
            return None
        
        try:
            end_date = datetime.now().strftime('%Y%m%d')
            start_date = (datetime.now() - timedelta(days=years*365)).strftime('%Y%m%d')
            
            # 获取历史每日估值数据
            daily_basic = self.tushare_service.pro.daily_basic(
                ts_code=ts_code,
                start_date=start_date,
                end_date=end_date,
                fields='ts_code,trade_date,pe'
            )
            
            if daily_basic is None or daily_basic.empty:
                return None
            
            # 提取PE值（排除无效值）
            pe_values = daily_basic['pe'].dropna()
            pe_values = pe_values[pe_values > 0]  # 排除负数和0
            pe_values = pe_values[pe_values < 1000]  # 排除异常值
            
            return pe_values.tolist()
            
        except Exception as e:
            logger.debug(f"获取历史PE数据失败 {ts_code}: {e}")
            return None
    
    def _clean_financial_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        数据清洗：剔除异常值
        """
        if df.empty:
            return df
        
        try:
            df_cleaned = df.copy()
            
            # 1. 剔除关键指标为NaN的行（如果有这些字段）
            critical_columns = []
            for col in ['revenue', 'net_profit', 'amount', '成交额']:
                if col in df_cleaned.columns:
                    critical_columns.append(col)
            
            if critical_columns:
                df_cleaned = df_cleaned.dropna(subset=critical_columns)
            
            # 2. 剔除指标为无限大（inf）的行
            for col in df_cleaned.select_dtypes(include=[np.number]).columns:
                df_cleaned = df_cleaned[~np.isinf(df_cleaned[col])]
            
            # 3. 剔除成交额为0的行（可能已停牌）
            if 'amount' in df_cleaned.columns:
                df_cleaned = df_cleaned[df_cleaned['amount'] > 0]
            elif '成交额' in df_cleaned.columns:
                df_cleaned = df_cleaned[df_cleaned['成交额'] > 0]
            
            return df_cleaned.reset_index(drop=True)
            
        except Exception as e:
            logger.error(f"数据清洗失败: {e}", exc_info=True)
            return df
    
    def _filter_new_stocks(
        self,
        df: pd.DataFrame,
        min_listing_years: float = 1.0
    ) -> pd.DataFrame:
        """
        剔除次新股：上市时间不足N年的公司
        """
        if not self.tushare_service.available:
            logger.warning("Tushare不可用，无法过滤次新股")
            return df
        
        try:
            # 获取所有股票基本信息（批量获取，避免循环请求）
            stock_basic = None
            try:
                stock_basic = self.tushare_service.pro.stock_basic(
                    exchange='',
                    list_status='L',
                    fields='ts_code,symbol,name,list_date'
                )
            except Exception as e:
                logger.warning(f"获取股票基本信息失败: {e}")
                return df
            
            if stock_basic is None or stock_basic.empty:
                return df
            
            # 创建上市日期映射
            listing_date_map = {}
            for _, row in stock_basic.iterrows():
                ts_code = row['ts_code']
                list_date_str = str(row['list_date'])
                if len(list_date_str) == 8:  # YYYYMMDD格式
                    try:
                        list_date = datetime.strptime(list_date_str, '%Y%m%d')
                        listing_date_map[ts_code] = list_date
                    except:
                        continue
            
            # 过滤次新股
            candidates = []
            current_date = datetime.now()
            code_col = 'code' if 'code' in df.columns else '代码'
            
            for _, row in df.iterrows():
                code = row.get(code_col, '')
                if not code:
                    candidates.append(row.to_dict())
                    continue
                
                clean_code = str(code).replace('sh', '').replace('sz', '').replace('SH', '').replace('SZ', '').strip()
                ts_code = self._normalize_to_ts_code(clean_code)
                
                if ts_code not in listing_date_map:
                    # 找不到上市日期，保留（可能是数据问题）
                    candidates.append(row.to_dict())
                    continue
                
                list_date = listing_date_map[ts_code]
                listing_years = (current_date - list_date).days / 365.0
                
                if listing_years >= min_listing_years:
                    candidates.append(row.to_dict())
            
            return pd.DataFrame(candidates) if candidates else pd.DataFrame()
            
        except Exception as e:
            logger.error(f"过滤次新股失败: {e}", exc_info=True)
            return df

