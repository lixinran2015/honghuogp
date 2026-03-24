"""
行业周期数据自动采集
采集宏观、行业指数、资金流向、行业营收增速、净现比/收现比分布
输出：data_warehouse/industry_cycle/cycle_data_YYYYMMDD.json
"""
import sys
import json
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional

# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Tushare 限频
class RateLimiter:
    def __init__(self, max_calls: int = 180, period: float = 60.0):
        import time
        import threading
        self.max_calls = max_calls
        self.period = period
        self.calls = []
        self.lock = threading.Lock()
        self._time = time.time
        self._sleep = time.sleep

    def wait_if_needed(self):
        import time
        with self.lock:
            now = self._time()
            self.calls = [t for t in self.calls if now - t < self.period]
            if len(self.calls) >= self.max_calls:
                wait_time = self.period - (now - min(self.calls)) + 0.2
                if wait_time > 0:
                    logger.debug(f"限频等待 {wait_time:.1f}s")
                    self._sleep(wait_time)
                    now = self._time()
                    self.calls = [t for t in self.calls if now - t < self.period]
            self.calls.append(now)


def collect_macro(tushare_pro, rate_limiter: RateLimiter) -> Dict:
    """采集宏观经济数据"""
    macro = {}
    try:
        rate_limiter.wait_if_needed()
        end_m = datetime.now().strftime('%Y%m')
        start_d = datetime.now() - timedelta(days=180)
        start_m = start_d.strftime('%Y%m')
        df = tushare_pro.cn_pmi(start_m=start_m, end_m=end_m)
        if df is not None and not df.empty:
            sort_col = 'month' if 'month' in df.columns else ('m' if 'm' in df.columns else df.columns[0])
            macro['pmi'] = df.sort_values(sort_col, ascending=False).head(3).to_dict(orient='records')
    except Exception as e:
        logger.warning(f"cn_pmi 采集失败: {e}")
    try:
        rate_limiter.wait_if_needed()
        df = tushare_pro.cn_gdp(start_year=datetime.now().year - 2)
        if df is not None and not df.empty:
            macro['gdp'] = df.to_dict(orient='records')
    except Exception as e:
        logger.warning(f"cn_gdp 采集失败: {e}")
    return macro


# 申万一级行业指数（Tushare 2021，与 industry_cycles 配置对应）
SW_INDUSTRY_MAP = [
    ("801150.SI", "医药生物"),
    ("801730.SI", "电力设备"),
    ("801080.SI", "电子"),
    ("801750.SI", "计算机"),
    ("801770.SI", "通信"),
    ("801740.SI", "国防军工"),
    ("801120.SI", "食品饮料"),
    ("801780.SI", "银行"),
    ("801790.SI", "非银金融"),
    ("801160.SI", "公用事业"),
    ("801170.SI", "交通运输"),
    ("801110.SI", "家用电器"),
    ("801200.SI", "商贸零售"),
    ("801010.SI", "农林牧渔"),
    ("801050.SI", "有色金属"),
    ("801180.SI", "房地产"),
    ("801040.SI", "钢铁"),
    ("801710.SI", "建筑材料"),
    ("801720.SI", "建筑装饰"),
    ("801760.SI", "传媒"),
    ("801210.SI", "社会服务"),
    ("801140.SI", "轻工制造"),
    ("801030.SI", "基础化工"),
    ("801230.SI", "综合"),
    ("801880.SI", "汽车"),
]


def collect_industry_float_mv(tushare_pro, rate_limiter: RateLimiter, trade_date: Optional[str] = None) -> List[Dict]:
    """采集申万一级行业当日流通市值（万元），用于相对资金指标。需 Tushare 5000 积分 sw_daily。"""
    import time
    result = []
    try:
        rate_limiter.wait_if_needed()
        dt = trade_date or datetime.now().strftime('%Y%m%d')
        df = tushare_pro.sw_daily(trade_date=dt, fields='ts_code,name,float_mv,total_mv')
        time.sleep(0.2)
        if df is None or df.empty:
            return result
        l1_codes = {t[0] for t in SW_INDUSTRY_MAP}
        for _, row in df.iterrows():
            tc = str(row.get('ts_code', '')).strip()
            if tc not in l1_codes:
                continue
            name = row.get('name')
            if not name:
                continue
            fmv = row.get('float_mv')
            if fmv is None or (hasattr(fmv, '__float__') and float(fmv) <= 0):
                continue
            try:
                fmv_wan = float(fmv)
            except (TypeError, ValueError):
                continue
            result.append({
                'industry': str(name).strip(),
                'float_mv_wan': round(fmv_wan, 0),
                'trade_date': dt,
            })
    except Exception as e:
        logger.warning(f"行业流通市值采集失败: {e}")
    return result


