"""
Memory 模块 - Agent 记忆系统

提供对话历史、知识和上下文管理能力
支持语义搜索（基于 embedding 余弦相似度）
"""

import json
import time
import asyncio
import math
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime
from collections import defaultdict
import logging

from app.utils.AiCodeUtil import get_embedding

logger = logging.getLogger(__name__)

# 语义搜索相似度阈值
SEMANTIC_SIMILARITY_THRESHOLD = 0.65


def cosine_similarity(a: List[float], b: List[float]) -> float:
    """计算两个向量的余弦相似度"""
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


@dataclass
class MemoryEntry:
    """记忆条目"""
    id: Optional[str] = None
    type: str = "conversation"  # "user", "assistant", "tool", "knowledge", "reflection"
    content: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    embedding: Optional[List[float]] = None
    importance: float = 1.0  # 0.0-1.0，越高越重要

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "type": self.type,
            "content": self.content,
            "metadata": self.metadata,
            "timestamp": self.timestamp,
            "importance": self.importance
        }


class BaseMemory:
    """记忆基类"""

    def add(self, entry: MemoryEntry) -> None:
        raise NotImplementedError

    def get_recent(self, limit: int = 10) -> List[MemoryEntry]:
        raise NotImplementedError

    def search(self, query: str, limit: int = 5) -> List[MemoryEntry]:
        raise NotImplementedError

    async def search_async(self, query: str, limit: int = 5) -> List[MemoryEntry]:
        """基于语义的异步搜索（使用 embedding 余弦相似度）"""
        raise NotImplementedError

    def clear(self) -> None:
        raise NotImplementedError


class ConversationMemory(BaseMemory):
    """对话历史记忆（支持自动压缩）"""

    # 触发压缩的阈值（条目数）
    COMPRESSION_THRESHOLD = 15
    # 压缩后保留的条目数
    COMPRESSED_ENTRIES = 5

    def __init__(self, max_entries: int = 100):
        self.max_entries = max_entries
        self._entries: List[MemoryEntry] = []
        self._counter = 0
        self._is_compressed = False  # 是否已压缩过

    def add(self, entry: MemoryEntry) -> None:
        if entry.id is None:
            entry.id = f"conv_{self._counter}"
            self._counter += 1

        self._entries.append(entry)

        # 超过阈值时自动压缩
        if len(self._entries) > self.COMPRESSION_THRESHOLD and not self._is_compressed:
            self._compress_old_entries()

        if len(self._entries) > self.max_entries:
            self._entries = self._entries[-self.max_entries:]

        logger.debug(f"对话记忆添加: {entry.type} - {len(self._entries)} 条")

    def _compress_old_entries(self):
        """压缩旧对话条目为摘要"""
        if len(self._entries) <= self.COMPRESSION_THRESHOLD:
            return

        # 保留最新的 COMPRESSED_ENTRIES 条
        recent_entries = self._entries[-self.COMPRESSED_ENTRIES:]

        # 将旧条目压缩为一条摘要
        old_entries = self._entries[:-self.COMPRESSED_ENTRIES]
        summary_parts = []
        
        # 按类型分组统计
        type_counts = defaultdict(int)
        key_topics = set()
        
        for entry in old_entries:
            type_counts[entry.type] += 1
            # 提取关键词（简单实现）
            content_words = entry.content.split()[:50]
            key_topics.update(content_words[:10])

        summary = (
            f"[对话摘要] 共 {len(old_entries)} 条历史记录，"
            f"包含 {type_counts.get('user', 0)} 条用户消息，"
            f"{type_counts.get('assistant', 0)} 条 AI 回复。"
            f"主要话题: {', '.join(list(key_topics)[:5])}"
        )

        # 创建摘要条目
        summary_entry = MemoryEntry(
            id=f"compressed_{len(self._entries)}",
            type="summary",
            content=summary,
            importance=0.5
        )

        # 保留摘要和最新条目
        self._entries = [summary_entry] + recent_entries
        self._is_compressed = True
        logger.info(f"对话记忆已压缩: {len(old_entries)} 条 -> 1 条摘要")

    def get_recent(self, limit: int = 10) -> List[MemoryEntry]:
        return self._entries[-limit:] if self._entries else []

    def get_with_context(self, max_tokens: int = 4000) -> str:
        """获取适合上下文的对话历史（自动包含摘要）"""
        result = []
        total_chars = 0

        for entry in reversed(self._entries):
            entry_text = f"[{entry.type.upper()}] {entry.content}"
            entry_len = len(entry_text)

            if total_chars + entry_len > max_tokens:
                break

            result.insert(0, entry_text)
            total_chars += entry_len

        return "\n".join(result)

    def search(self, query: str, limit: int = 5) -> List[MemoryEntry]:
        query_lower = query.lower()
        scored = []

        for entry in self._entries:
            if query_lower in entry.content.lower():
                scored.append((entry.importance, entry.timestamp, entry))

        scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
        return [e for _, _, e in scored[:limit]]

    async def search_async(self, query: str, limit: int = 5) -> List[MemoryEntry]:
        """基于语义的异步搜索（使用 embedding 余弦相似度）"""
        try:
            query_embedding = await get_embedding(query)
        except Exception as e:
            logger.warning(f"获取 query embedding 失败，回退到字符串搜索: {e}")
            return self.search(query, limit)

        scored = []
        for entry in self._entries:
            if entry.embedding:
                similarity = cosine_similarity(query_embedding, entry.embedding)
                if similarity >= SEMANTIC_SIMILARITY_THRESHOLD:
                    scored.append((similarity, entry.importance, entry.timestamp, entry))

        scored.sort(key=lambda x: (x[0], x[1], x[2]), reverse=True)
        return [e for _, _, _, e in scored[:limit]]

    def clear(self) -> None:
        self._entries.clear()
        self._is_compressed = False

    def get_summary(self) -> Dict[str, Any]:
        """获取记忆摘要"""
        types = defaultdict(int)
        for entry in self._entries:
            types[entry.type] += 1

        return {
            "total_entries": len(self._entries),
            "types": dict(types),
            "oldest": self._entries[0].timestamp if self._entries else None,
            "newest": self._entries[-1].timestamp if self._entries else None,
            "is_compressed": self._is_compressed
        }


