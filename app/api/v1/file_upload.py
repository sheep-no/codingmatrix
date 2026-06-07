"""
文件上传 API - 供 AI 对话时附加文件/图片使用
"""
import asyncio
import hashlib
import logging
import os
import uuid
from typing import Optional, List
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select, func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.file import File
from app.models.task import Task
from app.utils.security import verify_token
from app.schema.file_schema import FileUploadResponse, FileListResponse
from app.core.file_validator import validate_file_content  # 新增安全验证
from typing import List

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/files", tags=["文件上传"])

# 配置
UPLOAD_DIR = Path("./uploads")
CHUNKS_DIR = UPLOAD_DIR / ".chunks"  # 断点续传分片目录
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB
CHUNK_SIZE = 5 * 1024 * 1024  # 分片大小 5MB

# 分片上传锁（保护并发上传同一文件）
_chunk_locks: dict[str, asyncio.Lock] = {}
_chunk_locks_lock = asyncio.Lock()


class ChunkMetadata:
    """分片元数据"""
    def __init__(self, file_id: str, total_chunks: int, uploaded_chunks: List[int]):
        self.file_id = file_id
        self.total_chunks = total_chunks
        self.uploaded_chunks = uploaded_chunks
    
    @classmethod
    def load(cls, file_id: str, total_chunks: int) -> "ChunkMetadata":
        """从文件加载元数据"""
        meta_path = CHUNKS_DIR / file_id / "metadata.json"
        uploaded = []
        if meta_path.exists():
            import json
            data = json.loads(meta_path.read_text())
            uploaded = data.get("uploaded_chunks", [])
        return cls(file_id, total_chunks, uploaded)
    
    def save(self):
        """保存元数据"""
        meta_path = CHUNKS_DIR / self.file_id / "metadata.json"
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        import json
        meta_path.write_text(json.dumps({
            "file_id": self.file_id,
            "total_chunks": self.total_chunks,
            "uploaded_chunks": self.uploaded_chunks
        }))
    
    def add_chunk(self, chunk_index: int):
        """记录已上传的分片"""
        if chunk_index not in self.uploaded_chunks:
            self.uploaded_chunks.append(chunk_index)
            self.uploaded_chunks.sort()
            self.save()
    
    def is_complete(self) -> bool:
        """检查是否所有分片都已上传"""
        return len(self.uploaded_chunks) == self.total_chunks and \
               set(self.uploaded_chunks) == set(range(self.total_chunks))


async def _get_chunk_lock(file_id: str) -> asyncio.Lock:
    """获取文件分片锁（asyncio 安全，v4.8.0 改造）"""
    async with _chunk_locks_lock:
        if file_id not in _chunk_locks:
            _chunk_locks[file_id] = asyncio.Lock()
        return _chunk_locks[file_id]
ALLOWED_EXTENSIONS = {
    # 代码文件
    '.py', '.js', '.ts', '.java', '.cpp', '.c', '.go', '.rs', '.rb',
    '.html', '.css', '.scss', '.vue', '.jsx', '.tsx',
    # 配置文件
    '.json', '.yaml', '.yml', '.toml', '.ini', '.xml',
    # 文档
    '.txt', '.md', '.rst', '.pdf', '.doc', '.docx',
    # 压缩包
    '.zip', '.tar', '.gz', '.rar', '.7z',
    # 图片
    '.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp',
}


def calculate_file_hash(content: bytes) -> str:
    """计算文件 SHA256 哈希"""
    sha256 = hashlib.sha256()
    sha256.update(content)
    return sha256.hexdigest()


def validate_file_upload(file: UploadFile) -> None:
    """验证文件大小和扩展名（基础验证）"""
    # 检查文件大小
    file.file.seek(0, 2)  # 移动到文件末尾
    size = file.file.tell()
    file.file.seek(0)  # 重置指针
    
    if size == 0:
        raise HTTPException(status_code=400, detail="文件不能为空")
    if size > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail=f"文件大小超过限制 ({MAX_FILE_SIZE // 1024 // 1024}MB)")
    
    # 检查扩展名
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件类型：{ext}。允许的类型：{', '.join(ALLOWED_EXTENSIONS)}"
        )


