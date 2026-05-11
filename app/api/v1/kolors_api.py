"""
Kolors 图像生成 API - 重构版

重构内容：
1. 添加会话历史支持（compress_conversation_history）
2. 添加图片生成缓存（避免重复生成）
3. 图生图引用文件验证权限
4. 支持 session_id 隔离
"""
import json
import logging
from pathlib import Path
from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.utils.security import verify_token
from app.utils.image_generation import (
    text_to_image,
    image_to_image,
    inpaint_image,
    generate_avatar,
    generate_landscape,
    generate_icon,
    SUPPORTED_FORMATS,
    DEFAULT_CONFIG
)
from app.db.database import get_db
from app.models.history import History
from app.models.file import File
from app.db.models import ImageGenerationHistory

# 导入会话压缩函数
from app.api.v1.Aicode import compress_conversation_history

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/kolors", tags=["Kolors 图像生成"])


async def get_cached_image(
    db: AsyncSession,
    user_id: int,
    prompt: str,
    seed: Optional[int],
    conversation_id: Optional[int]
) -> Optional[str]:
    """
    获取缓存的图片（如果存在）
    
    逻辑：
    1. 在 metadata_json 中查找匹配的 prompt+seed
    2. 如果找到，返回图片路径
    3. 如果没找到，返回 None
    """
    try:
        # 构建缓存键
        cache_key = f"image:{prompt}:{seed}"
        
        # 查询历史
        if conversation_id:
            result = await db.execute(
                select(History).where(
                    History.user_id == user_id,
                    History.conversation_id == conversation_id,
                    History.metadata_json.contains(cache_key)
                ).order_by(History.id.desc()).limit(1)
            )
        else:
            result = await db.execute(
                select(History).where(
                    History.user_id == user_id,
                    History.metadata_json.contains(cache_key)
                ).order_by(History.id.desc()).limit(1)
            )
        
        history = result.scalar_one_or_none()
        
        if history and history.metadata_json:
            metadata = json.loads(history.metadata_json)
            if metadata.get("type") == "image" and metadata.get("path"):
                logger.info(f"使用缓存的图片 | cache_key={cache_key}")
                return metadata["path"]
        
        return None
        
    except (ValueError, TypeError, RuntimeError, OSError, SQLAlchemyError) as e:
        logger.error(f"检查图片缓存失败 | error={str(e)}")
        return None


async def cache_image_to_history(
    db: AsyncSession,
    user_id: int,
    conversation_id: Optional[int],
    prompt: str,
    image_path: str,
    seed: Optional[int]
) -> None:
    """
    缓存图片到 history.metadata_json
    
    用于后续快速访问，避免重复生成
    """
    try:
        # 查询当前用户的最大 conversation_id
        max_conv_stmt = select(__import__('sqlalchemy').func.max(History.conversation_id)).where(
            History.user_id == user_id
        )
        max_result = await db.execute(max_conv_stmt)
        max_conv_id = max_result.scalar() or 0
        
        # 确定 conversation_id
        if conversation_id is None:
            new_conv_id = int(max_conv_id) + 1
        else:
            new_conv_id = conversation_id
        
        # 构建元数据
        metadata = {
            "type": "image",
            "prompt": prompt,
            "seed": seed,
            "path": image_path,
            "cache_key": f"image:{prompt}:{seed}",
            "created_at": datetime.utcnow().isoformat()
        }
        
        # 创建历史记录
        history = History(
            user_id=user_id,
            conversation_id=new_conv_id,
            prompt=prompt,
            response=f"图片已生成：{image_path}",
            thinking=None,
            title=f"图像生成：{prompt[:50]}",
            metadata_json=json.dumps(metadata)
        )
        
        db.add(history)
        await db.commit()
        
        logger.info(f"缓存图片到历史 | conversation_id={new_conv_id} | path={image_path}")
        
    except (ValueError, TypeError, RuntimeError, OSError, SQLAlchemyError) as e:
        logger.error(f"缓存图片失败 | error={str(e)}")
        await db.rollback()


