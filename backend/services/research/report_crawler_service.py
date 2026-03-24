"""
研报自动入库服务
- 从东财研报中心爬取研报
- 提取核心观点
- 自动入库 RAG
"""

import logging
import re
import time
from datetime import datetime, date, timedelta
from typing import List, Dict, Optional, Any
import requests

logger = logging.getLogger(__name__)


class ReportCrawlerService:
    """研报爬虫服务"""

    EASTMONEY_REPORT_API = "https://reportapi.eastmoney.com/report/list"
    
    def __init__(self):
        self._rag_service = None
        self._ai_service = None

    @property
    def rag_service(self):
        if self._rag_service is None:
            try:
                from backend.knowledge_base.rag_service import RAGService
                self._rag_service = RAGService()
            except Exception as e:
                logger.warning(f"RAG服务初始化失败: {e}")
        return self._rag_service

    @property
    def ai_service(self):
        if self._ai_service is None:
            from backend.services.analysis.ai_analysis_service import AIAnalysisService
            self._ai_service = AIAnalysisService()
        return self._ai_service

    def fetch_reports(
        self,
        industry_code: Optional[str] = None,
        stock_code: Optional[str] = None,
        begin_time: Optional[str] = None,
        end_time: Optional[str] = None,
        page_size: int = 20,
        page_no: int = 1,
    ) -> List[Dict[str, Any]]:
        """
        从东财研报中心获取研报列表
        
        Args:
            industry_code: 行业代码（如 '451' 银行）
            stock_code: 股票代码（如 '600519'）
            begin_time: 开始日期 YYYY-MM-DD
            end_time: 结束日期 YYYY-MM-DD
            page_size: 每页数量
            page_no: 页码
        """
        try:
            params = {
                "industryCode": industry_code or "*",
                "pageSize": page_size,
                "industry": "*",
                "rating": "*",
                "ratingChange": "*",
                "beginTime": begin_time or (date.today() - timedelta(days=7)).isoformat(),
                "endTime": end_time or date.today().isoformat(),
                "pageNo": page_no,
                "fields": "",
                "qType": 0,
                "orgCode": "",
                "code": stock_code or "*",
                "rcode": "",
                "p": page_no,
                "pageNum": page_no,
                "pageNumber": page_no,
            }
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": "https://data.eastmoney.com/",
            }
            resp = requests.get(self.EASTMONEY_REPORT_API, params=params, headers=headers, timeout=15)
            if resp.status_code != 200:
                logger.warning(f"东财研报接口返回 {resp.status_code}")
                return []
            data = resp.json()
            reports = data.get("data", [])
            logger.info(f"获取到 {len(reports)} 篇研报")
            return reports
        except Exception as e:
            logger.error(f"获取研报列表失败: {e}")
            return []

    def fetch_report_content(self, info_code: str) -> Optional[str]:
        """
        获取研报详情内容（摘要）
        
        Args:
            info_code: 研报 infoCode
        """
        try:
            url = f"https://data.eastmoney.com/report/zw_industry.jshtml?infocode={info_code}"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            }
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code != 200:
                return None
            text = resp.text
            match = re.search(r'<div class="newsContent"[^>]*>(.*?)</div>', text, re.DOTALL)
            if match:
                content = re.sub(r'<[^>]+>', '', match.group(1)).strip()
                return content[:3000]
            return None
        except Exception as e:
            logger.debug(f"获取研报内容失败: {e}")
            return None

    def extract_key_points(self, title: str, content: str, timeout: int = 30) -> Optional[str]:
        """
        使用 AI 提取研报核心观点
        """
        if not content or len(content) < 50:
            return None
        try:
            prompt = f"""请从以下研报内容中提取3-5条核心观点，每条不超过50字：

【研报标题】{title}

【研报内容】
{content[:2000]}

【要求】
1. 每条观点一行，用数字编号
2. 提取最重要的投资观点、目标价、评级变化
3. 简洁、专业、可操作
"""
            from utils.config_manager import config_manager as cm

            if cm.is_ai_enabled("deepseek"):
                cfg = cm.get_ai_config("deepseek")
                api_url = cfg.get("api_url", "https://api.deepseek.com/v1/chat/completions")
                api_key = cfg.get("api_key", "")
                model = cfg.get("model", "deepseek-chat")
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}",
                }
                payload = {
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.5,
                    "max_tokens": 500,
                }
                resp = requests.post(api_url, headers=headers, json=payload, timeout=timeout)
                if resp.status_code == 200:
                    result = resp.json()
                    return result.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
            return None
        except Exception as e:
            logger.debug(f"提取核心观点失败: {e}")
            return None

    def import_reports_to_rag(
        self,
        industry_code: Optional[str] = None,
        stock_code: Optional[str] = None,
        days: int = 7,
        max_reports: int = 20,
        extract_points: bool = True,
    ) -> Dict[str, Any]:
        """
        抓取研报并导入 RAG
        
        Args:
            industry_code: 行业代码
            stock_code: 股票代码
            days: 抓取最近多少天
            max_reports: 最多导入多少篇
            extract_points: 是否用 AI 提取核心观点
        """
        begin_time = (date.today() - timedelta(days=days)).isoformat()
        end_time = date.today().isoformat()
        
        reports = self.fetch_reports(
            industry_code=industry_code,
            stock_code=stock_code,
            begin_time=begin_time,
            end_time=end_time,
            page_size=max_reports,
        )
        
        if not reports:
            return {"success": False, "message": "未获取到研报", "imported": 0}
        
        documents = []
        for rpt in reports[:max_reports]:
            title = rpt.get("title", "")
            org_name = rpt.get("orgSName", "")  # 券商简称
            pub_date = rpt.get("publishDate", "")[:10] if rpt.get("publishDate") else ""
            industry = rpt.get("industryName", "")
            stock_name = rpt.get("stockName", "")
            rating = rpt.get("emRatingName", "")  # 评级
            info_code = rpt.get("infoCode", "")
            
            # 构建内容
            content_parts = [f"【{title}】"]
            if org_name:
                content_parts.append(f"来源: {org_name}")
            if pub_date:
                content_parts.append(f"日期: {pub_date}")
            if industry:
                content_parts.append(f"行业: {industry}")
            if stock_name:
                content_parts.append(f"股票: {stock_name}")
            if rating:
                content_parts.append(f"评级: {rating}")
            
            # 获取详细内容
            detail_content = None
            if info_code:
                detail_content = self.fetch_report_content(info_code)
                time.sleep(0.3)  # 限速
            
            # 提取核心观点
            key_points = None
            if extract_points and detail_content:
                key_points = self.extract_key_points(title, detail_content)
                time.sleep(0.5)
            
            if key_points:
                content_parts.append(f"\n核心观点:\n{key_points}")
            elif detail_content:
                content_parts.append(f"\n摘要: {detail_content[:500]}")
            
            content = "\n".join(content_parts)
            
            doc_id = f"report_{info_code or pub_date}_{hash(title) % 100000}"
            documents.append({
                "id": doc_id,
                "content": content,
                "metadata": {
                    "title": title,
                    "category": "研报",
                    "source": org_name,
                    "industry": industry,
                    "stock": stock_name,
                    "rating": rating,
                    "pub_date": pub_date,
                    "type": "research_report",
                }
            })
        
        if not documents:
            return {"success": False, "message": "无有效研报内容", "imported": 0}
        
        # 导入 RAG
        if self.rag_service:
            success = self.rag_service.add_documents(documents)
            if success:
                return {"success": True, "message": f"成功导入 {len(documents)} 篇研报", "imported": len(documents)}
        
        return {"success": False, "message": "RAG服务不可用", "imported": 0}

    def get_recent_reports_summary(
        self,
        stock_code: Optional[str] = None,
        industry_code: Optional[str] = None,
        days: int = 30,
    ) -> List[Dict[str, Any]]:
        """
        获取近期研报摘要（不入库，仅展示）
        """
        begin_time = (date.today() - timedelta(days=days)).isoformat()
        end_time = date.today().isoformat()
        reports = self.fetch_reports(
            industry_code=industry_code,
            stock_code=stock_code,
            begin_time=begin_time,
            end_time=end_time,
            page_size=50,
        )
        result = []
        for rpt in reports:
            result.append({
                "title": rpt.get("title", ""),
                "org_name": rpt.get("orgSName", ""),
                "pub_date": rpt.get("publishDate", "")[:10] if rpt.get("publishDate") else "",
                "industry": rpt.get("industryName", ""),
                "stock_name": rpt.get("stockName", ""),
                "stock_code": rpt.get("stockCode", ""),
                "rating": rpt.get("emRatingName", ""),
                "info_code": rpt.get("infoCode", ""),
            })
        return result