@router.post("/upload", response_model=FileUploadResponse, summary="上传文件")
async def upload_file(
    file: UploadFile,
    conversation_id: Optional[int] = None,
    token: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db)
):
    """
    上传文件
    
    - 支持多种文件格式（代码、文档、图片、压缩包）
    - 自动检测文件重复（基于 SHA256）
    - 文件大小限制 100MB
    - 会话隔离：文件属于特定对话上下文
    
    参数：
    - conversation_id: 会话 ID（可选，用于隔离文件访问权限）
    """
    user_id = int(token.get("sub"))
    logger.info(f"文件上传请求 | user_id={user_id} | filename={file.filename} | conversation_id={conversation_id}")
    
    try:
        # 1. 基础验证（大小和扩展名）
        validate_file_upload(file)
        
        # 2. 读取文件内容
        content = await file.read()
        
        # 3. 深度验证（MIME 类型、文件内容、安全性检查）
        detected_mime, safe_filename = validate_file_content(content, file.filename)
        
        logger.info(f"文件验证通过 | detected_mime={detected_mime} | safe_filename={safe_filename}")
        
        # 4. 计算哈希
        file_hash = calculate_file_hash(content)
        
        # 检查是否已存在（去重）
        result = await db.execute(
            select(File).where(
                File.file_hash == file_hash,
                File.user_id == user_id,
                File.is_deleted == 0
            )
        )
        existing_file = result.scalar()
        
        if existing_file:
            logger.info(f"文件已存在，返回已有记录 | file_id={existing_file.id}")
            return FileUploadResponse(**existing_file.to_dict())
        
        # 生成存储路径
        file_ext = Path(file.filename).suffix.lower()
        storage_filename = f"{uuid.uuid4().hex}{file_ext}"
        storage_path = UPLOAD_DIR / datetime.utcnow().strftime("%Y/%m/%d") / storage_filename
        
        # 创建目录
        storage_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 保存文件
        with open(storage_path, 'wb') as f:
            f.write(content)
        
        # 创建数据库记录
        db_file = File(
            filename=file.filename,
            file_path=str(storage_path),
            file_size=len(content),
            content_type=file.content_type,
            file_hash=file_hash,
            user_id=user_id,
            conversation_id=conversation_id
        )
        
        db.add(db_file)
        await db.commit()
        await db.refresh(db_file)
        
        logger.info(f"文件上传成功 | file_id={db_file.id} | size={db_file.file_size}")
        
        return FileUploadResponse(**db_file.to_dict())
        
    except HTTPException:
        raise
    except (ValueError, TypeError, RuntimeError, OSError, SQLAlchemyError) as e:
        logger.error(f"文件上传失败 | error={str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"上传失败：{str(e)}")


@router.get("/{file_id}/download", summary="下载文件")
async def download_file(
    file_id: int,
    token: dict = Depends(verify_token)
):
    """
    下载文件
    
    - 需要权限验证
    - 支持断点续传（通过 /upload/init, /upload/chunk, /upload/merge 端点）
    """
    user_id = int(token.get("sub"))
    logger.info(f"文件下载请求 | user_id={user_id} | file_id={file_id}")
    
    # 查询文件
    async with get_db() as db:
        result = await db.execute(
            select(File).where(
                File.id == file_id,
                File.user_id == user_id,
                File.is_deleted == 0
            )
        )
        db_file = result.scalar()
    
    if not db_file:
        raise HTTPException(status_code=404, detail="文件不存在")
    
    # 检查文件是否存在
    file_path = Path(db_file.file_path)
    if not file_path.exists():
        logger.error(f"文件物理路径不存在 | path={file_path}")
        raise HTTPException(status_code=404, detail="文件已丢失")
    
    # 返回文件流
    logger.info(f"文件下载成功 | filename={db_file.filename}")
    
    return StreamingResponse(
        open(file_path, 'rb'),
        media_type=db_file.content_type or "application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{db_file.filename}"'
        }
    )


@router.post("/upload/init", summary="初始化分片上传")
async def init_chunked_upload(
    filename: str,
    file_size: int,
    file_hash: str,
    conversation_id: Optional[int] = None,
    token: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db)
):
    """
    初始化分片上传（断点续传）
    
    - 返回 file_id 和已上传的分片列表
    - 支持秒传（基于文件哈希）
    
    参数:
    - filename: 文件名
    - file_size: 文件大小（字节）
    - file_hash: 文件 SHA256 哈希
    - conversation_id: 会话 ID
    """
    user_id = int(token.get("sub"))
    logger.info(f"初始化分片上传 | user_id={user_id} | filename={filename} | size={file_size}")
    
    # 检查是否存在相同哈希的文件（秒传）
    existing_result = await db.execute(
        select(File).where(
            File.file_hash == file_hash,
            File.user_id == user_id,
            File.is_deleted == 0
        )
    )
    existing_file = existing_result.scalar_one_or_none()
    
    if existing_file:
        logger.info(f"文件已存在，支持秒传 | file_id={existing_file.id}")
        return {
            "file_id": str(existing_file.id),
            "status": "exists",
            "message": "文件已存在，支持秒传",
            "existing_file": existing_file.to_dict()
        }
    
    # 计算总分片数
    total_chunks = (file_size + CHUNK_SIZE - 1) // CHUNK_SIZE
    
    # 生成 file_id
    file_id = str(uuid.uuid4())
    
    # 加载或创建分片元数据
    meta_path = CHUNKS_DIR / file_id / "metadata.json"
    uploaded_chunks = []
    if meta_path.exists():
        import json
        data = json.loads(meta_path.read_text())
        uploaded_chunks = data.get("uploaded_chunks", [])
        logger.info(f"恢复断点续传 | file_id={file_id} | uploaded={len(uploaded_chunks)}/{total_chunks}")
    
    return {
        "file_id": file_id,
        "status": "new",
        "total_chunks": total_chunks,
        "chunk_size": CHUNK_SIZE,
        "uploaded_chunks": uploaded_chunks,
        "message": "请上传缺失的分片"
    }


