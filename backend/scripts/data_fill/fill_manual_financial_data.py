#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
补全手动提供的财务数据
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from data_warehouse.service.warehouse_service import WarehouseService
from sqlalchemy import text
from datetime import date
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 表1：6只股票的增长和现金流数据
TABLE1_DATA = {
    '000063.SZ': {  # 中兴通讯
        'revenue_growth_yoy': 3.0,
        'profit_growth_yoy': 15.0,
        'gross_margin_ttm': 36.0,
        'op_cf_ttm': 140.0 * 100000000,  # 转换为元
    },
    '000568.SZ': {  # 泸州老窖
        'revenue_growth_yoy': 19.0,
        'profit_growth_yoy': 22.0,
        'gross_margin_ttm': 91.0,
        'op_cf_ttm': 90.0 * 100000000,
    },
    '000625.SZ': {  # 长安汽车
        'revenue_growth_yoy': 23.0,
        'profit_growth_yoy': 32.0,
        'gross_margin_ttm': 19.0,
        'op_cf_ttm': 270.0 * 100000000,
    },
    '000858.SZ': {  # 五粮液
        'revenue_growth_yoy': 10.0,
        'profit_growth_yoy': 11.0,
        'gross_margin_ttm': 92.0,
        'op_cf_ttm': 170.0 * 100000000,
    },
    '002007.SZ': {  # 华兰生物
        'revenue_growth_yoy': 8.0,
        'profit_growth_yoy': 9.0,
        'gross_margin_ttm': 63.0,
        'op_cf_ttm': 23.0 * 100000000,
    },
    '002241.SZ': {  # 歌尔股份
        'revenue_growth_yoy': 6.0,
        'profit_growth_yoy': 50.0,
        'gross_margin_ttm': 14.0,
        'op_cf_ttm': 65.0 * 100000000,
    },
}

