"""分页参数必须显式限界。

`GET /api/v1/conversations`、`GET /api/v1/aicloud/history` 与
`GET /api/v1/aicloud/audit-logs` 原先把 `limit`/`offset` 声明为裸 `int`，
没有 `ge`/`le` 约束：负 limit 会生成非法 SQL 或返回空页，超大 limit
（如 10_000_000）可一次性物化整表，放大资源消耗。

这里直接检查 FastAPI 记录的查询参数约束，无需真实数据库。
"""

import pytest

from app.api.v1 import aicloud, auth


def _query_field(router, path: str, name: str):
    route = next(r for r in router.routes if getattr(r, "path", None) == path)
    for param in route.dependant.query_params:
        if param.name == name:
            return param.field_info
    raise AssertionError(f"{path} 缺少查询参数 {name}")


def _bounds(field) -> tuple:
    """FastAPI 把 ge/le 存在 field_info.metadata 的 Ge/Le 对象里。"""
    lower = upper = None
    for meta in field.metadata:
        lower = getattr(meta, "ge", lower)
        upper = getattr(meta, "le", upper)
    return lower, upper


@pytest.mark.parametrize(
    "router,path,name,ge,le",
    [
        (auth.router, "/conversations", "limit", 1, 100),
        (auth.router, "/conversations", "offset", 0, None),
        (aicloud.router, "/aicloud/history", "limit", 1, 100),
        (aicloud.router, "/aicloud/history", "offset", 0, None),
        (aicloud.router, "/aicloud/history", "days", 1, 365),
        (aicloud.router, "/aicloud/audit-logs", "limit", 1, 500),
        (aicloud.router, "/aicloud/history/search", "limit", 1, 100),
        (aicloud.router, "/aicloud/history/search", "days", 1, 365),
    ],
)
def test_pagination_declares_bounds(router, path, name, ge, le):
    """分页参数必须带上下界，否则越界值会直达查询。"""
    field = _query_field(router, path, name)
    lower, upper = _bounds(field)
    assert lower == ge, f"{path}?{name} 下界应为 {ge}，实际 {lower}"
    assert upper == le, f"{path}?{name} 上界应为 {le}，实际 {upper}"


def test_search_history_has_no_per_session_query():
    """`/history/search` 必须单次 JOIN 取数，不能按会话逐个查询。"""
    import inspect

    source = inspect.getsource(aicloud.search_history)
    assert "join(" in source
    assert "for session in sessions" not in source
