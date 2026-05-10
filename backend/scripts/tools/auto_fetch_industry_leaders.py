"""
自动获取行业龙头股票数据
从Tushare/AKShare等数据源自动识别行业龙头，基于市值、营收、市场份额等指标
"""

import sys
import logging
import time
from pathlib import Path
from datetime import datetime, timedelta, date
from typing import List, Dict, Optional
import pandas as pd
import numpy as np

# 添加项目根目录到路径
# 从 backend/scripts/tools/ 到项目根目录需要4层parent
script_path = Path(__file__).resolve()
project_root = script_path.parent.parent.parent.parent
if not (project_root / 'data_warehouse').exists():
    # 如果4层parent不对，尝试3层（从项目根目录运行的情况）
    project_root = script_path.parent.parent.parent
    if not (project_root / 'data_warehouse').exists():
        raise RuntimeError(f"无法找到项目根目录。脚本路径: {script_path}, 尝试的根目录: {project_root}")
sys.path.insert(0, str(project_root))

from data_warehouse.service.warehouse_service import WarehouseService
from data_warehouse.models.orm_classes import DimStock
from data_warehouse.models.generated_models import FactDailyPriceQfq
from backend.services.tushare_service import TushareService
from backend.services.akshare_service import AKShareService
from backend.services.hotspots.sector_heat_calculator import calculate_industry_heat_scores
from sqlalchemy import text, func, create_engine
from data_warehouse.config import DATABASE_URL

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 确保日志输出到控制台
import sys
if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


# 用于缓存daily_basic数据的全局变量（跨函数调用）
# 注意：这些变量在每次调用get_industry_leaders_by_market_cap时会被重置
# 但在处理同一个行业的不同批次时会共享
_daily_basic_cache = None
_cache_trade_date = None


def update_fundamental_valuation(daily_basic_df, trade_date):
    """
    将daily_basic中的估值数据（pe_ttm, pb, dv_ratio）更新到fact_daily_fundamental

    Args:
        daily_basic_df: daily_basic接口返回的DataFrame，需包含ts_code, pe_ttm, pb, dv_ratio
        trade_date: 交易日期（字符串YYYYMMDD）
    """
    if daily_basic_df is None or daily_basic_df.empty:
        return

    # 检查必要的列是否存在
    required_cols = ['ts_code']
    if not all(col in daily_basic_df.columns for col in required_cols):
        logger.warning("daily_basic数据缺少ts_code列，跳过更新")
        return

    try:
        wh_service = WarehouseService()
        session = wh_service.get_session()

        updated_count = 0
        skipped_count = 0

        for _, row in daily_basic_df.iterrows():
            ts_code = row.get('ts_code')
            if not ts_code:
                continue

            # 准备更新字段
            update_fields = []
            params = {'ts_code': ts_code, 'trade_date': trade_date}

            # PE_TTM
            if 'pe_ttm' in daily_basic_df.columns and pd.notna(row.get('pe_ttm')):
                pe_val = float(row['pe_ttm'])
                if pe_val > 0:  # 只更新有效值
                    update_fields.append("pe_ttm = :pe_ttm")
                    params['pe_ttm'] = pe_val

            # PB -> pb_lyr
            if 'pb' in daily_basic_df.columns and pd.notna(row.get('pb')):
                pb_val = float(row['pb'])
                if pb_val > 0:
                    update_fields.append("pb_lyr = :pb_lyr")
                    params['pb_lyr'] = pb_val

            # dv_ratio -> dividend_yield_ttm (Tushare返回百分比，如3.5表示3.5%)
            if 'dv_ratio' in daily_basic_df.columns and pd.notna(row.get('dv_ratio')):
                dv_val = float(row['dv_ratio'])
                if dv_val >= 0:
                    update_fields.append("dividend_yield_ttm = :dividend_yield_ttm")
                    params['dividend_yield_ttm'] = dv_val

            if not update_fields:
                skipped_count += 1
                continue

            try:
                sql = text(f"""
                    UPDATE fact_daily_fundamental
                    SET {', '.join(update_fields)}, updated_at = CURRENT_TIMESTAMP
                    WHERE ts_code = :ts_code
                """)
                result = session.execute(sql, params)
                if result.rowcount > 0:
                    updated_count += 1
                else:
                    # 如果该行不存在，插入新行（fact_daily_fundamental 主键只有 ts_code）
                    col_names = [f.split('=')[0].strip() for f in update_fields]
                    insert_sql = text(f"""
                        INSERT INTO fact_daily_fundamental
                        (ts_code, trade_date, {', '.join(col_names)}, source, updated_at)
                        VALUES (:ts_code, :trade_date, {', '.join([':' + c for c in col_names])}, 'tushare_daily_basic', CURRENT_TIMESTAMP)
                    """)
                    session.execute(insert_sql, params)
                    updated_count += 1
            except Exception as e:
                logger.debug(f"更新 {ts_code} 估值数据失败: {e}")
                skipped_count += 1
                continue

        session.commit()
        if updated_count > 0:
            logger.info(f"✅ 已更新 {updated_count} 只股票估值数据到 fact_daily_fundamental（跳过 {skipped_count} 只）")
    except Exception as e:
        logger.error(f"❌ 批量更新估值数据失败: {e}")
    finally:
        if 'session' in locals():
            session.close()

def get_industry_leaders_by_market_cap(industry_name: str, top_n: int = 3) -> List[Dict]:
    """
    根据市值获取行业龙头（市值最大的N只股票）
    
    注意：单纯按市值判断龙头有一定局限性：
    - 优点：数据易得、反映市场认可度
    - 缺点：可能包含被高估的公司、忽略盈利能力/市场份额/技术壁垒
    
    建议：使用综合评分法（get_industry_leaders_by_comprehensive_score）更可靠
    
    Args:
        industry_name: 行业名称
        top_n: 取前N只
        
    Returns:
        List[Dict]: 龙头股票列表
    """
    try:
        tushare_service = TushareService()
        if not tushare_service.available:
            logger.warning("Tushare服务不可用")
            return []
        
        # 0. 先获取最新交易日
        latest_trade_date = None
        try:
            # 获取交易日历，找到最新交易日
            logger.debug(f"  正在获取最新交易日...")
            trade_cal = tushare_service.pro.trade_cal(
                exchange='SSE',
                start_date='20240101',
                end_date='',
                is_open=1
            )
            if trade_cal is not None and not trade_cal.empty:
                latest_trade_date = trade_cal.iloc[-1]['cal_date']
                logger.info(f"  ✅ 最新交易日: {latest_trade_date}")
            else:
                logger.warning(f"  ⚠️ trade_cal返回空数据")
        except Exception as e:
            logger.warning(f"  获取最新交易日失败: {e}，使用最近日期")
            # 如果获取失败，使用最近一个工作日
            today = datetime.now()
            for days_back in range(1, 8):  # 尝试最近7天
                try_date = (today - timedelta(days=days_back))
                # 跳过周末
                if try_date.weekday() < 5:  # 0-4是周一到周五
                    latest_trade_date = try_date.strftime('%Y%m%d')
                    logger.info(f"  ✅ 使用最近工作日: {latest_trade_date}")
                    break
        
        if not latest_trade_date:
            logger.error("  ❌ 无法获取最新交易日，无法继续")
            return []
        
        # 1. 获取行业所有股票
        stock_basic = tushare_service.pro.stock_basic(
            exchange='',
            list_status='L',
            fields='ts_code,symbol,name,industry,list_date'
        )
        
        if stock_basic is None or stock_basic.empty:
            logger.warning(f"未获取到股票列表")
            return []
        
        # 筛选行业股票
        industry_stocks = stock_basic[stock_basic['industry'] == industry_name]
        
        if industry_stocks.empty:
            logger.debug(f"  ⚠️ 未找到行业股票: {industry_name}")
            return []
        
        logger.info(f"  📊 找到 {len(industry_stocks)} 只{industry_name}行业股票")
        
        # 2. 获取市值数据（使用daily_basic接口）
        ts_codes = industry_stocks['ts_code'].tolist()
        leaders = []
        all_market_caps = []  # 用于收集所有市值数据
        
        # 分批获取（Tushare有单次查询限制）
        batch_size = 100
        total_batches = (len(ts_codes) + batch_size - 1) // batch_size
        logger.info(f"  📦 分 {total_batches} 批获取市值数据，每批最多 {batch_size} 只股票...")
        
        for i in range(0, len(ts_codes), batch_size):
            batch_codes = ts_codes[i:i+batch_size]
            batch_num = i // batch_size + 1
            logger.info(f"  🔄 开始处理批次 {batch_num}/{total_batches} ({len(batch_codes)} 只股票)")
            
            try:
                # 使用最新交易日获取市值数据
                # daily_basic接口的两种调用方式：
                # 1. 只传trade_date：获取该日期所有股票的数据（推荐，更高效）
                # 2. 传ts_code和trade_date：获取指定股票的数据（但可能不支持多个代码）
                
                logger.debug(f"    批次 {batch_num}/{total_batches}: 调用daily_basic (trade_date={latest_trade_date})")
                
                # 方法1：只传trade_date，获取该日期所有股票的数据，然后筛选
                # 这样更高效，因为只需要调用一次API
                global _daily_basic_cache, _cache_trade_date
                
                # 检查缓存是否有效（同一交易日）
                logger.info(f"    🔍 [批次 {batch_num}] 检查缓存: cache={'存在' if _daily_basic_cache is not None else '不存在'}, trade_date={_cache_trade_date}")
                
                if _daily_basic_cache is None or _cache_trade_date != latest_trade_date:
                    # 第一个批次或交易日变化：获取该日期所有股票的数据
                    logger.info(f"    📥 [批次 {batch_num}] 开始获取交易日 {latest_trade_date} 的所有股票市值数据...")
                    try:
                        daily_basic_all = tushare_service.pro.daily_basic(
                            trade_date=latest_trade_date,  # 只传trade_date，获取所有股票
                            fields='ts_code,trade_date,total_mv,circ_mv,pe_ttm,pb,dv_ratio'
                        )
                        
                        if daily_basic_all is not None and not daily_basic_all.empty:
                            logger.info(f"    ✅ [批次 {batch_num}] 获取到 {len(daily_basic_all)} 条市值数据（所有股票）")
                            _daily_basic_cache = daily_basic_all
                            _cache_trade_date = latest_trade_date
                        else:
                            logger.warning(f"    ⚠️ [批次 {batch_num}] daily_basic返回空数据（可能是非交易日或数据未更新）")
                            logger.warning(f"    提示：请检查交易日 {latest_trade_date} 是否为交易日，或Tushare数据是否已更新")
                            _daily_basic_cache = pd.DataFrame()  # 设置为空DataFrame而不是None
                            _cache_trade_date = latest_trade_date
                    except Exception as e:
                        error_msg = str(e)
                        logger.error(f"    ❌ [批次 {batch_num}] 获取所有股票市值数据失败: {error_msg}")
                        logger.error(f"    错误类型: {type(e).__name__}")
                        # 显示完整的错误信息，帮助诊断问题
                        import traceback
                        logger.error(f"    完整错误堆栈:\n{traceback.format_exc()}")
                        _daily_basic_cache = pd.DataFrame()
                        _cache_trade_date = latest_trade_date
                else:
                    logger.debug(f"    [批次 {batch_num}] 使用缓存数据（交易日: {_cache_trade_date}）")
                
                # 从缓存中筛选当前批次的股票
                if _daily_basic_cache is not None and not _daily_basic_cache.empty:
                    daily_basic = _daily_basic_cache[_daily_basic_cache['ts_code'].isin(batch_codes)]
                    logger.debug(f"    批次 {batch_num}/{total_batches}: 从缓存筛选出 {len(daily_basic)} 条数据")
                else:
                    # 如果缓存不存在或为空，返回空DataFrame
                    logger.debug(f"    批次 {batch_num}/{total_batches}: 缓存为空，跳过")
                    daily_basic = pd.DataFrame()
                
                if daily_basic is not None and not daily_basic.empty:
                    logger.info(f"    批次 {batch_num}/{total_batches}: ✅ 获取到 {len(daily_basic)} 条市值数据")
                    # 收集所有市值数据
                    valid_count = 0
                    for _, row in daily_basic.iterrows():
                        if pd.notna(row['total_mv']) and row['total_mv'] > 0:
                            all_market_caps.append({
                                'ts_code': row['ts_code'],
                                'total_mv': row['total_mv']
                            })
                            valid_count += 1
                    logger.debug(f"    批次 {batch_num}/{total_batches}: 有效市值数据 {valid_count} 条")
                else:
                    logger.warning(f"    批次 {batch_num}/{total_batches}: ⚠️ 未获取到市值数据（返回空）")
                
                # 避免请求过快
                time.sleep(0.3)
                
            except Exception as e:
                error_msg = str(e)
                logger.error(f"    批次 {batch_num}/{total_batches} ❌ 获取市值数据失败: {error_msg}")
                logger.debug(f"    错误详情: {type(e).__name__}: {error_msg}")
                # 如果是API限制错误，等待更长时间
                if 'limit' in error_msg.lower() or '429' in error_msg or '请求过于频繁' in error_msg:
                    logger.warning(f"    ⚠️ 可能触发API限制，等待5秒...")
                    time.sleep(5)
                continue
        
        # 更新估值数据到 fact_daily_fundamental
        if _daily_basic_cache is not None and not _daily_basic_cache.empty:
            update_fundamental_valuation(_daily_basic_cache, latest_trade_date)

        # 3. 对所有市值数据进行排序，取前top_n
        if not all_market_caps:
            logger.warning(f"  ⚠️ 未获取到任何市值数据")
            return []
        
        logger.debug(f"  📊 共收集到 {len(all_market_caps)} 条市值数据")
        
        # 按市值排序
        all_market_caps.sort(key=lambda x: x['total_mv'], reverse=True)
        
        # 取前top_n只
        top_stocks = all_market_caps[:top_n]
        
        for rank, stock_data in enumerate(top_stocks, 1):
            ts_code = stock_data['ts_code']
            total_mv = stock_data['total_mv'] / 10000  # 转换为亿元
            
            # 获取股票名称
            stock_info = industry_stocks[industry_stocks['ts_code'] == ts_code]
            if not stock_info.empty:
                name = stock_info.iloc[0]['name']
                
                leaders.append({
                    'ts_code': ts_code,
                    'name': name,
                    'leader_type': '行业龙头' if rank == 1 else '板块龙头',
                    'reason': f'市值排名第{rank}位，总市值{total_mv:.0f}亿元',
                    'market_cap': total_mv,
                    'main_business': ''  # 需要从其他接口获取
                })
        
        logger.info(f"✅ 获取到 {len(leaders)} 只{industry_name}行业龙头股票")
        return leaders
        
    except Exception as e:
        logger.error(f"获取行业龙头失败: {e}", exc_info=True)
        return []


