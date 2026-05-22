"""
DynamicChunker - 动态分片策略

v4.8.0 新增：
- 根据上传速度动态调整分片大小 (1MB-50MB)
- 连续失败 3 次后降至最小分片
- 上传速度自适应：快则增、慢则缩
"""

import logging
from typing import List

logger = logging.getLogger(__name__)


class DynamicChunker:
    """
    动态分片策略管理器

    根据上传速度和失败率动态调整分片大小。
    """

    MIN_CHUNK_SIZE = 1 * 1024 * 1024    # 1MB
    MAX_CHUNK_SIZE = 50 * 1024 * 1024   # 50MB
    DEFAULT_CHUNK_SIZE = 5 * 1024 * 1024  # 5MB
    FAST_THRESHOLD = 10 * 1024 * 1024   # 10MB/s 视为快速
    SLOW_THRESHOLD = 2 * 1024 * 1024    # 2MB/s 视为慢速
    FAILURE_THRESHOLD = 3               # 连续失败次数阈值

    def __init__(self):
        self.current_chunk_size = self.DEFAULT_CHUNK_SIZE
        self.upload_speed_history: List[float] = []
        self.consecutive_failures = 0

    def get_chunk_size(self) -> int:
        """获取当前分片大小"""
        return self.current_chunk_size

    def adjust_chunk_size(self, upload_duration: float, chunk_bytes: int) -> int:
        """
        根据上传速度调整分片大小

        Args:
            upload_duration: 上传耗时（秒）
            chunk_bytes: 本次分片字节数

        Returns:
            新的分片大小
        """
        if upload_duration <= 0:
            return self.current_chunk_size

        speed = chunk_bytes / upload_duration
        self.upload_speed_history.append(speed)

        if speed > self.FAST_THRESHOLD:
            self.current_chunk_size = min(
                int(self.current_chunk_size * 1.5),
                self.MAX_CHUNK_SIZE,
            )
            logger.debug(
                f"快速上传 ({speed / 1024 / 1024:.1f}MB/s), "
                f"增大分片至 {self.current_chunk_size / 1024 / 1024:.1f}MB"
            )
        elif speed < self.SLOW_THRESHOLD:
            self.current_chunk_size = max(
                int(self.current_chunk_size * 0.5),
                self.MIN_CHUNK_SIZE,
            )
            logger.debug(
                f"慢速上传 ({speed / 1024 / 1024:.1f}MB/s), "
                f"缩小分片至 {self.current_chunk_size / 1024 / 1024:.1f}MB"
            )

        return self.current_chunk_size

    def on_upload_failure(self) -> int:
        """
        处理上传失败：连续失败达到阈值后降至最小分片

        Returns:
            当前分片大小
        """
        self.consecutive_failures += 1
        if self.consecutive_failures >= self.FAILURE_THRESHOLD:
            self.current_chunk_size = self.MIN_CHUNK_SIZE
            logger.warning(
                f"连续失败 {self.consecutive_failures} 次, "
                f"降至最小分片 {self.MIN_CHUNK_SIZE / 1024 / 1024:.1f}MB"
            )
        else:
            self.current_chunk_size = max(
                int(self.current_chunk_size * 0.5),
                self.MIN_CHUNK_SIZE,
            )
        return self.current_chunk_size

    def on_upload_success(self) -> None:
        """上传成功后重置失败计数"""
        self.consecutive_failures = 0

    def reset(self) -> None:
        """重置所有状态"""
        self.current_chunk_size = self.DEFAULT_CHUNK_SIZE
        self.upload_speed_history = []
        self.consecutive_failures = 0