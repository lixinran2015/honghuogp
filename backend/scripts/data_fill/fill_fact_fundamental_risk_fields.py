"""
回填 fact_fundamental 表的排雷相关字段（operate_profit, fin_exp, goodwill, total_equity, audit_result）
从 Tushare 拉取并更新，供利息偿付、商誉、审计检查本地化使用。

使用前请先执行迁移：psql -U postgres -d your_db -f migrations/add_fact_fundamental_risk_columns.sql

用法: python -m backend.scripts.data_fill.fill_fact_fundamental_risk_fields [--batch N] [--delay S]
"""

import sys
import time
import argparse
import logging
from pathlib import Path
from datetime import datetime, timedelta

project_root = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from data_warehouse.db import get_shared_engine
from sqlalchemy import text
from backend.services.tushare_service import TushareService

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def _safe_float(v, default=0.0):
    if v is None:
        return default
    try:
        f = float(v)
        return default if (f != f or abs(f) == float('inf')) else f
    except (ValueError, TypeError):
        return default


def fetch_and_update_one(engine, ts: TushareService, ts_code: str, rate_delay: float = 0.5) -> int:
    """拉取单只股票的风险字段并更新 fact_fundamental，返回更新行数"""
    updated = 0
    try:
        # 最近 2 年
        start = (datetime.now() - timedelta(days=730)).strftime('%Y%m%d')
        end = datetime.now().strftime('%Y%m%d')

        income_df = None
        balance_df = None
        audit_df = None
        try:
            time.sleep(rate_delay)
            income_df = ts.pro.income(
                ts_code=ts_code, start_date=start, end_date=end,
                fields='ts_code,end_date,operate_profit,fin_exp'
            )
        except Exception as e:
            logger.debug(f"income {ts_code}: {e}")

        try:
            time.sleep(rate_delay)
            balance_df = ts.pro.balancesheet(
                ts_code=ts_code, start_date=start, end_date=end,
                fields='ts_code,end_date,goodwill,total_hldr_eqy_exc_min_int'
            )
        except Exception as e:
            logger.debug(f"balancesheet {ts_code}: {e}")

        try:
            time.sleep(rate_delay)
            audit_df = ts.pro.fina_audit(
                ts_code=ts_code, start_date=start, end_date=end,
                fields='ts_code,end_date,audit_result'
            )
        except Exception as e:
            logger.debug(f"fina_audit {ts_code}: {e}")

        income_map = {}
        if income_df is not None and not income_df.empty:
            for _, row in income_df.iterrows():
                ed = str(row.get('end_date', ''))
                if ed:
                    income_map[ed] = {
                        'operate_profit': _safe_float(row.get('operate_profit')),
                        'fin_exp': _safe_float(row.get('fin_exp'))
                    }

        balance_map = {}
        if balance_df is not None and not balance_df.empty:
            for _, row in balance_df.iterrows():
                ed = str(row.get('end_date', ''))
                if ed:
                    balance_map[ed] = {
                        'goodwill': _safe_float(row.get('goodwill')),
                        'total_equity': _safe_float(row.get('total_hldr_eqy_exc_min_int'))
                    }

        audit_map = {}
        if audit_df is not None and not audit_df.empty:
            for _, row in audit_df.iterrows():
                ed = str(row.get('end_date', ''))
                val = row.get('audit_result')
                if ed and val is not None and str(val).strip():
                    audit_map[ed] = str(val).strip()

        all_dates = set(income_map.keys()) | set(balance_map.keys()) | set(audit_map.keys())
        if not all_dates:
            return 0

        with engine.connect() as conn:
            for end_date in all_dates:
                inc = income_map.get(end_date, {})
                bal = balance_map.get(end_date, {})
                aud = audit_map.get(end_date)

                updates = []
                params = {'ts_code': ts_code, 'end_date': end_date.replace('-', '')}
                if inc:
                    if inc.get('operate_profit') is not None:
                        updates.append("operate_profit = :op")
                        params['op'] = inc['operate_profit']
                    if inc.get('fin_exp') is not None:
                        updates.append("fin_exp = :fe")
                        params['fe'] = inc['fin_exp']
                if bal:
                    if bal.get('goodwill') is not None:
                        updates.append("goodwill = :gw")
                        params['gw'] = bal['goodwill']
                    if bal.get('total_equity') is not None:
                        updates.append("total_equity = :te")
                        params['te'] = bal['total_equity']
                if aud is not None:
                    updates.append("audit_result = :ar")
                    params['ar'] = aud

                if not updates:
                    continue
                sql = f"""
                    UPDATE fact_fundamental
                    SET {', '.join(updates)}
                    WHERE ts_code = :ts_code AND end_date = :end_date
                """
                result = conn.execute(text(sql), params)
                conn.commit()
                if result.rowcount:
                    updated += result.rowcount
    except Exception as e:
        logger.warning(f"回填失败 {ts_code}: {e}")
    return updated


def main():
    parser = argparse.ArgumentParser(description='回填 fact_fundamental 排雷字段')
    parser.add_argument('--batch', type=int, default=50, help='每 N 只股票打印一次进度')
    parser.add_argument('--delay', type=float, default=0.3, help='每请求间隔（秒）')
    args = parser.parse_args()

    engine = get_shared_engine()
    ts = TushareService()
    if not ts.available:
        logger.error("Tushare 服务不可用")
        sys.exit(1)

    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT DISTINCT ts_code FROM fact_fundamental ORDER BY ts_code
        """)).fetchall()
    ts_codes = [r[0] for r in rows]
    total = len(ts_codes)
    logger.info(f"共 {total} 只股票待回填")

    updated_total = 0
    for i, ts_code in enumerate(ts_codes):
        n = fetch_and_update_one(engine, ts, ts_code, rate_delay=args.delay)
        updated_total += n
        if (i + 1) % args.batch == 0:
            logger.info(f"进度 {i+1}/{total}，已更新 {updated_total} 行")

    logger.info(f"回填完成，共更新 {updated_total} 行")


if __name__ == '__main__':
    main()
