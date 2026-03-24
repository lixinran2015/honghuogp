import json
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta


API_BASE = "http://localhost:8000"


def get_json(path: str, params: dict | None = None, timeout_s: int = 180) -> dict:
    if params:
        url = f"{API_BASE}{path}?" + urllib.parse.urlencode(params)
    else:
        url = f"{API_BASE}{path}"
    raw = urllib.request.urlopen(url, timeout=timeout_s).read().decode("utf-8")
    return json.loads(raw)


def parse_trade_date_list(items: list) -> list[str]:
    # items from /api/data-warehouse/trade-calendar: [{trade_date, is_open, exchange}, ...]
    dates = []
    for it in items or []:
        td = it.get("trade_date")
        if td:
            dates.append(td)
    # sort for safety
    return sorted(set(dates))


def main() -> None:
    ts_code = "002730.SZ"  # 电光科技

    # 1) 最新交易日（取最近 3 个开市日）
    today = date.today()
    start = (today - timedelta(days=60)).isoformat()
    end = today.isoformat()
    cal = get_json("/api/data-warehouse/trade-calendar", params={"start_date": start, "end_date": end, "is_open": "true"}, timeout_s=120)
    trade_dates = parse_trade_date_list(cal.get("data", []))
    if not trade_dates:
        print("未从交易日历拿到开市日数据，无法继续。")
        return
    end_dates = trade_dates[-3:]
    print("ts_code:", ts_code)
    print("最近 3 个交易日:", end_dates)

    # 2) 看每个交易日的当日雷达里是否存在“空间龙头/刚启动龙头”
    for ed in end_dates:
        ed_dt = datetime.strptime(ed, "%Y-%m-%d").date()
        start_date = (ed_dt - timedelta(days=10)).isoformat()
        sector_strength = get_json(
            "/api/startup/sector-strength",
            params={
                "start_date": start_date,
                "end_date": ed,
                "min_score": 60,
                "stage": "confirmed",
                "stable": "true",
            },
            timeout_s=180,
        )

        sectors = sector_strength.get("sectors", []) or []
        # 前端口径：强度>5 的板块取前10
        filtered = [s for s in sectors if float(s.get("strength_score") or 0) > 5]
        filtered.sort(key=lambda x: float(x.get("strength_score") or 0), reverse=True)
        top_keys = set((filtered[:10] or []) and [s.get("sector_key") for s in filtered[:10]] or [])

        space_hits = []
        for item in sector_strength.get("space_leaders_lead", []) or []:
            for st in item.get("stocks", []) or []:
                if st.get("ts_code") == ts_code:
                    space_hits.append(item.get("sector_name") or item.get("sector_key"))

        new_hits = []
        for s in sectors:
            if s.get("sector_key") not in top_keys:
                continue
            for c in s.get("chain", []) or []:
                if c.get("ts_code") == ts_code and c.get("is_new_leader"):
                    new_hits.append(
                        {
                            "sector_name": s.get("sector_name"),
                            "sector_key": s.get("sector_key"),
                            "leader_type": c.get("leader_type"),
                            "continuous_limit": c.get("continuous_limit"),
                            "period_return_pct": c.get("period_return_pct"),
                        }
                    )

        print(f"\n=== sector-strength end_date={ed} ===")
        print("空间龙头命中数:", len(space_hits), "例:", space_hits[:3])
        print("刚启动命中数(仅主线Top10口径):", len(new_hits), "例:", new_hits[:1])

    # 3) 看它是否存在于持久跟踪池（当前接口默认到最新交易日）
    pool = get_json(
        "/api/leader-tracking/pool",
        params={
            "min_score": 60,
            "stage": "confirmed",
            "stable_window_id": "rolling_30d_v2",
            "bootstrap_days": 180,
            "do_bootstrap": "true",
            "force_sync": "false",
            # 不补历史，避免把现象“自动改掉”
            "catch_up_window_trading_days": 0,
            "catch_up_max_syncs": 0,
        },
        timeout_s=240,
    )
    hit = [x for x in (pool.get("pool") or []) if x.get("ts_code") == ts_code]
    print("\n=== leader-tracking/pool (当前池) ===")
    print("pool_hit_count:", len(hit))
    if hit:
        # print minimal fields
        x = hit[0]
        print(
            "first_space_date:", x.get("first_space_date"),
            "first_new_date:", x.get("first_new_date"),
            "last_seen_date:", x.get("last_seen_date"),
            "pool_created_at:", x.get("pool_created_at"),
        )

    # 4) 查启动候选里最近是否真的出现过它
    candidates = get_json(
        "/api/startup/candidates",
        params={
            "days": 20,
            "min_score": 60,
            "started_only": "false",
            "deduplicate": "false",
        },
        timeout_s=240,
    )
    arr = candidates.get("data", []) or candidates.get("candidates", []) or []
    hits = [c for c in arr if c.get("ts_code") == ts_code]
    print("\n=== startup/candidates 最近 20 交易日 (min_score=60) ===")
    print("candidates_hit_count:", len(hits))
    # print latest few
    # trade_date 可能是 date 类型或字符串；统一输出字符串
    def td_str(x):
        td = x.get("trade_date") or x.get("entry_date") or x.get("golden_cross_date")
        return str(td) if td else None

    hits_sorted = sorted(hits, key=lambda x: x.get("trade_date") or "", reverse=True)
    for c in hits_sorted[:5]:
        print(
            {
                "trade_date": td_str(c),
                "score": c.get("score"),
                "stage": c.get("stage"),
                "is_started": c.get("is_started"),
            }
        )


if __name__ == "__main__":
    main()

