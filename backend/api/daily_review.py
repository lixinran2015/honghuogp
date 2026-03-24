"""
每日复盘报告 API
规则：今日未收盘时不可复盘；盘中若需复盘，传 review_prev_day=1 复盘前一交易日。
"""

from fastapi import APIRouter, Query, HTTPException, Depends
from typing import Dict, Optional, List
from typing_extensions import Annotated
import logging
from datetime import date, datetime

from backend.services.analysis.daily_review_service import DailyReviewService
from backend.services.data.postgres_warehouse import PostgresWarehouse
from backend.utils.trade_date_utils import (
    is_trading_hours_cn,
    get_previous_trade_date,
)
from data_warehouse.models import FactDailyReviewReport
from sqlalchemy import select, desc
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/daily-review", tags=["daily-review"])
_warehouse = PostgresWarehouse()
_service = DailyReviewService()


def get_db_session():
    """获取数据库会话"""
    session = _warehouse.warehouse_service.SessionLocal()
    try:
        yield session
    finally:
        session.close()


def _resolve_review_date(review_prev_day: bool) -> tuple:
    """
    解析复盘日期：盘中未收盘时拒绝或使用前一交易日
    Returns:
        (review_date, is_prev_day, error_message)
        error_message 非空时表示应拒绝请求
    """
    if not is_trading_hours_cn():
        # 已收盘：复盘今日
        return date.today(), False, None
    # 盘中
    if not review_prev_day:
        return None, False, (
            "今日尚未收盘，暂不提供复盘。"
            "收盘后（15:00）可复盘今日；盘中若需复盘，请传 review_prev_day=1 复盘前一交易日。"
        )
    prev = get_previous_trade_date(_warehouse.warehouse_service) if _warehouse.warehouse_service else None
    if not prev:
        return None, False, "无法获取前一交易日，请稍后再试。"
    return prev, True, None


@router.get("/data")
async def get_review_data(
    user_id: int = Query(1, description="用户ID"),
    history_days: int = Query(30, description="历史清仓记录天数"),
    review_prev_day: bool = Query(False, description="盘中复盘时传1，复盘前一交易日"),
) -> Dict:
    """
    获取复盘报告所需的原始数据（不含 AI 生成内容）
    """
    try:
        review_date, is_prev, err = _resolve_review_date(review_prev_day)
        if err:
            raise HTTPException(status_code=400, detail=err)
        data = _service.collect_review_data(
            user_id=user_id,
            history_days=history_days,
            review_date=review_date,
            is_prev_day=is_prev,
        )
        return {"success": True, "data": data}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取复盘数据失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="获取复盘数据失败")


