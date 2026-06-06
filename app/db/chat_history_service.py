from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, delete
from datetime import datetime, timedelta, timezone
from app.models.chat_history import ChatHistory, ChatSummary
from typing import List, Optional, Tuple, Sequence


class ChatHistoryService:
    def __init__(self, db: AsyncSession):
        self.db: AsyncSession = db

    async def get_recent_context(self, user_id: str) -> Tuple[List[dict], Optional[str]]:
        """获取标准对话上下文（基于时间）"""
        # 获取最新摘要
        summary_stmt = (
            select(ChatSummary)
            .where(ChatSummary.user_id == user_id)
            .order_by(ChatSummary.end_date.desc())
            .limit(1)
        )
        result = await self.db.execute(summary_stmt)
        summary = result.scalar_one_or_none()
        summary_text = summary.summary_text if summary else None

        # 获取最近3天的对话
        three_days_ago = datetime.now(timezone.utc) - timedelta(days=3)
        recent_stmt = (
            select(ChatHistory)
            .where(
                and_(
                    ChatHistory.user_id == user_id,
                    ChatHistory.created_at >= three_days_ago,
                    ChatHistory.is_archived == False
                )
            )
            .order_by(ChatHistory.created_at.desc())
        )
        result = await self.db.execute(recent_stmt)
        recent_messages = result.scalars().all()

        # 兜底：如果3天内无对话，加载最近10条
        if not recent_messages:
            fallback_stmt = (
                select(ChatHistory)
                .where(
                    and_(
                        ChatHistory.user_id == user_id,
                        ChatHistory.is_archived == False
                    )
                )
                .order_by(ChatHistory.created_at.desc())
                .limit(10)
            )
            result = await self.db.execute(fallback_stmt)
            fallback_messages = result.scalars().all()
            fallback_messages.reverse()  # 反转回正序
            recent_messages = fallback_messages

        message_list = [
            {"role": msg.role, "content": msg.content}
            for msg in recent_messages
        ]
        return message_list, summary_text

    async def get_lightweight_context(
            self,
            user_id: str,
            max_messages: int = 5
    ) -> Tuple[List[dict], Optional[str]]:
        """获取轻量级对话上下文（基于数量限制）- 专为情感陪伴优化"""
        # 快速获取最新摘要
        summary_stmt = (
            select(ChatSummary)
            .where(ChatSummary.user_id == user_id)
            .order_by(ChatSummary.end_date.desc())
            .limit(1)
        )
        result = await self.db.execute(summary_stmt)
        summary = result.scalar_one_or_none()
        summary_text = summary.summary_text if summary else None

        # 快速获取最近N条对话（不限制时间）
        recent_stmt = (
            select(ChatHistory)
            .where(
                and_(
                    ChatHistory.user_id == user_id,
                    ChatHistory.is_archived == False
                )
            )
            .order_by(ChatHistory.created_at.desc())
            .limit(max_messages)
        )
        result = await self.db.execute(recent_stmt)
        recent_messages = result.scalars().all()

        # 转换格式并反转顺序（按时间正序）
        message_list = [
            {"role": msg.role, "content": msg.content}
            for msg in reversed(recent_messages)
        ]
        return message_list, summary_text

    async def save_conversation_turn(self, user_id: str, user_content: str,
                                     assistant_content: str, model: str, tokens_used: int,
                                     prompt_tokens: int = 0, completion_tokens: int = 0):
        """保存一轮对话（用户消息+助手回复）"""
        # 保存用户消息
        user_msg = ChatHistory(
            user_id=user_id,
            role="user",
            content=user_content,
            model=model
        )
        self.db.add(user_msg)

        # 保存助手回复
        assistant_msg = ChatHistory(
            user_id=user_id,
            role="assistant",
            content=assistant_content,
            model=model,
            token_usage=tokens_used,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens
        )
        self.db.add(assistant_msg)

        await self.db.commit()

    async def get_user_history(
            self,
            user_id: str,
            limit: int = 20,
            offset: int = 0,
            start_date: Optional[datetime] = None,
            end_date: Optional[datetime] = None
    ) -> Tuple[Sequence[ChatHistory], int]:
        """
        获取用户的历史对话记录

        Returns:
            Tuple[记录列表, 总记录数]
            注意：使用Sequence[ChatHistory]而非List[ChatHistory]避免类型检查误报
        """
        # 构建查询条件
        conditions = [ChatHistory.user_id == user_id, ChatHistory.is_archived == False]

        if start_date:
            conditions.append(ChatHistory.created_at >= start_date)
        if end_date:
            conditions.append(ChatHistory.created_at <= end_date)

        # 查询记录（倒序：最新的在前）
        records_stmt = (
            select(ChatHistory)
            .where(and_(*conditions))
            .order_by(ChatHistory.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.db.execute(records_stmt)
        records = result.scalars().all()

        # 查询总数（用于分页）
        count_stmt = (
            select(func.count())
            .select_from(ChatHistory)
            .where(and_(*conditions))
        )
        result = await self.db.execute(count_stmt)
        total = result.scalar()  # 使用scalar()而不是scalar_one()

        if total is None:
            total = 0

        return list(records), int(total)

    async def delete_record(self, record_id: int, user_id: str) -> bool:
        """
        删除单条历史记录

        Args:
            record_id: 记录 ID（整数）
            user_id: 用户 ID（用于权限验证）

        Returns:
            True 删除成功，False 记录不存在
        """
        stmt = delete(ChatHistory).where(
            and_(ChatHistory.id == record_id, ChatHistory.user_id == user_id)
        )
        result = await self.db.execute(stmt)
        await self.db.commit()
        return result.rowcount > 0

    async def delete_records(self, record_ids: List[str], user_id: str) -> int:
        """
        批量删除历史记录

        Args:
            record_ids: 记录 ID 列表
            user_id: 用户 ID（用于权限验证）

        Returns:
            删除的记录数
        """
        stmt = delete(ChatHistory).where(
            and_(ChatHistory.id.in_(record_ids), ChatHistory.user_id == user_id)
        )
        result = await self.db.execute(stmt)
        await self.db.commit()
        return result.rowcount

    async def clear_user_history(self, user_id: str) -> int:
        """
        清除用户所有历史记录

        Args:
            user_id: 用户 ID

        Returns:
            删除的记录数
        """
        stmt = delete(ChatHistory).where(ChatHistory.user_id == user_id)
        result = await self.db.execute(stmt)
        await self.db.commit()
        return result.rowcount