def collect_industry_index(tushare_pro, rate_limiter: RateLimiter, days: int = 20) -> List[Dict]:
    """采集申万行业指数涨跌幅"""
    import time
    result = []
    try:
        end_d = datetime.now()
        start_d = end_d - timedelta(days=days)
        start_str = start_d.strftime('%Y%m%d')
        end_str = end_d.strftime('%Y%m%d')
        for ts_code, name in SW_INDUSTRY_MAP:
            try:
                rate_limiter.wait_if_needed()
                df = tushare_pro.sw_daily(ts_code=ts_code, start_date=start_str, end_date=end_str)
                if df is not None and not df.empty:
                    df = df.sort_values('trade_date', ascending=False)
                    pct = float(df.iloc[0].get('pct_chg', df.iloc[0].get('pct_change', 0)) or 0)
                    result.append({'industry': name, 'index_code': ts_code, 'pct_chg': pct, 'trade_date': str(df.iloc[0].get('trade_date', ''))})
                time.sleep(0.25)
            except Exception as e:
                logger.debug(f"sw_daily {ts_code} 失败: {e}")
    except Exception as e:
        logger.warning(f"行业指数采集失败: {e}")
    return result


def collect_money_flow(moneyflow_dir: Path, days: int = 5) -> List[Dict]:
    """从 moneyflow JSON 读取近 N 日资金流向。唯一有效路径：项目根 data_warehouse/moneyflow/（与 DataWarehouse 写入一致）"""
    result = []
    # 统一使用项目根 data_warehouse/moneyflow/，不再使用 backend/data_warehouse/moneyflow/
    moneyflow_path = moneyflow_dir if (moneyflow_dir and moneyflow_dir.is_dir()) else PROJECT_ROOT / "data_warehouse" / "moneyflow"
    if not moneyflow_path.exists():
        logger.warning("moneyflow 目录不存在")
        return result
    files = sorted(moneyflow_path.glob("*.json"), key=lambda p: p.stem, reverse=True)[:days]
    for fp in files:
        try:
            with open(fp, 'r', encoding='utf-8') as f:
                data = json.load(f)
                for item in data.get('industry_moneyflow', []) or data.get('sector_moneyflow', []):
                    result.append({
                        'date': fp.stem,
                        'name': item.get('name', item.get('industry_name', item.get('industry', ''))),
                        'net_mf_amount': item.get('net_mf_amount', item.get('net_amount', 0)),
                    })
        except Exception as e:
            logger.debug(f"读取 {fp}: {e}")
    return result


def collect_industry_revenue_yoy(ws) -> List[Dict]:
    """按行业聚合营收同比增速（从 fact_fundamental.revenue_growth）"""
    from sqlalchemy import text
    result = []
    try:
        session = ws.get_session()
        try:
            q = text("""
                SELECT s.industry, AVG(f.revenue_growth)::float as avg_yoy_sales, COUNT(*) as cnt
                FROM fact_fundamental f
                JOIN dim_stock s ON f.ts_code = s.ts_code AND s.industry IS NOT NULL AND s.industry != ''
                WHERE f.end_date >= (SELECT MAX(end_date) FROM fact_fundamental) - interval '1 year'
                  AND f.revenue_growth IS NOT NULL
                GROUP BY s.industry
                HAVING COUNT(*) >= 3
            """)
            rows = session.execute(q).fetchall()
            for r in rows:
                result.append({
                    'industry': r[0],
                    'avg_yoy_sales': float(r[1]) if r[1] is not None else None,
                    'stock_count': r[2]
                })
        finally:
            session.close()
    except Exception as e:
        logger.warning(f"行业营收 YoY 采集失败: {e}")
    return result


