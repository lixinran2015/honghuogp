from __future__ import annotations

import requests


BASE = "http://localhost:8000"
URL = f"{BASE}/api/startup/sector-strength"


def collect_space_and_new(data: dict) -> tuple[set[str], set[str]]:
    space_codes: set[str] = set()
    for item in data.get("space_leaders_lead", []) or []:
        for s in item.get("stocks", []) or []:
            ts = s.get("ts_code")
            if ts:
                space_codes.add(ts)

    new_codes: set[str] = set()
    for sec in data.get("sectors", []) or []:
        for c in sec.get("chain", []) or []:
            if c.get("is_new_leader") and c.get("ts_code"):
                new_codes.add(c["ts_code"])

    return space_codes, new_codes


def check(stable: bool) -> None:
    params = {"min_score": 60, "stable": stable}
    r = requests.get(URL, params=params, timeout=60)
    r.raise_for_status()
    data = r.json()
    space_codes, new_codes = collect_space_and_new(data)
    print(f"stable={stable}")
    print("  success:", data.get("success"))
    print("  space_count:", len(space_codes))
    print("  new_count:", len(new_codes))
    print("  space_hit_000601:", "000601.SZ" in space_codes)
    print("  new_hit_000601:", "000601.SZ" in new_codes)
    print("  window:", data.get("window"))


if __name__ == "__main__":
    check(stable=False)
    check(stable=True)