# 表2：15只金融和科创板股票的核心财务指标
TABLE2_DATA = {
    # 银行（3）
    '601288.SH': {  # 农业银行
        'roe_ttm': 11.2,
        'net_margin_ttm': 32.8,
        'gross_margin_ttm': None,  # 银行无毛利率
        'op_cf_ttm': 6000.0 * 100000000,  # >6000亿，取6000
        'debt_ratio': 0.92,
    },
    '601398.SH': {  # 工商银行
        'roe_ttm': 11.6,
        'net_margin_ttm': 34.0,
        'gross_margin_ttm': None,
        'op_cf_ttm': 7000.0 * 100000000,  # >7000亿，取7000
        'debt_ratio': 0.92,
    },
    '601939.SH': {  # 建设银行
        'roe_ttm': 12.0,
        'net_margin_ttm': 33.6,
        'gross_margin_ttm': None,
        'op_cf_ttm': 6500.0 * 100000000,  # >6500亿，取6500
        'debt_ratio': 0.91,
    },
    # 证券（2）
    '601211.SH': {  # 国泰君安
        'roe_ttm': 6.5,
        'net_margin_ttm': 26.0,
        'gross_margin_ttm': None,  # 金融类无毛利率
        'op_cf_ttm': 450.0 * 100000000,
        'debt_ratio': 0.79,
    },
    '601688.SH': {  # 华泰证券
        'roe_ttm': 7.0,
        'net_margin_ttm': 25.0,
        'gross_margin_ttm': None,
        'op_cf_ttm': 410.0 * 100000000,
        'debt_ratio': 0.77,
    },
    # 保险（3）
    '601318.SH': {  # 中国平安
        'roe_ttm': 10.8,
        'net_margin_ttm': 9.5,
        'gross_margin_ttm': None,
        'op_cf_ttm': 850.0 * 100000000,
        'debt_ratio': 0.89,
    },
    '601628.SH': {  # 中国人寿
        'roe_ttm': 8.2,
        'net_margin_ttm': 8.0,
        'gross_margin_ttm': None,
        'op_cf_ttm': 780.0 * 100000000,
        'debt_ratio': 0.91,
    },
    '601601.SH': {  # 中国太保
        'roe_ttm': 7.0,
        'net_margin_ttm': 6.5,
        'gross_margin_ttm': None,
        'op_cf_ttm': 650.0 * 100000000,
        'debt_ratio': 0.89,
    },
    # 其他行业（9）
    '600887.SH': {  # 伊利股份
        'roe_ttm': 23.0,
        'net_margin_ttm': 8.2,
        'gross_margin_ttm': 35.0,
        'op_cf_ttm': 160.0 * 100000000,
        'debt_ratio': 0.61,
    },
    '601012.SH': {  # 隆基绿能
        'roe_ttm': 9.5,
        'net_margin_ttm': 7.2,
        'gross_margin_ttm': 19.0,
        'op_cf_ttm': 230.0 * 100000000,
        'debt_ratio': 0.66,
    },
    '601088.SH': {  # 中国神华
        'roe_ttm': 17.0,
        'net_margin_ttm': 25.0,
        'gross_margin_ttm': 38.0,
        'op_cf_ttm': 1700.0 * 100000000,
        'debt_ratio': 0.54,
    },
    '601225.SH': {  # 陕西煤业
        'roe_ttm': 22.0,
        'net_margin_ttm': 28.0,
        'gross_margin_ttm': 40.0,
        'op_cf_ttm': 900.0 * 100000000,
        'debt_ratio': 0.46,
    },
    '603501.SH': {  # 韦尔股份
        'roe_ttm': 5.0,
        'net_margin_ttm': 4.2,
        'gross_margin_ttm': 17.0,
        'op_cf_ttm': 30.0 * 100000000,
        'debt_ratio': 0.34,
    },
    '688111.SH': {  # 金山办公
        'roe_ttm': 18.0,
        'net_margin_ttm': 31.0,
        'gross_margin_ttm': 88.0,
        'op_cf_ttm': 37.0 * 100000000,
        'debt_ratio': 0.45,
    },
    '688981.SH': {  # 中芯国际
        'roe_ttm': 7.0,
        'net_margin_ttm': 12.0,
        'gross_margin_ttm': 27.0,
        'op_cf_ttm': 320.0 * 100000000,
        'debt_ratio': 0.44,
    },
    '600519.SH': {  # 贵州茅台
        'roe_ttm': 31.0,
        'net_margin_ttm': 52.0,
        'gross_margin_ttm': 91.0,
        'op_cf_ttm': 640.0 * 100000000,
        'debt_ratio': 0.41,
    },
    '002475.SZ': {  # 立讯精密
        'roe_ttm': 15.0,
        'net_margin_ttm': 6.8,
        'gross_margin_ttm': 14.0,
        'op_cf_ttm': 200.0 * 100000000,
        'debt_ratio': 0.63,
    },
}

