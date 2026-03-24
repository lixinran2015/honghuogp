"""
排查金叉日期记录问题

用于排查股票的金叉日期是否正确记录
"""

import sys
import os
from datetime import datetime, date, timedelta
from typing import Optional, Dict

# 添加项目根目录到路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from data_warehouse.service.warehouse_service import WarehouseService
from data_warehouse.models.startup_candidate import FactStockStartupCandidate
from data_warehouse.models.generated_models import FactDailyPriceQfq
from backend.services.stock.stock_startup_filter import StockStartupFilter
from sqlalchemy import func, and_
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def verify_all_conditions(ts_code: str, check_date: date, stock_data: Dict, db_record):
    """
    详细验证所有条件是否真的满足
    
    Args:
        ts_code: 股票代码
        check_date: 检查日期
        stock_data: 股票数据
        db_record: 数据库记录
    """
    logger.info(f"\n{'='*80}")
    logger.info(f"详细验证所有条件（{check_date}）")
    logger.info(f"{'='*80}")
    
    # 1. 突破90日高点
    high_90d = stock_data.get('high_90d', 0) or stock_data.get('high_120d', 0)
    close = stock_data.get('close', 0)
    breakthrough_90d = high_90d > 0 and close > high_90d
    
    logger.info(f"\n1️⃣ 突破90日高点:")
    logger.info(f"  收盘价: {close:.4f}")
    logger.info(f"  前90日收盘价最高价: {high_90d:.4f}")
    if high_90d > 0:
        if breakthrough_90d:
            breakthrough_pct = (close - high_90d) / high_90d * 100
            logger.info(f"  ✅ 通过: 收盘价 > 前90日收盘价最高价（已突破 {breakthrough_pct:.2f}%）")
        else:
            distance_pct = (high_90d - close) / high_90d * 100
            logger.info(f"  ❌ 未通过: 收盘价 ≤ 前90日收盘价最高价（差距 {distance_pct:.2f}%）")
    else:
        logger.info(f"  ❌ 数据不足: high_90d = {high_90d}")
    
    # 2. 量能放大
    avg_turnover_20d = stock_data.get('avg_turnover_20d', 0) or stock_data.get('avg_amount_20d', 0)
    amount = stock_data.get('amount', 0)
    volume_ratio = amount / avg_turnover_20d if avg_turnover_20d > 0 else 0
    volume_amplified = avg_turnover_20d > 0 and amount >= avg_turnover_20d * 1.5
    
    logger.info(f"\n2️⃣ 量能放大:")
    logger.info(f"  当日成交额: {amount:,.0f}")
    logger.info(f"  20日均成交额: {avg_turnover_20d:,.0f}")
    logger.info(f"  量比: {volume_ratio:.4f}x")
    if volume_amplified:
        logger.info(f"  ✅ 通过: 量比 {volume_ratio:.4f}x ≥ 1.5")
    else:
        logger.info(f"  ❌ 未通过: 量比 {volume_ratio:.4f}x < 1.5")
    
    # 3. 均线多头排列
    ma5 = stock_data.get('ma5', 0)
    ma10 = stock_data.get('ma10', 0)
    ma20 = stock_data.get('ma20', 0)
    ma60 = stock_data.get('ma60', 0)
    bullish_alignment = ma5 > ma10 > ma20 > ma60
    
    logger.info(f"\n3️⃣ 均线多头排列:")
    logger.info(f"  MA5: {ma5:.4f}")
    logger.info(f"  MA10: {ma10:.4f}")
    logger.info(f"  MA20: {ma20:.4f}")
    logger.info(f"  MA60: {ma60:.4f}")
    if bullish_alignment:
        logger.info(f"  ✅ 通过: MA5({ma5:.4f}) > MA10({ma10:.4f}) > MA20({ma20:.4f}) > MA60({ma60:.4f})")
    else:
        logger.info(f"  ❌ 未通过: 不满足 MA5 > MA10 > MA20 > MA60")
        if ma5 <= ma10:
            logger.info(f"    问题: MA5({ma5:.4f}) ≤ MA10({ma10:.4f})")
        elif ma10 <= ma20:
            logger.info(f"    问题: MA10({ma10:.4f}) ≤ MA20({ma20:.4f})")
        elif ma20 <= ma60:
            logger.info(f"    问题: MA20({ma20:.4f}) ≤ MA60({ma60:.4f})")
    
    # 4. MACD金叉
    macd_dif = stock_data.get('macd_dif', 0)
    macd_dea = stock_data.get('macd_dea', 0)
    macd_dif_prev = stock_data.get('macd_dif_prev', 0)
    macd_dea_prev = stock_data.get('macd_dea_prev', 0)
    macd_hist = stock_data.get('macd_hist', 0)
    macd_golden_cross = (macd_dif > macd_dea and macd_dif_prev <= macd_dea_prev and macd_hist > 0)
    
    logger.info(f"\n4️⃣ MACD金叉:")
    logger.info(f"  当前 DIF: {macd_dif:.4f}")
    logger.info(f"  当前 DEA: {macd_dea:.4f}")
    logger.info(f"  前一日 DIF: {macd_dif_prev:.4f}")
    logger.info(f"  前一日 DEA: {macd_dea_prev:.4f}")
    logger.info(f"  MACD柱: {macd_hist:.4f}")
    if macd_golden_cross:
        logger.info(f"  ✅ 通过: DIF({macd_dif:.4f}) > DEA({macd_dea:.4f}) 且 前一日DIF({macd_dif_prev:.4f}) ≤ 前一日DEA({macd_dea_prev:.4f}) 且 MACD柱({macd_hist:.4f}) > 0")
    else:
        logger.info(f"  ❌ 未通过:")
        if macd_dif <= macd_dea:
            logger.info(f"    问题: DIF({macd_dif:.4f}) ≤ DEA({macd_dea:.4f})")
        if macd_dif_prev > macd_dea_prev:
            logger.info(f"    问题: 前一日DIF({macd_dif_prev:.4f}) > 前一日DEA({macd_dea_prev:.4f})（未形成上穿）")
        if macd_hist <= 0:
            logger.info(f"    问题: MACD柱({macd_hist:.4f}) ≤ 0")
    
    # 5. 大单净流入≥5%
    big_order_net = stock_data.get('big_order_net_inflow', 0)
    big_order_ratio = (big_order_net / amount * 100) if amount > 0 else 0
    big_order_passed = big_order_net > 0 and big_order_ratio >= 5.0
    
    logger.info(f"\n5️⃣ 大单净流入≥5%:")
    logger.info(f"  大单净流入: {big_order_net:,.0f}")
    logger.info(f"  当日成交额: {amount:,.0f}")
    logger.info(f"  占比: {big_order_ratio:.2f}%")
    if big_order_passed:
        logger.info(f"  ✅ 通过: 大单净流入 {big_order_net:,.0f} > 0 且占比 {big_order_ratio:.2f}% ≥ 5%")
    else:
        logger.info(f"  ❌ 未通过:")
        if big_order_net <= 0:
            logger.info(f"    问题: 大单净流入 {big_order_net:,.0f} ≤ 0")
        else:
            logger.info(f"    问题: 占比 {big_order_ratio:.2f}% < 5%")
    
    # 总结
    logger.info(f"\n{'='*80}")
    logger.info(f"条件验证总结:")
    logger.info(f"{'='*80}")
    conditions = {
        '突破90日高点': breakthrough_90d,
        '量能放大(量比≥1.5)': volume_amplified,
        '均线多头排列(5>10>20>60)': bullish_alignment,
        'MACD金叉': macd_golden_cross,
        '大单净流入≥5%': big_order_passed
    }
    
    passed_count = sum(conditions.values())
    logger.info(f"\n通过的条件数: {passed_count}/5")
    for condition, passed in conditions.items():
        status = "✅" if passed else "❌"
        logger.info(f"  {status} {condition}: {passed}")
    
    # 与数据库记录对比
    if db_record and db_record.passed_signals:
        db_signals = set(db_record.passed_signals)
        actual_signals = set()
        if breakthrough_90d:
            actual_signals.add('突破90日高点')
        if volume_amplified:
            actual_signals.add('量能放大(量比≥1.5)')
        if bullish_alignment:
            actual_signals.add('均线多头排列(5>10>20>60)')
        if macd_golden_cross:
            actual_signals.add('MACD金叉')
        if big_order_passed:
            actual_signals.add('大单净流入≥5%')
        
        logger.info(f"\n📊 与数据库记录对比:")
        logger.info(f"  数据库记录的信号: {sorted(db_signals)}")
        logger.info(f"  实际验证的信号: {sorted(actual_signals)}")
        
        missing_in_db = actual_signals - db_signals
        extra_in_db = db_signals - actual_signals
        
        if missing_in_db:
            logger.warning(f"  ⚠️ 数据库缺少的信号: {sorted(missing_in_db)}")
        if extra_in_db:
            logger.warning(f"  ⚠️ 数据库多余的信号: {sorted(extra_in_db)}")
        if not missing_in_db and not extra_in_db:
            logger.info(f"  ✅ 数据库记录与实际验证完全一致")