class KnowledgeMemory(BaseMemory):
    """知识记忆 - 存储学到的知识和事实"""

    def __init__(self, max_entries: int = 500):
        self.max_entries = max_entries
        self._entries: Dict[str, MemoryEntry] = {}
        self._access_times: Dict[str, float] = {}
        self._counter = 0

    def add(self, entry: MemoryEntry) -> None:
        key = entry.metadata.get("key") or entry.content[:100]
        entry.id = key
        self._entries[key] = entry
        self._access_times[key] = time.time()

        if len(self._entries) > self.max_entries:
            self._evict_lru()

        logger.debug(f"知识记忆添加: {key}")

    def _evict_lru(self) -> None:
        if not self._entries:
            return

        lru_key = min(self._access_times.items(), key=lambda x: x[1])[0]
        del self._entries[lru_key]
        del self._access_times[lru_key]

    def get(self, key: str) -> Optional[MemoryEntry]:
        if key in self._entries:
            self._access_times[key] = time.time()
            return self._entries[key]
        return None

    def get_recent(self, limit: int = 10) -> List[MemoryEntry]:
        entries = sorted(
            self._entries.values(),
            key=lambda e: self._access_times.get(e.id, 0),
            reverse=True
        )
        return entries[:limit]

    def search(self, query: str, limit: int = 5) -> List[MemoryEntry]:
        query_lower = query.lower()
        results = []

        for entry in self._entries.values():
            if query_lower in entry.content.lower():
                results.append(entry)

        results.sort(key=lambda e: e.importance, reverse=True)
        return results[:limit]

    async def search_async(self, query: str, limit: int = 5) -> List[MemoryEntry]:
        """基于语义的异步搜索"""
        try:
            query_embedding = await get_embedding(query)
        except Exception as e:
            logger.warning(f"获取 query embedding 失败: {e}")
            return self.search(query, limit)

        scored = []
        for entry in self._entries.values():
            if entry.embedding:
                similarity = cosine_similarity(query_embedding, entry.embedding)
                if similarity >= SEMANTIC_SIMILARITY_THRESHOLD:
                    scored.append((similarity, entry.importance, entry))

        scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
        return [e for _, _, e in scored[:limit]]

    def clear(self) -> None:
        self._entries.clear()
        self._access_times.clear()

    def update_importance(self, key: str, importance: float) -> None:
        if key in self._entries:
            self._entries[key].importance = max(0.0, min(1.0, importance))


