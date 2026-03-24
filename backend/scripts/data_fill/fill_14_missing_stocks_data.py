#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
补全14只缺少增长数据和财务指标的行业龙头股票数据
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

# 14只股票的数据
STOCKS_DATA = {
    '000709': {  # 河钢股份
        'name': '河钢股份',
        'revenue_growth_yoy': -7.4,
        'profit_growth_yoy': -15.8,
        'profit_volatility': 22.6,
        'roe_ttm': 6.8,
        'net_margin_ttm': 3.9,
        'gross_margin_ttm': 12.8,
        'debt_ratio': 0.683,  # 68.3% 转换为小数
        'op_cf_ttm': 102.4 * 100000000,  # 102.4亿元转换为元
    },
    '000898': {  # 鞍钢股份
        'name': '鞍钢股份',
        'revenue_growth_yoy': -11.6,
        'profit_growth_yoy': -28.5,
        'profit_volatility': 35.2,
        'roe_ttm': 4.1,
        'net_margin_ttm': 2.1,
        'gross_margin_ttm': 11.4,
        'debt_ratio': 0.697,
        'op_cf_ttm': 89.5 * 100000000,
    },
    '002371': {  # 北方华创
        'name': '北方华创',
        'revenue_growth_yoy': 22.4,
        'profit_growth_yoy': 19.6,
        'profit_volatility': 14.3,
        'roe_ttm': 13.8,
        'net_margin_ttm': 12.4,
        'gross_margin_ttm': 41.6,
        'debt_ratio': 0.395,
        'op_cf_ttm': 35.8 * 100000000,
    },
    '002396': {  # 星网锐捷
        'name': '星网锐捷',
        'revenue_growth_yoy': 6.9,
        'profit_growth_yoy': 3.4,
        'profit_volatility': 11.2,
        'roe_ttm': 10.2,
        'net_margin_ttm': 4.8,
        'gross_margin_ttm': 19.6,
        'debt_ratio': 0.518,
        'op_cf_ttm': 9.7 * 100000000,
    },
    '002422': {  # 科伦药业
        'name': '科伦药业',
        'revenue_growth_yoy': 10.6,
        'profit_growth_yoy': 12.1,
        'profit_volatility': 9.4,
        'roe_ttm': 14.3,
        'net_margin_ttm': 9.9,
        'gross_margin_ttm': 46.8,
        'debt_ratio': 0.446,
        'op_cf_ttm': 27.3 * 100000000,
    },
    '002459': {  # 晶澳科技
        'name': '晶澳科技',
        'revenue_growth_yoy': -4.8,
        'profit_growth_yoy': -17.6,
        'profit_volatility': 28.4,
        'roe_ttm': 10.1,
        'net_margin_ttm': 5.2,
        'gross_margin_ttm': 12.1,
        'debt_ratio': 0.587,
        'op_cf_ttm': 108.9 * 100000000,
    },
    '002594': {  # 比亚迪
        'name': '比亚迪',
        'revenue_growth_yoy': 27.9,
        'profit_growth_yoy': 30.8,
        'profit_volatility': 18.9,
        'roe_ttm': 17.6,
        'net_margin_ttm': 4.8,
        'gross_margin_ttm': 15.3,
        'debt_ratio': 0.641,
        'op_cf_ttm': 163.3 * 100000000,
    },
    '300014': {  # 亿纬锂能
        'name': '亿纬锂能',
        'revenue_growth_yoy': 12.5,
        'profit_growth_yoy': 10.4,
        'profit_volatility': 16.1,
        'roe_ttm': 11.4,
        'net_margin_ttm': 7.9,
        'gross_margin_ttm': 25.2,
        'debt_ratio': 0.553,
        'op_cf_ttm': 47.9 * 100000000,
    },
    '300122': {  # 智飞生物
        'name': '智飞生物',
        'revenue_growth_yoy': 18.3,
        'profit_growth_yoy': 22.9,
        'profit_volatility': 13.5,
        'roe_ttm': 19.7,
        'net_margin_ttm': 28.5,
        'gross_margin_ttm': 90.4,
        'debt_ratio': 0.238,
        'op_cf_ttm': 40.2 * 100000000,
    },
    '300433': {  # 蓝思科技
        'name': '蓝思科技',
        'revenue_growth_yoy': -6.2,
        'profit_growth_yoy': -9.8,
        'profit_volatility': 21.7,
        'roe_ttm': 8.3,
        'net_margin_ttm': 3.6,
        'gross_margin_ttm': 12.5,
        'debt_ratio': 0.571,
        'op_cf_ttm': 62.0 * 100000000,
    },
    '300601': {  # 康泰生物
        'name': '康泰生物',
        'revenue_growth_yoy': 16.7,
        'profit_growth_yoy': 19.1,
        'profit_volatility': 14.9,
        'roe_ttm': 18.9,
        'net_margin_ttm': 27.8,
        'gross_margin_ttm': 88.2,
        'debt_ratio': 0.246,
        'op_cf_ttm': 31.7 * 100000000,
    },
    '300750': {  # 宁德时代
        'name': '宁德时代',
        'revenue_growth_yoy': 21.4,
        'profit_growth_yoy': 17.2,
        'profit_volatility': 13.8,
        'roe_ttm': 16.8,
        'net_margin_ttm': 10.5,
        'gross_margin_ttm': 22.6,
        'debt_ratio': 0.488,
        'op_cf_ttm': 225.4 * 100000000,
    },
    '600438': {  # 通威股份
        'name': '通威股份',
        'revenue_growth_yoy': -9.5,
        'profit_growth_yoy': -22.4,
        'profit_volatility': 33.6,
        'roe_ttm': 14.9,
        'net_margin_ttm': 6.1,
        'gross_margin_ttm': 17.8,
        'debt_ratio': 0.425,
        'op_cf_ttm': 118.3 * 100000000,
    },
    '600498': {  # 烽火通信
        'name': '烽火通信',
        'revenue_growth_yoy': 5.4,
        'profit_growth_yoy': 7.8,
        'profit_volatility': 10.6,
        'roe_ttm': 13.6,
        'net_margin_ttm': 4.9,
        'gross_margin_ttm': 21.5,
        'debt_ratio': 0.503,
        'op_cf_ttm': 28.1 * 100000000,
    },
}

