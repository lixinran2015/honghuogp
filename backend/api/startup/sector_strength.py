"""
启动龙头板块强度 API

将每日启动候选信号按「行业 / 题材」聚合成板块强度，帮助识别当前主线与次主线。
"""

from datetime import datetime, date, timedelta
from typing import Optional, Dict

from fastapi import APIRouter, HTTPException, Query
import logging

from data_warehouse.service.warehouse_service import WarehouseService
from backend.services.stock.startup_sector_analyzer import StartupSectorAnalyzer

# 注意：此处前缀只写子路径，由 startup.__init__.py 统一挂载到 /api/startup
router = APIRouter(prefix="/sector-strength", tags=["startup-sector"])
logger = logging.getLogger(__name__)


@router.get("")
async def get_startup_sector_strength(
  start_date: Optional[str] = Query(
    None, description="开始日期，YYYY-MM-DD，默认 end_date 往前 5 天"
  ),
  end_date: Optional[str] = Query(
    None, description="结束日期，YYYY-MM-DD，默认今天"
  ),
  min_score: int = Query(60, description="最低得分（默认60，仅统计核心启动信号）"),
  stage: Optional[str] = Query(
    None, description="阶段过滤：confirmed(启动确认), started(完全启动)，默认两者都包含"
  ),
  stable: bool = Query(
    False,
    description="是否按“上一交易日收盘”冻结榜单，减少盘中更新导致的空间龙头/刚启动榜单波动",
  ),
) -> Dict:
  """
  启动龙头板块强度统计。

  返回示例结构（简化）：
  {
    "success": true,
    "window": {"start_date": "...", "end_date": "..."},
    "sectors": [
      {
        "sector_key": "industry:半导体",
        "sector_name": "半导体",
        "sector_type": "industry",
        "total_signals": 12,
        "distinct_stocks": 7,
        "days_active": 3,
        "avg_score_overall": 72.5,
        "recent_3d_signals": 8,
        "strength_score": 15.6,
        "daily": [
          {"trade_date": "2025-03-03", "signals": 3, "distinct_stocks": 3, "avg_score": 70.0},
          ...
        ]
      },
      ...
    ]
  }
  """
  try:
    warehouse = WarehouseService()
    if end_date is None:
      # 用「最新有数据的交易日」，避免跨自然日 0 点后窗口变化
      end_dt = warehouse.get_latest_trade_date()
      if end_dt is None:
        end_dt = datetime.now().date()

    else:
      try:
        end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
      except ValueError as e:
        raise HTTPException(status_code=400, detail="end_date 日期格式错误，应为 YYYY-MM-DD")

    if start_date is None:
      start_dt = end_dt - timedelta(days=5)
    else:
      try:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
      except ValueError as e:
        raise HTTPException(status_code=400, detail="start_date 日期格式错误，应为 YYYY-MM-DD")

    if start_dt > end_dt:
      raise HTTPException(status_code=400, detail="start_date 不能晚于 end_date")

    if stage not in (None, "confirmed", "started"):
      raise HTTPException(
        status_code=400,
        detail="stage 仅支持 confirmed / started / 不传（三者之一）",
      )

    analyzer = StartupSectorAnalyzer(warehouse)
    # 优先使用新版 4+2 规则的 rolling_30d_v2，数据更准确（考虑启动时序、近期强弱）
    leader_window_ids = ["rolling_30d_v2"]
    result = analyzer.analyze(
      start_date=start_dt,
      end_date=end_dt,
      min_score=min_score,
      stage_filter=stage,
      leader_window_ids=leader_window_ids,
    )
    return result

  except HTTPException:
    raise
  except Exception as e:
    logger.error("获取启动板块强度失败: %s", e, exc_info=True)
    raise HTTPException(status_code=500, detail="内部错误，请稍后重试")

