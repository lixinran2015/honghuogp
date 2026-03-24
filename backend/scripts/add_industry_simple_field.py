"""
为 dim_stock 表添加 industry_simple 字段（行业简称）
保留原始 industry 字段，新增 industry_simple 用于显示
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from data_warehouse.service.warehouse_service import WarehouseService
from sqlalchemy import text

# 行业名称简化映射表（完整版）
INDUSTRY_MAPPING = {
    # 电子类
    'C39计算机、通信和其他电子设备制造业': '电子',
    'C38电气机械和器材制造业': '电气设备',
    
    # 环保类
    'N77生态保护和环境治理业': '环保',
    'N78公共设施管理业': '环保工程',
    'C42废弃资源综合利用业': '环保',
    
    # 金融类
    'J66货币金融服务': '银行',
    'J67资本市场服务': '证券',
    'J68保险业': '保险',
    'J69其他金融业': '其他金融',
    
    # 医药类
    'C27医药制造业': '医药制造',
    'Q83卫生': '医疗服务',
    'C276中药饮片加工': '中药',
    
    # 食品饮料
    'C13农副食品加工业': '食品加工',
    'C14食品制造业': '食品制造',
    'C15酒、饮料和精制茶制造业': '食品饮料',
    'C16烟草制品业': '烟草',
    
    # 汽车类
    'C36汽车制造业': '汽车',
    'C37铁路、船舶、航空航天和其他运输设备制造业': '交运设备',
    
    # 化工类
    'C26化学原料和化学制品制造业': '化工',
    'C28化学纤维制造业': '化纤',
    'C25石油、煤炭及其他燃料加工业': '石化',
    'C29橡胶和塑料制品业': '化工',
    
    # 建筑建材
    'C30非金属矿物制品业': '建材',
    'E47房屋建筑业': '建筑装饰',
    'E48土木工程建筑业': '基建',
    'E50建筑装饰和其他建筑业': '建筑装饰',
    'E50建筑装饰、装修和其他建筑业': '建筑装饰',
    
    # 纺织服装
    'C17纺织业': '纺织',
    'C18纺织服装、服饰业': '服装',
    'C19皮革、毛皮、羽毛及其制品和制鞋业': '轻工制造',
    'C21家具制造业': '家具',
    'C22造纸和纸制品业': '造纸',
    
    # 传媒
    'R87广播、电视、电影和影视录音制作业': '传媒',
    'R87广播、电视、电影和录音制作业': '传媒',
    'I63电信、广播电视和卫星传输服务': '通信服务',
    'I64互联网和相关服务': '互联网',
    'I65软件和信息技术服务业': '计算机',
    'C23印刷和记录媒介复制业': '印刷',
    'C24文教、工美、体育和娱乐用品制造业': '文体用品',
    'C20木材加工和木、竹、藤、棕、草制品业': '木材加工',
    
    # 零售
    'F52零售业': '商贸零售',
    'F51批发业': '商贸零售',
    'F53餐饮业': '餐饮',
    'H61住宿业': '酒店',
    'H62餐饮业': '餐饮',
    
    # 机械
    'C34通用设备制造业': '机械设备',
    'C35专用设备制造业': '机械设备',
    'C40仪器仪表制造业': '仪器仪表',
    'C41其他制造业': '其他制造',
    'C43金属制品、机械和设备修理业': '设备维修',
    
    # 有色金属
    'C31黑色金属冶炼和压延加工业': '钢铁',
    'C32有色金属冶炼和压延加工业': '有色金属',
    'C33金属制品业': '金属制品',
    
    # 采矿
    'B06煤炭开采和洗选业': '煤炭',
    'B07石油和天然气开采业': '石油开采',
    'B08黑色金属矿采选业': '黑色采矿',
    'B09有色金属矿采选业': '有色采矿',
    'B10非金属矿采选业': '非金属采矿',
    'B11开采专业及辅助性活动': '采矿服务',
    
    # 交运物流
    'G53铁路运输业': '交通运输',
    'G54道路运输业': '交通运输',
    'G55水上运输业': '交通运输',
    'G56航空运输业': '交通运输',
    'G57管道运输业': '管道运输',
    'G58装卸搬运和运输代理业': '物流',
    'G58多式联运和运输代理业': '物流',
    'G59仓储业': '物流',
    'G59装卸搬运和仓储业': '物流',
    'G60邮政业': '邮政',
    
    # 能源
    'D44电力、热力生产和供应业': '电力',
    'D45燃气生产和供应业': '燃气',
    'D46水的生产和供应业': '水务',
    
    # 农林牧渔
    'A01农业': '农业',
    'A02林业': '林业',
    'A03畜牧业': '畜牧业',
    'A04渔业': '渔业',
    'A05渔业': '渔业',
    'A05农、林、牧、渔专业及辅助性活动': '农业服务',
    
    # 房地产
    'K70房地产业': '房地产',
    
    # 服务业
    'L71租赁业': '租赁',
    'L72商务服务业': '商务服务',
    'M73研究和试验发展': '研发',
    'M74专业技术服务业': '专业服务',
    'M75科技推广和应用服务业': '科技服务',
    'N76水利、环境和公共设施管理业': '公共设施',
    'N77生态保护和环境治理业': '环保',
    'N78公共设施管理业': '环保工程',
    'O80居民服务业': '居民服务',
    'O81机动车、电子产品和日用产品修理业': '维修服务',
    'P82教育': '教育',
    'Q84社会工作': '社会服务',
    'R85新闻和出版业': '新闻出版',
    'R86文化艺术业': '文化',
    'R88文化艺术业': '文化',
    'S90综合': '综合',
}

def add_industry_simple_field():
    """添加行业简称字段"""
    print("="*70)
    print("为 dim_stock 表添加 industry_simple 字段")
    print("="*70)
    
    ws = WarehouseService()
    session = ws.get_session()
    
    try:
        # 1. 检查字段是否已存在
        print("\n🔍 检查 industry_simple 字段...")
        result = session.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'dim_stock' AND column_name = 'industry_simple'
        """)).fetchall()
        
        if result:
            print("   ℹ️ industry_simple 字段已存在")
        else:
            print("   ⚠️ industry_simple 字段不存在，正在添加...")
            # PostgreSQL需要分开添加列和注释
            session.execute(text("""
                ALTER TABLE dim_stock 
                ADD COLUMN industry_simple VARCHAR(50)
            """))
            session.execute(text("""
                COMMENT ON COLUMN dim_stock.industry_simple IS '行业简称（用于显示）'
            """))
            session.commit()
            print("   ✅ 字段添加成功")
        
        # 2. 更新 industry_simple 字段
        print("\n📝 更新 industry_simple 字段...")
        updated = 0
        
        for old_name, simple_name in INDUSTRY_MAPPING.items():
            result = session.execute(text("""
                UPDATE dim_stock 
                SET industry_simple = :simple_name
                WHERE industry = :old_name
            """), {'old_name': old_name, 'simple_name': simple_name})
            
            if result.rowcount > 0:
                updated += result.rowcount
                print(f"  ✅ {old_name[:35]:35} → {simple_name:12} ({result.rowcount:4} 只)")
        
        session.commit()
        print(f"\n✅ 更新完成！共更新 {updated} 只股票的简称")
        
        # 3. 对于没有映射的行业，使用原始名称或提取关键字
        print("\n📝 处理未映射的行业...")
        unmapped = session.execute(text("""
            UPDATE dim_stock 
            SET industry_simple = industry
            WHERE industry IS NOT NULL 
              AND industry != ''
              AND (industry_simple IS NULL OR industry_simple = '')
        """))
        session.commit()
        print(f"   ✅ 使用原名称: {unmapped.rowcount} 只")
        
        # 4. 验证结果
        print("\n📊 验证结果:")
        verify = session.execute(text("""
            SELECT 
                COUNT(*) as total,
                COUNT(CASE WHEN industry_simple IS NOT NULL AND industry_simple != '' THEN 1 END) as has_simple
            FROM dim_stock
        """)).fetchone()
        
        print(f"   总股票数: {verify[0]}")
        print(f"   有简称: {verify[1]} ({verify[1]/verify[0]*100:.1f}%)")
        
        # 5. 显示简化后的行业分布
        print("\n📊 简化后的行业分布（Top 15）:")
        top_industries = session.execute(text("""
            SELECT industry_simple, COUNT(*) as cnt
            FROM dim_stock
            WHERE industry_simple IS NOT NULL AND industry_simple != ''
            GROUP BY industry_simple
            ORDER BY COUNT(*) DESC
            LIMIT 15
        """)).fetchall()
        
        for idx, (industry, cnt) in enumerate(top_industries, 1):
            print(f"  {idx:2}. {industry:15} {cnt:4} 只")
        
        print("\n" + "="*70)
        print("✅ 完成！")
        print("现在可以使用 industry_simple 字段显示行业简称")
        print("="*70)
        
    except Exception as e:
        print(f"\n❌ 失败: {e}")
        import traceback
        traceback.print_exc()
        session.rollback()
    finally:
        session.close()

if __name__ == "__main__":
    add_industry_simple_field()

