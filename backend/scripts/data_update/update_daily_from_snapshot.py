"""
使用新的日线数据源（Baostock/AkShare）更新数据仓库
从 MarketDataService_v2 获取最新交易日数据并保存到 PostgreSQL 数据仓库
"""

import logging
import sys
from pathlib import Path
from datetime import date, datetime, timedelta
from typing import Optional, List
import pandas as pd
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from backend.services.market_data_service_v2 import MarketDataService
from backend.services.data.postgres_warehouse import PostgresWarehouse
from backend.services.stock.stock_universe_service import StockUniverseService
from data_warehouse.layers.raw_layer import RawDataLayer
from data_warehouse.layers.clean_layer import CleanDataLayer
from data_warehouse.service.warehouse_service import WarehouseService

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# 使用统一的股票代码转换工具
from backend.utils.stock_code_utils import convert_code_to_ts_code


def find_latest_trade_date(market_service, max_days_back: int = 10) -> Optional[date]:
    """
    数据获取场景：确定应该获取哪个交易日的数据

    使用 get_target_date_for_fetch 确保收盘后能正确获取当天数据，
    而不是总是获取数据库中最新有数据的日期。

    Args:
        market_service: MarketDataService 实例（保留参数以兼容旧代码）
        max_days_back: 最多往前查找多少天

    Returns:
        date: 应该获取数据的交易日，如果找不到返回None
    """
    try:
        # 使用专门的数据获取日期确定函数
        from backend.utils.trade_date_utils import get_target_date_for_fetch

        ws = WarehouseService()
        target_date = get_target_date_for_fetch(ws, max_days_back=max_days_back)

        if target_date:
            logger.info(f"✅ 确定数据获取目标日期: {target_date}")
            return target_date
        else:
            logger.warning("⚠️ 未找到目标交易日")
            return None

    except Exception as e:
        logger.error(f"查找目标交易日失败: {e}", exc_info=True)
        # 降级：使用简单判断
        today = date.today()
        for i in range(max_days_back):
            check_date = today - timedelta(days=i)
            if check_date.weekday() < 5:  # 周一到周五
                logger.info(f"✅ 使用降级逻辑，假定交易日: {check_date}")
                return check_date
        return None