def get_industry_leaders_by_revenue(industry_name: str, top_n: int = 3) -> List[Dict]:
    """
    根据营收获取行业龙头（营收最大的N只股票）
    
    Args:
        industry_name: 行业名称
        top_n: 取前N只
        
    Returns:
        List[Dict]: 龙头股票列表
    """
    try:
        tushare_service = TushareService()
        if not tushare_service.available:
            logger.warning("Tushare服务不可用")
            return []
        
        # 1. 获取行业所有股票
        stock_basic = tushare_service.pro.stock_basic(
            exchange='',
            list_status='L',
            fields='ts_code,symbol,name,industry'
        )
        
        industry_stocks = stock_basic[stock_basic['industry'] == industry_name]
        
        if industry_stocks.empty:
            return []
        
        # 2. 获取最新财报的营收数据
        ts_codes = industry_stocks['ts_code'].tolist()
        leaders = []
        
        # 获取最新报告期
        current_year = datetime.now().year
        current_month = datetime.now().month
        
        # 确定报告期（Q1: 0331, Q2: 0630, Q3: 0930, Q4: 1231）
        if current_month <= 3:
            report_date = f"{current_year-1}1231"  # 上一年年报
        elif current_month <= 6:
            report_date = f"{current_year}0331"  # 一季报
        elif current_month <= 9:
            report_date = f"{current_year}0630"  # 半年报
        else:
            report_date = f"{current_year}0930"  # 三季报
        
        batch_size = 50
        for i in range(0, len(ts_codes), batch_size):
            batch_codes = ts_codes[i:i+batch_size]
            codes_str = ','.join(batch_codes)
            
            try:
                # 获取财务指标数据
                fina_indicator = tushare_service.pro.fina_indicator(
                    ts_code=codes_str,
                    period=report_date,
                    fields='ts_code,revenue,total_mv'
                )
                
                if fina_indicator is not None and not fina_indicator.empty:
                    # 按营收排序
                    fina_indicator = fina_indicator.sort_values('revenue', ascending=False)
                    
                    for idx, row in fina_indicator.head(top_n).iterrows():
                        ts_code = row['ts_code']
                        revenue = row['revenue'] / 100000000  # 转换为亿元
                        
                        stock_info = industry_stocks[industry_stocks['ts_code'] == ts_code]
                        if not stock_info.empty:
                            name = stock_info.iloc[0]['name']
                            
                            leaders.append({
                                'ts_code': ts_code,
                                'name': name,
                                'leader_type': '行业龙头' if idx == 0 else '板块龙头',
                                'reason': f'营收排名第{idx+1}位，营收{revenue:.0f}亿元',
                                'market_cap': row.get('total_mv', 0) / 10000 if pd.notna(row.get('total_mv')) else 0,
                                'main_business': ''
                            })
                
                time.sleep(0.3)
                
            except Exception as e:
                logger.warning(f"获取营收数据失败: {e}")
                continue
        
        logger.info(f"✅ 获取到 {len(leaders)} 只{industry_name}行业龙头股票（按营收）")
        return leaders
        
    except Exception as e:
        logger.error(f"获取行业龙头失败: {e}", exc_info=True)
        return []


def batch_get_financial_from_db(ts_codes: List[str], report_date: str) -> Dict[str, Dict]:
    """
    批量从数据库读取财务数据（优化版本）
    一次性查询多只股票的财务数据，大幅提升效率
    
    Args:
        ts_codes: 股票代码列表
        report_date: 报告期（如 '20231231'）
        
    Returns:
        Dict[str, Dict]: {ts_code: financial_dict} 字典
    """
    if not ts_codes:
        return {}
    
    result_dict = {}
    
    try:
        engine = create_engine(DATABASE_URL, echo=False)
        with engine.connect() as conn:
            end_date_obj = datetime.strptime(report_date, '%Y%m%d').date()
            
            # 批量查询：先查询指定报告期的数据
            # 使用IN子句替代ANY，更兼容
            placeholders = ','.join([f':code_{i}' for i in range(len(ts_codes))])
            query_fundamental = text(f"""
                SELECT DISTINCT ON (ts_code) 
                    ts_code, roe, gross_margin, net_margin, debt_ratio, op_cf, total_asset, total_debt, 
                    revenue, revenue_growth, net_profit, ocf_to_revenue, end_date
                FROM fact_fundamental
                WHERE ts_code IN ({placeholders})
                AND end_date = :end_date
                ORDER BY ts_code, end_date DESC
            """)
            
            params = {f'code_{i}': code for i, code in enumerate(ts_codes)}
            params['end_date'] = end_date_obj
            
            results = conn.execute(query_fundamental, params).fetchall()
            
            # 记录已找到的股票代码
            found_codes = {row[0] for row in results}
            
            # 对于没有找到的股票，查询最新报告期
            missing_codes = [code for code in ts_codes if code not in found_codes]
            if missing_codes:
                placeholders_latest = ','.join([f':code_{i}' for i in range(len(missing_codes))])
                query_latest = text(f"""
                    SELECT DISTINCT ON (ts_code) 
                        ts_code, roe, gross_margin, net_margin, debt_ratio, op_cf, total_asset, total_debt,
                        revenue, revenue_growth, net_profit, ocf_to_revenue, end_date
                    FROM fact_fundamental
                    WHERE ts_code IN ({placeholders_latest})
                    AND end_date <= :end_date
                    ORDER BY ts_code, end_date DESC
                """)
                
                params_latest = {f'code_{i}': code for i, code in enumerate(missing_codes)}
                params_latest['end_date'] = end_date_obj
                
                latest_results = conn.execute(query_latest, params_latest).fetchall()
                
                results = list(results) + list(latest_results)
            
            if not results:
                return {}
            
            # 构建返回字典（直接从fact_fundamental读取所有字段，不再查询raw_fundamental）
            for row in results:
                ts_code, roe, gross_margin, net_margin, debt_ratio, op_cf, total_asset, total_debt, \
                revenue, revenue_growth, net_profit, ocf_to_revenue, actual_end_date = row
                
                # 转换数据格式
                revenue_val = float(revenue) if revenue else 0.0
                revenue = revenue_val / 100000000  # 转换为亿元
                revenue_growth_val = float(revenue_growth) if revenue_growth else 0.0
                net_profit_val = float(net_profit) if net_profit else 0.0
                net_profit = net_profit_val / 100000000  # 转换为亿元
                profit_growth = 0.0  # 需要多期数据才能计算，暂时为0
                cashflow_to_revenue_val = float(ocf_to_revenue) if ocf_to_revenue else 0.0
                cashflow_to_revenue = cashflow_to_revenue_val / 100 if cashflow_to_revenue_val > 1 else cashflow_to_revenue_val
                
                # 如果ocf_to_revenue为空，尝试从op_cf和revenue计算
                if not ocf_to_revenue and op_cf and revenue > 0:
                    cashflow_to_revenue = float(op_cf) / (revenue * 100000000)
                
                # 转换百分比
                roe_val = float(roe) if roe else 0.0
                roe = roe_val / 100 if roe_val > 1 else roe_val
                net_margin_val = float(net_margin) if net_margin else 0.0
                net_margin = net_margin_val / 100 if net_margin_val > 1 else net_margin_val
                gross_margin_val = float(gross_margin) if gross_margin else 0.0
                gross_margin = gross_margin_val / 100 if gross_margin_val > 1 else gross_margin_val
                debt_ratio_val = float(debt_ratio) if debt_ratio else 0.0
                debt_ratio = debt_ratio_val / 100 if debt_ratio_val > 1 else debt_ratio_val
                
                result_dict[ts_code] = {
                    'roe': roe,
                    'net_margin': net_margin,
                    'gross_margin': gross_margin,
                    'debt_ratio': debt_ratio,
                    'cashflow_to_revenue': cashflow_to_revenue,
                    'revenue_growth': revenue_growth_val,
                    'profit_growth': profit_growth,
                    'revenue': revenue,
                    'net_profit': net_profit
                }
                
    except Exception as e:
        logger.debug(f"批量从数据库读取财务数据失败: {e}")
    
    return result_dict


def get_financial_from_db(ts_code: str, report_date: str) -> Optional[Dict]:
    """
    从数据库读取财务数据（优先使用）
    如果指定报告期没有数据，自动回退到最新的可用报告期
    
    Args:
        ts_code: 股票代码
        report_date: 报告期（如 '20231231'）
        
    Returns:
        Dict: 财务数据字典，如果数据库没有则返回None
    """
    try:
        engine = create_engine(DATABASE_URL, echo=False)
        with engine.connect() as conn:
            end_date_obj = datetime.strptime(report_date, '%Y%m%d').date()
            
            # 先尝试查询指定报告期的数据（直接从fact_fundamental读取所有字段）
            query_fundamental = text("""
                SELECT roe, gross_margin, net_margin, debt_ratio, op_cf, total_asset, total_debt,
                       revenue, revenue_growth, net_profit, ocf_to_revenue, end_date
                FROM fact_fundamental
                WHERE ts_code = :ts_code
                AND end_date = :end_date
                ORDER BY end_date DESC
                LIMIT 1
            """)
            
            result = conn.execute(query_fundamental, {
                'ts_code': ts_code,
                'end_date': end_date_obj
            }).fetchone()
            
            # 如果指定报告期没有数据，查找最新的可用报告期
            if not result:
                query_latest = text("""
                    SELECT roe, gross_margin, net_margin, debt_ratio, op_cf, total_asset, total_debt,
                           revenue, revenue_growth, net_profit, ocf_to_revenue, end_date
                    FROM fact_fundamental
                    WHERE ts_code = :ts_code
                    AND end_date <= :end_date
                    ORDER BY end_date DESC
                    LIMIT 1
                """)
                result = conn.execute(query_latest, {
                    'ts_code': ts_code,
                    'end_date': end_date_obj
                }).fetchone()
            
            if result:
                roe, gross_margin, net_margin, debt_ratio, op_cf, total_asset, total_debt, \
                revenue, revenue_growth, net_profit, ocf_to_revenue, actual_end_date = result
                
                # 记录实际使用的报告期（如果与请求的不同）
                if actual_end_date != end_date_obj:
                    logger.debug(f"  📌 {ts_code} 使用报告期 {actual_end_date}（而非 {report_date}）")
                
                # 转换数据格式
                revenue_val = float(revenue) if revenue else 0.0
                revenue = revenue_val / 100000000  # 转换为亿元
                revenue_growth_val = float(revenue_growth) if revenue_growth else 0.0
                net_profit_val = float(net_profit) if net_profit else 0.0
                net_profit = net_profit_val / 100000000  # 转换为亿元
                profit_growth = 0.0  # 需要多期数据才能计算，暂时为0
                cashflow_to_revenue_val = float(ocf_to_revenue) if ocf_to_revenue else 0.0
                cashflow_to_revenue = cashflow_to_revenue_val / 100 if cashflow_to_revenue_val > 1 else cashflow_to_revenue_val
                
                # 如果ocf_to_revenue为空，尝试从op_cf和revenue计算
                if not ocf_to_revenue and op_cf and revenue > 0:
                    cashflow_to_revenue = float(op_cf) / (revenue * 100000000)
                
                # 转换百分比
                roe_val = float(roe) if roe else 0.0
                roe = roe_val / 100 if roe_val > 1 else roe_val
                net_margin_val = float(net_margin) if net_margin else 0.0
                net_margin = net_margin_val / 100 if net_margin_val > 1 else net_margin_val
                gross_margin_val = float(gross_margin) if gross_margin else 0.0
                gross_margin = gross_margin_val / 100 if gross_margin_val > 1 else gross_margin_val
                debt_ratio_val = float(debt_ratio) if debt_ratio else 0.0
                debt_ratio = debt_ratio_val / 100 if debt_ratio_val > 1 else debt_ratio_val
                
                return {
                    'roe': roe,
                    'net_margin': net_margin,
                    'gross_margin': gross_margin,
                    'debt_ratio': debt_ratio,
                    'cashflow_to_revenue': cashflow_to_revenue,
                    'revenue_growth': revenue_growth_val,
                    'profit_growth': profit_growth,  # 需要多期数据才能计算，暂时为0
                    'revenue': revenue,
                    'net_profit': net_profit
                }
    except Exception as e:
        logger.debug(f"从数据库读取财务数据失败 {ts_code}: {e}")
    
    return None


