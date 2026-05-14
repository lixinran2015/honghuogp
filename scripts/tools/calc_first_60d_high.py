#!/usr/bin/env python3
"""
计算指定股票列表在指定日期是否第一次突破60日新高。

用法:
    # 从数据库获取人气榜前100名，然后计算
    python calc_first_60d_high.py --popularity-date 2026-05-13 --check-date 2026-05-12

    # 直接传入股票代码列表
    python calc_first_60d_high.py --check-date 2026-05-12 --ts-codes 000001.SZ,000002.SZ

    # 计算全部股票（使用高效批量SQL）
    python calc_first_60d_high.py --check-date 2026-05-12 --all-stocks
"""

import os
import sys
import argparse
import logging
from datetime import date, datetime
from typing import List, Dict, Optional, Set
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).resolve().parents[2]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from sqlalchemy import func, and_, text
from data_warehouse.service.warehouse_service import WarehouseService
from data_warehouse.models.guba_popularity import FactGubaPopularityRank
from data_warehouse.models.generated_models import FactDailyPriceQfq
from data_warehouse.models.orm_classes import DimStock

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)


def get_popularity_stocks(session, popularity_date: date, max_rank: int = 100) -> List[str]:
    """从数据库获取指定日期的人气榜股票"""
    rows = session.query(FactGubaPopularityRank.ts_code).filter(
        FactGubaPopularityRank.crawl_date == popularity_date
    ).order_by(
        FactGubaPopularityRank.rank_position
    ).limit(max_rank).all()
    return [row[0] for row in rows]


def get_stock_names(session, ts_codes: List[str]) -> Dict[str, str]:
    """批量获取股票名称"""
    if not ts_codes:
        return {}
    rows = session.query(DimStock.ts_code, DimStock.name).filter(
        DimStock.ts_code.in_(ts_codes)
    ).all()
    return {row[0]: row[1] for row in rows}


def find_60d_high_stocks_batch(session, check_date: date, ts_codes_filter: Optional[List[str]] = None) -> List[str]:
    """
    使用批量SQL找出check_date是60日新高的所有股票。
    返回股票代码列表。
    """
    ts_filter_sql = ""
    params = {"check_date": check_date}

    if ts_codes_filter:
        ts_filter_sql = "AND p.ts_code = ANY(:ts_codes)"
        params["ts_codes"] = ts_codes_filter

    sql = text(f"""
        WITH dates AS (
            SELECT trade_date,
                   ROW_NUMBER() OVER (ORDER BY trade_date DESC) as rn
            FROM (SELECT DISTINCT trade_date FROM fact_daily_price_qfq WHERE trade_date <= :check_date) t
        ),
        check_date_row AS (SELECT trade_date FROM dates WHERE rn = 1),
        hist_60d_dates AS (SELECT trade_date FROM dates WHERE rn > 1 AND rn <= 61),
        max_60d AS (
            SELECT ts_code, MAX(close) as max_close
            FROM fact_daily_price_qfq
            WHERE trade_date IN (SELECT trade_date FROM hist_60d_dates)
            GROUP BY ts_code
        ),
        check_prices AS (
            SELECT ts_code, close
            FROM fact_daily_price_qfq
            WHERE trade_date = (SELECT trade_date FROM check_date_row)
              {ts_filter_sql.replace('p.ts_code', 'ts_code')}
        )
        SELECT c.ts_code, c.close, m.max_close
        FROM check_prices c
        JOIN max_60d m ON c.ts_code = m.ts_code
        WHERE c.close >= m.max_close
        ORDER BY c.ts_code
    """)

    rows = session.execute(sql, params).fetchall()
    return [row[0] for row in rows]


def get_recent_trading_dates(session, end_date: date, count: int = 65) -> List[date]:
    """获取最近N个交易日（包括end_date）"""
    rows = session.query(
        func.distinct(FactDailyPriceQfq.trade_date)
    ).filter(
        FactDailyPriceQfq.trade_date <= end_date
    ).order_by(
        FactDailyPriceQfq.trade_date.desc()
    ).limit(count).all()
    return sorted([row[0] for row in rows])


