"""
龙头优化系统 - 快捷数据获取 API
提供一键刷新所有必要数据的功能
"""

from fastapi import APIRouter, Query, HTTPException
from typing import Dict, Optional
from datetime import date
import logging

from backend.services.leader_tracking.leader_optimization_scheduler import LeaderOptimizationScheduler
from data_warehouse.service.warehouse_service import WarehouseService
from sqlalchemy import text

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/leader-optimization", tags=["leader-optimization-quick"])


@router.post("/quick-refresh")
async def quick_refresh(
    trade_date: Optional[date] = Query(None, description="交易日期，默认今天"),
    skip_if_exists: bool = Query(True, description="如果数据已存在则跳过"),
) -> Dict:
    """
    一键刷新龙头优化系统所需的所有数据

    执行顺序：
    1. 检查并补充涨停板数据
    2. 检查并补充资金流向数据
    3. 主线雷达扫描（如果当天未扫描）
    4. 同步龙头跟踪池（计算评分、封单比、买点信号）

    示例：
        POST /api/leader-optimization/quick-refresh?trade_date=2026-03-24
    """
    if trade_date is None:
        trade_date = date.today()

    results = []
    ws = WarehouseService()
    session = ws.get_session()

    try:
        # 1. 检查涨停板数据
        result = session.execute(
            text("SELECT COUNT(*) FROM fact_limit_up_daily WHERE trade_date = :d"),
            {'d': trade_date}
        )
        limit_up_count = result.scalar() or 0

        if limit_up_count == 0 or not skip_if_exists:
            logger.info(f"补充涨停板数据: {trade_date}")
            from backend.scripts.data_fill.fill_limitup_emotion import fill_limit_up_daily
            success = fill_limit_up_daily(trade_date.strftime('%Y-%m-%d'))
            results.append({
                'step': 'limit_up_daily',
                'success': success,
                'message': '已补充涨停板数据' if success else '补充失败或无需补充',
            })
        else:
            results.append({
                'step': 'limit_up_daily',
                'success': True,
                'skipped': True,
                'message': f'涨停板数据已存在 ({limit_up_count} 条)，跳过',
            })

        # 2. 检查资金流向数据
        result = session.execute(
            text("SELECT COUNT(*) FROM fact_money_flow WHERE trade_date = :d"),
            {'d': trade_date}
        )
        money_flow_count = result.scalar() or 0

        if money_flow_count == 0 or not skip_if_exists:
            logger.info(f"补充资金流向数据: {trade_date}")
            from backend.scripts.data_update.update_money_flow_from_tushare import update_money_flow_from_tushare
            mf_result = update_money_flow_from_tushare(trade_date=trade_date)
            results.append({
                'step': 'money_flow',
                'success': mf_result.get('success', False),
                'updated': mf_result.get('updated', 0),
                'message': mf_result.get('message', ''),
            })
        else:
            results.append({
                'step': 'money_flow',
                'success': True,
                'skipped': True,
                'message': f'资金流向数据已存在 ({money_flow_count} 条)，跳过',
            })

        # 3. 检查主线雷达数据
        result = session.execute(
            text("SELECT COUNT(*) FROM fact_stock_startup_candidate WHERE trade_date = :d"),
            {'d': trade_date}
        )
        startup_count = result.scalar() or 0

        if startup_count == 0:
            results.append({
                'step': 'startup_scan',
                'success': False,
                'message': '主线雷达数据为空，请在页面刷新主线雷达后重试',
                'hint': '访问主线雷达页面并刷新，或调用 /api/startup/scan',
            })
        else:
            results.append({
                'step': 'startup_scan',
                'success': True,
                'skipped': True,
                'message': f'主线雷达数据已存在 ({startup_count} 条)',
            })

        # 4. 同步龙头跟踪池
        logger.info(f"同步龙头跟踪池: {trade_date}")
        from backend.services.leader_tracking.leader_tracking_pool_service_enhanced import LeaderTrackingPoolServiceEnhanced

        service = LeaderTrackingPoolServiceEnhanced(
            warehouse=ws,
            emotion_cycle='震荡期',
        )

        sync_result = service.sync_pool_with_scoring(
            trade_date=trade_date,
            record_failures=True,
        )

        results.append({
            'step': 'leader_pool_sync',
            'success': sync_result.get('success', False),
            'entered_count': sync_result.get('entered_count', 0),
            'failed_count': sync_result.get('failed_count', 0),
            'message': f"入池 {sync_result.get('entered_count', 0)} 只，失败 {sync_result.get('failed_count', 0)} 只",
        })

        # 检查最终结果
        result = session.execute(
            text("""
                SELECT COUNT(*),
                       SUM(CASE WHEN score IS NOT NULL THEN 1 ELSE 0 END),
                       SUM(CASE WHEN block_ratio IS NOT NULL THEN 1 ELSE 0 END),
                       SUM(CASE WHEN buy_signal IS NOT NULL THEN 1 ELSE 0 END)
                FROM fact_leader_tracking_pool
                WHERE last_seen_date = :d
            """),
            {'d': trade_date}
        )
        row = result.fetchone()

        return {
            'success': True,
            'trade_date': trade_date.isoformat(),
            'results': results,
            'summary': {
                'total_pool': row[0] or 0,
                'with_score': row[1] or 0,
                'with_block_ratio': row[2] or 0,
                'with_buy_signal': row[3] or 0,
            },
        }

    except Exception as e:
        logger.error(f"快捷刷新失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"刷新失败: {str(e)}")
    finally:
        session.close()


@router.get("/data-status")
async def get_data_status(
    trade_date: Optional[date] = Query(None, description="交易日期，默认今天"),
) -> Dict:
    """
    获取龙头优化系统数据状态

    检查以下数据是否齐全：
    - 涨停板数据 (fact_limit_up_daily)
    - 资金流向数据 (fact_money_flow)
    - 主线雷达数据 (fact_stock_startup_candidate)
    - 跟踪池数据 (fact_leader_tracking_pool)

    示例：
        GET /api/leader-optimization/data-status?trade_date=2026-03-24
    """
    if trade_date is None:
        trade_date = date.today()

    ws = WarehouseService()
    session = ws.get_session()

    try:
        status = {}

        # 1. 涨停板数据
        result = session.execute(
            text("SELECT COUNT(*) FROM fact_limit_up_daily WHERE trade_date = :d"),
            {'d': trade_date}
        )
        count = result.scalar() or 0
        status['limit_up_daily'] = {
            'exists': count > 0,
            'count': count,
            'required': True,
            'description': '涨停板数据（含封单金额）',
        }

        # 2. 资金流向数据
        result = session.execute(
            text("SELECT COUNT(*) FROM fact_money_flow WHERE trade_date = :d"),
            {'d': trade_date}
        )
        count = result.scalar() or 0
        status['money_flow'] = {
            'exists': count > 0,
            'count': count,
            'required': True,
            'description': '个股资金流向',
        }

        # 3. 主线雷达数据
        result = session.execute(
            text("SELECT COUNT(*) FROM fact_stock_startup_candidate WHERE trade_date = :d"),
            {'d': trade_date}
        )
        count = result.scalar() or 0
        status['startup_candidate'] = {
            'exists': count > 0,
            'count': count,
            'required': True,
            'description': '主线雷达扫描结果',
        }

        # 4. 跟踪池数据
        result = session.execute(
            text("""
                SELECT COUNT(*),
                       SUM(CASE WHEN score IS NOT NULL THEN 1 ELSE 0 END),
                       SUM(CASE WHEN block_ratio IS NOT NULL THEN 1 ELSE 0 END),
                       SUM(CASE WHEN buy_signal IS NOT NULL THEN 1 ELSE 0 END)
                FROM fact_leader_tracking_pool
                WHERE last_seen_date >= :d
            """),
            {'d': trade_date}
        )
        row = result.fetchone()
        status['leader_pool'] = {
            'exists': (row[0] or 0) > 0,
            'total': row[0] or 0,
            'with_score': row[1] or 0,
            'with_block_ratio': row[2] or 0,
            'with_buy_signal': row[3] or 0,
            'required': True,
            'description': '龙头跟踪池（含评分、封单比、买点）',
        }

        # 判断整体状态
        all_ready = all(s['exists'] for s in status.values() if s['required'])

        return {
            'success': True,
            'trade_date': trade_date.isoformat(),
            'all_ready': all_ready,
            'status': status,
            'suggestion': '数据已齐全，可以正常使用' if all_ready else '部分数据缺失，建议执行 quick-refresh',
        }

    except Exception as e:
        logger.error(f"获取数据状态失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取状态失败: {str(e)}")
    finally:
        session.close()
