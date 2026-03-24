"""
股票启动API - 扫描
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from datetime import datetime, time
import json
import logging
import math
import numpy as np
import pandas as pd

from backend.services.stock.stock_startup_filter import StockStartupFilter
from data_warehouse.service.warehouse_service import WarehouseService
from data_warehouse.models.startup_candidate import FactStockStartupCandidate
from backend.utils.trade_date_utils import is_trade_date, get_trade_date_or_latest
from backend.services.recommendation.stock_recommender import StockRecommendationService
from .common import get_universe_stocks

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/scan")
async def scan_startup_stocks(
    universe: str = Query("mainboard", description="股票池类型：mainboard(主板)、base(基础池)、all(全市场)"),
    trade_date: Optional[str] = Query(None, description="交易日期，格式YYYY-MM-DD，默认最新"),
    min_score: int = Query(60, description="最低启动得分，默认60分")
):
    """
    扫描启动股票
    
    从指定股票池中筛选出满足启动条件的股票
    
    如果当天是交易日且已过15:00（收盘后），优先使用数据库中的数据
    """
    try:
        ws = WarehouseService()
        
        # 获取股票池列表
        stock_codes = await get_universe_stocks(universe)
        
        if not stock_codes:
            return {
                'success': True,
                'data': [],
                'summary': {
                    'total_scanned': 0,
                    'startup_count': 0,
                    'avg_score': 0
                }
            }
        
        # 确定目标日期
        _now = datetime.now()
        today = _now.date()
        current_time = _now.time()
        
        # 如果未指定交易日期，检查是否应该优先使用数据库数据
        prefer_db_data = False
        if not trade_date:
            # 检查今天是否是交易日
            if is_trade_date(ws, today):
                # 检查当前时间是否 >= 15:00（收盘后）
                if current_time >= time(15, 0):
                    prefer_db_data = True
                    # 设置 trade_date 为今天，这样扫描时会优先使用数据库中的价格数据
                    trade_date = today.strftime('%Y-%m-%d')
                    logger.info(f"✅ 今天是交易日且已过15:00，扫描时将优先使用数据库中的数据")
        
        # 执行扫描（15点后会优先使用数据库中的价格数据）
        startup_filter = StockStartupFilter(warehouse_service=ws)
        
        logger.info(f"开始扫描 {len(stock_codes)} 只股票...")
        
        # 批量筛选（会自动保存所有得分≥20的股票到数据库）
        # 如果 trade_date 已设置，扫描时会优先使用数据库中的价格数据
        result_df = startup_filter.batch_filter_startups(stock_codes, trade_date)
        
        # 过滤得分（检查DataFrame是否为空）
        if len(result_df) > 0 and min_score > 0:
            result_df = result_df[result_df['score'] >= min_score]
        
        # 转换为字典列表，并清理 nan 值（JSON 不支持 nan）
        # 使用 pandas 的 to_json 方法，它会自动将 nan 转换为 null（JSON 兼容）
        if len(result_df) > 0:
            # pandas to_json 会自动处理 nan -> null，然后解析回 Python 字典
            json_str = result_df.to_json(orient='records', date_format='iso', default_handler=str)
            startups = json.loads(json_str)
            
            # 额外处理：确保 numpy 类型转换为 Python 原生类型
            from .common import to_native
            startups = [to_native(item) for item in startups]
        else:
            startups = []
        
        # 从数据库查询实际保存的候选股票数量（更准确）
        session = ws.get_session()
        try:
            if trade_date:
                target_date = datetime.strptime(trade_date, '%Y-%m-%d').date()
            else:
                latest_trade_date = get_trade_date_or_latest(ws, None)
                target_date = latest_trade_date if latest_trade_date else today
            
            # 统计今日新增的候选股票（得分≥20）
            saved_count = session.query(FactStockStartupCandidate).filter(
                FactStockStartupCandidate.trade_date == target_date,
                FactStockStartupCandidate.score >= 20
            ).count()
            
            # 统计各阶段数量
            golden_cross_count = session.query(FactStockStartupCandidate).filter(
                FactStockStartupCandidate.trade_date == target_date,
                FactStockStartupCandidate.stage == 'golden_cross'
            ).count()
            
            confirmed_count = session.query(FactStockStartupCandidate).filter(
                FactStockStartupCandidate.trade_date == target_date,
                FactStockStartupCandidate.stage == 'confirmed'
            ).count()
            
            started_count = session.query(FactStockStartupCandidate).filter(
                FactStockStartupCandidate.trade_date == target_date,
                FactStockStartupCandidate.stage == 'started'
            ).count()
            
        finally:
            session.close()
        
        # 统计
        summary = {
            'total_scanned': len(stock_codes),
            'saved_count': saved_count,
            'golden_cross_count': golden_cross_count,
            'confirmed_count': confirmed_count,
            'started_count': started_count,
            'returned_count': len(startups),
            'scan_date': trade_date or datetime.now().strftime('%Y-%m-%d'),
            'prefer_db_data': prefer_db_data  # 标记是否优先使用数据库数据
        }
        
        logger.info(f"扫描完成: 保存{saved_count}只（金叉{golden_cross_count}，确认{confirmed_count}，完全启动{started_count}）/ 扫描{summary['total_scanned']}只")
        
        # 自动处理推荐：将完全启动的股票加入推荐池
        recommended_count = 0
        try:
            recommender = StockRecommendationService(ws)
            recommend_result = recommender.process_started_stocks(trade_date)
            
            if recommend_result['success']:
                recommended_count = recommend_result['added_count']
                logger.info(f"✅ 推荐处理完成: 新增{recommended_count}只到推荐池")
        except Exception as e:
            logger.warning(f"推荐处理失败: {e}")
        
        summary['recommended_count'] = recommended_count
        
        return {
            'success': True,
            'data': startups,
            'summary': summary
        }
        
    except Exception as e:
        logger.error(f"扫描启动股票失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="扫描失败，请稍后重试")