def collect_industry_net_cash_dist(ws) -> List[Dict]:
    """按行业计算净现比/收现比分布（P25/P50/P75）
    净现比=op_cf/net_profit, 收现比=op_cf/revenue 或 ocf_to_revenue/100
    """
    from sqlalchemy import text
    result = []
    try:
        session = ws.get_session()
        try:
            # 计算净现比(op_cf/net_profit)和收现比(ocf_to_revenue/100)，再按行业聚合分位数
            # 净现比合理区间 0.01~2.0，排除分母过小导致的异常值（如 15、145）
            q = text("""
                WITH calc AS (
                    SELECT s.industry,
                        CASE WHEN f.net_profit IS NOT NULL AND f.op_cf IS NOT NULL AND ABS(f.net_profit::float) >= 10000
                             THEN LEAST(2.0, GREATEST(0.01, (f.op_cf::float / NULLIF(f.net_profit::float, 0)))) ELSE NULL END as ncr,
                        CASE WHEN f.ocf_to_revenue IS NOT NULL
                             THEN LEAST(1.0, (f.ocf_to_revenue::float / 100.0)) ELSE NULL END as crr
                    FROM fact_fundamental f
                    JOIN dim_stock s ON f.ts_code = s.ts_code
                    WHERE s.industry IS NOT NULL AND s.industry != ''
                      AND f.end_date >= (SELECT MAX(end_date) FROM fact_fundamental) - interval '1 year'
                ),
                stats AS (
                    SELECT industry,
                        PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY ncr) as p25_ncr,
                        PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY ncr) as p50_ncr,
                        PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY ncr) as p75_ncr,
                        PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY crr) as p25_crr,
                        PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY crr) as p50_crr,
                        PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY crr) as p75_crr,
                        COUNT(*) as cnt
                    FROM calc
                    WHERE ncr IS NOT NULL OR crr IS NOT NULL
                    GROUP BY industry
                    HAVING COUNT(*) >= 5
                )
                SELECT industry, p25_ncr, p50_ncr, p75_ncr, p25_crr, p50_crr, p75_crr, cnt FROM stats
            """)
            rows = session.execute(q).fetchall()
            cols = ['industry', 'p25_ncr', 'p50_ncr', 'p75_ncr', 'p25_crr', 'p50_crr', 'p75_crr', 'cnt']
            for r in rows:
                industry = r[0]  # 行业名为字符串，不转 float
                nums = [float(x) if x is not None else None for x in r[1:8]]
                result.append(dict(zip(cols, [industry] + nums)))
        finally:
            session.close()
    except Exception as e:
        logger.warning(f"净现比分布采集失败: {e}")
    return result


def collect_industry_forecast_risk(tushare_pro, rate_limiter: RateLimiter, report_period: Optional[str] = None) -> List[Dict]:
    """按报告期汇总各申万一级行业的业绩预告风险（预减/首亏占比）。依赖 dim_stock.industry 与 forecast/forecast_vip。"""
    import time
    from collections import defaultdict
    result = []
    try:
        if report_period is None:
            now = datetime.now()
            q_end = [(3, 31), (6, 30), (9, 30), (12, 31)]
            for m, day in reversed(q_end):
                if now.month >= m:
                    report_period = f"{now.year}{m:02d}{day:02d}"
                    break
            else:
                report_period = f"{now.year - 1}1231"
        ts_to_ind: Dict[str, str] = {}
        try:
            from data_warehouse.service.warehouse_service import WarehouseService
            from data_warehouse.models.orm_classes import DimStock
            ws = WarehouseService()
            session = ws.get_session()
            try:
                rows = session.query(DimStock.ts_code, DimStock.industry).filter(
                    DimStock.industry.isnot(None), DimStock.industry != ""
                ).all()
                ts_to_ind = {str(r[0]): str(r[1]).strip() for r in rows if r[0] and r[1]}
            finally:
                session.close()
        except Exception as e:
            logger.debug(f"dim_stock 行业映射失败: {e}")
        if not ts_to_ind:
            return result
        rate_limiter.wait_if_needed()
        try:
            df = tushare_pro.forecast_vip(period=report_period, fields='ts_code,type')
        except Exception:
            try:
                df = tushare_pro.forecast(period=report_period, fields='ts_code,type')
            except Exception:
                df = None
        time.sleep(0.3)
        if df is None or df.empty:
            return result
        # 预减/首亏/续亏/略减 -> pre_dec; 首亏/续亏 -> pre_loss
        dec_types = {'预减', '首亏', '续亏', '略减'}
        loss_types = {'首亏', '续亏'}
        by_ind = defaultdict(lambda: {'dec': 0, 'loss': 0, 'total': 0})
        for _, row in df.iterrows():
            tc = str(row.get('ts_code', '')).strip()
            ind = ts_to_ind.get(tc)
            if not ind:
                continue
            t = str(row.get('type', '')).strip()
            by_ind[ind]['total'] += 1
            if t in dec_types:
                by_ind[ind]['dec'] += 1
            if t in loss_types:
                by_ind[ind]['loss'] += 1
        for ind, cnt in by_ind.items():
            total = cnt['total']
            if total < 3:
                continue
            result.append({
                'industry': ind,
                'report_period': report_period,
                'pre_dec_pct': round(cnt['dec'] / total, 4),
                'pre_loss_pct': round(cnt['loss'] / total, 4),
                'sample_count': total,
            })
    except Exception as e:
        logger.warning(f"业绩预告风险采集失败: {e}")
    return result


