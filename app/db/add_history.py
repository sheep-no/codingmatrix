import asyncio
import json
import logging
from typing import Any, Optional

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.history import History

logger = logging.getLogger(__name__)

# conversation_id 是「一个会话对多轮记录」的一对多字段，无法靠唯一约束
# 防重。新会话 id 由 max+1 生成，单进程 async 下两个新会话可能读到同一
# max 而撞号，用按用户粒度的进程内锁串行化「读取 max→插入→提交」。
_conversation_id_locks: dict[int, asyncio.Lock] = {}


def _database_dialect(db: AsyncSession) -> str:
    try:
        return db.get_bind().dialect.name
    except Exception:
        return ""


async def _acquire_conversation_id_lock(db: AsyncSession, user_id: int):
    if _database_dialect(db) != "mysql":
        return None
    bind = getattr(db, "bind", None)
    connect = getattr(bind, "connect", None)
    if connect is None:
        return None
    # 命名锁绑定在连接上，必须用独立连接持有到事务提交后再释放。
    lock_conn = await connect()
    try:
        result = await lock_conn.execute(
            text("SELECT GET_LOCK(:name, :timeout)"),
            {"name": f"conversation_id:{user_id}", "timeout": 10},
        )
        if result.scalar() != 1:
            raise RuntimeError("等待会话 ID 生成锁超时")
    except BaseException:
        await lock_conn.close()
        raise
    return lock_conn


async def _release_conversation_id_lock(lock_conn, user_id: int) -> None:
    try:
        await lock_conn.execute(
            text("SELECT RELEASE_LOCK(:name)"),
            {"name": f"conversation_id:{user_id}"},
        )
    finally:
        await lock_conn.close()


async def save_history_to_db(
        db: AsyncSession,
        user_id: int,
        conversation_id: Optional[int],
        prompt: str,
        response: str,
        thinking: Optional[str] = None,
        commit: bool = True,
        metadata: Optional[dict[str, Any]] = None,
) -> int:
    """
    保存历史记录到数据库
    - 如果 conversation_id 为 None，创建新对话（并发安全）
    - 如果 conversation_id 有值，续接对话
    """

    lock = _conversation_id_locks.setdefault(user_id, asyncio.Lock()) \
        if conversation_id is None else None
    if lock is not None:
        await lock.acquire()
    mysql_lock = None
    try:
        if conversation_id is not None:
            new_conv_id = conversation_id
        else:
            # MySQL 多 worker 部署用命名锁串行化「读取 max→写入」。
            mysql_lock = await _acquire_conversation_id_lock(db, user_id)
            max_conv_stmt = select(func.max(History.conversation_id)).where(
                History.user_id == user_id
            )
            max_result = await db.execute(max_conv_stmt)
            max_conv_id = max_result.scalar() or 0
            new_conv_id = int(max_conv_id) + 1

        history = History(
            user_id=user_id,
            conversation_id=new_conv_id,
            prompt=prompt,
            response=response,
            thinking=thinking,
            title=prompt[:100],
            metadata_json=json.dumps(metadata, ensure_ascii=False) if metadata else None,
        )
        db.add(history)
        if commit:
            await db.commit()
        else:
            await db.flush()
        await db.refresh(history)
    finally:
        try:
            if mysql_lock:
                await _release_conversation_id_lock(mysql_lock, user_id)
        finally:
            if lock is not None:
                lock.release()

    if commit:
        await invalidate_history_caches()

    return new_conv_id


async def invalidate_history_caches():
    try:
        from app.utils.cache_decorator import invalidate_cache_by_prefix
        await invalidate_cache_by_prefix("history")
        await invalidate_cache_by_prefix("conversations")
    except Exception as e:
        logger.warning(f"缓存失效失败: {e}")
