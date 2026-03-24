"""
fact_daily_fundamental 表的 UPSERT 工具函数
主键已改为 ts_code，每只股票只保留一条最新数据
"""

from sqlalchemy import text
from typing import Dict, Any, Optional
from datetime import date
import logging

logger = logging.getLogger(__name__)


def upsert_daily_fundamental(session, ts_code: str, data: Dict[str, Any], trade_date: Optional[date] = None):
    """
    更新或插入 fact_daily_fundamental 数据
    
    Args:
        session: SQLAlchemy session
        ts_code: 股票代码（Tushare格式，如 600000.SH）
        data: 要更新的字段字典，如 {'roe_ttm': 15.5, 'pe_ttm': 20.0}
        trade_date: 交易日期，默认为今天
    """
    if not ts_code or not data:
        return False
    
    if trade_date is None:
        trade_date = date.today()
    
    # 构建字段列表
    fields = ['ts_code', 'trade_date'] + list(data.keys())
    values = [':ts_code', ':trade_date'] + [f":{k}" for k in data.keys()]
    
    # 构建 UPDATE SET 子句（排除主键）
    update_set = ', '.join([f"{k} = EXCLUDED.{k}" for k in ['trade_date'] + list(data.keys())])
    
    sql = f"""
        INSERT INTO fact_daily_fundamental ({', '.join(fields)})
        VALUES ({', '.join(values)})
        ON CONFLICT (ts_code) 
        DO UPDATE SET {update_set}
    """
    
    params = {'ts_code': ts_code, 'trade_date': trade_date, **data}
    
    try:
        session.execute(text(sql), params)
        return True
    except Exception as e:
        logger.error(f"更新 {ts_code} 失败: {e}")
        return False


def batch_upsert_daily_fundamental(session, records: list):
    """
    批量更新或插入 fact_daily_fundamental 数据
    
    Args:
        session: SQLAlchemy session
        records: 记录列表，每条记录格式为 {'ts_code': 'xxx', 'trade_date': date, 'roe_ttm': xxx, ...}
    """
    if not records:
        return 0
    
    success_count = 0
    for record in records:
        ts_code = record.pop('ts_code', None)
        trade_date = record.pop('trade_date', date.today())
        
        if ts_code and record:
            if upsert_daily_fundamental(session, ts_code, record, trade_date):
                success_count += 1
    
    return success_count

