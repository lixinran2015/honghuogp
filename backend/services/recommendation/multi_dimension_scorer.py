"""
多维评分服务
实现七维评分+动态权重系统

PRODUCT_LINE: S  （当前主要服务于启动龙头与推荐池，可被其它产品线复用）
"""
import logging
from typing import Dict, Optional, List
from datetime import datetime, date
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class ScoringStrategy(Enum):
    """评分策略"""
    AGGRESSIVE = "aggressive"   # 短线激进
    BALANCED = "balanced"       # 均衡
    DEFENSIVE = "defensive"     # 防守


@dataclass
class DimensionScore:
    """单维度得分"""
    dimension: str
    score: float
    weight: float
    weighted_score: float
    detail: str


@dataclass
class MultiDimensionResult:
    """多维评分结果"""
    ts_code: str
    name: str
    total_score: float
    dimension_scores: Dict[str, float]
    dimension_details: Dict[str, str]
    weighted_scores: Dict[str, float]
    rank_reason: str
    strategy: str
    user_friendly_tags: List[str]


class MultiDimensionScorer:
    """多维评分服务"""
    
    # 维度权重配置
    WEIGHT_CONFIG = {
        ScoringStrategy.AGGRESSIVE.value: {
            'technical': 0.30,      # 技术面
            'leader': 0.20,         # 龙头地位
            'money_flow': 0.20,     # 资金流向
            'sector_cycle': 0.10,   # 板块周期
            'fundamental': 0.05,    # 财务质量
            'sentiment': 0.10,      # 情绪热度
            'timing': 0.05          # 介入时机
        },
        ScoringStrategy.BALANCED.value: {
            'technical': 0.20,
            'leader': 0.20,
            'money_flow': 0.15,
            'sector_cycle': 0.15,
            'fundamental': 0.15,
            'sentiment': 0.10,
            'timing': 0.05
        },
        ScoringStrategy.DEFENSIVE.value: {
            'technical': 0.15,
            'leader': 0.15,
            'money_flow': 0.10,
            'sector_cycle': 0.15,
            'fundamental': 0.25,
            'sentiment': 0.10,
            'timing': 0.10
        }
    }
    
    # 用户友好标签映射
    TAG_THRESHOLDS = {
        'technical': (80, '技术强势'),
        'leader': (80, '板块龙头'),
        'money_flow': (70, '资金流入'),
        'sector_cycle': (80, '启动初期'),
        'fundamental': (70, '基本面优'),
        'sentiment': (60, '市场关注')
    }
    
    def __init__(self, warehouse_service=None, strategy: str = "balanced"):
        self.ws = warehouse_service
        if not self.ws:
            from data_warehouse.service.warehouse_service import WarehouseService
            self.ws = WarehouseService()
        
        self.strategy = strategy
        self.weights = self.WEIGHT_CONFIG.get(strategy, self.WEIGHT_CONFIG['balanced'])
    
    def set_strategy(self, strategy: str):
        """设置评分策略"""
        if strategy in self.WEIGHT_CONFIG:
            self.strategy = strategy
            self.weights = self.WEIGHT_CONFIG[strategy]
    
    def score(self, stock_data: Dict, trade_date: Optional[str] = None) -> Dict:
        """
        计算七维综合得分
        
        Args:
            stock_data: 股票数据，包含以下字段：
                - ts_code: 股票代码
                - name: 股票名称
                - startup_score: 启动得分
                - leader_type: 龙头类型
                - sector_cycle: 板块周期
                - money_flow: 资金流向数据
                - fundamental: 财务数据
                - sentiment: 情绪数据
                - filter_result: 启动筛选结果
            trade_date: 交易日期
            
        Returns:
            Dict: 评分结果
        """
        try:
            ts_code = stock_data.get('ts_code', '')
            name = stock_data.get('name', '')
            
            # 计算各维度得分
            dimension_scores = {}
            dimension_details = {}
            weighted_scores = {}
            
            # 1. 技术面得分
            tech_score, tech_detail = self._calc_technical_score(stock_data)
            dimension_scores['technical'] = tech_score
            dimension_details['technical'] = tech_detail
            weighted_scores['technical'] = tech_score * self.weights['technical']
            
            # 2. 龙头地位得分
            leader_score, leader_detail = self._calc_leader_score(stock_data)
            dimension_scores['leader'] = leader_score
            dimension_details['leader'] = leader_detail
            weighted_scores['leader'] = leader_score * self.weights['leader']
            
            # 3. 资金流向得分
            flow_score, flow_detail = self._calc_money_flow_score(stock_data)
            dimension_scores['money_flow'] = flow_score
            dimension_details['money_flow'] = flow_detail
            weighted_scores['money_flow'] = flow_score * self.weights['money_flow']
            
            # 4. 板块周期得分
            cycle_score, cycle_detail = self._calc_sector_cycle_score(stock_data)
            dimension_scores['sector_cycle'] = cycle_score
            dimension_details['sector_cycle'] = cycle_detail
            weighted_scores['sector_cycle'] = cycle_score * self.weights['sector_cycle']
            
            # 5. 财务质量得分
            fund_score, fund_detail = self._calc_fundamental_score(stock_data)
            dimension_scores['fundamental'] = fund_score
            dimension_details['fundamental'] = fund_detail
            weighted_scores['fundamental'] = fund_score * self.weights['fundamental']
            
            # 6. 情绪热度得分
            sent_score, sent_detail = self._calc_sentiment_score(stock_data)
            dimension_scores['sentiment'] = sent_score
            dimension_details['sentiment'] = sent_detail
            weighted_scores['sentiment'] = sent_score * self.weights['sentiment']
            
            # 7. 介入时机得分
            timing_score, timing_detail = self._calc_timing_score(stock_data)
            dimension_scores['timing'] = timing_score
            dimension_details['timing'] = timing_detail
            weighted_scores['timing'] = timing_score * self.weights['timing']
            
            # 计算总分
            total_score = sum(weighted_scores.values())
            
            # 生成用户友好标签
            user_tags = self._generate_user_tags(dimension_scores, stock_data)
            
            # 生成排名理由
            rank_reason = self._generate_rank_reason(
                dimension_scores, dimension_details, total_score
            )
            
            result = MultiDimensionResult(
                ts_code=ts_code,
                name=name,
                total_score=round(total_score, 1),
                dimension_scores={k: round(v, 1) for k, v in dimension_scores.items()},
                dimension_details=dimension_details,
                weighted_scores={k: round(v, 2) for k, v in weighted_scores.items()},
                rank_reason=rank_reason,
                strategy=self.strategy,
                user_friendly_tags=user_tags
            )
            
            return {
                'success': True,
                'data': result.__dict__
            }
            
        except Exception as e:
            logger.error(f"计算多维评分失败: {e}", exc_info=True)
            return {
                'success': False,
                'error': '操作失败',
                'data': None
            }
    
    def score_batch(self, stocks_data: List[Dict], trade_date: Optional[str] = None) -> List[Dict]:
        """批量评分并排序"""
        results = []
        for stock_data in stocks_data:
            result = self.score(stock_data, trade_date)
            if result['success'] and result['data']:
                results.append(result['data'])
        
        # 按总分排序
        results.sort(key=lambda x: x['total_score'], reverse=True)
        return results
    
    def _calc_technical_score(self, stock_data: Dict) -> tuple:
        """计算技术面得分"""
        score = 50
        details = []
        
        # 启动得分贡献
        startup_score = stock_data.get('startup_score', 0)
        if startup_score >= 90:
            score += 30
            details.append(f'启动得分{startup_score}分(优秀)')
        elif startup_score >= 80:
            score += 20
            details.append(f'启动得分{startup_score}分(良好)')
        elif startup_score >= 70:
            score += 10
            details.append(f'启动得分{startup_score}分(一般)')
        else:
            details.append(f'启动得分{startup_score}分(偏低)')
        
        # 信号强度
        filter_result = stock_data.get('filter_result', {})
        if filter_result.get('core_passed'):
            score += 10
            details.append('核心条件全通过')
        
        assist_count = filter_result.get('assist_count', 0)
        if assist_count >= 2:
            score += 10
            details.append(f'辅助确认{assist_count}个')
        
        # 量能状态
        volume_ratio = stock_data.get('volume_ratio', 1)
        if volume_ratio >= 2:
            score += 10
            details.append(f'放量{volume_ratio:.1f}倍')
        elif volume_ratio >= 1.5:
            score += 5
            details.append(f'温和放量{volume_ratio:.1f}倍')

        # 趋势动量（优先使用 20 日动量因子）
        mom_20d = stock_data.get('mom_20d')
        if mom_20d is not None:
            try:
                m20 = float(mom_20d)
            except (TypeError, ValueError):
                m20 = None
            if m20 is not None:
                if m20 >= 40:
                    score += 15
                    details.append(f'20日涨幅{m20:.1f}%（强趋势）')
                elif m20 >= 20:
                    score += 10
                    details.append(f'20日涨幅{m20:.1f}%（趋势良好）')
                elif m20 <= -10:
                    score -= 10
                    details.append(f'20日跌幅{m20:.1f}%（短期走弱）')

        # 换手结构（20 日平均换手率）
        turn_20d = stock_data.get('turnover_20d')
        if turn_20d is not None:
            try:
                t20 = float(turn_20d)
            except (TypeError, ValueError):
                t20 = None
            if t20 is not None:
                if 1 <= t20 <= 8:
                    score += 5
                    details.append(f'20日均换手{t20:.1f}%（流动性适中）')
                elif t20 > 15:
                    score -= 5
                    details.append(f'20日均换手{t20:.1f}%（换手偏高，博弈浓）')
        
        return min(100, max(0, score)), '；'.join(details) if details else '技术面一般'
    
    def _calc_leader_score(self, stock_data: Dict) -> tuple:
        """计算龙头地位得分"""
        leader_type = stock_data.get('leader_type', '')
        leader_rank = stock_data.get('leader_rank', 99)
        continuous_limit = stock_data.get('continuous_limit', 0)
        
        if leader_type == 'absolute_leader':
            score = 100
            detail = f'绝对龙头(排名第{leader_rank})'
            if continuous_limit >= 3:
                detail += f'，连板{continuous_limit}天'
        elif leader_type == 'rel_strength':
            score = 65
            detail = '相对抗跌（本板块普跌）'
        elif leader_type == 'catch_up':
            score = 70
            detail = '补涨龙头'
        elif leader_type == 'resilient':
            score = 55
            detail = '抗跌股（本板块普跌）'
        elif leader_type == 'follower':
            score = 40
            detail = '跟风股'
        else:
            score = 20
            detail = '非板块龙头'
        
        return score, detail
    
    def _calc_money_flow_score(self, stock_data: Dict) -> tuple:
        """计算资金流向得分"""
        money_flow = stock_data.get('money_flow', {})
        
        if not money_flow:
            return 50, '资金数据缺失'
        
        score = money_flow.get('score', 50)
        details = []
        
        main_days = money_flow.get('main_flow_days', 0)
        if main_days >= 3:
            details.append(f'主力连续{main_days}天净流入')
        elif main_days <= -3:
            details.append(f'主力连续{abs(main_days)}天净流出')
        
        north_change = money_flow.get('north_change_pct', 0)
        if north_change > 5:
            details.append(f'北向增持{north_change:.1f}%')
        elif north_change < -5:
            details.append(f'北向减持{abs(north_change):.1f}%')
        
        current_vs_cost = money_flow.get('current_vs_cost', '')
        if current_vs_cost == 'near':
            details.append('接近主力成本')
        elif current_vs_cost == 'below':
            details.append('低于主力成本')
        
        return score, '；'.join(details) if details else '资金面中性'
    
    def _calc_sector_cycle_score(self, stock_data: Dict) -> tuple:
        """计算板块周期得分"""
        sector_cycle = stock_data.get('sector_cycle', {})
        
        if not sector_cycle:
            return 50, '板块周期数据缺失'
        
        cycle_stage = sector_cycle.get('cycle_stage', 'unknown')
        leader_days = sector_cycle.get('leader_days', 0)
        followers_ratio = sector_cycle.get('followers_ratio', 0)
        
        if cycle_stage == 'early':
            score = 100
            detail = f'启动初期(龙头{leader_days}天，跟风{followers_ratio:.0%})'
        elif cycle_stage == 'accelerating':
            score = 60
            detail = f'加速期(龙头{leader_days}天，跟风{followers_ratio:.0%})'
        elif cycle_stage == 'declining':
            score = 20
            detail = f'衰退期(龙头{leader_days}天，跟风{followers_ratio:.0%})'
        else:
            score = 50
            detail = '板块周期未知'
        
        return score, detail
    
    def _calc_fundamental_score(self, stock_data: Dict) -> tuple:
        """计算财务质量得分"""
        fundamental = stock_data.get('fundamental', {})
        
        if not fundamental:
            return 50, '财务数据缺失'
        
        score = 50
        details = []
        
        # PE评估
        pe = fundamental.get('pe_ttm', 0)
        if pe and 0 < pe < 30:
            score += 15
            details.append(f'PE={pe:.1f}(合理)')
        elif pe and 0 < pe < 50:
            score += 5
            details.append(f'PE={pe:.1f}(偏高)')
        elif pe and pe < 0:
            details.append('PE为负(亏损)')
            score -= 10
        
        # ROE评估
        roe = fundamental.get('roe_ttm', 0)
        if roe and roe > 15:
            score += 15
            details.append(f'ROE={roe:.1f}%(优秀)')
        elif roe and roe > 10:
            score += 10
            details.append(f'ROE={roe:.1f}%(良好)')
        elif roe and roe > 5:
            score += 5
            details.append(f'ROE={roe:.1f}%(一般)')
        
        # PB评估
        pb = fundamental.get('pb_mrq', 0)
        if pb and 0 < pb < 3:
            score += 10
            details.append(f'PB={pb:.1f}(安全)')
        elif pb and pb > 10:
            score -= 5
            details.append(f'PB={pb:.1f}(偏高)')
        
        # PEG评估
        peg = fundamental.get('peg', 0)
        if peg and 0 < peg < 1:
            score += 10
            details.append(f'PEG={peg:.2f}(成长性好)')
        
        return min(100, max(0, score)), '；'.join(details) if details else '基本面一般'
    
    def _calc_sentiment_score(self, stock_data: Dict) -> tuple:
        """计算情绪热度得分"""
        sentiment = stock_data.get('sentiment', {})
        
        if not sentiment:
            return 50, '情绪数据缺失'
        
        score = 50
        details = []
        
        # 新闻情绪
        news_sentiment = sentiment.get('news_sentiment', 'neutral')
        news_score = sentiment.get('news_score', 50)
        if news_sentiment == 'bullish' or news_score > 60:
            score += 15
            details.append('新闻偏利好')
        elif news_sentiment == 'bearish' or news_score < 40:
            score -= 10
            details.append('新闻偏利空')
        
        # 股吧热度
        guba_score = sentiment.get('guba_score', 50)
        if guba_score > 70:
            score += 15
            details.append('股吧热度高')
        elif guba_score > 55:
            score += 5
            details.append('股吧有关注')
        
        # 是否在热点板块
        is_hot_sector = sentiment.get('is_hot_sector', False)
        if is_hot_sector:
            score += 10
            details.append('处于热点板块')
        
        return min(100, max(0, score)), '；'.join(details) if details else '情绪面中性'
    
    def _calc_timing_score(self, stock_data: Dict) -> tuple:
        """计算介入时机得分"""
        filter_result = stock_data.get('filter_result', {})
        
        score = 50
        details = []
        
        # 根据阶段判断
        stage = filter_result.get('stage', '')
        if stage == 'started':
            score += 20
            details.append('完全启动')
        elif stage == 'confirmed':
            score += 10
            details.append('启动确认')
        elif stage == 'golden_cross':
            details.append('金叉候选')
        
        # 判断是否追高
        change_5d = stock_data.get('change_5d', 0)
        if change_5d > 20:
            score -= 20
            details.append(f'5日涨{change_5d:.1f}%，追高风险')
        elif change_5d > 10:
            score -= 10
            details.append(f'5日涨{change_5d:.1f}%，注意回调')
        elif change_5d < 0:
            score += 10
            details.append('近期回调，可能是买点')
        
        # RSI判断
        rsi = stock_data.get('rsi', 50)
        if rsi > 80:
            score -= 15
            details.append(f'RSI={rsi:.0f}超买')
        elif rsi < 30:
            score += 10
            details.append(f'RSI={rsi:.0f}超卖')
        
        return min(100, max(0, score)), '；'.join(details) if details else '时机一般'
    
    def _generate_user_tags(self, dimension_scores: Dict, stock_data: Dict) -> List[str]:
        """生成用户友好标签"""
        tags = []
        
        for dim, (threshold, tag) in self.TAG_THRESHOLDS.items():
            if dimension_scores.get(dim, 0) >= threshold:
                tags.append(tag)
        
        # 特殊标签
        leader_type = stock_data.get('leader_type', '')
        if leader_type == 'absolute_leader':
            if '板块龙头' not in tags:
                tags.append('板块龙头')
        
        continuous_limit = stock_data.get('continuous_limit', 0)
        if continuous_limit >= 2:
            tags.append(f'{continuous_limit}连板')
        
        return tags[:6]  # 最多6个标签
    
    def _generate_rank_reason(self, scores: Dict, details: Dict, total: float) -> str:
        """生成排名理由"""
        # 找出得分最高的3个维度
        sorted_dims = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:3]
        
        dim_names = {
            'technical': '技术面',
            'leader': '龙头地位',
            'money_flow': '资金流向',
            'sector_cycle': '板块周期',
            'fundamental': '基本面',
            'sentiment': '市场情绪',
            'timing': '介入时机'
        }
        
        reasons = []
        for dim, score in sorted_dims:
            if score >= 70:
                name = dim_names.get(dim, dim)
                detail = details.get(dim, '')
                reasons.append(f'{name}({score:.0f}分): {detail}')
        
        if reasons:
            return f'综合得分{total:.1f}分。' + '；'.join(reasons)
        else:
            return f'综合得分{total:.1f}分，各维度表现均衡。'
