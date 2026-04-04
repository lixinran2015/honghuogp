# backend/scripts/migrate_scheduled_tasks.py
"""
迁移脚本：合并旧定时任务为统一任务，并删除已下线任务

用法：
    python backend/scripts/migrate_scheduled_tasks.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from data_warehouse.db import get_session
from data_warehouse.models import DimScheduledTask

session = get_session()

# 合并规则：旧任务名 -> (新任务名, 新显示名, 新类型)
MERGE_MAP = {
    'recommendation_daily_track': ('recommendation_daily', '推荐系统日终维护', 'recommendation_daily'),
    'recommendation_auto_close': ('recommendation_daily', '推荐系统日终维护', 'recommendation_daily'),
    'north_holding_update': ('north_money_update', '北向资金更新', 'north_money_update'),
    'north_flow_update': ('north_money_update', '北向资金更新', 'north_money_update'),
    'sector_heat_update': ('sector_daily_maintenance', '板块日终维护', 'sector_daily_maintenance'),
    'sector_leaders_update': ('sector_daily_maintenance', '板块日终维护', 'sector_daily_maintenance'),
    'sector_daily_update': ('sector_daily_maintenance', '板块日终维护', 'sector_daily_maintenance'),
}

# 已下线任务：直接删除
DEPRECATED = ['limit_up_volume_shrink']

try:
    # 1. 处理合并
    for old_name, (new_name, display_name, task_type) in MERGE_MAP.items():
        old_task = session.query(DimScheduledTask).filter_by(task_name=old_name).first()
        if not old_task:
            print(f'⏭️  跳过不存在的旧任务: {old_name}')
            continue

        # 检查是否已经有统一任务
        unified = session.query(DimScheduledTask).filter_by(task_name=new_name).first()
        if not unified:
            # 用旧任务的配置创建新统一任务
            unified = DimScheduledTask(
                task_name=new_name,
                task_display_name=display_name,
                task_description=f'已合并：{old_name} 等旧任务',
                schedule_time=old_task.schedule_time,
                schedule_days=old_task.schedule_days,
                cron_expression=old_task.cron_expression,
                is_enabled=old_task.is_enabled,
                task_type=task_type,
            )
            session.add(unified)
            print(f'✅ 创建统一任务: {new_name}')
        else:
            print(f'⚠️ 统一任务已存在: {new_name}，跳过创建')

        # 删除旧任务
        session.delete(old_task)
        print(f'🗑️  删除旧任务: {old_name}')

    # 2. 处理已下线
    for name in DEPRECATED:
        t = session.query(DimScheduledTask).filter_by(task_name=name).first()
        if t:
            session.delete(t)
            print(f'🗑️  删除已下线任务: {name}')
        else:
            print(f'⏭️  跳过不存在的已下线任务: {name}')

    session.commit()
    print('\n迁移完成，请刷新前端页面查看效果。')
except Exception as e:
    session.rollback()
    print(f'\n❌ 迁移失败: {e}')
    raise
finally:
    session.close()