def get_enhanced_financial_indicators(
    tushare_service: TushareService,
    ts_code: str,
    report_date: str
) -> Dict:
    """
    获取增强的财务指标（优化：优先从数据库读取）
    
    Args:
        tushare_service: Tushare服务实例
        ts_code: 股票代码
        report_date: 报告期（如 '20231231'）
        
    Returns:
        Dict: 包含以下字段的字典
            - roe: ROE（净资产收益率）
            - net_margin: 净利率
            - gross_margin: 毛利率
            - debt_ratio: 负债率
            - cashflow_to_revenue: 经营现金流/营收
            - revenue_growth: 营收增长率
            - profit_growth: 净利润增长率
            - revenue: 营收（亿元）
            - net_profit: 净利润（亿元）
    """
    # 1. 优先从数据库读取
    db_data = get_financial_from_db(ts_code, report_date)
    if db_data:
        logger.debug(f"✅ 从数据库读取财务数据: {ts_code}")
        # 如果数据库有基本数据，但缺少利润表数据，尝试从API补充
        if db_data.get('net_profit', 0) == 0 or db_data.get('profit_growth', 0) == 0:
            try:
                profit_df = tushare_service.pro.income(
                    ts_code=ts_code,
                    period='',
                    fields='ts_code,end_date,n_income'
                )
                if profit_df is not None and not profit_df.empty:
                    if db_data.get('net_profit', 0) == 0:
                        db_data['net_profit'] = float(profit_df.iloc[0]['n_income'] or 0) / 100000000
                    if db_data.get('profit_growth', 0) == 0 and len(profit_df) >= 2:
                        profit_df = profit_df.sort_values('end_date', ascending=False)
                        current_profit = float(profit_df.iloc[0]['n_income'] or 0)
                        prev_profit = float(profit_df.iloc[1]['n_income'] or 0)
                        if prev_profit > 0:
                            db_data['profit_growth'] = ((current_profit - prev_profit) / prev_profit) * 100
            except Exception as e:
                logger.debug(f"从API补充利润表数据失败 {ts_code}: {e}")
        return db_data
    
    # 2. 数据库没有，从API获取
    try:
        # 获取财务指标
        fina_indicator = tushare_service.pro.fina_indicator(
            ts_code=ts_code,
            period=report_date,
            fields='ts_code,end_date,roe,netprofit_margin,grossprofit_margin,debt_to_assets,ocf_to_revenue,revenue,yoy_sales'
        )
        
        if fina_indicator is None or fina_indicator.empty:
            return {}
        
        latest = fina_indicator.iloc[0]
        
        # 获取利润表数据（用于计算净利润增长率）
        profit_df = None
        try:
            profit_df = tushare_service.pro.income(
                ts_code=ts_code,
                period='',
                fields='ts_code,end_date,n_income'
            )
        except Exception as e:
            logger.debug(f"获取利润表数据失败 {ts_code}: {e}")
        
        # 计算净利润增长率（需要对比两期数据）
        profit_growth = 0.0
        if profit_df is not None and not profit_df.empty and len(profit_df) >= 2:
            profit_df = profit_df.sort_values('end_date', ascending=False)
            current_profit = float(profit_df.iloc[0]['n_income'] or 0)
            prev_profit = float(profit_df.iloc[1]['n_income'] or 0)
            if prev_profit > 0:
                profit_growth = ((current_profit - prev_profit) / prev_profit) * 100
        
        # 处理百分比数据（Tushare可能返回百分比或小数）
        roe_val = float(latest.get('roe', 0) or 0)
        net_margin_val = float(latest.get('netprofit_margin', 0) or 0)
        gross_margin_val = float(latest.get('grossprofit_margin', 0) or 0)
        debt_ratio_val = float(latest.get('debt_to_assets', 0) or 0)
        cashflow_to_revenue_val = float(latest.get('ocf_to_revenue', 0) or 0)
        revenue_growth_val = float(latest.get('yoy_sales', 0) or 0)
        revenue_val = float(latest.get('revenue', 0) or 0) / 100000000  # 转换为亿元
        
        # 如果值>1，认为是百分比，需要除以100
        roe = roe_val / 100 if roe_val > 1 else roe_val
        net_margin = net_margin_val / 100 if net_margin_val > 1 else net_margin_val
        gross_margin = gross_margin_val / 100 if gross_margin_val > 1 else gross_margin_val
        debt_ratio = debt_ratio_val / 100 if debt_ratio_val > 1 else debt_ratio_val
        cashflow_to_revenue = cashflow_to_revenue_val / 100 if cashflow_to_revenue_val > 1 else cashflow_to_revenue_val
        
        # 计算净利润（从利润表）
        net_profit = 0.0
        if profit_df is not None and not profit_df.empty:
            net_profit = float(profit_df.iloc[0]['n_income'] or 0) / 100000000  # 转换为亿元
        
        result = {
            'roe': roe,
            'net_margin': net_margin,
            'gross_margin': gross_margin,
            'debt_ratio': debt_ratio,
            'cashflow_to_revenue': cashflow_to_revenue,
            'revenue_growth': revenue_growth_val,
            'profit_growth': profit_growth,
            'revenue': revenue_val,
            'net_profit': net_profit
        }
        
        # TODO: 保存到数据库（可以异步执行，避免阻塞）
        # save_financial_to_db(ts_code, report_date, result)
        
        return result
    except Exception as e:
        logger.warning(f"获取增强财务指标失败 {ts_code}: {e}")
        return {}


def batch_get_stability_indicators(
    tushare_service: TushareService,
    ts_codes: List[str]
) -> Dict[str, Dict]:
    """
    批量获取稳定性指标（优化版本，减少API调用）
    
    Args:
        tushare_service: Tushare服务实例
        ts_codes: 股票代码列表
        
    Returns:
        Dict[str, Dict]: {ts_code: {roe_stability, profit_continuity}}
    """
    result = {}
    batch_size = 50
    
    for i in range(0, len(ts_codes), batch_size):
        batch_codes = ts_codes[i:i+batch_size]
        codes_str = ','.join(batch_codes)
        
        try:
            # 批量获取财务指标（用于ROE稳定性）
            fina_indicator_batch = tushare_service.pro.fina_indicator(
                ts_code=codes_str,
                period='',
                fields='ts_code,end_date,roe'
            )
            
            # 批量获取利润表数据（用于盈利连续性）
            income_batch = None
            try:
                income_batch = tushare_service.pro.income(
                    ts_code=codes_str,
                    period='',
                    fields='ts_code,end_date,n_income'
                )
            except Exception as e:
                logger.debug(f"批量获取利润表数据失败: {e}")
            
            # 处理每只股票
            for ts_code in batch_codes:
                try:
                    # 计算ROE稳定性
                    roe_stability = 999.0
                    if fina_indicator_batch is not None and not fina_indicator_batch.empty:
                        stock_fina = fina_indicator_batch[fina_indicator_batch['ts_code'] == ts_code].sort_values('end_date', ascending=False)
                        annual_data = stock_fina[stock_fina['end_date'].astype(str).str.endswith('1231')]
                        
                        if annual_data.empty:
                            quarterly_data = stock_fina.head(12)
                            roe_values = []
                            for _, row in quarterly_data.iterrows():
                                roe_val = float(row.get('roe', 0) or 0)
                                roe_val = roe_val / 100 if roe_val > 1 else roe_val
                                if roe_val > 0:
                                    roe_values.append(roe_val)
                        else:
                            annual_data = annual_data.head(3)
                            roe_values = []
                            for _, row in annual_data.iterrows():
                                roe_val = float(row.get('roe', 0) or 0)
                                roe_val = roe_val / 100 if roe_val > 1 else roe_val
                                roe_values.append(roe_val)
                        
                        if len(roe_values) >= 2:
                            roe_stability = float(np.std(roe_values))
                    
                    # 计算盈利连续性
                    profit_continuity = 0
                    if income_batch is not None and not income_batch.empty:
                        stock_income = income_batch[income_batch['ts_code'] == ts_code].sort_values('end_date', ascending=False)
                        annual_profit = stock_income[stock_income['end_date'].astype(str).str.endswith('1231')]
                        
                        if annual_profit.empty:
                            quarterly_profit = stock_income.head(12)
                            profit_years = set()
                            for _, row in quarterly_profit.iterrows():
                                end_date = str(row['end_date'])
                                year = end_date[:4]
                                profit = float(row['n_income'] or 0)
                                if profit > 0:
                                    profit_years.add(year)
                            profit_continuity = len(profit_years)
                        else:
                            annual_profit = annual_profit.head(3)
                            for _, row in annual_profit.iterrows():
                                profit = float(row['n_income'] or 0)
                                if profit > 0:
                                    profit_continuity += 1
                                else:
                                    break
                    
                    result[ts_code] = {
                        'roe_stability': roe_stability,
                        'profit_continuity': profit_continuity
                    }
                except Exception as e:
                    logger.debug(f"处理股票 {ts_code} 稳定性指标失败: {e}")
                    result[ts_code] = {'roe_stability': 999.0, 'profit_continuity': 0}
            
            time.sleep(0.5)  # 增加延迟
            
        except Exception as e:
            logger.warning(f"批量获取稳定性指标失败: {e}")
            # 降级：单个获取
            for ts_code in batch_codes:
                try:
                    result[ts_code] = calculate_stability_indicators(tushare_service, ts_code)
                    time.sleep(0.3)
                except Exception as e2:
                    result[ts_code] = {'roe_stability': 999.0, 'profit_continuity': 0}
    
    return result


def calculate_stability_indicators(
    tushare_service: TushareService,
    ts_code: str
) -> Dict:
    """
    计算稳定性指标
    
    Args:
        tushare_service: Tushare服务实例
        ts_code: 股票代码
        
    Returns:
        Dict: 包含以下字段的字典
            - roe_stability: ROE稳定性（最近3年ROE的标准差，越小越好）
            - profit_continuity: 盈利连续性（最近3年连续盈利的年数，0-3）
    """
    try:
        # 获取最近3年的财务指标
        fina_indicator = tushare_service.pro.fina_indicator(
            ts_code=ts_code,
            period='',
            fields='ts_code,end_date,roe'
        )
        
        if fina_indicator is None or fina_indicator.empty:
            return {'roe_stability': 999.0, 'profit_continuity': 0}
        
        # 按日期倒序排列，取最近3年（12个季度或3个年度）
        fina_indicator = fina_indicator.sort_values('end_date', ascending=False)
        
        # 筛选年度数据（end_date以1231结尾）
        annual_data = fina_indicator[fina_indicator['end_date'].astype(str).str.endswith('1231')]
        
        if annual_data.empty:
            # 如果没有年度数据，使用季度数据（取最近12个季度）
            quarterly_data = fina_indicator.head(12)
            roe_values = []
            for _, row in quarterly_data.iterrows():
                roe_val = float(row.get('roe', 0) or 0)
                roe_val = roe_val / 100 if roe_val > 1 else roe_val
                if roe_val > 0:
                    roe_values.append(roe_val)
        else:
            # 使用年度数据（取最近3年）
            annual_data = annual_data.head(3)
            roe_values = []
            for _, row in annual_data.iterrows():
                roe_val = float(row.get('roe', 0) or 0)
                roe_val = roe_val / 100 if roe_val > 1 else roe_val
                roe_values.append(roe_val)
        
        # 计算ROE稳定性（标准差）
        roe_stability = 999.0
        if len(roe_values) >= 2:
            roe_stability = float(np.std(roe_values))
        
        # 获取利润表数据，计算盈利连续性
        profit_df = None
        try:
            profit_df = tushare_service.pro.income(
                ts_code=ts_code,
                period='',
                fields='ts_code,end_date,n_income'
            )
        except Exception as e:
            logger.debug(f"获取利润表数据失败 {ts_code}: {e}")
        
        profit_continuity = 0
        if profit_df is not None and not profit_df.empty:
            profit_df = profit_df.sort_values('end_date', ascending=False)
            # 筛选年度数据
            annual_profit = profit_df[profit_df['end_date'].astype(str).str.endswith('1231')]
            if annual_profit.empty:
                # 如果没有年度数据，使用季度数据（取最近12个季度）
                quarterly_profit = profit_df.head(12)
                # 检查最近3年是否每年都有盈利季度
                profit_years = set()
                for _, row in quarterly_profit.iterrows():
                    end_date = str(row['end_date'])
                    year = end_date[:4]
                    profit = float(row['n_income'] or 0)
                    if profit > 0:
                        profit_years.add(year)
                profit_continuity = len(profit_years)
            else:
                # 使用年度数据（取最近3年）
                annual_profit = annual_profit.head(3)
                for _, row in annual_profit.iterrows():
                    profit = float(row['n_income'] or 0)
                    if profit > 0:
                        profit_continuity += 1
                    else:
                        break  # 一旦遇到亏损，停止计数
        
        return {
            'roe_stability': roe_stability,
            'profit_continuity': profit_continuity
        }
    except Exception as e:
        logger.warning(f"计算稳定性指标失败 {ts_code}: {e}")
        return {'roe_stability': 999.0, 'profit_continuity': 0}


def calculate_quality_indicators(
    tushare_service: TushareService,
    ts_code: str,
    report_date: str
) -> Dict:
    """
    计算质量指标
    
    Args:
        tushare_service: Tushare服务实例
        ts_code: 股票代码
        report_date: 报告期
        
    Returns:
        Dict: 包含以下字段的字典
            - net_cash_ratio: 净现比（经营现金流/净利润）
            - non_oper_ratio: 扣非净利润占比（扣非净利润/净利润）
    """
    try:
        # 获取现金流量表数据
        cashflow_df = None
        try:
            cashflow_df = tushare_service.pro.cashflow(
                ts_code=ts_code,
                period=report_date,
                fields='ts_code,end_date,n_cashflow_act'
            )
        except Exception as e:
            logger.debug(f"获取现金流量表数据失败 {ts_code}: {e}")
        
        # 获取利润表数据
        profit_df = None
        try:
            profit_df = tushare_service.pro.income(
                ts_code=ts_code,
                period=report_date,
                fields='ts_code,end_date,n_income,n_income_attr_p'
            )
        except Exception as e:
            logger.debug(f"获取利润表数据失败 {ts_code}: {e}")
        
        net_cash_ratio = 0.0
        non_oper_ratio = 0.0
        
        if cashflow_df is not None and not cashflow_df.empty and profit_df is not None and not profit_df.empty:
            latest_cashflow = cashflow_df.iloc[0]
            latest_profit = profit_df.iloc[0]
            
            operating_cashflow = float(latest_cashflow.get('n_cashflow_act', 0) or 0)
            net_profit = float(latest_profit.get('n_income', 0) or 0)
            non_oper_profit = float(latest_profit.get('n_income_attr_p', 0) or 0)  # 扣非净利润
            
            # 计算净现比
            if net_profit > 0:
                net_cash_ratio = operating_cashflow / net_profit
            
            # 计算扣非净利润占比
            if net_profit != 0:
                non_oper_ratio = abs(non_oper_profit / net_profit) if non_oper_profit != 0 else 0.0
        
        return {
            'net_cash_ratio': net_cash_ratio,
            'non_oper_ratio': non_oper_ratio
        }
    except Exception as e:
        logger.warning(f"计算质量指标失败 {ts_code}: {e}")
        return {'net_cash_ratio': 0.0, 'non_oper_ratio': 0.0}