def collect_real_estate_l2(tushare_pro, rate_limiter: RateLimiter) -> List[Dict]:
    """采集房地产下申万二级行业及成分股，供子板块展示或规则细化。"""
    import time
    result = []
    try:
        rate_limiter.wait_if_needed()
        df = tushare_pro.index_classify(level='L2', src='SW')
        time.sleep(0.2)
        if df is None or df.empty:
            return result
        code_col = 'index_code' if 'index_code' in df.columns else df.columns[0]
        name_col = 'name' if 'name' in df.columns else df.columns[1]
        l2_real_estate = []
        for _, row in df.iterrows():
            name = str(row.get(name_col, '')).strip()
            if '房地产' in name:
                l2_real_estate.append((str(row.get(code_col, '')).strip(), name))
        for l2_code, l2_name in l2_real_estate:
            if not l2_code:
                continue
            try:
                rate_limiter.wait_if_needed()
                mf = tushare_pro.index_member_all(l2_code=l2_code, is_new='Y')
                time.sleep(0.15)
                constituents = []
                if mf is not None and not mf.empty and 'ts_code' in mf.columns:
                    constituents = mf['ts_code'].astype(str).str.strip().tolist()
                result.append({'l2_code': l2_code, 'l2_name': l2_name, 'constituents': constituents})
            except Exception as e:
                logger.debug(f"index_member_all {l2_code} 失败: {e}")
    except Exception as e:
        logger.warning(f"房地产二级采集失败: {e}")
    return result


def main(start_date: Optional[str] = None, end_date: Optional[str] = None):
    """主入口"""
    out_dir = PROJECT_ROOT / "data_warehouse" / "industry_cycle"
    out_dir.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime('%Y%m%d')
    out_path = out_dir / f"cycle_data_{date_str}.json"

    rate_limiter = RateLimiter()
    data = {
        'generated_at': datetime.now().isoformat(),
        'macro': {},
        'industry_index': [],
        'industry_float_mv': [],
        'money_flow': [],
        'industry_revenue_yoy': [],
        'industry_net_cash_dist': [],
        'industry_forecast_risk': [],
        'industry_capex_yoy': [],
        'real_estate_l2': [],
    }

    # 1. 宏观 + 行业指数 + 行业流通市值（需 Tushare 权限）
    try:
        from backend.services.tushare_service import TushareService
        ts = TushareService()
        if ts.available:
            data['macro'] = collect_macro(ts.pro, rate_limiter)
            data['industry_index'] = collect_industry_index(ts.pro, rate_limiter)
            try:
                data['industry_float_mv'] = collect_industry_float_mv(ts.pro, rate_limiter)
            except Exception as e:
                logger.warning(f"行业流通市值采集失败: {e}")
            try:
                data['industry_forecast_risk'] = collect_industry_forecast_risk(ts.pro, rate_limiter)
            except Exception as e:
                logger.warning(f"业绩预告风险采集失败: {e}")
            try:
                data['real_estate_l2'] = collect_real_estate_l2(ts.pro, rate_limiter)
            except Exception as e:
                logger.warning(f"房地产二级采集失败: {e}")
    except Exception as e:
        logger.warning(f"Tushare 初始化失败: {e}")

    # 2. 资金流向（拉取近 20 日供规则引擎做 5 日/20 日分离，过滤短期噪音）
    data['money_flow'] = collect_money_flow(PROJECT_ROOT / "data_warehouse" / "moneyflow", days=20)

    # 3. 行业营收、净现比（需 WarehouseService + fact_fundamental）
    try:
        from data_warehouse.service.warehouse_service import WarehouseService
        ws = WarehouseService()
        data['industry_revenue_yoy'] = collect_industry_revenue_yoy(ws)
        data['industry_net_cash_dist'] = collect_industry_net_cash_dist(ws)
    except Exception as e:
        logger.warning(f"WarehouseService 失败: {e}")

    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.info(f"✅ 数据已写入 {out_path}")
    return out_path


if __name__ == '__main__':
    main()
