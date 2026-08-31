# app/services/chat_archiver.py
"""
对话归档服务
每 10 天执行一次，将 3-13 天前的对话提取摘要后硬删除
摘要由 AI 生成，确保保留真正重要的信息

优化点：
- 批量处理 + 独立事务，防止单用户失败影响全局
- AI 调用带重试机制和并发控制
- 内存优化，防止 OOM
- 详细性能监控日志
"""
import logging
import time
import asyncio
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime, timedelta
from typing import List, Optional

from sqlalchemy import select, and_, delete, distinct
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat_history import ChatHistory, ChatSummary
from app.utils import call_llm
from app.db.database import async_session
from app.agent.models import DEFAULT_REASONING_MODEL
from app.services.girlai_state_adapter import (
    delete_messages_for_legacy_ids,
    save_summary_checkpoint,
)

logger = logging.getLogger(__name__)


class ChatArchiver:
    """负责定期归档用户对话，控制数据库存储大小"""

    # 类级别信号量，控制并发 AI 调用数
    _ai_semaphore = asyncio.Semaphore(3)

    def __init__(self, db: AsyncSession):
        self.db = db

    async def archive_all_users(self, days_ago_start: int = 3, days_ago_end: int = 13, batch_size: int = 100) -> None:
        """
        归档所有用户的旧消息（每 10 天调用一次）
        
        优化：
        - 分批获取用户，避免一次性加载过多
        - 每个用户独立会话和事务，失败不影响其他用户
        """
        total_users = 0
        success_count = 0
        failed_users = []
        
        try:
            logger.info(f"开始归档任务 | 时间范围={days_ago_start}-{days_ago_end} 天前")
            
            offset = 0
            
            while True:
                batch_start = time.time()
                
                # 分批获取用户 ID
                user_stmt = (
                    select(distinct(ChatHistory.user_id))
                    .limit(batch_size)
                    .offset(offset)
                )
                result = await self.db.execute(user_stmt)
                user_ids = result.scalars().all()
                
                if not user_ids:
                    logger.info(f"归档任务全部完成 | 总用户数={total_users} | 成功={success_count} | 失败={len(failed_users)}")
                    break
                
                logger.info(f"处理批次 | 偏移量={offset} | 本批用户数={len(user_ids)}")
                
                # 为每个用户创建独立会话
                for user_id in user_ids:
                    async with async_session() as session:
                        archiver = ChatArchiver(session)
                        try:
                            await archiver._archive_user(
                                user_id, 
                                days_ago_start, 
                                days_ago_end
                            )
                            await session.commit()
                            success_count += 1
                        except (ValueError, TypeError, RuntimeError, OSError, SQLAlchemyError) as e:
                            logger.error(f"用户 {user_id} 归档失败：{e}", exc_info=True)
                            await session.rollback()
                            failed_users.append(user_id)
                            # 继续处理下一个用户
                
                total_users += len(user_ids)
                batch_duration = time.time() - batch_start
                logger.debug(f"批次处理完成 | 耗时={batch_duration:.2f}s")
                
                offset += batch_size
            
            if failed_users:
                logger.warning(f"失败用户列表：{failed_users[:10]}{'...' if len(failed_users) > 10 else ''}")
            
            logger.info("归档任务全部完成")
            
        except (ValueError, TypeError, RuntimeError, OSError, SQLAlchemyError) as e:
            logger.error(f"归档任务异常：{e}", exc_info=True)
            raise

    async def _archive_user(self, user_id: int, days_ago_start: int, days_ago_end: int) -> None:
        """
        归档单个用户的对话
        
        优化：
        - 添加时间重叠检测，避免重复生成摘要
        - 详细的性能日志
        """
        start_time = time.time()
        now = datetime.utcnow()
        start_date = now - timedelta(days=days_ago_start)
        end_date = now - timedelta(days=days_ago_end)
        
        try:
            # 检查是否已在此周期内归档过
            last_summary_stmt = (
                select(ChatSummary)
                .where(ChatSummary.user_id == user_id)
                .order_by(ChatSummary.end_date.desc())
                .limit(1)
            )
            
            result = await self.db.execute(last_summary_stmt)
            last_summary = result.scalar_one_or_none()
            
            # 如果最近归档时间大于 end_date，说明已处理过，跳过
            if last_summary and last_summary.end_date > end_date:
                logger.debug(f"用户 {user_id} 已在此周期内归档过 (最后归档：{last_summary.end_date})，跳过处理")
                return
            
            # 检查时间重叠
            overlap_check = (
                select(ChatSummary)
                .where(
                    and_(
                        ChatSummary.user_id == user_id,
                        ChatSummary.start_date <= end_date,
                        ChatSummary.end_date >= start_date
                    )
                )
            )
            result = await self.db.execute(overlap_check)
            if result.scalar_one_or_none():
                logger.info(f"用户 {user_id} 在此时间段已有摘要，跳过")
                return
            
            # 获取指定时间范围的对话
            old_stmt = (
                select(ChatHistory)
                .where(
                    and_(
                        ChatHistory.user_id == user_id,
                        ChatHistory.created_at >= end_date,
                        ChatHistory.created_at < start_date,
                        ChatHistory.is_archived == False
                    )
                )
                .order_by(ChatHistory.created_at.asc())
            )
            
            result = await self.db.execute(old_stmt)
            old_messages = result.scalars().all()
            
            if not old_messages:
                logger.debug(f"用户 {user_id} 没有需要归档的旧消息")
                return
            
            # 使用 AI 生成摘要（带并发控制）
            summary_text = await self._generate_summary_with_ai(old_messages)
            
            # 创建摘要记录
            summary = ChatSummary(
                user_id=user_id,
                summary_text=summary_text,
                start_date=old_messages[0].created_at,
                end_date=old_messages[-1].created_at
            )
            self.db.add(summary)
            await self.db.flush()
            await save_summary_checkpoint(
                self.db,
                user_id,
                summary_text,
                old_messages[0].created_at,
                old_messages[-1].created_at,
                str(summary.id),
            )
            
            # 硬删除已归档的原始消息
            message_ids = [msg.id for msg in old_messages]
            delete_stmt = delete(ChatHistory).where(ChatHistory.id.in_(message_ids))
            deleted_count = await self.db.execute(delete_stmt)
            await delete_messages_for_legacy_ids(self.db, user_id, message_ids)
            
            # 性能日志
            duration = time.time() - start_time
            logger.info(
                f"用户 {user_id} 归档成功 | "
                f"消息数={len(old_messages)} | "
                f"删除数={deleted_count.rowcount} | "
                f"耗时={duration:.2f}s | "
                f"摘要长度={len(summary_text)}"
            )
            
        except (ValueError, TypeError, RuntimeError, OSError, SQLAlchemyError) as e:
            await self.db.rollback()
            logger.error(f"用户 {user_id} 归档失败：{e}", exc_info=True)
            raise

    async def _generate_summary_with_ai(self, messages: List[ChatHistory]) -> str:
        """
        调用 AI 生成摘要（带重试机制和并发控制）
        
        优化：
        - 指数退避重试（最多 3 次）
        - 信号量控制并发
        - 详细的失败日志
        """
        async with self._ai_semaphore:
            max_retries = 3
            base_delay = 1.0  # 秒
            
            for attempt in range(max_retries):
                try:
                    # 构建对话文本
                    conversation_text = self._build_conversation_text(messages)
                    
                    # 构建摘要 prompt
                    summary_prompt = self._build_summary_prompt(conversation_text)
                    
                    # 调用 AI 生成摘要
                    response = await call_llm(
                        model=DEFAULT_REASONING_MODEL,
                        prompt=summary_prompt,
                        stream=False,
                        max_tokens=300,
                        thinking_budget=256
                    )
                    
                    summary = response["choices"][0]["message"]["content"].strip()
                    
                    # 验证并限制摘要长度
                    if len(summary) > 800:
                        summary = summary[:797] + "..."
                    
                    logger.debug(f"AI 生成摘要成功 (尝试 {attempt + 1}/{max_retries}) | 长度={len(summary)}")
                    return summary
                
                except (ValueError, TypeError, RuntimeError, OSError, SQLAlchemyError) as e:
                    logger.warning(f"AI 摘要生成失败 (尝试 {attempt + 1}/{max_retries}): {e}")
                    
                    if attempt == max_retries - 1:
                        logger.error("AI 重试耗尽，降级到简单摘要", exc_info=True)
                        return self._fallback_summary(messages)
                    
                    # 指数退避：1s, 2s, 4s
                    delay = base_delay * (2 ** attempt)
                    await asyncio.sleep(delay)
            
            return self._fallback_summary(messages)

    def _build_conversation_text(self, messages: List[ChatHistory]) -> str:
        """
        将消息列表转换为适合 AI 理解的对话文本格式
        
        优化：
        - 限制总长度，防止 OOM
        - 提前退出，避免无谓累积
        """
        lines = []
        total_length = 0
        max_total_length = 8000  # 预留空间给 prompt 和摘要
        
        for i, msg in enumerate(messages):
            role = "用户" if msg.role == "user" else "助手"
            # 单条消息截断
            content = msg.content[:800] if len(msg.content) > 800 else msg.content
            
            line = f"[{role}]: {content}"
            total_length += len(line)
            
            if total_length > max_total_length:
                lines.append(f"...（省略 {len(messages) - i} 条消息）")
                break
            
            lines.append(line)
        
        return "\n".join(lines)

    def _build_summary_prompt(self, conversation_text: str) -> str:
        """
        构建用于生成摘要的 prompt
        明确指示 AI 提取关键信息
        """
        return f"""请作为对话分析助手，总结以下对话的关键信息。
要求：
1. 用简洁的中文总结，不超过 300 字
2. 提取用户的核心问题和需求
3. 保留助手的关键回答、建议和结论
4. 忽略日常问候、感谢、确认等无关内容
5. 按时间顺序组织要点，保持逻辑清晰

对话内容：
{conversation_text}

请生成摘要："""

    def _fallback_summary(self, messages: List[ChatHistory]) -> str:
        """
        AI 摘要失败时的降级方案
        简单提取用户提问主题
        """
        user_queries = [msg.content[:200] for msg in messages if msg.role == "user"]
        
        if len(user_queries) > 3:
            return f"历史对话主题：{'；'.join(user_queries[:3])}..."
        elif user_queries:
            return f"历史对话主题：{'；'.join(user_queries)}"
        
        return "历史对话：无主要内容"