class ReflectionMemory(BaseMemory):
    """反思记忆 - 存储自我反思和总结"""

    def __init__(self, max_entries: int = 50):
        self.max_entries = max_entries
        self._entries: List[MemoryEntry] = []
        self._counter = 0

    def add(self, entry: MemoryEntry) -> None:
        entry.id = f"refl_{self._counter}"
        self._counter += 1
        entry.type = "reflection"
        entry.importance = 0.8

        self._entries.append(entry)

        if len(self._entries) > self.max_entries:
            self._entries = self._entries[-self.max_entries:]

        logger.debug(f"反思记忆添加: {entry.content[:50]}...")

    def add_reflection(self, content: str, metadata: Dict = None) -> None:
        entry = MemoryEntry(
            id=f"refl_{self._counter}",
            type="reflection",
            content=content,
            metadata=metadata or {},
            importance=0.8
        )
        self._counter += 1
        self.add(entry)

    def get_recent(self, limit: int = 10) -> List[MemoryEntry]:
        return self._entries[-limit:] if self._entries else []

    def get_insights(self) -> List[str]:
        return [e.content for e in self._entries[-5:] if e.type == "reflection"]

    def search(self, query: str, limit: int = 5) -> List[MemoryEntry]:
        query_lower = query.lower()
        return [
            e for e in reversed(self._entries)
            if query_lower in e.content.lower()
        ][:limit]

    async def search_async(self, query: str, limit: int = 5) -> List[MemoryEntry]:
        """基于语义的异步搜索"""
        try:
            query_embedding = await get_embedding(query)
        except Exception as e:
            logger.warning(f"获取 query embedding 失败: {e}")
            return self.search(query, limit)

        scored = []
        for entry in self._entries:
            if entry.embedding:
                similarity = cosine_similarity(query_embedding, entry.embedding)
                if similarity >= SEMANTIC_SIMILARITY_THRESHOLD:
                    scored.append((similarity, entry.importance, entry))

        scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
        return [e for _, _, e in scored[:limit]]

    def clear(self) -> None:
        self._entries.clear()


