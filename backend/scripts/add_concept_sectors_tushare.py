"""
使用Tushare Pro获取概念板块数据
需要Tushare Pro积分（2000分以上）
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from data_warehouse.service.warehouse_service import WarehouseService
from sqlalchemy import text
from datetime import date
import time

def add_concept_sectors_from_tushare():
    """使用Tushare Pro添加概念板块"""
    print("="*70)
    print("使用Tushare Pro添加概念板块数据")
    print("="*70)
    
    # 1. 导入Tushare
    try:
        import tushare as ts
    except ImportError:
        print("❌ Tushare未安装，请安装: pip install tushare")
        return
    
    # 2. 初始化Tushare Pro（请替换为您的token）
    # 从环境变量或配置文件读取token
    try:
        from data_warehouse.config import TUSHARE_TOKEN
        token = TUSHARE_TOKEN
    except ImportError:
        print("⚠️ 未找到配置文件中的TUSHARE_TOKEN")
        token = input("请输入您的Tushare token: ").strip()
    
    if not token:
        print("❌ 未提供Tushare token")
        return
    
    try:
        pro = ts.pro_api(token)
        print("✅ Tushare Pro API初始化成功")
    except Exception as e:
        print(f"❌ Tushare Pro初始化失败: {e}")
        return
    
    ws = WarehouseService()
    session = ws.get_session()
    
    try:
        # 3. 获取概念板块列表
        print("\n📥 获取概念板块列表...")
        try:
            # Tushare接口：concept
            # 返回字段：code, name, src（来源）
            df_concepts = pro.concept(fields='code,name,src')
            print(f"✅ 获取到 {len(df_concepts)} 个概念板块")
            
            print(f"\n示例概念板块（前10个）:")
            for idx, row in df_concepts.head(10).iterrows():
                print(f"  {idx+1:2}. {row['code']:10} - {row['name']:20} (来源: {row['src']})")
        
        except Exception as e:
            print(f"❌ 获取概念板块列表失败: {e}")
            print("   可能原因：")
            print("   1. Tushare积分不足（需要2000分以上）")
            print("   2. Token无效")
            print("   3. 接口调用次数超限")
            return
        
        # 4. 更新 dim_sector 表（添加概念板块）
        print("\n📝 更新 dim_sector 表（概念板块）...")
        added_sectors = 0
        updated_sectors = 0
        
        for idx, row in df_concepts.iterrows():
            concept_code = row['code']
            concept_name = row['name']
            src = row.get('src', 'tushare')
            
            sector_id = f"CONCEPT_{concept_code}"
            
            # 检查是否已存在
            exists = session.execute(text("""
                SELECT COUNT(*) FROM dim_sector WHERE sector_id = :sector_id
            """), {'sector_id': sector_id}).scalar()
            
            if exists == 0:
                # 插入新概念板块
                session.execute(text("""
                    INSERT INTO dim_sector (sector_id, sector_type, name, provider, updated_at)
                    VALUES (:sector_id, :sector_type, :name, :provider, CURRENT_TIMESTAMP)
                """), {
                    'sector_id': sector_id,
                    'sector_type': 'concept',
                    'name': concept_name,
                    'provider': 'tushare'
                })
                added_sectors += 1
            else:
                # 更新已有板块
                session.execute(text("""
                    UPDATE dim_sector 
                    SET name = :name, updated_at = CURRENT_TIMESTAMP
                    WHERE sector_id = :sector_id
                """), {
                    'sector_id': sector_id,
                    'name': concept_name
                })
                updated_sectors += 1
            
            if (added_sectors + updated_sectors) % 100 == 0:
                session.commit()
                print(f"  已处理 {added_sectors + updated_sectors} 个概念板块...")
        
        session.commit()
        print(f"✅ dim_sector 更新完成: 新增 {added_sectors} 个, 更新 {updated_sectors} 个")
        
        # 5. 获取每个概念板块的成分股并建立关联
        print("\n📝 建立股票-概念板块关联...")
        print(f"   ⚠️ 这个过程较慢（约{len(df_concepts)}个概念），请耐心等待...")
        print("   ⚠️ Tushare有调用频率限制，每分钟200次")
        
        added_relations = 0
        updated_relations = 0
        failed_concepts = 0
        today = date.today()
        
        for idx, row in df_concepts.iterrows():
            concept_code = row['code']
            concept_name = row['name']
            sector_id = f"CONCEPT_{concept_code}"
            
            if (idx + 1) % 10 == 0:
                print(f"  [{idx+1}/{len(df_concepts)}] 处理 {concept_name}...")
            
            # 重试机制
            max_retries = 3
            success = False
            
            for retry in range(max_retries):
                try:
                    # Tushare接口：concept_detail
                    # 参数：id（概念代码）
                    # 返回字段：ts_code, name（股票名称）
                    df_stocks = pro.concept_detail(
                        id=concept_code,
                        fields='ts_code,name'
                    )
                    
                    if df_stocks is not None and not df_stocks.empty:
                        # 为每只股票建立关联
                        for _, stock_row in df_stocks.iterrows():
                            ts_code = stock_row['ts_code']
                            
                            # 检查关联是否存在
                            exists_rel = session.execute(text("""
                                SELECT COUNT(*) FROM fact_stock_sector 
                                WHERE ts_code = :ts_code 
                                  AND sector_id = :sector_id
                            """), {
                                'ts_code': ts_code,
                                'sector_id': sector_id
                            }).scalar()
                            
                            if exists_rel == 0:
                                # 插入新关联（概念板块 is_primary=false）
                                try:
                                    session.execute(text("""
                                        INSERT INTO fact_stock_sector 
                                        (ts_code, sector_id, start_date, is_primary, updated_at)
                                        VALUES (:ts_code, :sector_id, :start_date, :is_primary, CURRENT_TIMESTAMP)
                                    """), {
                                        'ts_code': ts_code,
                                        'sector_id': sector_id,
                                        'start_date': today,
                                        'is_primary': False  # 概念不是主分类
                                    })
                                    added_relations += 1
                                except Exception as e:
                                    # 股票不存在等情况，跳过
                                    pass
                            else:
                                updated_relations += 1
                        
                        # 每个概念处理完提交一次
                        session.commit()
                        success = True
                        break
                    else:
                        if retry < max_retries - 1:
                            time.sleep(0.5)
                
                except Exception as e:
                    if "抱歉，您每分钟最多访问" in str(e):
                        print(f"    ⚠️ 触发频率限制，暂停60秒...")
                        time.sleep(61)
                    elif retry < max_retries - 1:
                        print(f"    ⚠️ 失败: {str(e)[:50]}，重试...")
                        time.sleep(2.0)
                    else:
                        failed_concepts += 1
                        break
            
            if not success:
                failed_concepts += 1
            
            # 避免触发频率限制
            time.sleep(0.31)  # Tushare限制每分钟200次，即每次间隔0.3秒
            
            # 每处理50个概念显示一次进度
            if (idx + 1) % 50 == 0:
                print(f"    💾 进度: {idx+1}/{len(df_concepts)}, 新增关联 {added_relations} 条")
        
        session.commit()
        print(f"\n✅ 概念板块关联完成: 新增 {added_relations} 条, 已存在 {updated_relations} 条")
        print(f"   失败: {failed_concepts} 个概念")
        
        # 6. 最终统计
        print("\n" + "="*70)
        print("📊 最终统计")
        print("="*70)
        
        stats = session.execute(text("""
            SELECT 
                sector_type,
                COUNT(DISTINCT sector_id) as sector_count
            FROM dim_sector
            GROUP BY sector_type
        """)).fetchall()
        
        print("\ndim_sector（板块维表）:")
        for sector_type, count in stats:
            print(f"  {sector_type:10} : {count:4} 个")
        
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
            relation_type = "主行业" if is_primary else "概念板块"
            print(f"  {relation_type:10} : {count:6} 条")
        
        # 7. 显示示例股票的板块
        print("\n📊 示例股票的板块关联:")
        
        example_stocks = [
            ('300750.SZ', '宁德时代'),
            ('600519.SH', '贵州茅台'),
            ('000001.SZ', '平安银行'),
        ]
        
        for ts_code, name in example_stocks:
            print(f"\n{name} ({ts_code}):")
            example_sectors = session.execute(text("""
                SELECT ds.name, fss.is_primary
                FROM fact_stock_sector fss
                JOIN dim_sector ds ON fss.sector_id = ds.sector_id
                WHERE fss.ts_code = :ts_code
                  AND fss.end_date IS NULL
                ORDER BY fss.is_primary DESC
                LIMIT 10
            """), {'ts_code': ts_code}).fetchall()
            
            if example_sectors:
                for sector_name, is_primary in example_sectors:
                    tag = "【行业】" if is_primary else "【概念】"
                    print(f"  {tag} {sector_name}")
            else:
                print("  （无板块数据）")
        
        print("\n" + "="*70)
        print("✅ 完成！现在可以取消前端的板块列注释了")
        print("="*70)
        
    except Exception as e:
        print(f"\n❌ 失败: {e}")
        import traceback
        traceback.print_exc()
        session.rollback()
    finally:
        session.close()

if __name__ == "__main__":
    add_concept_sectors_from_tushare()

