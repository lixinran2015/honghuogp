"""
将 二六三(002471.SZ) 的启动候选记录改为「未推荐」，以便刷新推荐再次纳入。

运行（项目根目录、激活虚拟环境）:
  python scripts/fix/set_erliusan_not_recommended.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

TS_CODE = "002471.SZ"


def main():
    from data_warehouse.service.warehouse_service import WarehouseService
    from data_warehouse.models.startup_candidate import FactStockStartupCandidate

    ws = WarehouseService()
    session = ws.get_session()

    rows = (
        session.query(FactStockStartupCandidate)
        .filter(
            FactStockStartupCandidate.ts_code == TS_CODE,
            FactStockStartupCandidate.is_recommended == True,
        )
        .all()
    )
    if not rows:
        print(f"未找到 {TS_CODE} 的已推荐记录，无需修改")
        session.close()
        return

    for r in rows:
        r.is_recommended = False
        r.recommend_date = None
        r.recommend_id = None
        print(f"已改为未推荐: {r.ts_code} trade_date={r.trade_date}")

    session.commit()
    session.close()
    print(f"✅ 共更新 {len(rows)} 条，可重新执行「刷新推荐」纳入二六三。")


if __name__ == "__main__":
    main()
