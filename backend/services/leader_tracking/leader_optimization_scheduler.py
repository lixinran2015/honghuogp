#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
龙头优化系统 - 定时任务调度器
整合所有必要的数据获取和评分计算任务
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import logging
from datetime import date, datetime, time
from typing import Dict, Any, Optional

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class LeaderOptimizationScheduler:
    """
    龙头优化系统定时任务调度器

    数据依赖链：
    1. 日线数据 (daily_update) - 15:30
    2. 涨停板数据 (limit_up_daily) - 15:35
    3. 资金流向 (money_flow_update) - 17:35
    4. 主线雷达扫描 (startup_scan) - 17:40
    5. 龙头跟踪池同步 (leader_pool_sync) - 17:45
    """

    def __init__(self):
        self.tasks = {
            'limit_up_daily': {
                'name': 'limit_up_daily',
                'display_name': '涨停板数据更新',
                'schedule_time': '15:35',
                'schedule_days': '1-5',
                'handler': self._update_limit_up_daily,
                'description': '从AKShare获取涨停板数据，包含封单金额(seal_amount)',
            },
            'leader_pool_sync': {
                'name': 'leader_pool_sync',
                'display_name': '龙头跟踪池同步',
                'schedule_time': '17:45',
                'schedule_days': '1-5',
                'handler': self._sync_leader_pool,
                'description': '同步龙头跟踪池，计算评分、封单比、买点信号',
            },
            'startup_scan': {
                'name': 'startup_scan',
                'display_name': '主线雷达扫描',
                'schedule_time': '17:40',
                'schedule_days': '1-5',
                'handler': self._scan_startup,
                'description': '扫描股票启动候选，保存到fact_stock_startup_candidate',
            },
        }

    def _update_limit_up_daily(self, trade_date: Optional[date] = None) -> Dict[str, Any]:
        """更新涨停板数据"""
        from backend.scripts.data_fill.fill_limitup_emotion import fill_limit_up_daily

        if trade_date is None:
            trade_date = date.today()

        try:
            success = fill_limit_up_daily(trade_date.strftime('%Y-%m-%d'))
            return {
                'success': success,
                'task': 'limit_up_daily',
                'trade_date': trade_date.isoformat(),
            }
        except Exception as e:
            logger.error(f"更新涨停板数据失败: {e}")
            return {
                'success': False,
                'task': 'limit_up_daily',
                'error': str(e),
            }

    def _update_money_flow(self, trade_date: Optional[date] = None) -> Dict[str, Any]:
        """更新资金流向数据"""
        from backend.scripts.data_update.update_money_flow_from_tushare import update_money_flow_from_tushare

        try:
            result = update_money_flow_from_tushare(trade_date=trade_date)
            return {
                'success': result.get('success', False),
                'task': 'money_flow_update',
                'updated': result.get('updated', 0),
                'message': result.get('message', ''),
            }
        except Exception as e:
            logger.error(f"更新资金流向失败: {e}")
            return {
                'success': False,
                'task': 'money_flow_update',
                'error': str(e),
            }

    def _scan_startup(self, trade_date: Optional[date] = None) -> Dict[str, Any]:
        """主线雷达扫描"""
        from backend.services.stock.stock_startup_filter import StockStartupFilter
        from data_warehouse.service.warehouse_service import WarehouseService
        from backend.services.stock.stock_universe_service import StockUniverseService

        if trade_date is None:
            trade_date = date.today()

        try:
            ws = WarehouseService()
            universe_service = StockUniverseService()

            # 获取主板股票池
            stock_codes = universe_service.get_universe_stocks('mainboard', active_only=True)

            # 执行扫描
            startup_filter = StockStartupFilter(warehouse_service=ws)
            result_df = startup_filter.batch_filter_startups(stock_codes, trade_date.strftime('%Y-%m-%d'))

            return {
                'success': True,
                'task': 'startup_scan',
                'trade_date': trade_date.isoformat(),
                'scanned_count': len(stock_codes),
                'candidate_count': len(result_df),
            }
        except Exception as e:
            logger.error(f"主线雷达扫描失败: {e}")
            return {
                'success': False,
                'task': 'startup_scan',
                'error': str(e),
            }

    def _sync_leader_pool(self, trade_date: Optional[date] = None) -> Dict[str, Any]:
        """同步龙头跟踪池"""
        from backend.services.leader_tracking.leader_tracking_pool_service_enhanced import LeaderTrackingPoolServiceEnhanced
        from data_warehouse.service.warehouse_service import WarehouseService

        if trade_date is None:
            trade_date = date.today()

        try:
            ws = WarehouseService()
            service = LeaderTrackingPoolServiceEnhanced(
                warehouse=ws,
                emotion_cycle='震荡期',
            )

            result = service.sync_pool_with_scoring(
                trade_date=trade_date,
                record_failures=True,
            )

            return {
                'success': result.get('success', False),
                'task': 'leader_pool_sync',
                'trade_date': trade_date.isoformat(),
                'entered_count': result.get('entered_count', 0),
                'failed_count': result.get('failed_count', 0),
            }
        except Exception as e:
            logger.error(f"同步龙头跟踪池失败: {e}")
            return {
                'success': False,
                'task': 'leader_pool_sync',
                'error': str(e),
            }

    def run_task(self, task_name: str, trade_date: Optional[date] = None) -> Dict[str, Any]:
        """运行指定任务"""
        task = self.tasks.get(task_name)
        if not task:
            return {
                'success': False,
                'error': f'未知任务: {task_name}',
            }

        logger.info(f"执行任务: {task['display_name']}")
        return task['handler'](trade_date)

    def run_all(self, trade_date: Optional[date] = None) -> Dict[str, Any]:
        """按顺序运行所有任务"""
        results = []

        # 1. 更新涨停板数据
        results.append(self._update_limit_up_daily(trade_date))

        # 2. 更新资金流向（如果money_flow_update定时任务未运行）
        # results.append(self._update_money_flow(trade_date))

        # 3. 主线雷达扫描
        results.append(self._scan_startup(trade_date))

        # 4. 同步龙头跟踪池
        results.append(self._sync_leader_pool(trade_date))

        success_count = sum(1 for r in results if r.get('success'))

        return {
            'success': success_count == len(results),
            'results': results,
            'success_count': success_count,
            'total_count': len(results),
        }

    def get_task_configs(self) -> Dict[str, Dict]:
        """获取任务配置（用于数据库初始化）"""
        configs = {}
        for name, task in self.tasks.items():
            configs[name] = {
                'task_name': name,
                'task_display_name': task['display_name'],
                'task_description': task['description'],
                'schedule_time': task['schedule_time'],
                'schedule_days': task['schedule_days'],
                'task_type': 'leader_optimization',
                'is_enabled': True,
            }
        return configs


