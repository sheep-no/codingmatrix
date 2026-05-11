from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.models.history import History
from typing import Optional, Callable, AsyncGenerator, Any


async def save_history_to_db(
        db: AsyncSession,
        user_id: int,
        conversation_id: Optional[int],
        prompt: str,
        response: str,
        thinking: Optional[str] = None,
) -> int:
    """
    保存历史记录到数据库
    - 如果 conversation_id 为 None，创建新对话
    - 如果 conversation_id 有值，续接对话
    """

    max_conv_stmt = select(func.max(History.conversation_id)).where(
        History.user_id == user_id
    )
    max_result = await db.execute(max_conv_stmt)
    max_conv_id = max_result.scalar() or 0

    if conversation_id is None:
        new_conv_id =int (max_conv_id) + 1
    else:
        new_conv_id = conversation_id

    history = History(
        user_id=user_id,
        conversation_id=new_conv_id,
        prompt=prompt,
        response=response,
        thinking=thinking,
        title=prompt[:100],
    )
    db.add(history)
    await db.commit()
    await db.refresh(history)

    try:
        from app.utils.cache_decorator import invalidate_cache_by_prefix
        await invalidate_cache_by_prefix("history")
        await invalidate_cache_by_prefix("conversations")
    except Exception as e:
        from logging import getLogger
        getLogger(__name__).warning(f"缓存失效失败: {e}")

    return new_conv_id