def check_is_60d_high_on_date(session, ts_code: str, check_date: date, trading_dates_cache: List[date]) -> Optional[bool]:
    """
    检查指定日期是否突破60日新高（收盘价 >= 前60个交易日最高价）
    使用预加载的交易日列表提高效率。
    """
    if check_date not in trading_dates_cache:
        return None

    check_idx = trading_dates_cache.index(check_date)
    if check_idx < 60:
        return None  # 数据不足60个交易日

    # 前60个交易日（不包括check_date）
    hist_dates = trading_dates_cache[check_idx - 60:check_idx]

    # 查询这60个交易日的收盘价
    rows = session.query(FactDailyPriceQfq.close).filter(
        and_(
            FactDailyPriceQfq.ts_code == ts_code,
            FactDailyPriceQfq.trade_date.in_(hist_dates)
        )
    ).all()

    closes = [float(row[0]) for row in rows if row[0] is not None and float(row[0]) > 0]
    if len(closes) < 60:
        return None

    max_close_60d = max(closes)

    # 查询check_date收盘价
    check_row = session.query(FactDailyPriceQfq.close).filter(
        and_(
            FactDailyPriceQfq.ts_code == ts_code,
            FactDailyPriceQfq.trade_date == check_date
        )
    ).first()

    if not check_row or check_row[0] is None:
        return None

    check_close = float(check_row[0])
    return check_close >= max_close_60d


def filter_first_60d_high(session, ts_codes: List[str], check_date: date) -> List[str]:
    """
    从已知是60日新高的股票中，筛选出第一次突破的。

    策略：
    1. 获取check_date之前的120个交易日
    2. 对每只股票，从最近到最远检查每一天是否是60日新高
    3. 如果找到任何一天是60日新高，则不是第一次

    优化：使用交易日缓存，避免重复查询日期。
    """
    if not ts_codes:
        return []

    # 获取check_date之前120个交易日（用于检查历史）
    all_dates = get_recent_trading_dates(session, check_date, count=121)
    if check_date not in all_dates:
        return []

    check_idx = all_dates.index(check_date)
    previous_dates = all_dates[:check_idx]

    if len(previous_dates) < 1:
        return ts_codes  # 之前没有交易日，全是第一次

    # 从最近到最远检查（更可能快速找到）
    # 限制检查最近60个交易日（如果连续多天新高，只需要找到最近的一个）
    dates_to_check = previous_dates[-60:] if len(previous_dates) > 60 else previous_dates

    first_high_stocks = []

    for ts_code in ts_codes:
        had_before = False
        # 从最近到最远检查
        for prev_date in reversed(dates_to_check):
            is_high = check_is_60d_high_on_date(session, ts_code, prev_date, all_dates)
            if is_high is True:
                had_before = True
                logger.debug(f"  {ts_code}: {prev_date} 已有60日新高")
                break

        if not had_before:
            first_high_stocks.append(ts_code)

    return first_high_stocks


def calc_first_60d_high(
    session,
    ts_codes: List[str],
    check_date: date,
    stock_names: Optional[Dict[str, str]] = None
) -> List[Dict]:
    """
    计算给定股票列表中第一次突破60日新高的股票。

    步骤：
    1. 批量SQL找出check_date是60日新高的股票
    2. 对这些股票，检查是否是第一次突破
    """
    if stock_names is None:
        stock_names = get_stock_names(session, ts_codes)

    logger.info(f"步骤1: 批量找出 {check_date} 的60日新高股票...")
    high_stocks = find_60d_high_stocks_batch(session, check_date, ts_codes)
    logger.info(f"  找到 {len(high_stocks)} 只60日新高股票")

    if not high_stocks:
        return []

    logger.info(f"步骤2: 筛选第一次突破的股票（检查之前是否有过60日新高）...")
    first_high_stocks = filter_first_60d_high(session, high_stocks, check_date)
    logger.info(f"  其中 {len(first_high_stocks)} 只是第一次突破")

    # 查询详情
    results = []
    rows = session.query(
        FactDailyPriceQfq.ts_code,
        FactDailyPriceQfq.close,
        FactDailyPriceQfq.change_pct,
        FactDailyPriceQfq.amount
    ).filter(
        and_(
            FactDailyPriceQfq.ts_code.in_(first_high_stocks),
            FactDailyPriceQfq.trade_date == check_date
        )
    ).all()

    for row in rows:
        results.append({
            'ts_code': row[0],
            'name': stock_names.get(row[0], ''),
            'check_date': check_date.isoformat(),
            'is_first_60d_high': True,
            'close': float(row[1]) if row[1] else None,
            'change_pct': float(row[2]) if row[2] else None,
            'amount': float(row[3]) if row[3] else None,
        })

    # 按涨跌幅排序
    results.sort(key=lambda x: x['change_pct'] or 0, reverse=True)
    return results


