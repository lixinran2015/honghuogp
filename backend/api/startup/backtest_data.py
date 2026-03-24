"""
回测数据API - 获取已启动股票的历史数据用于回测
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional, List, Dict
from datetime import datetime, timedelta, date
import logging

from data_warehouse.service.warehouse_service import WarehouseService
from data_warehouse.models.startup_candidate import FactStockStartupCandidate
from data_warehouse.models.generated_models import FactDailyPriceQfq
from data_warehouse.models.orm_classes import DimStock
from sqlalchemy import and_, func, or_
from backend.services.stock.trade_plan_utils import compute_trade_plan

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/backtest-signals")
async def get_backtest_signals(
    start_date: Optional[str] = Query(None, description="回测开始日期，格式YYYY-MM-DD，默认1年前"),
    end_date: Optional[str] = Query(None, description="回测结束日期，格式YYYY-MM-DD，默认今天"),
    min_score: int = Query(40, description="最低得分（默认40，包含启动确认阶段）"),
    stage_filter: Optional[str] = Query(None, description="阶段过滤：confirmed(启动确认), started(完全启动), 不传则包含两者")
) -> Dict:
    """
    获取回测所需的已启动股票信号数据
    
    返回1年前至今（或指定日期范围）所有符合"已启动"条件的股票信息
    用于回测系统使用
    
    Returns:
        Dict: {
            'success': bool,
            'count': int,  # 信号总数
            'signals': List[Dict],  # 信号列表
            'period': {
                'start_date': str,
                'end_date': str
            }
        }
    """
    try:
        ws = WarehouseService()
        session = ws.get_session()
        
        try:
            # 确定日期范围
            if end_date is None:
                end_date_obj = date.today()
            else:
                end_date_obj = datetime.strptime(end_date, '%Y-%m-%d').date()
            
            if start_date is None:
                # 默认回测最近1年
                start_date_obj = end_date_obj - timedelta(days=365)
            else:
                start_date_obj = datetime.strptime(start_date, '%Y-%m-%d').date()
            
            logger.info(f"查询回测信号：{start_date_obj} 至 {end_date_obj}, min_score={min_score}, stage_filter={stage_filter}")
            
            # 构建查询
            query = session.query(
                FactStockStartupCandidate,
                DimStock.name.label('stock_name')
            ).join(
                DimStock,
                FactStockStartupCandidate.ts_code == DimStock.ts_code,
                isouter=True
            ).filter(
                FactStockStartupCandidate.trade_date >= start_date_obj,
                FactStockStartupCandidate.trade_date <= end_date_obj,
                FactStockStartupCandidate.score >= min_score,
                # 只查询已启动的股票（confirmed 或 started）
                or_(
                    FactStockStartupCandidate.stage == 'confirmed',
                    FactStockStartupCandidate.stage == 'started'
                ),
                # 排除已退出的股票
                or_(
                    FactStockStartupCandidate.is_exited == False,
                    FactStockStartupCandidate.is_exited.is_(None)
                )
            )
            
            # 可选的阶段过滤
            if stage_filter:
                if stage_filter == 'confirmed':
                    query = query.filter(FactStockStartupCandidate.stage == 'confirmed')
                elif stage_filter == 'started':
                    query = query.filter(FactStockStartupCandidate.stage == 'started')
                else:
                    raise HTTPException(status_code=400, detail=f"无效的stage_filter参数：{stage_filter}，可选值：confirmed, started")
            
            # 按日期排序
            candidates = query.order_by(
                FactStockStartupCandidate.trade_date.asc(),
                FactStockStartupCandidate.ts_code.asc()
            ).all()
            
            # 构建返回数据
            signals = []
            for candidate, stock_name in candidates:
                # 以入选日收盘价作为统一的参考买入价（不额外查压力位，走默认比例）
                entry_price = None
                try:
                    # 优先用 latest_price，如果没有则用 fact_daily_price_qfq.close
                    if getattr(candidate, "latest_price", None):
                        entry_price = float(candidate.latest_price)
                    else:
                        price_row = session.query(FactDailyPriceQfq.close).filter(
                            FactDailyPriceQfq.ts_code == candidate.ts_code,
                            FactDailyPriceQfq.trade_date == candidate.trade_date,
                        ).first()
                        if price_row and price_row[0]:
                            entry_price = float(price_row[0])
                except Exception:
                    entry_price = None

                trade_plan = compute_trade_plan(entry_price, stock_data=None) if entry_price and entry_price > 0 else None

                signals.append({
                    'signal_date': candidate.trade_date.isoformat(),  # 入选日期（信号日期）
                    'ts_code': candidate.ts_code,
                    'stock_name': stock_name or candidate.ts_code,
                    'entry_score': candidate.score,
                    'entry_stage': candidate.stage,
                    'risk_passed': candidate.risk_passed,
                    'assist_count': candidate.assist_count or 0,
                    'passed_signals': candidate.passed_signals or [],
                    'risk_reasons': candidate.risk_reasons or [],
                    'core_passed': candidate.core_passed,
                    'basic_passed': candidate.basic_passed,
                    'is_started': candidate.is_started,
                    'golden_cross_date': candidate.golden_cross_date.isoformat() if candidate.golden_cross_date else None,
                    'trade_plan': trade_plan,
                })
            
            logger.info(f"✅ 查询完成：找到 {len(signals)} 个回测信号")
            
            return {
                'success': True,
                'count': len(signals),
                'signals': signals,
                'period': {
                    'start_date': start_date_obj.isoformat(),
                    'end_date': end_date_obj.isoformat()
                },
                'filters': {
                    'min_score': min_score,
                    'stage_filter': stage_filter or 'all'
                }
            }
            
        except ValueError as e:
            logger.error(f"日期格式错误: {e}", exc_info=True)
            raise HTTPException(status_code=400, detail="日期格式错误，应为 YYYY-MM-DD")
        except Exception as e:
            logger.error(f"查询回测信号失败: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="查询失败，请稍后重试")
        finally:
            session.close()
            
    except Exception as e:
        logger.error(f"查询回测信号失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="查询失败，请稍后重试")


@router.get("/backtest-signals/stats")
async def get_backtest_signals_stats(
    start_date: Optional[str] = Query(None, description="回测开始日期，格式YYYY-MM-DD，默认1年前"),
    end_date: Optional[str] = Query(None, description="回测结束日期，格式YYYY-MM-DD，默认今天"),
    min_score: int = Query(40, description="最低得分（默认40，包含启动确认阶段）")
) -> Dict:
    """
    获取回测信号的统计信息
    
    Returns:
        Dict: {
            'success': bool,
            'total_count': int,
            'by_stage': Dict,  # 按阶段分组统计
            'by_score_range': Dict,  # 按得分区间分组统计
            'by_month': List[Dict],  # 按月分组统计
            'period': {
                'start_date': str,
                'end_date': str
            }
        }
    """
    try:
        ws = WarehouseService()
        session = ws.get_session()
        
        try:
            # 确定日期范围
            if end_date is None:
                end_date_obj = date.today()
            else:
                end_date_obj = datetime.strptime(end_date, '%Y-%m-%d').date()
            
            if start_date is None:
                start_date_obj = end_date_obj - timedelta(days=365)
            else:
                start_date_obj = datetime.strptime(start_date, '%Y-%m-%d').date()
            
            # 查询所有符合条件的记录
            query = session.query(
                FactStockStartupCandidate.stage,
                FactStockStartupCandidate.score,
                FactStockStartupCandidate.trade_date
            ).filter(
                FactStockStartupCandidate.trade_date >= start_date_obj,
                FactStockStartupCandidate.trade_date <= end_date_obj,
                FactStockStartupCandidate.score >= min_score,
                or_(
                    FactStockStartupCandidate.stage == 'confirmed',
                    FactStockStartupCandidate.stage == 'started'
                ),
                or_(
                    FactStockStartupCandidate.is_exited == False,
                    FactStockStartupCandidate.is_exited.is_(None)
                )
            )
            
            candidates = query.all()
            
            # 统计
            total_count = len(candidates)
            by_stage = {}
            by_score_range = {
                '60-69': 0,
                '70-99': 0,
                '100+': 0
            }
            by_month = {}
            
            for stage, score, trade_date in candidates:
                # 按阶段统计
                by_stage[stage] = by_stage.get(stage, 0) + 1
                
                # 按得分区间统计
                if score < 70:
                    by_score_range['60-69'] += 1
                elif score < 100:
                    by_score_range['70-99'] += 1
                else:
                    by_score_range['100+'] += 1
                
                # 按月统计
                month_key = trade_date.strftime('%Y-%m')
                by_month[month_key] = by_month.get(month_key, 0) + 1
            
            # 转换为列表格式（按月排序）
            by_month_list = [
                {'month': month, 'count': count}
                for month, count in sorted(by_month.items())
            ]
            
            return {
                'success': True,
                'total_count': total_count,
                'by_stage': by_stage,
                'by_score_range': by_score_range,
                'by_month': by_month_list,
                'period': {
                    'start_date': start_date_obj.isoformat(),
                    'end_date': end_date_obj.isoformat()
                }
            }
            
        except ValueError as e:
            logger.error(f"日期格式错误: {e}", exc_info=True)
            raise HTTPException(status_code=400, detail="日期格式错误，应为 YYYY-MM-DD")
        except Exception as e:
            logger.error(f"查询统计信息失败: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="查询失败，请稍后重试")
        finally:
            session.close()
            
    except Exception as e:
        logger.error(f"查询统计信息失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="查询失败，请稍后重试")

