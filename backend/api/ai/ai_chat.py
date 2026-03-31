"""
AI智能问答API
基于RAG知识库的自然语言问答，支持多轮对话和投资笔记提醒
"""

import asyncio
import logging
import re
from typing import Dict, Optional, List

import requests
from fastapi import APIRouter, HTTPException, Query, Body

from backend.knowledge_base.rag_service import RAGService
from backend.services.analysis.ai_analysis_service import AIAnalysisService
from backend.services.chat.session_service import get_session_service
from backend.services.notes.investment_notes_service import InvestmentNotesService

router = APIRouter(prefix="/api/ai-chat", tags=["ai-chat"])
logger = logging.getLogger(__name__)

# 初始化RAG服务（单例）
_rag_service: Optional[RAGService] = None
_notes_service: Optional[InvestmentNotesService] = None

def get_rag_service() -> Optional[RAGService]:
    """获取RAG服务实例"""
    global _rag_service
    if _rag_service is None:
        try:
            _rag_service = RAGService()
        except Exception as e:
            logger.warning(f"RAG服务初始化失败: {e}")
            return None
    return _rag_service

def get_notes_service() -> InvestmentNotesService:
    """获取笔记服务实例"""
    global _notes_service
    if _notes_service is None:
        _notes_service = InvestmentNotesService()
    return _notes_service

def extract_stock_from_query(query: str) -> Optional[Dict[str, str]]:
    """从查询中提取股票代码和名称"""
    # 匹配6位数字股票代码
    code_match = re.search(r'\b(\d{6})\b', query)
    if code_match:
        return {"symbol": code_match.group(1), "name": ""}
    return None


@router.post("")
async def chat(
    query: str = Body(..., description="用户问题"),
    use_rag: bool = Body(True, description="是否使用RAG知识库"),
    session_id: Optional[str] = Body(None, description="会话ID，用于多轮对话"),
    use_history: bool = Body(True, description="是否使用历史对话上下文"),
    include_lessons: bool = Body(True, description="是否包含投资教训提醒"),
) -> Dict:
    """
    AI智能问答接口
    
    支持基于RAG知识库的问答，多轮对话记忆，投资教训提醒
    """
    try:
        ai_service = AIAnalysisService()
        session_service = get_session_service()
        notes_service = get_notes_service()
        
        # 获取或创建会话
        session = session_service.get_or_create_session(session_id)
        
        # 提取股票信息
        stock_info = extract_stock_from_query(query)
        if stock_info:
            session.set_current_stock(stock_info["symbol"], stock_info.get("name", ""))
        
        # 如果启用RAG，先检索知识库
        context = ""
        if use_rag:
            rag_service = get_rag_service()
            if rag_service:
                context = rag_service.build_context(query, max_context_length=1500)
                logger.info(f"检索到上下文长度: {len(context)} 字符")
        
        # 获取投资教训上下文
        lessons_context = ""
        if include_lessons:
            current_stock = session.get_current_stock()
            symbol = current_stock.get("symbol") if current_stock else None
            lessons_context = notes_service.build_lessons_context(symbol=symbol)
        
        # 获取历史对话上下文
        history_messages = []
        if use_history and session.messages:
            history_messages = session.get_context_messages(limit=6)
        
        # 构建 Prompt（包含知识库、教训提醒）
        prompt_parts = []
        if context:
            prompt_parts.append(f"【知识库内容】\n{context}\n")
        if lessons_context:
            prompt_parts.append(f"{lessons_context}\n")
        prompt_parts.append(f"【用户问题】\n{query}\n")
        prompt_parts.append("""【要求】
1. 回答要专业、准确、易懂
2. 若问题涉及某只具体股票，需包含「是否龙头」：说明是否为行业/细分龙头及简要依据
3. 如果有历史投资教训，请在回答中适当提醒用户注意
4. 控制在200-500字""")
        
        prompt = "\n".join(prompt_parts)
        
        # 调用DeepSeek API
        deepseek_config = ai_service.config_manager.get_ai_config("deepseek") if ai_service.config_manager else None
        
        if not deepseek_config or not ai_service.config_manager.is_ai_enabled("deepseek"):
            return {
                'success': False,
                'message': 'AI服务未启用',
                'answer': None,
                'session_id': session.session_id,
            }
        
        api_url = deepseek_config.get("api_url", "")
        api_key = deepseek_config.get("api_key", "")
        model = deepseek_config.get("model", "deepseek-r1-250528")
        
        if not api_url or not api_key:
            return {
                'success': False,
                'message': 'AI API未配置',
                'answer': None,
                'session_id': session.session_id,
            }
        
        import requests
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        # 构建消息列表（包含历史对话）
        messages = [
            {
                "role": "system",
                "content": "你是一位专业的股票投资顾问，擅长回答股票投资相关问题。你会记住对话历史，支持追问式分析。"
            }
        ]
        # 添加历史对话
        for hist_msg in history_messages:
            messages.append(hist_msg)
        # 添加当前问题
        messages.append({"role": "user", "content": prompt})
        
        payload = {
            "model": model,
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": 800
        }
        
        logger.info(f"📡 调用DeepSeek API进行智能问答: {query[:50]}... (会话: {session.session_id})")
        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(
            None,
            lambda: requests.post(api_url, headers=headers, json=payload, timeout=60)
        )
        response.raise_for_status()
        
        result = response.json()
        content = result.get('choices', [{}])[0].get('message', {}).get('content', '')
        
        if not content:
            return {
                'success': False,
                'message': 'AI返回空内容',
                'answer': None,
                'session_id': session.session_id,
            }
        
        # 保存对话历史
        session.add_message("user", query)
        session.add_message("assistant", content)
        
        return {
            'success': True,
            'answer': content,
            'used_rag': bool(context),
            'context_length': len(context) if context else 0,
            'session_id': session.session_id,
            'message_count': len(session.messages),
            'has_lessons': bool(lessons_context),
        }
        
    except Exception as e:
        logger.error(f"智能问答失败: {e}", exc_info=True)
        return {
            'success': False,
            'message': '智能问答失败，请稍后重试',
            'answer': None
        }