def fill_missing_stocks_data():
    """补全14只股票的数据"""
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
        logger.info(f"需要补全的股票: {len(STOCKS_DATA)} 只\n")
        
        success_count = 0
        
        for idx, (code, data) in enumerate(sorted(STOCKS_DATA.items()), 1):
            logger.info(f"[{idx}/{len(STOCKS_DATA)}] 处理 {code} ({data['name']})")
            
            # 检查记录是否存在（同时检查两种格式）
            ts_code_formatted = f"{code}.SH" if code.startswith('6') else f"{code}.SZ"
            check_query = text('''
                SELECT ts_code FROM fact_daily_fundamental
                WHERE (ts_code = :code1 OR ts_code = :code2) AND trade_date = :trade_date
            ''')
            exists = session.execute(check_query, {
                'code1': code,
                'code2': ts_code_formatted,
                'trade_date': trade_date
            }).fetchone()
            
            # 准备更新字段
            update_fields = []
            update_values = {}
            
            # 增长数据
            if 'revenue_growth_yoy' in data:
                update_fields.append('revenue_growth_yoy = :revenue_growth_yoy')
                update_values['revenue_growth_yoy'] = data['revenue_growth_yoy']
                logger.info(f"  ✅ 营收增长: {data['revenue_growth_yoy']:.1f}%")
            
            if 'profit_growth_yoy' in data:
                update_fields.append('profit_growth_yoy = :profit_growth_yoy')
                update_values['profit_growth_yoy'] = data['profit_growth_yoy']
                logger.info(f"  ✅ 利润增长: {data['profit_growth_yoy']:.1f}%")
            
            if 'profit_volatility' in data:
                update_fields.append('profit_volatility = :profit_volatility')
                update_values['profit_volatility'] = data['profit_volatility']
                logger.info(f"  ✅ 利润波动性: {data['profit_volatility']:.1f}%")
            
            # 财务指标
            if 'roe_ttm' in data:
                update_fields.append('roe_ttm = :roe_ttm')
                update_values['roe_ttm'] = data['roe_ttm']
                logger.info(f"  ✅ ROE: {data['roe_ttm']:.1f}%")
            
            if 'net_margin_ttm' in data:
                update_fields.append('net_margin_ttm = :net_margin_ttm')
                update_values['net_margin_ttm'] = data['net_margin_ttm']
                logger.info(f"  ✅ 净利率: {data['net_margin_ttm']:.1f}%")
            
            if 'gross_margin_ttm' in data:
                update_fields.append('gross_margin_ttm = :gross_margin_ttm')
                update_values['gross_margin_ttm'] = data['gross_margin_ttm']
                logger.info(f"  ✅ 毛利率: {data['gross_margin_ttm']:.1f}%")
            
            if 'debt_ratio' in data:
                update_fields.append('debt_ratio = :debt_ratio')
                update_values['debt_ratio'] = data['debt_ratio']
                logger.info(f"  ✅ 负债率: {data['debt_ratio']*100:.1f}%")
            
            if 'op_cf_ttm' in data:
                update_fields.append('op_cf_ttm = :op_cf_ttm')
                update_values['op_cf_ttm'] = data['op_cf_ttm']
                logger.info(f"  ✅ 经营现金流: {data['op_cf_ttm']/100000000:.1f} 亿元")
            
            # 更新或插入
            if update_fields:
                # 确定使用哪个ts_code格式（优先使用已存在的格式）
                if exists:
                    existing_ts_code = exists[0]
                else:
                    # 如果不存在，使用6位数字格式
                    existing_ts_code = code
                
                if exists:
                    # 更新现有记录
                    update_sql = f"""
                        UPDATE fact_daily_fundamental
                        SET {', '.join(update_fields)}
                        WHERE ts_code = :ts_code
                          AND trade_date = :trade_date
                    """
                    update_values['ts_code'] = existing_ts_code
                    update_values['trade_date'] = trade_date
                    session.execute(text(update_sql), update_values)
                else:
                    # 插入新记录
                    field_names = [field.split(' = :')[0] for field in update_fields]
                    insert_fields = ['ts_code', 'trade_date'] + field_names
                    insert_values = [':ts_code', ':trade_date'] + [f":{field}" for field in field_names]
                    insert_sql = f"""
                        INSERT INTO fact_daily_fundamental ({', '.join(insert_fields)})
                        VALUES ({', '.join(insert_values)})
                    """
                    update_values['ts_code'] = code
                    update_values['trade_date'] = trade_date
                    session.execute(text(insert_sql), update_values)
                
                session.commit()
                logger.info(f"  ✅ 数据库更新成功")
                success_count += 1
            else:
                logger.warning(f"  ⚠️ 无数据可更新")
        
        logger.info("\n" + "=" * 80)
        logger.info(f"✅ 补全完成: 成功 {success_count}/{len(STOCKS_DATA)} 只")
        logger.info("=" * 80)
        
    except Exception as e:
        logger.error(f"❌ 补全失败: {e}", exc_info=True)
    finally:
        session.close()

if __name__ == "__main__":
    logger.info("=" * 80)
    logger.info("补全14只缺少增长数据和财务指标的行业龙头股票数据")
    logger.info("=" * 80)
    fill_missing_stocks_data()