def get_industry_leaders_by_value(industry_name: str, top_n: int = 3) -> List[Dict]:
    """
    价值龙头识别（基于财务指标的综合评分法）
    
    评分维度：
    - 盈利能力（25%）：ROE（12%）、净利率（8%）、毛利率（5%）
    - 财务健康度（20%）：负债率（10%）、经营现金流/营收（10%）
    - 成长性（20%）：营收增长率（12%）、净利润增长率（8%）
    - 市场表现（15%）：市值（8%）、PE合理性（4%）、PB合理性（3%）
    - 稳定性（15%）：ROE稳定性（8%）、盈利连续性（7%）
    - 质量指标（5%）：净现比（3%）、扣非净利润占比（2%）
    
    Args:
        industry_name: 行业名称
        top_n: 取前N只
        
    Returns:
        List[Dict]: 龙头股票列表
    """
    try:
        tushare_service = TushareService()
        if not tushare_service.available:
            logger.warning("Tushare服务不可用")
            return []
        
        # 1. 获取行业所有股票
        stock_basic = tushare_service.pro.stock_basic(
            exchange='',
            list_status='L',
            fields='ts_code,symbol,name,industry'
        )
        
        industry_stocks = stock_basic[stock_basic['industry'] == industry_name]
        
        if industry_stocks.empty:
            logger.debug(f"未找到行业股票: {industry_name}")
            return []
        
        logger.info(f"找到 {len(industry_stocks)} 只{industry_name}行业股票")
        
        # 2. 获取最新报告期
        current_year = datetime.now().year
        current_month = datetime.now().month
        if current_month <= 3:
            report_date = f"{current_year-1}1231"
        elif current_month <= 6:
            report_date = f"{current_year}0331"
        elif current_month <= 9:
            report_date = f"{current_year}0630"
        else:
            report_date = f"{current_year}0930"
        
        # 3. 获取最新交易日（用于市值和PE/PB）
        latest_trade_date = None
        try:
            trade_cal = tushare_service.pro.trade_cal(
                exchange='SSE',
                start_date='20240101',
                end_date='',
                is_open=1
            )
            if trade_cal is not None and not trade_cal.empty:
                latest_trade_date = trade_cal.iloc[-1]['cal_date']
        except Exception as e:
            logger.warning(f"获取最新交易日失败: {e}")
            today = datetime.now()
            for days_back in range(1, 8):
                try_date = (today - timedelta(days=days_back))
                if try_date.weekday() < 5:
                    latest_trade_date = try_date.strftime('%Y%m%d')
                    break
        
        if not latest_trade_date:
            logger.error("无法获取最新交易日")
            return []
        
        # 4. 批量获取所有股票的增强财务指标（优化：减少API调用）
        ts_codes = industry_stocks['ts_code'].tolist()
        scored_stocks = []
        
        # 先批量获取市值和PE/PB数据（一次性获取所有股票）
        try:
            daily_basic_all = tushare_service.pro.daily_basic(
                trade_date=latest_trade_date,
                fields='ts_code,total_mv,pe_ttm,pb,dv_ratio'
            )
        except Exception as e:
            logger.warning(f"批量获取市值数据失败: {e}")
            daily_basic_all = pd.DataFrame()

        # 更新估值数据到 fact_daily_fundamental
        if daily_basic_all is not None and not daily_basic_all.empty:
            update_fundamental_valuation(daily_basic_all, latest_trade_date)

        # 批量获取财务指标（分批处理，每批50只）
        # 优化：优先从数据库读取，减少API调用
        batch_size = 50
        all_financial_data = {}  # {ts_code: financial_dict}
        all_stability_data = {}  # {ts_code: stability_dict}
        all_quality_data = {}  # {ts_code: quality_dict}
        
        # 1. 先从数据库批量读取财务数据（优化：使用批量查询）
        logger.info(f"📊 优先从数据库读取财务数据（{len(ts_codes)}只股票）...")
        batch_financial_data = batch_get_financial_from_db(ts_codes, report_date)
        all_financial_data.update(batch_financial_data)
        db_missing_codes = [code for code in ts_codes if code not in all_financial_data]
        
        logger.info(f"✅ 从数据库读取到 {len(all_financial_data)}/{len(ts_codes)} 只股票的财务数据")
        if db_missing_codes:
            logger.info(f"📥 需要从API获取 {len(db_missing_codes)} 只股票的财务数据")
        
        # 2. 对于数据库没有的股票，从API批量获取
        for i in range(0, len(db_missing_codes), batch_size):
            batch_codes = db_missing_codes[i:i+batch_size]
            codes_str = ','.join(batch_codes)
            
            try:
                # 批量获取财务指标（先尝试指定报告期，如果为空则获取最新报告期）
                fina_indicator_batch = tushare_service.pro.fina_indicator(
                    ts_code=codes_str,
                    period=report_date,
                    fields='ts_code,end_date,roe,netprofit_margin,grossprofit_margin,debt_to_assets,ocf_to_revenue,revenue,yoy_sales'
                )
                
                # 如果指定报告期没有数据，尝试获取最新报告期（period为空时返回所有报告期）
                if fina_indicator_batch is None or fina_indicator_batch.empty:
                    logger.debug(f"指定报告期 {report_date} 无数据，尝试获取最新报告期...")
                    fina_indicator_batch = tushare_service.pro.fina_indicator(
                        ts_code=codes_str,
                        period='',  # 空字符串返回所有报告期
                        fields='ts_code,end_date,roe,netprofit_margin,grossprofit_margin,debt_to_assets,ocf_to_revenue,revenue,yoy_sales'
                    )
                    # 只保留每个股票最新的报告期数据
                    if fina_indicator_batch is not None and not fina_indicator_batch.empty:
                        fina_indicator_batch = fina_indicator_batch.sort_values('end_date', ascending=False).groupby('ts_code').first().reset_index()
                
                # 批量获取利润表数据（用于计算净利润增长率）
                income_batch = None
                try:
                    income_batch = tushare_service.pro.income(
                        ts_code=codes_str,
                        period='',
                        fields='ts_code,end_date,n_income,n_income_attr_p'
                    )
                except Exception as e:
                    logger.debug(f"批量获取利润表数据失败: {e}")
                
                # 批量获取现金流量表数据
                cashflow_batch = None
                try:
                    cashflow_batch = tushare_service.pro.cashflow(
                        ts_code=codes_str,
                        period=report_date,
                        fields='ts_code,end_date,n_cashflow_act'
                    )
                    # 如果指定报告期没有数据，尝试获取最新报告期
                    if cashflow_batch is None or cashflow_batch.empty:
                        cashflow_batch = tushare_service.pro.cashflow(
                            ts_code=codes_str,
                            period='',  # 空字符串返回所有报告期
                            fields='ts_code,end_date,n_cashflow_act'
                        )
                        if cashflow_batch is not None and not cashflow_batch.empty:
                            cashflow_batch = cashflow_batch.sort_values('end_date', ascending=False).groupby('ts_code').first().reset_index()
                except Exception as e:
                    logger.debug(f"批量获取现金流量表数据失败: {e}")
                
                # 处理每只股票的财务数据
                if fina_indicator_batch is not None and not fina_indicator_batch.empty:
                    actual_report_dates = fina_indicator_batch['end_date'].unique()
                    logger.debug(f"  ✅ 批量获取到 {len(fina_indicator_batch)} 条财务指标数据，报告期: {actual_report_dates}")
                    for _, row in fina_indicator_batch.iterrows():
                        ts_code = row['ts_code']
                        actual_end_date = row.get('end_date', report_date)
                        if str(actual_end_date) != report_date:
                            logger.debug(f"  📌 {ts_code} 使用报告期 {actual_end_date}（而非 {report_date}）")
                        
                        # 处理财务指标
                        roe_val = float(row.get('roe', 0) or 0)
                        net_margin_val = float(row.get('netprofit_margin', 0) or 0)
                        gross_margin_val = float(row.get('grossprofit_margin', 0) or 0)
                        debt_ratio_val = float(row.get('debt_to_assets', 0) or 0)
                        cashflow_to_revenue_val = float(row.get('ocf_to_revenue', 0) or 0)
                        revenue_growth_val = float(row.get('yoy_sales', 0) or 0)
                        revenue_val = float(row.get('revenue', 0) or 0) / 100000000
                        
                        # 转换百分比
                        roe = roe_val / 100 if roe_val > 1 else roe_val
                        net_margin = net_margin_val / 100 if net_margin_val > 1 else net_margin_val
                        gross_margin = gross_margin_val / 100 if gross_margin_val > 1 else gross_margin_val
                        debt_ratio = debt_ratio_val / 100 if debt_ratio_val > 1 else debt_ratio_val
                        cashflow_to_revenue = cashflow_to_revenue_val / 100 if cashflow_to_revenue_val > 1 else cashflow_to_revenue_val
                        
                        # 计算净利润增长率
                        profit_growth = 0.0
                        net_profit = 0.0
                        if income_batch is not None and not income_batch.empty:
                            stock_income = income_batch[income_batch['ts_code'] == ts_code].sort_values('end_date', ascending=False)
                            if not stock_income.empty and len(stock_income) >= 2:
                                current_profit = float(stock_income.iloc[0]['n_income'] or 0)
                                prev_profit = float(stock_income.iloc[1]['n_income'] or 0)
                                if prev_profit > 0:
                                    profit_growth = ((current_profit - prev_profit) / prev_profit) * 100
                                net_profit = current_profit / 100000000
                        
                        all_financial_data[ts_code] = {
                            'roe': roe,
                            'net_margin': net_margin,
                            'gross_margin': gross_margin,
                            'debt_ratio': debt_ratio,
                            'cashflow_to_revenue': cashflow_to_revenue,
                            'revenue_growth': revenue_growth_val,
                            'profit_growth': profit_growth,
                            'revenue': revenue_val,
                            'net_profit': net_profit
                        }
                        
                        # 计算质量指标
                        non_oper_ratio = 0.0
                        net_cash_ratio = 0.0
                        if income_batch is not None and not income_batch.empty:
                            stock_income = income_batch[income_batch['ts_code'] == ts_code]
                            if not stock_income.empty:
                                latest_income = stock_income.iloc[0]
                                net_profit_val = float(latest_income.get('n_income', 0) or 0)
                                non_oper_profit = float(latest_income.get('n_income_attr_p', 0) or 0)
                                if net_profit_val != 0:
                                    non_oper_ratio = abs(non_oper_profit / net_profit_val) if non_oper_profit != 0 else 0.0
                        
                        if cashflow_batch is not None and not cashflow_batch.empty:
                            stock_cashflow = cashflow_batch[cashflow_batch['ts_code'] == ts_code]
                            if not stock_cashflow.empty:
                                operating_cashflow = float(stock_cashflow.iloc[0].get('n_cashflow_act', 0) or 0)
                                if net_profit > 0:
                                    net_cash_ratio = operating_cashflow / (net_profit * 100000000)
                        
                        all_quality_data[ts_code] = {
                            'net_cash_ratio': net_cash_ratio,
                            'non_oper_ratio': non_oper_ratio
                        }
                
                # 批量获取稳定性指标（优化：使用批量函数）
                batch_stability = batch_get_stability_indicators(tushare_service, batch_codes)
                all_stability_data.update(batch_stability)
                
                time.sleep(0.5)  # 增加延迟，避免触发频率限制
                
            except Exception as e:
                logger.warning(f"批量获取数据失败（批次 {i//batch_size + 1}，{len(batch_codes)}只股票）: {e}")
                logger.debug(f"  失败批次股票代码: {batch_codes[:5]}..." if len(batch_codes) > 5 else f"  失败批次股票代码: {batch_codes}")
                # 如果批量获取失败，尝试单个获取（降级处理）
                for ts_code in batch_codes:
                    try:
                        financial = get_enhanced_financial_indicators(tushare_service, ts_code, report_date)
                        if financial:
                            all_financial_data[ts_code] = financial
                        stability = calculate_stability_indicators(tushare_service, ts_code)
                        all_stability_data[ts_code] = stability
                        quality = calculate_quality_indicators(tushare_service, ts_code, report_date)
                        all_quality_data[ts_code] = quality
                        time.sleep(0.3)  # 单个获取时增加延迟
                    except Exception as e2:
                        logger.debug(f"单个获取数据失败 {ts_code}: {e2}")
                continue
        
        # 5. 合并数据并计算得分
        logger.info(f"📊 开始合并数据，共 {len(ts_codes)} 只股票，已获取财务数据 {len(all_financial_data)} 只")
        for ts_code in ts_codes:
            try:
                financial = all_financial_data.get(ts_code)
                if not financial:
                    logger.debug(f"  ⚠️ 跳过 {ts_code}：无财务数据")
                    continue
                
                stability = all_stability_data.get(ts_code, {'roe_stability': 999.0, 'profit_continuity': 0})
                quality = all_quality_data.get(ts_code, {'net_cash_ratio': 0.0, 'non_oper_ratio': 0.0})
                
                # 获取市值和PE/PB
                stock_daily = daily_basic_all[daily_basic_all['ts_code'] == ts_code] if not daily_basic_all.empty else pd.DataFrame()
                market_cap = 0.0
                pe = 0.0
                pb = 0.0
                if not stock_daily.empty:
                    market_cap = float(stock_daily.iloc[0]['total_mv'] or 0) / 10000
                    pe = float(stock_daily.iloc[0]['pe'] or 0)
                    pb = float(stock_daily.iloc[0]['pb'] or 0)
                
                # 获取股票名称
                stock_info = industry_stocks[industry_stocks['ts_code'] == ts_code]
                if stock_info.empty:
                    continue
                name = stock_info.iloc[0]['name']
                
                scored_stocks.append({
                    'ts_code': ts_code,
                    'name': name,
                    'roe': financial.get('roe', 0),
                    'net_margin': financial.get('net_margin', 0),
                    'gross_margin': financial.get('gross_margin', 0),
                    'debt_ratio': financial.get('debt_ratio', 0),
                    'cashflow_to_revenue': financial.get('cashflow_to_revenue', 0),
                    'revenue_growth': financial.get('revenue_growth', 0),
                    'profit_growth': financial.get('profit_growth', 0),
                    'market_cap': market_cap,
                    'pe': pe,
                    'pb': pb,
                    'roe_stability': stability.get('roe_stability', 999.0),
                    'profit_continuity': stability.get('profit_continuity', 0),
                    'net_cash_ratio': quality.get('net_cash_ratio', 0),
                    'non_oper_ratio': quality.get('non_oper_ratio', 0),
                    'revenue': financial.get('revenue', 0)
                })
            except Exception as e:
                logger.debug(f"处理股票 {ts_code} 失败: {e}")
                continue
        
        if not scored_stocks:
            logger.warning(f"未获取到任何有效数据（共 {len(ts_codes)} 只股票，获取到财务数据 {len(all_financial_data)} 只）")
            if len(all_financial_data) == 0:
                logger.warning(f"  ⚠️ 所有股票都没有财务数据，可能原因：")
                logger.warning(f"     1. 数据库中没有该行业的财务数据")
                logger.warning(f"     2. API调用失败或返回空数据")
                logger.warning(f"     3. 报告期 {report_date} 数据尚未发布")
            return []
        
        # 6. 归一化并计算综合得分
        # 计算最大值（用于归一化）
        max_roe = max([s['roe'] for s in scored_stocks if s['roe'] > 0]) if any(s['roe'] > 0 for s in scored_stocks) else 1
        max_net_margin = max([s['net_margin'] for s in scored_stocks if s['net_margin'] > 0]) if any(s['net_margin'] > 0 for s in scored_stocks) else 1
        max_gross_margin = max([s['gross_margin'] for s in scored_stocks if s['gross_margin'] > 0]) if any(s['gross_margin'] > 0 for s in scored_stocks) else 1
        max_revenue_growth = max([s['revenue_growth'] for s in scored_stocks if s['revenue_growth'] > 0]) if any(s['revenue_growth'] > 0 for s in scored_stocks) else 1
        max_profit_growth = max([s['profit_growth'] for s in scored_stocks if s['profit_growth'] > 0]) if any(s['profit_growth'] > 0 for s in scored_stocks) else 1
        max_market_cap = max([s['market_cap'] for s in scored_stocks if s['market_cap'] > 0]) if any(s['market_cap'] > 0 for s in scored_stocks) else 1
        max_cashflow_to_revenue = max([s['cashflow_to_revenue'] for s in scored_stocks if s['cashflow_to_revenue'] > 0]) if any(s['cashflow_to_revenue'] > 0 for s in scored_stocks) else 1
        max_net_cash_ratio = max([s['net_cash_ratio'] for s in scored_stocks if s['net_cash_ratio'] > 0]) if any(s['net_cash_ratio'] > 0 for s in scored_stocks) else 1
        max_non_oper_ratio = max([s['non_oper_ratio'] for s in scored_stocks if s['non_oper_ratio'] > 0]) if any(s['non_oper_ratio'] > 0 for s in scored_stocks) else 1
        
        # 计算最小ROE稳定性（越小越好，需要反向评分）
        min_roe_stability = min([s['roe_stability'] for s in scored_stocks if s['roe_stability'] < 999]) if any(s['roe_stability'] < 999 for s in scored_stocks) else 1
        max_roe_stability = max([s['roe_stability'] for s in scored_stocks if s['roe_stability'] < 999]) if any(s['roe_stability'] < 999 for s in scored_stocks) else 1
        
        # 计算最大负债率（用于反向评分）
        max_debt_ratio = max([s['debt_ratio'] for s in scored_stocks if s['debt_ratio'] > 0]) if any(s['debt_ratio'] > 0 for s in scored_stocks) else 1
        
        # 计算最大盈利连续性
        max_profit_continuity = max([s['profit_continuity'] for s in scored_stocks]) if scored_stocks else 3
        
        # PE合理性评分（10-50为合理范围）
        def pe_score(pe_val):
            if pe_val <= 0:
                return 0
            elif 10 <= pe_val <= 50:
                return 1.0
            elif 5 <= pe_val < 10 or 50 < pe_val <= 100:
                return 0.5
            else:
                return 0.2
        
        # PB合理性评分（1-5为合理范围）
        def pb_score(pb_val):
            if pb_val <= 0:
                return 0
            elif 1 <= pb_val <= 5:
                return 1.0
            elif 0.5 <= pb_val < 1 or 5 < pb_val <= 10:
                return 0.5
            else:
                return 0.2
        
        # 计算每只股票的综合得分
        for stock in scored_stocks:
            # 盈利能力（25%）
            roe_score = (stock['roe'] / max_roe) if max_roe > 0 and stock['roe'] > 0 else 0
            net_margin_score = (stock['net_margin'] / max_net_margin) if max_net_margin > 0 and stock['net_margin'] > 0 else 0
            gross_margin_score = (stock['gross_margin'] / max_gross_margin) if max_gross_margin > 0 and stock['gross_margin'] > 0 else 0
            profitability_score = roe_score * 0.12 + net_margin_score * 0.08 + gross_margin_score * 0.05
            
            # 财务健康度（20%）
            # 负债率反向评分（越低越好）
            debt_score = 1 - (stock['debt_ratio'] / max_debt_ratio) if max_debt_ratio > 0 and stock['debt_ratio'] >= 0 else 0
            debt_score = max(0, min(1, debt_score))  # 限制在0-1
            cashflow_score = (stock['cashflow_to_revenue'] / max_cashflow_to_revenue) if max_cashflow_to_revenue > 0 and stock['cashflow_to_revenue'] > 0 else 0
            financial_health_score = debt_score * 0.10 + cashflow_score * 0.10
            
            # 成长性（20%）
            revenue_growth_score = (stock['revenue_growth'] / max_revenue_growth) if max_revenue_growth > 0 and stock['revenue_growth'] > 0 else 0
            profit_growth_score = (stock['profit_growth'] / max_profit_growth) if max_profit_growth > 0 and stock['profit_growth'] > 0 else 0
            growth_score = revenue_growth_score * 0.12 + profit_growth_score * 0.08
            
            # 市场表现（15%）
            market_cap_score = (stock['market_cap'] / max_market_cap) if max_market_cap > 0 and stock['market_cap'] > 0 else 0
            pe_score_val = pe_score(stock['pe'])
            pb_score_val = pb_score(stock['pb'])
            market_performance_score = market_cap_score * 0.08 + pe_score_val * 0.04 + pb_score_val * 0.03
            
            # 稳定性（15%）
            # ROE稳定性反向评分（越小越好）
            if stock['roe_stability'] < 999 and max_roe_stability > min_roe_stability:
                roe_stability_score = 1 - ((stock['roe_stability'] - min_roe_stability) / (max_roe_stability - min_roe_stability))
                roe_stability_score = max(0, min(1, roe_stability_score))
            else:
                roe_stability_score = 0
            profit_continuity_score = (stock['profit_continuity'] / max_profit_continuity) if max_profit_continuity > 0 else 0
            stability_score = roe_stability_score * 0.08 + profit_continuity_score * 0.07
            
            # 质量指标（5%）
            net_cash_ratio_score = (stock['net_cash_ratio'] / max_net_cash_ratio) if max_net_cash_ratio > 0 and stock['net_cash_ratio'] > 0 else 0
            non_oper_ratio_score = (stock['non_oper_ratio'] / max_non_oper_ratio) if max_non_oper_ratio > 0 and stock['non_oper_ratio'] > 0 else 0
            quality_score = net_cash_ratio_score * 0.03 + non_oper_ratio_score * 0.02
            
            # 综合得分（0-100）
            comprehensive_score = (
                profitability_score * 25 +
                financial_health_score * 20 +
                growth_score * 20 +
                market_performance_score * 15 +
                stability_score * 15 +
                quality_score * 5
            )
            
            stock['value_score'] = comprehensive_score
        
        # 6. 按综合得分排序
        scored_stocks.sort(key=lambda x: x.get('value_score', 0), reverse=True)
        
        # 7. 构造结果（展示时统一百分比：内部存的是小数 0~1，展示为 0~100%）
        def _to_pct_display(val):
            """将小数形式的比例转为百分比展示值（0.22 -> 22）。若已是百分比形式（如 15）则不变。"""
            if val is None:
                return 0.0
            v = float(val)
            if abs(v) <= 1.5 and v != 0:
                return v * 100
            return v

        leaders = []
        for idx, stock in enumerate(scored_stocks[:top_n]):
            roe_pct = _to_pct_display(stock['roe'])
            net_pct = _to_pct_display(stock['net_margin'])
            gross_pct = _to_pct_display(stock['gross_margin'])
            debt_pct = _to_pct_display(stock['debt_ratio'])
            cf_pct = _to_pct_display(stock['cashflow_to_revenue'])
            rev_growth_pct = _to_pct_display(stock['revenue_growth'])
            profit_growth_pct = _to_pct_display(stock['profit_growth'])
            non_oper_pct = _to_pct_display(stock['non_oper_ratio'])
            roe_stability_str = "暂无" if (stock.get('roe_stability') or 999) >= 999 else f"{stock['roe_stability']:.2f}（标准差，越小越好）"
            quality_line = f"- 净现比: {stock['net_cash_ratio']:.2f}\n- 扣非净利润占比: {non_oper_pct:.2f}%"
            if (stock.get('net_cash_ratio') or 0) == 0 and (stock.get('non_oper_ratio') or 0) == 0:
                quality_line = "- 暂无"

            reason = f"""价值龙头（综合得分排名第{idx+1}位，得分{stock['value_score']:.1f}/100）

【盈利能力】
- ROE: {roe_pct:.2f}%
- 净利率: {net_pct:.2f}%
- 毛利率: {gross_pct:.2f}%

【财务健康】
- 负债率: {debt_pct:.2f}%
- 现金流/营收: {cf_pct:.2f}%

【成长性】
- 营收增长: {rev_growth_pct:.2f}%
- 净利润增长: {profit_growth_pct:.2f}%

【稳定性】
- ROE稳定性: {roe_stability_str}
- 连续盈利: {stock['profit_continuity']}年

【质量指标】
{quality_line}"""
            
            leaders.append({
                'ts_code': stock['ts_code'],
                'name': stock['name'],
                'leader_type': '行业龙头' if idx == 0 else '板块龙头',
                'reason': reason,
                'market_cap': stock['market_cap'],
                'value_score': stock['value_score'],
                'roe': stock['roe'],
                'net_margin': stock['net_margin'],
                'gross_margin': stock['gross_margin'],
                'revenue': stock['revenue'],
                'main_business': ''
            })
        
        logger.info(f"✅ 获取到 {len(leaders)} 只{industry_name}行业价值龙头股票")
        return leaders
        
    except Exception as e:
        logger.error(f"获取价值龙头失败: {e}", exc_info=True)
        return []