@router.get("/health")
async def health_check() -> Dict:
    """检查RAG服务健康状态"""
    rag_service = get_rag_service()
    
    return {
        'rag_available': rag_service is not None,
        'collection_count': rag_service.collection.count() if rag_service else 0
    }


@router.get("/sessions")
async def list_sessions(user_id: int = Query(1, description="用户ID")) -> Dict:
    """列出用户的会话"""
    session_service = get_session_service()
    sessions = session_service.list_sessions(user_id)
    return {"success": True, "sessions": sessions}


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str) -> Dict:
    """删除会话"""
    session_service = get_session_service()
    success = session_service.delete_session(session_id)
    return {"success": success}


@router.get("/sessions/{session_id}/history")
async def get_session_history(session_id: str) -> Dict:
    """获取会话历史"""
    session_service = get_session_service()
    session = session_service.get_session(session_id)
    if not session:
        return {"success": False, "message": "会话不存在", "messages": []}
    return {
        "success": True,
        "session_id": session_id,
        "messages": session.messages,
        "current_stock": session.get_current_stock(),
    }


@router.post("/sessions/{session_id}/clear")
async def clear_session(session_id: str) -> Dict:
    """清空会话历史"""
    session_service = get_session_service()
    session = session_service.get_session(session_id)
    if session:
        session.clear()
        return {"success": True, "message": "会话已清空"}
    return {"success": False, "message": "会话不存在"}


# ========== 投资笔记 API ==========

@router.get("/notes")
async def list_notes(
    user_id: int = Query(1),
    symbol: Optional[str] = Query(None, description="筛选股票代码"),
    note_type: Optional[str] = Query(None, description="筛选类型"),
    limit: int = Query(50),
    offset: int = Query(0),
) -> Dict:
    """获取投资笔记列表"""
    notes_service = get_notes_service()
    notes = notes_service.get_notes(user_id, symbol, note_type, limit, offset)
    return {"success": True, "notes": notes, "count": len(notes)}


