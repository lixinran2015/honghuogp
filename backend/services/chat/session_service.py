"""
会话管理服务
- 多轮对话记忆
- 上下文管理
- 会话持久化
"""

import logging
import threading
import time
import uuid
from datetime import datetime
from typing import List, Dict, Optional, Any
from collections import OrderedDict

logger = logging.getLogger(__name__)


class ChatSession:
    """单个会话"""

    def __init__(self, session_id: str, user_id: int = 1, max_history: int = 20):
        self.session_id = session_id
        self.user_id = user_id
        self.max_history = max_history
        self.messages: List[Dict[str, str]] = []  # [{"role": "user/assistant", "content": "..."}]
        self.created_at = datetime.now()
        self.updated_at = datetime.now()
        self.metadata: Dict[str, Any] = {}  # 可存储当前讨论的股票、话题等

    def add_message(self, role: str, content: str):
        """添加消息"""
        self.messages.append({"role": role, "content": content, "timestamp": time.time()})
        self.updated_at = datetime.now()
        # 保留最近 max_history 条
        if len(self.messages) > self.max_history:
            self.messages = self.messages[-self.max_history:]

    def get_context_messages(self, limit: int = 10) -> List[Dict[str, str]]:
        """获取上下文消息（用于 API 调用）"""
        recent = self.messages[-limit:] if len(self.messages) > limit else self.messages
        return [{"role": m["role"], "content": m["content"]} for m in recent]

    def get_summary(self) -> str:
        """生成会话摘要（用于长对话）"""
        if len(self.messages) < 4:
            return ""
        # 简单拼接最近几轮
        summary_parts = []
        for m in self.messages[-6:]:
            role_label = "用户" if m["role"] == "user" else "AI"
            summary_parts.append(f"{role_label}: {m['content'][:100]}")
        return "\n".join(summary_parts)

    def set_current_stock(self, symbol: str, name: str):
        """设置当前讨论的股票"""
        self.metadata["current_stock"] = {"symbol": symbol, "name": name}

    def get_current_stock(self) -> Optional[Dict[str, str]]:
        """获取当前讨论的股票"""
        return self.metadata.get("current_stock")

    def clear(self):
        """清空会话"""
        self.messages = []
        self.metadata = {}
        self.updated_at = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        """序列化"""
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "messages": self.messages,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "message_count": len(self.messages),
        }


class SessionService:
    """会话管理服务"""

    def __init__(self, max_sessions: int = 100, session_ttl: int = 3600 * 24):
        """
        Args:
            max_sessions: 最大会话数（LRU淘汰）
            session_ttl: 会话过期时间（秒）
        """
        self.max_sessions = max_sessions
        self.session_ttl = session_ttl
        self._sessions: OrderedDict[str, ChatSession] = OrderedDict()
        self._lock = threading.Lock()

    def get_or_create_session(self, session_id: Optional[str] = None, user_id: int = 1) -> ChatSession:
        """获取或创建会话"""
        with self._lock:
            if session_id and session_id in self._sessions:
                session = self._sessions[session_id]
                # 检查是否过期
                if (datetime.now() - session.updated_at).total_seconds() > self.session_ttl:
                    session.clear()  # 过期则清空
                # 移到末尾（LRU）
                self._sessions.move_to_end(session_id)
                return session

            # 创建新会话（使用完整 UUID 避免碰撞）
            new_id = session_id or str(uuid.uuid4())
            session = ChatSession(new_id, user_id)
            self._sessions[new_id] = session

            # LRU 淘汰
            while len(self._sessions) > self.max_sessions:
                self._sessions.popitem(last=False)

            return session

    def get_session(self, session_id: str) -> Optional[ChatSession]:
        """获取会话"""
        with self._lock:
            return self._sessions.get(session_id)

    def delete_session(self, session_id: str) -> bool:
        """删除会话"""
        with self._lock:
            if session_id in self._sessions:
                del self._sessions[session_id]
                return True
            return False

    def list_sessions(self, user_id: int = 1) -> List[Dict[str, Any]]:
        """列出用户的会话"""
        with self._lock:
            snapshot = list(self._sessions.items())
        result = []
        for sid, session in snapshot:
            if session.user_id == user_id:
                result.append({
                    "session_id": sid,
                    "message_count": len(session.messages),
                    "updated_at": session.updated_at.isoformat(),
                    "current_stock": session.get_current_stock(),
                })
        return sorted(result, key=lambda x: x["updated_at"], reverse=True)

    def cleanup_expired(self):
        """清理过期会话"""
        now = datetime.now()
        with self._lock:
            expired = [
                sid for sid, session in self._sessions.items()
                if (now - session.updated_at).total_seconds() > self.session_ttl
            ]
            for sid in expired:
                del self._sessions[sid]
        if expired:
            logger.info(f"清理 {len(expired)} 个过期会话")


# 全局单例
_session_service: Optional[SessionService] = None
_session_service_lock = threading.Lock()


def get_session_service() -> SessionService:
    """获取会话服务单例（线程安全）"""
    global _session_service
    if _session_service is None:
        with _session_service_lock:
            if _session_service is None:
                _session_service = SessionService()
    return _session_service