def get_market_heat_indicators(
    warehouse_service: WarehouseService,
    tushare_service: TushareService,
    ts_code: str,
    industry_name: str,
    trade_date: str,
    lookback_days: int = 20
) -> Dict:
    """
    获取市场热度指标
    
    Args:
        warehouse_service: 数据仓库服务
        tushare_service: Tushare服务实例
        ts_code: 股票代码
        industry_name: 行业名称
        trade_date: 交易日期（YYYYMMDD格式）
        lookback_days: 回看天数
        
    Returns:
        Dict: 包含以下字段的字典
            - industry_heat: 行业热度（0-20）
            - stock_heat_score: 个股热度得分（0-100）
            - return_5d: 近5日涨幅
            - return_20d: 近20日涨幅
            - amount_ratio: 成交额放大倍数（相对20日均值）
            - turnover_rate: 换手率
            - relative_strength_industry: 相对行业强度
            - relative_strength_market: 相对大盘强度
            - amount_share: 成交额占比（个股/行业）
    """
    try:
        session = warehouse_service.get_session()
        
        try:
            # 1. 获取个股价格和成交数据
            trade_date_obj = datetime.strptime(trade_date, '%Y%m%d').date()
            start_date = trade_date_obj - timedelta(days=lookback_days + 10)  # 多取一些数据用于计算均线
            
            prices = session.query(FactDailyPriceQfq).filter(
                FactDailyPriceQfq.ts_code == ts_code,
                FactDailyPriceQfq.trade_date >= start_date,
                FactDailyPriceQfq.trade_date <= trade_date_obj
            ).order_by(FactDailyPriceQfq.trade_date).all()
            
            if not prices or len(prices) < 5:
                return {}
            
            # 转换为DataFrame
            price_data = []
            for p in prices:
                price_data.append({
                    'trade_date': p.trade_date,
                    'close': float(p.close) if p.close else None,
                    'amount': float(p.amount) if p.amount else 0,
                    'turnover_rate': float(p.turnover_rate) if p.turnover_rate else 0
                })
            price_df = pd.DataFrame(price_data)
            price_df = price_df.sort_values('trade_date')
            
            # 2. 计算涨幅
            if len(price_df) >= 5:
                current_price = price_df.iloc[-1]['close']
                price_5d_ago = price_df.iloc[-6]['close'] if len(price_df) >= 6 else price_df.iloc[0]['close']
                return_5d = ((current_price / price_5d_ago) - 1) * 100 if price_5d_ago > 0 else 0
            else:
                return_5d = 0
            
            if len(price_df) >= 20:
                price_20d_ago = price_df.iloc[-21]['close'] if len(price_df) >= 21 else price_df.iloc[0]['close']
                return_20d = ((current_price / price_20d_ago) - 1) * 100 if price_20d_ago > 0 else 0
            else:
                return_20d = return_5d
            
            # 3. 计算成交额放大倍数
            recent_amounts = price_df.tail(5)['amount'].values
            avg_amount_20d = price_df.tail(20)['amount'].mean() if len(price_df) >= 20 else price_df['amount'].mean()
            current_amount = price_df.iloc[-1]['amount']
            amount_ratio = (current_amount / avg_amount_20d) if avg_amount_20d > 0 else 1.0
            
            # 4. 获取换手率
            turnover_rate = price_df.iloc[-1]['turnover_rate'] if len(price_df) > 0 else 0
            
            # 5. 获取行业所有股票数据（用于计算行业热度）
            stock_basic = tushare_service.pro.stock_basic(
                exchange='',
                list_status='L',
                fields='ts_code,industry'
            )
            industry_stocks = stock_basic[stock_basic['industry'] == industry_name]
            industry_codes = industry_stocks['ts_code'].tolist()
            
            # 获取行业股票的价格数据
            industry_prices = session.query(FactDailyPriceQfq).filter(
                FactDailyPriceQfq.ts_code.in_(industry_codes),
                FactDailyPriceQfq.trade_date == trade_date_obj
            ).all()
            
            # 计算行业平均涨幅和总成交额
            industry_total_amount = sum([float(p.amount or 0) for p in industry_prices])
            amount_share = (current_amount / industry_total_amount * 100) if industry_total_amount > 0 else 0
            
            # 计算行业5日和20日涨幅（简化：使用行业平均）
            industry_return_5d = 0.0
            industry_return_20d = 0.0
            if len(industry_prices) > 0:
                # 获取行业股票5日前和20日前价格
                industry_start_date = trade_date_obj - timedelta(days=25)
                industry_historical = session.query(FactDailyPriceQfq).filter(
                    FactDailyPriceQfq.ts_code.in_(industry_codes),
                    FactDailyPriceQfq.trade_date >= industry_start_date,
                    FactDailyPriceQfq.trade_date <= trade_date_obj
                ).all()
                
                if industry_historical:
                    # 按日期和股票代码组织数据
                    industry_df_data = {}
                    for p in industry_historical:
                        if p.ts_code not in industry_df_data:
                            industry_df_data[p.ts_code] = []
                        industry_df_data[p.ts_code].append({
                            'trade_date': p.trade_date,
                            'close': float(p.close) if p.close else None
                        })
                    
                    # 计算每只股票的涨幅，然后取平均
                    returns_5d = []
                    returns_20d = []
                    for code, prices_list in industry_df_data.items():
                        prices_list = sorted(prices_list, key=lambda x: x['trade_date'])
                        if len(prices_list) >= 6:
                            current = prices_list[-1]['close']
                            price_5d = prices_list[-6]['close'] if len(prices_list) >= 6 else prices_list[0]['close']
                            if current and price_5d and price_5d > 0:
                                returns_5d.append(((current / price_5d) - 1) * 100)
                        if len(prices_list) >= 21:
                            current = prices_list[-1]['close']
                            price_20d = prices_list[-21]['close'] if len(prices_list) >= 21 else prices_list[0]['close']
                            if current and price_20d and price_20d > 0:
                                returns_20d.append(((current / price_20d) - 1) * 100)
                    
                    industry_return_5d = sum(returns_5d) / len(returns_5d) if returns_5d else 0
                    industry_return_20d = sum(returns_20d) / len(returns_20d) if returns_20d else 0
            
            # 6. 计算相对强度
            relative_strength_industry = return_5d - industry_return_5d
            relative_strength_market = return_5d  # 简化：假设大盘涨幅为0，实际可以从指数获取
            
            # 7. 计算个股热度得分（0-100）
            # 基于涨幅、成交额放大倍数、换手率
            heat_score = 0.0
            if return_5d > 0:
                heat_score += min(40, return_5d * 2)  # 涨幅得分，最高40分
            if amount_ratio > 1:
                heat_score += min(30, (amount_ratio - 1) * 15)  # 成交额放大得分，最高30分
            if turnover_rate > 0:
                heat_score += min(30, turnover_rate * 3)  # 换手率得分，最高30分
            
            # 8. 获取行业热度（简化：基于行业平均涨幅和成交额）
            # 实际应该调用 sector_heat_calculator，这里简化处理
            industry_heat = 0.0
            if industry_return_5d > 0:
                industry_heat = min(20, industry_return_5d * 2)
            
            return {
                'industry_heat': industry_heat,
                'stock_heat_score': min(100, heat_score),
                'return_5d': return_5d,
                'return_20d': return_20d,
                'amount_ratio': amount_ratio,
                'turnover_rate': turnover_rate,
                'relative_strength_industry': relative_strength_industry,
                'relative_strength_market': relative_strength_market,
                'amount_share': amount_share
            }
        finally:
            session.close()
            
    except Exception as e:
        logger.warning(f"获取市场热度指标失败 {ts_code}: {e}")
        return {}


