"""
会话历史存储模块 — Redis + 数据库混合存储

设计原则：
- 数据库是 source of truth（数据源权威）
- 写入时：先写数据库，再写 Redis（保证数据库始终有最新数据）
- 读取时：先查 Redis，miss 从数据库加载（快速读取）
- Redis 重启时：自动从数据库恢复（无数据丢失）

同步策略：
- 写入双写：每次写入都同时写数据库 + Redis
- 读取回填：Redis miss 时自动从数据库加载并写回 Redis
- 无定时任务：实时同步，不需要后台同步进程
"""

import asyncio
import json
import logging
import time
from typing import Dict, List, Optional, Any

import redis

logger = logging.getLogger(__name__)

# 配置
REDIS_KEY_PREFIX = "conversation:"
MAX_HISTORY_ROUNDS = 10  # 最多保留 10 轮
MAX_HISTORY_TOKENS = 4000  # 历史消息最多 4000 token
HISTORY_EXPIRE_SECONDS = 86400  # 24 小时过期

# 原子「读-改-写」追加脚本：Redis 侧单线程执行，避免并发 append 的
# last-write-wins 丢消息；key 不存在时用 ARGV[3]（数据库历史 seed）补齐，
# key 已存在时忽略 seed，避免重复历史。
_APPEND_SCRIPT = """
local raw = redis.call('GET', KEYS[1])
local list = {}
if raw then
  list = cjson.decode(raw)
elseif ARGV[3] ~= '' then
  list = cjson.decode(ARGV[3])
end
table.insert(list, cjson.decode(ARGV[1]))
redis.call('SETEX', KEYS[1], ARGV[2], cjson.encode(list))
return #list
"""


def _estimate_tokens(text: str) -> int:
    """粗略估算 token 数（中文约 1.5 字/token，英文约 4 字符/token）

    此前实现为总字符数 / 2，对英文高估约 2 倍，导致历史被过早截断。
    现按 CJK 与非 CJK 字符分别估算。
    """
    if not text:
        return 0
    cjk = 0
    for ch in text:
        code = ord(ch)
        # CJK 统一表意文字、日文假名、韩文音节
        if 0x4E00 <= code <= 0x9FFF or 0x3040 <= code <= 0x30FF or 0xAC00 <= code <= 0xD7A3:
            cjk += 1
    other = len(text) - cjk
    return int(cjk / 1.5 + other / 4)