async def save_image_generation_history(
    db: AsyncSession,
    user_id: int,
    prompt: str,
    negative_prompt: str,
    image_paths: List[str],
    generation_type: str,
    params: dict,
    seed: Optional[int],
    status: str = "completed",
    error_message: str = None
) -> None:
    """保存图像生成记录到 ImageGenerationHistory 表"""
    try:
        import uuid
        image_id = f"img_{uuid.uuid4().hex[:12]}"
        
        image_urls = [p for p in image_paths]
        
        record = ImageGenerationHistory(
            image_id=image_id,
            user_id=str(user_id),
            prompt=prompt,
            negative_prompt=negative_prompt if negative_prompt else None,
            image_urls=image_urls,
            generation_type=generation_type,
            params=params,
            seed=seed,
            status=status,
            error_message=error_message,
        )
        
        db.add(record)
        await db.commit()
        
        logger.info(f"图像生成历史记录已保存 | image_id={image_id}")
        
    except (ValueError, TypeError, RuntimeError, OSError, SQLAlchemyError) as e:
        logger.error(f"保存图像历史记录失败 | error={str(e)}")
        await db.rollback()


# 请求模型定义
# -----------------------------

class TextToImageRequest(BaseModel):
    """文生图请求"""
    prompt: str
    negative_prompt: str = ""
    width: int = 1024
    height: int = 1024
    num_inferences: int = 50
    guidance_scale: float = 7.5
    num_images: int = 1
    seed: Optional[int] = None
    conversation_id: Optional[int] = Field(None, description="会话 ID（用于缓存和携带历史）")


class ImageToImageRequest(BaseModel):
    """图生图请求"""
    prompt: str
    negative_prompt: str = ""
    strength: float = 0.75
    width: Optional[int] = None
    height: Optional[int] = None
    num_inferences: int = 50
    guidance_scale: float = 7.5
    num_images: int = 1
    seed: Optional[int] = None
    image_path: str  # 参考图片路径
    conversation_id: Optional[int] = Field(None, description="会话 ID")


# API 端点
# -----------------------------

