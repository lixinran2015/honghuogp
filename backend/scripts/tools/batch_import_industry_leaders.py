"""
批量导入行业龙头股票数据
支持从JSON文件或数据库一次性导入各行各业的龙头股票
"""

import sys
import json
import logging
from pathlib import Path
from datetime import datetime, date
from typing import List, Dict, Optional

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from data_warehouse.service.warehouse_service import WarehouseService
from data_warehouse.models.orm_classes import DimStock, DimSector
from backend.knowledge_base.rag_service import RAGService
from sqlalchemy import text

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def import_from_json_file(json_file: str):
    """
    从JSON文件导入行业龙头数据
    
    JSON格式示例：
    {
      "industry_leaders": [
        {
          "industry": "新能源",
          "sector_code": "BK0493",
          "sector_name": "新能源",
          "leaders": [
            {
              "ts_code": "300750.SZ",
              "name": "宁德时代",
              "leader_type": "行业龙头",
              "reason": "全球动力电池市场份额第一，技术领先",
              "market_cap": 10000.0,
              "main_business": "动力电池、储能系统"
            }
          ]
        }
      ]
    }
    """
    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    ws = WarehouseService()
    session = ws.get_session()
    
    try:
        imported_count = 0
        
        for industry_data in data.get('industry_leaders', []):
            industry = industry_data.get('industry', '')
            sector_code = industry_data.get('sector_code', '')
            sector_name = industry_data.get('sector_name', '')
            leaders = industry_data.get('leaders', [])
            
            logger.info(f"📊 处理行业: {industry} ({sector_name}), 龙头数量: {len(leaders)}")
            
            # 确保板块存在
            sector = session.query(DimSector).filter(DimSector.sector_id == sector_code).first()
            if not sector:
                logger.info(f"  创建板块: {sector_code} - {sector_name}")
                sector = DimSector(
                    sector_id=sector_code,
                    sector_type='industry',
                    name=sector_name,
                    level=1,
                    provider='manual',
                    updated_at=datetime.now()
                )
                session.add(sector)
                session.flush()
            
            # 导入龙头股票
            for leader in leaders:
                ts_code = leader.get('ts_code', '')
                name = leader.get('name', '')
                leader_type = leader.get('leader_type', '行业龙头')
                reason = leader.get('reason', '')
                market_cap = leader.get('market_cap', 0)
                main_business = leader.get('main_business', '')
                
                # 验证股票是否存在
                stock = session.query(DimStock).filter(DimStock.ts_code == ts_code).first()
                if not stock:
                    logger.warning(f"  ⚠️ 股票不存在: {ts_code} ({name})，跳过")
                    continue
                
                # 存储到行业龙头表
                insert_query = text("""
                    INSERT INTO dim_industry_leader 
                    (ts_code, stock_name, industry, sector_code, sector_name, leader_type, leader_reason, main_business, market_cap, source, is_active)
                    VALUES (:ts_code, :stock_name, :industry, :sector_code, :sector_name, :leader_type, :leader_reason, :main_business, :market_cap, 'manual', TRUE)
                    ON CONFLICT (ts_code, industry) 
                    DO UPDATE SET
                        stock_name = EXCLUDED.stock_name,
                        sector_code = EXCLUDED.sector_code,
                        sector_name = EXCLUDED.sector_name,
                        leader_type = EXCLUDED.leader_type,
                        leader_reason = EXCLUDED.leader_reason,
                        main_business = EXCLUDED.main_business,
                        market_cap = EXCLUDED.market_cap,
                        updated_at = CURRENT_TIMESTAMP,
                        is_active = TRUE
                """)
                
                session.execute(insert_query, {
                    'ts_code': ts_code,
                    'stock_name': name,
                    'industry': industry,
                    'sector_code': sector_code,
                    'sector_name': sector_name,
                    'leader_type': leader_type,
                    'leader_reason': reason,
                    'main_business': main_business,
                    'market_cap': market_cap
                })
                
                logger.info(f"  ✅ {ts_code} ({name}) - {leader_type}: {reason}")
                imported_count += 1
        
        session.commit()
        logger.info(f"✅ 导入完成，共导入 {imported_count} 只龙头股票")
        return imported_count
        
    except Exception as e:
        session.rollback()
        logger.error(f"❌ 导入失败: {e}", exc_info=True)
        return 0
    finally:
        session.close()


