"""
视觉模型 API - 图片理解、OCR、UI 转代码、内容审核
"""
import logging
import tempfile
import base64
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File as FastAPIFile
from pydantic import BaseModel, Field

from app.utils.security import verify_token
from app.utils.vision import (
    analyze_image,
    extract_text_from_image,
    generate_code_from_image,
    check_image_safety,
    SUPPORTED_IMAGE_FORMATS,
    MAX_IMAGE_SIZE,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/vision", tags=["视觉模型"])


# ==================== Request/Response Models ====================

class AnalyzeImageRequest(BaseModel):
    """图片分析请求"""
    prompt: str = Field(default="请详细描述这张图片的内容", description="分析提示词")
    image_url: Optional[str] = Field(default=None, description="图片 URL（可选，与 file 二选一）")


class AnalyzeImageResponse(BaseModel):
    """图片分析响应"""
    description: str
    objects: list
    text: str
    model_used: str


class OCRResponse(BaseModel):
    """OCR 响应"""
    text: str
    model_used: str


class CodeFromImageRequest(BaseModel):
    """UI 截图转代码请求"""
    requirement: str = Field(default="", description="额外需求描述")


class CodeFromImageResponse(BaseModel):
    """UI 截图转代码响应"""
    description: str
    technology_stack: list
    code_structure: str
    raw_description: str


class SafetyCheckResponse(BaseModel):
    """安全性检查响应"""
    safe: bool
    reason: str
    flags: list


# ==================== API Endpoints ====================

@router.post("/analyze", response_model=AnalyzeImageResponse)
async def api_analyze_image(
    file: Optional[UploadFile] = FastAPIFile(None),
    prompt: Optional[str] = "请详细描述这张图片的内容",
    image_url: Optional[str] = None,
    token: dict = Depends(verify_token),
):
    """
    分析图片内容

    支持两种方式：
    1. multipart/form-data: 上传 file + prompt 字段
    2. JSON body: image_url 字段（base64 data URI）

    视觉模型会自动降级，确保可用性。
    """
    if not file and not image_url:
        raise HTTPException(status_code=400, detail="请上传图片或提供 image_url")

    image_path = None
    try:
        if file:
            # 验证文件
            ext = Path(file.filename).suffix.lower() if file.filename else ""
            if ext not in SUPPORTED_IMAGE_FORMATS:
                raise HTTPException(
                    status_code=400,
                    detail=f"不支持的图片格式：{ext}，支持：{', '.join(SUPPORTED_IMAGE_FORMATS)}"
                )

            # 保存到临时文件
            with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
                content = await file.read()
                if len(content) > MAX_IMAGE_SIZE:
                    raise HTTPException(
                        status_code=400,
                        detail=f"图片文件过大：{len(content) / 1024 / 1024:.2f}MB > 10MB"
                    )
                tmp.write(content)
                tmp.flush()
                image_path = tmp.name
        else:
            # 处理 base64 或 URL
            if image_url.startswith("data:"):
                # base64 data URI
                header, encoded = image_url.split(",", 1)
                if len(encoded) > MAX_IMAGE_SIZE * 2:
                    raise HTTPException(
                        status_code=400,
                        detail="base64 图片数据过大"
                    )
                image_data = base64.b64decode(encoded)
                if len(image_data) > MAX_IMAGE_SIZE:
                    raise HTTPException(
                        status_code=400,
                        detail=f"图片文件过大：{len(image_data) / 1024 / 1024:.2f}MB > 10MB"
                    )
                mime = header.split(":")[1].split(";")[0]
                ext_map = {"image/png": ".png", "image/jpeg": ".jpg", "image/gif": ".gif", "image/webp": ".webp"}
                ext = ext_map.get(mime, ".png")
                with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
                    tmp.write(image_data)
                    tmp.flush()
                    image_path = tmp.name
            else:
                raise HTTPException(status_code=400, detail="image_url 仅支持 base64 data URI 格式")

        # 调用视觉分析
        result = await analyze_image(image_path, prompt=prompt)

        return AnalyzeImageResponse(
            description=result["description"],
            objects=result.get("objects", []),
            text=result.get("text", ""),
            model_used=result["model_used"],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"图片分析失败: {e}")
        raise HTTPException(status_code=500, detail=f"图片分析失败：{str(e)}")
    finally:
        if image_path:
            try:
                Path(image_path).unlink(missing_ok=True)
            except Exception:
                pass


@router.post("/ocr", response_model=OCRResponse)
async def api_ocr(
    file: UploadFile = FastAPIFile(...),
    token: dict = Depends(verify_token),
):
    """
    OCR 文字识别

    从图片中提取所有文字内容，保持原始格式。
    """
    ext = Path(file.filename).suffix.lower() if file.filename else ""
    if ext not in SUPPORTED_IMAGE_FORMATS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的图片格式：{ext}"
        )

    image_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
            content = await file.read()
            if len(content) > MAX_IMAGE_SIZE:
                raise HTTPException(
                    status_code=400,
                    detail=f"图片文件过大：{len(content) / 1024 / 1024:.2f}MB > 10MB"
                )
            tmp.write(content)
            tmp.flush()
            image_path = tmp.name

        text = await extract_text_from_image(image_path)

        return OCRResponse(text=text, model_used="deepseek-ai/DeepSeek-OCR")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"OCR 识别失败: {e}")
        raise HTTPException(status_code=500, detail=f"OCR 识别失败：{str(e)}")
    finally:
        if image_path:
            try:
                Path(image_path).unlink(missing_ok=True)
            except Exception:
                pass


