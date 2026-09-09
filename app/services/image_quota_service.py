"""用户级图片生成额度控制。"""

from __future__ import annotations

from collections import defaultdict
from datetime import date


class ImageQuotaService:
    def __init__(self, daily_limit: int = 20) -> None:
        if daily_limit < 1:
            raise ValueError("daily_limit must be positive")
        self.daily_limit = daily_limit
        self._usage: dict[tuple[int, date], int] = defaultdict(int)

    def remaining(self, user_id: int, *, on_date: date | None = None) -> int:
        current_date = on_date or date.today()
        return max(0, self.daily_limit - self._usage[(user_id, current_date)])

    def consume(self, user_id: int, amount: int = 1, *, on_date: date | None = None) -> int:
        if amount < 1:
            raise ValueError("amount must be positive")
        current_date = on_date or date.today()
        key = (user_id, current_date)
        if self._usage[key] + amount > self.daily_limit:
            raise RuntimeError("daily image generation quota exceeded")
        self._usage[key] += amount
        return self.remaining(user_id, on_date=current_date)
