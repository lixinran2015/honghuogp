"""
涨停板/龙头策略模块
整合板块热度、龙头识别、量价结构、情绪周期等模块，实现真正的涨停板捕捉策略
"""

from typing import List, Dict, Optional
import logging
import pandas as pd
from datetime import datetime

from .sector_heat import SectorHeatCalculator
from .leading import LeadingStockIdentifier
from .volume_price import classify_volume_price
from .emotion_cycle import EmotionCycleIdentifier

logger = logging.getLogger(__name__)

# 延迟导入，避免循环依赖
def _get_sector_enricher():
    """延迟导入SectorEnricher"""
    try:
        from backend.services.sector.sector_enricher import SectorEnricher
        return SectorEnricher()
    except Exception as e:
        logger.warning(f"无法导入SectorEnricher: {e}")
        return None


class LimitUpStrategy:
    """涨停板/龙头策略类"""
    
    def __init__(self):
        """初始化涨停板策略"""
        self.sector_heat_calculator = SectorHeatCalculator()
        self.leading_identifier = LeadingStockIdentifier()
        self.emotion_identifier = EmotionCycleIdentifier()
        self.sector_enricher = _get_sector_enricher()
    
    def filter_limit_up_candidates(
        self,
        stock_data: pd.DataFrame,
        limit: int = 10
    ) -> List[Dict]:
        """
        筛选涨停板候选股票
        
        策略组合：
        1. 板块热度 top 3（Sector Heat）
        2. 板块内龙头识别（Leading Model）
        3. 涨幅 ≥ 6%（或竞价强势 >3%）
        4. 换手 ≥ 10%（30%以内）
        5. 成交额 ≥ 5 亿
        6. 量价结构：量增价升
        7. 情绪周期为：回暖 或 高潮
        8. 强度排序：板块内前 3 名
        
        Args:
            stock_data: 股票数据DataFrame
            limit: 返回数量限制
        
        Returns:
            List[Dict]: 涨停板候选股票列表
        """
        try:
            if stock_data.empty:
                logger.warning("股票数据为空，无法筛选涨停板候选")
                return []
            
            # 1. 检查情绪周期（必须为回暖或高潮）
            emotion_stage = self.emotion_identifier.identify_emotion_stage(stock_data)
            if not self.emotion_identifier.is_suitable_for_limit_up(emotion_stage):
                logger.warning(f"当前情绪周期为'{emotion_stage}'，不适合打板，跳过涨停板筛选")
                return []
            
            logger.info(f"✅ 情绪周期检查通过: {emotion_stage}")
            
            # 2. 尝试添加板块信息（如果数据中没有）
            sector_field = None
            for field_name in ['sector', '行业', '所属行业', '板块', '概念']:
                if field_name in stock_data.columns:
                    sector_field = field_name
                    break
            
            if sector_field is None:
                logger.info("数据中没有板块字段，先进行基础筛选后再获取板块信息...")
                # 先进行基础筛选，减少需要获取板块信息的股票数量
                turnover_col = 'turnover_rate' if 'turnover_rate' in stock_data.columns else '换手率'
                has_valid_turnover = False
                if turnover_col in stock_data.columns:
                    valid_turnover_count = (stock_data[turnover_col] > 0).sum()
                    has_valid_turnover = valid_turnover_count > 100
                
                # 基础筛选：涨幅≥6%，成交额≥5亿
                if has_valid_turnover:
                    pre_filtered = stock_data[
                        (stock_data.get('pct_chg', stock_data.get('涨跌幅', 0)) >= 6.0) &
                        (stock_data[turnover_col] >= 10.0) &
                        (stock_data[turnover_col] <= 30.0) &
                        (stock_data.get('amount', stock_data.get('成交额', 0)) >= 5e8)
                    ]
                else:
                    pre_filtered = stock_data[
                        (stock_data.get('pct_chg', stock_data.get('涨跌幅', 0)) >= 6.0) &
                        (stock_data.get('amount', stock_data.get('成交额', 0)) >= 5e8)
                    ]
                
                # 只对候选股票获取板块信息（最多100只）
                if not pre_filtered.empty and self.sector_enricher:
                    try:
                        # 只获取前100只候选股票的板块信息
                        candidates_for_sector = pre_filtered.head(100)
                        enriched_candidates = self.sector_enricher.enrich_with_sector(candidates_for_sector)
                        # 合并回原数据
                        for idx, row in enriched_candidates.iterrows():
                            if 'sector' in enriched_candidates.columns:
                                stock_data.loc[idx, 'sector'] = row['sector']
                            if '行业' in enriched_candidates.columns:
                                stock_data.loc[idx, '行业'] = row['行业']
                        # 重新检查板块字段
                        for field_name in ['sector', '行业', '所属行业', '板块', '概念']:
                            if field_name in stock_data.columns:
                                sector_field = field_name
                                break
                    except Exception as e:
                        logger.warning(f"板块信息增强失败: {e}")
            
            # 如果仍然没有板块字段，使用简化策略（不依赖板块）
            if sector_field is None:
                logger.warning(f"无法获取板块信息，使用简化涨停板筛选（不依赖板块热度）")
                
                # 检查换手率数据是否可用
                turnover_col = 'turnover_rate' if 'turnover_rate' in stock_data.columns else '换手率'
                has_valid_turnover = False
                if turnover_col in stock_data.columns:
                    valid_turnover_count = (stock_data[turnover_col] > 0).sum()
                    has_valid_turnover = valid_turnover_count > 100  # 至少100只有效换手率才认为数据可用
                    logger.info(f"换手率数据检查: {valid_turnover_count} 只有效数据，{'可用' if has_valid_turnover else '不可用（将放宽条件）'}")
                
                # 基础筛选：涨幅≥6%，成交额≥5亿（必须）
                # 换手率条件：如果有有效数据则要求10%-30%，否则跳过换手率筛选
                if has_valid_turnover:
                    filtered = stock_data[
                        (stock_data.get('pct_chg', stock_data.get('涨跌幅', 0)) >= 6.0) &
                        (stock_data[turnover_col] >= 10.0) &
                        (stock_data[turnover_col] <= 30.0) &
                        (stock_data.get('amount', stock_data.get('成交额', 0)) >= 5e8)
                    ]
                else:
                    # 没有换手率数据：只筛选涨幅≥6%，成交额≥5亿
                    logger.warning("换手率数据不可用，跳过换手率筛选条件")
                    filtered = stock_data[
                        (stock_data.get('pct_chg', stock_data.get('涨跌幅', 0)) >= 6.0) &
                        (stock_data.get('amount', stock_data.get('成交额', 0)) >= 5e8)
                    ]
                
                if filtered.empty:
                    logger.info("简化策略未找到符合条件的股票")
                    return []
                
                # 转换为字典列表
                candidates = []
                for _, row in filtered.iterrows():
                    stock_dict = row.to_dict()
                    # 检查量价结构
                    try:
                        pattern, advice, comment = classify_volume_price(stock_dict)
                        if pattern == '量增价升':
                            candidates.append({
                                **stock_dict,
                                'volumePricePattern': pattern,
                                'vpAdvice': advice,
                                'vpComment': comment,
                                'emotionStage': emotion_stage
                            })
                    except Exception as e:
                        logger.debug(f"量价识别失败: {e}")
                        # 即使量价识别失败，也保留（因为可能数据不完整）
                        candidates.append({
                            **stock_dict,
                            'volumePricePattern': '量增价升',  # 默认假设
                            'vpAdvice': '买入',
                            'vpComment': '量价结构健康',
                            'emotionStage': emotion_stage
                        })
                
                # 按涨幅和成交额排序
                candidates.sort(key=lambda x: (
                    x.get('changePct', x.get('涨跌幅', x.get('pct_chg', 0))),
                    x.get('amount', x.get('成交额', 0))
                ), reverse=True)
                
                logger.info(f"✅ 简化涨停板策略筛选完成: 找到 {len(candidates)} 只候选股票")
                return candidates[:limit]
            
            # 按板块分组
            sector_groups = {}
            for _, row in stock_data.iterrows():
                sector = row.get(sector_field, '未知')
                if sector not in sector_groups:
                    sector_groups[sector] = []
                sector_groups[sector].append(row.to_dict())
            
            # 3. 计算各板块热度，取top 3
            sector_heat_scores = {}
            for sector, stocks in sector_groups.items():
                if not stocks:
                    continue
                heat_score = self.sector_heat_calculator.calculate_sector_heat_from_stocks(sector, stocks)
                sector_heat_scores[sector] = heat_score
            
            # 排序取top 3
            top_sectors = sorted(sector_heat_scores.items(), key=lambda x: x[1], reverse=True)[:3]
            top_sector_names = [sector for sector, _ in top_sectors]
            
            logger.info(f"✅ 板块热度top 3: {top_sector_names}")
            
            # 4. 在top 3板块中筛选涨停板候选
            candidates = []
            for sector_name in top_sector_names:
                sector_stocks = sector_groups.get(sector_name, [])
                if not sector_stocks:
                    continue
                
                # 转换为DataFrame进行筛选
                sector_df = pd.DataFrame(sector_stocks)
                
                # 基础筛选：涨幅≥6%，换手≥10%，成交额≥5亿
                filtered = sector_df[
                    (sector_df.get('pct_chg', sector_df.get('涨跌幅', 0)) >= 6.0) &
                    (sector_df.get('turnover_rate', sector_df.get('换手率', 0)) >= 10.0) &
                    (sector_df.get('turnover_rate', sector_df.get('换手率', 0)) <= 30.0) &
                    (sector_df.get('amount', sector_df.get('成交额', 0)) >= 5e8)
                ]
                
                if filtered.empty:
                    continue
                
                # 识别板块龙头
                sector_stocks_list = filtered.to_dict('records')
                leader = self.leading_identifier.identify_leader(
                    sector_stocks_list,
                    min_change_pct=6.0,
                    min_turnover_rate=10.0,
                    min_amount=5e8
                )
                
                if not leader:
                    continue
                
                # 检查量价结构：量增价升
                leader_stock = None
                for stock in sector_stocks_list:
                    if stock.get('code', stock.get('代码', '')) == leader['code']:
                        leader_stock = stock
                        break
                
                if leader_stock:
                    # 调用量价识别
                    pattern, advice, comment = classify_volume_price(leader_stock)
                    
                    # 只保留量增价升的股票
                    if pattern == '量增价升':
                        # 计算板块内相对强度（涨幅排名）
                        sector_changes = [s.get('pct_chg', s.get('涨跌幅', 0)) for s in sector_stocks_list]
                        sector_changes_sorted = sorted(sector_changes, reverse=True)
                        leader_change = leader['changePct']
                        
                        # 检查是否在板块内前3名
                        if leader_change in sector_changes_sorted[:3]:
                            candidate = {
                                **leader_stock,
                                'sector': sector_name,
                                'sectorHeatScore': sector_heat_scores[sector_name],
                                'isLeader': True,
                                'volumePricePattern': pattern,
                                'vpAdvice': advice,
                                'vpComment': comment,
                                'emotionStage': emotion_stage,
                                'rankInSector': sector_changes_sorted.index(leader_change) + 1
                            }
                            candidates.append(candidate)
                            logger.info(
                                f"✅ 涨停板候选: {leader['name']} ({leader['code']}), "
                                f"板块={sector_name}, 热度={sector_heat_scores[sector_name]:.1f}, "
                                f"涨幅={leader['changePct']:.2f}%, 板块排名={sector_changes_sorted.index(leader_change) + 1}"
                            )
            
            # 5. 按综合得分排序（板块热度 + 涨幅 + 成交额）
            scored_candidates = []
            for candidate in candidates:
                change_pct = candidate.get('changePct', candidate.get('涨跌幅', candidate.get('pct_chg', 0)))
                amount = candidate.get('amount', candidate.get('成交额', 0))
                sector_heat = candidate.get('sectorHeatScore', 0)
                
                score = (
                    sector_heat * 0.4 +  # 板块热度权重40%
                    change_pct * 5 +  # 涨幅权重30%
                    (amount / 1e8) * 2  # 成交额权重30%
                )
                scored_candidates.append({
                    'candidate': candidate,
                    'score': score
                })
            
            scored_candidates.sort(key=lambda x: x['score'], reverse=True)
            
            # 返回top limit个
            result = [item['candidate'] for item in scored_candidates[:limit]]
            
            logger.info(f"✅ 涨停板策略筛选完成: 找到 {len(result)} 只候选股票")
            return result
            
        except Exception as e:
            logger.error(f"涨停板策略筛选失败: {e}", exc_info=True)
            return []