class ConversationStore:
    """Redis + 数据库混合会话历史存储"""

    def __init__(self, redis_url: str = "redis://localhost:6379/0"):
        self.redis = redis.from_url(redis_url, decode_responses=True)
        # 序列化 seed 读取 + 数据库写入 + 原子追加三步，避免同进程内
        # 并发 append 时两次 seed 读到不同快照而重复历史。
        self._append_lock = asyncio.Lock()

    def _key(self, session_id: str) -> str:
        """生成 Redis key"""
        return f"{REDIS_KEY_PREFIX}{session_id}"

    def get_history(self, session_id: str, user_id: str = None) -> List[Dict[str, str]]:
        """
        获取会话历史（优先 Redis，miss 从数据库加载）

        数据流：
        1. 先查 Redis（快速）
        2. Redis miss → 从数据库加载（可靠）
        3. 加载后写回 Redis（下次直接命中）
        """
        # 1. 先查 Redis
        try:
            data = self.redis.get(self._key(session_id))
            if data:
                return json.loads(data)
        except Exception as e:
            logger.warning(f"Redis get failed: {e}")

        # 2. Redis miss，从数据库加载
        if user_id:
            messages = self._load_from_db_sync(session_id, user_id)
            if messages:
                # 3. 写回 Redis（下次直接命中）
                self._save_to_redis(session_id, messages)
            return messages

        return []

    async def get_history_async(self, session_id: str, user_id: str = None) -> List[Dict[str, str]]:
        """
        异步获取会话历史（优先 Redis，miss 从数据库加载）
        """
        # 1. 先查 Redis
        try:
            data = self.redis.get(self._key(session_id))
            if data:
                return json.loads(data)
        except Exception as e:
            logger.warning(f"Redis get failed: {e}")

        # 2. Redis miss，从数据库加载
        if user_id:
            messages = await self._load_from_db_async(session_id, user_id)
            if messages:
                # 3. 写回 Redis
                self._save_to_redis(session_id, messages)
            return messages

        return []

    def _load_from_db_sync(self, session_id: str, user_id: str) -> List[Dict[str, str]]:
        """同步方式从数据库加载历史消息"""
        try:
            import asyncio
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 已在异步上下文中，返回空（由异步方法处理）
                return []
            return loop.run_until_complete(self._load_from_db_async(session_id, user_id))
        except Exception as e:
            logger.warning(f"Failed to load from DB (sync): {e}")
            return []

    async def _load_from_db_async(self, session_id: str, user_id: str) -> List[Dict[str, str]]:
        """异步方式从数据库加载历史消息"""
        try:
            from app.db.database import async_session
            from app.db.models import ConversationMessage
            from sqlalchemy import select

            async with async_session() as session:
                result = await session.execute(
                    select(ConversationMessage)
                    .where(ConversationMessage.session_id == session_id)
                    .where(ConversationMessage.user_id == user_id)
                    .order_by(ConversationMessage.created_at)
                )
                rows = result.scalars().all()
                return [row.to_dict() for row in rows]
        except Exception as e:
            logger.warning(f"Failed to load from DB: {e}")
            return []

    def _save_to_redis(self, session_id: str, messages: List[Dict[str, str]]):
        """保存到 Redis（带过期时间）"""
        try:
            self.redis.setex(
                self._key(session_id),
                HISTORY_EXPIRE_SECONDS,
                json.dumps(messages, ensure_ascii=False)
            )
        except Exception as e:
            logger.warning(f"Failed to save to Redis: {e}")

    def _append_to_redis(
        self,
        session_id: str,
        message: Dict[str, str],
        seed: Optional[List[Dict[str, str]]] = None,
    ) -> int:
        """原子追加一条消息到 Redis，返回追加后的条数（失败返回 -1）"""
        try:
            script = self.redis.register_script(_APPEND_SCRIPT)
            count = script(
                keys=[self._key(session_id)],
                args=[
                    json.dumps(message, ensure_ascii=False),
                    HISTORY_EXPIRE_SECONDS,
                    json.dumps(seed, ensure_ascii=False) if seed else "",
                ],
            )
            return int(count)
        except Exception as e:
            logger.warning(f"Failed to append to Redis: {e}")
            return -1

    async def append_message(self, session_id: str, user_id: str, role: str, content: str):
        """
        追加一条消息（先写数据库，再写 Redis）

        数据流：
        1. 先写数据库（保证持久化）
        2. 再写 Redis（保证快速读取）
        3. 如果 Redis 写入失败，下次读取会从数据库回填
        """
        timestamp = int(time.time())
        message = {"role": role, "content": content, "timestamp": timestamp}

        async with self._append_lock:
            # Redis miss（如 24h 过期）时先取数据库历史作为 seed。必须在写 DB
            # 之前取，否则 seed 会包含本次新消息；此前在 async 上下文调用同步
            # get_history 会短路返回 []，使缓存被覆盖为仅最新一条、历史不可见。
            seed: Optional[List[Dict[str, str]]] = None
            try:
                if not self.redis.exists(self._key(session_id)):
                    seed = await self._load_from_db_async(session_id, user_id)
            except Exception as e:
                logger.warning(f"Failed to seed conversation cache: {e}")

            # 1. 先写数据库（source of truth）
            db_success = await self._save_message_to_db(
                session_id, user_id, role, content, timestamp
            )
            if not db_success:
                # DB 写失败时不再写 Redis，避免 Redis 出现数据库不存在的幽灵消息
                logger.warning(f"DB 写入失败，跳过 Redis 追加 | session={session_id}")
                return False

            # 2. 原子追加 Redis（key 已存在时 seed 被忽略，不会重复历史）
            self._append_to_redis(session_id, message, seed)
            return True

    async def _save_message_to_db(self, session_id: str, user_id: str, role: str, content: str, timestamp: int) -> bool:
        """保存单条消息到数据库"""
        try:
            from app.db.database import async_session
            from app.db.models import ConversationMessage
            from datetime import datetime, timezone

            async with async_session() as db:
                msg = ConversationMessage(
                    session_id=session_id,
                    user_id=user_id,
                    role=role,
                    content=content,
                    created_at=datetime.fromtimestamp(timestamp, tz=timezone.utc),
                )
                db.add(msg)
                await db.commit()
                return True
        except Exception as e:
            logger.error(f"Failed to save to DB: {e}")
            return False

    async def clear_history(self, session_id: str, user_id: str = None):
        """清空会话历史（先清数据库，再清 Redis）"""
        # 1. 清数据库
        if user_id:
            try:
                from app.db.database import async_session
                from app.db.models import ConversationMessage
                from sqlalchemy import delete as sql_delete

                async with async_session() as db:
                    await db.execute(
                        sql_delete(ConversationMessage)
                        .where(ConversationMessage.session_id == session_id)
                        .where(ConversationMessage.user_id == user_id)
                    )
                    await db.commit()
            except Exception as e:
                logger.warning(f"Failed to clear DB: {e}")

        # 2. 清 Redis
        try:
            self.redis.delete(self._key(session_id))
        except Exception as e:
            logger.warning(f"Failed to clear Redis: {e}")

    def truncate_history(
        self,
        messages: List[Dict[str, str]],
        max_rounds: int = MAX_HISTORY_ROUNDS,
        max_tokens: int = MAX_HISTORY_TOKENS
    ) -> List[Dict[str, str]]:
        """
        截断历史消息（不调用 LLM，纯规则截断）

        策略：
        1. 保留最近 max_rounds 轮（每轮 = user + assistant）
        2. 按 token 数截断，从最旧的消息开始丢弃
        """
        if not messages:
            return []

        # 保留最近 N 轮
        max_messages = max_rounds * 2
        if len(messages) > max_messages:
            messages = messages[-max_messages:]

        # 按 token 数截断
        total_tokens = 0
        for i in range(len(messages) - 1, -1, -1):
            total_tokens += _estimate_tokens(messages[i].get("content", ""))
            if total_tokens > max_tokens:
                # 丢弃超出部分
                messages = messages[i + 1:]
                break

        return messages

    async def compress_history(
        self,
        session_id: str,
        user_id: str,
        messages: List[Dict[str, str]],
        llm_caller: callable,
        max_tokens: int = MAX_HISTORY_TOKENS
    ) -> List[Dict[str, str]]:
        """
        压缩历史消息（调用 LLM 生成摘要）

        策略：
        1. 如果未超限，直接返回
        2. 将前半部分压缩成摘要
        3. 保留最近的消息
        """
        # 估算当前 token 数
        total_tokens = sum(_estimate_tokens(m.get("content", "")) for m in messages)

        if total_tokens <= max_tokens:
            return messages  # 未超限，不压缩

        # 将前半部分压缩成摘要
        mid = len(messages) // 2
        # 确保 mid 是偶数（完整轮次）
        if mid % 2 != 0:
            mid += 1
        old_messages = messages[:mid]
        recent_messages = messages[mid:]

        # 构建压缩 prompt
        conversation_text = "\n".join(
            f"{m['role']}: {m['content'][:500]}" for m in old_messages
        )

        try:
            summary = await llm_caller(
                "你是一个对话摘要助手。请将以下对话压缩成简短摘要，保留关键信息（项目名称、需求、决策、问题）。不超过 500 字。",
                conversation_text
            )

            # 用摘要替换旧消息
            compressed = [
                {"role": "system", "content": f"[历史对话摘要]\n{summary}", "timestamp": int(time.time())}
            ] + recent_messages

            # 更新存储（先清数据库旧数据，再写新数据）
            await self.clear_history(session_id, user_id)
            for msg in compressed:
                await self.append_message(session_id, user_id, msg["role"], msg["content"])

            logger.info(f"Compressed {len(old_messages)} messages into summary, kept {len(recent_messages)} recent messages")
            return compressed

        except Exception as e:
            logger.warning(f"Failed to compress history: {e}, falling back to truncation")
            return self.truncate_history(messages)


# 全局实例
_store: Optional[ConversationStore] = None


def get_conversation_store() -> ConversationStore:
    """获取全局会话存储实例"""
    global _store
    if _store is None:
        from app.core.config import settings
        redis_url = getattr(settings, 'REDIS_URL', 'redis://localhost:6379/0')
        _store = ConversationStore(redis_url)
    return _store