def init_leader_optimization_tasks():
    """初始化龙头优化系统定时任务到数据库"""
    from data_warehouse.service.warehouse_service import WarehouseService
    from data_warehouse.models.scheduled_task import DimScheduledTask

    ws = WarehouseService()
    session = ws.get_session()

    scheduler = LeaderOptimizationScheduler()
    configs = scheduler.get_task_configs()

    try:
        created_count = 0
        updated_count = 0

        for name, config in configs.items():
            existing = session.query(DimScheduledTask).filter(
                DimScheduledTask.task_name == name
            ).first()

            if existing:
                # 更新现有任务
                existing.task_display_name = config['task_display_name']
                existing.task_description = config['task_description']
                existing.schedule_time = config['schedule_time']
                existing.schedule_days = config['schedule_days']
                existing.task_type = config['task_type']
                existing.is_enabled = config['is_enabled']
                updated_count += 1
                logger.info(f"更新任务: {name}")
            else:
                # 创建新任务
                new_task = DimScheduledTask(**config)
                session.add(new_task)
                created_count += 1
                logger.info(f"创建任务: {name}")

        session.commit()
        logger.info(f"任务初始化完成: 创建 {created_count} 个, 更新 {updated_count} 个")

        return {
            'success': True,
            'created': created_count,
            'updated': updated_count,
        }

    except Exception as e:
        session.rollback()
        logger.error(f"初始化任务失败: {e}")
        return {
            'success': False,
            'error': str(e),
        }
    finally:
        session.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='龙头优化系统定时任务')
    parser.add_argument('--init', action='store_true', help='初始化定时任务配置到数据库')
    parser.add_argument('--run', type=str, help='运行指定任务 (limit_up_daily|startup_scan|leader_pool_sync)')
    parser.add_argument('--run-all', action='store_true', help='运行所有任务')
    parser.add_argument('--date', type=str, help='指定日期 YYYY-MM-DD，默认今天')

    args = parser.parse_args()

    target_date = None
    if args.date:
        target_date = datetime.strptime(args.date, '%Y-%m-%d').date()

    if args.init:
        result = init_leader_optimization_tasks()
        print(f"初始化结果: {result}")
    elif args.run:
        scheduler = LeaderOptimizationScheduler()
        result = scheduler.run_task(args.run, target_date)
        print(f"任务结果: {result}")
    elif args.run_all:
        scheduler = LeaderOptimizationScheduler()
        result = scheduler.run_all(target_date)
        print(f"所有任务结果: {result}")
    else:
        parser.print_help()
