from __future__ import annotations

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parents[1]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from data_warehouse.service.warehouse_service import WarehouseService
from data_warehouse.models import DimSector, FactSectorLeaderSnapshot


def main() -> None:
    # 题材名称与股票 ts_code
    sector_name = "光伏概念"
    ts_code = "000601.SZ"
    window_id = "rolling_30d_v2"

    ws = WarehouseService()
    session = ws.get_session()
    try:
        sector = (
            session.query(DimSector)
            .filter(DimSector.sector_type == "concept", DimSector.name == sector_name)
            .first()
        )
        if not sector:
            sector = (
                session.query(DimSector)
                .filter(
                    DimSector.sector_type == "concept",
                    DimSector.name.like(f"%{sector_name}%"),
                )
                .first()
            )

        if not sector:
            print(f"未找到概念: {sector_name}")
            sys.exit(1)

        print("sector:", {"sector_id": sector.sector_id, "name": sector.name})

        row = (
            session.query(FactSectorLeaderSnapshot)
            .filter(
                FactSectorLeaderSnapshot.window_id == window_id,
                FactSectorLeaderSnapshot.sector_code == sector.sector_id,
                FactSectorLeaderSnapshot.ts_code == ts_code,
            )
            .first()
        )
        print("韶能 snapshot exists:", bool(row))

        if row:
            print(
                "韶能 snapshot:",
                {
                    "ts_code": row.ts_code,
                    "leader_type": row.leader_type,
                    "leader_rank": row.leader_rank,
                    "period_return_pct": float(row.period_return_pct)
                    if row.period_return_pct is not None
                    else None,
                    "continuous_limit": row.continuous_limit,
                    "score": float(row.score) if row.score is not None else None,
                },
            )

        all_rows = (
            session.query(FactSectorLeaderSnapshot)
            .filter(
                FactSectorLeaderSnapshot.window_id == window_id,
                FactSectorLeaderSnapshot.sector_code == sector.sector_id,
            )
            .all()
        )

        # 用于复现 absolute_leader 条件里的 max_ret
        period_returns = [
            float(r.period_return_pct)
            for r in all_rows
            if r.period_return_pct is not None
        ]
        max_ret = max(period_returns) if period_returns else None

        print(
            "sector max_ret(period_return_pct):",
            max_ret,
            "total_snapshot_rows:",
            len(all_rows),
        )

        if row and max_ret is not None:
            ret_ok = float(row.period_return_pct or 0) >= 40.0
            if float(row.period_return_pct or 0) == 0:
                ret_val = 0.0
            else:
                ret_val = float(row.period_return_pct)
            cond_2 = (row.continuous_limit or 0) >= 2 or ret_val >= max_ret - 10.0
            print(
                "absolute_leader candidate checks(for 韶能):",
                {
                    "ret_window>=40": ret_ok,
                    "cond2(continuous>=2 or ret>=max_ret-10)": cond_2,
                    # recent_strength 不在 snapshot 字段里，无法直接从 DB 还原
                },
            )

        # 还原“谁是 metrics_list[0]（leader_score 最高）”
        top = (
            session.query(FactSectorLeaderSnapshot)
            .filter(
                FactSectorLeaderSnapshot.window_id == window_id,
                FactSectorLeaderSnapshot.sector_code == sector.sector_id,
            )
            .order_by(FactSectorLeaderSnapshot.score.desc())
            .first()
        )
        if top:
            print(
                "leader_score highest snapshot:",
                {
                    "ts_code": top.ts_code,
                    "leader_type": top.leader_type,
                    "period_return_pct": float(top.period_return_pct)
                    if top.period_return_pct is not None
                    else None,
                    "continuous_limit": top.continuous_limit,
                    "score": float(top.score) if top.score is not None else None,
                },
            )

    finally:
        session.close()


if __name__ == "__main__":
    main()

