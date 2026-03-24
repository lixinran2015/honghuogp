#!/usr/bin/env python
"""
轮动规律排查脚本：检查 config、dim_sector、fact_sector_daily 及领涨序列
支持 --backfill 仅补全监控板块日线（快速修复轮动规律为空）
"""
import sys
import argparse
from pathlib import Path

# 确保 backend 在路径中
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))


def backfill_monitor_sectors(days: int = 120, delay: float = 0.5, use_eastmoney: bool = False):
    """仅补全监控板块的日线数据。--use-eastmoney 使用东财直连（已加浏览器头），否则用 AkShare"""
    import time
    from datetime import datetime, timedelta
    import pandas as pd
    from sqlalchemy import create_engine, text
    from sqlalchemy.types import Date, Numeric, String
    from data_warehouse.config import DATABASE_URL
    from backend.services.sector.theme_rotation_service import ThemeRotationService

    if use_eastmoney:
        from backend.services.sector.eastmoney_sector_service import fetch_sector_daily_kline
    else:
        try:
            import akshare as ak
        except ImportError:
            print("❌ 请安装 akshare: pip install akshare，或使用 --use-eastmoney")
            return

    svc = ThemeRotationService()
    svc._ensure_theme_map()
    if not svc._monitor_sector_ids:
        print("❌ 无监控板块，请先检查 config 与 dim_sector")
        return

    engine = create_engine(DATABASE_URL, echo=False)
    end_str = datetime.now().strftime("%Y%m%d")
    start_str = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")

    sectors = []
    with engine.connect() as conn:
        for sid in svc._monitor_sector_ids:
            r = conn.execute(text("SELECT sector_id, name FROM dim_sector WHERE sector_id = :sid"), {"sid": sid}).fetchone()
            if r:
                sectors.append((r[0], r[1]))

    src = "东财直连（含浏览器头）" if use_eastmoney else "AkShare"
    print(f"📥 使用 {src} 补全 {len(sectors)} 个监控板块日线（{start_str} ~ {end_str}）...")

    dtype_map = {
        "sector_id": String(50), "trade_date": Date, "close": Numeric(12, 4),
        "pre_close": Numeric(12, 4), "change_pct": Numeric(8, 4),
        "volume": Numeric(20, 4), "amount": Numeric(20, 4),
    }
    total = 0

    for idx, (sector_id, sector_name) in enumerate(sectors):
        if idx > 0:
            time.sleep(delay)
        rows = []

        if use_eastmoney:
            df_raw = fetch_sector_daily_kline(sector_id, start_date=start_str, end_date=end_str)
            if df_raw is not None and not df_raw.empty:
                prev_close = None
                for _, row in df_raw.iterrows():
                    td = row["trade_date"]
                    close = row.get("close")
                    rows.append({
                        "sector_id": sector_id, "trade_date": td, "close": close,
                        "pre_close": prev_close, "change_pct": row.get("change_pct"),
                        "volume": row.get("volume"), "amount": row.get("amount"),
                    })
                    prev_close = close
        else:
            k_df = None
            for attempt in range(4):
                try:
                    k_df = ak.stock_board_industry_hist_em(
                        symbol=sector_name, start_date=start_str, end_date=end_str,
                        period="日k", adjust="",
                    )
                    break
                except (ConnectionError, OSError) as e:
                    err = str(e).lower()
                    if attempt < 3 and ("connection" in err or "remote" in err or "reset" in err):
                        wait = 1.5 * (attempt + 1)
                        print(f"  ⏳ {sector_name} 重试 {attempt+1}/4，{wait}s 后...")
                        time.sleep(wait)
                        continue
                    print(f"  ❌ {sector_name}: {e}")
                    break
                except Exception as e:
                    err = str(e).lower()
                    if attempt < 3 and ("connection" in err or "remote" in err or "reset" in err):
                        time.sleep(1.5 * (attempt + 1))
                        continue
                    print(f"  ❌ {sector_name}: {e}")
                    break
            if k_df is not None and not k_df.empty and "日期" in k_df.columns:
                for _, r in k_df.iterrows():
                    date_str = r["日期"]
                    if isinstance(date_str, str) and len(date_str) >= 10:
                        td = datetime.strptime(date_str[:10], "%Y-%m-%d").date()
                    else:
                        continue
                    close = float(r["收盘"]) if pd.notna(r.get("收盘")) else None
                    change_pct = float(r["涨跌幅"]) if pd.notna(r.get("涨跌幅")) else None
                    volume = float(r["成交量"]) if pd.notna(r.get("成交量")) else None
                    amount = float(r["成交额"]) if pd.notna(r.get("成交额")) else None
                    rows.append({
                        "sector_id": sector_id, "trade_date": td, "close": close,
                        "pre_close": None, "change_pct": change_pct, "volume": volume, "amount": amount,
                    })

        if not rows:
            continue
        try:
            df_in = pd.DataFrame(rows)
            temp_name = "temp_sector_daily_theme_rotation"
            with engine.connect() as conn:
                conn.execute(text(f"DROP TABLE IF EXISTS {temp_name}"))
                conn.commit()
                df_in.to_sql(
                    temp_name, conn, if_exists="append", index=False,
                    dtype={c: dtype_map[c] for c in df_in.columns if c in dtype_map},
                )
                conn.commit()
                conn.execute(text(f"""
                    INSERT INTO fact_sector_daily (sector_id, trade_date, close, pre_close, change_pct, volume, amount)
                    SELECT sector_id, trade_date, close, pre_close, change_pct, volume, amount FROM {temp_name}
                    ON CONFLICT (sector_id, trade_date) DO UPDATE SET
                    close = EXCLUDED.close, pre_close = EXCLUDED.pre_close, change_pct = EXCLUDED.change_pct,
                    volume = EXCLUDED.volume, amount = EXCLUDED.amount, updated_at = CURRENT_TIMESTAMP
                """))
                conn.execute(text(f"DROP TABLE IF EXISTS {temp_name}"))
                conn.commit()
            total += len(rows)
            print(f"  ✅ {sector_name}: {len(rows)} 条")
        except Exception as e:
            print(f"  ❌ {sector_name} 入库失败: {e}")
    print(f"✅ 共写入 {total} 条，可重新运行诊断验证")


