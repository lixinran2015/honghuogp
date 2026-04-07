"""
板块热度API接口
"""

from fastapi import APIRouter, HTTPException
from typing import Dict, List, Optional
import json
import logging
from datetime import datetime
import pandas as pd
import asyncio
from concurrent.futures import ThreadPoolExecutor

from backend.services.market_data_service import MarketDataService
from backend.services.moneyflow_service import MoneyflowService
from backend.strategy.sector_heat import SectorHeatCalculator
from backend.strategy.leading import LeadingStockIdentifier
from backend.services.darwin.darwin_data_service import DarwinDataService
from backend.services.sector.eastmoney_sector_service import (
    fetch_industry_boards_with_leaders,
    get_industry_boards_from_db,
    get_latest_trade_date_with_boards,
)
from data_warehouse.service.warehouse_service import WarehouseService
from data_warehouse.models import FactSectorHeatSnapshot

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/hot-sectors", tags=["hot-sectors"])

# 创建线程池用于执行阻塞操作
executor = ThreadPoolExecutor(max_workers=2)


@router.get("/today")
async def get_hot_sectors_today() -> Dict:
    """
    获取今日板块热度（热点板块 + 龙头）
    
    Returns:
        dict: 包含今日板块热度列表的字典
    """
    try:
        logger.info("📥 收到今日板块热度请求")
        
        # 初始化服务
        market_service = MarketDataService()
        moneyflow_service = MoneyflowService()
        heat_calculator = SectorHeatCalculator()
        leader_identifier = LeadingStockIdentifier()
        darwin_data_service = DarwinDataService()
        
        # 异步获取实时股票数据
        loop = asyncio.get_running_loop()
        stock_data = pd.DataFrame()
        
        try:
            stock_data = await asyncio.wait_for(
                loop.run_in_executor(executor, market_service.get_realtime_stocks, False),
                timeout=30.0
            )
        except asyncio.TimeoutError:
            logger.warning("⚠️ 获取股票数据超时")
            return {
                "date": datetime.now().strftime("%Y-%m-%d"),
                "items": [],
                "count": 0,
                "message": "数据获取超时，请稍后重试"
            }
        
        if stock_data.empty:
            logger.warning("⚠️ 获取到的股票数据为空")
            return {
                "date": datetime.now().strftime("%Y-%m-%d"),
                "items": [],
                "count": 0
            }
        
        # 转换为列表格式
        stock_list = []
        for _, row in stock_data.iterrows():
            stock_dict = row.to_dict()
            stock_list.append(stock_dict)
        
        # 批量获取行业信息（补充板块数据）
        stock_codes = []
        for stock in stock_list:
            code = stock.get('code', stock.get('代码', ''))
            if code:
                # 标准化代码格式（去除.SH/.SZ后缀）
                code_6digit = str(code).strip()
                if '.' in code_6digit:
                    code_6digit = code_6digit.split('.')[0]
                if len(code_6digit) == 6:
                    stock_codes.append(code_6digit)
        
        logger.info(f"📊 批量获取 {len(stock_codes)} 只股票的行业信息...")
        industry_info = darwin_data_service.get_industry_info_batch(stock_codes)
        logger.info(f"✅ 获取到 {len(industry_info)} 只股票的行业信息")
        
        # 补充板块信息到股票数据
        for stock in stock_list:
            code = stock.get('code', stock.get('代码', ''))
            if code:
                # 标准化代码格式
                code_6digit = str(code).strip()
                if '.' in code_6digit:
                    code_6digit = code_6digit.split('.')[0]
                if code_6digit in industry_info:
                    stock['sector'] = industry_info[code_6digit]
                    stock['行业'] = industry_info[code_6digit]
                    stock['所属行业'] = industry_info[code_6digit]
        
        # 按板块分组
        sector_stocks = {}
        for stock in stock_list:
            sector = stock.get('sector', stock.get('行业', stock.get('所属行业', '未知')))
            if sector == '未知' or not sector:
                continue
            if sector not in sector_stocks:
                sector_stocks[sector] = []
            sector_stocks[sector].append(stock)
        
        logger.info(f"📊 按板块分组: {len(sector_stocks)} 个板块")
        
        # 计算每个板块的热度并识别龙头股
        hot_sectors = []
        for sector_name, stocks in sector_stocks.items():
            if len(stocks) < 3:  # 至少3只股票才算板块
                continue
            
            # 计算板块热度
            heat_score = heat_calculator.calculate_sector_heat_from_stocks(
                sector_name=sector_name,
                stocks=stocks
            )
            
            # 识别龙头股
            leader = leader_identifier.identify_leader(
                stocks=stocks,
                min_change_pct=0.0,  # 不限制最小涨幅
                min_turnover_rate=1.0,
                min_amount=1e7  # 最小成交额1000万
            )
            
            # 生成策略建议
            strategy = _generate_sector_strategy(heat_score, leader)
            
            hot_sectors.append({
                "sector": sector_name,
                "heatScore": heat_score,
                "leader": leader if leader else {
                    "code": "",
                    "name": "暂无",
                    "changePct": 0.0
                },
                "strategy": strategy
            })
        
        # 按热度评分排序
        hot_sectors.sort(key=lambda x: x['heatScore'], reverse=True)
        
        # 取前20个
        hot_sectors = hot_sectors[:20]
        
        logger.info(f"✅ 生成 {len(hot_sectors)} 个热点板块")
        
        return {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "items": hot_sectors,
            "count": len(hot_sectors)
        }
        
    except Exception as e:
        logger.error(f"❌ 获取今日板块热度失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="获取今日板块热度失败，请稍后重试")


@router.get("/industry-boards-with-leaders")
async def get_industry_boards_with_leaders_api(
    refresh: bool = False,
    trade_date: Optional[str] = None,
) -> Dict:
    """
    获取东财行业板块列表（含领涨股、涨跌幅等，格式类似东财行情页）
    优先从 fact_sector_board_snapshot 读取；refresh=true 时重新拉取并写入库。
    
    Args:
        refresh: 是否强制刷新（重新拉取东财并写入 DB）
        trade_date: 交易日期 YYYY-MM-DD，默认当天
    
    Returns:
        dict: date, items, count, source(db/ live)
    """
    from datetime import date as date_type
    td = date_type.fromisoformat(trade_date) if trade_date else date_type.today()
    try:
        if not refresh:
            df = await asyncio.get_running_loop().run_in_executor(
                executor, lambda: get_industry_boards_from_db(td)
            )
            if df is not None and not df.empty:
                items = json.loads(df.to_json(orient="records", date_format="iso", default_handler=str))
                return {
                    "date": td.strftime("%Y-%m-%d"),
                    "items": items,
                    "count": len(items),
                    "source": "db",
                }
        loop = asyncio.get_running_loop()
        df = await asyncio.wait_for(
            loop.run_in_executor(executor, lambda: fetch_industry_boards_with_leaders(save_to_db=True)),
            timeout=30.0,
        )
        if df is None or df.empty:
            # 东财 API 失败时，回退到 DB 中最新日期的缓存
            fallback_date = get_latest_trade_date_with_boards()
            if fallback_date:
                df_fallback = get_industry_boards_from_db(fallback_date)
                if df_fallback is not None and not df_fallback.empty:
                    items = json.loads(df_fallback.to_json(orient="records", date_format="iso", default_handler=str))
                    return {
                        "date": fallback_date.strftime("%Y-%m-%d"),
                        "items": items,
                        "count": len(items),
                        "source": "db",
                        "message": "实时接口不可用，已返回最近缓存数据",
                    }
            return {
                "date": td.strftime("%Y-%m-%d"),
                "items": [],
                "count": 0,
                "source": "live",
                "message": "获取行业板块数据失败，请检查网络或稍后重试",
            }
        items = json.loads(df.to_json(orient="records", date_format="iso", default_handler=str))
        return {
            "date": td.strftime("%Y-%m-%d"),
            "items": items,
            "count": len(items),
            "source": "live",
        }
    except asyncio.TimeoutError:
        logger.warning("⚠️ 获取行业板块数据超时")
        return {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "items": [],
            "count": 0,
            "message": "数据获取超时，请稍后重试",
        }
    except Exception as e:
        logger.error(f"❌ 获取行业板块领涨数据失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="操作失败，请稍后重试")


def _generate_sector_strategy(heat_score: float, leader: Optional[Dict]) -> str:
    """
    根据板块热度和龙头股生成策略建议

    Args:
        heat_score: 板块热度评分
        leader: 龙头股信息

    Returns:
        str: 策略建议
    """
    try:
        if heat_score >= 80:
            if leader and leader.get('changePct', 0) >= 5:
                return "当日强势，可关注领涨龙头的回踩机会"
            else:
                return "板块热度极高，建议关注板块内强势个股"
        elif heat_score >= 60:
            if leader and leader.get('changePct', 0) >= 3:
                return "板块表现良好，可关注龙头股的突破机会"
            else:
                return "板块热度较高，建议观察板块轮动"
        elif heat_score >= 40:
            return "板块热度一般，建议谨慎观察"
        else:
            return "板块热度较低，建议观望"
    except Exception as e:
        logger.warning(f"生成策略建议失败: {e}")
        return "建议关注板块动态"


@router.get("/heat-snapshot")
async def get_sector_heat_snapshot(
    limit: int = 20,
    window_id: str = "rolling_30d_v2"
) -> Dict:
    """
    获取板块热度快照（用于短线龙头仪表盘）

    Args:
        limit: 返回板块数量
        window_id: 窗口ID，默认当前滚动30天

    Returns:
        dict: 板块热度列表
    """
    try:
        ws = WarehouseService()
        session = ws.get_session()
        try:
            # 查询板块热度快照
            records = (
                session.query(FactSectorHeatSnapshot)
                .filter(FactSectorHeatSnapshot.window_id == window_id)
                .order_by(FactSectorHeatSnapshot.return_index.desc())
                .limit(limit)
                .all()
            )

            sectors = []
            for r in records:
                # 计算热度分数（基于多个指标）
                heat_score = 0.0
                if r.return_index is not None:
                    heat_score += r.return_index * 2
                if r.active_stock_ratio_30d is not None:
                    heat_score += r.active_stock_ratio_30d * 50

                sectors.append({
                    "name": r.sector_name,
                    "code": r.sector_code,
                    "heat": round(heat_score, 1),
                    "return_30d": round(r.return_30d, 2) if r.return_30d else 0,
                    "return_index": round(r.return_index, 2) if r.return_index else 0,
                    "turnover_ratio": round(r.avg_turnover_ratio_now, 2) if r.avg_turnover_ratio_now else 0,
                    "amount": r.amount_now,
                })

            # 按热度排序
            sectors.sort(key=lambda x: x["heat"], reverse=True)

            return {
                "success": True,
                "sectors": sectors,
                "count": len(sectors),
                "window_id": window_id,
            }
        finally:
            session.close()

    except Exception as e:
        logger.error(f"获取板块热度快照失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取板块热度失败: {str(e)}")

