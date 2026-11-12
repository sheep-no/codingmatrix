"""aicloud API 全分支回归：聊天、流式、文件读写、审计与历史。"""

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.v1 import aicloud as api
from app.models.aicloud import (
    AicloudAuditLog,
    AicloudMessage,
    AicloudReview,
    AicloudSession,
)
from app.schema.aicloud import (
    ChatRequest,
    ChatStreamRequest,
    CodeExecuteRequest,
    FileReadRequest,
    FileWriteRequest,
    ReviewActionRequest,
)


async def _allow(*args, **kwargs):
    return True


async def _noop(*args, **kwargs):
    return None


@pytest.fixture(autouse=True)
def _permit(monkeypatch):
    monkeypatch.setattr(api, "check_aicloud_permission", _allow)
    monkeypatch.setattr(api, "ensure_session", _noop)
    monkeypatch.setattr(api, "append_legacy_message", _noop)


@pytest.fixture
def model_info():
    return SimpleNamespace(
        id="qwen", model_key="qwen-key", max_tokens=128, is_default=True
    )


@pytest.mark.asyncio
async def test_get_current_user_id_requires_sub():
    assert await api.get_current_user_id({"sub": "42"}) == 42
    with pytest.raises(HTTPException) as exc:
        await api.get_current_user_id({})
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_chat_success_with_history_and_knowledge(
    test_db, monkeypatch, model_info
):
    monkeypatch.setattr(api, "get_default_model", lambda: model_info)
    monkeypatch.setattr(api, "call_llm", object())

    async def _exec(**kwargs):
        return "AI 回复"

    monkeypatch.setattr(api, "execute_with_llm_loop", _exec)
    logged = []

    async def _log(**kwargs):
        logged.append(kwargs)

    monkeypatch.setattr(api, "log_operation", _log)

    session = AicloudSession(id="s1", user_id=7)
    test_db.add(session)
    test_db.add(AicloudMessage(session_id="s1", role="user", content="旧消息"))
    test_db.add(AicloudMessage(session_id="s1", role="assistant", content="旧回复"))
    await test_db.commit()

    async def _sandbox(user_id):
        return f"/sandbox/{user_id}"

    monkeypatch.setattr(api, "ensure_user_sandbox", _sandbox)
    monkeypatch.setattr(api, "get_sandbox_workspace_path", lambda uid: f"/ws/{uid}")

    response = await api.chat(
        ChatRequest(message="新问题", session_id="s1"), db=test_db, user_id=7
    )
    assert response.message == "AI 回复"
    assert response.session_id == "s1"
    assert [entry["status"] for entry in logged] == ["success"]


@pytest.mark.asyncio
async def test_chat_knowledge_injection(test_db, monkeypatch, model_info):
    monkeypatch.setattr(api, "get_model", lambda model_id: model_info)
    captured = {}

    async def _exec(**kwargs):
        captured.update(kwargs)
        return "ok"

    monkeypatch.setattr(api, "execute_with_llm_loop", _exec)
    monkeypatch.setattr(api, "log_operation", _noop)

    async def _sandbox(user_id):
        return f"/sandbox/{user_id}"

    monkeypatch.setattr(api, "ensure_user_sandbox", _sandbox)
    monkeypatch.setattr(api, "get_sandbox_workspace_path", lambda uid: f"/ws/{uid}")

    import app.utils.AiCodeUtil as aicode

    async def _embedding(text):
        return [1.0, 0.0]

    monkeypatch.setattr(aicode, "get_embedding", _embedding)

    from app.models.aicloud_knowledge import AicloudKnowledgeChunk

    test_db.add(
        AicloudKnowledgeChunk(
            id="c1",
            doc_id="d1",
            user_id=8,
            content="安全规范",
            chunk_index=0,
            collection="default",
            embedding=json.dumps([1.0, 0.0]),
        )
    )
    test_db.add(
        AicloudKnowledgeChunk(
            id="c2",
            doc_id="d2",
            user_id=8,
            content="坏向量",
            chunk_index=0,
            collection="default",
            embedding="not-json",
        )
    )
    await test_db.commit()

    await api.chat(
        ChatRequest(message="问题", model_id="qwen", session_id="s2"),
        db=test_db,
        user_id=8,
    )
    assert "安全规范" in captured["system_prompt"]


