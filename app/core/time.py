"""
统一时间工具。

项目时间约定：

- `DateTime(timezone=True)` 的列使用 aware UTC，即 `datetime.now(timezone.utc)`。
- 无时区的 `DateTime` 列，以及需要与从数据库读回的 naive 时间做算术或比较的场景，
  统一使用 `utcnow_naive()`。

SQLite 的 `DATETIME` 读回时一律是 naive（即使列声明 `timezone=True`），因此对这些
读回值做 Python 层运算时必须保持 naive，否则会触发 naive/aware 比较的 `TypeError`。
"""

from datetime import datetime, timezone

__all__ = ["utcnow_naive"]


def utcnow_naive() -> datetime:
    """
    返回无时区的 UTC 当前时间。

    `datetime.utcnow()` 自 Python 3.12 起被弃用（返回 naive 对象容易与本地时间混淆）。
    本函数显式构造 UTC 时间再去掉 tzinfo，值语义与 `datetime.utcnow()` 完全一致。
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)
