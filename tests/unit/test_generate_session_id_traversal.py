"""项目生成 session_id 会用于路径拼接，必须拒绝遍历字符。

`GenerateRequest.session_id` 原先没有任何格式约束，客户端可提交 `../../x`；
该值会写入 ProjectSession，删除会话时再被拼进 `shutil.rmtree` 的路径，
可越界删除任意目录。
"""

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from app.api.v1.ai_agent import orchestrate_endpoints as endpoints
from app.schema.codeRequest import GenerateRequest


def _request(session_id: str) -> GenerateRequest:
    return GenerateRequest(
        requirement="demo",
        session_id=session_id,
    )


@pytest.mark.parametrize(
    "session_id",
    ["../escape", "a/b", "a\\b", "..", "with space", "x" * 129],
)
def test_generate_request_rejects_path_like_session_id(session_id):
    with pytest.raises(ValidationError):
        _request(session_id)


@pytest.mark.parametrize("session_id", ["abc123", "abc_def-123", "A" * 128])
def test_generate_request_accepts_safe_session_id(session_id):
    assert _request(session_id).session_id == session_id


@pytest.mark.asyncio
async def test_delete_session_does_not_remove_outside_of_workspace(monkeypatch, tmp_path):
    """即使历史数据带有遍历字符，删除端点也不能越界删除。"""
    victim = tmp_path / "victim"
    victim.mkdir()
    (victim / "keep.txt").write_text("keep")

    projects = tmp_path / "projects"
    orchestrator = projects / "orchestrator"
    orchestrator.mkdir(parents=True)

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(endpoints, "_cancel_events", {})
    monkeypatch.setattr(
        endpoints, "_cancel_active_generation", AsyncMock(return_value=False)
    )
    monkeypatch.setattr(endpoints, "_cleanup_session_queues", AsyncMock())
    monkeypatch.setattr(
        endpoints,
        "get_session_manager",
        AsyncMock(return_value=SimpleNamespace(_lock=asyncio.Lock(), _active_sessions={})),
    )

    db = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(rowcount=1)),
        commit=AsyncMock(),
    )

    # 旧实现拼出 ./projects/orchestrator/../../victim，正好指向上面的目录。
    await endpoints.delete_session_endpoint(
        "../../victim", token={"sub": "1", "role": "user"}, db=db
    )

    assert victim.exists()
    assert (victim / "keep.txt").exists()
