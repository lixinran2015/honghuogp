#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
填充板块龙头和事件数据
从现有数据中提取或生成示例数据
"""

import sys
from pathlib import Path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import logging
from datetime import date, timedelta
from sqlalchemy import text, inspect
from data_warehouse.service.warehouse_service import WarehouseService
from data_warehouse.models import (
    FactSectorLeaderSnapshot, FactSectorEvent, FactSectorHeatSnapshot,
    DimStock, FactStockSector
)
from backend.api.darwin import map_industry_to_sector

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def fill_sector_leaders(window_id='current_rolling_30d'):
    """填充板块龙头数据"""
    logger.info("=" * 80)
    logger.info("填充板块龙头数据")
    logger.info("=" * 80)
    
    warehouse_service = WarehouseService()
    session = warehouse_service.get_session()
    
    try:
        inspector = inspect(session.bind)
        if 'fact_sector_leader_snapshot' not in inspector.get_table_names():
            logger.error("❌ fact_sector_leader_snapshot 表不存在，请先创建表")
            return
        
        # 获取所有板块热度快照
        heat_snapshots = session.query(FactSectorHeatSnapshot).filter(
            FactSectorHeatSnapshot.window_id == window_id
        ).all()
        
        logger.info(f"📊 找到 {len(heat_snapshots)} 个板块热度快照")
        
        # 按大板块分组
        sector_groups = {}
        for snap in heat_snapshots:
            mapped_sector = map_industry_to_sector(snap.sector_name)
            if mapped_sector not in sector_groups:
                sector_groups[mapped_sector] = []
            sector_groups[mapped_sector].append(snap.sector_code)
        
        logger.info(f"📊 找到 {len(sector_groups)} 个大板块")
        
        # 为每个板块生成龙头数据
        total_leaders = 0
        for sector_name, industry_codes in sector_groups.items():
            # 获取每个行业的股票
            for industry_code in industry_codes[:3]:  # 每个板块最多取3个行业
                # 获取该行业的股票
                stock_sectors = session.query(FactStockSector).filter(
                    FactStockSector.sector_id == industry_code,
                    FactStockSector.end_date.is_(None)
                ).limit(10).all()
                
                if not stock_sectors:
                    continue
                
                # 获取股票基本信息
                ts_codes = [s.ts_code for s in stock_sectors]
                stocks = session.query(DimStock).filter(
                    DimStock.ts_code.in_(ts_codes)
                ).all()
                
                if not stocks:
                    continue
                
                # 为每个股票生成龙头数据（简化版，实际应该从K线数据计算）
                for idx, stock in enumerate(stocks[:5]):  # 每个行业最多5只股票
                    leader_type = 'absolute_leader' if idx == 0 else ('catch_up' if idx == 1 else 'follower')
                    leader_rank = idx + 1
                    
                    # 检查是否已存在
                    existing = session.query(FactSectorLeaderSnapshot).filter(
                        FactSectorLeaderSnapshot.window_id == window_id,
                        FactSectorLeaderSnapshot.sector_code == industry_code,
                        FactSectorLeaderSnapshot.ts_code == stock.ts_code
                    ).first()
                    
                    if existing:
                        continue
                    
                    leader = FactSectorLeaderSnapshot(
                        window_id=window_id,
                        sector_code=industry_code,
                        ts_code=stock.ts_code,
                        stock_name=stock.name,
                        leader_type=leader_type,
                        leader_rank=leader_rank,
                        period_return_pct=10.0 + idx * 2.0,  # 示例数据
                        period_amount=50.0 + idx * 10.0,
                        period_turnover=3.0 + idx * 0.5,
                        market_cap=100.0 + idx * 50.0,
                        change_pct_1d=2.0 + idx * 0.5,
                        change_pct_5d=5.0 + idx * 1.0,
                        limit_up_days=1 if idx == 0 else 0,
                        continuous_limit=1 if idx == 0 else 0,
                        score=80.0 - idx * 10.0
                    )
                    session.add(leader)
                    total_leaders += 1
        
        session.commit()
        logger.info(f"✅ 成功填充 {total_leaders} 条龙头数据")
        
    except Exception as e:
        logger.error(f"❌ 填充龙头数据失败: {e}", exc_info=True)
        session.rollback()
        raise
    finally:
        session.close()


def fill_sector_events(window_id='current_rolling_30d'):
    """填充板块事件数据"""
    logger.info("=" * 80)
    logger.info("填充板块事件数据")
    logger.info("=" * 80)
    
    warehouse_service = WarehouseService()
    session = warehouse_service.get_session()
    
    try:
        inspector = inspect(session.bind)
        if 'fact_sector_event' not in inspector.get_table_names():
            logger.error("❌ fact_sector_event 表不存在，请先创建表")
            return
        
        # 获取所有板块热度快照
        heat_snapshots = session.query(FactSectorHeatSnapshot).filter(
            FactSectorHeatSnapshot.window_id == window_id
        ).all()
        
        # 按大板块分组
        sector_groups = {}
        for snap in heat_snapshots:
            mapped_sector = map_industry_to_sector(snap.sector_name)
            if mapped_sector not in sector_groups:
                sector_groups[mapped_sector] = []
            sector_groups[mapped_sector].append(snap.sector_code)
        
        # 为每个板块生成一些示例事件
        today = date.today()
        event_templates = {
            '科技': [
                ('政策', '人工智能产业发展规划发布', '国家发布人工智能产业发展规划，推动AI技术在多个领域的应用'),
                ('新闻', '半导体行业迎来新突破', '国内半导体企业在关键技术领域取得重要突破'),
                ('会议', '科技行业峰会召开', '2025年科技行业峰会成功举办，聚焦数字化转型'),
            ],
            '消费': [
                ('政策', '消费促进政策出台', '国家出台新一轮消费促进政策，支持消费市场复苏'),
                ('新闻', '电商平台双十一活动启动', '各大电商平台启动双十一促销活动'),
            ],
            '医药': [
                ('政策', '医药行业监管政策调整', '国家调整医药行业监管政策，支持创新药发展'),
                ('新闻', '新药研发取得进展', '多家药企新药研发取得重要进展'),
            ],
            '金融': [
                ('政策', '金融支持实体经济政策', '央行发布金融支持实体经济发展的政策措施'),
                ('新闻', '银行数字化转型加速', '多家银行加速数字化转型，推出创新金融产品'),
            ],
            '制造': [
                ('政策', '制造业转型升级政策发布', '国家发布制造业转型升级政策，支持高端装备制造发展'),
                ('新闻', '新能源汽车销量创新高', '新能源汽车市场持续火爆，销量创历史新高'),
                ('会议', '制造业高质量发展论坛', '2025年制造业高质量发展论坛成功举办，聚焦智能制造'),
            ],
            '周期': [
                ('政策', '基础设施建设政策支持', '国家加大基础设施建设投入，支持周期行业复苏'),
                ('新闻', '钢铁行业去产能成效显著', '钢铁行业去产能工作取得重要进展，行业效益提升'),
            ],
            '能源': [
                ('政策', '新能源发展政策出台', '国家出台新能源发展政策，支持清洁能源产业发展'),
                ('新闻', '光伏产业快速发展', '光伏产业迎来快速发展期，装机容量持续增长'),
            ],
        }
        
        total_events = 0
        for sector_name, industry_codes in sector_groups.items():
            if sector_name not in event_templates:
                continue
            
            templates = event_templates[sector_name]
            
            # 为每个行业生成事件
            for industry_code in industry_codes[:2]:  # 每个板块最多2个行业
                for idx, (event_type, title, summary) in enumerate(templates):
                    # 过去30天的事件
                    event_date = today - timedelta(days=20 - idx * 5)
                    event_id = f"{window_id}_{industry_code}_{event_date.strftime('%Y%m%d')}_{idx}"
                    
                    # 检查是否已存在
                    existing = session.query(FactSectorEvent).filter(
                        FactSectorEvent.id == event_id
                    ).first()
                    
                    if existing:
                        continue
                    
                    event = FactSectorEvent(
                        id=event_id,
                        window_id=window_id,
                        sector_code=industry_code,
                        date=event_date,
                        title=title,
                        summary=summary,
                        source="示例数据",
                        event_type=event_type  # 添加事件类型
                    )
                    session.add(event)
                    total_events += 1
                    
                    # 未来30天的事件
                    if idx < len(templates) - 1:
                        future_date = today + timedelta(days=10 + idx * 5)
                        future_event_id = f"{window_id}_{industry_code}_{future_date.strftime('%Y%m%d')}_{idx}"
                        
                        existing_future = session.query(FactSectorEvent).filter(
                            FactSectorEvent.id == future_event_id
                        ).first()
                        
                        if not existing_future:
                            future_event = FactSectorEvent(
                                id=future_event_id,
                                window_id=window_id,
                                sector_code=industry_code,
                                date=future_date,
                                title=f"预期：{title}",
                                summary=f"预期事件：{summary}",
                                source="示例数据",
                                event_type=event_type,  # 添加事件类型
                                expected_impact="预期对该板块形成利好预期"  # 添加预期影响
                            )
                            session.add(future_event)
                            total_events += 1
        
        session.commit()
        logger.info(f"✅ 成功填充 {total_events} 条事件数据")
        
    except Exception as e:
        logger.error(f"❌ 填充事件数据失败: {e}", exc_info=True)
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == '__main__':
    # 先创建表
    from backend.scripts.data_fill.create_sector_tables import create_tables
    create_tables()
    
    # 然后填充数据
    fill_sector_leaders()
    fill_sector_events()
    
    logger.info("\n✅ 所有数据填充完成！")