def get_technical_indicators(
    warehouse_service: WarehouseService,
    ts_code: str,
    trade_date: str,
    lookback_days: int = 20
) -> Dict:
    """
    获取技术面指标
    
    Args:
        warehouse_service: 数据仓库服务
        ts_code: 股票代码
        trade_date: 交易日期（YYYYMMDD格式）
        lookback_days: 回看天数
        
    Returns:
        Dict: 包含以下字段的字典
            - trend_strength: 趋势强度（0-100）
            - breakout_signal: 突破信号（0/1）
            - volume_price_match: 量价配合度（0-100）
            - rsi: RSI指标
            - macd_signal: MACD信号（'golden_cross'/'death_cross'/'none'）
    """
    try:
        session = warehouse_service.get_session()
        
        try:
            trade_date_obj = datetime.strptime(trade_date, '%Y%m%d').date()
            start_date = trade_date_obj - timedelta(days=lookback_days + 30)  # 多取一些数据用于计算指标
            
            prices = session.query(FactDailyPriceQfq).filter(
                FactDailyPriceQfq.ts_code == ts_code,
                FactDailyPriceQfq.trade_date >= start_date,
                FactDailyPriceQfq.trade_date <= trade_date_obj
            ).order_by(FactDailyPriceQfq.trade_date).all()
            
            if not prices or len(prices) < 20:
                return {}
            
            # 转换为DataFrame
            price_data = []
            for p in prices:
                price_data.append({
                    'trade_date': p.trade_date,
                    'close': float(p.close) if p.close else None,
                    'amount': float(p.amount) if p.amount else 0,
                    'volume': float(p.volume) if p.volume else 0
                })
            price_df = pd.DataFrame(price_data)
            price_df = price_df.sort_values('trade_date')
            
            # 1. 计算均线系统
            price_df['ma5'] = price_df['close'].rolling(window=5).mean()
            price_df['ma10'] = price_df['close'].rolling(window=10).mean()
            price_df['ma20'] = price_df['close'].rolling(window=20).mean()
            
            # 2. 计算趋势强度（MA5>MA10>MA20为最强趋势）
            if len(price_df) >= 20:
                latest = price_df.iloc[-1]
                ma5 = latest['ma5']
                ma10 = latest['ma10']
                ma20 = latest['ma20']
                
                trend_strength = 0.0
                if pd.notna(ma5) and pd.notna(ma10) and pd.notna(ma20):
                    if ma5 > ma10 > ma20:
                        trend_strength = 100.0
                    elif ma5 > ma10:
                        trend_strength = 60.0
                    elif ma5 > ma20:
                        trend_strength = 40.0
                    else:
                        trend_strength = 20.0
            else:
                trend_strength = 0.0
            
            # 3. 判断突破信号（简化：突破20日均线）
            breakout_signal = 0
            if len(price_df) >= 20:
                current_price = price_df.iloc[-1]['close']
                ma20_current = price_df.iloc[-1]['ma20']
                ma20_prev = price_df.iloc[-2]['ma20'] if len(price_df) >= 2 else ma20_current
                
                if pd.notna(ma20_current) and pd.notna(ma20_prev):
                    # 突破：当前价格>MA20，且之前价格<=MA20
                    if current_price > ma20_current and price_df.iloc[-2]['close'] <= ma20_prev:
                        breakout_signal = 1
            
            # 4. 计算量价配合度（简化：价格上涨时成交量放大）
            volume_price_match = 50.0  # 默认50分
            if len(price_df) >= 5:
                recent_prices = price_df.tail(5)
                price_change = (recent_prices.iloc[-1]['close'] / recent_prices.iloc[0]['close'] - 1) * 100
                volume_change = (recent_prices.iloc[-1]['amount'] / recent_prices.iloc[0]['amount'] - 1) * 100
                
                if price_change > 0 and volume_change > 0:
                    volume_price_match = min(100, 50 + (price_change + volume_change) * 2)
                elif price_change < 0 and volume_change < 0:
                    volume_price_match = min(100, 50 + abs(price_change + volume_change) * 2)
            
            # 5. 计算RSI（简化版）
            rsi = 50.0
            if len(price_df) >= 14:
                price_changes = price_df['close'].diff()
                gains = price_changes[price_changes > 0].tail(14).mean() if len(price_changes[price_changes > 0]) > 0 else 0
                losses = abs(price_changes[price_changes < 0].tail(14).mean()) if len(price_changes[price_changes < 0]) > 0 else 0
                
                if losses > 0:
                    rs = gains / losses
                    rsi = 100 - (100 / (1 + rs))
            
            # 6. 计算MACD信号（简化版）
            macd_signal = 'none'
            if len(price_df) >= 26:
                # 计算EMA12和EMA26
                ema12 = price_df['close'].ewm(span=12, adjust=False).mean()
                ema26 = price_df['close'].ewm(span=26, adjust=False).mean()
                macd_line = ema12 - ema26
                signal_line = macd_line.ewm(span=9, adjust=False).mean()
                
                if len(macd_line) >= 2 and len(signal_line) >= 2:
                    macd_current = macd_line.iloc[-1]
                    macd_prev = macd_line.iloc[-2]
                    signal_current = signal_line.iloc[-1]
                    signal_prev = signal_line.iloc[-2]
                    
                    if pd.notna(macd_current) and pd.notna(macd_prev) and pd.notna(signal_current) and pd.notna(signal_prev):
                        # 金叉：MACD从下方穿越信号线
                        if macd_prev <= signal_prev and macd_current > signal_current:
                            macd_signal = 'golden_cross'
                        # 死叉：MACD从上方穿越信号线
                        elif macd_prev >= signal_prev and macd_current < signal_current:
                            macd_signal = 'death_cross'
            
            return {
                'trend_strength': trend_strength,
                'breakout_signal': breakout_signal,
                'volume_price_match': volume_price_match,
                'rsi': rsi,
                'macd_signal': macd_signal
            }
        finally:
            session.close()
            
    except Exception as e:
        logger.warning(f"获取技术面指标失败 {ts_code}: {e}")
        return {}


