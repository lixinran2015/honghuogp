"""
行业周期配置更新 - 主工作流
支持：full | collect | suggest | apply | monitor
"""
import sys
import json
import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))


def _ic_dir() -> Path:
    return PROJECT_ROOT / "data_warehouse" / "industry_cycle"


def _latest_cycle_data() -> Optional[Path]:
    ic = _ic_dir().resolve()
    if not ic.exists():
        return None
    files = sorted(ic.glob("cycle_data_*.json"), key=lambda p: p.stem, reverse=True)
    return files[0] if files else None


def mode_collect() -> Path:
    """仅采集数据"""
    import importlib.util
    spec = importlib.util.spec_from_file_location("collect", PROJECT_ROOT / "scripts" / "tools" / "collect_industry_cycle_data.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.main()


def mode_suggest(cycle_data_path: Path = None) -> tuple[Path, list]:
    """生成变更建议"""
    import importlib.util
    spec = importlib.util.spec_from_file_location("rule_engine", PROJECT_ROOT / "scripts" / "tools" / "industry_cycle_rule_engine.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    run_suggestions = mod.run_suggestions
    _ic_dir().mkdir(parents=True, exist_ok=True)
    cycle_data_path = cycle_data_path or _latest_cycle_data()
    resolved = Path(cycle_data_path).resolve() if cycle_data_path else None
    if resolved and not resolved.exists():
        # 指定文件不存在时，尝试使用同目录下最新的 cycle_data_*.json
        fallback = _latest_cycle_data()
        if fallback and Path(fallback).resolve().exists():
            cycle_data_path = fallback
            print(f"[提示] 指定的文件不存在，已改用最新数据: {cycle_data_path}")
        else:
            cycle_data_path = None
    else:
        cycle_data_path = cycle_data_path and resolved or cycle_data_path
    if not cycle_data_path or not Path(cycle_data_path).resolve().exists():
        looked = _ic_dir().resolve()
        existing = list(looked.iterdir()) if looked.exists() else []
        hint = (
            "请先生成行业周期数据：\n"
            "  方式一：命令行执行  python scripts/tools/collect_industry_cycle_data.py\n"
            "  方式二：本脚本  python scripts/tools/industry_cycle_update.py --mode collect\n"
            "  方式三：前端「行业周期」页点击「采集数据」（若超时 504，可稍后刷新或改用方式一）\n"
            f"查找目录: {looked}"
        )
        if existing:
            hint += f"\n当前目录下仅有: {[p.name for p in existing]}"
        raise FileNotFoundError(hint)
    yaml_path = PROJECT_ROOT / "config" / "industry_cash_ratio_thresholds.yaml"
    result = run_suggestions(cycle_data_path, yaml_path)
    suggestions = result.get("suggestions", result) if isinstance(result, dict) else result
    date_str = datetime.now().strftime('%Y%m%d')
    out_path = _ic_dir() / f"suggest_{date_str}.json"
    payload = {
        "generated_at": datetime.now().isoformat(),
        "source_cycle_data": str(cycle_data_path),
        "suggestions": suggestions,
    }
    if isinstance(result, dict) and result.get("real_estate_l2_detail") is not None:
        payload["real_estate_l2_detail"] = result["real_estate_l2_detail"]
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"[OK] 建议已写入 {out_path}")
    return out_path, suggestions


def mode_full() -> Path:
    """完整流程：采集 → 建议 → 报告"""
    out_path = mode_collect()
    suggest_path, suggestions = mode_suggest(out_path)
    # 输出 Markdown 报告
    md_path = suggest_path.with_suffix(".md")
    lines = [f"## 行业周期变更建议（{datetime.now().strftime('%Y-%m-%d')})\n"]
    lines.append("| 行业 | 当前周期 | 建议周期 | 净现比 当前→建议 | 收现比 当前→建议 | 原因 |")
    lines.append("|------|----------|----------|------------------|------------------|------|")
    for s in suggestions:
        nc = f"{s['current_net_cash_ratio']}→{s['suggested_net_cash_ratio']}" if s.get('current_net_cash_ratio') is not None else "-"
        cc = f"{s['current_cash_receipt_ratio']}→{s['suggested_cash_receipt_ratio']}" if s.get('current_cash_receipt_ratio') is not None else "-"
        lines.append(f"| {s['industry']} | {s['current_cycle']} | {s['suggested_cycle']} | {nc} | {cc} | {s.get('reason', '')} |")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"[OK] 报告已写入 {md_path}")
    return suggest_path


