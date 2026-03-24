"""
初始化定时任务配置
"""

import logging
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from data_warehouse.service.warehouse_service import WarehouseService
from data_warehouse.models.scheduled_task import DimScheduledTask
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def init_scheduled_tasks():
    """初始化默认的定时任务配置"""
    
    # 默认任务配置
    default_tasks = [
        {
            'task_name': 'daily_update',
            'task_display_name': '日线数据更新',
            'task_description': '更新股票日线数据（从快照表更新）',
            'schedule_time': '15:30',
            'schedule_days': '1-5',  # 周一到周五
            'is_enabled': True,
            'task_type': 'daily_update',
        },
        {
            'task_name': 'fundamental_update',
            'task_display_name': '财务数据更新',
            'task_description': '更新股票财务数据',
            'schedule_time': '16:00',
            'schedule_days': '1',  # 周一
            'is_enabled': True,
            'task_type': 'fundamental_update',
        },
        {
            'task_name': 'refresh_snapshot',
            'task_display_name': '股票快照刷新',
            'task_description': '刷新股票快照并生成推荐',
            'schedule_time': '09:15',
            'schedule_days': '1-5',  # 周一到周五
            'is_enabled': True,
            'task_type': 'refresh_snapshot',
        },
        {
            'task_name': 'sector_heat_update',
            'task_display_name': '板块热度更新',
            'task_description': '更新板块热度快照',
            'schedule_time': '15:00',
            'schedule_days': '1-5',  # 周一到周五
            'is_enabled': True,
            'task_type': 'sector_heat_update',
        },
        {
            'task_name': 'sector_leaders_update',
            'task_display_name': '板块龙头更新',
            'task_description': '更新板块龙头快照',
            'schedule_time': '15:30',
            'schedule_days': '1-5',  # 周一到周五
            'is_enabled': True,
            'task_type': 'sector_leaders_update',
        },
        {
            'task_name': 'sync_stock',
            'task_display_name': '更新股票列表',
            'task_description': '同步股票基础信息（代码、名称等）',
            'schedule_time': '09:00',
            'schedule_days': '1',  # 周一
            'is_enabled': True,
            'task_type': 'sync_stock',
        },
        {
            'task_name': 'sync_industry',
            'task_display_name': '申万行业同步',
            'task_description': '将 dim_stock.industry 同步为申万一级行业分类',
            'schedule_time': '15:00',
            'schedule_days': '1-5',
            'is_enabled': True,
            'task_type': 'sync_industry',
        },
        {
            'task_name': 'industry_cycle_collect',
            'task_display_name': '行业周期数据采集',
            'task_description': '采集行业指数、营收增速、净现比分布等，供规则引擎使用（含申万行业同步）',
            'schedule_time': '15:30',
            'schedule_days': '1-5',
            'is_enabled': True,
            'task_type': 'industry_cycle_collect',
        },
        {
            'task_name': 'industry_cycle_suggest',
            'task_display_name': '行业周期建议生成',
            'task_description': '基于当日 cycle_data 生成 suggest_YYYYMMDD.json，供选股等行业周期筛选使用（周一早 8 点执行）',
            'schedule_time': '08:00',
            'schedule_days': '1',
            'is_enabled': True,
            'task_type': 'industry_cycle_suggest',
        },
        {
            'task_name': 'sync_trade_calendar',
            'task_display_name': '同步交易日历',
            'task_description': '从Tushare同步交易日历数据',
            'schedule_time': '08:00',
            'schedule_days': '1',  # 周一
            'is_enabled': True,
            'task_type': 'sync_trade_calendar',
        },
        {
            'task_name': 'guba_popularity_crawl_morning',
            'task_display_name': '股吧人气榜爬虫（早上）',
            'task_description': '爬取股吧人气排行榜数据（每天早上9点执行）',
            'schedule_time': '09:00',
            'schedule_days': '1-5',  # 周一到周五
            'is_enabled': True,
            'task_type': 'guba_popularity_crawl',
        },
        {
            'task_name': 'guba_popularity_crawl_noon',
            'task_display_name': '股吧人气榜爬虫（中午）',
            'task_description': '爬取股吧人气排行榜数据（每天中午12点执行）',
            'schedule_time': '12:00',
            'schedule_days': '1-5',  # 周一到周五
            'is_enabled': True,
            'task_type': 'guba_popularity_crawl',
        },
        {
            'task_name': 'limit_up_volume_shrink',
            'task_display_name': '涨停缩量计算',
            'task_description': '计算最近5天有涨停且量比<0.6的主板股票',
            'schedule_time': '15:30',
            'schedule_days': '1-5',  # 周一到周五
            'is_enabled': True,
            'task_type': 'limit_up_volume_shrink',
        },
        {
            'task_name': 's1_universe_update',
            'task_display_name': 'S1股票池更新',
            'task_description': '更新S1（新高策略）股票池，确保在快照刷新前数据是最新的',
            'schedule_time': '09:10',  # 在refresh_snapshot（09:15）之前5分钟执行
            'schedule_days': '1-5',  # 周一到周五
            'is_enabled': True,
            'task_type': 's1_universe_update',
        },
        {
            'task_name': 'pe_pb_update',
            'task_display_name': 'PE/PB 更新（Tushare）',
            'task_description': '从 Tushare daily_basic 拉取当日 PE/PB，更新 fact_daily_price_qfq 与 fact_daily_fundamental（建议 17:30 后执行）',
            'schedule_time': '17:30',
            'schedule_days': '1-5',
            'is_enabled': True,
            'task_type': 'pe_pb_update',
        },
        {
            'task_name': 'abnormal_analysis_scan',
            'task_display_name': '异动分析扫描',
            'task_description': '收盘后扫描当日异动股票，获取新闻/公告/龙虎榜/大宗交易，AI 分析异动原因',
            'schedule_time': '15:45',
            'schedule_days': '1-5',  # 周一到周五
            'is_enabled': True,
            'task_type': 'abnormal_analysis_scan',
        },
        {
            'task_name': 'recommendation_daily_track',
            'task_display_name': '推荐效果追踪',
            'task_description': '每日收盘后更新所有活跃推荐的表现数据（收益率、最大涨幅、最大回撤等）',
            'schedule_time': '15:30',
            'schedule_days': '1-5',  # 周一到周五
            'is_enabled': True,
            'task_type': 'recommendation_daily_track',
        },
        {
            'task_name': 'recommendation_auto_close',
            'task_display_name': '推荐自动平仓',
            'task_description': '自动平仓触及止损或止盈目标的推荐股票',
            'schedule_time': '15:35',
            'schedule_days': '1-5',  # 周一到周五
            'is_enabled': True,
            'task_type': 'recommendation_auto_close',
        },
        {
            'task_name': 'money_flow_update',
            'task_display_name': '个股主力资金更新',
            'task_description': '从 Tushare moneyflow 拉取个股主力资金流向，写入 fact_money_flow（建议 17:30 后执行）',
            'schedule_time': '17:35',
            'schedule_days': '1-5',
            'is_enabled': True,
            'task_type': 'money_flow_update',
        },
        {
            'task_name': 'north_holding_update',
            'task_display_name': '北向持股更新',
            'task_description': '从 Tushare hk_hold 拉取北向资金个股持仓，写入 fact_north_holding（注：2024-08-20 后日度停更）',
            'schedule_time': '17:40',
            'schedule_days': '1-5',
            'is_enabled': True,
            'task_type': 'north_holding_update',
        },
        {
            'task_name': 'north_flow_update',
            'task_display_name': '北向资金净流入更新',
            'task_description': '从 Tushare moneyflow_hsgt 拉取北向资金市场净流入，写入 fact_north_flow（用于市场环境分析）',
            'schedule_time': '17:45',
            'schedule_days': '1-5',
            'is_enabled': True,
            'task_type': 'north_flow_update',
        },
        {
            'task_name': 'sector_daily_update',
            'task_display_name': '板块日线更新',
            'task_description': '更新 fact_sector_daily（Tushare 申万行业日线），用于长期主题轮动/明日预测领涨',
            'schedule_time': '15:30',
            'schedule_days': '1-5',
            'is_enabled': True,
            'task_type': 'sector_daily_update',
        },
    ]
    
    ws = WarehouseService()
    session = ws.get_session()
    
    try:
        total_added = 0
        total_updated = 0
        
        for task_config in default_tasks:
            task_name = task_config['task_name']
            
            # 检查是否已存在
            existing = session.query(DimScheduledTask).filter(
                DimScheduledTask.task_name == task_name
            ).first()
            
            if existing:
                # 更新现有任务
                for key, value in task_config.items():
                    if hasattr(existing, key):
                        setattr(existing, key, value)
                existing.updated_at = datetime.now()
                total_updated += 1
                logger.info(f"🔄 更新任务配置: {task_name}")
            else:
                # 创建新任务
                new_task = DimScheduledTask(**task_config)
                session.add(new_task)
                total_added += 1
                logger.info(f"➕ 创建任务配置: {task_name}")
        
        session.commit()
        logger.info(f"✅ 初始化完成: 新增 {total_added} 个任务，更新 {total_updated} 个任务")
        
    except Exception as e:
        session.rollback()
        logger.error(f"❌ 初始化失败: {e}", exc_info=True)
        raise
    finally:
        session.close()


if __name__ == "__main__":
    init_scheduled_tasks()

