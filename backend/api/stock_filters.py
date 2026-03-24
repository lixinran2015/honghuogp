"""
股票筛选器API接口
提供四个筛选器的统一接口
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Dict, Optional
import logging
from datetime import datetime
import pandas as pd
import asyncio
from concurrent.futures import ThreadPoolExecutor

from backend.services.market_data_service import MarketDataService
from backend.services.stock.stock_filter_service import StockFilterService
from backend.services.data.financial_data_fetcher import FinancialDataFetcher

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/stock-filters", tags=["stock-filters"])

executor = ThreadPoolExecutor(max_workers=2)


@router.get("/all")
async def get_all_filters(
    limit: int = Query(10, description="每种策略返回数量限制"),
    date: Optional[str] = Query(None, description="日期，格式：YYYY-MM-DD，默认今天")
) -> Dict:
    """
    获取所有策略筛选结果
    
    Returns:
        Dict: {
            "limit_up": Dict,  # 短线强势股（打板策略）
            "reversal": Dict,  # 短线低吸股（反转策略）
            "pullback": Dict,  # 波段低吸
            "darwin": Dict,    # 达尔文长期
            "summary": Dict    # 汇总信息
        }
    """
    try:
        logger.info(f"📥 收到所有策略筛选请求: limit={limit}, date={date}")
        
        # 初始化服务
        market_service = MarketDataService()
        filter_service = StockFilterService()
        financial_fetcher = FinancialDataFetcher()
        
        # 异步获取股票数据（使用统一模型）
        loop = asyncio.get_running_loop()
        stock_data_list = []
        
        try:
            stock_data_list = await asyncio.wait_for(
                loop.run_in_executor(executor, market_service.get_realtime_stocks_as_models, False),
                timeout=60.0
            )
        except asyncio.TimeoutError:
            logger.warning("⚠️ 获取股票数据超时")
            raise HTTPException(status_code=500, detail="获取股票数据超时")
        
        if not stock_data_list:
            raise HTTPException(status_code=500, detail="无法获取股票数据")
        
        # 获取财务数据（可选）
        financial_data = None
        try:
            # 简化处理：只获取部分股票的财务数据
            sample_codes = [stock.code for stock in stock_data_list[:100]]
            financial_data = {}
            for code in sample_codes[:50]:  # 限制数量，避免超时
                try:
                    fin_info = financial_fetcher.fetch_financial_data(code)
                    if fin_info:
                        financial_data[code] = fin_info
                except Exception as e:
                    logger.debug(f"获取股票 {code} 的财务数据失败: {e}")
                    continue
        except Exception as e:
            logger.warning(f"获取财务数据失败: {e}")
        
        history_codes = [stock.code for stock in stock_data_list[:200]]
        historical_data = market_service.get_historical_kline(history_codes, days=120, max_codes=80)
        
        # 执行所有策略筛选
        results = filter_service.filter_all_strategies(
            stock_data=stock_data_list,
            historical_data=historical_data,
            financial_data=financial_data,
            limit=limit
        )
        
        # 转换为字典格式（兼容前端）
        from backend.models.strategy_result import StrategyResult
        return_dict = {}
        for key, result in results.items():
            if isinstance(result, StrategyResult):
                return_dict[key] = result.to_dict()
            else:
                return_dict[key] = result
        
        return return_dict
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ 获取所有策略筛选结果失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="获取筛选结果失败，请稍后重试")


@router.get("/limit-up")
async def get_limit_up_candidates(
    limit: int = Query(10, description="返回数量限制"),
    date: Optional[str] = Query(None, description="日期，格式：YYYY-MM-DD，默认今天")
) -> Dict:
    """
    获取短线强势股（打板策略）候选
    
    Returns:
        Dict: {
            "candidates": List[Dict],
            "warning": Optional[str],
            "filter_steps": Dict
        }
    """
    try:
        logger.info(f"📥 收到打板策略筛选请求: limit={limit}")
        
        market_service = MarketDataService()
        filter_service = StockFilterService()
        
        loop = asyncio.get_running_loop()
        stock_data_list = []
        
        try:
            stock_data_list = await asyncio.wait_for(
                loop.run_in_executor(executor, market_service.get_realtime_stocks_as_models, False),
                timeout=60.0
            )
        except asyncio.TimeoutError:
            raise HTTPException(status_code=500, detail="获取股票数据超时")
        
        if not stock_data_list:
            raise HTTPException(status_code=500, detail="无法获取股票数据")
        
        result = filter_service.filter_limit_up_stocks(
            stock_data_list,
            limit=limit
        )
        
        # 转换为字典格式
        from backend.models.strategy_result import StrategyResult
        if isinstance(result, StrategyResult):
            result_dict = result.to_dict()
        else:
            result_dict = result
        
        # 添加策略描述信息
        return {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "candidates": result_dict.get("candidates", []),
            "warning": result_dict.get("warning"),
            "filter_steps": result_dict.get("filter_steps", {}),
            "strategy_info": {
                "name": "打板策略",
                "description": "识别龙头、涨停捕捉、强趋势标的",
                "type": "attack"
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ 打板策略筛选失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="筛选失败，请稍后重试")


@router.get("/reversal")
async def get_reversal_candidates(
    limit: int = Query(10, description="返回数量限制"),
    date: Optional[str] = Query(None, description="日期，格式：YYYY-MM-DD，默认今天")
) -> Dict:
    """
    获取短线低吸股（反转策略）候选
    
    Returns:
        Dict: {
            "candidates": List[Dict],
            "warning": Optional[str],
            "filter_steps": Dict
        }
    """
    try:
        logger.info(f"📥 收到反转策略筛选请求: limit={limit}")
        
        market_service = MarketDataService()
        filter_service = StockFilterService()
        
        loop = asyncio.get_running_loop()
        stock_data_list = []
        
        try:
            stock_data_list = await asyncio.wait_for(
                loop.run_in_executor(executor, market_service.get_realtime_stocks_as_models, False),
                timeout=60.0
            )
        except asyncio.TimeoutError:
            raise HTTPException(status_code=500, detail="获取股票数据超时")
        
        if not stock_data_list:
            raise HTTPException(status_code=500, detail="无法获取股票数据")
        
        history_codes = [stock.code for stock in stock_data_list[:200]]
        historical_data = market_service.get_historical_kline(history_codes, days=120, max_codes=80)
        
        result = filter_service.filter_reversal_stocks(
            stock_data_list,
            historical_data=historical_data,
            limit=limit
        )
        
        # 转换为字典格式
        from backend.models.strategy_result import StrategyResult
        if isinstance(result, StrategyResult):
            result_dict = result.to_dict()
        else:
            result_dict = result
        
        # 添加策略描述信息
        return {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "candidates": result_dict.get("candidates", []),
            "warning": result_dict.get("warning"),
            "filter_steps": result_dict.get("filter_steps", {}),
            "strategy_info": {
                "name": "反转策略",
                "description": "识别冰点反转、超跌修复",
                "type": "bottom_fishing"
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ 反转策略筛选失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="筛选失败，请稍后重试")


@router.get("/pullback")
async def get_pullback_candidates(
    limit: int = Query(10, description="返回数量限制"),
    date: Optional[str] = Query(None, description="日期，格式：YYYY-MM-DD，默认今天")
) -> Dict:
    """
    获取波段低吸候选
    
    Returns:
        Dict: {
            "candidates": List[Dict],
            "warning": Optional[str],
            "filter_steps": Dict
        }
    """
    try:
        logger.info(f"📥 收到波段低吸筛选请求: limit={limit}")
        
        market_service = MarketDataService()
        filter_service = StockFilterService()
        
        loop = asyncio.get_running_loop()
        stock_data_list = []
        
        try:
            stock_data_list = await asyncio.wait_for(
                loop.run_in_executor(executor, market_service.get_realtime_stocks_as_models, False),
                timeout=60.0
            )
        except asyncio.TimeoutError:
            raise HTTPException(status_code=500, detail="获取股票数据超时")
        
        if not stock_data_list:
            raise HTTPException(status_code=500, detail="无法获取股票数据")
        
        history_codes = [stock.code for stock in stock_data_list[:200]]
        historical_data = market_service.get_historical_kline(history_codes, days=160, max_codes=80)
        
        result = filter_service.filter_pullback_stocks(
            stock_data_list,
            historical_data=historical_data,
            limit=limit
        )
        
        # 转换为字典格式
        from backend.models.strategy_result import StrategyResult
        if isinstance(result, StrategyResult):
            result_dict = result.to_dict()
        else:
            result_dict = result
        
        # 添加策略描述信息
        return {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "candidates": result_dict.get("candidates", []),
            "warning": result_dict.get("warning"),
            "filter_steps": result_dict.get("filter_steps", {}),
            "strategy_info": {
                "name": "波段低吸策略",
                "description": "识别趋势中的回踩机会",
                "type": "stable"
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ 波段低吸筛选失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="筛选失败，请稍后重试")


@router.get("/darwin")
async def get_darwin_companies(
    limit: int = Query(20, description="返回数量限制"),
    date: Optional[str] = Query(None, description="日期，格式：YYYY-MM-DD，默认今天")
) -> Dict:
    """
    获取达尔文公司（长期持仓）候选
    
    Returns:
        Dict: {
            "darwin_core": List[Dict],  # 核心长期持仓池
            "darwin_watch": List[Dict],  # 观察池
            "warning": Optional[str],
            "filter_steps": Dict
        }
    """
    try:
        logger.info(f"📥 收到达尔文筛选请求: limit={limit}")
        
        market_service = MarketDataService()
        filter_service = StockFilterService()
        
        # 使用新的达尔文数据服务
        from backend.services.darwin.darwin_data_service import DarwinDataService
        darwin_data_service = DarwinDataService()
        
        loop = asyncio.get_running_loop()
        stock_data_list = []
        
        try:
            stock_data_list = await asyncio.wait_for(
                loop.run_in_executor(executor, market_service.get_realtime_stocks_as_models, False),
                timeout=60.0
            )
        except asyncio.TimeoutError:
            raise HTTPException(status_code=500, detail="获取股票数据超时")
        
        if not stock_data_list:
            raise HTTPException(status_code=500, detail="无法获取股票数据")
        
        # 批量获取财务数据和行业信息
        logger.info(f"📊 批量获取财务数据和行业信息: {len(stock_data_list)} 只股票")
        
        stock_codes = [stock.code for stock in stock_data_list]
        financial_data = darwin_data_service.get_financial_data_batch(stock_codes)
        industry_info = darwin_data_service.get_industry_info_batch(stock_codes)
        
        logger.info(f"✅ 获取到财务数据: {len(financial_data)} 只，行业信息: {len(industry_info)} 只")
        
        # 将行业信息添加到股票数据中
        for stock in stock_data_list:
            if stock.code in industry_info:
                stock.sector = industry_info[stock.code]
        
        result = filter_service.filter_darwin_long_term_stocks(
            stock_data_list,
            financial_data=financial_data,
            limit=limit
        )
        
        # 转换为字典格式
        from backend.models.strategy_result import StrategyResult
        if isinstance(result, StrategyResult):
            result_dict = result.to_dict()
        else:
            result_dict = result
        
        # 添加行业信息和选股理由到结果中
        for category in ['darwin_core', 'darwin_watch']:
            for stock_dict in result_dict.get(category, []):
                code = stock_dict.get('code')
                if code:
                    # 添加行业信息
                    if code in industry_info:
                        stock_dict['sector'] = industry_info[code]
                    
                    # 生成选股理由
                    fin_data = financial_data.get(code)
                    reason = darwin_data_service.generate_selection_reason(
                        stock_dict, 
                        fin_data, 
                        stock_dict.get('sector')
                    )
                    stock_dict['reason'] = reason
        
        # 添加策略描述信息
        return {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "darwin_core": result_dict.get("darwin_core", []),
            "darwin_watch": result_dict.get("darwin_watch", []),
            "warning": result_dict.get("warning"),
            "filter_steps": result_dict.get("filter_steps", {}),
            "strategy_info": {
                "name": "达尔文长期策略",
                "description": "评估长期可持续的公司质量",
                "type": "long_term"
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ 达尔文筛选失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="筛选失败，请稍后重试")

