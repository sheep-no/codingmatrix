"""
ResumeManager - 断点续传管理器

v4.8.0 新增：
- 记录每个分片上传状态和 hash
- 支持从断点恢复上传
- 恢复前验证已上传分片的完整性
"""

import asyncio
import hashlib
import json
import logging
import os
import re
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# upload_id 白名单：仅允许字母/数字/下划线/连字符，防止 ../ 或绝对路径穿越
_UPLOAD_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


@dataclass
class ResumeState:
    """断点续传状态"""
    upload_id: str
    total_chunks: int
    completed_chunks: List[int]
    chunk_hashes: Dict[int, str]
    next_chunk_index: int


class ResumeManager:
    """
    断点续传管理器

    管理大文件上传的分片状态，支持中断后恢复。
    状态文件存储在 upload 目录下的 .resume 子目录中。
    """

    def __init__(self, resume_dir: Optional[Path] = None):
        self.resume_dir = resume_dir or Path("uploads/.resume")
        self.resume_dir.mkdir(parents=True, exist_ok=True)
        self._locks: Dict[str, asyncio.Lock] = {}

    def _state_file(self, upload_id: str) -> Path:
        """获取状态文件路径"""
        if not _UPLOAD_ID_RE.match(upload_id or ""):
            raise ValueError(f"非法 upload_id: {upload_id!r}")
        return self.resume_dir / f"{upload_id}.json"

    def _lock_for(self, upload_id: str) -> asyncio.Lock:
        """获取单个 upload_id 的异步锁（同进程内串行化读-改-写）"""
        lock = self._locks.get(upload_id)
        if lock is None:
            lock = self._locks[upload_id] = asyncio.Lock()
        return lock

    @staticmethod
    def _atomic_write(path: Path, content: str) -> None:
        """先写临时文件再原子替换，避免读到半写状态"""
        tmp_path = path.with_name(path.name + ".tmp")
        tmp_path.write_text(content)
        os.replace(tmp_path, path)

    @staticmethod
    def _load_state(path: Path) -> Optional[dict]:
        """读取状态文件，缺失时返回 None"""
        if not path.exists():
            return None
        return json.loads(path.read_text())

    def compute_chunk_hash(self, data: bytes) -> str:
        """计算分片数据的 MD5 hash"""
        return hashlib.md5(data).hexdigest()

    async def save_chunk_state(
        self,
        upload_id: str,
        chunk_index: int,
        chunk_hash: str,
    ) -> None:
        """
        记录成功上传的分片状态

        Args:
            upload_id: 上传唯一标识
            chunk_index: 分片序号
            chunk_hash: 分片数据 hash
        """
        state_file = self._state_file(upload_id)

        async with self._lock_for(upload_id):
            def _read_modify_write():
                data = self._load_state(state_file) or {
                    "upload_id": upload_id,
                    "completed_chunks": [],
                    "chunk_hashes": {},
                }
                completed = data.setdefault("completed_chunks", [])
                if chunk_index not in completed:
                    completed.append(chunk_index)
                data.setdefault("chunk_hashes", {})[chunk_index] = chunk_hash
                self._atomic_write(state_file, json.dumps(data))

            # 文件 I/O 放到线程，避免阻塞事件循环
            await asyncio.to_thread(_read_modify_write)

    async def get_resume_state(self, upload_id: str, total_chunks: int) -> ResumeState:
        """
        获取断点续传状态

        Args:
            upload_id: 上传唯一标识
            total_chunks: 总分片数

        Returns:
            ResumeState 包含已完成分片和下一个分片序号
        """
        state_file = self._state_file(upload_id)

        data = await asyncio.to_thread(self._load_state, state_file)
        if data is None:
            return ResumeState(
                upload_id=upload_id,
                total_chunks=total_chunks,
                completed_chunks=[],
                chunk_hashes={},
                next_chunk_index=0,
            )

        completed = data.get("completed_chunks", [])
        hashes = data.get("chunk_hashes", {})

        next_index = max(completed) + 1 if completed else 0
        next_index = min(next_index, total_chunks)

        return ResumeState(
            upload_id=upload_id,
            total_chunks=total_chunks,
            completed_chunks=completed,
            chunk_hashes=hashes,
            next_chunk_index=next_index,
        )

    async def validate_completed_chunks(
        self,
        upload_id: str,
        chunks_dir: Path,
    ) -> List[int]:
        """
        验证已上传分片的完整性

        Args:
            upload_id: 上传唯一标识
            chunks_dir: 分片存储目录

        Returns:
            验证失败的分片序号列表（需要重新上传）
        """
        state_file = self._state_file(upload_id)

        data = await asyncio.to_thread(self._load_state, state_file)
        if data is None:
            return []

        hashes = data.get("chunk_hashes", {})

        def _verify():
            invalid_chunks = []
            for chunk_index, expected_hash in hashes.items():
                chunk_file = chunks_dir / f"{upload_id}_chunk_{chunk_index}"
                if not chunk_file.exists():
                    invalid_chunks.append(int(chunk_index))
                    continue

                actual_hash = self.compute_chunk_hash(chunk_file.read_bytes())
                if actual_hash != expected_hash:
                    invalid_chunks.append(int(chunk_index))
                    logger.warning(
                        f"分片 {chunk_index} hash 不匹配: "
                        f"expected={expected_hash}, actual={actual_hash}"
                    )
            return invalid_chunks

        # 逐分片读文件 + 哈希同样是阻塞 I/O，整体放到线程
        return await asyncio.to_thread(_verify)

    async def clear_state(self, upload_id: str) -> None:
        """清除上传状态（合并完成后调用）"""
        state_file = self._state_file(upload_id)
        async with self._lock_for(upload_id):
            await asyncio.to_thread(state_file.unlink, missing_ok=True)
