"""
交易计划通用工具（启动/推荐共用）

统一计算：买入参考价区间、止损价、第一目标价。

设计原则：
- 尽量复用现有推荐池中的逻辑（90/120 日压力位 + 默认 10% 预期）
- 将止损比例等从配置中读取（config_manager.trading_config.recommendation_defaults）
"""

from __future__ import annotations

from typing import Dict, Optional, Tuple
import logging

try:
  # 与 stock_recommender 中保持一致的配置入口
  from utils.config_manager import config_manager
except Exception:  # pragma: no cover - 配置缺失时使用默认
  config_manager = None  # type: ignore

logger = logging.getLogger(__name__)


def _get_trade_plan_defaults() -> Tuple[float, float, float]:
  """
  返回 (target_1_pct, stop_loss_pct, entry_range_pct)：
  - target_1_pct: 无压力位时的默认第一目标价倍数（如 1.20 表示 +20%）
  - stop_loss_pct: 止损价倍数（如 0.94 表示 -6%）
  - entry_range_pct: 建议买入价上下浮动比例（如 0.02 表示 ±2%）
  """
  default_target = 1.20
  default_stop = 0.94
  default_entry_range = 0.02

  try:
    if not config_manager:
      return default_target, default_stop, default_entry_range
    trading_cfg = (config_manager.get_trading_config() or {}).get("recommendation_defaults") or {}
    target = float(trading_cfg.get("target_1_pct", default_target))
    stop = float(trading_cfg.get("stop_loss_pct", default_stop))
    entry_range = float(trading_cfg.get("entry_range_pct", default_entry_range))
    return target, stop, entry_range
  except Exception:
    return default_target, default_stop, default_entry_range


def _compute_target_from_resistance(entry_price: float, stock_data: Optional[Dict]) -> Tuple[float, str]:
  """
  基于技术面压力位计算第一目标价。

  - 优先 90 日收盘价最高价（未突破时作为第一目标）；
  - 已突破 90 日高点则用 120 日高点；
  - 无有效压力位时使用保守 10%（1.10）。
  """
  if not stock_data:
    target_1_pct, _, _ = _get_trade_plan_defaults()
    # 若配置给的是 1.20，则这里统一用配置；否则用 10% 兜底
    fallback = target_1_pct if target_1_pct > 1.0 else 1.10
    return round(entry_price * fallback, 2), "默认目标价"

  try:
    high_90d = float(stock_data.get("high_90d") or 0)
    high_120d = float(stock_data.get("high_120d") or 0)
  except Exception:
    high_90d = 0.0
    high_120d = 0.0

  # 无压力位时的保守预期（10%），与推荐池实现保持一致
  fallback_pct = 1.10
  if high_90d > 0 and high_90d > entry_price:
    return round(high_90d, 2), "90日高点"
  if high_120d > 0 and high_120d > entry_price:
    return round(high_120d, 2), "120日高点"
  return round(entry_price * fallback_pct, 2), "无压力位(10%)"


def compute_trade_plan(entry_price: float, stock_data: Optional[Dict] = None) -> Dict:
  """
  统一计算交易计划：

  返回结构示例：
  {
    "entry_price": 12.34,
    "buy_range": [12.1, 12.6],
    "stop_loss_price": 11.6,
    "take_profit_price": 13.8,
    "expected_return_pct": 12.0,
    "stop_loss_pct": -6.0,
    "buy_range_pct": 2.0,
    "target_source": "90日高点" / "120日高点" / "无压力位(10%)" / "默认目标价"
  }
  """
  if entry_price <= 0:
    return {
      "entry_price": 0.0,
      "buy_range": [0.0, 0.0],
      "stop_loss_price": 0.0,
      "take_profit_price": 0.0,
      "expected_return_pct": 0.0,
      "stop_loss_pct": 0.0,
      "buy_range_pct": 0.0,
      "target_source": "无有效价格",
    }

  target_1_pct, stop_loss_pct, entry_range_pct = _get_trade_plan_defaults()

  # 目标价：优先用压力位，fallback 10%；对无 stock_data 的情况才用配置 target_1_pct
  take_profit_price, target_source = _compute_target_from_resistance(entry_price, stock_data)
  if not stock_data:
    # 当没有技术面高点信息时，用配置 target_1_pct 替代 10% 的逻辑
    take_profit_price = round(entry_price * target_1_pct, 2)
    target_source = "默认目标价"

  stop_loss_price = round(entry_price * stop_loss_pct, 2)

  expected_return_pct = (
    (take_profit_price / entry_price - 1.0) * 100.0 if entry_price > 0 else 0.0
  )
  stop_loss_pct_val = (stop_loss_price / entry_price - 1.0) * 100.0 if entry_price > 0 else 0.0

  # 建议买入区间：± entry_range_pct
  low = round(entry_price * (1.0 - entry_range_pct), 2)
  high = round(entry_price * (1.0 + entry_range_pct), 2)

  return {
    "entry_price": round(entry_price, 2),
    "buy_range": [low, high],
    "stop_loss_price": stop_loss_price,
    "take_profit_price": take_profit_price,
    "expected_return_pct": round(expected_return_pct, 1),
    "stop_loss_pct": round(stop_loss_pct_val, 1),
    "buy_range_pct": round(entry_range_pct * 100.0, 1),
    "target_source": target_source,
  }

