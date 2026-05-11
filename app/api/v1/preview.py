"""
文件预览 API - 优化版

功能：
1. 统一预览接口
2. 智能格式检测
3. 缩略图生成
4. 分片加载
5. 实时协作
6. AI 内容分析
"""
import asyncio
import base64
import hashlib
import io
import json
import logging
import mimetypes
import os
import re
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
from enum import Enum

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse, FileResponse, JSONResponse
from fastapi.concurrency import run_in_threadpool
import aiofiles

from app.utils.security import verify_token

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/preview", tags=["文件预览"])

# 预览配置
PREVIEW_CONFIG = {
    "max_file_size": 100 * 1024 * 1024,  # 100MB
    "chunk_size": 1024 * 1024,  # 1MB 分片
    "thumbnail_size": (400, 300),
    "cache_ttl": 3600,  # 1 小时
    "supported_formats": {
        "document": ["pdf", "docx", "xlsx", "pptx", "md", "txt"],
        "image": ["jpg", "jpeg", "png", "gif", "svg", "webp", "bmp"],
        "code": ["py", "js", "ts", "java", "c", "cpp", "go", "rs", "vue", "html", "css", "json", "yaml"],
        "media": ["mp4", "webm", "mp3", "wav"],
        "archive": ["zip", "rar", "7z"]
    }
}


class FileType(str, Enum):
    DOCUMENT = "document"
    IMAGE = "image"
    CODE = "code"
    MEDIA = "media"
    ARCHIVE = "archive"
    OTHER = "other"


# 内存缓存（生产环境应使用 Redis）
preview_cache = {}
_preview_cache_lock = threading.Lock()


