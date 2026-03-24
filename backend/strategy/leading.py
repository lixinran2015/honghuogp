"""
龙头识别模块
根据涨幅、换手率、成交额等识别板块龙头股
"""

from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


class LeadingStockIdentifier:
    """龙头股识别器"""
    
    def __init__(self):
        """初始化龙头股识别器"""
        pass
    
    def identify_leader(
        self,
        stocks: List[Dict],
        min_change_pct: float = 0.0,
        min_turnover_rate: float = 1.0,
        min_amount: float = 0.0
    ) -> Optional[Dict]:
        """
        识别板块龙头股
        
        逻辑：
        1. 涨幅前排（优先考虑）
        2. 换手率健康（1%-10%之间）
        3. 成交额大（流动性好）
        
        Args:
            stocks: 板块内股票列表，每个股票包含行情数据
            min_change_pct: 最小涨幅要求（%）
            min_turnover_rate: 最小换手率要求（%）
            min_amount: 最小成交额要求（元）
        
        Returns:
            dict: 龙头股信息，包含code, name, changePct等，如果没有符合条件的返回None
        """
        try:
            if not stocks:
                return None
            
            # 筛选符合条件的股票
            candidates = []
            for stock in stocks:
                change_pct = stock.get('changePct', stock.get('涨跌幅', stock.get('pct_chg', 0)))
                turnover_rate = stock.get('turnoverRate', stock.get('换手率', stock.get('turnover_rate', 0)))
                amount = stock.get('amount', stock.get('成交额', 0))
                
                # 检查基本条件
                if change_pct < min_change_pct:
                    continue
                if turnover_rate < min_turnover_rate:
                    continue
                if amount < min_amount:
                    continue
                
                # 换手率健康检查（1%-10%之间）
                if not (1.0 <= turnover_rate <= 10.0):
                    continue
                
                candidates.append(stock)
            
            if not candidates:
                logger.debug("未找到符合条件的龙头股")
                return None
            
            # 计算综合得分：涨幅权重40%，成交额权重30%，换手率权重30%
            scored_candidates = []
            for stock in candidates:
                change_pct = stock.get('changePct', stock.get('涨跌幅', stock.get('pct_chg', 0)))
                turnover_rate = stock.get('turnoverRate', stock.get('换手率', stock.get('turnover_rate', 0)))
                amount = stock.get('amount', stock.get('成交额', 0))
                
                # 归一化得分（0-100）
                change_score = min(100, change_pct * 10)  # 涨幅*10，最高100分
                turnover_score = min(100, turnover_rate * 10)  # 换手率*10，最高100分
                amount_score = min(100, (amount / 1e8) * 10)  # 成交额/亿*10，最高100分
                
                # 综合得分
                total_score = (
                    change_score * 0.4 +
                    amount_score * 0.3 +
                    turnover_score * 0.3
                )
                
                scored_candidates.append({
                    'stock': stock,
                    'score': total_score
                })
            
            # 按综合得分排序，取最高分
            scored_candidates.sort(key=lambda x: x['score'], reverse=True)
            leader_stock = scored_candidates[0]['stock']
            
            # 构造龙头股信息
            leader_info = {
                'code': leader_stock.get('code', leader_stock.get('代码', '')),
                'name': leader_stock.get('name', leader_stock.get('名称', leader_stock.get('股票名称', ''))),
                'changePct': leader_stock.get('changePct', leader_stock.get('涨跌幅', leader_stock.get('pct_chg', 0))),
                'turnoverRate': leader_stock.get('turnoverRate', leader_stock.get('换手率', leader_stock.get('turnover_rate', 0))),
                'amount': leader_stock.get('amount', leader_stock.get('成交额', 0)),
                'sector': leader_stock.get('sector', leader_stock.get('行业', leader_stock.get('所属行业', '未知')))
            }
            
            logger.debug(
                f"识别到龙头股: {leader_info['name']} ({leader_info['code']}), "
                f"涨幅={leader_info['changePct']:.2f}%, "
                f"换手率={leader_info['turnoverRate']:.2f}%, "
                f"成交额={leader_info['amount']/1e8:.2f}亿"
            )
            
            return leader_info
            
        except Exception as e:
            logger.error(f"识别龙头股失败: {e}", exc_info=True)
            return None
    
    def identify_leaders_by_sector(
        self,
        stocks: List[Dict],
        sector_field: str = 'sector'
    ) -> Dict[str, Dict]:
        """
        按板块识别龙头股
        
        Args:
            stocks: 所有股票列表
            sector_field: 板块字段名
        
        Returns:
            dict: 板块名称 -> 龙头股信息的字典
        """
        try:
            # 按板块分组
            sector_stocks = {}
            for stock in stocks:
                sector = stock.get(sector_field, stock.get('行业', stock.get('所属行业', '未知')))
                if sector not in sector_stocks:
                    sector_stocks[sector] = []
                sector_stocks[sector].append(stock)
            
            # 为每个板块识别龙头股
            leaders = {}
            for sector, sector_stock_list in sector_stocks.items():
                leader = self.identify_leader(sector_stock_list)
                if leader:
                    leaders[sector] = leader
            
            logger.info(f"识别到 {len(leaders)} 个板块的龙头股")
            return leaders
            
        except Exception as e:
            logger.error(f"按板块识别龙头股失败: {e}", exc_info=True)
            return {}