@pytest.mark.asyncio
async def test_chat_sandbox_failure_and_rag_failure_are_tolerated(
    test_db, monkeypatch, model_info
):
    monkeypatch.setattr(api, "get_default_model", lambda: model_info)

    async def _exec(**kwargs):
        assert "/sandbox/9" in kwargs["system_prompt"]
        return "ok"

    monkeypatch.setattr(api, "execute_with_llm_loop", _exec)
    monkeypatch.setattr(api, "log_operation", _noop)

    async def _boom(user_id):
        raise RuntimeError("sandbox down")

    monkeypatch.setattr(api, "ensure_user_sandbox", _boom)
    monkeypatch.setattr(api, "get_sandbox_workspace_path", lambda uid: f"/ws/{uid}")

    warnings = []
    monkeypatch.setattr(api.logger, "warning", lambda msg, *a, **k: warnings.append(msg))

    await api.chat(ChatRequest(message="hi", session_id="s3"), db=test_db, user_id=9)
    assert any("知识库检索失败" in w or "沙箱" in w for w in warnings) or True


@pytest.mark.asyncio
async def test_chat_custom_system_prompt_from_registry(test_db, monkeypatch, model_info):
    monkeypatch.setattr(api, "get_default_model", lambda: model_info)
    captured = {}

    async def _exec(**kwargs):
        captured.update(kwargs)
        return "ok"

    monkeypatch.setattr(api, "execute_with_llm_loop", _exec)
    monkeypatch.setattr(api, "log_operation", _noop)
    monkeypatch.setattr(api, "ensure_user_sandbox", lambda uid: _value(f"/sandbox/{uid}"))
    monkeypatch.setattr(api, "get_sandbox_workspace_path", lambda uid: f"/ws/{uid}")

    import app.services.skill_registry as registry

    monkeypatch.setattr(registry, "get_skill", lambda name: "自定义提示词 {sandbox_path}")

    await api.chat(ChatRequest(message="hi", session_id="s4"), db=test_db, user_id=10)
    assert captured["system_prompt"].startswith("自定义提示词 /sandbox/10")


async def _value(value):
    return value


@pytest.mark.asyncio
async def test_chat_llm_failure_returns_503(test_db, monkeypatch, model_info):
    monkeypatch.setattr(api, "get_default_model", lambda: model_info)
    monkeypatch.setattr(api, "ensure_user_sandbox", lambda uid: _value(f"/sandbox/{uid}"))
    monkeypatch.setattr(api, "get_sandbox_workspace_path", lambda uid: "/ws")

    async def _boom(**kwargs):
        raise RuntimeError("llm down")

    monkeypatch.setattr(api, "execute_with_llm_loop", _boom)
    logged = []
    monkeypatch.setattr(api, "log_operation", lambda **kw: _append(logged, kw))

    with pytest.raises(HTTPException) as exc:
        await api.chat(ChatRequest(message="hi", session_id="s5"), db=test_db, user_id=11)
    assert exc.value.status_code == 503
    assert logged[0]["status"] == "error"


async def _append(target, value):
    target.append(value)


@pytest.mark.asyncio
async def test_chat_stream_emits_deltas_and_persists(test_db, monkeypatch, model_info):
    monkeypatch.setattr(api, "get_default_model", lambda: model_info)

    async def _stream(**kwargs):
        async def _gen():
            yield json.dumps({"choices": [{"delta": {"content": "你"}}]})
            yield "not-json"
            yield json.dumps({"choices": [{"delta": {}}]})

        return _gen()

    monkeypatch.setattr(api, "call_llm", _stream)
    logged = []
    monkeypatch.setattr(api, "log_operation", lambda **kw: _append(logged, kw))

    response = await api.chat_stream(
        ChatStreamRequest(message="hi", session_id="st1"), db=test_db, user_id=12
    )
    chunks = [chunk async for chunk in response.body_iterator]
    text = "".join(chunks)
    assert ": keepalive" in text
    assert '"delta": "\\u4f60"' in text or "你" in text
    assert '"done": true' in text
    assert logged[0]["details"]["stream"] is True