def fill_manual_data():
    """补全手动提供的财务数据"""
    wh_service = WarehouseService()
    session = wh_service.get_session()
    
    try:
        # 获取最新交易日期
        latest_date_query = text('''
            SELECT MAX(trade_date) FROM fact_daily_fundamental
            LIMIT 1
        ''')
        latest_date_result = session.execute(latest_date_query).fetchone()
        trade_date = latest_date_result[0] if latest_date_result and latest_date_result[0] else date.today()
        
        logger.info(f"使用交易日期: {trade_date}")
        logger.info(f"表1数据: {len(TABLE1_DATA)} 只股票")
        logger.info(f"表2数据: {len(TABLE2_DATA)} 只股票\n")
        
        success_count = 0
        
        # 合并所有数据
        all_data = {**TABLE1_DATA, **TABLE2_DATA}
        
        for idx, (ts_code_full, data) in enumerate(sorted(all_data.items()), 1):
            # 转换ts_code格式：从 600519.SH 转换为 600519
            ts_code = ts_code_full.split('.')[0]
            logger.info(f"[{idx}/{len(all_data)}] 处理 {ts_code_full} -> {ts_code}")
            
            # 检查记录是否存在
            check_query = text('''
                SELECT ts_code FROM fact_daily_fundamental
                WHERE ts_code = :ts_code AND trade_date = :trade_date
            ''')
            exists = session.execute(check_query, {
                'ts_code': ts_code,
                'trade_date': trade_date
            }).fetchone()
            
            # 准备更新字段
            update_fields = []
            update_values = {}
            
            # 表1字段
            if 'revenue_growth_yoy' in data and data['revenue_growth_yoy'] is not None:
                update_fields.append('revenue_growth_yoy = :revenue_growth_yoy')
                update_values['revenue_growth_yoy'] = data['revenue_growth_yoy']
                logger.info(f"  ✅ 营收增长: {data['revenue_growth_yoy']:.1f}%")
            
            if 'profit_growth_yoy' in data and data['profit_growth_yoy'] is not None:
                update_fields.append('profit_growth_yoy = :profit_growth_yoy')
                update_values['profit_growth_yoy'] = data['profit_growth_yoy']
                logger.info(f"  ✅ 利润增长: {data['profit_growth_yoy']:.1f}%")
            
            # 表2字段
            if 'roe_ttm' in data and data['roe_ttm'] is not None:
                update_fields.append('roe_ttm = :roe_ttm')
                update_values['roe_ttm'] = data['roe_ttm']
                logger.info(f"  ✅ ROE: {data['roe_ttm']:.1f}%")
            
            if 'net_margin_ttm' in data and data['net_margin_ttm'] is not None:
                update_fields.append('net_margin_ttm = :net_margin_ttm')
                update_values['net_margin_ttm'] = data['net_margin_ttm']
                logger.info(f"  ✅ 净利率: {data['net_margin_ttm']:.1f}%")
            
            if 'gross_margin_ttm' in data and data['gross_margin_ttm'] is not None:
                update_fields.append('gross_margin_ttm = :gross_margin_ttm')
                update_values['gross_margin_ttm'] = data['gross_margin_ttm']
                logger.info(f"  ✅ 毛利率: {data['gross_margin_ttm']:.1f}%")
            
            if 'op_cf_ttm' in data and data['op_cf_ttm'] is not None:
                update_fields.append('op_cf_ttm = :op_cf_ttm')
                update_values['op_cf_ttm'] = data['op_cf_ttm']
                logger.info(f"  ✅ 经营现金流: {data['op_cf_ttm']/100000000:.0f} 亿元")
            
            if 'debt_ratio' in data and data['debt_ratio'] is not None:
                update_fields.append('debt_ratio = :debt_ratio')
                update_values['debt_ratio'] = data['debt_ratio']
                logger.info(f"  ✅ 负债率: {data['debt_ratio']*100:.1f}%")
            
            # 更新或插入（使用 UPSERT，主键为 ts_code）
            if update_fields:
                # 提取字段名（去掉 ' = :field_name' 部分）
                field_names = [field.split(' = :')[0] for field in update_fields]
                
                # 构建 UPSERT SQL
                insert_fields = ['ts_code', 'trade_date'] + field_names
                insert_values = [':ts_code', ':trade_date'] + [f":{field}" for field in field_names]
                update_set = ', '.join([f"{f} = EXCLUDED.{f}" for f in ['trade_date'] + field_names])
                
                upsert_sql = f"""
                    INSERT INTO fact_daily_fundamental ({', '.join(insert_fields)})
                    VALUES ({', '.join(insert_values)})
                    ON CONFLICT (ts_code) 
                    DO UPDATE SET {update_set}
                """
                update_values['ts_code'] = ts_code
                update_values['trade_date'] = trade_date
                session.execute(text(upsert_sql), update_values)
                
                session.commit()
                logger.info(f"  ✅ 数据库更新成功")
                success_count += 1
            else:
                logger.warning(f"  ⚠️ 无数据可更新")
        
        logger.info("\n" + "=" * 80)
        logger.info(f"✅ 补全完成: 成功 {success_count}/{len(all_data)} 只")
        logger.info("=" * 80)
        
    except Exception as e:
        logger.error(f"❌ 补全失败: {e}", exc_info=True)
    finally:
        session.close()


if __name__ == "__main__":
    logger.info("=" * 80)
    logger.info("补全手动提供的财务数据")
    logger.info("=" * 80)
    fill_manual_data()