class AgentMemory:
    """
    Agent 记忆系统 - 整合多种记忆类型
    """

    def __init__(
        self,
        conversation_max: int = 100,
        knowledge_max: int = 500,
        reflection_max: int = 50
    ):
        self.conversation = ConversationMemory(max_entries=conversation_max)
        self.knowledge = KnowledgeMemory(max_entries=knowledge_max)
        self.reflection = ReflectionMemory(max_entries=reflection_max)

        self._session_id: Optional[str] = None
        self._created_at = time.time()

    @property
    def session_id(self) -> str:
        if self._session_id is None:
            self._session_id = f"session_{int(self._created_at)}"
        return self._session_id

    def add_user_message(self, content: str, metadata: Dict = None) -> None:
        entry = MemoryEntry(
            id=f"user_{int(time.time() * 1000)}",
            type="user",
            content=content,
            metadata=metadata or {}
        )
        self.conversation.add(entry)

    def add_assistant_message(self, content: str, metadata: Dict = None) -> None:
        entry = MemoryEntry(
            id=f"asst_{int(time.time() * 1000)}",
            type="assistant",
            content=content,
            metadata=metadata or {}
        )
        self.conversation.add(entry)

    def add_tool_result(self, tool_name: str, result: str, success: bool = True) -> None:
        entry = MemoryEntry(
            id=f"tool_{int(time.time() * 1000)}",
            type="tool",
            content=f"[{tool_name}] {'成功' if success else '失败'}: {result[:200]}",
            metadata={"tool": tool_name, "success": success}
        )
        self.conversation.add(entry)

    def add_knowledge(self, content: str, key: str = None, importance: float = 0.5) -> None:
        entry = MemoryEntry(
            id=key or f"know_{int(time.time() * 1000)}",
            type="knowledge",
            content=content,
            metadata={"key": key} if key else {},
            importance=importance
        )
        self.knowledge.add(entry)

    def add_reflection(self, content: str, metadata: Dict = None) -> None:
        self.reflection.add_reflection(content, metadata)

    def get_context_for_prompt(self, max_tokens: int = 4000) -> str:
        """构建用于 prompt 的上下文"""
        parts = []

        insights = self.reflection.get_insights()
        if insights:
            parts.append("【反思总结】")
            parts.extend(insights[-3:])
            parts.append("")

        recent_knowledge = self.knowledge.get_recent(limit=3)
        if recent_knowledge:
            parts.append("【相关知识】")
            for e in recent_knowledge:
                parts.append(f"- {e.content}")
            parts.append("")

        conversation_context = self.conversation.get_with_context(max_tokens=max_tokens // 2)
        if conversation_context:
            parts.append("【对话历史】")
            parts.append(conversation_context)

        return "\n".join(parts)

    def get_full_context(self) -> Dict[str, Any]:
        """获取完整上下文"""
        return {
            "session_id": self.session_id,
            "conversation_summary": self.conversation.get_summary(),
            "recent_knowledge": [e.to_dict() for e in self.knowledge.get_recent(5)],
            "recent_reflections": [e.content for e in self.reflection.get_recent(5)],
            "created_at": self._created_at,
            "last_updated": time.time()
        }

    async def search_async(self, query: str, limit: int = 5) -> Dict[str, List]:
        """统一的语义搜索入口，搜索所有记忆类型"""
        results = {
            "conversation": await self.conversation.search_async(query, limit),
            "knowledge": await self.knowledge.search_async(query, limit),
            "reflection": await self.reflection.search_async(query, limit)
        }
        return results

    def clear_session(self) -> None:
        """清除会话记忆（保留知识）"""
        self.conversation.clear()
        self._session_id = f"session_{int(time.time())}"

    def clear_all(self) -> None:
        """清除所有记忆"""
        self.conversation.clear()
        self.knowledge.clear()
        self.reflection.clear()
        self._session_id = None

    async def save_to_storage(self, storage_path: str) -> bool:
        """保存记忆到存储"""
        try:
            data = {
                "session_id": self._session_id,
                "created_at": self._created_at,
                "conversation": [e.to_dict() for e in self.conversation.get_recent(100)],
                "knowledge": [e.to_dict() for e in self.knowledge.get_recent(100)],
                "reflections": [e.to_dict() for e in self.reflection.get_recent(50)]
            }

            async def _write_json():
                with open(storage_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)

            await asyncio.to_thread(_write_json)

            logger.info(f"记忆已保存到 {storage_path}")
            return True
        except Exception as e:
            logger.error(f"保存记忆失败: {e}")
            return False

    async def load_from_storage(self, storage_path: str) -> bool:
        """从存储加载记忆"""
        try:
            async def _read_json():
                with open(storage_path, 'r', encoding='utf-8') as f:
                    return json.load(f)

            data = await asyncio.to_thread(_read_json)

            self._session_id = data.get("session_id")
            self._created_at = data.get("created_at", time.time())

            for e in data.get("conversation", []):
                self.conversation.add(MemoryEntry(**e))

            for e in data.get("knowledge", []):
                self.knowledge.add(MemoryEntry(**e))

            for e in data.get("reflections", []):
                self.reflection.add(MemoryEntry(**e))

            logger.info(f"记忆已从 {storage_path} 加载")
            return True
        except Exception as e:
            logger.error(f"加载记忆失败: {e}")
            return False
