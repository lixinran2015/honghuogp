"""
龙头跟踪池 API
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Query, HTTPException

from backend.services.leader_tracking.leader_tracking_pool_service import LeaderTrackingPoolService
from backend.services.leader_tracking.leader_recent_days_service import LeaderRecentDaysService

router = APIRouter(prefix="/api/leader-tracking", tags=["leader-tracking"])


@router.get("/pool")
async def get_leader_tracking_pool(
  trade_date: Optional[str] = Query(
    None,
    description="交易日，YYYY-MM-DD；不传则取最新交易日",
  ),
  min_score: int = Query(60, description="启动得分阈值"),
  stage: str = Query("confirmed", description="阶段过滤：confirmed / started"),
  stable_window_id: str = Query("rolling_30d_v2", description="快照窗口：用于判断空间/刚启动角色的稳定性"),
  bootstrap_days: int = Query(180, description="池为空时的历史补齐天数（只用于首次初始化）"),
  do_bootstrap: bool = Query(True, description="是否在池为空时自动 bootstrap"),
  force_sync: bool = Query(False, description="是否强制重新同步当天（会跳过 sync log）"),
  catch_up_window_trading_days: int = Query(
    30,
    ge=0,
    le=120,
    description="补同步：向前查看多少个交易日内的 sync 缺口（0 表示不补历史，仅同步 end 日）",
  ),
  catch_up_max_syncs: int = Query(
    30,
    ge=0,
    le=30,
    description="补同步：单次请求最多补跑几个缺失交易日（默认与窗口一致，一次补满近 30 个交易日缺口）",
  ),
  replay_sync_days: int = Query(
    0,
    ge=0,
    le=60,
    description="为 >0 时先删除最近 n 个交易日的 sync_log 再补跑（入池规则变更或需重灌历史时用）",
  ),
) -> dict:
  svc = LeaderTrackingPoolService()
  # 简单参数校验
  if stage not in ("confirmed", "started"):
    raise HTTPException(status_code=400, detail="stage 仅支持 confirmed / started")

  td = None
  if trade_date:
    try:
      td = date.fromisoformat(trade_date)
    except ValueError:
      raise HTTPException(status_code=400, detail="trade_date 格式错误，应为 YYYY-MM-DD")

  return svc.get_pool(
    trade_date=td,
    min_score=min_score,
    stage_filter=stage,
    stable_window_id=stable_window_id,
    bootstrap_days=bootstrap_days,
    do_bootstrap=do_bootstrap,
    force_sync=force_sync,
    catch_up_window_trading_days=catch_up_window_trading_days,
    catch_up_max_syncs=catch_up_max_syncs,
    replay_sync_days=replay_sync_days,
  )


@router.get("/recent-days")
async def get_leader_tracking_recent_days(
  end_date: Optional[str] = Query(
    None,
    description="截止交易日 YYYY-MM-DD；不传则取最近交易日",
  ),
  trading_days: int = Query(10, ge=1, le=60, description="向前取几个交易日（含 end_date）"),
  min_score: int = Query(60, description="启动得分阈值"),
  stage: str = Query("confirmed", description="阶段过滤：confirmed / started"),
  stable_window_id: str = Query("rolling_30d_v2", description="龙头快照窗口"),
  include_status: bool = Query(True, description="是否计算当日强势/震荡/退潮风险（与龙头跟踪页一致）"),
) -> dict:
  if stage not in ("confirmed", "started"):
    raise HTTPException(status_code=400, detail="stage 仅支持 confirmed / started")

  ed: Optional[date] = None
  if end_date:
    try:
      ed = date.fromisoformat(end_date)
    except ValueError:
      raise HTTPException(status_code=400, detail="end_date 格式错误，应为 YYYY-MM-DD")

  svc = LeaderRecentDaysService()
  return svc.get_recent_days(
    end_date=ed,
    trading_days=trading_days,
    min_score=min_score,
    stage_filter=stage,
    stable_window_id=stable_window_id,
    include_status=include_status,
  )

