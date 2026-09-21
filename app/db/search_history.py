from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, and_
from app.models.history import History
from typing import Optional, List
from datetime import datetime


def escape_like_pattern(pattern: str) -> str:
    """Escape special characters in LIKE pattern"""
    return pattern.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _apply_conversation_filters(
        stmt,
        user_id: int,
        prompt_keyword: Optional[str],
        start_date: Optional[datetime],
        end_date: Optional[datetime],
):
    """列表与计数共用的过滤口径：任一条消息命中全部条件即该会话命中。

    关键词必须作用在会话的任意一条消息上，否则会话早期消息命中、最新一条
    不含关键词时会漏召回，并与计数口径不一致。
    """
    stmt = stmt.where(History.user_id == user_id)
    if start_date:
        stmt = stmt.where(History.created_at >= start_date)
    if end_date:
        stmt = stmt.where(History.created_at <= end_date)
    if prompt_keyword:
        escaped_keyword = escape_like_pattern(prompt_keyword)
        stmt = stmt.where(History.prompt.like(f"%{escaped_keyword}%", escape="\\"))
    return stmt


# 主函数：获取每个对话的最新记录（用于左侧历史列表）
async def search_history_to_db(
        db: AsyncSession,
        user_id: int,
        prompt_keyword: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 20,
        offset: int = 0
) -> List[History]:
    """
    获取用户的历史记录，按 conversation_id 分组，每个对话只返回最新的一条记录
    用于前端历史记录列表展示
    
    优化点：
    1. 使用子查询先获取每个 conversation_id 的最大 id
    2. 主查询通过 IN 子句获取详细记录（避免复杂 JOIN）
    3. 尽早应用过滤条件减少数据量
    """
    # 命中会话集合：任一条消息命中关键词即可，与计数函数保持同一口径
    matching_conversations = _apply_conversation_filters(
        select(History.conversation_id), user_id, prompt_keyword, start_date, end_date
    )

    # 展示行仍取该会话在时间范围内的最新一条记录
    subquery = _apply_conversation_filters(
        select(History.conversation_id, func.max(History.id).label('max_id')),
        user_id, None, start_date, end_date
    ).where(History.conversation_id.in_(matching_conversations))
    subquery = subquery.group_by(History.conversation_id).subquery()

    max_ids_subquery = select(subquery.c.max_id)

    stmt = select(History).where(
        and_(
            History.id.in_(max_ids_subquery),
            History.user_id == user_id
        )
    )

    stmt = stmt.order_by(desc(History.id)).limit(limit).offset(offset)
    
    result = await db.execute(stmt)
    return result.scalars().all()


# 新增函数：获取同一conversation_id的更多记录（用于对话详情）
async def get_conversation_history(
        db: AsyncSession,
        user_id: int,
        conversation_id: int,
        last_history_id: Optional[int] = None,
        limit: int = 20
) -> List[History]:
    """
    获取同一conversation_id的更多历史记录
    用于前端点击某个对话后，滚动到顶部时加载更多记录

    Args:
        db: 数据库会话
        user_id: 用户ID
        conversation_id: 对话ID
        last_history_id: 前端当前显示的最小id（用于分页）
        limit: 每次加载的记录数

    Returns:
        历史记录列表（从早到晚排序）
    """
    stmt = select(History).where(
        and_(
            History.user_id == user_id,
            History.conversation_id == conversation_id
        )
    )

    # 如果提供了last_history_id，加载比它更早的记录
    if last_history_id:
        stmt = stmt.where(History.id < last_history_id)

    # 按id升序排列（从早到晚，前端反转后显示）
    stmt = stmt.order_by(History.id).limit(limit)

    result = await db.execute(stmt)
    return result.scalars().all()


# 辅助函数：获取分组后的总数（用于分页）
async def get_distinct_conversation_count(
        db: AsyncSession,
        user_id: int,
        prompt_keyword: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
) -> int:
    """
    获取不同 conversation_id 的总数（用于主列表分页）
    
    优化点：
    1. 子查询中提前应用时间过滤
    2. 简化总数统计逻辑
    """
    subquery = _apply_conversation_filters(
        select(History.conversation_id), user_id, prompt_keyword, start_date, end_date
    )

    subquery = subquery.group_by(History.conversation_id).subquery()
    
    stmt = select(func.count()).select_from(subquery)
    
    result = await db.execute(stmt)
    return result.scalar() or 0
