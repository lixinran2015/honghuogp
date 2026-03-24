#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
补充23只缺少毛利率和PE数据的股票
使用用户提供的手动整理数据
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import logging
from datetime import date, datetime
from sqlalchemy import create_engine, text
from data_warehouse.config import DATABASE_URL

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 用户提供的数据
STOCK_DATA = [
    {"code": "600095", "name": "湘财股份", "gross_margin": 4.92, "pe": 82.46},
    {"code": "600104", "name": "上汽集团", "gross_margin": 8.56, "pe": 61.50},
    {"code": "600113", "name": "浙江东日", "gross_margin": 39.70, "pe": 165.79},
    {"code": "600118", "name": "中国卫星", "gross_margin": 9.62, "pe": 846.55},
    {"code": "600156", "name": "华升股份", "gross_margin": 3.38, "pe": -93.08},
    {"code": "600203", "name": "福日电子", "gross_margin": 7.50, "pe": -48.36},
    {"code": "600210", "name": "紫江企业", "gross_margin": 23.56, "pe": 9.54},
    {"code": "600272", "name": "开开实业", "gross_margin": 15.70, "pe": 277.26},
    {"code": "600292", "name": "远达环保", "gross_margin": 14.20, "pe": 3018.74},
    {"code": "600328", "name": "中盐化工", "gross_margin": 10.48, "pe": 86.93},
    {"code": "600343", "name": "航天动力", "gross_margin": 8.66, "pe": -48.73},
    {"code": "600372", "name": "中航机载", "gross_margin": 27.94, "pe": 71.69},
    {"code": "600391", "name": "航发科技", "gross_margin": 13.37, "pe": 202.10},
    {"code": "600403", "name": "大有能源", "gross_margin": 0.54, "pe": -15.44},
    {"code": "600408", "name": "安泰集团", "gross_margin": 0.75, "pe": -36.49},
    {"code": "600409", "name": "三友化工", "gross_margin": 12.85, "pe": 59.75},
    {"code": "600410", "name": "华胜天成", "gross_margin": 12.13, "pe": 51.24},
    {"code": "600460", "name": "士兰微", "gross_margin": 24.16, "pe": 86.34},
    {"code": "600497", "name": "驰宏锌锗", "gross_margin": 17.96, "pe": 29.69},
    {"code": "600550", "name": "保变电气", "gross_margin": 12.90, "pe": 137.66},
    {"code": "600595", "name": "中孚实业", "gross_margin": 13.48, "pe": 22.15},
    {"code": "600610", "name": "中毅达", "gross_margin": 20.10, "pe": 259.78},
    {"code": "600629", "name": "华建集团", "gross_margin": 21.81, "pe": 71.34},
]


def get_latest_trade_date():
    """获取最新的交易日期"""
    engine = create_engine(DATABASE_URL, echo=False)
    with engine.connect() as conn:
        # 从fact_daily_price获取最新日期
        result = conn.execute(text("""
            SELECT MAX(trade_date) 
            FROM fact_daily_price
        """))
        row = result.fetchone()
        if row and row[0]:
            return row[0]
        
        # 如果fact_daily_price没有数据，使用今天
        return date.today()


def fill_missing_stocks_fundamental():
    """补充23只股票的毛利率和PE数据"""
    logger.info("=" * 60)
    logger.info("补充23只股票的毛利率和PE数据")
    logger.info("=" * 60)
    
    # 获取最新交易日期
    latest_date = get_latest_trade_date()
    logger.info(f"使用交易日期: {latest_date}")
    
    engine = create_engine(DATABASE_URL, echo=False)
    
    success_count = 0
    error_count = 0
    
    with engine.connect() as conn:
        for idx, stock in enumerate(STOCK_DATA, 1):
            code = stock["code"]
            name = stock["name"]
            gross_margin = stock["gross_margin"]
            pe = stock["pe"]
            
            # 转换为ts_code格式
            if code.startswith("6"):
                ts_code = f"{code}.SH"
            else:
                ts_code = f"{code}.SZ"
            
            try:
                # 检查是否已存在该日期的数据
                check_query = text("""
                    SELECT COUNT(*) 
                    FROM fact_daily_fundamental
                    WHERE ts_code = :ts_code 
                      AND trade_date = :trade_date
                """)
                result = conn.execute(check_query, {
                    "ts_code": ts_code,
                    "trade_date": latest_date
                })
                exists = result.fetchone()[0] > 0
                
                if exists:
                    # 更新现有记录
                    update_query = text("""
                        UPDATE fact_daily_fundamental
                        SET gross_margin_ttm = :gross_margin,
                            pe_ttm = :pe,
                            source = 'manual_input',
                            updated_at = :updated_at
                        WHERE ts_code = :ts_code 
                          AND trade_date = :trade_date
                    """)
                    conn.execute(update_query, {
                        "ts_code": ts_code,
                        "trade_date": latest_date,
                        "gross_margin": gross_margin,
                        "pe": pe if pe > 0 else None,  # 负PE设为NULL
                        "updated_at": datetime.now()
                    })
                    logger.info(f"  [{idx}/23] ✅ 更新: {code}({name}) - 毛利率={gross_margin}%, PE={pe if pe > 0 else 'N/A'}")
                else:
                    # 插入新记录
                    insert_query = text("""
                        INSERT INTO fact_daily_fundamental 
                        (ts_code, trade_date, gross_margin_ttm, pe_ttm, source, created_at, updated_at)
                        VALUES 
                        (:ts_code, :trade_date, :gross_margin, :pe, 'manual_input', :created_at, :updated_at)
                    """)
                    conn.execute(insert_query, {
                        "ts_code": ts_code,
                        "trade_date": latest_date,
                        "gross_margin": gross_margin,
                        "pe": pe if pe > 0 else None,  # 负PE设为NULL
                        "created_at": datetime.now(),
                        "updated_at": datetime.now()
                    })
                    logger.info(f"  [{idx}/23] ✅ 插入: {code}({name}) - 毛利率={gross_margin}%, PE={pe if pe > 0 else 'N/A'}")
                
                conn.commit()
                success_count += 1
                
            except Exception as e:
                logger.error(f"  [{idx}/23] ❌ 失败: {code}({name}) - {e}")
                conn.rollback()
                error_count += 1
    
    logger.info("=" * 60)
    logger.info(f"✅ 补充完成: 成功 {success_count} 只，失败 {error_count} 只")
    logger.info("=" * 60)
    
    # 验证数据
    logger.info("")
    logger.info("📊 验证补充结果...")
    with engine.connect() as conn:
        for stock in STOCK_DATA:
            code = stock["code"]
            if code.startswith("6"):
                ts_code = f"{code}.SH"
            else:
                ts_code = f"{code}.SZ"
            
            query = text("""
                SELECT gross_margin_ttm, pe_ttm, trade_date
                FROM fact_daily_fundamental
                WHERE ts_code = :ts_code
                ORDER BY trade_date DESC
                LIMIT 1
            """)
            result = conn.execute(query, {"ts_code": ts_code})
            row = result.fetchone()
            
            if row:
                logger.info(f"  ✅ {code}: 毛利率={row[0]}, PE={row[1]}, 日期={row[2]}")
            else:
                logger.warning(f"  ⚠️ {code}: 未找到数据")


if __name__ == "__main__":
    fill_missing_stocks_fundamental()

