"""
启动状态管理器
整合状态机的使用，提供统一的状态管理接口
"""

import logging
from typing import Dict, Tuple
from backend.services.stock.startup_state_machine import StartupStateMachine

logger = logging.getLogger(__name__)


class StartupStateManager:
    """启动状态管理器"""
    
    def __init__(self, state_machine: StartupStateMachine = None):
        """
        初始化状态管理器
        
        Args:
            state_machine: 状态机实例（可选，默认使用静态方法）
        """
        self.state_machine = state_machine or StartupStateMachine
    
    def determine_state(
        self,
        basic_passed: bool,
        core_passed: bool,
        assist_count: int,
        risk_passed: bool,
        score: int = None,
        core_passed_count: int = 4
    ) -> Tuple[str, Dict]:
        """
        根据条件确定阶段
        
        Args:
            basic_passed: 基础条件是否通过
            core_passed: 核心条件是否通过
            assist_count: 辅助条件满足数量
            risk_passed: 风险排除是否通过
            score: 得分（可选，用于确定阶段）
            core_passed_count: 核心条件满足数量（1-4，默认4）
            
        Returns:
            Tuple[str, Dict]: (阶段名称, 阶段信息)
        """
        return StartupStateMachine.determine_stage(
            basic_passed=basic_passed,
            core_passed=core_passed,
            assist_count=assist_count,
            risk_passed=risk_passed,
            score=score or self.calculate_score(
                basic_passed=basic_passed,
                core_passed=core_passed,
                assist_count=assist_count,
                risk_passed=risk_passed,
                core_passed_count=core_passed_count
            )
        )
    
    def calculate_score(
        self,
        basic_passed: bool,
        core_passed: bool,
        assist_count: int,
        risk_passed: bool,
        core_passed_count: int = 4
    ) -> int:
        """
        计算得分
        
        Args:
            basic_passed: 基础条件是否通过
            core_passed: 核心条件是否通过
            assist_count: 辅助条件满足数量
            risk_passed: 风险排除是否通过
            core_passed_count: 核心条件满足数量（1-4，默认4）
            
        Returns:
            int: 得分
        """
        return StartupStateMachine.calculate_score(
            basic_passed=basic_passed,
            core_passed=core_passed,
            assist_count=assist_count,
            risk_passed=risk_passed,
            core_passed_count=core_passed_count
        )
    
    def can_transition(self, from_stage: str, to_stage: str) -> bool:
        """
        检查是否可以转换状态
        
        Args:
            from_stage: 当前阶段
            to_stage: 目标阶段
        
        Returns:
            bool: 是否可以转换
        """
        return StartupStateMachine.can_transition(from_stage, to_stage)
    
    def get_stage_info(self, stage: str) -> Dict:
        """
        获取阶段信息
        
        Args:
            stage: 阶段名称
        
        Returns:
            Dict: 阶段信息
        """
        return StartupStateMachine.get_stage_info(stage)
    
    def get_state_flow_diagram(self) -> str:
        """
        获取状态流转图
        
        Returns:
            str: 状态流转图文本
        """
        return StartupStateMachine.get_state_flow_diagram()