@router.post("/notes")
async def add_note(
    title: str = Body(..., description="标题"),
    content: str = Body(..., description="内容"),
    user_id: int = Body(1),
    symbol: Optional[str] = Body(None, description="关联股票代码"),
    stock_name: Optional[str] = Body(None, description="股票名称"),
    note_type: str = Body("general", description="类型: general/lesson/success/mistake"),
    tags: Optional[str] = Body(None, description="标签"),
    trade_date: Optional[str] = Body(None, description="相关日期 YYYY-MM-DD"),
    profit_rate: Optional[float] = Body(None, description="相关盈亏率"),
) -> Dict:
    """添加投资笔记"""
    from datetime import datetime
    notes_service = get_notes_service()
    td = None
    if trade_date:
        try:
            td = datetime.strptime(trade_date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=422, detail="trade_date 格式错误，请使用 YYYY-MM-DD")
    note_id = notes_service.add_note(
        title=title,
        content=content,
        user_id=user_id,
        symbol=symbol,
        stock_name=stock_name,
        note_type=note_type,
        tags=tags,
        trade_date=td,
        profit_rate=profit_rate,
    )
    if note_id:
        return {"success": True, "note_id": note_id}
    return {"success": False, "message": "添加失败"}


@router.get("/notes/{note_id}")
async def get_note(note_id: int, user_id: int = Query(1)) -> Dict:
    """获取单条笔记"""
    notes_service = get_notes_service()
    note = notes_service.get_note_by_id(note_id, user_id)
    if note:
        return {"success": True, "note": note}
    return {"success": False, "message": "笔记不存在"}


@router.put("/notes/{note_id}")
async def update_note(
    note_id: int,
    user_id: int = Body(1),
    title: Optional[str] = Body(None),
    content: Optional[str] = Body(None),
    note_type: Optional[str] = Body(None),
    tags: Optional[str] = Body(None),
) -> Dict:
    """更新笔记"""
    notes_service = get_notes_service()
    success = notes_service.update_note(note_id, user_id, title, content, note_type, tags)
    return {"success": success}


@router.delete("/notes/{note_id}")
async def delete_note(note_id: int, user_id: int = Query(1)) -> Dict:
    """删除笔记"""
    notes_service = get_notes_service()
    success = notes_service.delete_note(note_id, user_id)
    return {"success": success}


@router.post("/notes/sync-to-rag")
async def sync_notes_to_rag(user_id: int = Body(1)) -> Dict:
    """同步投资笔记到 RAG 知识库"""
    notes_service = get_notes_service()
    result = notes_service.sync_notes_to_rag(user_id)
    return result


# ========== 研报入库 API ==========

@router.get("/reports")
async def list_reports(
    stock_code: Optional[str] = Query(None, description="股票代码"),
    industry_code: Optional[str] = Query(None, description="行业代码"),
    days: int = Query(30, description="最近天数"),
) -> Dict:
    """获取近期研报列表（不入库）"""
    from backend.services.research.report_crawler_service import ReportCrawlerService
    crawler = ReportCrawlerService()
    reports = crawler.get_recent_reports_summary(stock_code, industry_code, days)
    return {"success": True, "reports": reports, "count": len(reports)}


@router.post("/reports/import")
async def import_reports_to_rag(
    stock_code: Optional[str] = Body(None, description="股票代码"),
    industry_code: Optional[str] = Body(None, description="行业代码"),
    days: int = Body(7, description="抓取最近天数"),
    max_reports: int = Body(20, description="最多导入篇数"),
    extract_points: bool = Body(True, description="是否用AI提取核心观点"),
) -> Dict:
    """抓取研报并导入 RAG 知识库"""
    from backend.services.research.report_crawler_service import ReportCrawlerService
    crawler = ReportCrawlerService()
    result = crawler.import_reports_to_rag(
        industry_code=industry_code,
        stock_code=stock_code,
        days=days,
        max_reports=max_reports,
        extract_points=extract_points,
    )
    return result
