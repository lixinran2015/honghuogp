"""
股票启动API - 公共辅助函数
"""

import logging
import math
import numpy as np
from typing import Dict, List, Any

logger = logging.getLogger(__name__)


def clean_nan_values(data: dict) -> dict:
    """
    清理字典中的NaN值
    
    Args:
        data: 字典数据
    
    Returns:
        清理后的字典
    """
    if not isinstance(data, dict):
        return data
    
    cleaned = {}
    for key, value in data.items():
        if isinstance(value, (int, float)):
            if math.isnan(value) or math.isinf(value):
                cleaned[key] = 0
            else:
                cleaned[key] = value
        elif isinstance(value, dict):
            cleaned[key] = clean_nan_values(value)
        elif isinstance(value, list):
            cleaned[key] = [clean_nan_values(item) if isinstance(item, dict) else item for item in value]
        else:
            cleaned[key] = value
    
    return cleaned


def to_native(value: Any) -> Any:
    """
    转换numpy类型为Python原生类型
    
    Args:
        value: 待转换的值
    
    Returns:
        转换后的值
    """
    if isinstance(value, (np.bool_, np.generic)):
        return value.item()
    elif isinstance(value, np.ndarray):
        return value.tolist()
    elif isinstance(value, dict):
        return {k: to_native(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [to_native(item) for item in value]
    return value


async def get_universe_stocks(universe: str) -> List[str]:
    """
    获取指定股票池的股票列表
    
    Args:
        universe: 股票池类型（mainboard/base/all）
    
    Returns:
        股票代码列表
    """
    try:
        from data_warehouse.models.orm_classes import DimStockUniverse, DimStock
        from data_warehouse.service.warehouse_service import WarehouseService
        
        ws = WarehouseService()
        session = ws.get_session()
        
        try:
            if universe == 'all':
                # 全市场（排除退市、ST）
                stocks = session.query(DimStock.ts_code).filter(
                    DimStock.list_status == '上市',
                    ~DimStock.name.like('%ST%'),
                    ~DimStock.name.like('%退%')
                ).all()
                return [s[0] for s in stocks]
            
            elif universe in ['mainboard', 'base']:
                # 从股票池表查询
                stocks = session.query(DimStockUniverse.ts_code).filter(
                    DimStockUniverse.universe_type == universe,
                    DimStockUniverse.is_active == True
                ).distinct().all()
                return [s[0] for s in stocks]
            
            else:
                logger.warning(f"未知股票池类型: {universe}")
                return []
                
        finally:
            session.close()
        
    except Exception as e:
        logger.error(f"获取股票池失败: {e}", exc_info=True)
        return []

