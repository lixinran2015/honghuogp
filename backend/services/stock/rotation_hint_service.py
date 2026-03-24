"""
明日轮动方向预判

收盘后根据「主线分歧 vs 结束」「次强板块是否接棒」给出明天可能的轮动方向：
- 主线内部轮动（高切低）
- 次主线接棒（具体板块）
- 全面退潮（轻仓/空仓）
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Any

import logging
from sqlalchemy.orm import Session

from data_warehouse.service.warehouse_service import WarehouseService
from data_warehouse.models.generated_models import FactDailyPriceQfq, DimTradeCalendar
from backend.services.stock.startup_sector_analyzer import StartupSectorAnalyzer

logger = logging.getLogger(__name__)


@dataclass
class FrontStockCandle:
    """主线前排单日 K 线摘要"""
    ts_code: str
    name: str
    change_pct: float
    is_big_yin: bool
    is_long_upper_shadow: bool
    near_ma5: bool
    tail_reflow: bool


@dataclass
class SecondSectorSignals:
    """次强板块今日信号"""
    sector_key: str
    sector_name: str
    sector_type: str
    strength_score: float
    first_board_count: int
    startup_count_today: int
    startup_count_yesterday: int
    startup_delta: int


@dataclass
class RotationHintResult:
    """轮动预判结果"""
    trade_date: date
    predict_date: Optional[date]
    main_sector_key: str
    main_sector_name: str
    main_front_candles: List[FrontStockCandle]
    main_sector_chain: List[Dict[str, Any]]  # 主线接力链条，对应可关注的股票
    main_has_tail_reflow: bool
    main_all_big_yin: bool
    second_sectors: List[SecondSectorSignals]
    conclusion: str
    conclusion_type: str
    suggest_sector: Optional[str]
    details: List[str]

    def to_dict(self) -> Dict[str, Any]:
        """供 API 返回的 JSON 可序列化字典"""
        return {
            "trade_date": self.trade_date.isoformat() if self.trade_date else None,
            "predict_date": self.predict_date.isoformat() if self.predict_date else None,
            "main_sector_key": self.main_sector_key,
            "main_sector_name": self.main_sector_name,
            "main_front_candles": [
                {
                    "ts_code": c.ts_code,
                    "name": c.name,
                    "change_pct": c.change_pct,
                    "is_big_yin": c.is_big_yin,
                    "is_long_upper_shadow": c.is_long_upper_shadow,
                    "near_ma5": c.near_ma5,
                    "tail_reflow": c.tail_reflow,
                }
                for c in (self.main_front_candles or [])
            ],
            "main_sector_chain": [
                {
                    "ts_code": c.get("ts_code"),
                    "name": c.get("name") or c.get("ts_code"),
                    "role_label": c.get("role_label") or "",
                    "position_type": c.get("position_type", "low"),
                }
                for c in (self.main_sector_chain or [])
            ],
            "main_has_tail_reflow": self.main_has_tail_reflow,
            "main_all_big_yin": self.main_all_big_yin,
            "second_sectors": [
                {
                    "sector_key": s.sector_key,
                    "sector_name": s.sector_name,
                    "sector_type": s.sector_type,
                    "strength_score": s.strength_score,
                    "first_board_count": s.first_board_count,
                    "startup_count_today": s.startup_count_today,
                    "startup_count_yesterday": s.startup_count_yesterday,
                    "startup_delta": s.startup_delta,
                }
                for s in (self.second_sectors or [])
            ],
            "conclusion": self.conclusion,
            "conclusion_type": self.conclusion_type,
            "suggest_sector": self.suggest_sector,
            "details": self.details or [],
        }


class RotationHintService:
    """明日轮动方向预判服务"""

    def __init__(self, warehouse_service: Optional[WarehouseService] = None) -> None:
        self.ws = warehouse_service or WarehouseService()

    def get_rotation_hint(
        self,
        end_date: Optional[date] = None,
        start_date: Optional[date] = None,
        min_score: int = 60,
        stage_filter: Optional[str] = None,
    ) -> RotationHintResult:
        """基于 end_date 当日板块强度与 K 线，给出明日轮动方向预判。"""
        session: Session = self.ws.get_session()
        try:
            if end_date is None:
                end_date = self.ws.get_latest_trade_date()
                if end_date is None:
                    end_date = datetime.now().date()
            if start_date is None:
                start_date = end_date - timedelta(days=5)

            # 预测日：默认取下一个交易日（如无则为空）
            predict_date = self._next_trade_date(session, end_date)

            analyzer = StartupSectorAnalyzer(self.ws)
            result = analyzer.analyze(
                start_date=start_date,
                end_date=end_date,
                min_score=min_score,
                stage_filter=stage_filter,
            )
            if not result.get("success") or not result.get("sectors"):
                return RotationHintResult(
                    trade_date=end_date,
                    predict_date=predict_date,
                    main_sector_key="",
                    main_sector_name="",
                    main_front_candles=[],
                    main_sector_chain=[],
                    main_has_tail_reflow=False,
                    main_all_big_yin=False,
                    second_sectors=[],
                    conclusion="暂无主线数据，无法预判轮动。",
                    conclusion_type="",
                    suggest_sector=None,
                    details=["请先确保有启动候选与板块强度数据。"],
                )

            sectors = result["sectors"]
            main = sectors[0] if sectors else {}
            # 次强板块：取排名2~5中的概念类板块（优先），兜底取前2个
            candidates = sectors[1:5] if len(sectors) >= 2 else []
            second_list = [s for s in candidates if s.get("sector_type") == "concept"][:3]
            if not second_list:
                second_list = candidates[:2]

            main_sector_key = main.get("sector_key", "")
            main_sector_name = main.get("sector_name", "")
            main_chain = main.get("chain") or []
            main_codes = [c["ts_code"] for c in main_chain[:3] if c.get("ts_code")]

            front_candles: List[FrontStockCandle] = []
            has_tail_reflow = False
            all_big_yin = False
            if main_codes:
                rows = session.query(
                    FactDailyPriceQfq.ts_code,
                    FactDailyPriceQfq.open,
                    FactDailyPriceQfq.high,
                    FactDailyPriceQfq.low,
                    FactDailyPriceQfq.close,
                    FactDailyPriceQfq.change_pct,
                    FactDailyPriceQfq.ma5,
                ).filter(
                    FactDailyPriceQfq.ts_code.in_(main_codes),
                    FactDailyPriceQfq.trade_date == end_date,
                ).all()
                name_map = {c["ts_code"]: c.get("name") or c["ts_code"] for c in main_chain}
                for r in rows:
                    o = float(r.open or 0)
                    h = float(r.high or 0)
                    l = float(r.low or 0)
                    c = float(r.close or 0)
                    chg = float(r.change_pct or 0)
                    ma5 = float(r.ma5 or 0)
                    hl_range = h - l if h > l else 1e-8
                    upper_shadow = (h - max(o, c)) / hl_range
                    is_long_upper = upper_shadow >= 0.5 and c < o
                    is_big_yin = chg <= -2.5 and c < o
                    near_ma5 = ma5 > 0 and c >= ma5 * 0.98
                    tail_reflow = (c - l) / hl_range >= 0.35
                    if tail_reflow:
                        has_tail_reflow = True
                    front_candles.append(FrontStockCandle(
                        ts_code=r.ts_code,
                        name=name_map.get(r.ts_code, r.ts_code),
                        change_pct=chg,
                        is_big_yin=is_big_yin,
                        is_long_upper_shadow=is_long_upper,
                        near_ma5=near_ma5,
                        tail_reflow=tail_reflow,
                    ))
                # 循环结束后计算：有数据且全部是大阴
                all_big_yin = bool(front_candles) and all(fc.is_big_yin for fc in front_candles)

            prev_date = self._prev_trade_date(session, end_date)
            second_sectors: List[SecondSectorSignals] = []
            for sec in second_list:
                sk = sec.get("sector_key", "")
                sn = sec.get("sector_name", "")
                st = sec.get("sector_type", "")
                strength = float(sec.get("strength_score", 0))
                chain = sec.get("chain") or []
                codes = [c["ts_code"] for c in chain if c.get("ts_code")]
                first_board = 0
                if codes:
                    first_board = session.query(FactDailyPriceQfq).filter(
                        FactDailyPriceQfq.ts_code.in_(codes),
                        FactDailyPriceQfq.trade_date == end_date,
                        FactDailyPriceQfq.change_pct >= 9.5,
                    ).count()
                daily_list = sec.get("daily") or []
                # daily 来自 to_dict()，trade_date 可能是 date 或序列化后的 str
                startup_today = sum(
                    d.get("signals", 0)
                    for d in daily_list
                    if d.get("trade_date") and str(d.get("trade_date")) == str(end_date)
                )
                startup_yesterday = sum(
                    d.get("signals", 0)
                    for d in daily_list
                    if prev_date and d.get("trade_date") and str(d.get("trade_date")) == str(prev_date)
                )
                second_sectors.append(SecondSectorSignals(
                    sector_key=sk,
                    sector_name=sn,
                    sector_type=st,
                    strength_score=strength,
                    first_board_count=first_board,
                    startup_count_today=startup_today,
                    startup_count_yesterday=startup_yesterday,
                    startup_delta=startup_today - startup_yesterday,
                ))

            conclusion_type = "internal_rotation"
            conclusion = "明日可能以主线内部轮动（高切低）为主，可关注主线内低位补涨与稳健票。"
            suggest_sector: Optional[str] = None
            details: List[str] = []

            if main_sector_name:
                details.append(f"主线：{main_sector_name}；前排 {len(front_candles)} 只。")
            for fc in front_candles:
                parts = [f"{fc.name}({fc.change_pct:+.1f}%)"]
                if fc.is_big_yin:
                    parts.append("大阴")
                if fc.is_long_upper_shadow:
                    parts.append("长上影")
                if fc.near_ma5:
                    parts.append("守5日线")
                if fc.tail_reflow:
                    parts.append("尾盘有回流")
                details.append("  " + "，".join(parts))

            if front_candles and all_big_yin and not has_tail_reflow:
                conclusion_type = "retreat"
                conclusion = "主线前排集体大阴且尾盘无承接，情绪退潮概率大，建议轻仓或空仓观望。"
                details.append("（前排大阴+无尾盘回流 → 退潮）")
            else:
                best_second = None
                for ss in second_sectors:
                    if ss.first_board_count >= 1 or ss.startup_delta >= 1:
                        if best_second is None or ss.first_board_count + ss.startup_delta > (
                            best_second.first_board_count + best_second.startup_delta
                        ):
                            best_second = ss
                if best_second and (not has_tail_reflow or all_big_yin):
                    conclusion_type = "second_taking_over"
                    suggest_sector = best_second.sector_name
                    conclusion = f"主线分歧或走弱，次强板块「{best_second.sector_name}」今日有首板/启动增多，明日可能接棒，可适当关注。"
                    details.append(f"次强接棒候选：{best_second.sector_name}（首板约{best_second.first_board_count}只，启动变化{best_second.startup_delta:+d}）。")
                else:
                    details.append("尾盘有回流或前排未集体大阴，偏向主线内部轮动。")

            return RotationHintResult(
                trade_date=end_date,
                predict_date=predict_date,
                main_sector_key=main_sector_key,
                main_sector_name=main_sector_name,
                main_front_candles=front_candles,
                main_sector_chain=[
                    {
                        "ts_code": c.get("ts_code"),
                        "name": c.get("name") or c.get("ts_code"),
                        "role_label": c.get("role_label") or "",
                        "position_type": "high" if (c.get("role_label") or "").find("空间龙头") >= 0 else "low",
                    }
                    for c in main_chain
                    if c.get("ts_code")
                ],
                main_has_tail_reflow=has_tail_reflow,
                main_all_big_yin=all_big_yin,
                second_sectors=second_sectors,
                conclusion=conclusion,
                conclusion_type=conclusion_type,
                suggest_sector=suggest_sector,
                details=details,
            )
        finally:
            session.close()

    def _prev_trade_date(self, session: Session, d: date) -> Optional[date]:
        row = session.query(DimTradeCalendar.trade_date).filter(
            DimTradeCalendar.trade_date < d,
            DimTradeCalendar.is_open.is_(True),
        ).order_by(DimTradeCalendar.trade_date.desc()).limit(1).first()
        return row[0] if row else None

    def _next_trade_date(self, session: Session, d: date) -> Optional[date]:
        row = session.query(DimTradeCalendar.trade_date).filter(
            DimTradeCalendar.trade_date > d,
            DimTradeCalendar.is_open.is_(True),
        ).order_by(DimTradeCalendar.trade_date.asc()).limit(1).first()
        return row[0] if row else None