def mode_apply(input_path: Path, dry_run: bool = False) -> bool:
    """应用已审批的变更到 YAML：更新净现比/收现比，并按建议周期移动行业（使 当前周期 与 建议周期 一致）"""
    import yaml
    import copy
    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    suggestions = data.get("suggestions", [])
    if not suggestions:
        print("无变更建议可应用")
        return False
    yaml_path = PROJECT_ROOT / "config" / "industry_cash_ratio_thresholds.yaml"
    with open(yaml_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    date_str = datetime.now().strftime('%Y%m%d')
    backup_path = yaml_path.parent / f"industry_cash_ratio_thresholds.yaml.bak.{date_str}"
    sugg_by_name = {s["industry"]: s for s in suggestions}
    cycles = config.get("industry_cycles", {})

    if dry_run:
        print("[dry-run] 将备份:", backup_path)
        print("[dry-run] 将更新以下行业:")
        for s in suggestions:
            if s.get("current_cycle") != s.get("suggested_cycle"):
                print(f"  - {s['industry']}: 周期 {s.get('current_cycle')}→{s.get('suggested_cycle')}")
            if s.get("suggested_net_cash_ratio") != s.get("current_net_cash_ratio") or \
               s.get("suggested_cash_receipt_ratio") != s.get("current_cash_receipt_ratio"):
                print(f"  - {s['industry']}: 净现比 {s.get('current_net_cash_ratio')}->{s.get('suggested_net_cash_ratio')}")
        return True

    shutil.copy(yaml_path, backup_path)

    # 1. 按建议周期移动行业：从 current_cycle 移到 suggested_cycle
    for s in suggestions:
        name, from_c, to_c = s.get("industry"), s.get("current_cycle"), s.get("suggested_cycle")
        if not name or not to_c or from_c == to_c:
            continue
        if from_c not in cycles or to_c not in cycles:
            continue
        source_list = cycles[from_c]
        target_list = cycles[to_c]
        block = next((b for b in source_list if b.get("name") == name), None)
        if not block:
            continue
        new_block = copy.deepcopy(block)
        if s.get("suggested_net_cash_ratio") is not None:
            new_block["net_cash_ratio"] = s["suggested_net_cash_ratio"]
        if s.get("suggested_cash_receipt_ratio") is not None:
            new_block["cash_receipt_ratio"] = s["suggested_cash_receipt_ratio"]
        source_list[:] = [b for b in source_list if b.get("name") != name]
        target_list.append(new_block)

    # 2. 对未移动的行业仅更新净现比/收现比
    for cycle in ["rising", "mature", "declining"]:
        for ind in cycles.get(cycle, []):
            s = sugg_by_name.get(ind.get("name"))
            if not s:
                continue
            if s.get("suggested_net_cash_ratio") is not None:
                ind["net_cash_ratio"] = s["suggested_net_cash_ratio"]
            if s.get("suggested_cash_receipt_ratio") is not None:
                ind["cash_receipt_ratio"] = s["suggested_cash_receipt_ratio"]

    with open(yaml_path, "w", encoding="utf-8") as f:
        yaml.dump(config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
    # 追加 CHANGELOG
    clog_path = PROJECT_ROOT / "docs" / "CHANGELOG_industry_cycle.md"
    clog_path.parent.mkdir(parents=True, exist_ok=True)
    with open(clog_path, "a", encoding="utf-8") as f:
        f.write(f"\n## {date_str}\n")
        for s in suggestions:
            parts = [s['industry']]
            if s.get('current_cycle') != s.get('suggested_cycle'):
                parts.append(f"周期 {s['current_cycle']}→{s['suggested_cycle']}")
            if s.get('current_net_cash_ratio') != s.get('suggested_net_cash_ratio'):
                parts.append(f"净现比 {s.get('current_net_cash_ratio')}→{s.get('suggested_net_cash_ratio')}")
            if s.get('current_cash_receipt_ratio') != s.get('suggested_cash_receipt_ratio'):
                parts.append(f"收现比 {s.get('current_cash_receipt_ratio')}→{s.get('suggested_cash_receipt_ratio')}")
            if len(parts) > 1:
                f.write(f"- {', '.join(parts)}\n")
    print(f"[OK] 已应用变更，备份: {backup_path}")
    return True


def mode_monitor() -> Path:
    """监控告警：检测异常并生成 alerts JSON"""
    cycle_data_path = _latest_cycle_data()
    if not cycle_data_path or not cycle_data_path.exists():
        raise FileNotFoundError("无 cycle_data，请先 collect")
    with open(cycle_data_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    alerts = []
    for item in data.get("industry_index", []):
        if abs(item.get("pct_chg", 0)) > 5:
            alerts.append({"type": "index_swing", "industry": item.get("industry"), "pct_chg": item.get("pct_chg")})
    import importlib.util
    spec = importlib.util.spec_from_file_location("rule_engine", PROJECT_ROOT / "scripts" / "tools" / "industry_cycle_rule_engine.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    run_suggestions = mod.run_suggestions
    yaml_path = PROJECT_ROOT / "config" / "industry_cash_ratio_thresholds.yaml"
    result = run_suggestions(cycle_data_path, yaml_path)
    suggestions = result.get("suggestions", result) if isinstance(result, dict) else result
    diff_count = sum(1 for s in suggestions if s.get("suggested_cycle") != s.get("current_cycle"))
    if diff_count >= 2:
        alerts.append({"type": "cycle_drift", "count": diff_count})
    date_str = datetime.now().strftime('%Y%m%d')
    out_path = _ic_dir() / f"alerts_{date_str}.json"
    _ic_dir().mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"generated_at": datetime.now().isoformat(), "alerts": alerts}, f, ensure_ascii=False, indent=2)
    if alerts:
        print(f"[WARN] 告警已写入 {out_path}: {len(alerts)} 条")
    return out_path


def main():
    # 子进程被 API 调用时统一用 UTF-8 输出，避免 Windows 下中文乱码
    if hasattr(sys.stdout, "reconfigure") and getattr(sys.stdout, "encoding", "").lower() != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass
    import argparse
    parser = argparse.ArgumentParser(description="行业周期配置更新工作流")
    parser.add_argument("--mode", choices=["full", "collect", "suggest", "apply", "monitor"], required=True)
    parser.add_argument("--input", type=Path, help="apply 模式: suggest_YYYYMMDD.json；suggest 模式: cycle_data_YYYYMMDD.json")
    parser.add_argument("--dry-run", action="store_true", help="apply 时仅输出 diff 不写入")
    args = parser.parse_args()

    _ic_dir().mkdir(parents=True, exist_ok=True)

    if args.mode == "collect":
        mode_collect()
    elif args.mode == "suggest":
        mode_suggest(cycle_data_path=args.input)
    elif args.mode == "full":
        mode_full()
    elif args.mode == "apply":
        inp = args.input or sorted(_ic_dir().glob("suggest_*.json"), key=lambda p: p.stem, reverse=True)[0]
        if not inp.exists():
            print("未找到 suggest_*.json，请先运行 --mode suggest 或 --mode full")
            sys.exit(1)
        mode_apply(inp, dry_run=args.dry_run)
    elif args.mode == "monitor":
        mode_monitor()


if __name__ == "__main__":
    main()
