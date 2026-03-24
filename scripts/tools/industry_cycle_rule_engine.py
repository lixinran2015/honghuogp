"""
行业周期规则引擎
基于采集数据 + 当前 YAML 配置，输出周期建议（rising/mature/declining）及阈值建议。

局限与优化方向（供后续迭代参考）：
- 营收来自财报，存在滞后，可引入业绩预告/PMI 等前瞻指标修正。
- 50 亿为绝对值，可改为相对指标（如资金净流出/行业流通市值）以跨行业可比。
- 5 日资金已用 20 日资金辅助过滤短期噪音；成熟期可结合资本开支等细化。
- 房地产已单独降级为下滑期，可细分子板块（保障房、商管等）再评估。
"""
import sys
from pathlib import Path
from typing import Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

# 规则常量（可调参）
MONEY_OUTFLOW_ABS_DECLINING_亿 = 50
MONEY_OUTFLOW_RATIO_DECLINING = 0.01  # 资金净流出/行业流通市值 >= 1% 可判下滑
FORECAST_PRE_DEC_WARN_PCT = 0.3
FORECAST_PRE_LOSS_WARN_PCT = 0.15
CAPEX_YOY_MATURE_THRESHOLD = -10

# 申万一级行业 -> 同花顺行业名列表（资金数据为同花顺口径，需汇总到申万）
SW_TO_THS_MONEYFLOW = {
    "通信": ["通信设备", "通信服务"],
    "电力设备": ["电网设备", "光伏设备", "风电设备", "电池", "电机", "其他电源设备"],
    "电子": ["消费电子", "半导体", "其他电子", "元件", "光学光电子"],
    "国防军工": ["军工装备", "军工电子"],
    "非银金融": ["证券", "保险", "多元金融"],
    "农林牧渔": ["种植业与林业", "养殖业", "农产品加工", "农化制品"],
    "有色金属": ["能源金属", "贵金属", "工业金属", "金属新材料", "小金属"],
    "房地产": ["房地产"],
    "综合": ["综合"],
    "银行": ["银行"],
    "公用事业": ["电力", "燃气", "环境治理"],
    "交通运输": ["公路铁路运输", "港口航运", "机场航运", "物流"],
    "家用电器": ["白色家电", "小家电", "黑色家电", "厨卫电器"],
    "计算机": ["计算机设备", "软件开发", "IT服务"],
    "医药生物": ["化学制药", "中药", "生物制品", "医疗器械", "医药商业", "医疗服务"],
    "纺织服饰": ["纺织制造", "服装家纺"],
    "传媒": ["影视院线", "文化传媒", "游戏"],
    "社会服务": ["旅游及酒店", "其他社会服务", "教育"],
    "轻工制造": ["造纸", "包装印刷", "家居用品"],
    "基础化工": ["化学制品", "化学原料", "电子化学品", "化学纤维", "塑料制品", "橡胶制品"],
    "建筑装饰": ["建筑装饰", "建筑材料"],
    "汽车": ["汽车整车", "汽车零部件", "汽车服务及其他"],
    "机械设备": ["通用设备", "专用设备", "自动化设备", "环保设备", "轨交设备", "工程机械"],
    "石油石化": ["石油加工贸易", "油气开采及服务"],
    "煤炭": ["煤炭开采加工"],
    "钢铁": ["钢铁"],
    "环保": ["环境治理", "环保设备"],
    "食品饮料": ["白酒", "饮料制造", "食品加工制造"],
    "商贸零售": ["零售", "贸易"],
    "美容护理": ["美容护理"],
    "电力": ["电力"],
}


def _moneyflow_for_sw(moneyflow_map: Dict[str, float], sw_name: str, raw_names: List[str]) -> float:
    """按申万行业名从资金映射中汇总金额（亿元）。先试申万名/配置名，再试同花顺口径汇总。"""
    for r in raw_names:
        if r in moneyflow_map:
            return float(moneyflow_map[r])
    # 申万与同花顺名称不一致，用 SW_TO_THS 汇总同花顺子行业
    ths_names = [sw_name] + SW_TO_THS_MONEYFLOW.get(sw_name, [])
    total = 0.0
    for name in ths_names:
        total += float(moneyflow_map.get(name, 0) or 0)
    return total