def import_to_rag_knowledge_base(json_file: str):
    """
    将行业龙头数据导入RAG知识库
    """
    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    try:
        rag_service = RAGService()
        documents = []
        
        for industry_data in data.get('industry_leaders', []):
            industry = industry_data.get('industry', '')
            sector_name = industry_data.get('sector_name', '')
            leaders = industry_data.get('leaders', [])
            
            # 为每个行业创建一个文档
            leader_list = []
            for leader in leaders:
                ts_code = leader.get('ts_code', '')
                name = leader.get('name', '')
                leader_type = leader.get('leader_type', '行业龙头')
                reason = leader.get('reason', '')
                main_business = leader.get('main_business', '')
                
                leader_info = f"- {name} ({ts_code}): {leader_type}，{reason}"
                if main_business:
                    leader_info += f"，主营业务：{main_business}"
                leader_list.append(leader_info)
            
            # 构建文档内容
            content = f"""【{industry}】行业龙头股票列表

{sector_name}行业的龙头股票包括：

{chr(10).join(leader_list)}

这些股票在各自行业中具有领先地位，通常具有以下特征：
1. 市场份额领先
2. 技术或成本优势明显
3. 品牌影响力强
4. 财务状况稳健
"""
            
            documents.append({
                'id': f"industry_leader_{industry}",
                'content': content,
                'metadata': {
                    'title': f'{industry}行业龙头',
                    'category': '行业龙头',
                    'industry': industry,
                    'sector_name': sector_name,
                    'leader_count': len(leaders),
                    'source': 'manual_import',
                    'updated_at': datetime.now().isoformat()
                }
            })
        
        # 批量添加到知识库
        if documents:
            success = rag_service.add_documents(documents)
            if success:
                logger.info(f"✅ 成功导入 {len(documents)} 个行业龙头文档到RAG知识库")
                return len(documents)
            else:
                logger.error("❌ 导入RAG知识库失败")
                return 0
        else:
            logger.warning("⚠️ 没有文档可导入")
            return 0
            
    except Exception as e:
        logger.error(f"❌ 导入RAG知识库失败: {e}", exc_info=True)
        return 0


def query_industry_leaders_from_db(industry: Optional[str] = None) -> List[Dict]:
    """
    从数据库查询行业龙头数据
    
    Args:
        industry: 行业名称（可选，不提供则查询所有）
        
    Returns:
        List[Dict]: 行业龙头列表
    """
    ws = WarehouseService()
    session = ws.get_session()
    
    try:
        if industry:
            query = text("""
                SELECT ts_code, stock_name, industry, sector_code, sector_name, 
                       leader_type, leader_reason, main_business, market_cap
                FROM dim_industry_leader
                WHERE industry = :industry AND is_active = TRUE
                ORDER BY industry, leader_type, ts_code
            """)
            results = session.execute(query, {'industry': industry}).fetchall()
        else:
            query = text("""
                SELECT ts_code, stock_name, industry, sector_code, sector_name, 
                       leader_type, leader_reason, main_business, market_cap
                FROM dim_industry_leader
                WHERE is_active = TRUE
                ORDER BY industry, leader_type, ts_code
            """)
            results = session.execute(query).fetchall()
        
        leaders = []
        for row in results:
            leaders.append({
                'ts_code': row[0],
                'name': row[1],
                'industry': row[2],
                'sector_code': row[3],
                'sector_name': row[4],
                'leader_type': row[5],
                'reason': row[6] or '',
                'main_business': row[7] or '',
                'market_cap': float(row[8]) if row[8] else 0
            })
        
        return leaders
    finally:
        session.close()