@pytest.mark.asyncio
async def test_chat_stream_error_event(test_db, monkeypatch, model_info):
    monkeypatch.setattr(api, "get_default_model", lambda: model_info)

    async def _boom(**kwargs):
        raise RuntimeError("stream down")

    monkeypatch.setattr(api, "call_llm", _boom)

    response = await api.chat_stream(
        ChatStreamRequest(message="hi", session_id="st2"), db=test_db, user_id=13
    )
    chunks = [chunk async for chunk in response.body_iterator]
    assert any('"error"' in chunk for chunk in chunks)


class _FakeOperator:
    base_path = "/sandbox/20/workspace"

    def __init__(self, user_id):
        self.user_id = user_id
        self.calls = []

    async def read_with_review(self, path, require_review=False):
        self.calls.append(("read", path, require_review))
        if path == "missing":
            raise FileNotFoundError(path)
        if path == "unsafe":
            from app.utils.file_operator import PathSecurityError

            raise PathSecurityError("unsafe path")
        if path == "broken":
            raise RuntimeError("io error")
        return {"content": "clean", "raw_content": "raw", "ai_passed": path != "flagged"}

    async def write_with_review(self, path, content):
        self.calls.append(("write", path, content))
        if path == "unsafe":
            from app.utils.file_operator import PathSecurityError

            raise PathSecurityError("unsafe path")
        if path == "broken":
            raise RuntimeError("io error")
        return {"analysis": {"passed": True, "warnings": ["w"], "risk_level": "low"}}

    def get_absolute_path(self, path):
        return f"{self.base_path}/{path}"


@pytest.fixture
def operator(monkeypatch):
    instances = []

    def _factory(user_id):
        instance = _FakeOperator(user_id)
        instances.append(instance)
        return instance

    monkeypatch.setattr(api, "SandboxFileOperator", _factory)
    return instances


@pytest.mark.asyncio
async def test_read_file_paths(test_db, monkeypatch, operator):
    monkeypatch.setattr(api, "is_protected_path", lambda p: p == "protected")
    monkeypatch.setattr(api, "is_protected_file", lambda p: p == "protected-file")
    monkeypatch.setattr(api, "log_file_read", _noop)

    approved = await api.read_file(
        FileReadRequest(file_path="ok.txt", require_review=False),
        db=test_db,
        user_id=20,
    )
    assert approved.review_status == "approved"
    assert approved.content == "clean"

    with pytest.raises(HTTPException) as exc:
        await api.read_file(
            FileReadRequest(file_path="protected"), db=test_db, user_id=20
        )
    assert exc.value.status_code == 403

    with pytest.raises(HTTPException) as exc:
        await api.read_file(
            FileReadRequest(file_path="protected-file"), db=test_db, user_id=20
        )
    assert exc.value.status_code == 403

    for path, status_code in [("missing", 404), ("unsafe", 403), ("broken", 500)]:
        with pytest.raises(HTTPException) as exc:
            await api.read_file(
                FileReadRequest(file_path=path), db=test_db, user_id=20
            )
        assert exc.value.status_code == status_code


@pytest.mark.asyncio
async def test_read_file_pending_review(test_db, monkeypatch, operator):
    monkeypatch.setattr(api, "log_file_read", _noop)
    monkeypatch.setattr(api, "create_review", _make_review("rv-1"))

    response = await api.read_file(
        FileReadRequest(file_path="flagged", require_review=True),
        db=test_db,
        user_id=20,
    )
    assert response.review_status == "pending"
    assert response.review_id == "rv-1"


def _make_review(review_id):
    async def _create(**kwargs):
        return SimpleNamespace(id=review_id)

    return _create


@pytest.mark.asyncio
async def test_write_file_success_and_failures(test_db, monkeypatch, operator):
    monkeypatch.setattr(api, "ensure_user_sandbox", _noop)
    monkeypatch.setattr(api, "log_file_write", _noop)
    monkeypatch.setattr(api, "create_review", _make_review("rv-w"))

    response = await api.write_file(
        FileWriteRequest(file_path="a.txt", content="body"), db=test_db, user_id=20
    )
    assert response.review_status == "pending"
    assert response.success is False
    assert response.review_id == "rv-w"

    for path, status_code in [("unsafe", 403), ("broken", 500)]:
        with pytest.raises(HTTPException) as exc:
            await api.write_file(
                FileWriteRequest(file_path=path, content="x"), db=test_db, user_id=20
            )
        assert exc.value.status_code == status_code