def check_golden_cross_date(ts_code: str, check_date: date, ws: WarehouseService):
    """
    检查指定日期的金叉情况
    
    Args:
        ts_code: 股票代码
        check_date: 检查日期
        ws: 数据仓库服务
    """
    session = ws.get_session()
    filter_service = StockStartupFilter(warehouse_service=ws)
    
    try:
        logger.info(f"\n{'='*80}")
        logger.info(f"检查股票: {ts_code} 在 {check_date} 的金叉情况")
        logger.info(f"{'='*80}")
        
        # 获取该日期的股票数据
        stock_data = filter_service._get_stock_indicators(ts_code, check_date.strftime('%Y-%m-%d'))
        
        if not stock_data:
            logger.warning(f"  ❌ 未找到 {check_date} 的股票数据")
            return None
        
        # 获取前一日的数据（用于判断金叉）
        prev_date = check_date - timedelta(days=1)
        prev_stock_data = None
        for i in range(1, 10):  # 往前找最多10天
            test_date = check_date - timedelta(days=i)
            prev_stock_data = filter_service._get_stock_indicators(ts_code, test_date.strftime('%Y-%m-%d'))
            if prev_stock_data:
                prev_date = test_date
                break
        
        # 显示关键指标
        ma5 = stock_data.get('ma5', 0)
        ma10 = stock_data.get('ma10', 0)
        ma5_prev = stock_data.get('ma5_prev', 0)
        ma10_prev = stock_data.get('ma10_prev', 0)
        
        logger.info(f"\n📊 {check_date} 的指标数据:")
        logger.info(f"  MA5: {ma5:.4f}")
        logger.info(f"  MA10: {ma10:.4f}")
        logger.info(f"  MA5_prev: {ma5_prev:.4f} (前一日)")
        logger.info(f"  MA10_prev: {ma10_prev:.4f} (前一日)")
        
        # 判断金叉
        is_golden_cross_today = ma5 > ma10 and ma5_prev <= ma10_prev
        
        logger.info(f"\n🔍 金叉判断:")
        logger.info(f"  当前: MA5({ma5:.4f}) > MA10({ma10:.4f}) = {ma5 > ma10}")
        logger.info(f"  前一日: MA5_prev({ma5_prev:.4f}) <= MA10_prev({ma10_prev:.4f}) = {ma5_prev <= ma10_prev}")
        logger.info(f"  是否金叉: {is_golden_cross_today}")
        
        if prev_stock_data:
            prev_ma5 = prev_stock_data.get('ma5', 0)
            prev_ma10 = prev_stock_data.get('ma10', 0)
            logger.info(f"\n📊 {prev_date} 的实际指标数据:")
            logger.info(f"  MA5: {prev_ma5:.4f}")
            logger.info(f"  MA10: {prev_ma10:.4f}")
            logger.info(f"  前一日是否满足: MA5({prev_ma5:.4f}) <= MA10({prev_ma10:.4f}) = {prev_ma5 <= prev_ma10}")
        
        # 检查基础条件
        from backend.services.stock.startup.conditions.basic_condition_checker import BasicConditionChecker
        basic_checker = BasicConditionChecker()
        basic_checks = basic_checker.check(stock_data, skip_golden_cross=False)
        
        logger.info(f"\n✅ 基础条件检查:")
        logger.info(f"  通过: {basic_checks['passed']}")
        if not basic_checks['passed']:
            logger.info(f"  失败原因: {basic_checks.get('failed_reasons', [])}")
        
        # 查询数据库中的记录
        db_record = session.query(FactStockStartupCandidate).filter(
            FactStockStartupCandidate.ts_code == ts_code,
            FactStockStartupCandidate.trade_date == check_date
        ).first()
        
        if db_record:
            logger.info(f"\n💾 数据库记录:")
            logger.info(f"  trade_date: {db_record.trade_date}")
            logger.info(f"  golden_cross_date: {db_record.golden_cross_date}")
            logger.info(f"  stage: {db_record.stage}")
            logger.info(f"  score: {db_record.score}")
            logger.info(f"  signals: {db_record.passed_signals}")
        else:
            logger.info(f"\n💾 数据库记录: 无")
        
        # ✅ 详细验证所有条件
        verify_all_conditions(ts_code, check_date, stock_data, db_record)
        
        return {
            'date': check_date,
            'is_golden_cross': is_golden_cross_today,
            'ma5': ma5,
            'ma10': ma10,
            'ma5_prev': ma5_prev,
            'ma10_prev': ma10_prev,
            'basic_passed': basic_checks['passed'],
            'db_record': db_record
        }
        
    finally:
        session.close()


