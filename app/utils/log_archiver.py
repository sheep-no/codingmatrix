"""
日志归档模块

功能：
- 按时间轮转日志文件
- 压缩旧日志
- 自动清理过期日志
- 定时执行归档任务
"""
import asyncio
import gzip
import logging
import os
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)


class LogArchiver:
    """
    日志归档器

    支持：
    - 按大小轮转（当日志文件超过阈值时）
    - 按时间轮转（每日/每周/每月）
    - 压缩归档
    - 自动清理
    """

    def __init__(
        self,
        log_dir: str = "logs",
        max_size_mb: float = 100,
        retention_days: int = 7,
        compression_enabled: bool = True,
        archive_format: str = "gz"
    ):
        """
        初始化日志归档器

        Args:
            log_dir: 日志目录
            max_size_mb: 单个日志文件最大大小（MB），超过则轮转
            retention_days: 日志保留天数
            compression_enabled: 是否压缩归档
            archive_format: 压缩格式 (gz/zip)
        """
        self.log_dir = Path(log_dir)
        self.max_size_bytes = int(max_size_mb * 1024 * 1024)
        self.retention_days = retention_days
        self.compression_enabled = compression_enabled
        self.archive_format = archive_format

    def get_log_files(self, pattern: str = "*.log") -> List[Path]:
        """获取日志目录下的所有日志文件"""
        if not self.log_dir.exists():
            return []
        return sorted(self.log_dir.glob(pattern), key=lambda p: p.stat().st_mtime)

    def should_rotate_by_size(self, file_path: Path) -> bool:
        """检查文件是否需要按大小轮转"""
        if not file_path.exists():
            return False
        return file_path.stat().st_size >= self.max_size_bytes

    def rotate_file(self, file_path: Path) -> Optional[Path]:
        """
        轮转日志文件

        Args:
            file_path: 日志文件路径

        Returns:
            轮转后的归档文件路径
        """
        if not file_path.exists():
            return None

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        archive_name = f"{file_path.stem}_{timestamp}.log"

        if self.compression_enabled:
            archive_name += f".{self.archive_format}"
            archived_path = self.log_dir / archive_name

            try:
                if self.archive_format == "gz":
                    with open(file_path, 'rb') as f_in:
                        with gzip.open(archived_path, 'wb') as f_out:
                            shutil.copyfileobj(f_in, f_out)
                else:
                    import zipfile
                    with zipfile.ZipFile(archived_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                        zf.write(file_path, arcname=file_path.name)

                file_path.unlink()
                logger.info(f"日志归档完成: {file_path.name} -> {archive_name}")
                return archived_path

            except Exception as e:
                logger.error(f"日志归档失败: {e}")
                if archived_path.exists():
                    archived_path.unlink()
                return None
        else:
            archive_path = self.log_dir / archive_name
            shutil.move(str(file_path), str(archive_path))
            logger.info(f"日志轮转完成: {file_path.name} -> {archive_name}")
            return archive_path

    def cleanup_old_logs(self, dry_run: bool = False) -> List[Path]:
        """
        清理过期日志

        Args:
            dry_run: 是否仅预览不删除

        Returns:
            被清理的文件列表
        """
        cleaned_files = []
        cutoff_date = datetime.now() - timedelta(days=self.retention_days)

        archive_pattern = f"*.log.{self.archive_format}" if self.compression_enabled else "*.log.*"
        for log_file in self.log_dir.glob(archive_pattern):
            try:
                mtime = datetime.fromtimestamp(log_file.stat().st_mtime)
                if mtime < cutoff_date:
                    if dry_run:
                        cleaned_files.append(log_file)
                    else:
                        log_file.unlink()
                        cleaned_files.append(log_file)
                        logger.info(f"清理过期日志: {log_file.name}")
            except Exception as e:
                logger.error(f"清理日志失败 {log_file.name}: {e}")

        return cleaned_files

    def archive_all(self) -> dict:
        """
        执行归档任务

        Returns:
            归档统计信息
        """
        stats = {
            "rotated": [],
            "archived": [],
            "cleaned": [],
            "errors": []
        }

        for log_file in self.get_log_files("*.log"):
            try:
                if self.should_rotate_by_size(log_file):
                    result = self.rotate_file(log_file)
                    if result:
                        stats["rotated"].append(str(result))
            except Exception as e:
                logger.error(f"轮转日志失败 {log_file.name}: {e}")
                stats["errors"].append(str(log_file.name))

        for log_file in self.get_log_files("*.log.*"):
            if log_file.suffix == f".{self.archive_format}":
                continue
            try:
                result = self.rotate_file(log_file)
                if result:
                    stats["archived"].append(str(result))
            except Exception as e:
                logger.error(f"归档日志失败 {log_file.name}: {e}")
                stats["errors"].append(str(log_file.name))

        cleaned = self.cleanup_old_logs()
        stats["cleaned"] = [str(f) for f in cleaned]

        return stats

    def get_archive_stats(self) -> dict:
        """获取归档统计信息"""
        total_size = 0
        file_count = 0
        oldest_file = None
        newest_file = None

        archive_pattern = "*.log.*" if not self.compression_enabled else f"*.log.{self.archive_format}"

        for log_file in self.log_dir.glob(archive_pattern):
            total_size += log_file.stat().st_size
            file_count += 1
            mtime = log_file.stat().st_mtime

            if oldest_file is None or mtime < oldest_file[1]:
                oldest_file = (log_file.name, mtime)

            if newest_file is None or mtime > newest_file[1]:
                newest_file = (log_file.name, mtime)

        return {
            "total_size_bytes": total_size,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "file_count": file_count,
            "oldest_file": oldest_file[0] if oldest_file else None,
            "newest_file": newest_file[0] if newest_file else None,
            "retention_days": self.retention_days
        }


_log_archiver: Optional[LogArchiver] = None


def get_log_archiver() -> LogArchiver:
    """获取日志归档器单例"""
    global _log_archiver
    if _log_archiver is None:
        from app.core.config import settings

        log_dir = getattr(settings, 'LOG_DIR', 'logs')
        log_level = getattr(settings, 'LOG_LEVEL', 'INFO')

        if log_level == 'DEBUG':
            retention_days = 3
        elif log_level == 'WARNING':
            retention_days = 14
        elif log_level == 'ERROR':
            retention_days = 30
        else:
            retention_days = 7

        _log_archiver = LogArchiver(
            log_dir=log_dir,
            retention_days=retention_days,
            compression_enabled=True
        )

    return _log_archiver


async def run_archive_task():
    """定时归档任务"""
    try:
        archiver = get_log_archiver()
        stats = archiver.archive_all()
        logger.info(f"日志归档任务完成 | rotated={len(stats['rotated'])} cleaned={len(stats['cleaned'])}")
        return stats
    except Exception as e:
        logger.error(f"日志归档任务失败: {e}")
        return {"error": str(e)}


class LogRotationHandler(logging.Handler):
    """
    日志轮转处理器

    继承 logging.Handler，支持日志写入时自动轮转
    """

    def __init__(self, log_file: str, max_bytes: int = 100 * 1024 * 1024, backup_count: int = 5):
        super().__init__()
        self.log_file = Path(log_file)
        self.max_bytes = max_bytes
        self.backup_count = backup_count

        self.log_file.parent.mkdir(parents=True, exist_ok=True)

    def emit(self, record):
        """发送日志记录"""
        try:
            if self.log_file.exists() and self.log_file.stat().st_size >= self.max_bytes:
                self._do_rotate()

            msg = self.format(record) + "\n"
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(msg)
        except Exception:
            self.handleError(record)

    def _do_rotate(self):
        """执行轮转"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        for i in range(self.backup_count - 1, 0, -1):
            old_file = self.log_file.with_suffix(f".{i}")
            new_file = self.log_file.with_suffix(f".{i + 1}")
            if old_file.exists():
                if new_file.exists():
                    new_file.unlink()
                shutil.move(str(old_file), str(new_file))

        archive_file = self.log_file.with_suffix(".1")
        if archive_file.exists():
            archive_file.unlink()
        shutil.move(str(self.log_file), str(archive_file))