def main():
    from backend.services.sector.theme_rotation_service import ThemeRotationService

    print("=" * 60)
    print("轮动规律排查")
    print("=" * 60)

    svc = ThemeRotationService()

    # 1. 诊断信息
    print("\n【1. 诊断信息】")
    diag = svc.get_diagnostic()
    for k, v in diag.items():
        if k == "matched_sectors" and v:
            print(f"  {k}: {len(v)} 个板块")
            for m in v[:5]:
                print(f"    - {m['sector_id']} {m['sector_name']} -> {m['theme_name']}")
            if len(v) > 5:
                print(f"    ... 共 {len(v)} 个")
        elif k == "matched_sectors" and not v:
            print(f"  {k}: (空)")
        elif k == "unmapped_sector_names" and v:
            print(f"  {k}: {v}")
        else:
            print(f"  {k}: {v}")

    # 2. 领涨序列（最近 10 天）
    print("\n【2. 领涨序列（最近 10 天）】")
    svc._ensure_theme_map()
    series = svc._get_leading_theme_series(lookback_days=120)
    if not series:
        print("  (空 - 无法计算轮动规律)")
    else:
        print(f"  共 {len(series)} 个交易日")
        for s in series[-10:]:
            print(f"    {s['trade_date']} 领涨: {s['leading_theme_name'] or s['leading_theme_code'] or '(未识别)'}")

    # 3. 轮动规律
    print("\n【3. 轮动规律】")
    patterns = svc.get_rotation_patterns(lookback_days=120)
    print(f"  sample_days: {patterns.get('sample_days')}")
    print(f"  total_pairs: {patterns.get('total_pairs')}")
    print(f"  momentum_ratio: {patterns.get('momentum_ratio')}")
    print(f"  reversal_ratio: {patterns.get('reversal_ratio')}")
    if patterns.get("message"):
        print(f"  message: {patterns['message']}")
    tm = patterns.get("transition_matrix") or {}
    print(f"  transition_matrix 条数: {len(tm)}")
    if tm:
        items = sorted(tm.items(), key=lambda x: -x[1])[:5]
        for k, v in items:
            print(f"    {k}: {v*100:.1f}%")

    print("\n" + "=" * 60)