def load_cycle_data(path: Path) -> Dict:
    """加载采集数据"""
    import json
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_yaml_config(path: Path) -> Dict:
    """加载 YAML 配置"""
    import yaml
    with open(path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def build_industry_revenue_map(cycle_data: Dict) -> Dict[str, float]:
    """构建 行业->营收YoY 映射"""
    m = {}
    for item in cycle_data.get('industry_revenue_yoy', []):
        ind = item.get('industry')
        if ind and item.get('avg_yoy_sales') is not None:
            m[ind] = float(item['avg_yoy_sales'])
    return m


def build_industry_moneyflow_map(cycle_data: Dict, days: int = 5) -> Dict[str, float]:
    """构建 行业->近N个交易日资金净流入 映射（亿元）。按日期取最近 N 日再按行业汇总，便于 5 日/20 日分离。"""
    from collections import defaultdict
    items = cycle_data.get('money_flow', [])
    if not items:
        return {}
    # 解析并归一化金额；(date, name) -> amount（同一天同行业可能有多条则累加）
    by_date_name = defaultdict(float)
    for item in items[: 100 * 20]:  # 最多 20 日 * 约 50 行业
        name = item.get('name', item.get('industry_name', ''))
        if not name:
            continue
        amount = item.get('net_mf_amount', item.get('net_amount', 0)) or 0
        if isinstance(amount, (int, float)):
            amount = float(amount)
            if abs(amount) >= 1e6:
                amount = amount / 1e8
        else:
            amount = 0
        dt = item.get('date', '')
        by_date_name[(dt, name)] += amount
    # 取最近 N 个交易日
    unique_dates = sorted(set(d for d, _ in by_date_name if d), reverse=True)[:days]
    if not unique_dates:
        return {}
    date_set = set(unique_dates)
    m = defaultdict(float)
    for (d, name), amount in by_date_name.items():
        if d in date_set:
            m[name] += amount
    return dict(m)


def build_industry_index_map(cycle_data: Dict) -> Dict[str, float]:
    """构建 行业->指数涨跌幅 映射"""
    return {item['industry']: item['pct_chg'] for item in cycle_data.get('industry_index', []) if item.get('industry')}


def build_industry_float_mv_map(cycle_data: Dict) -> Dict[str, float]:
    """构建 行业->流通市值(亿元) 映射。float_mv_wan 为万元，除以 10000 得亿。"""
    m = {}
    for item in cycle_data.get('industry_float_mv', []):
        ind = item.get('industry')
        fw = item.get('float_mv_wan')
        if ind and fw is not None:
            try:
                m[ind] = float(fw) / 10000.0
            except (TypeError, ValueError):
                pass
    return m


def build_industry_forecast_risk_map(cycle_data: Dict) -> Dict[str, Dict]:
    """构建 行业->{ pre_dec_pct, pre_loss_pct, sample_count } 映射"""
    m = {}
    for item in cycle_data.get('industry_forecast_risk', []):
        ind = item.get('industry')
        if not ind:
            continue
        m[ind] = {
            'pre_dec_pct': item.get('pre_dec_pct'),
            'pre_loss_pct': item.get('pre_loss_pct'),
            'sample_count': item.get('sample_count', 0),
        }
    return m


def build_industry_capex_yoy_map(cycle_data: Dict) -> Dict[str, float]:
    """构建 行业->Capex同比(%) 映射。暂无采集时返回空。"""
    m = {}
    for item in cycle_data.get('industry_capex_yoy', []):
        ind = item.get('industry')
        val = item.get('capex_yoy_pct')
        if ind and val is not None:
            try:
                m[ind] = float(val)
            except (TypeError, ValueError):
                pass
    return m


def get_current_cycle_for_industry(yaml_config: Dict, industry: str) -> Optional[str]:
    """从 YAML 获取行业的当前周期"""
    industry_lower = industry.lower()
    for cycle in ['rising', 'mature', 'declining']:
        for ind in yaml_config.get('industry_cycles', {}).get(cycle, []):
            keywords = ind.get('keywords', [])
            if any(kw.lower() in industry_lower for kw in keywords):
                return cycle
    return None


def get_config_industry_name(yaml_config: Dict, industry: str) -> Optional[str]:
    """从 YAML 获取匹配的配置行业名"""
    mapping = yaml_config.get('industry_mapping', {})
    industry = mapping.get(industry, industry)
    if isinstance(industry, list):
        industry = industry[0] if industry else industry
    industry_lower = (industry or '').lower()
    for cycle in ['rising', 'mature', 'declining']:
        for ind in yaml_config.get('industry_cycles', {}).get(cycle, []):
            keywords = ind.get('keywords', [])
            if any(kw.lower() in industry_lower for kw in keywords):
                return ind.get('name')
    return None


def suggest_cycle(
    industry: str,
    revenue_yoy: Optional[float],
    moneyflow_5d: float,
    index_pct: Optional[float],
    moneyflow_20d: Optional[float] = None,
    float_mv_亿: Optional[float] = None,
    capex_yoy: Optional[float] = None,
) -> tuple[str, str]:
    """
    规则引擎：建议周期。
    可选 moneyflow_20d：近 20 日资金净流入（亿元），用于 5 日大幅流出时过滤短期噪音。
    可选 float_mv_亿：行业流通市值(亿)，用于按流出/市值比例判下滑（>=1% 可判下滑）。
    可选 capex_yoy：Capex 同比(%)，成熟期时可追加说明。
    Returns: (suggested_cycle, reason)
    """
    # R1: 营收 YoY > 10% 且 资金近5日净流入 -> rising（房地产单独降级为下滑期）
    if revenue_yoy is not None and revenue_yoy > 10 and moneyflow_5d > 0:
        if industry == '房地产':
            return ('declining', f'营收YoY {revenue_yoy:.1f}%，资金净流入（房地产单独降级为下滑期）')
        return ('rising', f'营收YoY {revenue_yoy:.1f}%，资金近5日净流入{moneyflow_5d:.1f}亿')
    # R3: 营收 YoY < 0% -> declining
    if revenue_yoy is not None and revenue_yoy < 0:
        return ('declining', f'营收YoY {revenue_yoy:.1f}% 为负')
    # 资金净流出：有流通市值时按流出/市值比例>=1%判下滑，否则按绝对值>-50亿判下滑
    abs_outflow = abs(moneyflow_5d)
    use_ratio = float_mv_亿 is not None and float_mv_亿 > 0
    outflow_ratio = (abs_outflow / float_mv_亿) if use_ratio else None
    if (use_ratio and outflow_ratio is not None and outflow_ratio >= MONEY_OUTFLOW_RATIO_DECLINING) or (
        not use_ratio and moneyflow_5d < -MONEY_OUTFLOW_ABS_DECLINING_亿
    ):
        if revenue_yoy is not None and revenue_yoy > 15:
            return ('rising', f'营收YoY {revenue_yoy:.1f}%（资金近5日净流出{abs_outflow:.1f}亿，营收高增不单凭资金判下滑）')
        if moneyflow_20d is not None and moneyflow_20d > -30:
            return ('mature', f'资金5日净流出{abs_outflow:.1f}亿，20日资金{moneyflow_20d:.1f}亿，疑为短期波动不判下滑')
        if use_ratio and outflow_ratio is not None:
            return ('declining', f'资金5日净流出占流通市值{outflow_ratio * 100:.2f}%')
        return ('declining', f'资金近5日净流出{abs_outflow:.1f}亿')
    # R2: 营收 YoY 0~10% -> mature（房地产单独降级为下滑期；排除“全 0”疑似数据缺失，优先用指数）
    if revenue_yoy is not None and 0 <= revenue_yoy <= 10:
        if industry == '房地产':
            return ('declining', f'营收YoY {revenue_yoy:.1f}%（房地产单独降级为下滑期）')
        # 营收 YoY 恰好为 0 时，多为 fact_fundamental.revenue_growth 未填充，优先用指数信号
        if revenue_yoy == 0 and index_pct is not None:
            if index_pct > 3:
                if industry == '房地产':
                    return ('declining', f'营收YoY 0%（疑似数据缺失），指数+{index_pct:.1f}%（房地产单独降级为下滑期）')
                return ('rising', f'营收YoY 0%（疑似数据缺失），指数+{index_pct:.1f}%')
            if index_pct < -3:
                return ('declining', f'营收YoY 0%（疑似数据缺失），指数{index_pct:.1f}%')
            return ('mature', f'营收YoY 0%（疑似数据缺失），指数波动{index_pct:.1f}%')
        if index_pct is not None and -3 <= index_pct <= 3:
            return ('mature', f'营收YoY {revenue_yoy:.1f}%，指数波动{index_pct:.1f}%')
        return ('mature', f'营收YoY {revenue_yoy:.1f}%')
    # R1 扩展：营收 YoY > 10% 且资金未明显净流出（无比例时>= -50 亿）-> rising（房地产单独降级为下滑期）
    # moneyflow_5d==0 表示无数据：data_warehouse/moneyflow/*.json 的 industry_moneyflow 为空
    no_outflow_declining = (use_ratio and (outflow_ratio is None or outflow_ratio < MONEY_OUTFLOW_RATIO_DECLINING)) or (
        not use_ratio and moneyflow_5d >= -MONEY_OUTFLOW_ABS_DECLINING_亿
    )
    if revenue_yoy is not None and revenue_yoy > 10 and no_outflow_declining:
        if industry == '房地产':
            return ('declining', f'营收YoY {revenue_yoy:.1f}%（房地产单独降级为下滑期）')
        if moneyflow_5d == 0:
            return ('rising', f'营收YoY {revenue_yoy:.1f}%（无行业资金流向数据，仅按营收高增判断）')
        return ('rising', f'营收YoY {revenue_yoy:.1f}%（资金近5日净流出{abs(moneyflow_5d):.1f}亿，未达-50亿阈值，按营收判断）')
    # R4: 指数单日 > ±5% -> 建议复核
    if index_pct is not None and abs(index_pct) > 5:
        return ('review', f'指数涨跌幅{index_pct:.1f}%，建议人工复核')
    # R5 兜底：缺营收/资金时，若有指数数据则用指数弱信号推断
    if revenue_yoy is None and index_pct is not None:
        if index_pct > 3:
            if industry == '房地产':
                return ('declining', f'指数+{index_pct:.1f}%（缺营收/资金数据，房地产单独降级为下滑期）')
            return ('rising', f'指数+{index_pct:.1f}%（缺营收/资金数据，仅指数信号）')
        if index_pct < -3:
            return ('declining', f'指数{index_pct:.1f}%（缺营收/资金数据，仅指数信号）')
        return ('mature', f'指数{index_pct:.1f}%（缺营收/资金数据，仅指数信号）')
    return ('unknown', '该行业在数据源中无匹配（数据缺失或 industry_index 未采集该申万行业）')


def suggest_thresholds(
    cycle: str,
    p25_ncr: Optional[float],
    p50_ncr: Optional[float],
    p75_ncr: Optional[float],
    p25_crr: Optional[float],
    p50_crr: Optional[float],
    p75_crr: Optional[float],
) -> tuple[Optional[float], Optional[float]]:
    """
    阈值智能建议
    Returns: (suggested_net_cash_ratio, suggested_cash_receipt_ratio)
    """
    if cycle == 'rising':
        ncr = (p25_ncr or 0.4) * 0.8 if p25_ncr else 0.4
        crr = (p25_crr or 0.5) * 0.8 if p25_crr else 0.5
    elif cycle == 'mature':
        ncr = (p50_ncr or 0.6) * 0.9 if p50_ncr else 0.6
        crr = (p50_crr or 0.7) * 0.9 if p50_crr else 0.7
    elif cycle == 'declining':
        ncr = max(p75_ncr or 0.8, 0.9)
        crr = max(p75_crr or 0.8, 0.85)
    else:
        ncr, crr = 0.6, 0.7
    # 净现比上限 1.2，避免金融行业 op_cf/net_profit 失真导致 3.x 等异常建议
    ncr = min(ncr, 1.2) if ncr is not None else 0.6
    crr = min(crr, 1.0) if crr is not None else 0.7
    return (round(ncr, 2), round(crr, 2))


def build_reverse_mapping(yaml_config: Dict) -> Dict[str, List[str]]:
    """配置名 -> [原始行业名列表]，支持 raw -> [config1, config2] 一对多"""
    rev = {}
    for raw, cfg in yaml_config.get('industry_mapping', {}).items():
        configs = [cfg] if not isinstance(cfg, list) else cfg
        for c in configs:
            if c:
                rev.setdefault(c, []).append(raw)
    return rev


def run_suggestions(cycle_data_path: Path, yaml_path: Path) -> Dict:
    """
    运行规则引擎。
    返回: {"suggestions": List[Dict], "real_estate_l2_detail": List (若有采集)}
    """
    cycle_data = load_cycle_data(cycle_data_path)
    yaml_config = load_yaml_config(yaml_path)
    revenue_map = build_industry_revenue_map(cycle_data)
    moneyflow_map_5d = build_industry_moneyflow_map(cycle_data, days=5)
    moneyflow_map_20d = build_industry_moneyflow_map(cycle_data, days=20)
    index_map = build_industry_index_map(cycle_data)
    float_mv_map = build_industry_float_mv_map(cycle_data)
    forecast_risk_map = build_industry_forecast_risk_map(cycle_data)
    capex_map = build_industry_capex_yoy_map(cycle_data)
    reverse_map = build_reverse_mapping(yaml_config)

    # 构建 net_cash 分布映射（key 为 dim_stock.industry 原始名）
    dist_map = {}
    for item in cycle_data.get('industry_net_cash_dist', []):
        dist_map[item['industry']] = item

    suggestions = []
    for cycle in ['rising', 'mature', 'declining']:
        for ind in yaml_config.get('industry_cycles', {}).get(cycle, []):
            config_name = ind.get('name', '')
            if not config_name:
                continue
            current = cycle
            raw_names = list(dict.fromkeys([config_name] + reverse_map.get(config_name, [])))
            revenue_yoy = next((revenue_map.get(r) for r in raw_names if r in revenue_map), None)
            moneyflow_5d = _moneyflow_for_sw(moneyflow_map_5d, config_name, raw_names)
            moneyflow_20d = _moneyflow_for_sw(moneyflow_map_20d, config_name, raw_names) or None
            index_pct = next((index_map.get(r) for r in raw_names if r in index_map), None)
            float_mv_亿 = next((float_mv_map.get(r) for r in raw_names if r in float_mv_map), None)
            capex_yoy = next((capex_map.get(r) for r in raw_names if r in capex_map), None)
            dist = next((dist_map.get(r) for r in raw_names if r in dist_map), {})
            suggested_cycle, reason = suggest_cycle(
                config_name, revenue_yoy, moneyflow_5d, index_pct, moneyflow_20d,
                float_mv_亿=float_mv_亿, capex_yoy=capex_yoy,
            )
            if suggested_cycle == 'review':
                suggested_cycle = current
            if suggested_cycle == 'unknown':
                suggested_cycle = current
            # 成熟期且 Capex 同比下行时追加说明
            if suggested_cycle == 'mature' and capex_yoy is not None and capex_yoy < CAPEX_YOY_MATURE_THRESHOLD:
                reason = f'{reason}（Capex同比{capex_yoy:.1f}%，成熟期特征）'
            # 上升期且业绩预告预减/首亏占比较高时追加提示
            forecast_risk = next((forecast_risk_map.get(r) for r in raw_names if r in forecast_risk_map), None)
            warning_forecast = False
            if suggested_cycle == 'rising' and forecast_risk:
                pre_dec = forecast_risk.get('pre_dec_pct')
                pre_loss = forecast_risk.get('pre_loss_pct')
                if (pre_dec is not None and pre_dec > FORECAST_PRE_DEC_WARN_PCT) or (
                    pre_loss is not None and pre_loss > FORECAST_PRE_LOSS_WARN_PCT
                ):
                    reason = f'{reason}（业绩预告预减/首亏占比较高，建议关注）'
                    warning_forecast = True
            sug_ncr, sug_crr = suggest_thresholds(
                suggested_cycle,
                dist.get('p25_ncr'), dist.get('p50_ncr'), dist.get('p75_ncr'),
                dist.get('p25_crr'), dist.get('p50_crr'), dist.get('p75_crr'),
            )
            curr_ncr, curr_crr = ind.get('net_cash_ratio'), ind.get('cash_receipt_ratio')
            item = {
                'industry': config_name,
                'current_cycle': current,
                'suggested_cycle': suggested_cycle,
                'current_net_cash_ratio': curr_ncr,
                'suggested_net_cash_ratio': sug_ncr,
                'current_cash_receipt_ratio': curr_crr,
                'suggested_cash_receipt_ratio': sug_crr,
                'reason': reason,
            }
            if warning_forecast:
                item['warning_forecast'] = True
            suggestions.append(item)
    out = {'suggestions': suggestions}
    if cycle_data.get('real_estate_l2'):
        out['real_estate_l2_detail'] = cycle_data['real_estate_l2']
    return out


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--cycle-data', type=Path, default=PROJECT_ROOT / 'data_warehouse' / 'industry_cycle' / 'cycle_data_latest.json')
    parser.add_argument('--yaml', type=Path, default=PROJECT_ROOT / 'config' / 'industry_cash_ratio_thresholds.yaml')
    args = parser.parse_args()
    # 查找最新的 cycle_data
    ic_dir = PROJECT_ROOT / 'data_warehouse' / 'industry_cycle'
    if not args.cycle_data.exists():
        files = sorted(ic_dir.glob('cycle_data_*.json'), key=lambda p: p.stem, reverse=True)
        args.cycle_data = files[0] if files else args.cycle_data
    result = run_suggestions(args.cycle_data, args.yaml)
    for s in result.get('suggestions', []):
        print(s)
