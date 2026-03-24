"""
达尔文评分服务
用于长线投公司模型，计算达尔文评分
"""

import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class DarwinScorer:
    """达尔文评分服务类"""
    
    def calculate_darwin_score(self, stock_data: Dict, financial_data: Dict, commodity_data: Optional[Dict] = None) -> float:
        """
        计算达尔文评分（满分100）
        
        评分构成（6大维度）：
        - 成长性（25%）：营收增长、利润增长、增长稳定性
        - 盈利能力（25%）：ROE、净利率、毛利率
        - 财务健康度（15%）：债务、现金、资本结构
        - 成本优势/竞争优势（10%）：毛利率、行业地位
        - 估值（15%）：PE、PB、PEG
        - 资金行为与趋势（10%）：K线、量能、趋势
        
        Args:
            stock_data: 股票数据
            financial_data: 财务数据
            commodity_data: 商品价格数据（可选，暂不使用）
            
        Returns:
            float: 达尔文评分（0-100）
        """
        try:
            score = 0.0
            
            # 1. 成长性（25%）
            growth_score = self._calculate_growth_score(financial_data)
            score += growth_score * 0.25
            
            # 2. 盈利能力（25%）
            profitability_score = self._calculate_profitability_score(financial_data)
            score += profitability_score * 0.25
            
            # 3. 财务健康度（15%）
            health_score = self._calculate_financial_health_score(financial_data)
            score += health_score * 0.15
            
            # 4. 成本优势/竞争优势（10%）
            moat_score = self._calculate_moat_score(financial_data)
            score += moat_score * 0.10
            
            # 5. 估值（15%）
            valuation_score = self._calculate_valuation_score(stock_data, financial_data)
            score += valuation_score * 0.15
            
            # 6. 资金行为与趋势（10%）
            behavior_score = self._calculate_behavior_score(stock_data)
            score += behavior_score * 0.10
            
            return min(score, 100.0)
            
        except Exception as e:
            logger.error(f"计算达尔文评分失败: {e}", exc_info=True)
            return 0.0
    
    def calculate_financial_health(self, financial_data: Dict) -> float:
        """
        计算财务健康系数（0.6~1.0）
        
        构成：
        - ROE水平（40%）
        - 现金流健康（30%）
        - 负债率合理（20%）
        - 盈利质量（10%）
        
        Args:
            financial_data: 财务数据
            
        Returns:
            float: 财务健康系数（0.6~1.0）
        """
        try:
            roe = financial_data.get('roe_ttm', 0) or financial_data.get('roe', 0)
            operating_cashflow = financial_data.get('op_cf_ttm', 0) or financial_data.get('operating_cashflow', 0)
            debt_ratio = financial_data.get('debt_ratio', 0.5)
            net_margin = financial_data.get('net_margin_ttm', 0) or financial_data.get('net_margin', 0)
            
            # 1. ROE水平评分（40%）
            if roe <= 0:
                roe_health = 0.6
            elif roe < 10:
                roe_health = 0.65
            elif roe < 15:
                roe_health = 0.75
            elif roe < 20:
                roe_health = 0.85
            elif roe < 25:
                roe_health = 0.90
            else:
                roe_health = 0.95
            
            # 2. 现金流健康（30%）
            if operating_cashflow > 0:
                cashflow_health = 1.0
            else:
                cashflow_health = 0.6
            
            # 3. 负债率合理（20%）
            # 负债率在20%-70%之间为合理，过低或过高都扣分
            if 0.2 <= debt_ratio <= 0.7:
                debt_health = 1.0
            elif debt_ratio < 0.2:
                debt_health = 0.9  # 负债率过低可能意味着资金利用不充分
            elif debt_ratio <= 0.8:
                debt_health = 0.8
            else:
                debt_health = 0.6  # 负债率过高风险大
            
            # 4. 盈利质量（10%）：基于净利率
            if net_margin <= 0:
                profit_quality = 0.6
            elif net_margin < 5:
                profit_quality = 0.7
            elif net_margin < 10:
                profit_quality = 0.8
            elif net_margin < 15:
                profit_quality = 0.9
            else:
                profit_quality = 1.0
            
            # 综合财务健康系数
            financial_health = (roe_health * 0.4 + 
                              cashflow_health * 0.3 + 
                              debt_health * 0.2 + 
                              profit_quality * 0.1)
            
            return max(0.6, min(financial_health, 1.0))
            
        except Exception as e:
            logger.error(f"计算财务健康系数失败: {e}", exc_info=True)
            return 0.6
    
    def _calculate_financial_health_score(self, financial_data: Dict) -> float:
        """
        计算财务健康得分（满分100）
        
        基于：ROE、现金流、负债率、盈利质量
        """
        # 使用已有的财务健康系数，转换为0-100分
        health_coefficient = self.calculate_financial_health(financial_data)
        # 财务健康系数是0.6-1.0，转换为0-100分
        return (health_coefficient - 0.6) / 0.4 * 100
    
    def _calculate_profitability_score(self, financial_data: Dict) -> float:
        """
        计算盈利能力得分（满分100）
        
        基于：ROE、净利率
        """
        roe = financial_data.get('roe_ttm', 0) or financial_data.get('roe', 0)
        net_margin = financial_data.get('net_margin_ttm', 0) or financial_data.get('net_margin', 0)
        
        # ROE评分：0-50分
        if roe <= 0:
            roe_score = 0
        elif roe < 10:
            roe_score = roe * 5  # 0-50分
        elif roe < 20:
            roe_score = 50 + (roe - 10) * 2  # 50-70分
        elif roe < 30:
            roe_score = 70 + (roe - 20) * 1.5  # 70-85分
        else:
            roe_score = 85 + min((roe - 30) * 0.5, 15)  # 85-100分
        
        # 净利率评分：0-50分
        if net_margin <= 0:
            margin_score = 0
        elif net_margin < 5:
            margin_score = net_margin * 10  # 0-50分
        elif net_margin < 10:
            margin_score = 50 + (net_margin - 5) * 4  # 50-70分
        elif net_margin < 20:
            margin_score = 70 + (net_margin - 10) * 2  # 70-90分
        else:
            margin_score = 90 + min((net_margin - 20) * 0.5, 10)  # 90-100分
        
        # 综合：ROE和净利率各占50%
        return (roe_score * 0.5 + margin_score * 0.5)
    
    def _calculate_growth_score(self, financial_data: Dict) -> float:
        """
        计算成长性得分（满分100）
        
        基于：营收同比增长率、净利润同比增长率、增长稳定性
        成长性 = 营收增长(40%) + 利润增长(40%) + 增长稳定性(20%)
        """
        revenue_growth = financial_data.get('revenue_growth_yoy', 0) or financial_data.get('revenue_growth', 0)
        profit_growth = financial_data.get('profit_growth_yoy', 0) or financial_data.get('profit_growth', 0)
        profit_volatility = financial_data.get('profit_volatility', 0)  # 利润波动性（标准差）
        
        # 1. 营收增长评分：0-40分
        if revenue_growth <= 0:
            revenue_score = 0
        elif revenue_growth < 10:
            revenue_score = revenue_growth * 4  # 0-40分
        elif revenue_growth < 20:
            revenue_score = 40 + (revenue_growth - 10) * 1.6  # 40-56分
        elif revenue_growth < 50:
            revenue_score = 56 + (revenue_growth - 20) * 0.53  # 56-72分
        else:
            revenue_score = 72 + min((revenue_growth - 50) * 0.16, 8)  # 72-80分
        revenue_score = min(revenue_score, 40)  # 最高40分
        
        # 2. 净利润增长评分：0-40分
        if profit_growth <= 0:
            profit_score = 0
        elif profit_growth < 10:
            profit_score = profit_growth * 4  # 0-40分
        elif profit_growth < 20:
            profit_score = 40 + (profit_growth - 10) * 1.6  # 40-56分
        elif profit_growth < 50:
            profit_score = 56 + (profit_growth - 20) * 0.53  # 56-72分
        else:
            profit_score = 72 + min((profit_growth - 50) * 0.16, 8)  # 72-80分
        profit_score = min(profit_score, 40)  # 最高40分
        
        # 3. 增长稳定性评分：0-20分（波动性越小，得分越高）
        if profit_volatility == 0:
            stability_score = 20  # 无波动，满分
        elif profit_volatility < 5:
            stability_score = 20 - profit_volatility * 2  # 20-10分
        elif profit_volatility < 10:
            stability_score = 10 - (profit_volatility - 5) * 1  # 10-5分
        elif profit_volatility < 20:
            stability_score = 5 - (profit_volatility - 10) * 0.3  # 5-2分
        else:
            stability_score = max(0, 2 - (profit_volatility - 20) * 0.1)  # 2-0分
        
        # 综合：营收增长40% + 利润增长40% + 增长稳定性20%
        return revenue_score + profit_score + stability_score
    
    def _calculate_valuation_score(self, stock_data: Dict, financial_data: Dict) -> float:
        """
        计算估值得分（满分100）
        
        基于：PE、PB
        估值越低（PE/PB越小），得分越高
        """
        # 优先从stock_data获取，如果没有则从financial_data获取
        pe = stock_data.get('pe_ttm', 0) or financial_data.get('pe_ttm', 0) or financial_data.get('pe', 0)
        pb = stock_data.get('pb', 0) or financial_data.get('pb_lyr', 0) or financial_data.get('pb_mrq', 0) or financial_data.get('pb', 0)
        
        # PE评分：0-50分（PE越低越好）
        if pe <= 0:
            pe_score = 0  # 负PE或0表示亏损
        elif pe < 10:
            pe_score = 50  # PE < 10，估值很低，满分
        elif pe < 20:
            pe_score = 50 - (pe - 10) * 2  # 50-30分
        elif pe < 30:
            pe_score = 30 - (pe - 20) * 1.5  # 30-15分
        elif pe < 50:
            pe_score = 15 - (pe - 30) * 0.5  # 15-5分
        else:
            pe_score = max(0, 5 - (pe - 50) * 0.1)  # 5-0分
        
        # PB评分：0-50分（PB越低越好）
        if pb <= 0:
            pb_score = 0  # 负PB或0
        elif pb < 1:
            pb_score = 50  # PB < 1，估值很低，满分
        elif pb < 2:
            pb_score = 50 - (pb - 1) * 20  # 50-30分
        elif pb < 3:
            pb_score = 30 - (pb - 2) * 15  # 30-15分
        elif pb < 5:
            pb_score = 15 - (pb - 3) * 5  # 15-5分
        else:
            pb_score = max(0, 5 - (pb - 5) * 0.5)  # 5-0分
        
        # 综合：PE和PB各占50%
        return (pe_score * 0.5 + pb_score * 0.5)
    
    def _calculate_profit_elasticity_score(self, financial_data: Dict) -> float:
        """计算盈利弹性得分（满分100）"""
        roe = financial_data.get('roe_ttm', 0) or financial_data.get('roe', 0)
        net_margin = financial_data.get('net_margin_ttm', 0) or financial_data.get('net_margin', 0)
        
        # ROE评分：0-50分
        # ROE < 10%: 0-20分
        # ROE 10-20%: 20-35分
        # ROE 20-30%: 35-45分
        # ROE >= 30%: 45-50分
        if roe <= 0:
            roe_score = 0
        elif roe < 10:
            roe_score = roe * 2  # 0-20分
        elif roe < 20:
            roe_score = 20 + (roe - 10) * 1.5  # 20-35分
        elif roe < 30:
            roe_score = 35 + (roe - 20) * 1.0  # 35-45分
        else:
            roe_score = 45 + min((roe - 30) * 0.5, 5)  # 45-50分
        
        # 净利率评分：0-50分
        # 净利率 < 5%: 0-20分
        # 净利率 5-10%: 20-35分
        # 净利率 10-20%: 35-45分
        # 净利率 >= 20%: 45-50分
        if net_margin <= 0:
            margin_score = 0
        elif net_margin < 5:
            margin_score = net_margin * 4  # 0-20分
        elif net_margin < 10:
            margin_score = 20 + (net_margin - 5) * 3  # 20-35分
        elif net_margin < 20:
            margin_score = 35 + (net_margin - 10) * 1.0  # 35-45分
        else:
            margin_score = 45 + min((net_margin - 20) * 0.5, 5)  # 45-50分
        
        return min(roe_score + margin_score, 100.0)
    
    def _calculate_cost_advantage_score(self, financial_data: Dict) -> float:
        """计算成本优势得分（满分100）"""
        gross_margin = financial_data.get('gross_margin_ttm', 0) or financial_data.get('gross_margin', 0)
        
        # 毛利率评分：0-100分
        # 毛利率 < 10%: 0-30分
        # 毛利率 10-20%: 30-60分
        # 毛利率 20-30%: 60-80分
        # 毛利率 30-50%: 80-95分
        # 毛利率 >= 50%: 95-100分
        if gross_margin <= 0:
            return 0
        elif gross_margin < 10:
            return gross_margin * 3  # 0-30分
        elif gross_margin < 20:
            return 30 + (gross_margin - 10) * 3  # 30-60分
        elif gross_margin < 30:
            return 60 + (gross_margin - 20) * 2  # 60-80分
        elif gross_margin < 50:
            return 80 + (gross_margin - 30) * 0.75  # 80-95分
        else:
            return 95 + min((gross_margin - 50) * 0.1, 5)  # 95-100分
    
    def _calculate_moat_score(self, financial_data: Dict) -> float:
        """
        计算成本优势/竞争优势得分（满分100）
        
        基于毛利率和行业地位（护城河）
        """
        gross_margin = financial_data.get('gross_margin_ttm', 0) or financial_data.get('gross_margin', 0)
        cr4 = financial_data.get('industry_cr4', 0)
        market_share = financial_data.get('market_share', 0)
        
        # 如果没有行业集中度数据，基于毛利率推断竞争优势
        if cr4 == 0 and market_share == 0:
            # 基于毛利率计算（高毛利率通常意味着有竞争优势）
            return self._calculate_cost_advantage_score(financial_data)
        
        # 如果有行业数据，使用行业内分位数
        # 简化：基于毛利率和行业地位综合计算
        cost_advantage = self._calculate_cost_advantage_score(financial_data)
        industry_score = min(cr4 * 50, 50) + min(market_share * 10, 50)
        
        # 综合：成本优势70%，行业地位30%
        return cost_advantage * 0.7 + industry_score * 0.3
    
    def _calculate_industry_structure_score(self, financial_data: Dict) -> float:
        """计算行业格局得分（满分100）- 保留兼容性"""
        return self._calculate_moat_score(financial_data)
    
    def _calculate_behavior_score(self, stock_data: Dict) -> float:
        """
        计算资金行为与趋势得分（满分100）
        
        基于K线、量能、趋势等市场行为数据
        """
        # 1. 成交额（30%）
        amount = stock_data.get('amount', 0) or stock_data.get('成交额', 0)
        if amount > 0:
            # 成交额越大，资金关注度越高
            # 10亿以上：30分，5-10亿：20分，1-5亿：10分，1亿以下：5分
            if amount >= 1000000000:  # 10亿
                amount_score = 30
            elif amount >= 500000000:  # 5亿
                amount_score = 20
            elif amount >= 100000000:  # 1亿
                amount_score = 10
            else:
                amount_score = 5
        else:
            amount_score = 0
        
        # 2. 换手率（30%）
        turnover_rate = stock_data.get('turnover_rate', 0) or stock_data.get('换手率', 0)
        if turnover_rate > 0:
            # 换手率越高，流动性越好
            # 5%以上：30分，3-5%：20分，1-3%：10分，1%以下：5分
            if turnover_rate >= 5:
                turnover_score = 30
            elif turnover_rate >= 3:
                turnover_score = 20
            elif turnover_rate >= 1:
                turnover_score = 10
            else:
                turnover_score = 5
        else:
            turnover_score = 0
        
        # 3. 趋势（40%）：基于MA20斜率、涨跌幅等
        ma20 = stock_data.get('ma20', 0)
        current_price = stock_data.get('lastPrice', 0) or stock_data.get('当前价', 0) or stock_data.get('close', 0)
        change_pct = stock_data.get('change_pct', 0) or stock_data.get('涨跌幅', 0) or stock_data.get('pct_chg', 0)
        
        trend_score = 0
        if ma20 > 0 and current_price > 0:
            # 价格在MA20之上，趋势向上
            if current_price > ma20 * 1.05:  # 价格高于MA20 5%以上
                trend_score = 40
            elif current_price > ma20 * 1.02:  # 价格高于MA20 2%以上
                trend_score = 30
            elif current_price > ma20:  # 价格在MA20之上
                trend_score = 20
            else:
                trend_score = 10
        
        # 涨跌幅加分
        if change_pct > 0:
            if change_pct >= 5:
                trend_score += 10
            elif change_pct >= 2:
                trend_score += 5
        
        trend_score = min(trend_score, 40)  # 最高40分
        
        # 综合得分
        return min(amount_score + turnover_score + trend_score, 100.0)
    
    def _calculate_capital_attention_score(self, stock_data: Dict) -> float:
        """计算资金关注度得分 - 保留兼容性，调用behavior_score"""
        return self._calculate_behavior_score(stock_data)

