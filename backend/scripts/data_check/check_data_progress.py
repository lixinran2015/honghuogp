"""
数据补充进度检查脚本
实时查看各项数据补充任务的进度
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy import create_engine, text
from data_warehouse.config import DATABASE_URL


def check_progress():
    """检查数据补充进度"""
    engine = create_engine(DATABASE_URL, echo=False)
    
    print('='*80)
    print('数据补充进度实时监控')
    print('='*80)
    
    with engine.connect() as conn:
        # 1. fact_stock_sector
        result = conn.execute(text('''
            SELECT COUNT(*) as total,
                   COUNT(DISTINCT ts_code) as stocks,
                   COUNT(DISTINCT sector_id) as sectors
            FROM fact_stock_sector
        '''))
        row = result.fetchone()
        pct = row[1] * 100 / 5482 if row[1] else 0
        print(f'\n📊 1. 股票-板块关联 (fact_stock_sector):')
        print(f'   ✅ 关联记录: {row[0]:,} 条')
        print(f'   ✅ 覆盖股票: {row[1]:,} / 5,482 ({pct:.1f}%)')
        print(f'   ✅ 覆盖板块: {row[2]} / 86 ({row[2]*100//86}%)')
        
        # 2. MA字段
        result = conn.execute(text('''
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN ma5 IS NOT NULL THEN 1 ELSE 0 END) as has_ma5,
                SUM(CASE WHEN ma10 IS NOT NULL THEN 1 ELSE 0 END) as has_ma10,
                SUM(CASE WHEN ma20 IS NOT NULL THEN 1 ELSE 0 END) as has_ma20,
                SUM(CASE WHEN ma60 IS NOT NULL THEN 1 ELSE 0 END) as has_ma60
            FROM fact_daily_price_qfq
        '''))
        row = result.fetchone()
        print(f'\n📊 2. MA均线计算 (全部数据):')
        print(f'   总记录: {row[0]:,}')
        print(f'   ✅ MA5:  {row[1]:,} ({row[1]*100//row[0] if row[0] > 0 else 0}%)')
        print(f'   ⏳ MA10: {row[2]:,} ({row[2]*100//row[0] if row[0] > 0 else 0}%)')
        print(f'   ⏳ MA20: {row[3]:,} ({row[3]*100//row[0] if row[0] > 0 else 0}%)')
        print(f'   ⏳ MA60: {row[4]:,} ({row[4]*100//row[0] if row[0] > 0 else 0}%)')
        
        # 3. 成交量指标
        result = conn.execute(text('''
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN avg_volume_5 IS NOT NULL THEN 1 ELSE 0 END) as has_avg_vol,
                SUM(CASE WHEN volume_ratio IS NOT NULL THEN 1 ELSE 0 END) as has_ratio
            FROM fact_daily_price_qfq
        '''))
        row = result.fetchone()
        print(f'\n📊 3. 成交量指标:')
        print(f'   总记录: {row[0]:,}')
        print(f'   ⏳ avg_volume_5: {row[1]:,} ({row[1]*100//row[0] if row[0] > 0 else 0}%)')
        print(f'   ⏳ volume_ratio: {row[2]:,} ({row[2]*100//row[0] if row[0] > 0 else 0}%)')
        
        # 4. 板块日线
        result = conn.execute(text('''
            SELECT COUNT(*) as total,
                   COUNT(DISTINCT sector_id) as sectors
            FROM fact_sector_daily
        '''))
        row = result.fetchone()
        print(f'\n📊 4. 板块日线 (fact_sector_daily):')
        print(f'   ✅ 记录数: {row[0]:,} 条')
        print(f'   ✅ 板块数: {row[1]} / 86 ({row[1]*100//86 if row[1] else 0}%)')
        
        # 5. 涨停板和市场情绪
        result = conn.execute(text('''
            SELECT 
                (SELECT COUNT(*) FROM fact_limit_up_daily) as limit_up_count,
                (SELECT COUNT(DISTINCT trade_date) FROM fact_limit_up_daily) as limit_up_dates,
                (SELECT COUNT(*) FROM fact_market_emotion_daily) as emotion_count
        '''))
        row = result.fetchone()
        print(f'\n📊 5. 涨停板和市场情绪:')
        print(f'   ✅ 涨停板记录: {row[0]:,} 条')
        print(f'   ✅ 涨停板交易日: {row[1]} 天')
        print(f'   ✅ 市场情绪记录: {row[2]} 天')
        
    print('\n' + '='*80)
    print('提示: 运行 python3 backend/scripts/check_data_progress.py 查看最新进度')
    print('='*80)


if __name__ == "__main__":
    check_progress()