@router.post("/upload/chunk/{file_id}/{chunk_index}", summary="上传分片")
async def upload_chunk(
    file_id: str,
    chunk_index: int,
    chunk: UploadFile,
    total_chunks: int,
    token: dict = Depends(verify_token)
):
    """
    上传单个分片

    - 支持断点续传
    - 分片会自动保存到临时目录
    """
    user_id = int(token.get("sub"))
    chunk_dir = CHUNKS_DIR / file_id
    chunk_dir.mkdir(parents=True, exist_ok=True)

    chunk_path = chunk_dir / f"chunk_{chunk_index}"

    # 保存分片
    content = await chunk.read()
    chunk_path.write_bytes(content)

    logger.info(f"分片上传成功 | file_id={file_id} | chunk={chunk_index}/{total_chunks} | size={len(content)}")

    # 更新元数据（需要锁保护并发访问）
    lock = await _get_chunk_lock(file_id)
    async with lock:
        meta = ChunkMetadata.load(file_id, total_chunks)
        meta.add_chunk(chunk_index)

        return {
            "status": "success",
            "chunk_index": chunk_index,
            "uploaded_chunks": meta.uploaded_chunks,
            "is_complete": meta.is_complete()
        }


@router.post("/upload/merge/{file_id}", summary="合并分片")
async def merge_chunks(
    file_id: str,
    filename: str,
    file_hash: str,
    file_size: int,
    content_type: Optional[str] = None,
    conversation_id: Optional[int] = None,
    token: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db)
):
    """
    合并所有分片为完整文件

    - 验证分片完整性
    - 合并分片并计算最终哈希
    - 保存到正式存储目录
    """
    user_id = int(token.get("sub"))
    logger.info(f"合并分片 | file_id={file_id} | filename={filename}")

    chunk_dir = CHUNKS_DIR / file_id

    # 使用锁保护合并操作
    lock = await _get_chunk_lock(file_id)
    async with lock:
        meta = ChunkMetadata.load(file_id, 0)

        # 检查所有分片是否已上传
        if not meta.is_complete():
            missing = set(range(meta.total_chunks)) - set(meta.uploaded_chunks)
            raise HTTPException(
                status_code=400,
                detail=f"分片不完整，缺失：{missing}"
            )

        # 合并文件
        output_dir = UPLOAD_DIR / datetime.now().strftime("%Y%m%d")
        output_dir.mkdir(parents=True, exist_ok=True)

        # 清理文件名，防止路径穿越
        safe_filename = Path(filename).name
        file_path = output_dir / f"{uuid.uuid4()}_{safe_filename}"

        with open(file_path, 'wb') as f:
            for i in range(meta.total_chunks):
                chunk_path = chunk_dir / f"chunk_{i}"
                if not chunk_path.exists():
                    raise HTTPException(status_code=500, detail=f"分片 {i} 丢失")
                f.write(chunk_path.read_bytes())

        # 验证合并后的文件哈希
        merged_content = file_path.read_bytes()
        actual_hash = hashlib.sha256(merged_content).hexdigest()

        if actual_hash != file_hash:
            logger.error(f"哈希不匹配 | expected={file_hash}, actual={actual_hash}")
            file_path.unlink()
            raise HTTPException(
                status_code=500,
                detail="文件校验失败，请重新上传"
            )

        # 写入数据库
        db_file = File(
            filename=filename,
            file_path=str(file_path),
            file_size=len(merged_content),
            content_type=content_type,
            file_hash=actual_hash,
            user_id=user_id,
            conversation_id=conversation_id
        )

        db.add(db_file)
        await db.commit()
        await db.refresh(db_file)

        # 清理临时分片
        import shutil
        shutil.rmtree(chunk_dir)

        logger.info(f"分片合并成功 | file_id={db_file.id} | path={db_file.file_path}")
    
    return {
        "success": True,
        "file": db_file.to_dict(),
        "message": "分片上传完成"
    }