@router.get("/file/{file_id}")
async def preview_file(
    file_id: str,
    format: Optional[str] = None,
    page: int = Query(1, ge=1, description="页码"),
    quality: str = Query("high", description="质量：low/medium/high"),
    token: dict = Depends(verify_token)
):
    """
    统一文件预览接口
    
    自动检测文件类型并返回对应的预览数据
    """
    user_id = token.get("sub", "anonymous")
    logger.info(f"预览请求 | user: {user_id} | file: {file_id}")
    
    # 1. 检查缓存
    cache_key = f"{file_id}_{page}_{quality}"
    with _preview_cache_lock:
        if cache_key in preview_cache:
            cache_entry = preview_cache[cache_key]
            if time.time() - cache_entry["time"] < PREVIEW_CONFIG["cache_ttl"]:
                logger.info(f"缓存命中 | file: {file_id}")
                return JSONResponse(cache_entry["data"])
    
    # 2. 获取文件信息
    file_path = await get_file_path(file_id)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    
    # 3. 检查文件大小
    file_size = file_path.stat().st_size
    if file_size > PREVIEW_CONFIG["max_file_size"]:
        raise HTTPException(
            status_code=413,
            detail=f"文件过大（最大{PREVIEW_CONFIG['max_file_size'] // 1024 // 1024}MB）"
        )
    
    # 4. 检测文件类型
    file_type = detect_file_type(file_path)
    logger.info(f"文件类型：{file_type.value} | file: {file_id}")
    
    # 5. 根据类型生成预览
    try:
        if file_type == FileType.IMAGE:
            preview_data = await generate_image_preview(file_path, quality)
        elif file_type == FileType.PDF:
            preview_data = await generate_pdf_preview(file_path, page)
        elif file_type == FileType.CODE:
            preview_data = await generate_code_preview(file_path)
        elif file_type == FileType.DOCUMENT:
            preview_data = await generate_document_preview(file_path)
        elif file_type == FileType.MEDIA:
            preview_data = await generate_media_preview(file_path)
        else:
            preview_data = {"type": "unknown", "message": "不支持的预览格式"}
        
        # 6. 缓存结果
        with _preview_cache_lock:
            preview_cache[cache_key] = {
                "data": preview_data,
                "time": time.time()
            }

        return JSONResponse(preview_data)
        
    except Exception as e:
        logger.error(f"预览生成失败 | file: {file_id} | error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"预览生成失败：{str(e)}")


@router.get("/file/{file_id}/thumbnail")
async def get_file_thumbnail(
    file_id: str,
    size: str = Query("medium", description="尺寸：small/medium/large"),
    token: dict = Depends(verify_token)
):
    """
    获取文件缩略图
    """
    file_path = await get_file_path(file_id)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    
    file_type = detect_file_type(file_path)
    
    if file_type == FileType.IMAGE:
        thumbnail = await generate_image_thumbnail(file_path, size)
        return StreamingResponse(
            io.BytesIO(thumbnail),
            media_type="image/jpeg"
        )
    elif file_type == FileType.DOCUMENT or file_type == FileType.PDF:
        # 返回默认文档图标
        return await get_default_thumbnail("document")
    elif file_type == FileType.CODE:
        return await get_default_thumbnail("code")
    else:
        return await get_default_thumbnail("file")


@router.get("/file/{file_id}/pages")
async def get_file_pages(
    file_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    token: dict = Depends(verify_token)
):
    """
    分页获取文件内容（适用于大文件）
    """
    file_path = await get_file_path(file_id)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    
    file_type = detect_file_type(file_path)
    
    if file_type in [FileType.CODE, FileType.DOCUMENT]:
        content = await read_file_chunk(file_path, page, page_size)
        return {
            "page": page,
            "page_size": page_size,
            "has_more": True,  # 实际应检查文件是否结束
            "content": content
        }
    else:
        raise HTTPException(status_code=400, detail="该文件类型不支持分页预览")


@router.post("/file/compare")
async def compare_files(
    file1_id: str,
    file2_id: str,
    token: dict = Depends(verify_token)
):
    """
    对比两个文件（代码/文本）
    """
    file1_path = await get_file_path(file1_id)
    file2_path = await get_file_path(file2_id)
    
    if not file1_path.exists() or not file2_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    
    # 读取文件内容
    content1 = file1_path.read_text(encoding="utf-8", errors="ignore")
    content2 = file2_path.read_text(encoding="utf-8", errors="ignore")
    
    # 生成 diff
    diff_result = generate_diff(content1.splitlines(), content2.splitlines())
    
    return {
        "file1": file1_id,
        "file2": file2_id,
        "diff": diff_result,
        "stats": {
            "additions": sum(1 for line in diff_result if line.startswith("+")),
            "deletions": sum(1 for line in diff_result if line.startswith("-")),
            "unchanged": sum(1 for line in diff_result if not line.startswith(("+", "-")))
        }
    }


@router.websocket("/file/{file_id}/collaborate")
async def collaborate_preview(websocket: WebSocket, file_id: str):
    """
    实时协作预览（WebSocket）
    """
    await websocket.accept()
    
    # 加入协作文档
    room_id = f"preview:{file_id}"
    
    try:
        while True:
            # 接收客户端消息
            data = await websocket.receive_json()
            
            # 广播给其他协作者
            await broadcast_to_room(
                room_id,
                {
                    "type": data.get("type"),
                    "user": websocket.headers.get("X-User-Id", "anonymous"),
                    "data": data.get("data"),
                    "timestamp": time.time()
                }
            )
            
    except WebSocketDisconnect:
        logger.info(f"用户断开协作 | room: {room_id}")
    except Exception as e:
        logger.error(f"协作错误 | room: {room_id} | error: {str(e)}")


@router.get("/file/{file_id}/ai-summary")
async def get_ai_summary(
    file_id: str,
    length: str = Query("short", description="摘要长度：short/medium/long"),
    token: dict = Depends(verify_token)
):
    """
    AI 生成文件摘要
    """
    file_path = await get_file_path(file_id)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    
    # 读取文件内容（限制长度）
    content = file_path.read_text(encoding="utf-8", errors="ignore")[:10000]
    
    # 调用 AI 生成摘要
    summary = await generate_ai_summary(content, length)
    
    return {
        "file_id": file_id,
        "summary": summary,
        "length": length,
        "generated_at": datetime.now().isoformat()
    }


@router.post("/file/{file_id}/annotation")
async def add_annotation(
    file_id: str,
    annotation: Dict[str, Any],
    token: dict = Depends(verify_token)
):
    """
    添加文件批注
    """
    user_id = token.get("sub", "anonymous")
    
    annotation_data = {
        "id": f"ann_{int(time.time() * 1000)}",
        "file_id": file_id,
        "author": user_id,
        "content": annotation.get("content"),
        "type": annotation.get("type", "text"),
        "position": annotation.get("position"),
        " created_at": datetime.now().isoformat()
    }
    
    # 存储批注（实际应存储到数据库）
    annotations_key = f"annotations:{file_id}"
    with _preview_cache_lock:
        if annotations_key not in preview_cache:
            preview_cache[annotations_key] = []
        preview_cache[annotations_key].append(annotation_data)

    return annotation_data


@router.get("/file/{file_id}/annotations")
async def get_annotations(
    file_id: str,
    token: dict = Depends(verify_token)
):
    """
    获取文件所有批注
    """
    annotations_key = f"annotations:{file_id}"
    with _preview_cache_lock:
        annotations = preview_cache.get(annotations_key, [])

    return {
        "file_id": file_id,
        "total": len(annotations),
        "annotations": annotations
    }


# ============ 辅助函数 ============

async def get_file_path(file_id: str) -> Path:
    """获取文件路径"""
    # 实际项目应从数据库查询文件路径
    base_dir = Path("./uploads")
    return base_dir / file_id


def detect_file_type(file_path: Path) -> FileType:
    """检测文件类型"""
    ext = file_path.suffix.lower().lstrip(".")
    
    if ext in PREVIEW_CONFIG["supported_formats"]["document"]:
        return FileType.DOCUMENT
    elif ext in PREVIEW_CONFIG["supported_formats"]["image"]:
        return FileType.IMAGE
    elif ext in PREVIEW_CONFIG["supported_formats"]["code"]:
        return FileType.CODE
    elif ext in PREVIEW_CONFIG["supported_formats"]["media"]:
        return FileType.MEDIA
    elif ext in PREVIEW_CONFIG["supported_formats"]["archive"]:
        return FileType.ARCHIVE
    else:
        return FileType.OTHER


async def generate_image_preview(file_path: Path, quality: str) -> Dict[str, Any]:
    """生成图片预览"""
    # 返回图片 URL 和元数据
    return {
        "type": "image",
        "url": f"/api/v1/files/download/{file_path.name}",
        "metadata": {
            "width": 0,  # 实际应读取图片元数据
            "height": 0,
            "format": file_path.suffix.lstrip("."),
            "size": file_path.stat().st_size
        }
    }


async def generate_image_thumbnail(file_path: Path, size: str) -> bytes:
    """生成图片缩略图"""
    # 实际项目应使用 Pillow 等库生成缩略图
    return file_path.read_bytes()


async def generate_pdf_preview(file_path: Path, page: int) -> Dict[str, Any]:
    """生成 PDF 预览"""
    # 实际项目应使用 pdf2image 或 PyMuPDF
    return {
        "type": "pdf",
        "pages": 1,  # 实际应读取 PDF 页数
        "current_page": page,
        "thumbnail": None
    }


async def generate_code_preview(file_path: Path) -> Dict[str, Any]:
    """生成代码预览"""
    content = file_path.read_text(encoding="utf-8", errors="ignore")
    
    return {
        "type": "code",
        "content": content,
        "language": file_path.suffix.lstrip("."),
        "lines": len(content.splitlines()),
        "size": file_path.stat().st_size
    }


async def generate_document_preview(file_path: Path) -> Dict[str, Any]:
    """生成文档预览"""
    content = file_path.read_text(encoding="utf-8", errors="ignore")
    
    return {
        "type": "document",
        "content": content[:10000],  # 限制返回长度
        "format": file_path.suffix.lstrip("."),
        "size": file_path.stat().st_size
    }


async def generate_media_preview(file_path: Path) -> Dict[str, Any]:
    """生成媒体文件预览"""
    return {
        "type": "media",
        "url": f"/api/v1/files/download/{file_path.name}",
        "format": file_path.suffix.lstrip("."),
        "size": file_path.stat().st_size
    }


async def get_default_thumbnail(doc_type: str) -> StreamingResponse:
    """返回默认缩略图"""
    # 实际应返回对应文件类型的图标
    return StreamingResponse(io.BytesIO(b""), media_type="image/png")


async def read_file_chunk(file_path: Path, page: int, page_size: int) -> str:
    """分块读取文件"""
    start_line = (page - 1) * page_size
    async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
        lines = []
        async for line in f:
            lines.append(line)
            if len(lines) >= start_line + page_size:
                break
        
        return ''.join(lines[start_line:start_line + page_size])


def generate_diff(lines1: List[str], lines2: List[str]) -> List[str]:
    """生成文件差异"""
    import difflib
    diff = list(difflib.unified_diff(lines1, lines2, lineterm=''))
    return diff


async def generate_ai_summary(content: str, length: str) -> str:
    """AI 生成摘要（伪代码）"""
    # 实际应调用 LLM API
    lines = content.splitlines()
    important_lines = [line for line in lines if line.strip() and not line.startswith('#')]
    
    max_lines = {"short": 3, "medium": 5, "long": 10}.get(length, 5)
    
    return "\n".join(important_lines[:max_lines])


async def broadcast_to_room(room_id: str, message: Dict[str, Any]):
    """广播消息到协作房间"""
    # 实际应使用 WebSocket 连接池
    pass


# 缓存清理任务
async def cleanup_cache():
    """定期清理过期缓存"""
    while True:
        current_time = time.time()
        expired_keys = []
        
        for key, entry in preview_cache.items():
            if isinstance(entry, dict) and "time" in entry:
                if current_time - entry["time"] > PREVIEW_CONFIG["cache_ttl"]:
                    expired_keys.append(key)
        
        for key in expired_keys:
            del preview_cache[key]
        
        logger.info(f"缓存清理完成 | 清理：{len(expired_keys)} 项")
        await asyncio.sleep(300)  # 每 5 分钟清理一次
