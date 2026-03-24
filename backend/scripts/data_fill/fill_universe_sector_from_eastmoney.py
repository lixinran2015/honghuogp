#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
为股票池（S1、S2、S3）快速补充行业数据
使用东方财富免费API，直接按股票代码查询行业信息
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import logging
import time
import requests
from datetime import date
from sqlalchemy import create_engine, text
from data_warehouse.config import DATABASE_URL
from backend.services.stock.stock_universe_service import StockUniverseService

# 禁用SSL警告
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_industry_from_eastmoney(code: str, retry: int = 3) -> dict:
    """
    从东方财富API获取股票行业信息
    
    Args:
        code: 6位股票代码，如 "600104"
        retry: 重试次数
    
    Returns:
        {
            "code": "600104",
            "name": "上汽集团",
            "industry": "汽车整车",
            "concept": "沪股通;上证380"
        }
    """
    # 转换代码格式：6开头是上交所 secid=1.XXXXXX，0/3开头是深交所 secid=0.XXXXXX
    if code.startswith("6"):
        secid = f"1.{code}"
    elif code.startswith(("0", "3")):
        secid = f"0.{code}"
    else:
        return {"code": code, "name": None, "industry": None, "concept": None}
    
    # 尝试多个API地址
    urls = [
        f"http://push2.eastmoney.com/api/qt/stock/get?secid={secid}&fields=f14,f100,f152",
        f"https://push2.eastmoney.com/api/qt/stock/get?secid={secid}&fields=f14,f100,f152",
        f"http://17.push2.eastmoney.com/api/qt/stock/get?secid={secid}&fields=f14,f100,f152",
    ]
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Referer': 'http://quote.eastmoney.com/',
        'Accept': 'application/json',
        'Connection': 'keep-alive'
    }
    
    for attempt in range(retry):
        for url in urls:
            try:
                response = requests.get(url, headers=headers, timeout=10, verify=False)
                response.raise_for_status()
                json_data = response.json()
                
                # 检查返回格式
                if json_data.get("data"):
                    data = json_data.get("data", {})
                    industry = data.get("f100")
                    
                    # 如果f100为空，尝试从其他字段获取
                    if not industry:
                        # 可能返回格式不同，尝试其他字段
                        industry = data.get("industry") or data.get("hy")
                    
                    return {
                        "code": code,
                        "name": data.get("f14"),
                        "industry": industry,
                        "concept": data.get("f152")
                    }
                else:
                    # 返回格式异常，尝试下一个URL
                    continue
                    
            except requests.exceptions.RequestException as e:
                # 尝试下一个URL
                continue
            except Exception as e:
                # 尝试下一个URL
                continue
        
        # 所有URL都失败，等待后重试
        if attempt < retry - 1:
            time.sleep(0.5 * (attempt + 1))  # 指数退避
            continue
        logger.debug(f"获取 {code} 行业信息失败: 所有URL都失败")
        return {"code": code, "name": None, "industry": None, "concept": None}
    
    return {"code": code, "name": None, "industry": None, "concept": None}