@router.post("/text-to-image", summary="文生图")
async def text_to_image_api(
    request: TextToImageRequest,
    token: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db)
):
    """
    根据文字描述生成图片（重构版）
    
    新增：
    - 检查缓存（避免重复生成）
    - 缓存结果到 history
    - 携带会话历史上下文
    """
    user_id = int(token.get("sub"))
    logger.info(f"文生图请求 | user_id={user_id} | prompt={request.prompt[:50]}...")
    
    try:
        # Step 1: 检查缓存
        cached_path = await get_cached_image(
            db, user_id, request.prompt, request.seed, request.conversation_id
        )
        
        if cached_path:
            # 缓存命中，直接返回
            return {
                "success": True,
                "cached": True,
                "paths": [cached_path],
                "message": "使用缓存的图片"
            }
        
        # Step 2: 携带会话历史（构建增强 prompt）
        full_prompt = request.prompt
        if request.conversation_id:
            history_context = await compress_conversation_history(
                db, user_id, request.conversation_id, max_messages=5
            )
            if history_context:
                full_prompt = f"{request.prompt}\n\n[参考历史]\n{history_context}"
        
        # Step 3: 调用模型生成
        result = await text_to_image(
            prompt=full_prompt,  # 使用增强后的 prompt
            negative_prompt=request.negative_prompt,
            width=request.width,
            height=request.height,
            num_inferences=request.num_inferences,
            guidance_scale=request.guidance_scale,
            num_images=request.num_images,
            seed=request.seed
        )
        
        # Step 4: 缓存结果
        if result["success"] and result["paths"]:
            await cache_image_to_history(
                db, user_id, request.conversation_id,
                request.prompt, result["paths"][0], request.seed
            )
            
            await save_image_generation_history(
                db=db,
                user_id=user_id,
                prompt=request.prompt,
                negative_prompt=request.negative_prompt,
                image_paths=result["paths"],
                generation_type="text-to-image",
                params={
                    "width": request.width,
                    "height": request.height,
                    "num_inferences": request.num_inferences,
                    "guidance_scale": request.guidance_scale,
                    "num_images": request.num_images,
                },
                seed=request.seed,
            )
        
        return {
            "success": result["success"],
            "cached": False,
            "paths": result["paths"],
            "paths_hash": [p.split("/")[-1] for p in result["paths"]]  # 只返回文件名
        }
        
    except (ValueError, TypeError, RuntimeError, OSError, SQLAlchemyError) as e:
        logger.error(f"文生图失败 | error={str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"生成失败：{str(e)}")


@router.post("/image-to-image", summary="图生图")
async def image_to_image_api(
    request: ImageToImageRequest,
    token: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db)
):
    """
    图生图（重构版）
    
    新增：
    - 验证参考图片权限
    - 检查缓存
    - 携带会话历史
    """
    user_id = int(token.get("sub"))
    logger.info(f"图生图请求 | user_id={user_id} | prompt={request.prompt[:50]}...")
    
    try:
        # Step 1: 验证参考图片权限
        result = await db.execute(
            select(File).where(
                File.user_id == user_id,
                File.file_path.contains(request.image_path)
            )
        )
        file_record = result.scalar_one_or_none()
        
        if not file_record:
            # 如果没有记录，检查是否是最近生成的缓存图片
            if request.conversation_id:
                history_result = await db.execute(
                    select(History).where(
                        History.user_id == user_id,
                        History.conversation_id == request.conversation_id,
                        History.metadata_json.contains(request.image_path)
                    )
                )
                history = history_result.scalar_one_or_none()
                
                if not history:
                    raise HTTPException(
                        status_code=403,
                        detail="无权访问该参考图片（可能属于其他会话）"
                    )
        
        # Step 2: 检查缓存
        cached_path = await get_cached_image(
            db, user_id, request.prompt, request.seed, request.conversation_id
        )
        
        if cached_path:
            return {
                "success": True,
                "cached": True,
                "paths": [cached_path],
                "message": "使用缓存的图片"
            }
        
        # Step 3: 携带会话历史
        full_prompt = request.prompt
        if request.conversation_id:
            history_context = await compress_conversation_history(
                db, user_id, request.conversation_id, max_messages=5
            )
            if history_context:
                full_prompt = f"{request.prompt}\n\n[参考历史]\n{history_context}"
        
        # Step 4: 调用模型生成
        result = await image_to_image(
            image_path=request.image_path,
            prompt=full_prompt,
            negative_prompt=request.negative_prompt,
            strength=request.strength,
            width=request.width or 1024,
            height=request.height or 1024,
            num_inferences=request.num_inferences,
            guidance_scale=request.guidance_scale,
            num_images=request.num_images,
            seed=request.seed
        )
        
        # Step 5: 缓存结果
        if result["success"] and result["paths"]:
            await cache_image_to_history(
                db, user_id, request.conversation_id,
                request.prompt, result["paths"][0], request.seed
            )
            
            await save_image_generation_history(
                db=db,
                user_id=user_id,
                prompt=request.prompt,
                negative_prompt=request.negative_prompt,
                image_paths=result["paths"],
                generation_type="image-to-image",
                params={
                    "width": request.width or 1024,
                    "height": request.height or 1024,
                    "strength": request.strength,
                    "num_inferences": request.num_inferences,
                    "guidance_scale": request.guidance_scale,
                    "num_images": request.num_images,
                    "reference_image": request.image_path,
                },
                seed=request.seed,
            )
        
        return {
            "success": result["success"],
            "cached": False,
            "paths": result["paths"],
            "paths_hash": [p.split("/")[-1] for p in result["paths"]]
        }
        
    except HTTPException:
        raise
    except (ValueError, TypeError, RuntimeError, OSError, SQLAlchemyError) as e:
        logger.error(f"图生图失败 | error={str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"生成失败：{str(e)}")


@router.post("/inpaint", summary="图像修复")
async def inpaint_api(
    request: ImageToImageRequest,
    token: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db)
):
    """
    图像修复（Inpainting）
    
    使用 mask 指定要修复的区域，AI 会自动填充内容
    
    参数:
    - image_path: 原始图片路径
    - mask_path: 掩码图片路径（白色区域为要修复的部分）
    - prompt: 修复后的描述
    - seed: 随机种子
    - conversation_id: 会话 ID
    """
    user_id = int(token.get("sub"))
    logger.info(f"图像修复请求 | user_id={user_id} | prompt={request.prompt[:50]}")
    
    try:
        # Step 1: 验证原图权限
        if request.image_path:
            result = await db.execute(
                select(File).where(
                    File.file_path.contains(request.image_path),
                    File.user_id == user_id,
                    File.is_deleted == 0
                )
            )
            file_record = result.scalar_one_or_none()
            
            if not file_record:
                raise HTTPException(
                    status_code=403,
                    detail="无权访问该参考图片"
                )
            
            # 验证会话隔离
            if request.conversation_id and file_record.conversation_id:
                if str(file_record.conversation_id) != str(request.conversation_id):
                    raise HTTPException(
                        status_code=403,
                        detail="无权访问该参考图片（可能属于其他会话）"
                    )
        
        # Step 2: 验证 mask 图片权限（如果有）
        if request.mask_path:
            result = await db.execute(
                select(File).where(
                    File.file_path.contains(request.mask_path),
                    File.user_id == user_id,
                    File.is_deleted == 0
                )
            )
            mask_record = result.scalar_one_or_none()
            
            if not mask_record:
                raise HTTPException(
                    status_code=403,
                    detail="无权访问 mask 图片"
                )
        
        # Step 3: 检查缓存
        cached_path = await get_cached_image(
            db, user_id, request.prompt, request.seed, request.conversation_id
        )
        
        if cached_path:
            return {
                "success": True,
                "cached": True,
                "paths": [cached_path],
                "message": "使用缓存的图片"
            }
        
        # Step 4: 携带会话历史
        full_prompt = request.prompt
        if request.conversation_id:
            history_context = await compress_conversation_history(
                db, user_id, request.conversation_id, max_messages=5
            )
            if history_context:
                full_prompt = f"{request.prompt}\n\n[参考历史]\n{history_context}"
        
        # Step 5: 调用图像修复模型
        result = await inpaint_image(
            image_path=request.image_path,
            mask_path=request.mask_path,
            prompt=full_prompt,
            negative_prompt=request.negative_prompt,
            width=request.width or 1024,
            height=request.height or 1024,
            num_inferences=request.num_inferences,
            guidance_scale=request.guidance_scale,
            num_images=request.num_images,
            seed=request.seed
        )
        
        # Step 6: 缓存结果
        if result["success"] and result["paths"]:
            await cache_image_to_history(
                db, user_id, request.conversation_id,
                request.prompt, result["paths"][0], request.seed
            )
        
        return {
            "success": result["success"],
            "cached": False,
            "paths": result["paths"],
            "paths_hash": [p.split("/")[-1] for p in result["paths"]],
            "message": result.get("message", "图像修复成功")
        }
        
    except HTTPException:
        raise
    except (ValueError, TypeError, RuntimeError, OSError, SQLAlchemyError) as e:
        logger.error(f"图像修复失败 | error={str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"修复失败：{str(e)}")


@router.post("/avatar", summary="生成头像")
async def generate_avatar_api(
    prompt: str,
    style: str = "anime",
    token: dict = Depends(verify_token)
):
    """生成头像（快捷方式）"""
    user_id = int(token.get("sub"))
    logger.info(f"生成头像 | user_id={user_id} | style={style}")
    
    try:
        result = await generate_avatar(prompt, style)
        return {
            "success": result["success"],
            "path": result["path"] if result["success"] else None
        }
    except (ValueError, TypeError, RuntimeError, OSError, SQLAlchemyError) as e:
        logger.error(f"生成头像失败 | error={str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/landscape", summary="生成风景图")
async def generate_landscape_api(
    prompt: str,
    style: str = "realistic",
    token: dict = Depends(verify_token)
):
    """生成风景图（快捷方式）"""
    user_id = int(token.get("sub"))
    logger.info(f"生成风景图 | user_id={user_id} | style={style}")
    
    try:
        result = await generate_landscape(prompt, style)
        return {
            "success": result["success"],
            "path": result["path"] if result["success"] else None
        }
    except (ValueError, TypeError, RuntimeError, OSError, SQLAlchemyError) as e:
        logger.error(f"生成风景图失败 | error={str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/icon", summary="生成图标")
async def generate_icon_api(
    prompt: str,
    style: str = "flat",
    token: dict = Depends(verify_token)
):
    """生成图标（快捷方式）"""
    user_id = int(token.get("sub"))
    logger.info(f"生成图标 | user_id={user_id} | style={style}")
    
    try:
        result = await generate_icon(prompt, style)
        return {
            "success": result["success"],
            "path": result["path"] if result["success"] else None
        }
    except (ValueError, TypeError, RuntimeError, OSError, SQLAlchemyError) as e:
        logger.error(f"生成图标失败 | error={str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/config", summary="获取配置信息")
async def get_config():
    """获取 Kolors 配置信息"""
    return {
        "supported_formats": SUPPORTED_FORMATS,
        "default_config": DEFAULT_CONFIG,
        "max_width": 1280,
        "max_height": 1280,
        "max_num_images": 4
    }
