"""
PPT 文件存储管理器

负责管理 PPT 文件的生命周期：
- 保存生成的文件
- 获取文件元数据
- 删除过期文件
- 检查存储使用率
"""

import asyncio
import json
import logging
import shutil
import time
import uuid
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

# 默认存储目录
DEFAULT_STORAGE_DIR = Path("./data/ppt-files")

# 文件保留天数
DEFAULT_RETENTION_DAYS = 7

# 存储使用率阈值（超过此比例触发清理）
STORAGE_THRESHOLD = 0.80


@dataclass
class FileMetadata:
    """文件元数据"""
    file_id: str
    task_id: str
    user_id: int
    filename: str
    format: str  # pptx, pdf, html, markdown
    size_bytes: int
    created_at: str  # ISO 8601
    last_accessed: str
    access_count: int = 0
    download_url: str = ""
    error_message: Optional[str] = None


class FileStorageError(Exception):
    """文件存储异常"""
    pass


class FileNotFoundError(FileStorageError):
    """文件不存在异常"""
    pass


class StorageQuotaExceededError(FileStorageError):
    """存储配额超出异常"""
    pass


class FileStorageManager:
    """
    PPT 文件存储管理器
    
    管理 PPT 文件的存储、检索和清理。
    """
    
    def __init__(
        self,
        storage_dir: Optional[Path] = None,
        retention_days: int = DEFAULT_RETENTION_DAYS,
        max_total_size_gb: float = 10.0,
    ):
        """
        初始化文件存储管理器
        
        Args:
            storage_dir: 存储目录路径
            retention_days: 文件保留天数
            max_total_size_gb: 最大存储容量（GB）
        """
        self._storage_dir = storage_dir or DEFAULT_STORAGE_DIR
        self._retention_days = retention_days
        self._max_total_size_bytes = int(max_total_size_gb * 1024 * 1024 * 1024)
        
        # 元数据缓存（避免频繁读取文件）
        self._metadata_cache: Dict[str, FileMetadata] = {}
        
        # 确保存储目录存在
        self._storage_dir.mkdir(parents=True, exist_ok=True)
    
    async def save(
        self,
        task_id: str,
        file_path: Path,
        user_id: int,
        output_format: str = "pptx",
    ) -> str:
        """
        保存文件并返回文件 ID
        
        Args:
            task_id: 任务 ID
            file_path: 源文件路径
            user_id: 用户 ID
            output_format: 输出格式
            
        Returns:
            file_id: 文件唯一标识符
        
        Raises:
            FileStorageError: 保存失败
            StorageQuotaExceededError: 存储容量不足
        """
        if not file_path.exists():
            raise FileStorageError(f"源文件不存在：{file_path}")
        
        # 检查存储容量
        await self._check_storage_capacity(file_path.stat().st_size)
        
        # 生成文件 ID
        file_id = str(uuid.uuid4())
        
        # 创建文件目录
        file_dir = self._storage_dir / file_id
        file_dir.mkdir(parents=True, exist_ok=True)
        
        # 确定文件名
        filename = f"{task_id}.{output_format}"
        dest_path = file_dir / filename
        
        # 复制文件到存储目录
        try:
            shutil.copy2(str(file_path), str(dest_path))
        except Exception as e:
            raise FileStorageError(f"文件复制失败：{e}")
        
        # 创建元数据
        now = time.time()
        metadata = FileMetadata(
            file_id=file_id,
            task_id=task_id,
            user_id=user_id,
            filename=filename,
            format=output_format,
            size_bytes=dest_path.stat().st_size,
            created_at=_timestamp_to_iso(now),
            last_accessed=_timestamp_to_iso(now),
            download_url=f"/api/v1/pptx/download/{file_id}",
        )
        
        # 保存元数据
        await self._save_metadata(file_id, metadata)
        
        # 更新缓存
        self._metadata_cache[file_id] = metadata
        
        logger.info(
            f"文件保存成功 | file_id={file_id} | task_id={task_id} | size={metadata.size_bytes} bytes"
        )
        
        return file_id
    
    async def get(self, file_id: str) -> Optional[FileMetadata]:
        """
        获取文件元数据
        
        Args:
            file_id: 文件 ID
            
        Returns:
            文件元数据，不存在时返回 None
        """
        # 先查缓存
        if file_id in self._metadata_cache:
            metadata = self._metadata_cache[file_id]
            # 更新访问计数
            metadata.access_count += 1
            metadata.last_accessed = _timestamp_to_iso(time.time())
            await self._save_metadata(file_id, metadata)
            return metadata
        
        # 从文件系统读取
        metadata_path = self._storage_dir / file_id / "metadata.json"
        
        if not metadata_path.exists():
            return None
        
        try:
            with open(metadata_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            metadata = FileMetadata(**data)
            metadata.access_count += 1
            metadata.last_accessed = _timestamp_to_iso(time.time())
            
            # 更新缓存
            self._metadata_cache[file_id] = metadata
            
            # 保存更新后的元数据
            await self._save_metadata(file_id, metadata)
            
            return metadata
            
        except Exception as e:
            logger.error(f"读取元数据失败 | file_id={file_id} | error={e}")
            return None
    
    async def get_file_path(self, file_id: str) -> Optional[Path]:
        """
        获取文件的实际路径
        
        Args:
            file_id: 文件 ID
            
        Returns:
            文件路径，不存在时返回 None
        """
        metadata = await self.get(file_id)
        
        if metadata is None:
            return None
        
        file_path = self._storage_dir / file_id / metadata.filename
        
        if not file_path.exists():
            return None
        
        return file_path
    
    async def delete(self, file_id: str) -> bool:
        """
        删除文件及其元数据
        
        Args:
            file_id: 文件 ID
            
        Returns:
            是否删除成功
        """
        file_dir = self._storage_dir / file_id
        
        if not file_dir.exists():
            # 目录不存在，清理缓存
            self._metadata_cache.pop(file_id, None)
            return False
        
        try:
            # 删除目录及内容
            shutil.rmtree(str(file_dir))
            
            # 清理缓存
            self._metadata_cache.pop(file_id, None)
            
            logger.info(f"文件删除成功 | file_id={file_id}")
            return True
            
        except Exception as e:
            logger.error(f"文件删除失败 | file_id={file_id} | error={e}")
            return False
    
    async def cleanup_expired(
        self,
        retention_days: Optional[int] = None,
    ) -> int:
        """
        清理过期文件
        
        Args:
            retention_days: 保留天数，不传则使用默认值
            
        Returns:
            清理的文件数量
        """
        days = retention_days or self._retention_days
        now = time.time()
        cutoff_time = now - (days * 86400)  # 转换为秒
        
        cleaned_count = 0
        
        # 遍历所有文件目录
        for item in self._storage_dir.iterdir():
            if not item.is_dir():
                continue
            
            file_id = item.name
            
            # 读取元数据
            metadata = await self.get(file_id)
            
            if metadata is None:
                # 没有元数据，可能是临时文件，跳过
                continue
            
            # 检查是否过期
            created_at = _iso_to_timestamp(metadata.created_at)
            
            if created_at < cutoff_time:
                success = await self.delete(file_id)
                if success:
                    cleaned_count += 1
                    logger.info(f"清理过期文件 | file_id={file_id} | age={days} days")
        
        if cleaned_count > 0:
            logger.info(f"过期文件清理完成 | cleaned={cleaned_count}")
        
        return cleaned_count
    
    async def check_storage_usage(self) -> Dict[str, Any]:
        """
        检查存储使用情况
        
        Returns:
            存储使用统计信息
        """
        total_size = 0
        file_count = 0
        oldest_file = None
        newest_file = None
        
        # 遍历所有文件
        for item in self._storage_dir.iterdir():
            if not item.is_dir():
                continue
            
            file_id = item.name
            metadata = await self.get(file_id)
            
            if metadata is None:
                continue
            
            total_size += metadata.size_bytes
            file_count += 1
            
            # 更新最旧/最新文件
            created_at = _iso_to_timestamp(metadata.created_at)
            
            if oldest_file is None or created_at < oldest_file[1]:
                oldest_file = (metadata.file_id, created_at)
            
            if newest_file is None or created_at > newest_file[1]:
                newest_file = (metadata.file_id, created_at)
        
        # 获取磁盘信息
        disk_usage = shutil.disk_usage(str(self._storage_dir))
        usage_percentage = disk_usage.used / disk_usage.total if disk_usage.total > 0 else 0
        
        return {
            "total_files": file_count,
            "total_size_bytes": total_size,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "max_size_gb": round(self._max_total_size_bytes / (1024 * 1024 * 1024), 2),
            "usage_percentage": round(usage_percentage * 100, 2),
            "oldest_file_id": oldest_file[0] if oldest_file else None,
            "newest_file_id": newest_file[0] if newest_file else None,
            "disk_total_gb": round(disk_usage.total / (1024 * 1024 * 1024), 2),
            "disk_used_gb": round(disk_usage.used / (1024 * 1024 * 1024), 2),
            "disk_free_gb": round(disk_usage.free / (1024 * 1024 * 1024), 2),
        }
    
    async def get_user_files(self, user_id: int) -> List[FileMetadata]:
        """
        获取用户的所有文件
        
        Args:
            user_id: 用户 ID
            
        Returns:
            文件元数据列表
        """
        user_files = []
        
        for item in self._storage_dir.iterdir():
            if not item.is_dir():
                continue
            
            file_id = item.name
            metadata = await self.get(file_id)
            
            if metadata and metadata.user_id == user_id:
                user_files.append(metadata)
        
        # 按创建时间倒序排列
        user_files.sort(key=lambda m: m.created_at, reverse=True)
        
        return user_files
    
    async def cleanup_by_storage_threshold(self) -> int:
        """
        当存储使用率超过阈值时，清理最旧的文件
        
        Returns:
            清理的文件数量
        """
        usage = await self.check_storage_usage()
        
        if usage["usage_percentage"] < STORAGE_THRESHOLD * 100:
            return 0
        
        cleaned_count = 0
        
        # 获取最旧的文件并逐个清理，直到低于阈值
        while True:
            usage = await self.check_storage_usage()
            
            if usage["usage_percentage"] < STORAGE_THRESHOLD * 100:
                break
            
            oldest_file_id = usage.get("oldest_file_id")
            
            if oldest_file_id is None:
                break
            
            success = await self.delete(oldest_file_id)
            
            if success:
                cleaned_count += 1
            else:
                # 无法删除，避免死循环
                break
        
        if cleaned_count > 0:
            logger.info(f"按存储阈值清理完成 | cleaned={cleaned_count}")
        
        return cleaned_count
    
    async def _check_storage_capacity(self, file_size: int) -> None:
        """
        检查是否有足够的存储空间
        
        Args:
            file_size: 文件大小（字节）
        
        Raises:
            StorageQuotaExceededError: 存储容量不足
        """
        usage = await self.check_storage_usage()
        
        if usage["total_size_bytes"] + file_size > self._max_total_size_bytes:
            # 尝试清理过期文件
            await self.cleanup_expired()
            
            # 再次检查
            usage = await self.check_storage_usage()
            
            if usage["total_size_bytes"] + file_size > self._max_total_size_bytes:
                # 尝试按阈值清理
                await self.cleanup_by_storage_threshold()
                
                # 最后一次检查
                usage = await self.check_storage_usage()
                
                if usage["total_size_bytes"] + file_size > self._max_total_size_bytes:
                    raise StorageQuotaExceededError(
                        f"存储容量不足，当前使用 {usage['total_size_mb']} MB，"
                        f"最大限制 {round(self._max_total_size_bytes / (1024 * 1024), 2)} MB"
                    )
    
    async def _save_metadata(self, file_id: str, metadata: FileMetadata) -> None:
        """保存元数据到文件"""
        metadata_path = self._storage_dir / file_id / "metadata.json"
        metadata_path.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            with open(metadata_path, 'w', encoding='utf-8') as f:
                json.dump(asdict(metadata), f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存元数据失败 | file_id={file_id} | error={e}")


def _timestamp_to_iso(timestamp: float) -> str:
    """将时间戳转换为 ISO 8601 格式"""
    from datetime import datetime, timezone
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()


def _iso_to_timestamp(iso_string: str) -> float:
    """将 ISO 8601 格式转换为时间戳"""
    from datetime import datetime
    # 处理可能的时区信息
    try:
        dt = datetime.fromisoformat(iso_string)
        if dt.tzinfo is None:
            from datetime import timezone
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except Exception:
        return 0.0


# 全局单例
file_storage = FileStorageManager()
