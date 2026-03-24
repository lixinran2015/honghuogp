"""
腾讯接口获取行业板块数据服务
尝试使用腾讯API获取股票行业信息
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import logging
import requests
import time
from typing import Optional, List, Dict
import pandas as pd
from datetime import date
from sqlalchemy import create_engine, text
from data_warehouse.config import DATABASE_URL

logger = logging.getLogger(__name__)


def fetch_stock_info_from_tencent(ts_code: str) -> Optional[Dict]:
    """
    从腾讯获取股票基本信息（可能包含行业信息）
    
    Args:
        ts_code: 股票代码，如 000001.SZ
    
    Returns:
        包含股票信息的字典，如果失败返回None
    """
    # 转换代码格式：000001.SZ -> sz000001
    code, exch = ts_code.split(".")
    if exch == "SH":
        symbol = f"sh{code}"
    elif exch == "SZ":
        symbol = f"sz{code}"
    else:
        return None
    
    url = f"https://qt.gtimg.cn/q={symbol}"
    
    try:
        resp = requests.get(url, timeout=5)
        resp.raise_for_status()
        
        # 腾讯返回格式：v_sz000001="51~平安银行~000001~..."
        text = resp.text
        if not text or '=' not in text:
            return None
        
        # 解析数据
        parts = text.split('=')[1].strip().strip('"').split('~')
        if len(parts) < 3:
            return None
        
        return {
            'code': parts[2] if len(parts) > 2 else code,
            'name': parts[1] if len(parts) > 1 else '',
            'symbol': symbol,
            'ts_code': ts_code
        }
    except Exception as e:
        logger.debug(f"获取 {ts_code} 信息失败: {e}")
        return None


def fetch_industry_stocks_from_tencent(industry_name: str) -> Optional[List[str]]:
    """
    从腾讯获取行业成分股（如果接口可用）
    
    注意：腾讯可能没有直接的行业成分股接口
    这个方法作为备选方案，可能需要结合其他数据源
    
    Args:
        industry_name: 行业名称
    
    Returns:
        股票代码列表，如果失败返回None
    """
    # 腾讯可能没有直接的行业成分股接口
    # 这里先返回None，后续可以尝试其他方式
    logger.warning(f"腾讯API可能不支持直接获取行业成分股: {industry_name}")
    return None


def fill_stock_sector_from_tencent_batch(stock_codes: List[str], delay: float = 0.1) -> Dict[str, Optional[str]]:
    """
    批量从腾讯获取股票信息（用于推断行业）
    
    注意：这个方法主要用于获取股票基本信息，
    行业信息可能需要从其他数据源获取或通过映射获得
    
    Args:
        stock_codes: 股票代码列表
        delay: 每次请求延迟（秒）
    
    Returns:
        字典：{ts_code: stock_info}
    """
    results = {}
    
    for ts_code in stock_codes:
        info = fetch_stock_info_from_tencent(ts_code)
        results[ts_code] = info
        time.sleep(delay)
        
        if len(results) % 100 == 0:
            logger.info(f"已处理 {len(results)}/{len(stock_codes)} 只股票")
    
    return results


def fill_stock_sector_using_existing_data():
    """
    使用现有数据仓库中的数据来补全股票-板块关联
    这是一个备选方案：如果无法从外部API获取，可以使用已有的股票基本信息
    
    思路：
    1. 从 dim_stock 获取所有股票
    2. 如果有行业字段，直接使用
    3. 如果没有，尝试从其他表推断
    """
    engine = create_engine(DATABASE_URL, echo=False)
    
    logger.info("="*60)
    logger.info("使用现有数据补全股票-板块关联")
    logger.info("="*60)
    
    with engine.connect() as conn:
        # 检查 dim_stock 表是否有行业字段
        result = conn.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'dim_stock'
        """))
        columns = [row[0] for row in result]
        logger.info(f"dim_stock 表的列: {columns}")
        
        # 检查是否有行业相关字段
        industry_columns = [col for col in columns if 'industry' in col.lower() or 'sector' in col.lower() or '行业' in col]
        
        if industry_columns:
            logger.info(f"找到行业字段: {industry_columns}")
            # 可以使用这些字段来补全关联
        else:
            logger.warning("dim_stock 表中没有找到行业字段")
            logger.info("建议：从其他数据源获取行业信息后，更新 dim_stock 表或直接写入 fact_stock_sector")
    
    logger.info("="*60)


if __name__ == "__main__":
    # 测试
    logging.basicConfig(level=logging.INFO)
    
    # 测试获取单只股票信息
    print("测试获取股票信息...")
    info = fetch_stock_info_from_tencent("000001.SZ")
    print(f"结果: {info}")
    
    # 测试使用现有数据
    fill_stock_sector_using_existing_data()