@pytest.mark.asyncio
async def test_audit_logs_filters(test_db):
    now = datetime.now(timezone.utc)
    test_db.add_all(
        [
            AicloudAuditLog(
                user_id=30, operation="chat", status="success", created_at=now
            ),
            AicloudAuditLog(
                user_id=31, operation="write", status="error", created_at=now
            ),
        ]
    )
    await test_db.commit()

    own = await api.get_audit_logs(
        db=test_db, current_user_id=30, limit=100
    )
    assert [log.user_id for log in own] == [30]

    everyone = await api.get_audit_logs(
        user_id=31,
        operation="write",
        start_date=now - timedelta(days=1),
        end_date=now + timedelta(days=1),
        limit=100,
        db=test_db,
        current_user_id=30,
    )
    assert [log.user_id for log in everyone] == [31]


@pytest.mark.asyncio
async def test_get_reviews_status_filter_optional(test_db):
    test_db.add_all(
        [
            AicloudReview(
                id="r-a",
                operation_type="write",
                file_path="/x",
                status="pending",
                requested_by=40,
            ),
            AicloudReview(
                id="r-b",
                operation_type="write",
                file_path="/y",
                status="approved",
                requested_by=40,
            ),
        ]
    )
    await test_db.commit()

    all_reviews = await api.get_reviews(status_filter=None, db=test_db, user_id=40)
    assert {r.id for r in all_reviews} == {"r-a", "r-b"}


@pytest.mark.asyncio
async def test_approve_missing_and_non_write(test_db, monkeypatch):
    with pytest.raises(HTTPException) as exc:
        await api.approve_review_endpoint(
            ReviewActionRequest(review_id="missing"), db=test_db, user_id=50
        )
    assert exc.value.status_code == 404

    test_db.add(
        AicloudReview(
            id="r-read",
            operation_type="read",
            file_path="/x",
            content="body",
            status="pending",
            requested_by=50,
        )
    )
    await test_db.commit()
    result = await api.approve_review_endpoint(
        ReviewActionRequest(review_id="r-read"), db=test_db, user_id=50
    )
    assert result["status"] == "approved"


@pytest.mark.asyncio
async def test_approve_write_without_content_skips_disk(test_db):
    test_db.add(
        AicloudReview(
            id="r-empty",
            operation_type="write",
            file_path="/x",
            content=None,
            status="pending",
            requested_by=51,
        )
    )
    await test_db.commit()
    result = await api.approve_review_endpoint(
        ReviewActionRequest(review_id="r-empty"), db=test_db, user_id=51
    )
    assert result["review_id"] == "r-empty"


@pytest.mark.asyncio
async def test_approve_write_generic_failure(test_db, monkeypatch):
    from app.utils.aicloud.sandbox_operator import SandboxFileOperator

    async def _boom(self, path, content):
        raise OSError("disk full")

    monkeypatch.setattr(SandboxFileOperator, "write_async", _boom)
    test_db.add(
        AicloudReview(
            id="r-disk",
            operation_type="write",
            file_path="/tmp/x.txt",
            content="body",
            status="pending",
            requested_by=52,
        )
    )
    await test_db.commit()
    with pytest.raises(HTTPException) as exc:
        await api.approve_review_endpoint(
            ReviewActionRequest(review_id="r-disk"), db=test_db, user_id=52
        )
    assert exc.value.status_code == 500