@router.post("/code-from-image", response_model=CodeFromImageResponse)
async def api_code_from_image(
    file: UploadFile = FastAPIFile(...),
    requirement: str = "",
    token: dict = Depends(verify_token),
):
    """
    UI 截图转代码

    根据 UI 设计图/截图生成前端代码建议。
    """
    ext = Path(file.filename).suffix.lower() if file.filename else ""
    if ext not in SUPPORTED_IMAGE_FORMATS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的图片格式：{ext}"
        )

    image_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
            content = await file.read()
            if len(content) > MAX_IMAGE_SIZE:
                raise HTTPException(
                    status_code=400,
                    detail=f"图片文件过大：{len(content) / 1024 / 1024:.2f}MB > 10MB"
                )
            tmp.write(content)
            tmp.flush()
            image_path = tmp.name

        result = await generate_code_from_image(image_path, requirement=requirement)

        return CodeFromImageResponse(
            description=result["description"],
            technology_stack=result["technology_stack"],
            code_structure=result["code_structure"],
            raw_description=result["raw_description"],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"UI 转代码失败: {e}")
        raise HTTPException(status_code=500, detail=f"UI 转代码失败：{str(e)}")
    finally:
        if image_path:
            try:
                Path(image_path).unlink(missing_ok=True)
            except Exception:
                pass


@router.post("/check-safety", response_model=SafetyCheckResponse)
async def api_check_safety(
    file: UploadFile = FastAPIFile(...),
    token: dict = Depends(verify_token),
):
    """
    图片内容安全审核

    检测图片是否包含色情、暴力、侵权等不当内容。
    """
    ext = Path(file.filename).suffix.lower() if file.filename else ""
    if ext not in SUPPORTED_IMAGE_FORMATS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的图片格式：{ext}"
        )

    image_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
            content = await file.read()
            if len(content) > MAX_IMAGE_SIZE:
                raise HTTPException(
                    status_code=400,
                    detail=f"图片文件过大：{len(content) / 1024 / 1024:.2f}MB > 10MB"
                )
            tmp.write(content)
            tmp.flush()
            image_path = tmp.name

        result = await check_image_safety(image_path)

        return SafetyCheckResponse(
            safe=result["safe"],
            reason=result["reason"],
            flags=result["flags"],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"安全审核失败: {e}")
        raise HTTPException(status_code=500, detail=f"安全审核失败：{str(e)}")
    finally:
        if image_path:
            try:
                Path(image_path).unlink(missing_ok=True)
            except Exception:
                pass
