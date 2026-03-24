"""
月度热点API接口
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Dict, List, Optional
import logging
from datetime import datetime
import pandas as pd
import asyncio
from concurrent.futures import ThreadPoolExecutor

from backend.strategy.monthly_theme import get_monthly_themes, get_current_month_theme
from backend.services.market_data_service import MarketDataService
from backend.strategy.sector_heat import SectorHeatCalculator
from backend.strategy.leading import LeadingStockIdentifier
from backend.services.darwin.darwin_data_service import DarwinDataService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/monthly-themes", tags=["monthly-themes"])

# 创建线程池用于执行阻塞操作
executor = ThreadPoolExecutor(max_workers=2)


@router.get("")
async def get_themes(
    year: int = Query(2025, description="年份"),
    include_today_heat: bool = Query(True, description="是否包含今日板块热度")
) -> Dict:
    """
    获取月度热点列表（整合今日板块热度）
    
    Args:
        year: 年份
        include_today_heat: 是否包含今日板块热度数据
    
    Returns:
        dict: 包含月度热点列表和今日板块热度的字典
    """
    try:
        logger.info(f"📥 收到月度热点请求: year={year}, include_today_heat={include_today_heat}")
        
        themes = get_monthly_themes(year)
        
        logger.info(f"✅ 成功获取 {len(themes)} 个月度热点")
        
        # 转换为新格式，确保包含所有必需字段
        formatted_themes = []
        for theme in themes:
            formatted_theme = {
                "month": theme.get('month', 0),
                "title": theme.get('title', ''),
                "hotSectors": theme.get('hotSectors', []),
                "leaders": theme.get('leaders', []),
                "strategies": {
                    "shortTerm": theme.get('strategies', {}).get('shortTerm', ''),
                    "swing": theme.get('strategies', {}).get('swing', ''),
                    "longTerm": theme.get('strategies', {}).get('longTerm', '')
                }
            }
            formatted_themes.append(formatted_theme)
        
        result = {
            "year": year,
            "themes": formatted_themes,
            "count": len(formatted_themes)
        }
        
        # 如果请求包含今日板块热度，获取并整合
        if include_today_heat:
            try:
                today_heat = await get_today_sector_heat_with_top3()
                result["todaySectorHeat"] = today_heat
                logger.info(f"✅ 成功获取今日板块热度: {len(today_heat.get('items', []))} 个板块")
            except Exception as e:
                logger.warning(f"⚠️ 获取今日板块热度失败: {e}")
                result["todaySectorHeat"] = {
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "items": [],
                    "count": 0
                }
        
        return result
        
    except Exception as e:
        logger.error(f"❌ 获取月度热点失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="获取月度热点失败，请稍后重试")


@router.get("/current")
async def get_current_theme() -> Dict:
    """
    获取当前月份的月度热点
    
    Returns:
        dict: 当前月份的月度热点
    """
    try:
        logger.info("📥 收到当前月份热点请求")
        
        theme = get_current_month_theme()
        
        if theme:
            logger.info(f"✅ 成功获取当前月份热点: {theme.get('title', '')}")
            return {
                "success": True,
                "data": theme
            }
        else:
            logger.warning("⚠️ 未找到当前月份热点")
            return {
                "success": False,
                "data": None,
                "message": "未找到当前月份热点配置"
            }
        
    except Exception as e:
        logger.error(f"❌ 获取当前月份热点失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="获取当前月份热点失败，请稍后重试")


async def get_today_sector_heat_with_top3() -> Dict:
    """
    获取今日板块热度（包含每个板块的top3股票）
    
    Returns:
        dict: 包含今日板块热度列表的字典，每个板块包含top3股票
    """
    try:
        # 初始化服务
        market_service = MarketDataService()
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
        
        # 计算每个板块的热度并获取top3股票
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
            
            # 获取top3股票（按涨幅排序）
            top3_stocks = _get_top3_stocks_by_change(stocks)
            
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
                "top3Stocks": top3_stocks,
                "strategy": strategy
            })
        
        # 按热度评分排序
        hot_sectors.sort(key=lambda x: x['heatScore'], reverse=True)
        
        logger.info(f"✅ 生成 {len(hot_sectors)} 个热点板块（包含top3股票）")
        
        return {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "items": hot_sectors,
            "count": len(hot_sectors)
        }
        
    except Exception as e:
        logger.error(f"❌ 获取今日板块热度失败: {e}", exc_info=True)
        return {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "items": [],
            "count": 0,
            'error': '操作失败'
        }


def _get_top3_stocks_by_change(stocks: List[Dict]) -> List[Dict]:
    """
    获取板块内涨幅top3的股票
    
    Args:
        stocks: 板块内股票列表
    
    Returns:
        List[Dict]: top3股票列表，每个包含code, name, changePct等信息
    """
    try:
        # 提取涨幅并排序
        scored_stocks = []
        for stock in stocks:
            change_pct = stock.get('changePct', stock.get('涨跌幅', stock.get('pct_chg', 0)))
            code = stock.get('code', stock.get('代码', ''))
            name = stock.get('name', stock.get('股票名称', stock.get('名称', '')))
            current_price = stock.get('currentPrice', stock.get('最新价', stock.get('lastPrice', 0)))
            turnover_rate = stock.get('turnoverRate', stock.get('换手率', stock.get('turnover_rate', 0)))
            amount = stock.get('amount', stock.get('成交额', 0))
            
            scored_stocks.append({
                'code': code,
                'name': name,
                'changePct': float(change_pct) if change_pct else 0.0,
                'currentPrice': float(current_price) if current_price else 0.0,
                'turnoverRate': float(turnover_rate) if turnover_rate else 0.0,
                'amount': float(amount) if amount else 0.0
            })
        
        # 按涨幅排序，取top3
        scored_stocks.sort(key=lambda x: x['changePct'], reverse=True)
        top3 = scored_stocks[:3]
        
        return top3
        
    except Exception as e:
        logger.error(f"获取top3股票失败: {e}", exc_info=True)
        return []


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