def get_sector_mapping():
    """
    获取行业名称到sector_id的映射
    """
    engine = create_engine(DATABASE_URL, echo=False)
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT sector_id, name 
            FROM dim_sector 
            WHERE sector_type = 'industry'
        """))
        mapping = {row[1]: row[0] for row in result}
        return mapping


def match_industry_to_sector(industry_name: str, sector_mapping: dict) -> str:
    """
    将行业名称匹配到sector_id
    
    Args:
        industry_name: 行业名称（如"汽车整车"）
        sector_mapping: {行业名称: sector_id} 的映射
    
    Returns:
        sector_id，如果无法匹配返回None
    """
    if not industry_name:
        return None
    
    # 精确匹配
    if industry_name in sector_mapping:
        return sector_mapping[industry_name]
    
    # 模糊匹配（部分匹配）
    for sector_name, sector_id in sector_mapping.items():
        if industry_name in sector_name or sector_name in industry_name:
            return sector_id
    
    # 尝试去除常见后缀后匹配
    industry_clean = industry_name.replace('行业', '').replace('板块', '').strip()
    for sector_name, sector_id in sector_mapping.items():
        sector_clean = sector_name.replace('行业', '').replace('板块', '').strip()
        if industry_clean == sector_clean or industry_clean in sector_clean or sector_clean in industry_clean:
            return sector_id
    
    return None


def fill_universe_sector_from_eastmoney(universe_types: list = ['s1', 's2', 's3'], delay: float = 0.1):
    """
    为股票池快速补充行业数据（使用东方财富API）
    
    Args:
        universe_types: 股票池类型列表
        delay: 每次请求延迟（秒），避免请求过快
    """
    logger.info("=" * 60)
    logger.info("为股票池快速补充行业数据（使用东方财富API）")
    logger.info("=" * 60)
    
    # 获取股票池代码
    service = StockUniverseService()
    all_codes = set()
    code_to_ts_code = {}  # 6位数字 -> ts_code
    
    for universe_type in universe_types:
        codes = service.get_universe_stocks(universe_type)
        logger.info(f"{universe_type.upper()}股票池: {len(codes)} 只股票")
        
        for code in codes:
            code_str = str(code).strip()
            if len(code_str) == 6 and code_str.isdigit():
                all_codes.add(code_str)
                # 转换为ts_code格式
                if code_str.startswith('6'):
                    code_to_ts_code[code_str] = f"{code_str}.SH"
                elif code_str.startswith(('0', '3')):
                    code_to_ts_code[code_str] = f"{code_str}.SZ"
    
    logger.info(f"总共需要处理 {len(all_codes)} 只股票（去重后）")
    
    # 检查哪些股票已经有行业关联
    engine = create_engine(DATABASE_URL, echo=False)
    ts_codes_list = list(code_to_ts_code.values())
    
    with engine.connect() as conn:
        query = text("""
            SELECT DISTINCT ts_code
            FROM fact_stock_sector
            WHERE ts_code = ANY(:ts_codes)
              AND is_primary = TRUE
              AND (end_date IS NULL OR end_date > CURRENT_DATE)
        """)
        result = conn.execute(query, {'ts_codes': ts_codes_list})
        has_sector = {row[0] for row in result}
    
    # 找出需要补充的股票（6位数字格式）
    need_sector_codes = []
    for code, ts_code in code_to_ts_code.items():
        if ts_code not in has_sector:
            need_sector_codes.append(code)
    
    logger.info(f"已有行业关联: {len(has_sector)} 只")
    logger.info(f"需要补充行业关联: {len(need_sector_codes)} 只")
    
    if not need_sector_codes:
        logger.info("✅ 所有股票都有行业关联，无需补充")
        return
    
    # 获取行业映射
    sector_mapping = get_sector_mapping()
    logger.info(f"可用行业板块: {len(sector_mapping)} 个")
    
    # 准备关联数据
    stock_sector_rows = []
    today = date.today()
    success_count = 0
    failed_count = 0
    
    logger.info("")
    logger.info("开始批量获取行业数据...")
    
    # 批量获取行业信息
    for idx, code in enumerate(need_sector_codes, 1):
        if idx % 50 == 0:
            logger.info(f"  进度: {idx}/{len(need_sector_codes)} ({idx/len(need_sector_codes)*100:.1f}%)")
        
        # 从东方财富获取行业信息
        industry_info = get_industry_from_eastmoney(code)
        
        if not industry_info.get("industry"):
            failed_count += 1
            if idx <= 5:  # 前5个显示详细信息
                logger.warning(f"  ⚠️ {code} 未获取到行业信息: {industry_info}")
            time.sleep(delay)
            continue
        
        industry_name = industry_info["industry"]
        ts_code = code_to_ts_code[code]
        
        # 匹配行业到sector_id
        sector_id = match_industry_to_sector(industry_name, sector_mapping)
        
        if sector_id:
            stock_sector_rows.append({
                "ts_code": ts_code,
                "sector_id": sector_id,
                "start_date": today,
                "end_date": None,
                "is_primary": True,
            })
            success_count += 1
            if idx <= 10:  # 前10个显示详细信息
                logger.info(f"  ✅ {code}({industry_info.get('name', '')}) -> {industry_name} (sector_id: {sector_id})")
        else:
            failed_count += 1
            if idx <= 10:  # 前10个显示详细信息
                logger.warning(f"  ⚠️ {code}({industry_info.get('name', '')}) 行业 '{industry_name}' 无法匹配到板块")
                # 显示可用的行业列表（前5个）
                if idx <= 5:
                    sample_sectors = list(sector_mapping.keys())[:5]
                    logger.debug(f"    可用行业示例: {sample_sectors}")
        
        time.sleep(delay)  # 延迟，避免请求过快
    
    logger.info("")
    logger.info(f"获取完成: 成功 {success_count} 只，失败 {failed_count} 只")
    logger.info(f"准备导入 {len(stock_sector_rows)} 条股票-板块关联")
    
    # 批量入库
    if stock_sector_rows:
        import pandas as pd
        with engine.connect() as conn:
            temp_table_name = 'temp_stock_sector_import'
            
            # 删除临时表
            conn.execute(text(f"DROP TABLE IF EXISTS {temp_table_name}"))
            conn.commit()
            
            # 创建临时表
            df_stock_sector = pd.DataFrame(stock_sector_rows)
            df_stock_sector.to_sql(
                temp_table_name,
                conn,
                if_exists='append',
                index=False,
                method='multi',
                chunksize=5000
            )
            conn.commit()
            
            # 批量插入
            insert_cols = ', '.join(df_stock_sector.columns)
            select_cols_list = []
            for col in df_stock_sector.columns:
                if col == 'end_date':
                    select_cols_list.append(f"NULLIF({col}, '')::DATE")
                else:
                    select_cols_list.append(col)
            select_cols = ', '.join(select_cols_list)
            
            sql = f"""
            INSERT INTO fact_stock_sector 
            ({insert_cols})
            SELECT {select_cols}
            FROM {temp_table_name}
            ON CONFLICT (ts_code, sector_id, start_date) 
            DO NOTHING
            """
            
            conn.execute(text(sql))
            conn.commit()
            
            # 删除临时表
            conn.execute(text(f"DROP TABLE IF EXISTS {temp_table_name}"))
            conn.commit()
        
        logger.info(f"✅ 成功导入 {len(stock_sector_rows)} 条关联数据")
    else:
        logger.warning("⚠️ 没有可导入的关联数据")
    
    logger.info("=" * 60)
    logger.info("✅ 行业数据补充完成")
    logger.info("=" * 60)


if __name__ == "__main__":
    fill_universe_sector_from_eastmoney(['s1', 's2', 's3'], delay=0.1)