@router.get("/report")
async def get_ai_report(
    user_id: int = Query(1, description="用户ID"),
    history_days: int = Query(30, description="历史清仓记录天数"),
    review_prev_day: bool = Query(False, description="盘中复盘时传1，复盘前一交易日"),
) -> Dict:
    """
    获取 AI 生成的复盘报告
    """
    try:
        review_date, is_prev, err = _resolve_review_date(review_prev_day)
        if err:
            raise HTTPException(status_code=400, detail=err)
        data = _service.collect_review_data(
            user_id=user_id,
            history_days=history_days,
            review_date=review_date,
            is_prev_day=is_prev,
        )
        report = _service.generate_ai_review(data, timeout=60)
        return {
            "success": True,
            "data": data,
            "report": report,
            "generated_at": date.today().isoformat(),
            "review_date": review_date.isoformat(),
            "is_prev_day_review": is_prev,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"生成复盘报告失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="生成复盘报告失败")


@router.get("/pattern-analysis")
async def get_pattern_analysis(
    user_id: int = Query(1, description="用户ID"),
    history_days: int = Query(60, description="分析的历史天数"),
) -> Dict:
    """
    获取操作模式分析（成功/失败模式）
    """
    try:
        closed = _service.get_closed_history(user_id=user_id, days=history_days)
        records = closed.get("records", [])
        if not records:
            return {
                "success": True,
                "analysis": "暂无清仓记录，无法分析操作模式。",
                "summary": closed.get("summary", {}),
            }
        analysis = _service.generate_pattern_analysis(records, timeout=30)
        return {
            "success": True,
            "analysis": analysis or "AI 分析暂不可用",
            "summary": closed.get("summary", {}),
            "records_count": len(records),
        }
    except Exception as e:
        logger.error(f"操作模式分析失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="操作模式分析失败")


@router.get("/holdings")
async def get_holdings_performance(
    user_id: int = Query(1, description="用户ID"),
) -> Dict:
    """
    获取当前持仓表现
    """
    try:
        data = _service.get_holdings_performance(user_id)
        return {"success": True, **data}
    except Exception as e:
        logger.error(f"获取持仓表现失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="获取持仓表现失败")


@router.get("/closed-history")
async def get_closed_history(
    user_id: int = Query(1, description="用户ID"),
    days: int = Query(30, description="天数"),
) -> Dict:
    """
    获取历史清仓记录
    """
    try:
        data = _service.get_closed_history(user_id, days)
        return {"success": True, **data}
    except Exception as e:
        logger.error(f"获取清仓历史失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="获取清仓历史失败")


@router.get("/market")
async def get_market_summary() -> Dict:
    """
    获取大盘走势
    """
    try:
        data = _service.get_market_summary()
        return {"success": True, **data}
    except Exception as e:
        logger.error(f"获取大盘数据失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="获取大盘数据失败")


@router.post("/save-report")
async def save_daily_review_report(
    user_id: Annotated[int, Query(description="用户ID")] = 1,
    review_date: Annotated[Optional[date], Query(description="复盘日期，默认今日")] = None,
    report_type: Annotated[str, Query(description="报告类型：daily/pattern")] = "daily",
    is_prev_day_review: Annotated[bool, Query(description="是否为复盘前一交易日")] = False,
    session: Session = Depends(get_db_session),
) -> Dict:
    """
    保存当前AI复盘报告到数据库
    """
    try:
        # 如果没有指定日期，使用今日
        if review_date is None:
            review_date = date.today()

        # 获取复盘数据并生成报告
        data = _service.collect_review_data(
            user_id=user_id,
            history_days=30,
            review_date=review_date,
            is_prev_day=is_prev_day_review,
        )

        if report_type == "pattern":
            # 模式分析报告
            closed = _service.get_closed_history(user_id=user_id, days=60)
            records = closed.get("records", [])
            if not records:
                report_content = "暂无清仓记录，无法分析操作模式。"
            else:
                report_content = _service.generate_pattern_analysis(records, timeout=30) or "AI分析暂不可用"
        else:
            # 每日复盘报告
            report_content = _service.generate_ai_review(data, timeout=60)

        # 检查是否已存在同日期同类型的报告
        existing = session.execute(
            select(FactDailyReviewReport).where(
                FactDailyReviewReport.user_id == user_id,
                FactDailyReviewReport.review_date == review_date,
                FactDailyReviewReport.report_type == report_type,
            )
        ).scalar_one_or_none()

        if existing:
            # 更新现有报告
            existing.report_content = report_content
            existing.raw_data = data
            existing.is_prev_day_review = is_prev_day_review
            existing.updated_at = datetime.now()
            message = "报告已更新"
        else:
            # 创建新报告
            new_report = FactDailyReviewReport(
                user_id=user_id,
                review_date=review_date,
                report_type=report_type,
                report_content=report_content,
                raw_data=data,
                is_prev_day_review=is_prev_day_review,
            )
            session.add(new_report)
            message = "报告已保存"

        session.commit()
        return {
            "success": True,
            "message": message,
            "review_date": review_date.isoformat(),
            "report_type": report_type,
        }
    except Exception as e:
        logger.error(f"保存复盘报告失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="保存复盘报告失败")


@router.get("/saved-reports")
async def list_saved_reports(
    user_id: Annotated[int, Query(description="用户ID")] = 1,
    report_type: Annotated[Optional[str], Query(description="报告类型过滤：daily/pattern")] = None,
    limit: Annotated[int, Query(description="返回数量限制")] = 30,
    session: Session = Depends(get_db_session),
) -> Dict:
    """
    获取已保存的复盘报告列表
    """
    try:
        query = select(FactDailyReviewReport).where(
            FactDailyReviewReport.user_id == user_id
        )

        if report_type:
            query = query.where(FactDailyReviewReport.report_type == report_type)

        query = query.order_by(desc(FactDailyReviewReport.review_date)).limit(limit)
        results = session.execute(query).scalars().all()

        reports = []
        for r in results:
            reports.append({
                "id": r.id,
                "review_date": r.review_date.isoformat(),
                "report_type": r.report_type,
                "is_prev_day_review": r.is_prev_day_review,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "updated_at": r.updated_at.isoformat() if r.updated_at else None,
                "preview": r.report_content[:200] + "..." if len(r.report_content) > 200 else r.report_content,
            })

        return {
            "success": True,
            "reports": reports,
            "total": len(reports),
        }
    except Exception as e:
        logger.error(f"获取复盘报告列表失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="获取复盘报告列表失败")


@router.get("/saved-report/{report_id}")
async def get_saved_report(
    report_id: int,
    user_id: Annotated[int, Query(description="用户ID")] = 1,
    session: Session = Depends(get_db_session),
) -> Dict:
    """
    获取指定ID的已保存复盘报告详情
    """
    try:
        report = session.execute(
            select(FactDailyReviewReport).where(
                FactDailyReviewReport.id == report_id,
                FactDailyReviewReport.user_id == user_id,
            )
        ).scalar_one_or_none()

        if not report:
            raise HTTPException(status_code=404, detail="报告不存在")

        return {
            "success": True,
            "report": {
                "id": report.id,
                "review_date": report.review_date.isoformat(),
                "report_type": report.report_type,
                "report_content": report.report_content,
                "raw_data": report.raw_data,
                "is_prev_day_review": report.is_prev_day_review,
                "created_at": report.created_at.isoformat() if report.created_at else None,
                "updated_at": report.updated_at.isoformat() if report.updated_at else None,
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取复盘报告详情失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="获取复盘报告详情失败")


@router.delete("/saved-report/{report_id}")
async def delete_saved_report(
    report_id: int,
    user_id: Annotated[int, Query(description="用户ID")] = 1,
    session: Session = Depends(get_db_session),
) -> Dict:
    """
    删除指定的复盘报告
    """
    try:
        report = session.execute(
            select(FactDailyReviewReport).where(
                FactDailyReviewReport.id == report_id,
                FactDailyReviewReport.user_id == user_id,
            )
        ).scalar_one_or_none()

        if not report:
            raise HTTPException(status_code=404, detail="报告不存在")

        session.delete(report)
        session.commit()

        return {
            "success": True,
            "message": "报告已删除",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除复盘报告失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="删除复盘报告失败")