def get_industry_leaders_by_market_heat(
    industry_name: str,
    top_n: int = 3,
    lookback_days: int = 20
) -> List[Dict]:
    """
    基于市场热度识别行业龙头
    
    评分维度：
    - 市场热度（35%）：行业热度（15%）、个股热度（20%）
    - 资金关注度（25%）：成交额占比（25%）
    - 技术面表现（20%）：相对强度（10%）、技术形态（10%）
    - 市场地位（20%）：涨幅排名（10%）、成交额排名（10%）
    
    Args:
        industry_name: 行业名称
        top_n: 取前N只
        lookback_days: 回看天数
        
    Returns:
        List[Dict]: 市场龙头列表
    """
    try:
        tushare_service = TushareService()
        if not tushare_service.available:
            logger.warning("Tushare服务不可用")
            return []
        
        warehouse_service = WarehouseService()
        
        # 1. 获取行业所有股票
        stock_basic = tushare_service.pro.stock_basic(
            exchange='',
            list_status='L',
            fields='ts_code,symbol,name,industry'
        )
        
        industry_stocks = stock_basic[stock_basic['industry'] == industry_name]
        
        if industry_stocks.empty:
            logger.debug(f"未找到行业股票: {industry_name}")
            return []
        
        logger.info(f"找到 {len(industry_stocks)} 只{industry_name}行业股票")
        
        # 2. 获取最新交易日
        latest_trade_date = None
        try:
            trade_cal = tushare_service.pro.trade_cal(
                exchange='SSE',
                start_date='20240101',
                end_date='',
                is_open=1
            )
            if trade_cal is not None and not trade_cal.empty:
                latest_trade_date = trade_cal.iloc[-1]['cal_date']
        except Exception as e:
            logger.warning(f"获取最新交易日失败: {e}")
            today = datetime.now()
            for days_back in range(1, 8):
                try_date = (today - timedelta(days=days_back))
                if try_date.weekday() < 5:
                    latest_trade_date = try_date.strftime('%Y%m%d')
                    break
        
        if not latest_trade_date:
            logger.error("无法获取最新交易日")
            return []
        
        # 3. 对每只股票计算市场热度指标和技术面指标
        ts_codes = industry_stocks['ts_code'].tolist()
        scored_stocks = []
        
        for ts_code in ts_codes:
            try:
                # 获取市场热度指标
                heat_indicators = get_market_heat_indicators(
                    warehouse_service, tushare_service, ts_code, industry_name,
                    latest_trade_date, lookback_days
                )
                
                if not heat_indicators:
                    continue
                
                # 获取技术面指标
                technical_indicators = get_technical_indicators(
                    warehouse_service, ts_code, latest_trade_date, lookback_days
                )
                
                # 获取股票名称
                stock_info = industry_stocks[industry_stocks['ts_code'] == ts_code]
                if stock_info.empty:
                    continue
                name = stock_info.iloc[0]['name']
                
                scored_stocks.append({
                    'ts_code': ts_code,
                    'name': name,
                    'industry_heat': heat_indicators.get('industry_heat', 0),
                    'stock_heat_score': heat_indicators.get('stock_heat_score', 0),
                    'return_5d': heat_indicators.get('return_5d', 0),
                    'return_20d': heat_indicators.get('return_20d', 0),
                    'amount_ratio': heat_indicators.get('amount_ratio', 1),
                    'turnover_rate': heat_indicators.get('turnover_rate', 0),
                    'relative_strength_industry': heat_indicators.get('relative_strength_industry', 0),
                    'relative_strength_market': heat_indicators.get('relative_strength_market', 0),
                    'amount_share': heat_indicators.get('amount_share', 0),
                    'trend_strength': technical_indicators.get('trend_strength', 0),
                    'breakout_signal': technical_indicators.get('breakout_signal', 0),
                    'volume_price_match': technical_indicators.get('volume_price_match', 50),
                    'rsi': technical_indicators.get('rsi', 50),
                    'macd_signal': technical_indicators.get('macd_signal', 'none')
                })
            except Exception as e:
                logger.debug(f"处理股票 {ts_code} 失败: {e}")
                continue
        
        if not scored_stocks:
            logger.warning(f"[{industry_name}] 市场热度未获取到任何有效数据（可能缺少近期K线或热度数据），该行业综合龙头将仅按价值维度排序")
            return []
        
        # 4. 计算市场地位（涨幅排名、成交额排名）
        scored_stocks.sort(key=lambda x: x['return_5d'], reverse=True)
        for idx, stock in enumerate(scored_stocks):
            stock['return_rank'] = idx + 1
        
        scored_stocks.sort(key=lambda x: x['amount_share'], reverse=True)
        for idx, stock in enumerate(scored_stocks):
            stock['amount_rank'] = idx + 1
        
        # 5. 归一化并计算综合得分
        max_industry_heat = max([s['industry_heat'] for s in scored_stocks]) if scored_stocks else 1
        max_stock_heat = max([s['stock_heat_score'] for s in scored_stocks]) if scored_stocks else 1
        max_amount_share = max([s['amount_share'] for s in scored_stocks]) if scored_stocks else 1
        max_relative_strength = max([abs(s['relative_strength_industry']) for s in scored_stocks]) if scored_stocks else 1
        max_trend_strength = max([s['trend_strength'] for s in scored_stocks]) if scored_stocks else 1
        max_volume_price_match = max([s['volume_price_match'] for s in scored_stocks]) if scored_stocks else 1
        total_stocks = len(scored_stocks)
        
        for stock in scored_stocks:
            # 市场热度（35%）
            industry_heat_score = (stock['industry_heat'] / max_industry_heat) if max_industry_heat > 0 else 0
            stock_heat_score = (stock['stock_heat_score'] / max_stock_heat) if max_stock_heat > 0 else 0
            market_heat_score = industry_heat_score * 0.15 + stock_heat_score * 0.20
            
            # 资金关注度（25%）
            amount_share_score = (stock['amount_share'] / max_amount_share) if max_amount_share > 0 else 0
            money_attention_score = amount_share_score * 0.25
            
            # 技术面表现（20%）
            relative_strength_score = (abs(stock['relative_strength_industry']) / max_relative_strength) if max_relative_strength > 0 else 0
            trend_score = (stock['trend_strength'] / max_trend_strength) if max_trend_strength > 0 else 0
            volume_price_score = (stock['volume_price_match'] / max_volume_price_match) if max_volume_price_match > 0 else 0
            technical_score = relative_strength_score * 0.10 + (trend_score * 0.6 + volume_price_score * 0.4) * 0.10
            
            # 市场地位（20%）
            return_rank_score = 1 - ((stock['return_rank'] - 1) / total_stocks) if total_stocks > 0 else 0
            amount_rank_score = 1 - ((stock['amount_rank'] - 1) / total_stocks) if total_stocks > 0 else 0
            market_position_score = return_rank_score * 0.10 + amount_rank_score * 0.10
            
            # 综合得分（0-100）
            market_score = (
                market_heat_score * 35 +
                money_attention_score * 25 +
                technical_score * 20 +
                market_position_score * 20
            )
            
            stock['market_score'] = market_score
        
        # 6. 按综合得分排序
        scored_stocks.sort(key=lambda x: x.get('market_score', 0), reverse=True)
        
        # 7. 构造结果
        leaders = []
        for idx, stock in enumerate(scored_stocks[:top_n]):
            reason = f"""市场龙头（综合得分排名第{idx+1}位，得分{stock['market_score']:.1f}/100）

【市场热度】
- 行业热度: {stock['industry_heat']:.1f}/20
- 个股热度: {stock['stock_heat_score']:.1f}/100
- 近5日涨幅: {stock['return_5d']:+.2f}%
- 近20日涨幅: {stock['return_20d']:+.2f}%

【资金关注】
- 成交额: 放大{stock['amount_ratio']:.2f}倍
- 换手率: {stock['turnover_rate']:.2f}%
- 成交额占比: {stock['amount_share']:.2f}%（个股/行业）

【技术面】
- 相对强度: 相对行业{stock['relative_strength_industry']:+.2f}%，相对大盘{stock['relative_strength_market']:+.2f}%
- 趋势强度: {stock['trend_strength']:.1f}/100
- 突破信号: {'已突破' if stock['breakout_signal'] else '未突破'}
- 量价配合: {stock['volume_price_match']:.1f}/100

【市场地位】
- 涨幅排名: 第{stock['return_rank']}位
- 成交额排名: 第{stock['amount_rank']}位"""
            
            leaders.append({
                'ts_code': stock['ts_code'],
                'name': stock['name'],
                'leader_type': '行业龙头' if idx == 0 else '板块龙头',
                'reason': reason,
                'market_score': stock['market_score'],
                'return_5d': stock['return_5d'],
                'return_20d': stock['return_20d'],
                'amount_ratio': stock['amount_ratio'],
                'main_business': ''
            })
        
        logger.info(f"✅ 获取到 {len(leaders)} 只{industry_name}行业市场龙头股票")
        return leaders
        
    except Exception as e:
        logger.error(f"获取市场龙头失败: {e}", exc_info=True)
        return []


def get_industry_leaders_by_comprehensive(
    industry_name: str,
    top_n: int = 3,
    value_weight: float = 0.4,
    market_weight: float = 0.6
) -> List[Dict]:
    """
    综合价值+市场双维度识别龙头
    
    流程：
    1. 分别计算价值得分和市场得分
    2. 加权平均：综合得分 = 价值得分 × value_weight + 市场得分 × market_weight
    3. 按综合得分排序，取前top_n
    
    Args:
        industry_name: 行业名称
        top_n: 取前N只
        value_weight: 价值权重（默认0.4）
        market_weight: 市场权重（默认0.6）
        
    Returns:
        List[Dict]: 综合龙头列表
    """
    try:
        # 1. 分别计算价值得分和市场得分
        value_leaders = get_industry_leaders_by_value(industry_name, top_n * 2)  # 多取一些，确保有足够候选
        market_leaders = get_industry_leaders_by_market_heat(industry_name, top_n * 2)
        
        # 2. 合并数据，建立ts_code到得分的映射
        value_scores = {leader['ts_code']: leader.get('value_score', 0) for leader in value_leaders}
        market_scores = {leader['ts_code']: leader.get('market_score', 0) for leader in market_leaders}
        if not market_leaders:
            logger.info(f"[{industry_name}] 市场热度无数据，综合龙头仅按价值维度排序")
        
        # 3. 获取所有候选股票（价值或市场至少有一个得分）
        all_codes = set(value_scores.keys()) | set(market_scores.keys())
        
        if not all_codes:
            logger.warning(f"未找到任何候选股票")
            return []
        
        # 4. 计算综合得分
        comprehensive_stocks = []
        for ts_code in all_codes:
            value_score = value_scores.get(ts_code, 0)
            market_score = market_scores.get(ts_code, 0)
            
            # 如果某个维度得分为0，使用行业平均值填充（简化处理）
            if value_score == 0:
                avg_value = sum(value_scores.values()) / len(value_scores) if value_scores else 0
                value_score = avg_value
            if market_score == 0:
                avg_market = sum(market_scores.values()) / len(market_scores) if market_scores else 0
                market_score = avg_market
            
            comprehensive_score = value_score * value_weight + market_score * market_weight
            
            # 获取股票名称
            name = ''
            for leader in value_leaders + market_leaders:
                if leader['ts_code'] == ts_code:
                    name = leader['name']
                    break
            
            comprehensive_stocks.append({
                'ts_code': ts_code,
                'name': name,
                'value_score': value_score,
                'market_score': market_score,
                'comprehensive_score': comprehensive_score
            })
        
        # 5. 按综合得分排序
        comprehensive_stocks.sort(key=lambda x: x['comprehensive_score'], reverse=True)
        
        # 6. 构造结果
        leaders = []
        for idx, stock in enumerate(comprehensive_stocks[:top_n]):
            # 获取详细的reason（优先从value或market leaders中获取）
            reason = ""
            value_reason = ""
            market_reason = ""
            
            for leader in value_leaders:
                if leader['ts_code'] == stock['ts_code']:
                    value_reason = leader.get('reason', '')
                    break
            
            for leader in market_leaders:
                if leader['ts_code'] == stock['ts_code']:
                    market_reason = leader.get('reason', '')
                    break
            
            # 标记各维度数据是否缺失（用于展示）
            value_has_data = bool(value_reason.strip())
            market_has_data = bool(market_reason.strip())
            data_status_value = "完整" if value_has_data else "缺失（得分由行业均值填充）"
            data_status_market = "完整" if market_has_data else "缺失（得分由行业均值填充）"
            
            # 根据实际得分生成【特点】，避免低分仍写“优秀/强劲”
            vs, ms = stock['value_score'], stock['market_score']
            if vs >= 60 and ms >= 60:
                trait = "既有优秀的财务指标，又有强劲的市场表现，是价值与热度兼备的优质龙头"
            elif vs >= 60 and ms < 60:
                trait = "财务指标较好，但市场热度偏弱，偏价值型龙头"
            elif vs < 60 and ms >= 60:
                trait = "市场表现较强，但财务指标一般，偏热度型龙头"
            else:
                trait = "价值与市场得分均偏低，为行业相对排名靠前，建议结合基本面和走势综合判断"

            reason = f"""综合龙头（价值+市场双维度）

【数据说明】价值维度：{data_status_value}；市场维度：{data_status_market}

【价值维度】得分{stock['value_score']:.1f}/100
{value_reason[:200].strip() if value_reason else '（本维度数据缺失）'}

【市场维度】得分{stock['market_score']:.1f}/100
{market_reason[:200].strip() if market_reason else '（本维度数据缺失）'}

【综合得分】{stock['comprehensive_score']:.1f}/100（价值{value_weight*100:.0f}% + 市场{market_weight*100:.0f}%，行业排名第{idx+1}）

【特点】{trait}"""
            
            leaders.append({
                'ts_code': stock['ts_code'],
                'name': stock['name'],
                'leader_type': '行业龙头' if idx == 0 else '板块龙头',
                'reason': reason,
                'value_score': stock['value_score'],
                'market_score': stock['market_score'],
                'comprehensive_score': stock['comprehensive_score'],
                'main_business': ''
            })
        
        logger.info(f"✅ 获取到 {len(leaders)} 只{industry_name}行业综合龙头股票")
        return leaders
        
    except Exception as e:
        logger.error(f"获取综合龙头失败: {e}", exc_info=True)
        return []


