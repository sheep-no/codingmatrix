"""
文件上传 API - 供 AI 对话时附加文件/图片使用
"""
import asyncio
import hashlib
import logging
import os
import shutil
import time
import uuid
from contextlib import asynccontextmanager
from typing import Optional, List
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select, func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.file import File
from app.models.task import Task
from app.utils.security import verify_token
from app.schema.file_schema import FileUploadResponse, FileListResponse
from app.core.file_validator import validate_file_path

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/files", tags=["文件上传"])

# 配置
UPLOAD_DIR = Path("./uploads")
CHUNKS_DIR = UPLOAD_DIR / ".chunks"  # 断点续传分片目录
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB
CHUNK_SIZE = 5 * 1024 * 1024  # 分片大小 5MB
MAX_TOTAL_CHUNKS = (MAX_FILE_SIZE + CHUNK_SIZE - 1) // CHUNK_SIZE  # 由文件上限推导
CHUNK_TTL_SECONDS = 24 * 60 * 60  # 孤儿分片保留时长（无活动即视为中断上传）

# 分片上传锁（保护并发上传同一文件）；按 (user_id, file_id) 隔离，用引用计数在
# 最后一个使用者离开后回收，避免锁表随上传次数无界增长（FL5）。
_chunk_locks: dict[tuple[int, str], asyncio.Lock] = {}
_chunk_lock_refs: dict[tuple[int, str], int] = {}
_chunk_locks_lock = asyncio.Lock()


class ChunkMetadata:
    """分片元数据"""
    def __init__(
        self,
        file_id: str,
        total_chunks: int,
        uploaded_chunks: List[int],
        base_dir: Optional[Path] = None,
    ):
        self.file_id = file_id
        self.total_chunks = total_chunks
        self.uploaded_chunks = uploaded_chunks
        # 显式传入时固定；否则延迟到使用时读取模块级 CHUNKS_DIR（便于测试 patch）
        self._base_dir = Path(base_dir) if base_dir is not None else None

    def _meta_path(self) -> Path:
        root = self._base_dir if self._base_dir is not None else CHUNKS_DIR
        return root / self.file_id / "metadata.json"

    @classmethod
    def load(
        cls,
        file_id: str,
        total_chunks: int,
        base_dir: Optional[Path] = None,
    ) -> "ChunkMetadata":
        """从文件加载元数据"""
        root = Path(base_dir) if base_dir is not None else CHUNKS_DIR
        meta_path = root / file_id / "metadata.json"
        uploaded = []
        if meta_path.exists():
            import json
            data = json.loads(meta_path.read_text())
            uploaded = data.get("uploaded_chunks", [])
        return cls(file_id, total_chunks, uploaded, base_dir=base_dir)
    
    def save(self):
        """保存元数据"""
        meta_path = self._meta_path()
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


@asynccontextmanager
async def _chunk_lock_scope(user_id: int, file_id: str):
    """独占某用户某文件的分片操作，并在无人使用时回收入口。"""
    key = (user_id, file_id)
    async with _chunk_locks_lock:
        lock = _chunk_locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            _chunk_locks[key] = lock
        _chunk_lock_refs[key] = _chunk_lock_refs.get(key, 0) + 1
    try:
        async with lock:
            yield
    finally:
        async with _chunk_locks_lock:
            remaining = _chunk_lock_refs.get(key, 1) - 1
            if remaining > 0:
                _chunk_lock_refs[key] = remaining
            else:
                _chunk_lock_refs.pop(key, None)
                _chunk_locks.pop(key, None)


def _storage_date_dir() -> Path:
    """上传落盘的日期子目录；统一时钟与格式（原单文件用 utcnow %Y/%m/%d，合并用 now %Y%m%d）。"""
    return UPLOAD_DIR / datetime.now().strftime("%Y%m%d")


def _cleanup_stale_user_chunks(user_dir: Path) -> None:
    """清理当前用户久未活动的分片目录，避免中断的上传永久占用磁盘（FL3）。
    只扫当前用户目录，不跨用户清理；活跃上传会持续刷新 mtime，故过期即视为中断。
    """
    if not user_dir.is_dir():
        return
    cutoff = time.time() - CHUNK_TTL_SECONDS
    for entry in user_dir.iterdir():
        try:
            if entry.is_dir() and entry.stat().st_mtime < cutoff:
                shutil.rmtree(entry, ignore_errors=True)
                logger.info(f"已清理过期分片目录 | {entry}")
        except OSError as error:
            logger.warning(f"清理分片目录失败 | {entry} | error={error}")