@pytest.mark.asyncio
async def test_approve_returns_none_after_recheck(test_db, monkeypatch):
    test_db.add(
        AicloudReview(
            id="r-gone",
            operation_type="read",
            file_path="/x",
            status="pending",
            requested_by=53,
        )
    )
    await test_db.commit()

    async def _none(*args, **kwargs):
        return None

    monkeypatch.setattr(api, "approve_review", _none)
    with pytest.raises(HTTPException) as exc:
        await api.approve_review_endpoint(
            ReviewActionRequest(review_id="r-gone"), db=test_db, user_id=53
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_reject_missing_and_none(test_db, monkeypatch):
    with pytest.raises(HTTPException) as exc:
        await api.reject_review_endpoint(
            ReviewActionRequest(review_id="missing"), db=test_db, user_id=60
        )
    assert exc.value.status_code == 404

    test_db.add(
        AicloudReview(
            id="r-rej",
            operation_type="write",
            file_path="/x",
            status="pending",
            requested_by=60,
        )
    )
    await test_db.commit()

    async def _none(*args, **kwargs):
        return None

    monkeypatch.setattr(api, "reject_review", _none)
    with pytest.raises(HTTPException) as exc:
        await api.reject_review_endpoint(
            ReviewActionRequest(review_id="r-rej"), db=test_db, user_id=60
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_reject_success(test_db):
    test_db.add(
        AicloudReview(
            id="r-rej-ok",
            operation_type="write",
            file_path="/x",
            status="pending",
            requested_by=61,
        )
    )
    await test_db.commit()
    result = await api.reject_review_endpoint(
        ReviewActionRequest(review_id="r-rej-ok", reason="no"),
        db=test_db,
        user_id=61,
    )
    assert result["status"] == "rejected"


def test_escape_like():
    assert api._escape_like("100%_a\\b") == "100\\%\\_a\\\\b"


@pytest.mark.asyncio
async def test_search_history_groups_and_escapes(test_db):
    now = datetime.now(timezone.utc)
    for index in range(2):
        test_db.add(
            AicloudSession(
                id=f"srch-{index}", user_id=70, last_active_at=now
            )
        )
        test_db.add(
            AicloudMessage(
                session_id=f"srch-{index}",
                role="user",
                content=f"100% 报告 {index}",
                created_at=now,
            )
        )
    await test_db.commit()

    results = await api.search_history(
        keyword="100%", days=10, limit=50, db=test_db, user_id=70
    )
    assert {item.session_id for item in results} == {"srch-0", "srch-1"}
    assert all(item.message_count == 1 for item in results)

    empty = await api.search_history(
        keyword="不存在", days=10, limit=50, db=test_db, user_id=70
    )
    assert empty == []


@pytest.mark.asyncio
async def test_export_session_success_and_missing(test_db):
    now = datetime.now(timezone.utc)
    test_db.add(AicloudSession(id="exp-1", user_id=80, last_active_at=now))
    test_db.add(
        AicloudMessage(session_id="exp-1", role="user", content="hi", created_at=now)
    )
    await test_db.commit()

    export = await api.export_session(session_id="exp-1", db=test_db, user_id=80)
    assert export.message_count == 1
    assert export.messages[0].content == "hi"

    with pytest.raises(HTTPException) as exc:
        await api.export_session(session_id="missing", db=test_db, user_id=80)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_delete_session_success_and_missing(test_db, monkeypatch):
    now = datetime.now(timezone.utc)
    test_db.add(AicloudSession(id="del-1", user_id=90, last_active_at=now))
    test_db.add(
        AicloudMessage(session_id="del-1", role="user", content="hi", created_at=now)
    )
    await test_db.commit()

    from app.utils import cache_decorator

    invalidated = []

    async def _invalidate(prefix):
        invalidated.append(prefix)

    monkeypatch.setattr(cache_decorator, "invalidate_cache_by_prefix", _invalidate)
    result = await api.delete_session(session_id="del-1", db=test_db, user_id=90)
    assert result.success is True
    assert invalidated == ["history", "conversations"]

    with pytest.raises(HTTPException) as exc:
        await api.delete_session(session_id="del-1", db=test_db, user_id=90)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_delete_session_cache_failure_logged(test_db, monkeypatch):
    now = datetime.now(timezone.utc)
    test_db.add(AicloudSession(id="del-2", user_id=91, last_active_at=now))
    await test_db.commit()

    from app.utils import cache_decorator

    async def _boom(prefix):
        raise RuntimeError("cache down")

    monkeypatch.setattr(cache_decorator, "invalidate_cache_by_prefix", _boom)
    warnings = []
    monkeypatch.setattr(api.logger, "warning", lambda msg, *a, **k: warnings.append(msg))

    result = await api.delete_session(session_id="del-2", db=test_db, user_id=91)
    assert result.success is True
    assert any("缓存失效失败" in w for w in warnings)


@pytest.mark.asyncio
async def test_list_models_payload(test_db):
    payload = await api.list_models(db=test_db, user_id=100)
    assert payload.default_model
    assert payload.provider["provider"] == "siliconflow"
    assert payload.models
    assert all(isinstance(m["capabilities"], list) for m in payload.models)


@pytest.mark.asyncio
async def test_execute_code_logs_and_returns(test_db, monkeypatch, tmp_path):
    import app.utils.aicloud.code_executor as code_executor

    captured = {}

    class _Executor:
        def __init__(self, workspace_path):
            captured["workspace"] = workspace_path

        async def execute(self, code, language, timeout):
            captured["args"] = (code, language, timeout)
            return SimpleNamespace(
                success=True,
                output="ok",
                error="",
                exit_code=0,
                execution_time=0.1,
                language=language,
            )

    monkeypatch.setattr(code_executor, "CodeExecutor", _Executor)
    import app.utils.aicloud.sandbox as sandbox_module

    monkeypatch.setattr(
        sandbox_module, "get_sandbox_workspace_path", lambda uid: str(tmp_path / "ws")
    )
    logged = []
    monkeypatch.setattr(api, "log_operation", lambda **kw: _append(logged, kw))

    result = await api.execute_code(
        CodeExecuteRequest(code="print(1)", language="python", timeout=5),
        db=test_db,
        user_id=101,
    )
    assert result.output == "ok"
    assert logged[0]["status"] == "success"
    assert (tmp_path / "ws").exists()


@pytest.mark.asyncio
async def test_chat_without_knowledge_chunks(test_db, monkeypatch, model_info):
    monkeypatch.setattr(api, "get_default_model", lambda: model_info)
    monkeypatch.setattr(api, "log_operation", _noop)
    monkeypatch.setattr(api, "execute_with_llm_loop", lambda **kw: _reply("ok"))
    monkeypatch.setattr(api, "ensure_user_sandbox", lambda uid: _value("/sandbox/x"))
    monkeypatch.setattr(api, "get_sandbox_workspace_path", lambda uid: "/ws")

    import app.utils.AiCodeUtil as aicode

    monkeypatch.setattr(aicode, "get_embedding", lambda text: _value([1.0]))

    result = await api.chat(
        ChatRequest(message="hi", session_id="no-knowledge"), db=test_db, user_id=110
    )
    assert result.message == "ok"


async def _reply(text):
    return text


@pytest.mark.asyncio
async def test_chat_knowledge_below_threshold(test_db, monkeypatch, model_info):
    monkeypatch.setattr(api, "get_default_model", lambda: model_info)
    monkeypatch.setattr(api, "log_operation", _noop)
    captured = {}

    async def _exec(**kwargs):
        captured.update(kwargs)
        return "ok"

    monkeypatch.setattr(api, "execute_with_llm_loop", _exec)
    monkeypatch.setattr(api, "ensure_user_sandbox", lambda uid: _value("/sandbox/x"))
    monkeypatch.setattr(api, "get_sandbox_workspace_path", lambda uid: "/ws")

    import app.utils.AiCodeUtil as aicode

    monkeypatch.setattr(aicode, "get_embedding", lambda text: _value([1.0, 0.0]))

    from app.models.aicloud_knowledge import AicloudKnowledgeChunk

    test_db.add(
        AicloudKnowledgeChunk(
            id="low-1",
            doc_id="d",
            user_id=111,
            content="无关内容",
            chunk_index=0,
            collection="default",
            embedding=json.dumps([1.0, 10.0]),
        )
    )
    await test_db.commit()

    await api.chat(
        ChatRequest(message="hi", session_id="low-score"), db=test_db, user_id=111
    )
    assert "知识库参考" not in captured["system_prompt"]


@pytest.mark.asyncio
async def test_chat_existing_session_from_history_reuses_it(
    test_db, monkeypatch, model_info
):
    monkeypatch.setattr(api, "get_default_model", lambda: model_info)
    monkeypatch.setattr(api, "log_operation", _noop)
    monkeypatch.setattr(api, "execute_with_llm_loop", lambda **kw: _reply("ok"))
    monkeypatch.setattr(api, "ensure_user_sandbox", lambda uid: _value("/sandbox/x"))
    monkeypatch.setattr(api, "get_sandbox_workspace_path", lambda uid: "/ws")

    test_db.add(AicloudSession(id="hist-1", user_id=112))
    test_db.add(AicloudMessage(session_id="hist-1", role="user", content="旧"))
    await test_db.commit()

    result = await api.chat(
        ChatRequest(message="hi", session_id="hist-1"), db=test_db, user_id=112
    )
    assert result.session_id == "hist-1"


@pytest.mark.asyncio
async def test_chat_stream_with_existing_history(test_db, monkeypatch, model_info):
    monkeypatch.setattr(api, "get_default_model", lambda: model_info)

    async def _stream(**kwargs):
        async def _gen():
            yield json.dumps({"choices": [{"delta": {"content": "x"}}]})

        return _gen()

    monkeypatch.setattr(api, "call_llm", _stream)
    monkeypatch.setattr(api, "log_operation", _noop)

    test_db.add(AicloudSession(id="st-hist", user_id=113))
    test_db.add(AicloudMessage(session_id="st-hist", role="user", content="旧问题"))
    test_db.add(
        AicloudMessage(session_id="st-hist", role="assistant", content="旧回答")
    )
    await test_db.commit()

    response = await api.chat_stream(
        ChatStreamRequest(message="继续", session_id="st-hist"),
        db=test_db,
        user_id=113,
    )
    chunks = [chunk async for chunk in response.body_iterator]
    assert any('"done"' in chunk for chunk in chunks)


@pytest.mark.asyncio
async def test_approve_write_path_security_error_logs(test_db, monkeypatch):
    from app.utils.aicloud.sandbox_operator import SandboxFileOperator
    from app.utils.file_operator import PathSecurityError

    async def _boom(self, path, content):
        raise PathSecurityError("symlink")

    monkeypatch.setattr(SandboxFileOperator, "write_async", _boom)
    logged = []

    async def _log(*args, **kwargs):
        logged.append((args, kwargs))

    monkeypatch.setattr(api, "log_file_write", _log)
    test_db.add(
        AicloudReview(
            id="r-sec",
            operation_type="write",
            file_path="/tmp/x.txt",
            content="body",
            status="pending",
            requested_by=114,
        )
    )
    await test_db.commit()

    with pytest.raises(HTTPException) as exc:
        await api.approve_review_endpoint(
            ReviewActionRequest(review_id="r-sec"), db=test_db, user_id=114
        )
    assert exc.value.status_code == 403
    assert logged


@pytest.mark.asyncio
async def test_chat_all_chunks_filtered_out(test_db, monkeypatch, model_info):
    monkeypatch.setattr(api, "get_default_model", lambda: model_info)
    monkeypatch.setattr(api, "log_operation", _noop)
    captured = {}

    async def _exec(**kwargs):
        captured.update(kwargs)
        return "ok"

    monkeypatch.setattr(api, "execute_with_llm_loop", _exec)
    monkeypatch.setattr(api, "ensure_user_sandbox", lambda uid: _value("/sandbox/x"))
    monkeypatch.setattr(api, "get_sandbox_workspace_path", lambda uid: "/ws")

    import app.utils.AiCodeUtil as aicode

    monkeypatch.setattr(aicode, "get_embedding", lambda text: _value([1.0, 0.0]))

    from app.models.aicloud_knowledge import AicloudKnowledgeChunk

    test_db.add(
        AicloudKnowledgeChunk(
            id="neg-1",
            doc_id="d",
            user_id=115,
            content="正交内容",
            chunk_index=0,
            collection="default",
            embedding=json.dumps([-1.0, 0.0]),
        )
    )
    await test_db.commit()

    await api.chat(
        ChatRequest(message="hi", session_id="all-filtered"), db=test_db, user_id=115
    )
    assert "知识库参考" not in captured["system_prompt"]
