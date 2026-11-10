"""第八轮扫描新增约束的回归用例。

`ConversationHistoryRequest.limit`、已保存项目列表、会话列表与并发限制
变更历史原先缺少上下界，负值或超大值会直达 SQL/内存切片。
"""

import asyncio

import pytest
from pydantic import ValidationError

from app.api.v1.ai_agent import generate_endpoints, orchestrate_endpoints
from app.schema.history import ConversationHistoryRequest
from app.utils.dynamic_concurrent import ConcurrentLimitManager


def _query_field(router, path: str, name: str):
    route = next(r for r in router.routes if getattr(r, "path", None) == path)
    for param in route.dependant.query_params:
        if param.name == name:
            return param.field_info
    raise AssertionError(f"{path} 缺少查询参数 {name}")


def _bounds(field) -> tuple:
    lower = upper = None
    for meta in field.metadata:
        lower = getattr(meta, "ge", lower)
        upper = getattr(meta, "le", upper)
    return lower, upper


@pytest.mark.parametrize("limit", [0, -1, 101])
def test_conversation_history_rejects_invalid_limit(limit):
    with pytest.raises(ValidationError):
        ConversationHistoryRequest(conversation_id=1, limit=limit)


def test_conversation_history_accepts_boundary_limit():
    assert ConversationHistoryRequest(conversation_id=1, limit=1).limit == 1
    assert ConversationHistoryRequest(conversation_id=1, limit=100).limit == 100


@pytest.mark.parametrize(
    "router,path,name,ge,le",
    [
        (generate_endpoints.router, "/saved", "offset", 0, None),
        (generate_endpoints.router, "/saved", "limit", 1, 100),
        (orchestrate_endpoints.router, "/sessions", "limit", 1, 50),
        (orchestrate_endpoints.router, "/concurrent-limits/history", "limit", 1, 500),
    ],
)
def test_pagination_declares_bounds(router, path, name, ge, le):
    lower, upper = _bounds(_query_field(router, path, name))
    assert lower == ge, f"{path}?{name} 下界应为 {ge}，实际 {lower}"
    assert upper == le, f"{path}?{name} 上界应为 {le}，实际 {upper}"


def test_change_log_is_capped_and_read_clamped():
    manager = ConcurrentLimitManager()
    manager._change_log.clear()

    try:
        for index in range(manager.MAX_CHANGE_LOG + 20):
            asyncio.run(manager.update_limit("free", index + 1, "admin"))

        assert len(manager._change_log) == manager.MAX_CHANGE_LOG
        assert manager.get_change_history(10_000)[0].new_limit == 21
        assert manager.get_change_history(0) == []
        assert manager.get_change_history(-5) == []
    finally:
        manager._limits = dict(manager.BASE_LIMITS)
        manager._change_log.clear()
