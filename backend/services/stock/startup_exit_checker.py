"""
股票启动退出检查服务
检查已启动股票是否满足退出条件（破20日线：收盘价 < MA20）
"""
import logging
from datetime import date
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)


class StartupExitChecker:
    """股票启动退出检查服务"""
    
    def __init__(self, warehouse_service):
        """
        初始化退出检查服务
        
        Args:
            warehouse_service: 数据仓库服务实例
        """
        self.ws = warehouse_service
    
    def check_below_ma20(self, stock_data: Dict) -> bool:
        """
        检查是否破20日线
        
        破20日线条件：收盘价 < MA20
        
        Args:
            stock_data: 股票数据字典，包含 close, ma20
        
        Returns:
            bool: 是否破20日线
        """
        close = stock_data.get('close') or 0
        ma20 = stock_data.get('ma20') or 0
        
        # 检查数据有效性
        if not close or not ma20:
            return False
        
        return float(close) < float(ma20)
    
    def check_exit_conditions(self, ts_code: str, stock_data: Dict, check_date: date) -> Tuple[bool, Optional[str]]:
        """
        检查已启动股票是否满足退出条件
        
        Args:
            ts_code: 股票代码
            stock_data: 股票数据字典
            check_date: 检查日期
        
        Returns:
            Tuple[bool, Optional[str]]: (是否满足退出条件, 退出原因)
        """
        try:
            # 检查是否破20日线
            if self.check_below_ma20(stock_data):
                close = stock_data.get('close', 0)
                ma20 = stock_data.get('ma20', 0)
                exit_reason = f'破20日线（收盘价{close:.2f} < MA20={ma20:.2f}）'
                logger.info(f"  ⚠️ {ts_code} 满足退出条件: {exit_reason}")
                return True, exit_reason
            
            return False, None
            
        except Exception as e:
            logger.error(f"检查 {ts_code} 退出条件失败: {e}", exc_info=True)
            return False, None
    
    def mark_as_exited(self, candidate, exit_date: date, exit_reason: str):
        """
        标记股票为已退出
        
        Args:
            candidate: 候选股票对象（已与session关联）
            exit_date: 退出日期
            exit_reason: 退出原因
        """
        try:
            candidate.is_exited = True
            candidate.exit_date = exit_date
            candidate.exit_reason = exit_reason
            
            logger.info(f"  ✅ {candidate.ts_code} 已标记为退出: {exit_reason}, 退出日期: {exit_date}")
            
        except Exception as e:
            logger.error(f"标记 {candidate.ts_code} 为退出失败: {e}", exc_info=True)
