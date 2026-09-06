"""图片生成资源指标的轻量记录器。"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass


@dataclass(frozen=True)
class ImageGenerationMetric:
    user_id: int
    generation_type: str
    profile: str | None
    cache_hit: bool
    total_duration_ms: int
    retry_count: int
    image_count: int
    output_bytes: int
    status: str
    failure_code: str | None = None


class ImageGenerationMetrics:
    def __init__(self) -> None:
        self._records: list[ImageGenerationMetric] = []

    def record(self, metric: ImageGenerationMetric) -> None:
        self._records.append(metric)

    @property
    def records(self) -> tuple[ImageGenerationMetric, ...]:
        return tuple(self._records)

    def summary(self) -> dict[str, int]:
        counts = Counter(metric.status for metric in self._records)
        return {
            "requests": len(self._records),
            "cache_hits": sum(metric.cache_hit for metric in self._records),
            "images": sum(metric.image_count for metric in self._records),
            "output_bytes": sum(metric.output_bytes for metric in self._records),
            "completed": counts["completed"],
            "failed": counts["failed"],
        }
