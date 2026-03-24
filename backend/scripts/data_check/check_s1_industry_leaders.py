#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查S1股票池是否包含行业龙头股票
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.services.stock.stock_universe_service import StockUniverseService
from data_warehouse.service.warehouse_service import WarehouseService
from sqlalchemy import text

# 45只行业龙头股票列表（6位数字代码）
INDUSTRY_LEADERS = [
    '601288', '601398', '601939',  # 银行
    '600030', '601688', '601211',  # 证券
    '601318', '601628', '601601',  # 保险
    '600519', '000858', '600887',  # 食品饮料
    '000568',  # 酿酒行业
    '002594', '600104', '000625',  # 汽车整车
    '300750', '300014',  # 电池
    '601012', '600438', '002459',  # 光伏
    '688981', '002371', '603501',  # 半导体
    '002475', '002241', '300433',  # 消费电子
    '000063', '600498', '002396',  # 通信设备
    '600588', '600570', '688111',  # 软件开发
    '600276', '600196', '002422',  # 化学制药
    '300122', '300601', '002007',  # 生物制品
    '601088', '601225', '600188',  # 煤炭
    '600019', '000898', '000709',  # 钢铁
]

def check_s1_universe():
    """检查S1股票池是否包含行业龙头股票"""
    
    print("=" * 80)
    print("检查S1股票池是否包含行业龙头股票")
    print("=" * 80)
    
    # 1. 获取S1股票池
    universe_service = StockUniverseService()
    s1_stocks = universe_service.get_universe_stocks('s1')
    print(f"\n📊 S1股票池数量: {len(s1_stocks)} 只")
    
    # 2. 检查行业龙头股票是否在S1中
    s1_codes = set(s1_stocks)
    leader_in_s1 = []
    leader_not_in_s1 = []
    
    for code in INDUSTRY_LEADERS:
        if code in s1_codes:
            leader_in_s1.append(code)
        else:
            leader_not_in_s1.append(code)
    
    print(f"\n✅ 行业龙头股票在S1中: {len(leader_in_s1)}/{len(INDUSTRY_LEADERS)} 只")
    if leader_in_s1:
        print(f"   包含: {', '.join(sorted(leader_in_s1))}")
    
    print(f"\n❌ 行业龙头股票不在S1中: {len(leader_not_in_s1)}/{len(INDUSTRY_LEADERS)} 只")
    if leader_not_in_s1:
        print(f"   未包含: {', '.join(sorted(leader_not_in_s1))}")
    
    # 3. 分析未包含的原因
    if leader_not_in_s1:
        print(f"\n📋 分析未包含原因（S1筛选条件：ROE>=10%, 毛利率>=15%, PE<60, 净利率>0）:")
        print("-" * 80)
        
        wh_service = WarehouseService()
        session = wh_service.get_session()
        
        try:
            # 获取最新交易日期
            latest_date_query = text('''
                SELECT MAX(trade_date) FROM fact_daily_fundamental
                LIMIT 1
            ''')
            latest_date_result = session.execute(latest_date_query).fetchone()
            trade_date = latest_date_result[0] if latest_date_result and latest_date_result[0] else None
            
            print(f"使用交易日期: {trade_date}\n")
            
            for code in sorted(leader_not_in_s1):
                query = text('''
                    SELECT 
                        roe_ttm,
                        gross_margin_ttm,
                        pe_ttm,
                        net_margin_ttm
                    FROM fact_daily_fundamental
                    WHERE ts_code = :ts_code AND trade_date = :trade_date
                ''')
                result = session.execute(query, {'ts_code': code, 'trade_date': trade_date}).fetchone()
                
                if result:
                    roe, gross_margin, pe, net_margin = result
                    reasons = []
                    
                    if not roe or roe < 10.0:
                        reasons.append(f'ROE={roe:.1f}%<10%' if roe else 'ROE缺失')
                    if not gross_margin or gross_margin < 15.0:
                        if gross_margin is None:
                            reasons.append('毛利率缺失（金融股正常）')
                        else:
                            reasons.append(f'毛利率={gross_margin:.1f}%<15%')
                    if not pe or pe >= 60.0:
                        reasons.append(f'PE={pe:.1f}>=60' if pe else 'PE缺失')
                    if not net_margin or net_margin <= 0:
                        reasons.append(f'净利率={net_margin:.1f}%<=0' if net_margin else '净利率缺失')
                    
                    if reasons:
                        print(f"{code}: {' | '.join(reasons)}")
                    else:
                        print(f"{code}: ✅ 数据满足条件（可能在其他筛选环节被剔除）")
                else:
                    print(f"{code}: ❌ 无财务数据")
        finally:
            session.close()
    
    # 4. 统计信息
    print(f"\n📊 统计信息:")
    print(f"   S1股票池总数: {len(s1_stocks)} 只")
    print(f"   行业龙头股票总数: {len(INDUSTRY_LEADERS)} 只")
    print(f"   行业龙头股票在S1中: {len(leader_in_s1)} 只 ({len(leader_in_s1)/len(INDUSTRY_LEADERS)*100:.1f}%)")
    print(f"   行业龙头股票不在S1中: {len(leader_not_in_s1)} 只 ({len(leader_not_in_s1)/len(INDUSTRY_LEADERS)*100:.1f}%)")
    
    # 5. 建议
    print(f"\n💡 建议:")
    if len(leader_not_in_s1) > 0:
        financial_stocks = ['601288', '601398', '601939', '600030', '601688', '601211', 
                           '601318', '601628', '601601']
        financial_not_in_s1 = [code for code in leader_not_in_s1 if code in financial_stocks]
        
        if financial_not_in_s1:
            print(f"   ⚠️ {len(financial_not_in_s1)} 只金融股因毛利率缺失被剔除（行业特性）")
            print(f"      建议：对金融股放宽毛利率要求或单独处理")
        
        non_financial_not_in_s1 = [code for code in leader_not_in_s1 if code not in financial_stocks]
        if non_financial_not_in_s1:
            print(f"   ⚠️ {len(non_financial_not_in_s1)} 只非金融股未包含，需检查具体原因")
    else:
        print(f"   ✅ 所有行业龙头股票都在S1中！")


if __name__ == "__main__":
    check_s1_universe()