def _scoped_chunk_dir(user_id: int, file_id: str) -> Path:
    """分片目录按用户隔离，避免仅凭 file_id 越权操作他人分片（FL1）。

    file_id 由客户端提供，同时拒绝路径穿越字符。
    """
    if not file_id or "/" in file_id or "\\" in file_id or ".." in file_id:
        raise HTTPException(status_code=400, detail="非法的 file_id")
    return CHUNKS_DIR / str(user_id) / file_id


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
    """计算文件 SHA256 哈希（保留给旧调用方）。"""
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
    
    temp_path = None
    try:
        # 1. 基础验证（大小和扩展名）
        validate_file_upload(file)
        
        # 2. 流式写入临时文件，避免将整个上传内容放入内存。
        temp_path = UPLOAD_DIR / ".tmp" / f"{uuid.uuid4().hex}.upload"
        temp_path.parent.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256()
        total_size = 0
        with open(temp_path, "wb") as temp_file:
            while chunk := await file.read(CHUNK_SIZE):
                total_size += len(chunk)
                if total_size > MAX_FILE_SIZE:
                    raise HTTPException(status_code=413, detail=f"文件大小超过限制 ({MAX_FILE_SIZE // 1024 // 1024}MB)")
                digest.update(chunk)
                temp_file.write(chunk)

        # 3. 深度验证（MIME 类型、文件内容、安全性检查）
        detected_mime, safe_filename = validate_file_path(temp_path, file.filename)
        
        logger.info(f"文件验证通过 | detected_mime={detected_mime} | safe_filename={safe_filename}")
        
        # 4. 计算哈希
        file_hash = digest.hexdigest()
        
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
        storage_path = _storage_date_dir() / storage_filename
        
        # 创建目录
        storage_path.parent.mkdir(parents=True, exist_ok=True)
        os.replace(temp_path, storage_path)
        
        # 创建数据库记录
        db_file = File(
            filename=file.filename,
            file_path=str(storage_path),
            file_size=total_size,
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
    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink()


@router.get("/{file_id}/download", summary="下载文件")
async def download_file(
    file_id: int,
    token: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db)
):
    """
    下载文件
    
    - 需要权限验证
    - 支持断点续传（通过 /upload/init, /upload/chunk, /upload/merge 端点）
    """
    user_id = int(token.get("sub"))
    logger.info(f"文件下载请求 | user_id={user_id} | file_id={file_id}")
    
    # 查询文件
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
            "Content-Disposition": f'attachment; filename="{Path(db_file.filename).name}"'
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

    if file_size <= 0 or file_size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"文件大小超过限制 (最大 {MAX_FILE_SIZE // 1024 // 1024}MB)"
        )

    # 顺带回收本用户此前中断上传留下的过期分片
    _cleanup_stale_user_chunks(CHUNKS_DIR / str(user_id))

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
    
    # 加载或创建分片元数据（按用户隔离，避免越权）
    meta_path = _scoped_chunk_dir(user_id, file_id) / "metadata.json"
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

    if total_chunks < 1 or total_chunks > MAX_TOTAL_CHUNKS:
        raise HTTPException(status_code=400, detail="非法的分片总数")
    if chunk_index < 0 or chunk_index >= total_chunks:
        raise HTTPException(status_code=400, detail="非法的分片序号")

    chunk_dir = _scoped_chunk_dir(user_id, file_id)
    chunk_dir.mkdir(parents=True, exist_ok=True)

    chunk_path = chunk_dir / f"chunk_{chunk_index}"

    # 保存分片；多读 1 字节以识别超限，避免无上限写入磁盘（FL3）
    content = await chunk.read(CHUNK_SIZE + 1)
    if len(content) > CHUNK_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"单个分片超过限制 ({CHUNK_SIZE // 1024 // 1024}MB)"
        )
    chunk_path.write_bytes(content)

    logger.info(f"分片上传成功 | file_id={file_id} | chunk={chunk_index}/{total_chunks} | size={len(content)}")

    # 更新元数据（需要锁保护并发访问）
    async with _chunk_lock_scope(user_id, file_id):
        meta = ChunkMetadata.load(file_id, total_chunks, base_dir=chunk_dir.parent)
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

    chunk_dir = _scoped_chunk_dir(user_id, file_id)

    # 使用锁保护合并操作
    async with _chunk_lock_scope(user_id, file_id):
        # 从文件加载元数据（包含正确的 total_chunks）
        meta_path = chunk_dir / "metadata.json"
        if not meta_path.exists():
            raise HTTPException(status_code=404, detail="分片元数据不存在")
        import json as _json
        meta_data = _json.loads(meta_path.read_text())
        total = meta_data.get("total_chunks", 0)
        meta = ChunkMetadata.load(file_id, total, base_dir=chunk_dir.parent)

        # 检查所有分片是否已上传
        if not meta.is_complete():
            missing = set(range(meta.total_chunks)) - set(meta.uploaded_chunks)
            raise HTTPException(
                status_code=400,
                detail=f"分片不完整，缺失：{missing}"
            )

        # 合并文件
        output_dir = _storage_date_dir()
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

        # 验证合并后的文件哈希（分块计算，避免大文件 OOM）
        actual_hash = hashlib.sha256()
        with open(file_path, 'rb') as f:
            while chunk := f.read(8192):
                actual_hash.update(chunk)
        actual_hash_hex = actual_hash.hexdigest()

        if actual_hash_hex != file_hash:
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
            file_size=file_path.stat().st_size,
            content_type=content_type,
            file_hash=actual_hash_hex,
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
