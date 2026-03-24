"""
股票启动状态机
统一管理状态流转逻辑
"""
from typing import Dict, List, Optional, Tuple
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class StartupStage(Enum):
    """启动阶段枚举"""
    FILTERED = 'filtered'  # 已过滤（未通过基础条件）
    GOLDEN_CROSS = 'golden_cross'  # 金叉候选
    CONFIRMED = 'confirmed'  # 启动确认（有风险）
    STARTED = 'started'  # 完全启动（无风险）


class StartupStateMachine:
    """股票启动状态机"""
    
    # 状态转换规则
    STATE_TRANSITIONS = {
        StartupStage.FILTERED: {
            'next_stages': [StartupStage.GOLDEN_CROSS],
            'conditions': ['基础条件通过（含金叉）']
        },
        StartupStage.GOLDEN_CROSS: {
            'next_stages': [StartupStage.CONFIRMED, StartupStage.STARTED],
            'conditions': ['核心条件4/4通过 → confirmed', '核心+辅助+风险全部通过 → started']
        },
        StartupStage.CONFIRMED: {
            'next_stages': [StartupStage.STARTED],
            'conditions': ['风险排除通过 → started']
        },
        StartupStage.STARTED: {
            'next_stages': [],  # 终态
            'conditions': []
        }
    }
    
    @staticmethod
    def get_stage_info(stage: str) -> Dict:
        """
        获取阶段信息
        
        Args:
            stage: 阶段名称
            
        Returns:
            Dict: 阶段信息
        """
        stage_enum = StartupStage(stage) if isinstance(stage, str) else stage
        
        info = {
            'name': stage_enum.value,
            'label': {
                StartupStage.FILTERED: '已过滤',
                StartupStage.GOLDEN_CROSS: '金叉候选',
                StartupStage.CONFIRMED: '启动确认',
                StartupStage.STARTED: '完全启动'
            }.get(stage_enum, stage_enum.value),
            'score_range': {
                StartupStage.FILTERED: (0, 0),
                StartupStage.GOLDEN_CROSS: (20, 50),  # 20分基础 + 最多30分核心条件（部分核心条件满足）
                StartupStage.CONFIRMED: (60, 90),  # ✅ 修改：核心确认阶段：60-90分（20金叉 + 40核心确认 + 10-30辅助确认）
                StartupStage.STARTED: (70, 100)
            }.get(stage_enum, (0, 0)),
            'description': {
                StartupStage.FILTERED: '未通过基础条件筛选',
                StartupStage.GOLDEN_CROSS: '5日金叉10日，等待核心条件满足',
                StartupStage.CONFIRMED: '核心条件已满足，但有风险提示',
                StartupStage.STARTED: '所有条件满足，无风险，可进入推荐池'
            }.get(stage_enum, '未知阶段')
        }
        
        # 添加转换信息
        transitions = StartupStateMachine.STATE_TRANSITIONS.get(stage_enum, {})
        info['next_stages'] = [s.value for s in transitions.get('next_stages', [])]
        info['transition_conditions'] = transitions.get('conditions', [])
        
        return info
    
    @staticmethod
    def can_transition(from_stage: str, to_stage: str) -> bool:
        """
        检查是否可以转换状态
        
        Args:
            from_stage: 当前阶段
            to_stage: 目标阶段
            
        Returns:
            bool: 是否可以转换
        """
        try:
            from_enum = StartupStage(from_stage) if isinstance(from_stage, str) else from_stage
            to_enum = StartupStage(to_stage) if isinstance(to_stage, str) else to_stage
            
            transitions = StartupStateMachine.STATE_TRANSITIONS.get(from_enum, {})
            next_stages = transitions.get('next_stages', [])
            
            return to_enum in next_stages
        except (ValueError, AttributeError):
            return False
    
    @staticmethod
    def determine_stage(
        basic_passed: bool,
        core_passed: bool,
        assist_count: int,
        risk_passed: bool,
        score: int
    ) -> Tuple[str, Dict]:
        """
        根据条件确定阶段
        
        Args:
            basic_passed: 基础条件是否通过
            core_passed: 核心条件是否通过
            assist_count: 辅助条件满足数量
            risk_passed: 风险排除是否通过
            score: 得分
            
        Returns:
            Tuple[str, Dict]: (阶段名称, 阶段信息)
        """
        if not basic_passed:
            stage = StartupStage.FILTERED
        elif not core_passed:
            stage = StartupStage.GOLDEN_CROSS
        elif not risk_passed:
            stage = StartupStage.CONFIRMED
        else:
            stage = StartupStage.STARTED
        
        stage_info = StartupStateMachine.get_stage_info(stage)
        
        return stage.value, stage_info
    
    @staticmethod
    def calculate_score(
        basic_passed: bool,
        core_passed: bool,
        assist_count: int,
        risk_passed: bool,
        core_passed_count: int = 4  # ✅ 修改：核心条件现在是4个（默认4个全满足）
    ) -> int:
        """
        计算得分
        
        得分规则：
        - 基础条件（金叉）：20分
        - 核心条件：每个条件10分，共40分（4个条件全满足）
        - 辅助确认：每个条件10分，共3个条件，最多30分
          * MACD金叉（DIF上穿DEA）：10分
          * KDJ金叉（J值50-70）：10分
          * 大单净流入（占比≥5%）：10分
        - 风险排除：通过则进入完全启动阶段
        
        得分计算：
        - 核心确认阶段（核心全满足但辅助不足）：20（金叉）+ 40（核心确认）= 60分
        - 金叉(20) + 核心确认(40) + 辅助确认(10-30) = 70-90分
          * 1个辅助条件：20 + 40 + 10 = 70分
          * 2个辅助条件：20 + 40 + 20 = 80分
          * 3个辅助条件：20 + 40 + 30 = 90分
        - 风险排除未通过：返回金叉+核心确认+辅助确认得分（70-90分）
        - 完全启动：70分基础 + 每个辅助信号10分（最多100分）
        
        Args:
            basic_passed: 基础条件是否通过
            core_passed: 核心条件是否全部通过（4/4）
            assist_count: 辅助条件满足数量
            risk_passed: 风险排除是否通过
            core_passed_count: 核心条件满足数量（1-4，默认4）
            
        Returns:
            int: 得分
        """
        if not basic_passed:
            return 0
        
        # 基础分：金叉候选 20分
        base_score = 20
        
        # 核心条件得分：每个条件10分，共40分（4个条件全满足）
        core_score = min(core_passed_count, 4) * 10
        
        if not core_passed:
            # 核心条件未全部通过：基础分 + 核心条件得分
            return base_score + core_score
        
        # 核心条件全部通过（40分），进入核心确认阶段
        # 核心确认阶段得分：60分（20金叉 + 40核心确认）
        
        if assist_count < 1:
            # 核心通过但辅助不足：金叉(20) + 核心确认(40) = 60分
            return base_score + 40
        
        # 辅助确认加分：每个条件10分，共3个条件，最多30分
        # 辅助确认条件：1. MACD金叉 2. KDJ金叉(J值50-70) 3. 大单净流入≥5%
        assist_score = min(assist_count, 3) * 10  # 最多3个条件，每个10分
        
        # 总得分 = 金叉(20) + 核心确认(40) + 辅助确认(10-30) = 70-90分
        # 1个辅助条件：20 + 40 + 10 = 70分
        # 2个辅助条件：20 + 40 + 20 = 80分
        # 3个辅助条件：20 + 40 + 30 = 90分
        confirmed_with_assist_score = base_score + 40 + assist_score
        
        if not risk_passed:
            # 核心+辅助通过但有风险：返回金叉+核心确认+辅助确认得分（70-90分）
            return confirmed_with_assist_score
        
        # 所有条件满足：70分基础 + 每个辅助信号10分（最多100分）
        # 70分基础 = 20（金叉）+ 40（核心确认）+ 10（风险排除通过的基础分）
        return min(70 + assist_count * 10, 100)
    
    @staticmethod
    def get_state_flow_diagram() -> str:
        """
        获取状态流转图（文本格式）
        
        Returns:
            str: 状态流转图
        """
        diagram = """
股票启动状态流转图
==================

[扫描/筛选]
    ↓
[基础条件检查]
    ├─ 未通过 → [已过滤] (stage='filtered', score=0)
    └─ 通过 → [金叉检查]
                ├─ 未金叉 → [已过滤] (stage='filtered', score=0)
                └─ 已金叉 → [金叉候选] (stage='golden_cross', score=20)
                            ↓
                            [核心条件检查] (4个条件：突破90日高点、量能放大、均线多头排列、近6个交易日有涨停)
                            ├─ 满足3/4 → [金叉候选 + 待监控] (is_watching=True)
                            ├─ 未通过 → [金叉候选] (stage='golden_cross', score=20)
                            └─ 通过 → [辅助条件检查] (至少1个，共3个条件，每个条件10分)
                                        ├─ 未通过 → [核心确认] (stage='confirmed', score=60)
                                        └─ 通过 → [风险排除检查]
                                                    ├─ 有风险 → [启动确认] (stage='confirmed', score=70-90)
                                                    └─ 无风险 → [完全启动] (stage='started', score=70-100)
                                                                ↓
                                                                [推荐池] (is_recommended=True)

状态说明：
----------
1. filtered (已过滤)
   - 得分：0分
   - 条件：未通过基础条件或金叉检查
   - 说明：不符合筛选条件，不进入候选池

2. golden_cross (金叉候选)
   - 得分：20分
   - 条件：5日金叉10日 + 基础条件通过
   - 说明：已金叉，等待核心条件满足
   - 特殊：如果满足3/4核心条件，自动加入待监控池

3. confirmed (启动确认/核心确认)
   - 得分：60-90分
   - 条件：核心条件通过，但辅助不足或有风险
   - 说明：可适当关注，注意风险提示
   - 60分：金叉(20) + 核心确认(40)，但辅助不足（0个辅助条件）- 核心确认阶段
   - 70-90分：金叉(20) + 核心确认(40) + 辅助确认(10-30) - 启动确认阶段
     * 70分 = 20（金叉）+ 40（核心确认）+ 10（1个辅助条件）
     * 80分 = 20（金叉）+ 40（核心确认）+ 20（2个辅助条件）
     * 90分 = 20（金叉）+ 40（核心确认）+ 30（3个辅助条件）
   - 辅助确认条件（共3个）：
     * MACD金叉（DIF上穿DEA）：10分
     * KDJ金叉（J值50-70）：10分
     * 大单净流入（占比≥5%）：10分

4. started (完全启动)
   - 得分：70-100分
   - 条件：所有条件满足（基础+核心+辅助+风险排除）
   - 说明：无风险，自动进入推荐池
   - 得分计算：60分基础 + 每个辅助信号10分（最多100分）

状态转换规则：
--------------
- filtered → golden_cross: 基础条件通过（含金叉）
- golden_cross → confirmed: 核心条件4/4通过
- golden_cross → started: 核心+辅助+风险全部通过（跳过confirmed）
- confirmed → started: 风险排除通过

注意事项：
----------
1. 状态只能向前转换，不能回退
2. 同一只股票在不同日期可能有不同状态
3. 待监控池（is_watching=True）是 golden_cross 阶段的特殊标记
4. 推荐池（is_recommended=True）是 started 阶段的后续处理
"""
        return diagram.strip()

