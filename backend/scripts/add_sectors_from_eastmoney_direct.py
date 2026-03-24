"""
使用东方财富个股接口直接获取股票的板块信息
这个接口可以直接查询：股票 → 所属板块
比Tushare的反向查询快得多
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from data_warehouse.service.warehouse_service import WarehouseService
from data_warehouse.models import DimStock
from sqlalchemy import text
from datetime import date
import requests
import time
import json

def get_stock_sectors_eastmoney(stock_code, exchange):
    """
    获取单只股票的板块信息（东方财富接口）
    
    Args:
        stock_code: 6位股票代码，如 301148
        exchange: 交易所，SZ/SH/BJ
    
    Returns:
        list: 板块列表，每个元素包含 {code, name, rank}
    """
    code_with_exchange = f"{exchange}{stock_code}"
    url = "http://emweb.securities.eastmoney.com/PC_HSF10/CoreConception/PageAjax"
    params = {'code': code_with_exchange}
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': 'http://emweb.securities.eastmoney.com/'
    }
    
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            sectors = []
            
            # ssbk: 所属板块
            if 'ssbk' in data and data['ssbk']:
                for item in data['ssbk']:
                    sectors.append({
                        'code': item.get('BOARD_CODE', ''),
                        'name': item.get('BOARD_NAME', ''),
                        'rank': item.get('BOARD_RANK', 999)
                    })
            
            return sectors
        else:
            return []
    except Exception as e:
        print(f"      ⚠️ 获取失败: {str(e)[:50]}")
        return []

def add_sectors_from_eastmoney_direct():
    """使用东方财富个股接口直接获取板块信息"""
    print("="*70)
    print("使用东方财富个股接口获取板块数据")
    print("="*70)
    
    ws = WarehouseService()
    session = ws.get_session()
    
    try:
        # 1. 获取所有股票列表
        print("\n📥 获取股票列表...")
        stocks = session.query(DimStock).all()
        print(f"✅ 获取到 {len(stocks)} 只股票")
        
        # 2. 遍历每只股票，获取其板块信息
        print("\n📝 获取每只股票的板块信息...")
        print("   ⚠️ 这个过程较慢，请耐心等待...")
        
        added_sectors = 0
        added_relations = 0
        failed_stocks = 0
        today = date.today()
        
        for idx, stock in enumerate(stocks):
            ts_code = stock.ts_code
            stock_code = stock.symbol  # 6位代码
            exchange = stock.exchange  # SSE/SZSE/BSE
            
            # 转换交易所代码
            if exchange == 'SSE':
                ex_code = 'SH'
            elif exchange == 'SZSE':
                ex_code = 'SZ'
            elif exchange == 'BSE':
                ex_code = 'BJ'
            else:
                continue
            
            if (idx + 1) % 100 == 0:
                print(f"  [{idx+1}/{len(stocks)}] 处理中...")
            
            # 获取板块信息
            sectors = get_stock_sectors_eastmoney(stock_code, ex_code)
            
            if not sectors:
                failed_stocks += 1
                time.sleep(0.2)
                continue
            
            # 处理每个板块
            for sector in sectors:
                sector_code = sector['code']
                sector_name = sector['name']
                
                if not sector_code or not sector_name:
                    continue
                
                sector_id = f"EM_{sector_code}"  # 东方财富板块ID
                
                # 1. 确保板块存在于 dim_sector
                exists_sector = session.execute(text("""
                    SELECT COUNT(*) FROM dim_sector WHERE sector_id = :sector_id
                """), {'sector_id': sector_id}).scalar()
                
                if exists_sector == 0:
                    # 插入新板块
                    try:
                        session.execute(text("""
                            INSERT INTO dim_sector (sector_id, sector_type, name, provider, updated_at)
                            VALUES (:sector_id, :sector_type, :name, :provider, CURRENT_TIMESTAMP)
                        """), {
                            'sector_id': sector_id,
                            'sector_type': 'concept',  # 东方财富的板块视为概念
                            'name': sector_name,
                            'provider': 'eastmoney'
                        })
                        added_sectors += 1
                    except Exception as e:
                        # 可能已存在（并发问题）
                        pass
                
                # 2. 建立股票-板块关联
                exists_relation = session.execute(text("""
                    SELECT COUNT(*) FROM fact_stock_sector
                    WHERE ts_code = :ts_code AND sector_id = :sector_id
                """), {
                    'ts_code': ts_code,
                    'sector_id': sector_id
                }).scalar()
                
                if exists_relation == 0:
                    try:
                        # rank=1 表示主板块（通常是行业板块）
                        is_primary = (sector['rank'] == 1)
                        
                        session.execute(text("""
                            INSERT INTO fact_stock_sector
                            (ts_code, sector_id, start_date, is_primary, updated_at)
                            VALUES (:ts_code, :sector_id, :start_date, :is_primary, CURRENT_TIMESTAMP)
                        """), {
                            'ts_code': ts_code,
                            'sector_id': sector_id,
                            'start_date': today,
                            'is_primary': is_primary
                        })
                        added_relations += 1
                    except Exception as e:
                        # 股票不存在等情况
                        pass
            
            # 每100只股票提交一次
            if (idx + 1) % 100 == 0:
                session.commit()
                print(f"    💾 进度: {idx+1}/{len(stocks)}, 新增板块 {added_sectors}, 新增关联 {added_relations}")
            
            # 避免请求过快
            time.sleep(0.5)
        
        session.commit()
        print(f"\n✅ 完成！")
        print(f"   新增板块: {added_sectors} 个")
        print(f"   新增关联: {added_relations} 条")
        print(f"   失败: {failed_stocks} 只")
        
        # 3. 最终统计
        print("\n" + "="*70)
        print("📊 最终统计")
        print("="*70)
        
        stats = session.execute(text("""
            SELECT 
                sector_type,
                provider,
                COUNT(DISTINCT sector_id) as sector_count
            FROM dim_sector
            GROUP BY sector_type, provider
            ORDER BY sector_type, provider
        """)).fetchall()
        
        print("\ndim_sector（板块维表）:")
        for sector_type, provider, count in stats:
            print(f"  {sector_type:10} ({provider:10}): {count:4} 个")
        
        stats2 = session.execute(text("""
            SELECT 
                is_primary,
                COUNT(*) as relation_count
            FROM fact_stock_sector
            WHERE end_date IS NULL
            GROUP BY is_primary
        """)).fetchall()
        
        print("\nfact_stock_sector（关联表）:")
        for is_primary, count in stats2:
            relation_type = "主板块" if is_primary else "概念板块"
            print(f"  {relation_type:10}: {count:6} 条")
        
        # 4. 显示示例股票的板块
        print("\n📊 示例股票的板块关联:")
        example_stocks = [
            ('301148.SZ', '嘉戎技术'),
            ('300750.SZ', '宁德时代'),
            ('600519.SH', '贵州茅台'),
        ]
        
        for ts_code, name in example_stocks:
            sectors = session.execute(text("""
                SELECT ds.name, fss.is_primary
                FROM fact_stock_sector fss
                JOIN dim_sector ds ON fss.sector_id = ds.sector_id
                WHERE fss.ts_code = :ts_code
                ORDER BY fss.is_primary DESC
                LIMIT 10
            """), {'ts_code': ts_code}).fetchall()
            
            print(f"\n{name} ({ts_code}): {len(sectors)} 个板块")
            if sectors:
                for sector_name, is_primary in sectors:
                    tag = "【主】" if is_primary else "【副】"
                    print(f"  {tag} {sector_name}")
            else:
                print("  （无板块数据）")
        
        print("\n" + "="*70)
        print("✅ 完成！现在可以在前端看到板块信息了")
        print("="*70)
        
    except Exception as e:
        print(f"\n❌ 失败: {e}")
        import traceback
        traceback.print_exc()
        session.rollback()
    finally:
        session.close()

if __name__ == "__main__":
    add_sectors_from_eastmoney_direct()