def main():
    parser = argparse.ArgumentParser(description='计算第一次突破60日新高的股票')
    parser.add_argument('--popularity-date', type=str, help='人气榜日期 (YYYY-MM-DD)，从数据库获取该日人气榜前100名')
    parser.add_argument('--check-date', type=str, required=True, help='检查日期 (YYYY-MM-DD)，判断这一天是否突破60日新高')
    parser.add_argument('--ts-codes', type=str, help='股票代码列表，逗号分隔，如 "000001.SZ,000002.SZ"')
    parser.add_argument('--all-stocks', action='store_true', help='计算全部股票（使用批量SQL，较快）')
    parser.add_argument('--max-rank', type=int, default=100, help='人气榜排名范围（默认前100名）')
    parser.add_argument('--output', type=str, help='输出结果到JSON文件')

    args = parser.parse_args()

    check_date = datetime.strptime(args.check_date, "%Y-%m-%d").date()

    ws = WarehouseService()
    session = ws.get_session()

    try:
        # 确定要计算的股票列表
        if args.popularity_date:
            popularity_date = datetime.strptime(args.popularity_date, "%Y-%m-%d").date()
            ts_codes = get_popularity_stocks(session, popularity_date, args.max_rank)
            logger.info(f"从 {popularity_date} 人气榜获取 {len(ts_codes)} 只股票")
        elif args.ts_codes:
            ts_codes = [c.strip() for c in args.ts_codes.split(',')]
            logger.info(f"传入 {len(ts_codes)} 只股票")
        elif args.all_stocks:
            # 获取check_date有数据的所有股票
            rows = session.query(func.distinct(FactDailyPriceQfq.ts_code)).filter(
                FactDailyPriceQfq.trade_date == check_date
            ).all()
            ts_codes = [row[0] for row in rows]
            logger.info(f"全部股票: {len(ts_codes)} 只")
        else:
            print("请指定 --popularity-date、--ts-codes 或 --all-stocks")
            sys.exit(1)

        if not ts_codes:
            print("没有要计算的股票")
            sys.exit(1)

        # 获取股票名称
        stock_names = get_stock_names(session, ts_codes)

        # 计算
        results = calc_first_60d_high(session, ts_codes, check_date, stock_names)

        # 输出结果
        print(f"\n{'='*70}")
        print(f"计算结果: {check_date} 第一次突破60日新高的股票")
        print(f"{'='*70}")
        print(f"检查股票数: {len(ts_codes)} 只")
        print(f"第一次突破60日新高: {len(results)} 只\n")

        for i, r in enumerate(results, 1):
            name = r['name'] or ''
            close = f"{r['close']:.2f}" if r['close'] else '-'
            change = f"{r['change_pct']:+.2f}%" if r['change_pct'] else '-'
            amount = f"{r['amount']/1e8:.2f}亿" if r['amount'] else '-'
            print(f"{i:3d}. {r['ts_code']} {name:10s}  收盘:{close:>8s}  涨幅:{change:>10s}  成交额:{amount}")

        # 保存到文件
        if args.output:
            import json
            with open(args.output, 'w', encoding='utf-8') as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            print(f"\n结果已保存到: {args.output}")

    finally:
        session.close()


if __name__ == '__main__':
    main()
