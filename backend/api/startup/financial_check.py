"""
已启动股票财务检测API
对已启动的股票进行财务健康检测（使用达尔文筛选器）
"""

from fastapi import APIRouter, HTTPException, Query, Body
from typing import Optional, List, Dict
from datetime import datetime, date
from pydantic import BaseModel
# 1. 获取股票基础数据
from data_warehouse.models.generated_models import FactDailyPriceQfq
from data_warehouse.models.orm_classes import DimStock
from data_warehouse.models.startup_candidate import FactStockStartupCandidate
from sqlalchemy import and_
import logging
import json

from data_warehouse.service.warehouse_service import WarehouseService
from backend.strategy.darwin_long_term import DarwinLongTermFilter
from backend.services.darwin.darwin_data_service import DarwinDataService
from backend.models.stock_data import StockData
from backend.utils.trade_date_utils import get_trade_date_or_latest

router = APIRouter()
logger = logging.getLogger(__name__)


class FinancialCheckRequest(BaseModel):
    ts_codes: List[str]
    trade_date: Optional[str] = None


@router.post("/financial-check")
async def check_started_stocks_financial(
    request: FinancialCheckRequest = Body(...)
) -> Dict:
    """
    对已启动的股票进行财务健康检测
    
    Args:
        request: 请求体，包含ts_codes和trade_date
    
    Returns:
        Dict: {
            "success": bool,
            "results": List[Dict],  # 每只股票的检测结果
            "summary": Dict  # 统计信息
        }
    """
    try:
        ts_codes = request.ts_codes
        trade_date = request.trade_date
        
        ws = WarehouseService()
        darwin_filter = DarwinLongTermFilter()
        darwin_data_service = DarwinDataService()
        
        # 获取交易日期
        if not trade_date:
            latest_date = get_trade_date_or_latest(ws, None)
            if latest_date:
                trade_date = latest_date.strftime('%Y-%m-%d')
            else:
                trade_date = datetime.now().strftime('%Y-%m-%d')
        
        logger.info(f"📊 开始对 {len(ts_codes)} 只已启动股票进行财务检测，日期：{trade_date}")
        
        
        
        session = ws.get_session()
        try:
            from sqlalchemy import func
            
            # 先尝试获取指定日期的股票数据
            stocks_query = session.query(
                DimStock.ts_code,
                DimStock.name,
                FactDailyPriceQfq.close,
                FactDailyPriceQfq.amount,
                FactDailyPriceQfq.vol,
                FactDailyPriceQfq.change_pct,
                FactDailyPriceQfq.trade_date
            ).join(
                FactDailyPriceQfq,
                DimStock.ts_code == FactDailyPriceQfq.ts_code
            ).filter(
                DimStock.ts_code.in_(ts_codes),
                FactDailyPriceQfq.trade_date == trade_date
            )
            
            stocks_data = stocks_query.all()
            found_codes = {row.ts_code for row in stocks_data}
            missing_codes = set(ts_codes) - found_codes
            
            # 如果某些股票没有指定日期的数据，查询它们的最新可用数据
            if missing_codes:
                logger.info(f"⚠️ {len(missing_codes)} 只股票在日期 {trade_date} 没有数据，查询最新可用数据")
                
                # 为每只缺失的股票查询最新可用数据
                for ts_code in missing_codes:
                    latest_query = session.query(
                        DimStock.ts_code,
                        DimStock.name,
                        FactDailyPriceQfq.close,
                        FactDailyPriceQfq.amount,
                        FactDailyPriceQfq.vol,
                        FactDailyPriceQfq.change_pct,
                        FactDailyPriceQfq.trade_date
                    ).join(
                        FactDailyPriceQfq,
                        DimStock.ts_code == FactDailyPriceQfq.ts_code
                    ).filter(
                        DimStock.ts_code == ts_code,
                        FactDailyPriceQfq.trade_date <= trade_date
                    ).order_by(
                        FactDailyPriceQfq.trade_date.desc()
                    ).limit(1).first()
                    
                    if latest_query:
                        stocks_data.append(latest_query)
                        logger.debug(f"✅ {ts_code} 使用最新数据日期: {latest_query.trade_date}")
            
            if not stocks_data:
                return {
                    "success": False,
                    "message": f"未找到日期 {trade_date} 及之前的股票数据",
                    "results": [],
                    "summary": {}
                }
            
            # 记录实际使用的日期范围
            actual_dates = {row.trade_date for row in stocks_data}
            if len(actual_dates) > 1:
                logger.info(f"📅 使用混合日期数据: 请求日期 {trade_date}，实际日期范围 {min(actual_dates)} 至 {max(actual_dates)}")
            
            # 转换交易日期字符串为日期对象（用于后续使用）
            check_date_obj = datetime.strptime(trade_date, '%Y-%m-%d').date()
            
            # 转换为StockData模型
            stock_data_list = []
            code_to_ts_code = {}  # 6位代码 -> ts_code 的映射
            ts_code_to_actual_date = {}  # ts_code -> 实际使用的日期
            
            for row in stocks_data:
                # 使用字典方式创建StockData，支持字段名映射
                ts_code = row.ts_code
                actual_date = row.trade_date  # 实际使用的日期
                ts_code_to_actual_date[ts_code] = actual_date
                
                # 提取6位数字代码
                clean_code = ts_code.replace('.SH', '').replace('.SZ', '').replace('.sz', '').replace('.sh', '').strip()
                code_to_ts_code[clean_code] = ts_code
                
                stock_dict = {
                    'code': clean_code,  # 使用6位数字代码
                    'name': row.name,
                    'close': float(row.close) if row.close else 0.0,
                    'amount': float(row.amount) if row.amount else 0.0,
                    'vol': float(row.vol) if row.vol else 0.0,
                    'change_pct': float(row.change_pct) if row.change_pct else 0.0,
                    'ts_code': ts_code,  # 保存原始 ts_code 到 extra
                    'actual_date': actual_date.isoformat()  # 保存实际使用的日期
                }
                stock = StockData.from_dict(stock_dict)
                # 确保 extra 中有 ts_code 和 actual_date
                if 'ts_code' not in stock.extra:
                    stock.extra['ts_code'] = ts_code
                if 'actual_date' not in stock.extra:
                    stock.extra['actual_date'] = actual_date.isoformat()
                stock_data_list.append(stock)
            
            # 2. 批量获取财务数据和行业信息
            # stock.code 已经是清理后的6位数字
            stock_codes = [s.code for s in stock_data_list]
            
            logger.debug(f"📊 准备获取财务数据，股票代码: {stock_codes[:5]}... (共{len(stock_codes)}只)")
            financial_data = darwin_data_service.get_financial_data_batch(stock_codes)
            industry_info = darwin_data_service.get_industry_info_batch(stock_codes)
            
            logger.info(f"✅ 获取到财务数据: {len(financial_data)} 只，行业信息: {len(industry_info)} 只")
            if len(financial_data) == 0:
                logger.warning(
                    f"⚠️ 未获取到财务数据（共{len(stock_codes)}只，示例: {stock_codes[:5]}）。"
                    f"缺 fact_daily_fundamental 表数据（ROE/PE/毛利/净利等），"
                    f"补表: 1) backfill_fundamental 回补 fact_fundamental；2) fill_daily_fundamental_from_fact 生成 fact_daily_fundamental"
                )
            
            # 将行业信息添加到财务数据中（get_industry_info_batch 返回 {code: industry_name}）
            for code, info in industry_info.items():
                industry_name = info.get('industry', info) if isinstance(info, dict) else info
                sector_name = info.get('sector', industry_name) if isinstance(info, dict) else industry_name
                industry_val = industry_name if industry_name else '未知'
                sector_val = sector_name if sector_name else '未知'
                if code in financial_data:
                    financial_data[code]['industry'] = industry_val
                    financial_data[code]['sector'] = sector_val
                else:
                    financial_data[code] = {
                        'industry': industry_val,
                        'sector': sector_val
                    }
            
            # 3. 批量财务检测（一次排雷，避免逐只调用）
            import pandas as pd
            rows = []
            for s in stock_data_list:
                d = s.to_dict()
                c = str(d.get('code', '')).replace('sh', '').replace('sz', '').replace('SH', '').replace('SZ', '').strip()
                fd = financial_data.get(c, {})
                d['industry'] = fd.get('industry', '') or fd.get('sector', '')
                d['sector'] = fd.get('sector', '') or fd.get('industry', '')
                rows.append(d)
            stock_df = pd.DataFrame(rows)

            # 预取 ST/退市 缓存（一次 Tushare 调用）
            def _to_ts(c):
                c = str(c).replace('sh', '').replace('sz', '').replace('SH', '').replace('SZ', '').strip()
                if not c:
                    return ''
                return code_to_ts_code.get(c, '') or (f"{c}.SH" if c.startswith('6') else f"{c}.SZ")
            all_ts = list({_to_ts(s.code) for s in stock_data_list if _to_ts(s.code)})
            st_cache = darwin_filter._fetch_st_delisting_cache(all_ts)

            # 一次性排雷，并返回失败原因
            healthy_stocks, failed_reasons_dict = darwin_filter._filter_financial_health(
                stock_df, financial_data,
                return_failed_reasons=True,
                st_delisting_cache=st_cache if st_cache else None
            )
            passed_codes = set()
            if not healthy_stocks.empty and 'code' in healthy_stocks.columns:

                def _norm(c):
                    if c is None or (isinstance(c, float) and pd.isna(c)):
                        return ''
                    return str(c).strip().replace('sh', '').replace('sz', '').replace('SH', '').replace('SZ', '')
                passed_codes = set(_norm(c) for c in healthy_stocks['code'].tolist() if _norm(c))

            results = []
            passed_count = 0
            failed_count = 0
            failed_reasons = {}
            for stock in stock_data_list:
                try:
                    clean_code = str(stock.code).strip().replace('sh', '').replace('sz', '').replace('SH', '').replace('SZ', '')
                    ts_code = code_to_ts_code.get(clean_code, stock.extra.get('ts_code', ''))
                    if not ts_code:
                        ts_code = f"{clean_code}.SH" if clean_code.startswith('6') else f"{clean_code}.SZ"
                    stock_fin_data = financial_data.get(clean_code, {})
                    is_passed = clean_code in passed_codes
                    failure_reasons_list = failed_reasons_dict.get(clean_code, []) if not is_passed else []
                    if not is_passed and not failure_reasons_list:
                        failure_reasons_list = ["财务数据不足"]
                    actual_date_for_result = ts_code_to_actual_date.get(ts_code, check_date_obj)
                    result = {
                        "ts_code": ts_code,
                        "code": stock.code,
                        "name": stock.name,
                        "is_passed": is_passed,
                        "failure_reasons": failure_reasons_list,
                        "industry": stock_fin_data.get('industry', '未知'),
                        "sector": stock_fin_data.get('sector', '未知'),
                        "actual_data_date": actual_date_for_result.isoformat() if actual_date_for_result != check_date_obj else None,
                    }
                    results.append(result)
                    if is_passed:
                        passed_count += 1
                    else:
                        failed_count += 1
                        for r in failure_reasons_list:
                            failed_reasons[r] = failed_reasons.get(r, 0) + 1
                except Exception as e:
                    logger.error(f"检测股票 {stock.code} 失败: {e}", exc_info=True)
                    # 获取 ts_code
                    clean_code = stock.code
                    ts_code_err = code_to_ts_code.get(clean_code, stock.extra.get('ts_code', ''))
                    if not ts_code_err:
                        if clean_code.startswith('6'):
                            ts_code_err = f"{clean_code}.SH"
                        elif clean_code.startswith('0') or clean_code.startswith('3'):
                            ts_code_err = f"{clean_code}.SZ"
                        else:
                            ts_code_err = clean_code
                    
                    # 获取该股票实际使用的日期
                    actual_date_for_err = ts_code_to_actual_date.get(ts_code_err, check_date_obj)
                    
                    results.append({
                        "ts_code": ts_code_err,  # 使用完整的 ts_code 格式
                        "code": stock.code,  # 保留6位数字代码
                        "name": stock.name,
                        "is_passed": False,
                        "failure_reasons": ["检测异常，请稍后重试"],
                        "industry": "未知",
                        "sector": "未知",
                        "actual_data_date": actual_date_for_err.isoformat() if actual_date_for_err != check_date_obj else None  # 如果使用了最新数据，记录实际日期
                    })
                    failed_count += 1
            
            summary = {
                "total": len(ts_codes),
                "passed": passed_count,
                "failed": failed_count,
                "pass_rate": round(passed_count / len(ts_codes) * 100, 2) if ts_codes else 0,
                "failed_reasons": failed_reasons
            }
            
            logger.info(f"✅ 财务检测完成: 通过 {passed_count}/{len(ts_codes)} 只，通过率 {summary['pass_rate']}%")
            
            # 4. 保存财务检测结果到数据库
            # check_date_obj 已在前面定义，这里直接使用
            saved_count = 0
            
            try:
                for result in results:
                    ts_code = result.get('ts_code')
                    if not ts_code:
                        # 如果没有 ts_code，尝试从 code 字段获取
                        code = result.get('code')
                        if code:
                            if code.startswith('6'):
                                ts_code = f"{code}.SH"
                            elif code.startswith('0') or code.startswith('3'):
                                ts_code = f"{code}.SZ"
                            else:
                                ts_code = code
                        else:
                            continue
                    
                    # 确保 ts_code 格式正确（如果只有6位数字，需要添加后缀）
                    if '.' not in ts_code:
                        if ts_code.startswith('6'):
                            ts_code = f"{ts_code}.SH"
                        elif ts_code.startswith('0') or ts_code.startswith('3'):
                            ts_code = f"{ts_code}.SZ"
                    
                    # 获取该股票实际使用的日期（如果使用了最新数据）
                    actual_date = ts_code_to_actual_date.get(ts_code, check_date_obj)
                    
                    # ✅ 修复：查找该股票的最新启动记录（按trade_date降序），而不是按save_date查找
                    # 这样可以确保财务检测结果保存在正确的记录上，即使使用了不同日期的数据
                    # ✅ 只查找"启动确认"或"完全启动"状态的记录
                    candidate = session.query(FactStockStartupCandidate).filter(
                        FactStockStartupCandidate.ts_code == ts_code,
                        FactStockStartupCandidate.stage.in_(['started', 'confirmed'])
                    ).order_by(
                        FactStockStartupCandidate.trade_date.desc()
                    ).first()
                    
                    if not candidate:
                        # ✅ 如果找不到已启动的记录，跳过该股票，不创建新记录
                        logger.warning(f"⚠️ {ts_code} 未找到已启动记录（stage='started'或'confirmed'），跳过财务检测结果保存")
                        continue
                    
                    # 使用找到的记录日期
                    save_date = candidate.trade_date
                    
                    # ✅ 验证记录状态：确保是已启动状态
                    if candidate.stage not in ['started', 'confirmed']:
                        logger.warning(f"⚠️ {ts_code} 记录状态为 {candidate.stage}，不是已启动状态，跳过财务检测结果保存")
                        continue
                    
                    # 保存财务检测结果（记录实际使用的日期）
                    financial_check_data = {
                        "is_passed": result.get('is_passed', False),
                        "failure_reasons": result.get('failure_reasons', []),
                        "industry": result.get('industry', '未知'),
                        "sector": result.get('sector', '未知'),
                        "check_date": trade_date,  # 请求的检测日期
                        "actual_data_date": actual_date.isoformat()  # 实际使用的数据日期
                    }
                    
                    candidate.financial_check_result = financial_check_data
                    candidate.last_financial_check_date = save_date  # 使用记录的实际日期
                    
                    logger.debug(f"💾 保存财务检测结果: {ts_code}, trade_date={save_date}, is_passed={result.get('is_passed')}")
                    saved_count += 1
                
                # 提交事务
                session.commit()
                logger.info(f"💾 已保存 {saved_count} 只股票的财务检测结果到数据库")
                
            except Exception as e:
                session.rollback()
                logger.error(f"❌ 保存财务检测结果失败: {e}", exc_info=True)
                # 即使保存失败，也返回检测结果
            
            return {
                "success": True,
                "results": results,
                "summary": summary,
                "saved_count": saved_count
            }
            
        finally:
            session.close()
            
    except Exception as e:
        logger.error(f"财务检测失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="财务检测失败，请稍后重试")


@router.post("/financial-check/auto")
async def auto_check_all_started_stocks(
    trade_date: Optional[str] = Query(None, description="检测日期，默认为最新交易日"),
    days: int = Query(30, ge=1, le=365, description="检测最近N个交易日内的已启动股票（1-365）")
) -> Dict:
    """
    自动检测所有已启动但未检测的股票
    
    这个端点会自动查找所有已启动（stage='started'或'confirmed'）但未进行财务检测的股票，
    并对它们进行批量财务检测。
    
    Args:
        trade_date: 检测日期，默认为最新交易日
        days: 检测最近N个交易日内的已启动股票
    
    Returns:
        Dict: {
            "success": bool,
            "message": str,
            "checked_count": int,  # 本次检测的股票数量
            "results": List[Dict],  # 检测结果
            "summary": Dict  # 统计信息
        }
    """
    try:
        # 提前验证 trade_date 格式，避免后续 strptime 报 500
        if trade_date:
            try:
                datetime.strptime(trade_date, '%Y-%m-%d')
            except ValueError:
                raise HTTPException(status_code=400, detail="trade_date 格式错误，应为 YYYY-MM-DD")

        ws = WarehouseService()
        session = ws.get_session()
        try:
            # 获取交易日期
            if not trade_date:
                latest_date = get_trade_date_or_latest(ws, None)
                if latest_date:
                    trade_date = latest_date.strftime('%Y-%m-%d')
                else:
                    trade_date = datetime.now().strftime('%Y-%m-%d')

            logger.info(f"🔍 开始自动检测已启动但未检测的股票，日期：{trade_date}")

            # 计算日期范围
            from datetime import timedelta
            end_date = datetime.strptime(trade_date, '%Y-%m-%d').date()
            start_date = end_date - timedelta(days=days + 10)  # 多查询几天，确保覆盖

            # 查找所有已启动但未检测的股票
            from sqlalchemy import func

            subq = session.query(
                FactStockStartupCandidate.ts_code,
                func.max(FactStockStartupCandidate.trade_date).label('max_date')
            ).filter(
                FactStockStartupCandidate.trade_date >= start_date,
                FactStockStartupCandidate.trade_date <= end_date,
                FactStockStartupCandidate.stage.in_(['started', 'confirmed'])
            ).group_by(FactStockStartupCandidate.ts_code).subquery()

            unchecked_query = session.query(FactStockStartupCandidate.ts_code).join(
                subq,
                and_(
                    FactStockStartupCandidate.ts_code == subq.c.ts_code,
                    FactStockStartupCandidate.trade_date == subq.c.max_date
                )
            ).filter(
                FactStockStartupCandidate.stage.in_(['started', 'confirmed']),
                (FactStockStartupCandidate.financial_check_result.is_(None)) |
                (FactStockStartupCandidate.last_financial_check_date.is_(None))
            )
            candidate_tuples = unchecked_query.distinct().all()
        finally:
            session.close()

        if not candidate_tuples:
            return {
                "success": True,
                "message": "没有需要检测的股票（所有已启动股票都已检测过）",
                "checked_count": 0,
                "results": [],
                "summary": {}
            }

        # 提取ts_code列表
        ts_codes = [t[0] for t in candidate_tuples]
        logger.info(f"📊 找到 {len(ts_codes)} 只已启动但未检测的股票")

        # 调用财务检测API
        request = FinancialCheckRequest(ts_codes=ts_codes, trade_date=trade_date)
        result = await check_started_stocks_financial(request)

        return {
            "success": result.get("success", True),
            "message": f"自动检测完成，共检测 {len(ts_codes)} 只股票",
            "checked_count": len(ts_codes),
            "results": result.get("results", []),
            "summary": result.get("summary", {})
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"自动财务检测失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="自动财务检测失败")