def find_actual_golden_cross_date(ts_code: str, start_date: date, end_date: date, ws: WarehouseService):
    """
    查找实际的金叉日期
    
    Args:
        ts_code: 股票代码
        start_date: 开始日期
        end_date: 结束日期
        ws: 数据仓库服务
    """
    logger.info(f"\n{'='*80}")
    logger.info(f"查找 {ts_code} 在 {start_date} 至 {end_date} 期间的实际金叉日期")
    logger.info(f"{'='*80}")
    
    filter_service = StockStartupFilter(warehouse_service=ws)
    session = ws.get_session()
    
    try:
        # 获取日期范围内的所有交易日
        trading_dates_query = session.query(
            func.distinct(FactDailyPriceQfq.trade_date)
        ).filter(
            and_(
                FactDailyPriceQfq.ts_code == ts_code,
                FactDailyPriceQfq.trade_date >= start_date,
                FactDailyPriceQfq.trade_date <= end_date
            )
        ).order_by(
            FactDailyPriceQfq.trade_date.asc()
        ).all()
        
        trading_dates = sorted([row[0] for row in trading_dates_query])
        
        if not trading_dates:
            logger.warning(f"  未找到交易日数据")
            return None
        
        logger.info(f"  找到 {len(trading_dates)} 个交易日")
        
        golden_cross_dates = []
        
        for i, trade_date in enumerate(trading_dates):
            stock_data = filter_service._get_stock_indicators(ts_code, trade_date.strftime('%Y-%m-%d'))
            
            if not stock_data:
                continue
            
            ma5 = stock_data.get('ma5', 0)
            ma10 = stock_data.get('ma10', 0)
            ma5_prev = stock_data.get('ma5_prev', 0)
            ma10_prev = stock_data.get('ma10_prev', 0)
            
            # 判断金叉：MA5 > MA10 且 MA5_prev <= MA10_prev
            is_golden_cross = ma5 > ma10 and ma5_prev <= ma10_prev
            
            if is_golden_cross:
                golden_cross_dates.append(trade_date)
                logger.info(f"  ✅ {trade_date}: 金叉 (MA5={ma5:.4f} > MA10={ma10:.4f}, MA5_prev={ma5_prev:.4f} <= MA10_prev={ma10_prev:.4f})")
            else:
                if i < 5:  # 只显示前5个非金叉日期
                    logger.debug(f"  ❌ {trade_date}: 非金叉 (MA5={ma5:.4f}, MA10={ma10:.4f})")
        
        return golden_cross_dates
        
    finally:
        session.close()


