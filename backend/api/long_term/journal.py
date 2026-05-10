"""
长线投资日志 API

路由:
- GET /journal          查询投资日志
- POST /journal         添加投资日志
- GET /journal/stats    获取日志统计
"""

from fastapi import APIRouter, Query
from pydantic import BaseModel
from typing import List, Optional
from datetime import date

from backend.services.long_term.long_term_journal import LongTermJournal
from data_warehouse.service.warehouse_service import WarehouseService

router = APIRouter()


class JournalEntryCreate(BaseModel):
    ts_code: str
    action: str  # buy/add/reduce/sell/hold_review
    trade_date: date
    price: Optional[float] = None
    shares: Optional[int] = None
    weight_change: Optional[float] = None
    reason: Optional[str] = None
    darwin_score: Optional[float] = None
    pe_percentile: Optional[float] = None
    pb_percentile: Optional[float] = None
    market_trend: Optional[str] = None
    emotion_cycle: Optional[str] = None


@router.get("/journal")
async def get_journal(
    ts_code: Optional[str] = None,
    action: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """查询投资日志"""
    warehouse = WarehouseService()
    journal = LongTermJournal(warehouse)

    entries = journal.get_entries(
        ts_code=ts_code,
        action=action,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset,
    )

    return {"entries": entries, "count": len(entries)}


@router.post("/journal")
async def create_journal_entry(entry: JournalEntryCreate):
    """添加投资日志记录"""
    warehouse = WarehouseService()
    journal = LongTermJournal(warehouse)

    result = journal.add_entry(
        ts_code=entry.ts_code,
        action=entry.action,
        trade_date=entry.trade_date,
        price=entry.price,
        shares=entry.shares,
        weight_change=entry.weight_change,
        reason=entry.reason,
        darwin_score=entry.darwin_score,
        pe_percentile=entry.pe_percentile,
        pb_percentile=entry.pb_percentile,
        market_trend=entry.market_trend,
        emotion_cycle=entry.emotion_cycle,
    )

    return result


@router.get("/journal/stats")
async def get_journal_stats(ts_code: Optional[str] = None):
    """获取投资日志统计"""
    warehouse = WarehouseService()
    journal = LongTermJournal(warehouse)

    stats = journal.get_stats(ts_code=ts_code)
    return stats
