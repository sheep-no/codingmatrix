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
import tempfile
from pathlib import Path
from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
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

# 临时文件目录（用于上传的参考图）
TEMP_DIR = Path(tempfile.gettempdir()) / "kolors_uploads"
TEMP_DIR.mkdir(exist_ok=True)


async def _save_upload_file(upload_file: UploadFile) -> str:
    """保存上传文件到临时目录，返回文件路径"""
    import uuid
    ext = Path(upload_file.filename or "image.png").suffix or ".png"
    filename = f"upload_{uuid.uuid4().hex[:12]}{ext}"
    file_path = TEMP_DIR / filename
    content = await upload_file.read()
    with open(file_path, "wb") as f:
        f.write(content)
    return str(file_path)


async def get_cached_image(
    db: AsyncSession,
    user_id: int,
    prompt: str,
    seed: Optional[int],
    conversation_id: Optional[int],
    max_age_hours: int = 24
) -> Optional[str]:
    """
    获取缓存的图片（如果存在）
    
    逻辑：
    1. 在 metadata_json 中查找匹配的 prompt+seed
    2. 检查缓存是否在有效期内（默认 24 小时）
    3. 如果找到且有效，返回图片路径
    4. 如果没找到或已过期，返回 None
    """
    try:
        from datetime import datetime, timedelta
        cache_key = f"image:{prompt}:{seed}"
        cutoff_time = datetime.utcnow() - timedelta(hours=max_age_hours)
        
        query_conditions = [
            History.user_id == user_id,
            History.metadata_json.contains(cache_key),
            History.created_at >= cutoff_time
        ]
        
        if conversation_id:
            query_conditions.append(History.conversation_id == conversation_id)
        
        result = await db.execute(
            select(History).where(*query_conditions).order_by(History.id.desc()).limit(1)
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
        max_conv_stmt = select(func.max(History.conversation_id)).where(
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
        
        record = ImageGenerationHistory(
            image_id=image_id,
            user_id=str(user_id),
            prompt=prompt,
            negative_prompt=negative_prompt if negative_prompt else None,
            image_urls=list(image_paths),
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

# 风格 prompt 映射（内置）
_BUILTIN_STYLE_PROMPTS = {
    "realistic": "写实风格，高质量照片级真实感，专业摄影",
    "anime": "日系动漫风格，精美插画，色彩鲜艳",
    "digital_art": "数字艺术风格，概念艺术，精细细节",
    "oil_painting": "油画风格，艺术大师作品，丰富笔触",
    "watercolor": "水彩画风格，清新淡雅，柔和色调",
    "sketch": "素描风格，铅笔画，黑白灰层次分明",
    "cyberpunk": "赛博朋克风格，霓虹灯光，未来都市",
    "fantasy": "奇幻风格，魔法元素，梦幻场景",
    "pixel": "像素艺术风格，复古游戏画面",
    "minimalist": "极简主义风格，简洁构图，大面积留白",
}


def _load_custom_image_styles() -> dict:
    """从 Skill 注册表加载自定义图片风格"""
    custom_styles = {}
    try:
        from app.services.skill_registry import get_registry
        registry = get_registry()
        
        # 获取 "image_styles" skill
        skill_data = registry.get("image_styles")
        if skill_data and isinstance(skill_data, str):
            # 解析 Markdown 格式的风格定义
            # 格式：# 风格名称\n描述内容
            current_name = None
            current_desc = []
            
            for line in skill_data.split('\n'):
                if line.startswith('# ') and not line.startswith('## '):
                    # 保存上一个风格
                    if current_name and current_desc:
                        custom_styles[current_name] = '\n'.join(current_desc).strip()
                    # 开始新风格
                    current_name = line[2:].strip().lower().replace(' ', '_')
                    current_desc = []
                elif current_name:
                    current_desc.append(line)
            
            # 保存最后一个风格
            if current_name and current_desc:
                custom_styles[current_name] = '\n'.join(current_desc).strip()
    except Exception as e:
        logger.debug(f"加载自定义图片风格失败: {e}")
    
    return custom_styles


def get_style_prompts() -> dict:
    """获取所有风格 prompt（内置 + 自定义）"""
    styles = dict(_BUILTIN_STYLE_PROMPTS)
    styles.update(_load_custom_image_styles())
    return styles


# 向后兼容
STYLE_PROMPTS = get_style_prompts()


class TextToImageRequest(BaseModel):
    """文生图请求"""
    prompt: str
    negative_prompt: str = ""
    width: int = 1024
    height: int = 1024
    num_inferences: int = Field(50, description="推理步数 (20-100)")
    guidance_scale: float = Field(7.5, description="引导系数 (1-20)")
    num_images: int = 1
    seed: Optional[int] = None
    conversation_id: Optional[int] = Field(None, description="会话 ID（用于缓存和携带历史）")
    api_key_token: Optional[str] = Field(None, description="用户 API Key Token")
    # 前端兼容字段
    steps: Optional[int] = Field(None, description="推理步数（别名，优先于 num_inferences）")
    cfg_scale: Optional[float] = Field(None, description="引导系数（别名，优先于 guidance_scale）")
    style: Optional[str] = Field(None, description="画面风格（写实/动漫/数字艺术等）")

    def get_num_inferences(self) -> int:
        return self.steps if self.steps is not None else self.num_inferences

    def get_guidance_scale(self) -> float:
        return self.cfg_scale if self.cfg_scale is not None else self.guidance_scale


class ImageToImageRequest(BaseModel):
    """图生图请求"""
    prompt: str
    negative_prompt: str = ""
    strength: float = 0.75
    denoising_strength: Optional[float] = Field(None, description="降噪强度（别名，优先于 strength）")
    width: Optional[int] = None
    height: Optional[int] = None
    num_inferences: int = 50
    guidance_scale: float = 7.5
    num_images: int = 1
    seed: Optional[int] = None
    image_path: Optional[str] = None  # 参考图片路径
    image_url: Optional[str] = Field(None, description="参考图片 URL（别名，优先于 image_path）")
    mask_path: Optional[str] = None  # 掩码图片路径（inpaint 用）
    mask_url: Optional[str] = Field(None, description="掩码图片 URL（别名，优先于 mask_path）")
    conversation_id: Optional[int] = Field(None, description="会话 ID")
    api_key_token: Optional[str] = Field(None, description="用户 API Key Token")
    # 前端兼容字段
    steps: Optional[int] = Field(None, description="推理步数（别名，优先于 num_inferences）")
    cfg_scale: Optional[float] = Field(None, description="引导系数（别名，优先于 guidance_scale）")
    style: Optional[str] = Field(None, description="画面风格")

    def get_image_path(self) -> str:
        return self.image_url or self.image_path or ""

    def get_mask_path(self) -> str:
        return self.mask_url or self.mask_path or ""

    def get_strength(self) -> float:
        return self.denoising_strength if self.denoising_strength is not None else self.strength

    def get_num_inferences(self) -> int:
        return self.steps if self.steps is not None else self.num_inferences

    def get_guidance_scale(self) -> float:
        return self.cfg_scale if self.cfg_scale is not None else self.guidance_scale


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
        # Step 1: 拼接风格描述（动态获取，包括自定义风格）
        full_prompt = request.prompt
        style_prompts = get_style_prompts()
        if request.style and request.style in style_prompts:
            full_prompt = f"{style_prompts[request.style]}，{full_prompt}"

        # Step 3: 携带会话历史（构建增强 prompt）
        if request.conversation_id:
            history_context = await compress_conversation_history(
                db, user_id, request.conversation_id, max_messages=5
            )
            if history_context:
                full_prompt = f"{full_prompt}\n\n[参考历史]\n{history_context}"

        # Step 4: 调用模型生成
        result = await text_to_image(
            prompt=full_prompt,
            negative_prompt=request.negative_prompt,
            width=request.width,
            height=request.height,
            num_inferences=request.get_num_inferences(),
            guidance_scale=request.get_guidance_scale(),
            num_images=request.num_images,
            seed=request.seed,
            api_key_token=request.api_key_token
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
                image_paths=result.get("images", result["paths"]),
                generation_type="text-to-image",
                params={
                    "width": request.width,
                    "height": request.height,
                    "num_inferences": request.get_num_inferences(),
                    "guidance_scale": request.get_guidance_scale(),
                    "num_images": request.num_images,
                    "style": request.style,
                },
                seed=request.seed,
            )
        
        return {
            "success": result["success"],
            "cached": False,
            "images": result.get("images", []),
            "paths": result["paths"],
            "paths_hash": [p.split("/")[-1] for p in result["paths"]]
        }
        
    except (ValueError, TypeError, RuntimeError, OSError, SQLAlchemyError) as e:
        logger.error(f"文生图失败 | error={str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"生成失败：{str(e)}")


@router.post("/image-to-image", summary="图生图")
async def image_to_image_api(
    http_request: Request,
    token: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db)
):
    """
    图生图（重构版）
    
    支持两种请求格式：
    1. application/json：通过 image_path 传参考图路径
    2. multipart/form-data：通过 image 字段上传文件
    
    新增：
    - 验证参考图片权限
    - 检查缓存
    - 携带会话历史
    """
    user_id = int(token.get("sub"))
    
    # 根据 Content-Type 解析请求
    content_type = http_request.headers.get("content-type", "")
    uploaded_temp_path = None
    
    if "multipart/form-data" in content_type:
        form = await http_request.form()
        image_file = form.get("image")
        if image_file and hasattr(image_file, "read"):
            uploaded_temp_path = await _save_upload_file(image_file)
            image_path = uploaded_temp_path
        else:
            image_path = str(form.get("image_path") or form.get("image_url") or "")
        
        request = ImageToImageRequest(
            prompt=str(form.get("prompt", "")),
            negative_prompt=str(form.get("negative_prompt", "")),
            strength=float(form.get("strength") or form.get("denoising_strength") or 0.75),
            width=int(form["width"]) if form.get("width") else None,
            height=int(form["height"]) if form.get("height") else None,
            num_inferences=int(form.get("steps") or form.get("num_inferences") or 50),
            guidance_scale=float(form.get("cfg_scale") or form.get("guidance_scale") or 7.5),
            num_images=int(form.get("num_images") or 1),
            seed=int(form["seed"]) if form.get("seed") and str(form["seed"]).strip() not in ("", "-1", "undefined") else None,
            image_path=image_path,
            mask_path=str(form.get("mask_path") or form.get("mask_url") or "") or None,
            conversation_id=int(form["conversation_id"]) if form.get("conversation_id") else None,
            api_key_token=str(form.get("api_key_token") or ""),
            style=str(form.get("style") or "") or None,
        )
    else:
        body = await http_request.json()
        request = ImageToImageRequest(**body)
        image_path = request.get_image_path()

    logger.info(f"图生图请求 | user_id={user_id} | prompt={request.prompt[:50]}...")
    
    try:
        if not image_path:
            raise HTTPException(status_code=422, detail="请提供参考图片（image 文件或 image_path）")

        # Step 1: 验证参考图片权限（跳过上传文件的权限检查）
        if not uploaded_temp_path:
            result = await db.execute(
                select(File).where(
                    File.user_id == user_id,
                    File.file_path.contains(image_path)
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
                            History.metadata_json.contains(image_path)
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
                "images": [],
                "paths": [cached_path],
                "message": "使用缓存的图片"
            }
        
        # Step 3: 拼接风格描述（动态获取，包括自定义风格）
        full_prompt = request.prompt
        style_prompts = get_style_prompts()
        if request.style and request.style in style_prompts:
            full_prompt = f"{style_prompts[request.style]}，{full_prompt}"

        # Step 4: 携带会话历史
        if request.conversation_id:
            history_context = await compress_conversation_history(
                db, user_id, request.conversation_id, max_messages=5
            )
            if history_context:
                full_prompt = f"{full_prompt}\n\n[参考历史]\n{history_context}"

        # Step 5: 调用模型生成
        result = await image_to_image(
            image_path=image_path,
            prompt=full_prompt,
            negative_prompt=request.negative_prompt,
            strength=request.get_strength(),
            width=request.width or 1024,
            height=request.height or 1024,
            num_inferences=request.get_num_inferences(),
            guidance_scale=request.get_guidance_scale(),
            num_images=request.num_images,
            seed=request.seed,
            api_key_token=request.api_key_token
        )
        
        # Step 6: 缓存结果
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
                image_paths=result.get("images", result["paths"]),
                generation_type="image-to-image",
                params={
                    "width": request.width or 1024,
                    "height": request.height or 1024,
                    "strength": request.get_strength(),
                    "num_inferences": request.get_num_inferences(),
                    "guidance_scale": request.get_guidance_scale(),
                    "num_images": request.num_images,
                    "reference_image": image_path,
                    "style": request.style,
                },
                seed=request.seed,
            )
        
        return {
            "success": result["success"],
            "cached": False,
            "images": result.get("images", []),
            "paths": result["paths"],
            "paths_hash": [p.split("/")[-1] for p in result["paths"]]
        }
        
    except HTTPException:
        raise
    except (ValueError, TypeError, RuntimeError, OSError, SQLAlchemyError) as e:
        logger.error(f"图生图失败 | error={str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"生成失败：{str(e)}")
    finally:
        # 清理上传的临时文件
        if uploaded_temp_path:
            try:
                Path(uploaded_temp_path).unlink(missing_ok=True)
            except OSError:
                pass


@router.post("/inpaint", summary="图像修复")
async def inpaint_api(
    http_request: Request,
    token: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db)
):
    """
    图像修复（Inpainting）
    
    支持两种请求格式：
    1. application/json：通过 image_path/mask_path 传路径
    2. multipart/form-data：通过 image/mask 字段上传文件
    """
    user_id = int(token.get("sub"))
    
    content_type = http_request.headers.get("content-type", "")
    uploaded_temp_paths = []
    
    if "multipart/form-data" in content_type:
        form = await http_request.form()
        
        image_file = form.get("image")
        if image_file and hasattr(image_file, "read"):
            image_path = await _save_upload_file(image_file)
            uploaded_temp_paths.append(image_path)
        else:
            image_path = str(form.get("image_path") or form.get("image_url") or "")
        
        mask_file = form.get("mask")
        if mask_file and hasattr(mask_file, "read"):
            mask_path = await _save_upload_file(mask_file)
            uploaded_temp_paths.append(mask_path)
        else:
            mask_path = str(form.get("mask_path") or form.get("mask_url") or "")
        
        request = ImageToImageRequest(
            prompt=str(form.get("prompt", "")),
            negative_prompt=str(form.get("negative_prompt", "")),
            strength=float(form.get("strength") or form.get("denoising_strength") or 0.75),
            width=int(form["width"]) if form.get("width") else None,
            height=int(form["height"]) if form.get("height") else None,
            num_inferences=int(form.get("steps") or form.get("num_inferences") or 50),
            guidance_scale=float(form.get("cfg_scale") or form.get("guidance_scale") or 7.5),
            num_images=int(form.get("num_images") or 1),
            seed=int(form["seed"]) if form.get("seed") and str(form["seed"]).strip() not in ("", "-1", "undefined") else None,
            image_path=image_path,
            mask_path=mask_path or None,
            conversation_id=int(form["conversation_id"]) if form.get("conversation_id") else None,
            api_key_token=str(form.get("api_key_token") or ""),
        )
    else:
        body = await http_request.json()
        request = ImageToImageRequest(**body)
        image_path = request.get_image_path()
        mask_path = request.get_mask_path()

    logger.info(f"图像修复请求 | user_id={user_id} | prompt={request.prompt[:50]}")

    try:
        if not image_path:
            raise HTTPException(status_code=422, detail="请提供参考图片（image 文件或 image_path）")

        # Step 1: 验证原图权限（跳过上传文件的权限检查）
        if not uploaded_temp_paths:
            if image_path:
                result = await db.execute(
                    select(File).where(
                        File.file_path.contains(image_path),
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
            if mask_path:
                result = await db.execute(
                    select(File).where(
                        File.file_path.contains(mask_path),
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
                "images": [],
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
            image_path=image_path,
            mask_path=mask_path,
            prompt=full_prompt,
            negative_prompt=request.negative_prompt,
            width=request.width or 1024,
            height=request.height or 1024,
            num_inferences=request.get_num_inferences(),
            guidance_scale=request.get_guidance_scale(),
            num_images=request.num_images,
            seed=request.seed,
            api_key_token=request.api_key_token
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
            "images": result.get("images", []),
            "paths": result["paths"],
            "paths_hash": [p.split("/")[-1] for p in result["paths"]],
            "message": result.get("message", "图像修复成功")
        }
        
    except HTTPException:
        raise
    except (ValueError, TypeError, RuntimeError, OSError, SQLAlchemyError) as e:
        logger.error(f"图像修复失败 | error={str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"修复失败：{str(e)}")
    finally:
        for tmp in uploaded_temp_paths:
            try:
                Path(tmp).unlink(missing_ok=True)
            except OSError:
                pass


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
            "images": result.get("images", []),
            "paths": result.get("paths", [])
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
            "images": result.get("images", []),
            "paths": result.get("paths", [])
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
            "images": result.get("images", []),
            "paths": result.get("paths", [])
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


@router.get("/styles", summary="获取所有可用风格")
async def get_styles():
    """
    获取所有可用的图片风格（内置 + 自定义）
    
    返回：
    - styles: 风格名称列表
    - style_prompts: 风格名称到描述的映射
    - builtin_count: 内置风格数量
    - custom_count: 自定义风格数量
    """
    builtin_styles = dict(_BUILTIN_STYLE_PROMPTS)
    all_styles = get_style_prompts()
    
    custom_styles = {k: v for k, v in all_styles.items() if k not in builtin_styles}
    
    return {
        "styles": list(all_styles.keys()),
        "style_prompts": all_styles,
        "builtin_count": len(builtin_styles),
        "custom_count": len(custom_styles),
        "custom_styles": list(custom_styles.keys())
    }
