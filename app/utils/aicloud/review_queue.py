"""
审查队列

实现 aicloud 的文件审查功能：
- 创建审查记录
- 获取审查状态
- 审批/拒绝审查
- 用户偏好设置
"""

from datetime import datetime
from typing import Optional, Dict, Any
from uuid import uuid4
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import json

from app.models.aicloud import AicloudReview


async def create_review(
    db: AsyncSession,
    operation_type: str,
    file_path: str,
    content: Optional[str],
    requested_by: int,
    ai_filter_passed: bool,
    details: Optional[Dict[str, Any]] = None
) -> AicloudReview:
    """
    创建审查记录

    Args:
        db: 数据库会话
        operation_type: 操作类型 ('read' or 'write')
        file_path: 文件路径
        content: 文件内容
        requested_by: 请求用户 ID
        ai_filter_passed: AI 过滤器是否通过
        details: 额外详情

    Returns:
        创建的审查记录
    """
    review_id = str(uuid4())

    review = AicloudReview(
        id=review_id,
        operation_type=operation_type,
        file_path=file_path,
        content=content,
        status="pending",
        requested_by=requested_by,
        ai_filter_passed=ai_filter_passed,
        details=json.dumps(details) if details else None
    )

    db.add(review)
    await db.commit()
    await db.refresh(review)

    return review


async def get_review(
    db: AsyncSession,
    review_id: str
) -> Optional[AicloudReview]:
    """
    获取审查记录

    Args:
        db: 数据库会话
        review_id: 审查 ID

    Returns:
        审查记录或 None
    """
    result = await db.execute(
        select(AicloudReview).where(AicloudReview.id == review_id)
    )
    return result.scalar_one_or_none()


async def approve_review(
    db: AsyncSession,
    review_id: str,
    reviewed_by: int
) -> Optional[AicloudReview]:
    """
    批准审查

    Args:
        db: 数据库会话
        review_id: 审查 ID
        reviewed_by: 审批用户 ID

    Returns:
        更新后的审查记录或 None
    """
    review = await get_review(db, review_id)
    if not review:
        return None

    review.status = "approved"
    review.reviewed_by = reviewed_by
    review.reviewed_at = datetime.utcnow()

    await db.commit()
    await db.refresh(review)

    return review


async def reject_review(
    db: AsyncSession,
    review_id: str,
    reviewed_by: int,
    reason: Optional[str] = None
) -> Optional[AicloudReview]:
    """
    拒绝审查

    Args:
        db: 数据库会话
        review_id: 审查 ID
        reviewed_by: 审批用户 ID
        reason: 拒绝原因

    Returns:
        更新后的审查记录或 None
    """
    review = await get_review(db, review_id)
    if not review:
        return None

    review.status = "rejected"
    review.reviewed_by = reviewed_by
    review.reviewed_at = datetime.utcnow()

    if reason:
        details = json.loads(review.details or "{}")
        details["reject_reason"] = reason
        review.details = json.dumps(details)

    await db.commit()
    await db.refresh(review)

    return review