def import_csv(csv_path: str):
    """从 CSV 手动导入板块日线。CSV 需含列：sector_id 或 sector_name, trade_date, close, change_pct (可选 volume, amount)"""
    import pandas as pd
    from sqlalchemy import create_engine, text
    from sqlalchemy.types import Date, Numeric, String
    from data_warehouse.config import DATABASE_URL

    path = Path(csv_path)
    if not path.exists():
        print(f"❌ 文件不存在: {csv_path}")
        return
    df = pd.read_csv(path)
    req = {"trade_date", "close"}
    if "sector_id" not in df.columns and "sector_name" not in df.columns:
        print("❌ CSV 需含 sector_id 或 sector_name 列")
        return
    if not req.issubset(df.columns):
        print(f"❌ CSV 需含 {req} 列")
        return

    engine = create_engine(DATABASE_URL, echo=False)
    if "sector_name" in df.columns and "sector_id" not in df.columns:
        df["sector_id"] = None
        with engine.connect() as conn:
            for name in df["sector_name"].dropna().unique():
                r = conn.execute(text("SELECT sector_id FROM dim_sector WHERE name = :n"), {"n": str(name).strip()}).fetchone()
                if r:
                    df.loc[df["sector_name"] == name, "sector_id"] = r[0]
                else:
                    print(f"  ⚠️ 未找到板块: {name}")
        df = df[df["sector_id"].notna()].copy()

    df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date
    for col in ["pre_close", "change_pct", "volume", "amount"]:
        if col not in df.columns:
            df[col] = None
    cols = ["sector_id", "trade_date", "close", "pre_close", "change_pct", "volume", "amount"]
    rows = df[cols].to_dict("records")
    rows = [r for r in rows if pd.notna(r.get("sector_id")) and pd.notna(r.get("trade_date"))]

    if not rows:
        print("❌ 无有效数据行")
        return
    df_in = pd.DataFrame(rows)
    dtype_map = {"sector_id": String(50), "trade_date": Date, "close": Numeric(12, 4), "pre_close": Numeric(12, 4),
                 "change_pct": Numeric(8, 4), "volume": Numeric(20, 4), "amount": Numeric(20, 4)}
    temp_name = "temp_sector_daily_import"
    with engine.connect() as conn:
        conn.execute(text(f"DROP TABLE IF EXISTS {temp_name}"))
        conn.commit()
    df_in.to_sql(temp_name, engine, if_exists="append", index=False, dtype={c: dtype_map.get(c) for c in df_in.columns if dtype_map.get(c)})
    with engine.connect() as conn:
        conn.execute(text(f"""
            INSERT INTO fact_sector_daily (sector_id, trade_date, close, pre_close, change_pct, volume, amount)
            SELECT sector_id, trade_date, close, pre_close, change_pct, volume, amount FROM {temp_name}
            ON CONFLICT (sector_id, trade_date) DO UPDATE SET
            close = EXCLUDED.close, pre_close = EXCLUDED.pre_close, change_pct = EXCLUDED.change_pct,
            volume = EXCLUDED.volume, amount = EXCLUDED.amount, updated_at = CURRENT_TIMESTAMP
        """))
        conn.execute(text(f"DROP TABLE IF EXISTS {temp_name}"))
        conn.commit()
    print(f"✅ 导入 {len(rows)} 条")