def main():
    """主函数"""
    ts_code = "600893.SH"
    check_date_1 = date(2024, 11, 5)
    check_date_2 = date(2024, 11, 6)
    
    ws = WarehouseService()
    session = ws.get_session()
    
    try:
        # 查询数据库中的记录
        logger.info(f"\n{'='*80}")
        logger.info(f"查询数据库中的记录")
        logger.info(f"{'='*80}")
        
        records = session.query(FactStockStartupCandidate).filter(
            FactStockStartupCandidate.ts_code == ts_code,
            FactStockStartupCandidate.trade_date.in_([check_date_1, check_date_2])
        ).order_by(
            FactStockStartupCandidate.trade_date.asc()
        ).all()
        
        logger.info(f"\n找到 {len(records)} 条记录:")
        for record in records:
            logger.info(f"\n  ID: {record.id}")
            logger.info(f"  trade_date: {record.trade_date}")
            logger.info(f"  golden_cross_date: {record.golden_cross_date}")
            logger.info(f"  stage: {record.stage}")
            logger.info(f"  score: {record.score}")
            logger.info(f"  signals: {record.passed_signals}")
            logger.info(f"  created_at: {record.created_at}")
            logger.info(f"  updated_at: {record.updated_at}")
        
        # 检查11月05日的数据
        result_1 = check_golden_cross_date(ts_code, check_date_1, ws)
        
        # 检查11月06日的数据
        result_2 = check_golden_cross_date(ts_code, check_date_2, ws)
        
        # 查找实际的金叉日期
        start_date = check_date_1 - timedelta(days=5)
        end_date = check_date_2 + timedelta(days=5)
        actual_golden_cross_dates = find_actual_golden_cross_date(ts_code, start_date, end_date, ws)
        
        # 分析问题
        logger.info(f"\n{'='*80}")
        logger.info(f"问题分析")
        logger.info(f"{'='*80}")
        
        if result_1 and result_1['is_golden_cross']:
            logger.info(f"\n✅ 11月05日: 是金叉日")
            if result_1['db_record']:
                if result_1['db_record'].golden_cross_date == check_date_1:
                    logger.info(f"  ✅ 数据库记录正确: golden_cross_date = {result_1['db_record'].golden_cross_date}")
                else:
                    logger.warning(f"  ⚠️ 数据库记录错误: golden_cross_date = {result_1['db_record'].golden_cross_date} (应该是 {check_date_1})")
            else:
                logger.warning(f"  ⚠️ 数据库中没有11月05日的记录")
        else:
            logger.info(f"\n❌ 11月05日: 不是金叉日")
        
        if result_2 and result_2['is_golden_cross']:
            logger.info(f"\n✅ 11月06日: 是金叉日")
            if result_2['db_record']:
                logger.info(f"  数据库记录: golden_cross_date = {result_2['db_record'].golden_cross_date}")
        else:
            logger.info(f"\n❌ 11月06日: 不是金叉日")
            if result_2 and result_2['db_record']:
                logger.warning(f"  ⚠️ 11月06日不是金叉日，但数据库中有记录")
                logger.warning(f"  ⚠️ 可能的问题: 金叉日期记录错误")
        
        if actual_golden_cross_dates:
            logger.info(f"\n📅 实际金叉日期: {actual_golden_cross_dates}")
            if check_date_1 in actual_golden_cross_dates:
                logger.info(f"  ✅ 11月05日是实际金叉日期")
            if check_date_2 in actual_golden_cross_dates:
                logger.info(f"  ✅ 11月06日也是金叉日期（可能是连续金叉）")
        
    finally:
        session.close()


if __name__ == "__main__":
    main()

