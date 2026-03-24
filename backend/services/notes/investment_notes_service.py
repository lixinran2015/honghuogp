"""
投资笔记服务
- 管理用户的投资笔记、教训、复盘
- 关联股票
- AI 提醒历史教训
"""

import logging
from datetime import datetime, date
from typing import List, Dict, Optional, Any
from decimal import Decimal

logger = logging.getLogger(__name__)


class InvestmentNotesService:
    """投资笔记服务"""

    def __init__(self):
        self._warehouse = None

    @property
    def warehouse(self):
        if self._warehouse is None:
            from backend.services.data.postgres_warehouse import PostgresWarehouse
            self._warehouse = PostgresWarehouse()
        return self._warehouse

    def _ensure_table(self):
        """确保笔记表存在"""
        try:
            if not self.warehouse.warehouse_service:
                return False
            session = self.warehouse.warehouse_service.get_session()
            try:
                session.execute("""
                    CREATE TABLE IF NOT EXISTS fact_investment_notes (
                        id SERIAL PRIMARY KEY,
                        user_id INTEGER NOT NULL DEFAULT 1,
                        symbol VARCHAR(20),
                        stock_name VARCHAR(100),
                        note_type VARCHAR(20) NOT NULL DEFAULT 'general',
                        title VARCHAR(200) NOT NULL,
                        content TEXT NOT NULL,
                        tags VARCHAR(500),
                        trade_date DATE,
                        profit_rate NUMERIC(8,4),
                        created_at TIMESTAMP DEFAULT NOW(),
                        updated_at TIMESTAMP DEFAULT NOW()
                    )
                """)
                session.commit()
                return True
            finally:
                session.close()
        except Exception as e:
            logger.debug(f"创建笔记表失败: {e}")
            return False

    def add_note(
        self,
        title: str,
        content: str,
        user_id: int = 1,
        symbol: Optional[str] = None,
        stock_name: Optional[str] = None,
        note_type: str = "general",
        tags: Optional[str] = None,
        trade_date: Optional[date] = None,
        profit_rate: Optional[float] = None,
    ) -> Optional[int]:
        """
        添加投资笔记
        
        Args:
            title: 标题
            content: 内容
            user_id: 用户ID
            symbol: 股票代码
            stock_name: 股票名称
            note_type: 类型 general/lesson/success/mistake
            tags: 标签
            trade_date: 相关日期
            profit_rate: 相关盈亏率
        
        Returns:
            笔记ID
        """
        self._ensure_table()
        try:
            if not self.warehouse.warehouse_service:
                return None
            session = self.warehouse.warehouse_service.get_session()
            try:
                from sqlalchemy import text
                result = session.execute(
                    text("""
                        INSERT INTO fact_investment_notes 
                        (user_id, symbol, stock_name, note_type, title, content, tags, trade_date, profit_rate)
                        VALUES (:user_id, :symbol, :stock_name, :note_type, :title, :content, :tags, :trade_date, :profit_rate)
                        RETURNING id
                    """),
                    {
                        "user_id": user_id,
                        "symbol": symbol,
                        "stock_name": stock_name,
                        "note_type": note_type,
                        "title": title,
                        "content": content,
                        "tags": tags,
                        "trade_date": trade_date,
                        "profit_rate": profit_rate,
                    }
                )
                note_id = result.fetchone()[0]
                session.commit()
                logger.info(f"添加投资笔记: id={note_id}, title={title}")
                return note_id
            finally:
                session.close()
        except Exception as e:
            logger.error(f"添加笔记失败: {e}")
            return None

    def get_notes(
        self,
        user_id: int = 1,
        symbol: Optional[str] = None,
        note_type: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """获取笔记列表"""
        self._ensure_table()
        try:
            if not self.warehouse.warehouse_service:
                return []
            session = self.warehouse.warehouse_service.get_session()
            try:
                from sqlalchemy import text
                conditions = ["user_id = :user_id"]
                params = {"user_id": user_id, "limit": limit, "offset": offset}
                if symbol:
                    conditions.append("symbol = :symbol")
                    params["symbol"] = symbol
                if note_type:
                    conditions.append("note_type = :note_type")
                    params["note_type"] = note_type
                where_clause = " AND ".join(conditions)
                result = session.execute(
                    text(f"""
                        SELECT id, symbol, stock_name, note_type, title, content, tags, 
                               trade_date, profit_rate, created_at, updated_at
                        FROM fact_investment_notes
                        WHERE {where_clause}
                        ORDER BY created_at DESC
                        LIMIT :limit OFFSET :offset
                    """),
                    params
                )
                notes = []
                for row in result:
                    notes.append({
                        "id": row[0],
                        "symbol": row[1],
                        "stock_name": row[2],
                        "note_type": row[3],
                        "title": row[4],
                        "content": row[5],
                        "tags": row[6],
                        "trade_date": row[7].isoformat() if row[7] else None,
                        "profit_rate": float(row[8]) if row[8] else None,
                        "created_at": row[9].isoformat() if row[9] else None,
                        "updated_at": row[10].isoformat() if row[10] else None,
                    })
                return notes
            finally:
                session.close()
        except Exception as e:
            logger.error(f"获取笔记失败: {e}")
            return []

    def get_note_by_id(self, note_id: int, user_id: int = 1) -> Optional[Dict[str, Any]]:
        """获取单条笔记"""
        self._ensure_table()
        try:
            if not self.warehouse.warehouse_service:
                return None
            session = self.warehouse.warehouse_service.get_session()
            try:
                from sqlalchemy import text
                result = session.execute(
                    text("""
                        SELECT id, symbol, stock_name, note_type, title, content, tags,
                               trade_date, profit_rate, created_at, updated_at
                        FROM fact_investment_notes
                        WHERE id = :id AND user_id = :user_id
                    """),
                    {"id": note_id, "user_id": user_id}
                )
                row = result.fetchone()
                if not row:
                    return None
                return {
                    "id": row[0],
                    "symbol": row[1],
                    "stock_name": row[2],
                    "note_type": row[3],
                    "title": row[4],
                    "content": row[5],
                    "tags": row[6],
                    "trade_date": row[7].isoformat() if row[7] else None,
                    "profit_rate": float(row[8]) if row[8] else None,
                    "created_at": row[9].isoformat() if row[9] else None,
                    "updated_at": row[10].isoformat() if row[10] else None,
                }
            finally:
                session.close()
        except Exception as e:
            logger.error(f"获取笔记失败: {e}")
            return None

    def update_note(
        self,
        note_id: int,
        user_id: int = 1,
        title: Optional[str] = None,
        content: Optional[str] = None,
        note_type: Optional[str] = None,
        tags: Optional[str] = None,
    ) -> bool:
        """更新笔记"""
        try:
            if not self.warehouse.warehouse_service:
                return False
            session = self.warehouse.warehouse_service.get_session()
            try:
                from sqlalchemy import text
                updates = ["updated_at = NOW()"]
                params = {"id": note_id, "user_id": user_id}
                if title is not None:
                    updates.append("title = :title")
                    params["title"] = title
                if content is not None:
                    updates.append("content = :content")
                    params["content"] = content
                if note_type is not None:
                    updates.append("note_type = :note_type")
                    params["note_type"] = note_type
                if tags is not None:
                    updates.append("tags = :tags")
                    params["tags"] = tags
                session.execute(
                    text(f"""
                        UPDATE fact_investment_notes
                        SET {", ".join(updates)}
                        WHERE id = :id AND user_id = :user_id
                    """),
                    params
                )
                session.commit()
                return True
            finally:
                session.close()
        except Exception as e:
            logger.error(f"更新笔记失败: {e}")
            return False

    def delete_note(self, note_id: int, user_id: int = 1) -> bool:
        """删除笔记"""
        try:
            if not self.warehouse.warehouse_service:
                return False
            session = self.warehouse.warehouse_service.get_session()
            try:
                from sqlalchemy import text
                session.execute(
                    text("DELETE FROM fact_investment_notes WHERE id = :id AND user_id = :user_id"),
                    {"id": note_id, "user_id": user_id}
                )
                session.commit()
                return True
            finally:
                session.close()
        except Exception as e:
            logger.error(f"删除笔记失败: {e}")
            return False

    def get_lessons_for_stock(self, symbol: str, user_id: int = 1) -> List[Dict[str, Any]]:
        """
        获取某只股票相关的教训/经验笔记（用于 AI 提醒）
        """
        return self.get_notes(user_id=user_id, symbol=symbol, note_type="lesson") + \
               self.get_notes(user_id=user_id, symbol=symbol, note_type="mistake")

    def get_all_lessons(self, user_id: int = 1, limit: int = 20) -> List[Dict[str, Any]]:
        """获取所有教训类笔记"""
        lessons = self.get_notes(user_id=user_id, note_type="lesson", limit=limit)
        mistakes = self.get_notes(user_id=user_id, note_type="mistake", limit=limit)
        all_notes = lessons + mistakes
        all_notes.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return all_notes[:limit]

    def build_lessons_context(self, symbol: Optional[str] = None, user_id: int = 1) -> str:
        """
        构建教训/经验上下文，供 AI 使用
        """
        if symbol:
            notes = self.get_lessons_for_stock(symbol, user_id)
        else:
            notes = self.get_all_lessons(user_id, limit=10)
        
        if not notes:
            return ""
        
        context_parts = ["【历史投资教训】"]
        for n in notes[:5]:
            title = n.get("title", "")
            content = n.get("content", "")[:200]
            stock = n.get("stock_name", "")
            profit = n.get("profit_rate")
            profit_str = f" (盈亏{profit:+.1f}%)" if profit is not None else ""
            line = f"- {stock}{profit_str}: {title} - {content}"
            context_parts.append(line)
        
        return "\n".join(context_parts)

    def sync_notes_to_rag(self, user_id: int = 1) -> Dict[str, Any]:
        """
        将投资笔记同步到 RAG 知识库
        """
        try:
            notes = self.get_notes(user_id=user_id, limit=200)
            if not notes:
                return {"success": True, "message": "无笔记可同步", "synced": 0}
            
            from backend.knowledge_base.rag_service import RAGService
            rag = RAGService()
            
            documents = []
            for n in notes:
                doc_id = f"note_{n['id']}"
                content = f"【{n['title']}】\n类型: {n['note_type']}\n"
                if n.get("stock_name"):
                    content += f"股票: {n['stock_name']} ({n.get('symbol', '')})\n"
                if n.get("profit_rate") is not None:
                    content += f"盈亏: {n['profit_rate']:+.1f}%\n"
                content += f"\n{n['content']}"
                
                documents.append({
                    "id": doc_id,
                    "content": content,
                    "metadata": {
                        "title": n["title"],
                        "category": "投资笔记",
                        "type": n["note_type"],
                        "symbol": n.get("symbol", ""),
                        "stock_name": n.get("stock_name", ""),
                    }
                })
            
            success = rag.add_documents(documents)
            if success:
                return {"success": True, "message": f"同步 {len(documents)} 条笔记到知识库", "synced": len(documents)}
            return {"success": False, "message": "同步失败", "synced": 0}
        except Exception as e:
            logger.error(f"同步笔记到 RAG 失败: {e}")
            return {"success": False, "message": "同步失败，请稍后重试", "synced": 0}
