"""
短线强势股（打板策略）筛选器
从全市场中筛选最有可能当日或次日涨停/走出强趋势的龙头股
"""

from typing import List, Dict, Optional
import logging
import pandas as pd
from datetime import datetime

from backend.models.stock_data import StockData
from backend.models.strategy_result import StrategyResult
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


class ShortTermLimitUpFilter:
    """短线强势股（打板策略）筛选器"""
    
    def __init__(self):
        """初始化打板策略筛选器"""
        self.sector_heat_calculator = SectorHeatCalculator()
        self.leading_identifier = LeadingStockIdentifier()
        self.emotion_identifier = EmotionCycleIdentifier()
        self.sector_enricher = _get_sector_enricher()
    
    def filter_limit_up_candidates(
        self,
        stock_data: List[StockData],
        limit: int = 10,
        min_samples: int = 3
    ) -> StrategyResult:
        """
        筛选短线强势股（打板候选）
        
        Args:
            stock_data: 股票数据模型列表
            limit: 返回数量限制
            min_samples: 最小样本数，低于此数量会返回警告
        
        Returns:
            StrategyResult: 策略筛选结果
        """
        try:
            if not stock_data:
                return StrategyResult(
                    candidates=[],
                    warning="输入数据为空",
                    filter_steps={}
                )
            
            # 转换为DataFrame以便使用现有逻辑（临时方案）
            stock_dicts = [stock.to_dict() for stock in stock_data]
            df = pd.DataFrame(stock_dicts)
            
            filter_steps = {}
            
            # Step 1: 锁定热点板块
            sector_field = self._get_sector_field(df)
            if sector_field:
                df = self._enrich_sector_info(df)
                hot_sectors = self._identify_hot_sectors(df, sector_field)
                filter_steps["hot_sectors"] = len(hot_sectors)
                logger.info(f"✅ Step 1: 识别到 {len(hot_sectors)} 个热点板块")
            else:
                hot_sectors = []
                filter_steps["hot_sectors"] = 0
                logger.warning("⚠️ Step 1: 无法获取板块信息，跳过热点板块过滤")
            
            # Step 2: 在热点板块内筛选强势个股
            if hot_sectors:
                # 只筛选热点板块内的股票
                filtered_stocks = df[
                    df[sector_field].isin(hot_sectors)
                ].copy()
            else:
                # 没有板块信息，直接筛选全市场
                filtered_stocks = df.copy()
            
            # 基础筛选条件
            filtered_stocks = self._filter_strong_stocks(filtered_stocks)
            filter_steps["after_basic_filter"] = len(filtered_stocks)
            logger.info(f"✅ Step 2: 基础筛选后剩余 {len(filtered_stocks)} 只股票")
            
            if filtered_stocks.empty:
                return StrategyResult(
                    candidates=[],
                    warning="基础筛选后无符合条件的股票",
                    filter_steps=filter_steps
                )
            
            # Step 3: 量价结构必须健康
            filtered_stocks = self._filter_volume_price_pattern(filtered_stocks)
            filter_steps["after_volume_price"] = len(filtered_stocks)
            logger.info(f"✅ Step 3: 量价结构筛选后剩余 {len(filtered_stocks)} 只股票")
            
            if filtered_stocks.empty:
                return StrategyResult(
                    candidates=[],
                    warning="量价结构筛选后无符合条件的股票",
                    filter_steps=filter_steps
                )
            
            # Step 4: 板块内部排序（龙头识别）
            candidate_dicts = self._rank_by_sector(filtered_stocks, sector_field, limit)
            filter_steps["final_candidates"] = len(candidate_dicts)
            
            # 将字典列表转换为StockData列表
            candidates = []
            for candidate_dict in candidate_dicts:
                try:
                    stock = StockData.from_dict(candidate_dict)
                    candidates.append(stock)
                except Exception as e:
                    logger.warning(f"转换候选股票失败: {e}")
                    continue
            
            # 检查样本数
            warning = None
            if len(candidates) < min_samples:
                warning = f"符合条件的标的过少（{len(candidates)}只），策略可能过严或数据不足"
            
            return StrategyResult(
                candidates=candidates,
                warning=warning,
                filter_steps=filter_steps
            )
            
        except Exception as e:
            logger.error(f"打板策略筛选失败: {e}", exc_info=True)
            return StrategyResult(
                candidates=[],
                warning=f"筛选过程出错: {str(e)}",
                filter_steps={}
            )
    
    def _get_sector_field(self, df: pd.DataFrame) -> Optional[str]:
        """获取板块字段名"""
        for field_name in ['sector', '行业', '所属行业', '板块', '概念']:
            if field_name in df.columns:
                return field_name
        return None
    
    def _enrich_sector_info(self, df: pd.DataFrame) -> pd.DataFrame:
        """增强板块信息"""
        sector_field = self._get_sector_field(df)
        if sector_field is None and self.sector_enricher:
            try:
                df = self.sector_enricher.enrich_with_sector(df)
            except Exception as e:
                logger.warning(f"板块信息增强失败: {e}")
        return df
    
    def _check_sector_heat(self, stock) -> bool:
        """
        短线必须来自热门板块（>=10）
        无板块数据按兜底逻辑返回 True
        
        Args:
            stock: StockData对象或字典，包含short_heat_score字段
        
        Returns:
            bool: 是否通过板块热度检查
        """
        try:
            # 获取板块热度
            heat = getattr(stock, "short_heat_score", None)
            
            if heat is None:
                # 允许通过，但打一个 warning
                code = getattr(stock, "code", "未知")
                logger.warning(f"[short] 无板块热度数据，允许兜底通过: {code}")
                return True
            
            # 统一阈值：>= 10
            return heat >= 10
            
        except Exception as e:
            logger.warning(f"检查板块热度失败: {e}")
            return True  # 出错时允许通过
    
    def _identify_hot_sectors(
        self,
        stock_data: pd.DataFrame,
        sector_field: str,
        top_n: int = 5,
        min_sector_change: float = 2.0
    ) -> List[str]:
        """
        识别热点板块
        
        条件：
        - sector_rank ≤ 5（板块涨幅排在前5）
        或 sector_change_pct ≥ 2%
        """
        try:
            # 按板块分组
            sector_groups = {}
            for _, row in stock_data.iterrows():
                sector = row.get(sector_field, '未知')
                if sector not in sector_groups:
                    sector_groups[sector] = []
                sector_groups[sector].append(row.to_dict())
            
            # 计算各板块涨幅
            sector_changes = {}
            for sector, stocks in sector_groups.items():
                if not stocks:
                    continue
                changes = [
                    s.get('changePct', s.get('涨跌幅', s.get('pct_chg', 0)))
                    for s in stocks
                ]
                avg_change = sum(changes) / len(changes) if changes else 0
                sector_changes[sector] = avg_change
            
            # 排序取top N
            sorted_sectors = sorted(sector_changes.items(), key=lambda x: x[1], reverse=True)
            
            # 筛选热点板块
            hot_sectors = []
            for sector, change_pct in sorted_sectors[:top_n]:
                if change_pct >= min_sector_change:
                    hot_sectors.append(sector)
            
            return hot_sectors
            
        except Exception as e:
            logger.error(f"识别热点板块失败: {e}", exc_info=True)
            return []
    
    def _filter_strong_stocks(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        筛选强势个股
        
        条件（放宽）：
        - change_pct ≥ 3%（放宽：从6%降到3%）
        - turnover_rate ≥ 5%（放宽：从10%降到5%，如果没有换手率数据则跳过）
        - amount ≥ 1e8（放宽：从5亿降到1亿）
        - 非ST、非退市整理股
        """
        try:
            filtered = df.copy()
            
            # 涨幅≥3%（放宽：从6%降到3%）
            change_col = None
            for col in ['changePct', 'pct_chg', '涨跌幅', 'change_pct']:
                if col in filtered.columns:
                    change_col = col
                    break
            
            if change_col:
                filtered = filtered[filtered[change_col] >= 3.0]  # 放宽：从6.0降到3.0
            else:
                logger.warning("没有找到涨幅字段，跳过涨幅筛选")
                return pd.DataFrame()
            
            # 换手率≥5%（放宽：从10%降到5%，如果数据可用）
            turnover_col = None
            for col in ['turnoverRate', 'turnover_rate', '换手率']:
                if col in filtered.columns:
                    turnover_col = col
                    break
            
            if turnover_col:
                valid_turnover = (filtered[turnover_col] > 0).sum()
                if valid_turnover > 100:  # 至少100只有效换手率才认为数据可用
                    filtered = filtered[filtered[turnover_col] >= 5.0]  # 放宽：从10.0降到5.0
                else:
                    logger.warning("换手率数据不可用，跳过换手率筛选")
            else:
                logger.warning("没有找到换手率字段，跳过换手率筛选")
            
            # 成交额≥1亿（放宽：从5亿降到1亿）
            amount_col = None
            for col in ['amount', '成交额']:
                if col in filtered.columns:
                    amount_col = col
                    break
            
            if amount_col:
                filtered = filtered[filtered[amount_col] >= 1e8]  # 放宽：从5e8降到1e8
            else:
                logger.warning("没有找到成交额字段，跳过成交额筛选")
            
            # 排除ST、退市
            filtered = self._exclude_st_and_delisted(filtered)
            
            return filtered
            
        except Exception as e:
            logger.error(f"强势个股筛选失败: {e}", exc_info=True)
            return pd.DataFrame()
    
    def _exclude_st_and_delisted(self, df: pd.DataFrame) -> pd.DataFrame:
        """排除ST和退市股票"""
        try:
            name_col = None
            for col in ['name', '股票名称', '名称']:
                if col in df.columns:
                    name_col = col
                    break
            
            if name_col:
                mask = ~df[name_col].astype(str).str.contains('ST', na=False)
                mask = mask & ~df[name_col].astype(str).str.contains('退', na=False)
                return df[mask].copy()
            
            return df
            
        except Exception as e:
            logger.warning(f"排除ST股票失败: {e}")
            return df
    
    def _filter_volume_price_pattern(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        量价结构必须健康
        
        优先保留：
        - 量增价升
        - 量平价升
        
        如果没有5日均量数据，放宽条件：
        - 涨幅>0且换手率>0的股票也保留
        """
        try:
            candidates = []
            for _, row in df.iterrows():
                stock_dict = row.to_dict()
                try:
                    pattern, advice, comment = classify_volume_price(stock_dict)
                    # 优先保留量增价升和量平价升
                    if pattern in ['量增价升', '量平价升']:
                        stock_dict['volumePricePattern'] = pattern
                        stock_dict['vpAdvice'] = advice
                        stock_dict['vpComment'] = comment
                        candidates.append(stock_dict)
                    # 如果没有5日均量数据，但涨幅>0，也保留（放宽条件，因为很多股票的换手率数据是0）
                    elif pattern == '无量价平' and stock_dict.get('changePct', stock_dict.get('涨跌幅', stock_dict.get('pct_chg', 0))) > 0:
                        change_pct = stock_dict.get('changePct', stock_dict.get('涨跌幅', stock_dict.get('pct_chg', 0)))
                        turnover_rate = stock_dict.get('turnoverRate', stock_dict.get('turnover_rate', stock_dict.get('换手率', 0)))
                        # 假设是量增价升（乐观估计），即使换手率为0也保留（因为数据可能不完整）
                        stock_dict['volumePricePattern'] = '量增价升'
                        stock_dict['vpAdvice'] = '买入'
                        if turnover_rate > 0:
                            stock_dict['vpComment'] = f'涨幅{change_pct:.2f}%，换手率{turnover_rate:.2f}%，量价配合（缺少5日均量数据）'
                        else:
                            stock_dict['vpComment'] = f'涨幅{change_pct:.2f}%，量价配合（缺少5日均量和换手率数据）'
                        candidates.append(stock_dict)
                except Exception as e:
                    logger.debug(f"量价识别失败: {e}")
                    # 如果量价识别失败，但涨幅>0，默认保留（可能数据不完整）
                    change_pct = stock_dict.get('changePct', stock_dict.get('涨跌幅', stock_dict.get('pct_chg', 0)))
                    if change_pct >= 6.0:  # 只保留涨幅≥6%的股票（符合打板策略）
                        stock_dict['volumePricePattern'] = '量增价升'  # 默认假设
                        stock_dict['vpAdvice'] = '买入'
                        stock_dict['vpComment'] = f'涨幅{change_pct:.2f}%，量价结构健康（数据不完整，基于涨幅判断）'
                        candidates.append(stock_dict)
            
            logger.info(f"✅ 量价结构筛选：从 {len(df)} 只股票中筛选出 {len(candidates)} 只")
            return pd.DataFrame(candidates) if candidates else pd.DataFrame()
            
        except Exception as e:
            logger.error(f"量价结构筛选失败: {e}", exc_info=True)
            return pd.DataFrame()
    
    def _rank_by_sector(
        self,
        df: pd.DataFrame,
        sector_field: Optional[str],
        limit: int
    ) -> List[Dict]:
        """
        板块内部排序（龙头识别）
        
        排序规则：
        1. 是否涨停（is_limit_up = True）
        2. 涨幅（越高越靠前）
        3. 成交额（越大越靠前）
        4. 换手率（10-30%区间最优）
        """
        try:
            candidates = []
            
            # 计算是否涨停
            def calculate_is_limit_up(row):
                close = row.get('close', row.get('当前价', row.get('lastPrice', 0)))
                pre_close = row.get('pre_close', row.get('昨收', 0))
                if pre_close > 0:
                    limit_up_price = pre_close * 1.1  # 10%涨停
                    return close >= limit_up_price * 0.999
                return False
            
            df['is_limit_up'] = df.apply(calculate_is_limit_up, axis=1)
            
            # 计算综合得分
            def calculate_score(row):
                score = 0
                
                # 是否涨停（权重最高）
                if row['is_limit_up']:
                    score += 1000
                
                # 涨幅（权重30%）
                change_pct = row.get('changePct', row.get('涨跌幅', row.get('pct_chg', 0)))
                score += change_pct * 10
                
                # 成交额（权重20%）
                amount = row.get('amount', row.get('成交额', 0))
                score += (amount / 1e8) * 2  # 每亿得2分
                
                # 换手率（权重10%，10-30%区间最优）
                turnover_col = 'turnover_rate' if 'turnover_rate' in row.index else '换手率'
                if turnover_col in row.index:
                    turnover = row.get(turnover_col, 0)
                    if 10 <= turnover <= 30:
                        score += 10  # 最优区间
                    elif turnover > 0:
                        score += 5  # 有换手率但不在最优区间
                
                return score
            
            df['score'] = df.apply(calculate_score, axis=1)
            
            # 如果有板块信息，按板块分组排序
            if sector_field and sector_field in df.columns:
                sector_groups = {}
                for _, row in df.iterrows():
                    sector = row.get(sector_field, '未知')
                    if sector not in sector_groups:
                        sector_groups[sector] = []
                    sector_groups[sector].append(row.to_dict())
                
                # 每个板块取前1-3名
                for sector, stocks in sector_groups.items():
                    sorted_stocks = sorted(stocks, key=lambda x: x.get('score', 0), reverse=True)
                    candidates.extend(sorted_stocks[:3])
                
                # 最终按得分排序，取前limit个
                candidates.sort(key=lambda x: x.get('score', 0), reverse=True)
                return candidates[:limit]
            else:
                # 没有板块信息，直接按得分排序
                sorted_df = df.sort_values('score', ascending=False)
                return sorted_df.head(limit).to_dict('records')
            
        except Exception as e:
            logger.error(f"板块内部排序失败: {e}", exc_info=True)
            # 降级：简单按涨幅和成交额排序
            df_sorted = df.sort_values(
                by=['changePct' if 'changePct' in df.columns else '涨跌幅', 'amount' if 'amount' in df.columns else '成交额'],
                ascending=[False, False]
            )
            return df_sorted.head(limit).to_dict('records')

