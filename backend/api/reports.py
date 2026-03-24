"""
报告生成API接口
"""

import os
from fastapi import APIRouter, HTTPException, Query
from typing import Dict, Optional
import logging
from datetime import datetime

from backend.services.report_generator import ReportGenerator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("/{report_type}")
async def generate_report(
    report_type: str,
    date: Optional[str] = Query(None, description="日期，格式：YYYY-MM-DD，默认今天")
) -> Dict:
    """
    生成投研报告
    
    Args:
        report_type: 报告类型（short-term/middle-term/long-term/fund）
        date: 日期（可选）
        
    Returns:
        dict: 报告信息
    """
    try:
        logger.info(f"📥 收到报告生成请求: type={report_type}, date={date}")
        
        report_generator = ReportGenerator()
        file_path = ""
        content = ""
        
        if report_type == "short-term":
            # 获取短线推荐和市场概况
            from backend.api.recommendations import get_recommendations
            from backend.api.market import get_market_summary
            
            rec_result = await get_recommendations(type="short", limit=10)
            market_result = await get_market_summary()
            
            short_stocks = rec_result.get("data", {}).get("short", [])
            market_summary = market_result.get("data", {})
            
            file_path = report_generator.generate_short_term_report(short_stocks, market_summary)
            
        elif report_type == "middle-term":
            # 获取波段推荐
            from backend.api.recommendations import get_recommendations
            
            rec_result = await get_recommendations(type="swing", limit=10)
            swing_stocks = rec_result.get("data", {}).get("swing", [])
            
            file_path = report_generator.generate_middle_term_report(swing_stocks)
            
        elif report_type == "long-term":
            # 获取长线推荐（待实现）
            long_stocks = []
            file_path = report_generator.generate_long_term_report(long_stocks)
            
        elif report_type == "fund":
            # 获取基金定投建议
            from backend.api.fund import get_fund_recommendations
            
            fund_result = await get_fund_recommendations()
            fund_recommendations = fund_result.get("data", [])
            
            file_path = report_generator.generate_fund_report(fund_recommendations)
            
        else:
            raise HTTPException(status_code=400, detail=f"未知的报告类型: {report_type}")
        
        if file_path:
            # 读取报告内容
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
            except Exception as e:
                logger.warning(f"读取报告内容失败: {e}")
                content = ""
        
        return {
            "success": True,
            "data": {
                "type": report_type,
                "date": date or datetime.now().strftime("%Y-%m-%d"),
                "file_path": os.path.basename(file_path) if file_path else None,
                "content": content
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ 生成报告失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="生成报告失败，请稍后重试")

