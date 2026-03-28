"""
因子验证系统 API
Phase 1: 因子有效性验证

提供以下端点：
- POST /api/factor-validation/run - 运行因子验证
- GET /api/factor-validation/results/{task_id} - 获取验证结果
- GET /api/factor-validation/report/{task_id} - 获取HTML报告
- GET /api/factor-validation/status - 查看系统状态
"""

from fastapi import APIRouter, Query, HTTPException, BackgroundTasks
from typing import Dict, List, Optional
from datetime import date
import logging
import asyncio

from backend.services.factor_validation import (
    FactorValidator,
    FactorReportGenerator,
    run_factor_validation,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/factor-validation", tags=["factor-validation"])

# 存储运行中的任务（生产环境应使用Redis）
_task_store: Dict[str, dict] = {}


@router.post("/run")
async def run_validation(
    background_tasks: BackgroundTasks,
    start_date: Optional[date] = Query(None, description="开始日期，默认一年前"),
    end_date: Optional[date] = Query(None, description="结束日期，默认今天"),
    forward_days: int = Query(5, description="预测未来N日收益率", ge=1, le=20),
) -> Dict:
    """
    启动因子验证任务

    该任务会：
    1. 获取龙头跟踪系统的四大因子历史数据
    2. 进行IC分析（信息系数）
    3. 进行分层回测
    4. 进行VIF多重共线性检验
    5. 生成综合报告

    示例:
    ```
    POST /api/factor-validation/run?start_date=2025-01-01&end_date=2026-03-28
    ```
    """
    try:
        task_id = f"factor_val_{date.today().strftime('%Y%m%d')}_{len(_task_store)}"

        _task_store[task_id] = {
            'status': 'running',
            'progress': 0,
            'start_date': start_date,
            'end_date': end_date,
            'result': None,
            'error': None,
        }

        # 在后台运行验证
        background_tasks.add_task(
            _run_validation_task,
            task_id,
            start_date,
            end_date,
            forward_days,
        )

        return {
            'success': True,
            'task_id': task_id,
            'message': '因子验证任务已启动',
            'check_url': f'/api/factor-validation/results/{task_id}',
        }

    except Exception as e:
        logger.error(f"启动因子验证失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"启动失败: {str(e)}")


async def _run_validation_task(
    task_id: str,
    start_date: Optional[date],
    end_date: Optional[date],
    forward_days: int,
):
    """后台运行验证任务"""
    try:
        from data_warehouse.service.warehouse_service import WarehouseService

        validator = FactorValidator(WarehouseService())
        generator = FactorReportGenerator()

        # 更新进度
        _task_store[task_id]['progress'] = 10
        _task_store[task_id]['message'] = '正在获取因子数据...'

        # 获取因子数据
        factor_data = validator.get_leader_tracking_factors(start_date, end_date)

        if not factor_data:
            _task_store[task_id]['status'] = 'failed'
            _task_store[task_id]['error'] = '未获取到因子数据，请检查fact_leader_score_history表'
            return

        _task_store[task_id]['progress'] = 30
        _task_store[task_id]['message'] = f'已获取{len(factor_data)}个因子，正在进行IC分析...'

        # 验证因子
        results = validator.validate_multiple(factor_data, forward_days)

        _task_store[task_id]['progress'] = 70
        _task_store[task_id]['message'] = '正在生成报告...'

        # 生成各种格式的报告
        html_report = generator.generate_html_report(results)
        json_report = generator.generate_json_report(results)
        md_report = generator.generate_markdown_report(results)

        # 保存结果
        _task_store[task_id].update({
            'status': 'completed',
            'progress': 100,
            'message': '验证完成',
            'result': {
                'json': json_report,
                'html': html_report,
                'markdown': md_report,
            },
            'summary': {
                'total_factors': len(results),
                'valid_factors': sum(1 for r in results.values() if r.overall_grade in ['A', 'B']),
                'grade_distribution': {
                    'A': sum(1 for r in results.values() if r.overall_grade == 'A'),
                    'B': sum(1 for r in results.values() if r.overall_grade == 'B'),
                    'C': sum(1 for r in results.values() if r.overall_grade == 'C'),
                },
            },
        })

        logger.info(f"因子验证任务 {task_id} 完成")

    except Exception as e:
        logger.error(f"因子验证任务失败: {e}", exc_info=True)
        _task_store[task_id]['status'] = 'failed'
        _task_store[task_id]['error'] = str(e)


@router.get("/results/{task_id}")
async def get_validation_results(task_id: str) -> Dict:
    """获取验证结果（JSON格式）"""
    if task_id not in _task_store:
        raise HTTPException(status_code=404, detail="任务不存在")

    task = _task_store[task_id]

    if task['status'] == 'failed':
        return {
            'success': False,
            'task_id': task_id,
            'status': 'failed',
            'error': task.get('error', '未知错误'),
        }

    if task['status'] == 'running':
        return {
            'success': True,
            'task_id': task_id,
            'status': 'running',
            'progress': task['progress'],
            'message': task.get('message', '处理中...'),
        }

    # completed
    return {
        'success': True,
        'task_id': task_id,
        'status': 'completed',
        'summary': task.get('summary', {}),
        'data': task['result']['json'],
    }


@router.get("/report/{task_id}")
async def get_html_report(task_id: str) -> str:
    """获取HTML格式的验证报告"""
    if task_id not in _task_store:
        raise HTTPException(status_code=404, detail="任务不存在")

    task = _task_store[task_id]

    if task['status'] == 'failed':
        return f"""
        <html><body>
            <h1>验证失败</h1>
            <p>{task.get('error', '未知错误')}</p>
        </body></html>
        """

    if task['status'] == 'running':
        return f"""
        <html><body>
            <h1>正在处理中...</h1>
            <p>进度: {task['progress']}%</p>
            <p>{task.get('message', '请稍候...')}</p>
            <meta http-equiv="refresh" content="3">
        </body></html>
        """

    return task['result']['html']


@router.get("/quick-test")
async def quick_validation_test() -> Dict:
    """
    快速验证测试（使用最近30天数据）

    用于快速验证系统是否正常工作
    """
    try:
        from data_warehouse.service.warehouse_service import WarehouseService

        validator = FactorValidator(WarehouseService())

        # 获取最近30天的数据
        end_date = date.today()
        start_date = end_date - __import__('datetime').timedelta(days=30)

        factor_data = validator.get_leader_tracking_factors(start_date, end_date)

        if not factor_data:
            return {
                'success': False,
                'error': '未获取到因子数据，请先运行龙头评分同步',
            }

        # 只验证第一个因子作为测试
        first_factor = list(factor_data.keys())[0]
        result = validator.validate(
            factor_name=first_factor,
            factor_data=factor_data[first_factor],
        )

        return {
            'success': True,
            'test_factor': first_factor,
            'result': result.to_dict(),
            'message': '快速测试完成，系统运行正常',
        }

    except Exception as e:
        logger.error(f"快速测试失败: {e}", exc_info=True)
        return {
            'success': False,
            'error': str(e),
        }


@router.get("/status")
async def get_system_status() -> Dict:
    """获取因子验证系统状态"""
    return {
        'success': True,
        'active_tasks': sum(1 for t in _task_store.values() if t['status'] == 'running'),
        'completed_tasks': sum(1 for t in _task_store.values() if t['status'] == 'completed'),
        'failed_tasks': sum(1 for t in _task_store.values() if t['status'] == 'failed'),
        'total_tasks': len(_task_store),
    }