def get_industry_leaders_by_comprehensive_score(industry_name: str, top_n: int = 3) -> List[Dict]:
    """
    综合评分法获取行业龙头（推荐方法）
    
    评分维度：
    - 市值（30%）：反映市场认可度和规模
    - 营收（25%）：反映业务规模
    - ROE（25%）：反映盈利能力
    - 营收增长率（20%）：反映成长性
    
    优点：综合考虑规模、盈利能力、成长性，更可靠
    
    Args:
        industry_name: 行业名称
        top_n: 取前N只
        
    Returns:
        List[Dict]: 龙头股票列表
    """
    try:
        tushare_service = TushareService()
        if not tushare_service.available:
            logger.warning("Tushare服务不可用")
            return []
        
        # 1. 获取行业所有股票
        stock_basic = tushare_service.pro.stock_basic(
            exchange='',
            list_status='L',
            fields='ts_code,symbol,name,industry'
        )
        
        industry_stocks = stock_basic[stock_basic['industry'] == industry_name]
        
        if industry_stocks.empty:
            return []
        
        logger.info(f"找到 {len(industry_stocks)} 只{industry_name}行业股票")
        
        # 2. 获取综合数据
        ts_codes = industry_stocks['ts_code'].tolist()
        scored_stocks = []
        
        # 获取最新报告期
        current_year = datetime.now().year
        current_month = datetime.now().month
        if current_month <= 3:
            report_date = f"{current_year-1}1231"
        elif current_month <= 6:
            report_date = f"{current_year}0331"
        elif current_month <= 9:
            report_date = f"{current_year}0630"
        else:
            report_date = f"{current_year}0930"
        
        batch_size = 50
        for i in range(0, len(ts_codes), batch_size):
            batch_codes = ts_codes[i:i+batch_size]
            codes_str = ','.join(batch_codes)
            
            try:
                # 获取市值数据
                daily_basic = tushare_service.pro.daily_basic(
                    ts_code=codes_str,
                    trade_date='',
                    fields='ts_code,trade_date,total_mv,pe_ttm,pb,dv_ratio'
                )

                # 更新估值数据到 fact_daily_fundamental
                if daily_basic is not None and not daily_basic.empty:
                    batch_trade_date = str(daily_basic.iloc[0]['trade_date']) if 'trade_date' in daily_basic.columns else None
                    if batch_trade_date:
                        update_fundamental_valuation(daily_basic, batch_trade_date)

                # 获取财务指标
                fina_indicator = tushare_service.pro.fina_indicator(
                    ts_code=codes_str,
                    period=report_date,
                    fields='ts_code,revenue,roe,yoy_sales'
                )
                
                # 合并数据
                if daily_basic is not None and not daily_basic.empty:
                    for _, row in daily_basic.iterrows():
                        ts_code = row['ts_code']
                        market_cap = row['total_mv'] / 10000 if pd.notna(row['total_mv']) else 0
                        
                        # 获取财务数据
                        fina_data = fina_indicator[fina_indicator['ts_code'] == ts_code] if fina_indicator is not None and not fina_indicator.empty else None
                        revenue = fina_data.iloc[0]['revenue'] / 100000000 if fina_data is not None and not fina_data.empty and pd.notna(fina_data.iloc[0]['revenue']) else 0
                        roe = fina_data.iloc[0]['roe'] if fina_data is not None and not fina_data.empty and pd.notna(fina_data.iloc[0]['roe']) else 0
                        revenue_growth = fina_data.iloc[0]['yoy_sales'] if fina_data is not None and not fina_data.empty and pd.notna(fina_data.iloc[0]['yoy_sales']) else 0
                        
                        # 获取股票名称
                        stock_info = industry_stocks[industry_stocks['ts_code'] == ts_code]
                        if not stock_info.empty:
                            name = stock_info.iloc[0]['name']
                            
                            scored_stocks.append({
                                'ts_code': ts_code,
                                'name': name,
                                'market_cap': market_cap,
                                'revenue': revenue,
                                'roe': roe,
                                'revenue_growth': revenue_growth
                            })
                
                time.sleep(0.3)
                
            except Exception as e:
                logger.warning(f"获取数据失败: {e}")
                continue
        
        if not scored_stocks:
            return []
        
        # 3. 归一化并计算综合得分
        max_cap = max([s['market_cap'] for s in scored_stocks]) if scored_stocks else 1
        max_revenue = max([s['revenue'] for s in scored_stocks]) if scored_stocks else 1
        max_roe = max([s['roe'] for s in scored_stocks if s['roe'] > 0]) if any(s['roe'] > 0 for s in scored_stocks) else 1
        max_growth = max([s['revenue_growth'] for s in scored_stocks if s['revenue_growth'] > 0]) if any(s['revenue_growth'] > 0 for s in scored_stocks) else 1
        
        for stock in scored_stocks:
            cap_score = (stock['market_cap'] / max_cap) if max_cap > 0 else 0
            revenue_score = (stock['revenue'] / max_revenue) if max_revenue > 0 else 0
            roe_score = (stock['roe'] / max_roe) if max_roe > 0 and stock['roe'] > 0 else 0
            growth_score = (stock['revenue_growth'] / max_growth) if max_growth > 0 and stock['revenue_growth'] > 0 else 0
            
            # 综合得分：市值30% + 营收25% + ROE25% + 增长率20%
            stock['comprehensive_score'] = (
                cap_score * 0.3 +
                revenue_score * 0.25 +
                roe_score * 0.25 +
                growth_score * 0.2
            )
        
        # 4. 按综合得分排序
        scored_stocks.sort(key=lambda x: x['comprehensive_score'], reverse=True)
        
        # 5. 构造结果
        leaders = []
        for idx, stock in enumerate(scored_stocks[:top_n]):
            leaders.append({
                'ts_code': stock['ts_code'],
                'name': stock['name'],
                'leader_type': '行业龙头' if idx == 0 else '板块龙头',
                'reason': f'综合评分排名第{idx+1}位（市值{stock["market_cap"]:.0f}亿，营收{stock["revenue"]:.0f}亿，ROE{stock["roe"]:.2f}%，营收增长{stock["revenue_growth"]:.2f}%）',
                'market_cap': stock['market_cap'],
                'main_business': ''
            })
        
        logger.info(f"✅ 获取到 {len(leaders)} 只{industry_name}行业龙头股票（综合评分法）")
        return leaders
        
    except Exception as e:
        logger.error(f"获取行业龙头失败: {e}", exc_info=True)
        return []


def auto_fetch_all_industry_leaders(method: str = 'market_cap', top_n: int = 3) -> Dict[str, List[Dict]]:
    """
    自动获取所有行业的龙头股票
    
    Args:
        method: 识别方法 ('market_cap' 市值 / 'revenue' 营收)
        top_n: 每个行业取前N只
        
    Returns:
        Dict[str, List[Dict]]: {行业名称: [龙头股票列表]}
    """
    try:
        tushare_service = TushareService()
        if not tushare_service.available:
            logger.error("Tushare服务不可用")
            return {}
        
        # 获取所有行业列表
        stock_basic = tushare_service.pro.stock_basic(
            exchange='',
            list_status='L',
            fields='ts_code,industry'
        )
        
        if stock_basic is None or stock_basic.empty:
            logger.error("未获取到股票列表")
            return {}
        
        # 统计所有行业
        industries = stock_basic['industry'].dropna().unique().tolist()
        logger.info(f"📊 找到 {len(industries)} 个行业")
        
        all_leaders = {}
        
        # 重置全局缓存（每个行业处理前重置）
        global _daily_basic_cache, _cache_trade_date
        _daily_basic_cache = None
        _cache_trade_date = None
        
        for idx, industry in enumerate(sorted(industries), 1):
            logger.info(f"\n[{idx}/{len(industries)}] 处理行业: {industry}")
            
            try:
                if method == 'market_cap':
                    leaders = get_industry_leaders_by_market_cap(industry, top_n)
                elif method == 'revenue':
                    leaders = get_industry_leaders_by_revenue(industry, top_n)
                else:
                    logger.warning(f"未知的方法: {method}")
                    continue
                
                if leaders:
                    all_leaders[industry] = leaders
                    logger.info(f"  ✅ 获取到 {len(leaders)} 只龙头股票")
                else:
                    logger.warning(f"  ⚠️ 未获取到龙头股票")
            except Exception as e:
                logger.error(f"  ❌ 处理行业 {industry} 时出错: {e}", exc_info=True)
                continue
            finally:
                # 处理完一个行业后，清理缓存（为下一个行业做准备）
                _daily_basic_cache = None
                _cache_trade_date = None
        
        total_stocks = sum(len(leaders) for leaders in all_leaders.values())
        logger.info(f"\n{'='*60}")
        logger.info(f"✅ 完成！共获取 {len(all_leaders)} 个行业的龙头数据，共 {total_stocks} 只股票")
        logger.info(f"{'='*60}")
        return all_leaders
        
    except Exception as e:
        logger.error(f"自动获取行业龙头失败: {e}", exc_info=True)
        return {}


def import_to_database(leaders_dict: Dict[str, List[Dict]], sector_mapping: Optional[Dict[str, str]] = None):
    """
    将获取的行业龙头数据导入数据库
    
    Args:
        leaders_dict: {行业名称: [龙头股票列表]}
        sector_mapping: 行业到板块代码的映射（可选）
    """
    ws = WarehouseService()
    session = ws.get_session()
    
    # 检查表是否存在
    try:
        check_table_query = text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'dim_industry_leader'
            );
        """)
        table_exists = session.execute(check_table_query).scalar()
        
        if not table_exists:
            logger.error("\n" + "="*60)
            logger.error("❌ 数据库表 dim_industry_leader 不存在！")
            logger.error("="*60)
            logger.error("\n📋 请先执行SQL迁移脚本创建表：")
            logger.error("\n方法1：使用psql命令行")
            logger.error("   psql -U your_user -d your_database -f migrations/create_industry_leaders_table.sql")
            logger.error("\n方法2：使用数据库管理工具（如pgAdmin、DBeaver）")
            logger.error("   执行文件：migrations/create_industry_leaders_table.sql")
            logger.error("\n方法3：使用Python脚本（需要先配置数据库连接）")
            logger.error("   python -c \"from data_warehouse.service.warehouse_service import WarehouseService; ws = WarehouseService(); session = ws.get_session(); session.execute(open('migrations/create_industry_leaders_table.sql').read()); session.commit()\"")
            logger.error("\n" + "="*60)
            session.close()
            return 0
    except Exception as e:
        logger.warning(f"⚠️ 检查表是否存在时出错: {e}，继续尝试导入...")
    
    try:
        imported_count = 0
        
        for industry, leaders in leaders_dict.items():
            # 获取板块代码（如果有映射）
            sector_code = sector_mapping.get(industry, '') if sector_mapping else ''
            sector_name = industry
            
            logger.info(f"📊 导入行业: {industry}, 龙头数量: {len(leaders)}")
            
            for leader in leaders:
                ts_code = leader.get('ts_code', '')
                name = leader.get('name', '')
                leader_type = leader.get('leader_type', '行业龙头')
                reason = leader.get('reason', '')
                market_cap = leader.get('market_cap', 0)
                main_business = leader.get('main_business', '')
                
                # 获取额外的财务指标（如果存在）
                roe = leader.get('roe')
                revenue = leader.get('revenue')
                
                # 验证股票是否存在
                stock = session.query(DimStock).filter(DimStock.ts_code == ts_code).first()
                if not stock:
                    logger.warning(f"  ⚠️ 股票不存在: {ts_code} ({name})，跳过")
                    continue
                
                # 存储到行业龙头表
                insert_query = text("""
                    INSERT INTO dim_industry_leader 
                    (ts_code, stock_name, industry, sector_code, sector_name, leader_type, leader_reason, main_business, market_cap, roe, source, is_active)
                    VALUES (:ts_code, :stock_name, :industry, :sector_code, :sector_name, :leader_type, :leader_reason, :main_business, :market_cap, :roe, 'api', TRUE)
                    ON CONFLICT (ts_code, industry) 
                    DO UPDATE SET
                        stock_name = EXCLUDED.stock_name,
                        sector_code = EXCLUDED.sector_code,
                        sector_name = EXCLUDED.sector_name,
                        leader_type = EXCLUDED.leader_type,
                        leader_reason = EXCLUDED.leader_reason,
                        main_business = EXCLUDED.main_business,
                        market_cap = EXCLUDED.market_cap,
                        roe = EXCLUDED.roe,
                        updated_at = CURRENT_TIMESTAMP,
                        is_active = TRUE
                """)
                
                try:
                    session.execute(insert_query, {
                        'ts_code': ts_code,
                        'stock_name': name,
                        'industry': industry,
                        'sector_code': sector_code,
                        'sector_name': sector_name,
                        'leader_type': leader_type,
                        'leader_reason': reason,
                        'main_business': main_business,
                        'market_cap': market_cap,
                        'roe': roe
                    })
                    
                    imported_count += 1
                    logger.debug(f"  ✅ 导入: {ts_code} ({name})")
                except Exception as e:
                    logger.error(f"  ❌ 导入失败 {ts_code} ({name}): {e}")
                    continue
        
        session.commit()
        logger.info(f"\n{'='*60}")
        logger.info(f"✅ 导入完成！")
        logger.info(f"   行业数: {len(leaders_dict)}")
        logger.info(f"   成功导入: {imported_count} 只龙头股票")
        logger.info(f"{'='*60}")
        return imported_count
        
    except Exception as e:
        session.rollback()
        logger.error(f"❌ 导入失败: {e}", exc_info=True)
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='自动获取行业龙头股票数据')
    parser.add_argument('--method', type=str, default='comprehensive', 
                        choices=['market_cap', 'revenue', 'comprehensive'],
                        help='识别方法：market_cap（市值）、revenue（营收）或 comprehensive（综合评分，推荐）')
    parser.add_argument('--top', type=int, default=3, help='每个行业取前N只（默认3）')
    parser.add_argument('--industry', type=str, help='只处理指定行业（不提供则处理所有行业）')
    parser.add_argument('--import-db', action='store_true', help='导入到数据库')
    parser.add_argument('--export', type=str, help='导出到JSON文件（文件路径）')
    
    args = parser.parse_args()
    
    if args.industry:
        # 只处理指定行业
        logger.info(f"📊 处理行业: {args.industry}")
        if args.method == 'market_cap':
            leaders = get_industry_leaders_by_market_cap(args.industry, args.top)
        elif args.method == 'revenue':
            leaders = get_industry_leaders_by_revenue(args.industry, args.top)
        else:  # comprehensive
            leaders = get_industry_leaders_by_comprehensive_score(args.industry, args.top)
        
        leaders_dict = {args.industry: leaders}
    else:
        # 处理所有行业
        logger.info(f"\n{'='*60}")
        logger.info(f"📊 自动获取所有行业龙头")
        logger.info(f"   方法: {args.method}")
        logger.info(f"   每个行业取前: {args.top} 只")
        logger.info(f"{'='*60}")
        
        if args.method == 'comprehensive':
            # 综合评分法需要单独处理每个行业
            logger.warning("⚠️ 综合评分法暂不支持批量处理所有行业，请使用 --industry 参数指定行业")
            logger.info("💡 建议：先使用 market_cap 或 revenue 方法批量获取，再人工审核")
            exit(1)
        
        leaders_dict = auto_fetch_all_industry_leaders(args.method, args.top)
        
        if not leaders_dict:
            logger.error("❌ 未获取到任何数据，请检查Tushare API配置和网络连接")
            exit(1)
    
    if not leaders_dict:
        logger.error("❌ 未获取到任何数据")
        exit(1)
    
    # 导出到JSON
    if args.export:
        import json
        export_data = {'industry_leaders': []}
        
        for industry, leaders in leaders_dict.items():
            export_data['industry_leaders'].append({
                'industry': industry,
                'sector_code': '',
                'sector_name': industry,
                'leaders': leaders
            })
        
        with open(args.export, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"✅ 已导出到文件: {args.export}")
    
    # 导入到数据库
    if args.import_db:
        logger.info(f"\n{'='*60}")
        logger.info(f"📥 开始导入数据到数据库")
        logger.info(f"{'='*60}")
        total_leaders = sum(len(leaders) for leaders in leaders_dict.values())
        logger.info(f"📊 准备导入: {len(leaders_dict)} 个行业，共 {total_leaders} 只龙头股票")
        imported_count = import_to_database(leaders_dict)
        if imported_count > 0:
            logger.info(f"\n✅ 成功导入 {imported_count} 只龙头股票到数据库")
        else:
            logger.warning(f"\n⚠️ 未导入任何数据，请检查错误信息")
    else:
        total_leaders = sum(len(leaders) for leaders in leaders_dict.values())
        logger.info(f"\n💡 提示：共获取 {len(leaders_dict)} 个行业，{total_leaders} 只龙头股票")
        logger.info("💡 使用 --import-db 参数可以将数据导入数据库")
