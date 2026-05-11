"""
Agent Memory Service

提供 Agent 记忆的数据库操作服务
"""

import json
from typing import List, Dict, Any, Optional
from datetime import datetime
from sqlalchemy import select, update, delete, desc, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.agent_memory import (
    AgentSession,
    MemoryEntry,
    AgentReflection,
    KnowledgeEntry,
    ToolExecutionLog,
    ModelUsageStats,
)


class AgentMemoryService:
    """Agent 记忆服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_session(
        self,
        user_id: int,
        session_type: str = "general",
        model_key: str = "deepseek-r1-qwen3-8b"
    ) -> AgentSession:
        """创建新会话"""
        session = AgentSession(
            user_id=user_id,
            session_type=session_type,
            model_key=model_key
        )
        self.db.add(session)
        await self.db.commit()
        await self.db.refresh(session)
        return session

    async def get_session(self, session_id: str) -> Optional[AgentSession]:
        """获取会话"""
        result = await self.db.execute(
            select(AgentSession).where(AgentSession.id == session_id)
        )
        return result.scalar_one_or_none()

    async def get_user_sessions(
        self,
        user_id: int,
        limit: int = 20,
        offset: int = 0
    ) -> List[AgentSession]:
        """获取用户的所有会话"""
        result = await self.db.execute(
            select(AgentSession)
            .where(AgentSession.user_id == user_id)
            .order_by(desc(AgentSession.created_at))
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def end_session(
        self,
        session_id: str,
        success: bool = True,
        total_steps: int = 0,
        total_tokens: int = 0
    ) -> Optional[AgentSession]:
        """结束会话"""
        session = await self.get_session(session_id)
        if session:
            session.ended_at = datetime.utcnow()
            session.success = success
            session.total_steps = total_steps
            session.total_tokens = total_tokens
            await self.db.commit()
            await self.db.refresh(session)
        return session

    async def add_memory_entry(
        self,
        session_id: str,
        entry_type: str,
        content: str,
        extra_data: Dict = None,
        importance: float = 1.0
    ) -> MemoryEntry:
        """添加记忆条目"""
        entry = MemoryEntry(
            session_id=session_id,
            entry_type=entry_type,
            content=content,
            extra_data=extra_data or {},
            importance=importance
        )
        self.db.add(entry)
        await self.db.commit()
        await self.db.refresh(entry)
        return entry

    async def get_session_memory(
        self,
        session_id: str,
        entry_type: str = None,
        limit: int = 100
    ) -> List[MemoryEntry]:
        """获取会话的记忆"""
        query = select(MemoryEntry).where(MemoryEntry.session_id == session_id)

        if entry_type:
            query = query.where(MemoryEntry.entry_type == entry_type)

        query = query.order_by(desc(MemoryEntry.created_at)).limit(limit)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_memory_context(
        self,
        session_id: str,
        max_entries: int = 50
    ) -> str:
        """构建记忆上下文文本"""
        entries = await self.get_session_memory(session_id, limit=max_entries)

        parts = []
        for entry in reversed(entries):
            role = entry.entry_type.upper()
            parts.append(f"[{role}] {entry.content}")

        return "\n".join(parts)

    async def add_reflection(
        self,
        session_id: str,
        task: str,
        reflection: str,
        insights: List[str] = None,
        confidence: float = 0.5
    ) -> AgentReflection:
        """添加反思"""
        refl = AgentReflection(
            session_id=session_id,
            task=task,
            reflection=reflection,
            insights=insights or [],
            confidence=confidence
        )
        self.db.add(refl)
        await self.db.commit()
        await self.db.refresh(refl)
        return refl

    async def get_session_reflections(
        self,
        session_id: str,
        limit: int = 10
    ) -> List[AgentReflection]:
        """获取会话的反思"""
        result = await self.db.execute(
            select(AgentReflection)
            .where(AgentReflection.session_id == session_id)
            .order_by(desc(AgentReflection.created_at))
            .limit(limit)
        )
        return list(result.scalars().all())

    async def add_knowledge(
        self,
        user_id: int,
        content: str,
        knowledge_key: str = None,
        category: str = "general",
        source: str = "agent",
        importance: float = 0.5
    ) -> KnowledgeEntry:
        """添加知识"""
        knowledge = KnowledgeEntry(
            user_id=user_id,
            knowledge_key=knowledge_key,
            content=content,
            category=category,
            source=source,
            importance=importance
        )
        self.db.add(knowledge)
        await self.db.commit()
        await self.db.refresh(knowledge)
        return knowledge

    async def search_knowledge(
        self,
        user_id: int,
        query: str,
        category: str = None,
        limit: int = 10
    ) -> List[KnowledgeEntry]:
        """搜索知识"""
        q = select(KnowledgeEntry).where(
            and_(
                KnowledgeEntry.user_id == user_id,
                KnowledgeEntry.content.ilike(f"%{query}%")
            )
        )

        if category:
            q = q.where(KnowledgeEntry.category == category)

        q = q.order_by(desc(KnowledgeEntry.importance), desc(KnowledgeEntry.usage_count)).limit(limit)

        result = await self.db.execute(q)
        return list(result.scalars().all())

    async def increment_knowledge_usage(self, knowledge_id: str) -> None:
        """增加知识使用次数"""
        knowledge = await self.db.get(KnowledgeEntry, knowledge_id)
        if knowledge:
            knowledge.usage_count += 1
            knowledge.last_used_at = datetime.utcnow()
            await self.db.commit()

    async def get_user_knowledge(
        self,
        user_id: int,
        category: str = None,
        limit: int = 50
    ) -> List[KnowledgeEntry]:
        """获取用户的知识库"""
        q = select(KnowledgeEntry).where(KnowledgeEntry.user_id == user_id)

        if category:
            q = q.where(KnowledgeEntry.category == category)

        q = q.order_by(desc(KnowledgeEntry.importance), desc(KnowledgeEntry.updated_at)).limit(limit)

        result = await self.db.execute(q)
        return list(result.scalars().all())

    async def log_tool_execution(
        self,
        session_id: str,
        tool_name: str,
        tool_params: Dict,
        result: str,
        success: bool = True,
        error_message: str = None,
        execution_time: float = 0
    ) -> ToolExecutionLog:
        """记录工具执行"""
        log = ToolExecutionLog(
            session_id=session_id,
            tool_name=tool_name,
            tool_params=tool_params,
            tool_result=result[:10000] if result else None,
            success=success,
            error_message=error_message,
            execution_time=execution_time
        )
        self.db.add(log)
        await self.db.commit()
        await self.db.refresh(log)
        return log

    async def update_model_stats(
        self,
        user_id: int,
        model_key: str,
        model_name: str,
        tokens: int = 0,
        success: bool = True,
        execution_time: float = 0
    ) -> ModelUsageStats:
        """更新模型使用统计"""
        result = await self.db.execute(
            select(ModelUsageStats).where(
                and_(
                    ModelUsageStats.user_id == user_id,
                    ModelUsageStats.model_key == model_key
                )
            )
        )
        stats = result.scalar_one_or_none()

        if stats:
            stats.request_count += 1
            stats.total_tokens += tokens
            if success:
                stats.success_count += 1
            else:
                stats.failure_count += 1

            total_requests = stats.success_count + stats.failure_count
            if total_requests > 0:
                stats.avg_execution_time = (
                    (stats.avg_execution_time * (total_requests - 1) + execution_time) / total_requests
                )

            stats.last_used_at = datetime.utcnow()
        else:
            stats = ModelUsageStats(
                user_id=user_id,
                model_key=model_key,
                model_name=model_name,
                request_count=1,
                total_tokens=tokens,
                success_count=1 if success else 0,
                failure_count=0 if success else 1,
                avg_execution_time=execution_time,
                last_used_at=datetime.utcnow()
            )
            self.db.add(stats)

        await self.db.commit()
        await self.db.refresh(stats)
        return stats

    async def get_user_model_stats(
        self,
        user_id: int
    ) -> List[ModelUsageStats]:
        """获取用户的模型使用统计"""
        result = await self.db.execute(
            select(ModelUsageStats)
            .where(ModelUsageStats.user_id == user_id)
            .order_by(desc(ModelUsageStats.last_used_at))
        )
        return list(result.scalars().all())

    async def delete_session(self, session_id: str) -> bool:
        """删除会话"""
        session = await self.get_session(session_id)
        if session:
            await self.db.delete(session)
            await self.db.commit()
            return True
        return False

    async def get_session_summary(self, session_id: str) -> Dict[str, Any]:
        """获取会话摘要"""
        session = await self.get_session(session_id)
        if not session:
            return {}

        memory_count = len(await self.get_session_memory(session_id))
        reflections = await self.get_session_reflections(session_id)

        return {
            "session_id": session.id,
            "session_type": session.session_type,
            "model_key": session.model_key,
            "total_steps": session.total_steps,
            "total_tokens": session.total_tokens,
            "success": session.success,
            "memory_entries": memory_count,
            "reflections": len(reflections),
            "created_at": session.created_at.isoformat() if session.created_at else None,
            "ended_at": session.ended_at.isoformat() if session.ended_at else None,
        }
