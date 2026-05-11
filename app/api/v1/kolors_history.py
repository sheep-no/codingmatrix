"""
AI 绘图历史记录 API

API 端点：
- GET /api/v1/kolors/history - 获取绘图历史记录
- GET /api/v1/kolors/history/{image_id} - 获取单条历史详情
- DELETE /api/v1/kolors/history/{image_id} - 删除单条历史记录
- DELETE /api/v1/kolors/history - 清空所有历史记录
"""

import json
import logging
import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete as sql_delete

from app.db.database import get_db
from app.db.models import ImageGenerationHistory
from app.utils.security import verify_token

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/kolors", tags=["kolors-history"])


def _delete_image_files(image_urls: list):
    """删除本地图片文件"""
    for url in (image_urls or []):
        try:
            file_path = Path(url)
            if file_path.exists():
                file_path.unlink()
                logger.info(f"已删除图片文件: {url}")
        except OSError as e:
            logger.warning(f"删除图片文件失败: {url} | error={e}")


@router.get("/history")
async def get_image_history(
    token: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
):
    """获取当前用户的 AI 绘图历史记录"""
    user_id = token.get("sub") or token.get("user_id")

    query = (
        select(ImageGenerationHistory)
        .where(ImageGenerationHistory.user_id == user_id)
        .order_by(ImageGenerationHistory.created_at.desc())
    )

    total_result = await db.execute(
        select(ImageGenerationHistory).where(ImageGenerationHistory.user_id == user_id)
    )
    total = len(total_result.all())

    offset = (page - 1) * page_size
    result = await db.execute(query.offset(offset).limit(page_size))
    records = result.scalars().all()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [r.to_dict() for r in records],
    }


@router.get("/history/{image_id}")
async def get_image_history_detail(
    image_id: str,
    token: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db),
):
    """获取 AI 绘图历史详情"""
    user_id = token.get("sub") or token.get("user_id")

    result = await db.execute(
        select(ImageGenerationHistory)
        .where(ImageGenerationHistory.image_id == image_id)
        .where(ImageGenerationHistory.user_id == user_id)
    )
    record = result.scalar_one_or_none()

    if not record:
        raise HTTPException(status_code=404, detail="绘图历史记录不存在")

    return record.to_dict()


@router.delete("/history/{image_id}")
async def delete_image_history(
    image_id: str,
    token: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db),
):
    """删除 AI 绘图历史记录（同时删除本地图片文件）"""
    user_id = token.get("sub") or token.get("user_id")

    result = await db.execute(
        select(ImageGenerationHistory)
        .where(ImageGenerationHistory.image_id == image_id)
        .where(ImageGenerationHistory.user_id == user_id)
    )
    record = result.scalar_one_or_none()

    if not record:
        raise HTTPException(status_code=404, detail="绘图历史记录不存在")

    _delete_image_files(record.image_urls)

    await db.delete(record)
    await db.commit()

    return {
        "image_id": image_id,
        "status": "deleted",
        "message": "绘图历史记录已删除",
    }


@router.delete("/history")
async def delete_all_image_history(
    token: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db),
):
    """清空当前用户的所有 AI 绘图历史记录（同时删除本地图片文件）"""
    user_id = token.get("sub") or token.get("user_id")

    result = await db.execute(
        select(ImageGenerationHistory)
        .where(ImageGenerationHistory.user_id == user_id)
    )
    records = result.scalars().all()

    deleted_count = 0
    for record in records:
        _delete_image_files(record.image_urls)
        await db.delete(record)
        deleted_count += 1

    await db.commit()

    return {
        "status": "deleted_all",
        "deleted_count": deleted_count,
        "message": f"已清空 {deleted_count} 条绘图历史记录",
    }