def create_sample_json_template(output_file: str = "industry_leaders_template.json"):
    """
    创建示例JSON模板文件
    """
    template = {
        "industry_leaders": [
            {
                "industry": "新能源",
                "sector_code": "BK0493",
                "sector_name": "新能源",
                "leaders": [
                    {
                        "ts_code": "300750.SZ",
                        "name": "宁德时代",
                        "leader_type": "行业龙头",
                        "reason": "全球动力电池市场份额第一，技术领先",
                        "market_cap": 10000.0,
                        "main_business": "动力电池、储能系统"
                    },
                    {
                        "ts_code": "002594.SZ",
                        "name": "比亚迪",
                        "leader_type": "行业龙头",
                        "reason": "新能源汽车销量全球领先，全产业链布局",
                        "market_cap": 8000.0,
                        "main_business": "新能源汽车、电池、电子"
                    }
                ]
            },
            {
                "industry": "白酒",
                "sector_code": "BK0737",
                "sector_name": "白酒",
                "leaders": [
                    {
                        "ts_code": "600519.SH",
                        "name": "贵州茅台",
                        "leader_type": "行业龙头",
                        "reason": "白酒行业第一品牌，品牌价值最高",
                        "market_cap": 20000.0,
                        "main_business": "白酒生产销售"
                    }
                ]
            }
        ]
    }
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(template, f, ensure_ascii=False, indent=2)
    
    logger.info(f"✅ 已创建示例模板文件: {output_file}")
    logger.info(f"   请编辑此文件，填入实际的行业龙头数据，然后运行导入脚本")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='批量导入行业龙头股票数据')
    parser.add_argument('--json', type=str, help='JSON数据文件路径')
    parser.add_argument('--no-rag', action='store_true', dest='no_rag', help='导入时跳过RAG知识库同步（默认会同步）')
    parser.add_argument('--template', action='store_true', help='创建示例模板文件')
    parser.add_argument('--query', type=str, help='查询行业龙头数据（行业名称，不提供则查询所有）')
    parser.add_argument('--export', type=str, help='导出数据到JSON文件（文件路径）')
    
    args = parser.parse_args()
    
    if args.template:
        create_sample_json_template()
    elif args.query is not None:
        # 查询行业龙头数据
        leaders = query_industry_leaders_from_db(args.query if args.query else None)
        logger.info(f"📊 查询结果: 找到 {len(leaders)} 只行业龙头股票")
        
        if args.export:
            # 导出到JSON文件
            export_data = {'industry_leaders': []}
            current_industry = None
            current_group = None
            
            for leader in leaders:
                if leader['industry'] != current_industry:
                    if current_group:
                        export_data['industry_leaders'].append(current_group)
                    current_industry = leader['industry']
                    current_group = {
                        'industry': leader['industry'],
                        'sector_code': leader.get('sector_code', ''),
                        'sector_name': leader.get('sector_name', leader['industry']),
                        'leaders': []
                    }
                
                current_group['leaders'].append({
                    'ts_code': leader['ts_code'],
                    'name': leader['name'],
                    'leader_type': leader['leader_type'],
                    'reason': leader['reason'],
                    'market_cap': leader['market_cap'],
                    'main_business': leader['main_business']
                })
            
            if current_group:
                export_data['industry_leaders'].append(current_group)
            
            with open(args.export, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"✅ 已导出到文件: {args.export}")
        else:
            # 直接打印
            current_industry = None
            for leader in leaders:
                if leader['industry'] != current_industry:
                    current_industry = leader['industry']
                    logger.info(f"\n📊 {current_industry}:")
                logger.info(f"  - {leader['name']} ({leader['ts_code']}): {leader['leader_type']} - {leader['reason']}")
    elif args.json:
        logger.info(f"📥 开始导入行业龙头数据: {args.json}")
        
        # 导入到数据库
        db_count = import_from_json_file(args.json)
        
        # 导入到 RAG 知识库（默认同步，--no-rag 可跳过）
        if not args.no_rag:
            try:
                rag_count = import_to_rag_knowledge_base(args.json)
                logger.info(f"📊 导入统计: 数据库 {db_count} 只，RAG知识库 {rag_count} 个文档")
            except Exception as e:
                logger.warning(f"⚠️ RAG知识库导入失败（数据库已导入）: {e}")
                logger.info(f"📊 导入统计: 数据库 {db_count} 只")
        else:
            logger.info(f"📊 导入统计: 数据库 {db_count} 只（已跳过RAG同步）")
    else:
        parser.print_help()
        print("\n📖 使用说明：")
        print("\n1️⃣ 创建模板文件:")
        print("   python batch_import_industry_leaders.py --template")
        print("   生成 industry_leaders_template.json 模板文件")
        print("\n2️⃣ 编辑模板文件，填入实际的行业龙头数据")
        print("\n3️⃣ 导入数据到数据库:")
        print("   python batch_import_industry_leaders.py --json industry_leaders.json")
        print("\n4️⃣ 导入时默认同步到RAG知识库（用于AI查询），可用 --no-rag 跳过")
        print("\n5️⃣ 查询已导入的数据:")
        print("   python batch_import_industry_leaders.py --query 新能源")
        print("   python batch_import_industry_leaders.py --query  # 查询所有")
        print("\n6️⃣ 导出数据到JSON文件:")
        print("   python batch_import_industry_leaders.py --query --export exported_data.json")