def backfill_from_tushare(days: int = 120):
    """使用 Tushare 申万行业指数补全（需 config 中 tushare token，且积分≥120）"""
    from datetime import datetime, timedelta
    import pandas as pd
    from sqlalchemy import create_engine, text
    from sqlalchemy.types import Date, Numeric, String
    from data_warehouse.config import DATABASE_URL

    try:
        from backend.services.tushare_service import TushareService
    except Exception:
        print("❌ 无法导入 TushareService")
        return
    svc = TushareService()
    if not svc.available:
        print("❌ Tushare 未配置或不可用，请检查 config.json 中 tushare token")
        return

    # 申万一级行业 -> 主题（6 个代表性行业）
    SW_THEME_MAP = [
        ("801150.SI", "医药生物", "aging_health"),
        ("801730.SI", "电力设备", "new_energy"),
        ("801080.SI", "电子", "semiconductor"),
        ("801750.SI", "计算机", "ai_digital"),
        ("801120.SI", "食品饮料", "consumption"),
        ("801010.SI", "农林牧渔", "agriculture"),
    ]

    engine = create_engine(DATABASE_URL, echo=False)
    end_str = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
    start_str = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")

    # 确保 dim_sector 有申万板块（sector_id 如 SW801150）
    with engine.connect() as conn:
        for ts_code, name, _ in SW_THEME_MAP:
            sector_id = f"SW{ts_code.replace('.SI', '')}"
            conn.execute(text("""
                INSERT INTO dim_sector (sector_id, sector_type, name) VALUES (:sid, 'industry', :name)
                ON CONFLICT (sector_id) DO UPDATE SET name = EXCLUDED.name
            """), {"sid": sector_id, "name": name})
        conn.commit()

    print(f"📥 使用 Tushare 申万行业补全 6 个板块（{start_str} ~ {end_str}）...")
    total = 0
    dtype_map = {"sector_id": String(50), "trade_date": Date, "close": Numeric(12, 4), "pre_close": Numeric(12, 4),
                 "change_pct": Numeric(8, 4), "volume": Numeric(20, 4), "amount": Numeric(20, 4)}

    for ts_code, name, _ in SW_THEME_MAP:
        try:
            df = svc.pro.sw_daily(ts_code=ts_code, start_date=start_str, end_date=end_str)
            if df is None or df.empty:
                print(f"  ⚠️ {name} 无数据")
                continue
            sector_id = f"SW{ts_code.replace('.SI', '')}"
            df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date
            df["change_pct"] = df["pct_change"] if "pct_change" in df.columns else None
            df["volume"] = df["vol"] if "vol" in df.columns else None
            rows = []
            prev_close = None
            for _, r in df.iterrows():
                close = float(r["close"]) if pd.notna(r.get("close")) else None
                rows.append({"sector_id": sector_id, "trade_date": r["trade_date"], "close": close,
                             "pre_close": prev_close, "change_pct": r.get("change_pct"),
                             "volume": r.get("volume"), "amount": r.get("amount")})
                prev_close = close
            if not rows:
                continue
            df_in = pd.DataFrame(rows)
            temp_name = "temp_sector_daily_tushare"
            with engine.connect() as conn:
                conn.execute(text(f"DROP TABLE IF EXISTS {temp_name}"))
                conn.commit()
                df_in.to_sql(temp_name, conn, if_exists="append", index=False,
                             dtype={c: dtype_map[c] for c in df_in.columns if c in dtype_map})
                conn.commit()
                conn.execute(text(f"""
                    INSERT INTO fact_sector_daily (sector_id, trade_date, close, pre_close, change_pct, volume, amount)
                    SELECT sector_id, trade_date, close, pre_close, change_pct, volume, amount FROM {temp_name}
                    ON CONFLICT (sector_id, trade_date) DO UPDATE SET
                    close = EXCLUDED.close, pre_close = EXCLUDED.pre_close, change_pct = EXCLUDED.change_pct,
                    volume = EXCLUDED.volume, amount = EXCLUDED.amount, updated_at = CURRENT_TIMESTAMP
                """))
                conn.execute(text(f"DROP TABLE IF EXISTS {temp_name}"))
                conn.commit()
            total += len(rows)
            print(f"  ✅ {name}: {len(rows)} 条")
        except Exception as e:
            print(f"  ❌ {name}: {e}")

    # 需在 long_term_themes.json 中加入申万行业名（医药生物、电力设备等）以参与轮动
    print(f"✅ 共写入 {total} 条")
    print("  提示：若轮动仍为空，请在 config/long_term_themes.json 的 sector_names 中加入：医药生物、电力设备、电子、计算机、食品饮料、农林牧渔")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="轮动规律排查")
    ap.add_argument("--backfill", action="store_true", help="补全监控板块日线（约 19 个板块 × 120 天）")
    ap.add_argument("--use-eastmoney", action="store_true", help="用东财直连（含浏览器头），AkShare 断连时可试")
    ap.add_argument("--use-tushare", action="store_true", help="用 Tushare 申万行业（需 token，东财/AkShare 均不可用时用）")
    ap.add_argument("--import-csv", type=str, metavar="PATH", help="从 CSV 导入（列：sector_id 或 sector_name, trade_date, close, change_pct）")
    ap.add_argument("--days", type=int, default=120, help="补全天数（默认 120）")
    ap.add_argument("--delay", type=float, default=0.5, help="请求间隔秒数")
    args = ap.parse_args()

    if args.import_csv:
        import_csv(args.import_csv)
    elif args.use_tushare:
        backfill_from_tushare(days=args.days)
    elif args.backfill:
        backfill_monitor_sectors(days=args.days, delay=args.delay, use_eastmoney=args.use_eastmoney)
    else:
        main()