def update_daily_prices_from_snapshot(
    target_date: Optional[date] = None,
    stock_codes: Optional[List[str]] = None,
    task_type: str = 'scheduled',
    task_id: Optional[str] = None
) -> bool:
    """
    使用新的日线数据源更新数据仓库
    
    Args:
        target_date: 目标日期，如果为None则自动查找最近交易日
        stock_codes: 可选的股票代码列表（6位数字格式），如果为None则获取全市场
        
    Returns:
        bool: 是否更新成功
    """
    from backend.utils.task_logger import task_execution_log
    
    with task_execution_log('daily_update', task_type) as log_entry:
        logger.info("=" * 60)
        logger.info("使用新日线数据源更新数据仓库")
        logger.info("=" * 60)
        
        # 初始化服务
        market_service = MarketDataService()
        
        # 检查接口状态（接口状态通）
        # 注意：我们不再依赖 market_service.daily_source，而是直接管理 iFinD/Tushare 数据源
        logger.info("📊 日线数据更新开始，将优先尝试 iFinD 数据源")
        
        # 确定目标日期
        if target_date is None:
            # 自动查找最近交易日
            target_date = find_latest_trade_date(market_service)
            if target_date is None:
                logger.error("❌ 无法找到最近交易日")
                return False
            logger.info(f"📅 自动选择交易日: {target_date}")
        else:
            logger.info(f"📅 使用指定日期: {target_date}")
        
        # 初始化其他服务
        warehouse_service = WarehouseService()
        universe_service = StockUniverseService()
        raw_layer = RawDataLayer()
        clean_layer = CleanDataLayer()
    
        # 获取股票列表（从全市场获取）
        if stock_codes is None:
            logger.info("从dim_stock表获取全市场股票列表...")
            try:
                from data_warehouse.models import DimStock
                
                session = warehouse_service.get_session()
                try:
                    # 获取所有A股代码（排除退市股票）
                    stocks = session.query(DimStock.ts_code).filter(
                        DimStock.ts_code.isnot(None),
                        DimStock.delist_date.is_(None)
                    ).all()
                    
                    all_ts_codes = [s[0] for s in stocks if s[0]]
                    
                    if not all_ts_codes:
                        logger.error("❌ dim_stock表为空，无法获取股票列表")
                        return False
                    
                    # 转换为6位数字格式
                    stock_codes = []
                    for ts_code in all_ts_codes:
                        code = ts_code.replace('.SH', '').replace('.SZ', '').replace('.BJ', '')
                        if len(code) == 6:
                            stock_codes.append(code)
                    
                    logger.info(f"✅ 从dim_stock表获取到 {len(stock_codes)} 只股票（全市场）")
                finally:
                    session.close()
                    
            except Exception as e:
                logger.error(f"❌ 获取全市场股票失败: {e}", exc_info=True)
                return False
        else:
            logger.info(f"使用指定的 {len(stock_codes)} 只股票")
        
        # 使用 Tushare 优先策略获取数据
        date_str = target_date.strftime("%Y%m%d")
        date_str_dash = target_date.strftime("%Y-%m-%d")
        
        logger.info(f"📥 获取日线数据: date={date_str}, codes={len(stock_codes)}")
        
        # ✅ 检查数据库中该日期的数据完整度（避免重复获取）
        completeness_threshold = 0.90  # 90%完整度阈值
        should_skip_fetch = False
        existing_complete_count = 0
        
        try:
            from data_warehouse.models.generated_models import FactDailyPriceQfq
            from data_warehouse.models.generated_models import DimTradeCalendar
            from sqlalchemy import func
            
            # 转换为ts_code格式用于查询
            ts_codes = []
            for code in stock_codes:
                ts_code = convert_code_to_ts_code(code)
                if ts_code:
                    ts_codes.append(ts_code)
            
            total_codes = len(ts_codes)
            if total_codes > 0:
                session = warehouse_service.get_session()
                try:
                    # 查询已有记录数
                    existing_count = session.query(func.count(FactDailyPriceQfq.ts_code)).filter(
                        FactDailyPriceQfq.trade_date == target_date,
                        FactDailyPriceQfq.ts_code.in_(ts_codes)
                    ).scalar()
                    
                    # 查询完整记录数（收盘价 > 0）
                    complete_count = session.query(func.count(FactDailyPriceQfq.ts_code)).filter(
                        FactDailyPriceQfq.trade_date == target_date,
                        FactDailyPriceQfq.ts_code.in_(ts_codes),
                        FactDailyPriceQfq.close > 0
                    ).scalar()
                    
                    existing_complete_count = complete_count
                    completeness_ratio = complete_count / total_codes if total_codes > 0 else 0.0
                    
                    logger.info(f"🔍 {target_date} 日线数据完整性检查: 已有记录数={existing_count}/{total_codes}, "
                               f"完整记录数（收盘价>0）={complete_count}/{total_codes}, "
                               f"完整性比例={completeness_ratio:.2%}, 阈值={completeness_threshold:.2%}")
                    
                    # 如果记录数完整且完整性比例达到阈值，跳过获取
                    if existing_count == total_codes and completeness_ratio >= completeness_threshold:
                        # 额外校验：如果 pre_close 退化成与 close 基本相等，且上一交易日 close 差异明显，
                        # 则说明数据源侧 pre_close/pct_chg 可能错误，需要重新计算 change_pct。
                        prev_trade_date = (
                            session.query(DimTradeCalendar.trade_date)
                            .filter(DimTradeCalendar.trade_date < target_date, DimTradeCalendar.is_open == True)
                            .order_by(DimTradeCalendar.trade_date.desc())
                            .limit(1)
                            .scalar()
                        )
                        if prev_trade_date:
                            prev_subq = (
                                session.query(
                                    FactDailyPriceQfq.ts_code.label("ts_code"),
                                    FactDailyPriceQfq.close.label("prev_close"),
                                )
                                .filter(FactDailyPriceQfq.trade_date == prev_trade_date)
                                .subquery()
                            )

                            # mismatch：当前 close 与上一交易日 close 不同；但当前 pre_close 退化为 close（导致 change_pct=0）
                            mismatch_count = (
                                session.query(func.count())
                                .select_from(FactDailyPriceQfq)
                                .join(prev_subq, FactDailyPriceQfq.ts_code == prev_subq.c.ts_code)
                                .filter(
                                    FactDailyPriceQfq.trade_date == target_date,
                                    FactDailyPriceQfq.ts_code.in_(ts_codes),
                                    FactDailyPriceQfq.pre_close.isnot(None),
                                    func.abs(FactDailyPriceQfq.pre_close - FactDailyPriceQfq.close) < 0.0001,
                                    func.abs(FactDailyPriceQfq.change_pct) < 0.00001,
                                    func.abs(FactDailyPriceQfq.close - prev_subq.c.prev_close) > 0.0001,
                                )
                                .scalar()
                            )

                            if mismatch_count and mismatch_count > 0:
                                logger.warning(
                                    f"⚠️ 检测到 change_pct 异常数据（mismatch_count={mismatch_count}），{target_date} 不跳过获取以重算"
                                )
                            else:
                                logger.info(
                                    f"✅ {target_date} 的日线数据已存在且完整（完整性={completeness_ratio:.2%} >= {completeness_threshold:.2%}），跳过获取"
                                )
                                should_skip_fetch = True
                        else:
                            logger.info(f"✅ {target_date} 跳过校验（无前一交易日），跳过获取")
                            should_skip_fetch = True
                    elif existing_count > 0 and completeness_ratio < completeness_threshold:
                        logger.info(f"⚠️ {target_date} 的日线数据不完整（完整性={completeness_ratio:.2%} < {completeness_threshold:.2%}），将重新获取")
                    elif existing_count == 0:
                        logger.info(f"📥 {target_date} 的日线数据不存在，将获取")
                finally:
                    session.close()
            else:
                logger.warning(f"⚠️ 无法转换股票代码，跳过完整性检查，将继续获取数据")
        except Exception as e:
            logger.warning(f"⚠️ 检查数据完整性失败: {e}，将继续获取数据", exc_info=True)
        
        all_dfs = []
        data_source_used = None

        # 显示当前数据获取决策
        if should_skip_fetch:
            logger.info(f"📊 目标日期 {target_date} 数据已完整，将跳过获取")
        else:
            logger.info(f"📊 目标日期 {target_date} 数据不完整或不存在，将从数据源获取")

        # 如果数据完整，跳过获取
        if should_skip_fetch:
            logger.info(f"✅ 跳过数据获取，使用已有数据（完整性 >= {completeness_threshold:.0%}）")
            # 返回成功，但不需要处理数据
            if log_entry:
                log_entry.update_records_processed(existing_complete_count)
            return True
        
        # 1. 强制优先使用 iFinDPy（用户明确要求日线数据从iFinD获取）
        try:
            from backend.services.data_sources.ifind_daily_source import IfindDailySource
            ifind = IfindDailySource()
            if ifind.available:
                logger.info("📥 使用 iFinDPy 获取数据（用户配置的优先数据源）...")
                df = ifind.get_daily_snapshot(date=date_str_dash, codes=stock_codes)
                if df is not None and not df.empty:
                    all_dfs.append(df)
                    data_source_used = "iFinDPy"
                    logger.info(f"✅ iFinDPy 获取到 {len(df)} 条数据")
                else:
                    logger.warning("⚠️ iFinDPy 返回空数据，将尝试其他数据源")
            else:
                logger.warning("⚠️ iFinDPy 不可用（可能未登录），将尝试其他数据源")
        except Exception as e:
            logger.warning(f"⚠️ iFinDPy 获取失败: {e}，将尝试其他数据源")
        
        # 2. 如果iFinD失败，根据操作系统决定是否降级
        import platform
        if not all_dfs:
            if platform.system() == 'Darwin':
                # macOS 开发环境：iFinD没有macOS版本，允许降级到Tushare
                logger.warning("⚠️ macOS环境：iFinDPy库不兼容，降级到Tushare获取数据")
                try:
                    from backend.services.data_sources.tushare_source import TushareDailySource
                    tushare = TushareDailySource()
                    if tushare.available:
                        logger.info("📥 使用 Tushare 获取数据...")
                        df = tushare.get_daily_snapshot(date_str)
                        if df is not None and not df.empty:
                            all_dfs.append(df)
                            data_source_used = "Tushare"
                            logger.info(f"✅ Tushare 获取到 {len(df)} 条数据")
                        else:
                            logger.warning("⚠️ Tushare 返回空数据")
                            if log_entry:
                                log_entry.update_records_processed(0)
                            return False
                    else:
                        logger.error("❌ Tushare 不可用")
                        if log_entry:
                            log_entry.update_records_processed(0)
                        return False
                except Exception as e:
                    logger.error(f"❌ Tushare 获取失败: {e}")
                    if log_entry:
                        log_entry.update_records_processed(0)
                    return False
            else:
                # Linux生产环境：强制使用iFinD，不允许降级
                logger.error("❌ iFinDPy 未能获取到数据，且用户要求使用iFinD作为日线数据源，不再尝试其他数据源")
                logger.error("   请检查：1) iFinD是否已登录 2) 账号是否有足够额度 3) 网络连接")
                if log_entry:
                    log_entry.update_records_processed(0)
                return False
        
        
        if data_source_used:
            logger.info(f"✅ 使用数据源: {data_source_used}")
        
        # 合并所有批次的数据
        if not all_dfs:
            logger.warning("⚠️ 所有批次都未获取到数据")
            return False
        
        df = pd.concat(all_dfs, ignore_index=True)
        logger.info(f"✅ 总共获取到 {len(df)} 条日线数据")
        
        # 预先准备“上一交易日 close”，用于纠正数据源 pre_close/pct_chg 错误导致的 change_pct=0
        # 典型场景：数据源返回 pct_chg=0，但实际 close 相比上一交易日仍有涨跌。
        prev_close_map = {}
        try:
            from data_warehouse.models.generated_models import DimTradeCalendar, FactDailyPriceQfq

            ts_codes_for_prev = [convert_code_to_ts_code(c) for c in stock_codes or []]
            ts_codes_for_prev = [x for x in ts_codes_for_prev if x]

            session = warehouse_service.get_session()
            try:
                prev_trade_date = (
                    session.query(DimTradeCalendar.trade_date)
                    .filter(DimTradeCalendar.trade_date < target_date, DimTradeCalendar.is_open == True)
                    .order_by(DimTradeCalendar.trade_date.desc())
                    .limit(1)
                    .scalar()
                )

                if prev_trade_date and ts_codes_for_prev:
                    prev_rows = (
                        session.query(FactDailyPriceQfq.ts_code, FactDailyPriceQfq.close)
                        .filter(
                            FactDailyPriceQfq.trade_date == prev_trade_date,
                            FactDailyPriceQfq.ts_code.in_(ts_codes_for_prev),
                        )
                        .all()
                    )
                    for ts, close_v in prev_rows:
                        if close_v is not None:
                            close_f = float(close_v)
                            if close_f > 0:
                                prev_close_map[ts] = close_f
            finally:
                session.close()
        except Exception as e:
            logger.warning(f"⚠️ 预先准备上一交易日 close 失败（仍将使用数据源 pre_close）: {e}")

        # 尝试从同花顺API获取量比数据并补充
        try:
            from data_warehouse.sources.tonghuashun_client import TonghuashunClient
            ths_client = TonghuashunClient()
            if ths_client.available:
                logger.info("📥 尝试从同花顺API获取量比数据...")
                # 获取所有股票代码（ts_code格式）
                ts_codes = []
                for idx, row in df.iterrows():
                    code = str(row.get('code', '')).strip()
                    if code and len(code) == 6:
                        ts_code = convert_code_to_ts_code(code)
                        if ts_code:
                            ts_codes.append(ts_code)
                
                if ts_codes:
                    # 从同花顺获取量比数据（minimal=True：仅获取涨跌停状态和量比，减少不必要指标）
                    volume_ratio_df = ths_client.get_limit_up_status_and_volume_ratio(
                        ts_codes,
                        date_str_dash,
                        minimal=True,
                    )
                    
                    if not volume_ratio_df.empty and 'volume_ratio' in volume_ratio_df.columns:
                        # 将量比数据合并到主DataFrame
                        # 创建临时DataFrame用于合并
                        code_to_ts_code = {}
                        for idx, row in df.iterrows():
                            code = str(row.get('code', '')).strip()
                            if code and len(code) == 6:
                                ts_code = convert_code_to_ts_code(code)
                                if ts_code:
                                    code_to_ts_code[code] = ts_code
                        
                        # 添加ts_code列到df用于合并
                        df['ts_code'] = df['code'].map(code_to_ts_code)
                        
                        # 合并量比数据
                        df = df.merge(
                            volume_ratio_df[['ts_code', 'volume_ratio']],
                            on='ts_code',
                            how='left'
                        )
                        
                        # 统计获取到量比的数量
                        volume_ratio_count = df['volume_ratio'].notna().sum()
                        logger.info(f"✅ 从同花顺API获取到 {volume_ratio_count}/{len(df)} 条量比数据")
                    else:
                        logger.warning("⚠️ 同花顺API未返回量比数据")
                else:
                    logger.warning("⚠️ 没有有效的股票代码用于获取量比")
            else:
                logger.info("ℹ️ 同花顺客户端不可用，跳过量比数据获取")
        except Exception as e:
            logger.warning(f"⚠️ 从同花顺API获取量比数据失败: {e}")
        
        # 统计信息
        success_count = 0
        failed_count = 0
        skip_count = 0
        
        # 处理每条数据
        for idx, row in df.iterrows():
            try:
                code = str(row.get('code', '')).strip()
                if not code or len(code) != 6:
                    skip_count += 1
                    continue
                
                # 转换为Tushare格式
                ts_code = convert_code_to_ts_code(code)
                
                # 准备数据
                pre_close_from_source = float(row.get('pre_close', 0) or row.get('preClose', 0) or 0)
                daily_data = {
                    'open': float(row.get('open', 0) or 0),
                    'high': float(row.get('high', 0) or 0),
                    'low': float(row.get('low', 0) or 0),
                    'close': float(row.get('close', 0) or 0),
                    'pre_close': pre_close_from_source,
                    'vol': float(row.get('volume', 0) or 0),
                    'amount': float(row.get('amount', 0) or 0),
                    'turnover_rate': float(row.get('turnover_rate', 0) or 0),
                    'volume_ratio': float(row.get('volume_ratio', 0) or 0) if pd.notna(row.get('volume_ratio')) else None,  # 量比数据
                }
                
                # 如果上一交易日 close 可用，则以数据库为准修正 pre_close
                prev_close = prev_close_map.get(ts_code)
                if prev_close is not None and prev_close > 0:
                    daily_data['pre_close'] = prev_close

                # 检查数据有效性
                if daily_data['close'] <= 0:
                    skip_count += 1
                    continue
                
                # 保存到Raw层
                source_name = data_source_used.lower() if data_source_used else 'ifind'
                raw_saved = raw_layer.save_daily_price(
                    ts_code=ts_code,
                    trade_date=target_date,
                    data=daily_data,
                    source=source_name,
                    raw_payload=row.to_dict()
                )
                
                if not raw_saved:
                    skip_count += 1
                    continue
                
                # 合并到Fact层
                fact_data = clean_layer.merge_daily_prices(
                    ts_code=ts_code,
                    trade_date=target_date
                )
                
                if fact_data:
                    # 保存到 fact_daily_price_qfq（前复权表，fact_daily_price 已废弃）
                    try:
                        if clean_layer.save_fact_daily_price_qfq(fact_data):
                            success_count += 1
                        else:
                            skip_count += 1
                    except Exception as e:
                        logger.debug(f"保存数据失败: {ts_code}, {e}")
                        skip_count += 1
                else:
                    skip_count += 1
                
                # 进度提示
                if (success_count + failed_count + skip_count) % 100 == 0:
                    logger.info(f"  📝 已处理 {success_count + failed_count + skip_count} 只股票...")
                    
            except Exception as e:
                logger.error(f"  ❌ 处理股票 {code} 失败: {e}")
                failed_count += 1
                continue
        
        logger.info("=" * 60)
        logger.info(f"数据更新完成: {target_date}")
        logger.info(f"  总计: {len(df)} 条")
        logger.info(f"  成功: {success_count} 条")
        logger.info(f"  跳过: {skip_count} 条")
        logger.info(f"  失败: {failed_count} 条")
        logger.info("=" * 60)
        
        # 更新处理记录数（确保在任务完成前更新）
        if log_entry:
            log_entry.update_records_processed(success_count)
        
        # 任务成功判断：接口状态通 + 更新数据完整才算成功
        # 1. 接口状态通：数据源可用（已在前面检查）
        # 2. 更新数据完整：成功数量 > 0 且成功率 >= 80%（允许部分失败）
        total_processed = success_count + failed_count + skip_count
        success_rate = (success_count / total_processed * 100) if total_processed > 0 else 0
        
        # 任务成功判断：根据操作系统确定是否必须使用iFinD
        # Linux生产环境：必须使用iFinD
        # macOS开发环境：允许使用Tushare作为降级
        is_macos = platform.system() == 'Darwin'
        required_source = None if is_macos else "iFinDPy"  # macOS不强制数据源类型

        is_success = (
            success_count > 0 and  # 至少成功处理一条
            success_rate >= 80.0 and  # 成功率 >= 80%
            (required_source is None or data_source_used == required_source)  # 数据源要求
        )

        if not is_success:
            logger.warning(f"⚠️ 任务未完全成功: 数据源={data_source_used}, 成功数={success_count}, 成功率={success_rate:.2f}%")
        
        # 刷新物化视图 mv_base_universe_daily
        if is_success:
            try:
                ws = WarehouseService()
                session = ws.get_session()
                logger.info(f"📦 刷新物化视图 mv_base_universe_daily...")
                session.execute(text("REFRESH MATERIALIZED VIEW CONCURRENTLY mv_base_universe_daily"))
                session.commit()
                session.close()
                logger.info(f"✅ 物化视图刷新完成")
            except Exception as e:
                logger.warning(f"⚠️ 物化视图刷新失败: {e}")
        
        return is_success


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='使用新日线数据源更新数据仓库')
    parser.add_argument('--date', type=str, help='目标日期（YYYY-MM-DD），默认今天')
    parser.add_argument('--codes', type=str, nargs='+', help='股票代码列表（6位数字格式），可选')
    
    args = parser.parse_args()
    
    # 解析日期
    target_date = None
    if args.date:
        target_date = date.fromisoformat(args.date)
    
    # 执行更新
    success = update_daily_prices_from_snapshot(target_date, args.codes)
    
    if success:
        logger.info("✅ 更新成功")
        sys.exit(0)
    else:
        logger.error("❌ 更新失败")
        sys.exit(1)


if __name__ == '__main__':
    main()

