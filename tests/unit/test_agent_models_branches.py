"""模型注册表与路由器全分支回归。"""

from types import SimpleNamespace

import pytest

from app.agent import models as m


def test_registry_get_and_get_by_name():
    assert m.ModelRegistry.get("qwen3-8b").key == "qwen3-8b"
    assert m.ModelRegistry.get("missing") is None
    assert m.ModelRegistry.get_by_name("Qwen/Qwen3-8B").key == "qwen3-8b"
    assert m.ModelRegistry.get_by_name("nope") is None


def test_registry_list_all():
    keys = {model.key for model in m.ModelRegistry.list_all()}
    assert {"qwen3-8b", "kolors", "bce-embedding"} <= keys


def test_route_primary_model():
    assert m.ModelRouter.route(m.TaskType.OCR).key == "deepseek-ocr"
    assert m.ModelRouter.route(m.TaskType.EMBEDDING).key == "bce-embedding"


def test_route_unknown_task_falls_back():
    class _Unknown:
        pass

    assert m.ModelRouter.route(_Unknown()).key == "deepseek-r1-qwen3-8b"


def test_route_prefer_fast_picks_fast_model():
    assert m.ModelRouter.route(m.TaskType.GENERAL, prefer_fast=True).key == "qwen3-8b"


def test_route_prefer_fast_without_fast_candidate():
    assert m.ModelRouter.route(m.TaskType.OCR, prefer_fast=True).key == "deepseek-ocr"


def test_route_primary_missing_falls_back(monkeypatch):
    monkeypatch.setitem(m.ModelRouter.TASK_MODEL_MAP, m.TaskType.OCR, ["gone"])
    assert m.ModelRouter.route(m.TaskType.OCR).key == "deepseek-r1-qwen3-8b"


@pytest.mark.asyncio
async def test_route_dynamic_prefer_fast(monkeypatch):
    calls = {}

    class _Router:
        async def get_best_model(self, keys, task):
            calls["keys"] = keys
            calls["task"] = task
            return "qwen3.5-4b"

    async def _get_router():
        return _Router()

    import app.agent.dynamic_model_router as dmr

    monkeypatch.setattr(dmr, "get_dynamic_router", _get_router)
    model = await m.ModelRouter.route_dynamic(m.TaskType.GENERAL, prefer_fast=True)
    assert model.key == "qwen3.5-4b"
    assert calls["task"] == "general"
    assert "qwen3-8b" in calls["keys"]


@pytest.mark.asyncio
async def test_route_dynamic_prefer_fast_without_fast(monkeypatch):
    calls = {}

    class _Router:
        async def get_best_model(self, keys, task):
            calls["keys"] = keys
            return "deepseek-ocr"

    async def _get_router():
        return _Router()

    import app.agent.dynamic_model_router as dmr

    monkeypatch.setattr(dmr, "get_dynamic_router", _get_router)
    model = await m.ModelRouter.route_dynamic(m.TaskType.OCR, prefer_fast=True)
    assert model.key == "deepseek-ocr"
    assert calls["keys"] == ["deepseek-ocr"]


@pytest.mark.asyncio
async def test_route_dynamic_unknown_best_key_falls_back(monkeypatch):
    class _Router:
        async def get_best_model(self, keys, task):
            return "not-registered"

    async def _get_router():
        return _Router()

    import app.agent.dynamic_model_router as dmr

    monkeypatch.setattr(dmr, "get_dynamic_router", _get_router)
    model = await m.ModelRouter.route_dynamic(m.TaskType.CODE_GENERATION)
    assert model.key == "deepseek-r1-qwen3-8b"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role,complexity,expected",
    [
        (m.AgentRole.ARCHITECT, "LARGE", "qwen3-8b"),
        (m.AgentRole.FRONTEND, "SMALL", "qwen2.5-7b"),
        (m.AgentRole.BACKEND, "MEDIUM", "qwen3.5-4b"),
        (m.AgentRole.REVIEWER, "ENTERPRISE", "glm-z1-9b"),
        (m.AgentRole.FALLBACK, "SIMPLE", "glm-4-9b"),
    ],
)
async def test_get_role_model_uses_learning_assignment(
    monkeypatch, role, complexity, expected
):
    assignment = SimpleNamespace(
        architect_model="qwen3-8b",
        frontend_model="qwen2.5-7b",
        backend_model="qwen3.5-4b",
        reviewer_model="glm-z1-9b",
        fallback_model="glm-4-9b",
    )

    class _Router:
        async def get_assignment_with_learning(self):
            return assignment

    async def _get_router():
        return _Router()

    import app.agent.dynamic_model_router as dmr

    monkeypatch.setattr(dmr, "get_dynamic_router", _get_router)
    model = await m.ModelRouter.get_role_model(role, complexity)
    assert model.key == expected


@pytest.mark.asyncio
async def test_get_role_model_unknown_key_falls_back_to_reasoning(monkeypatch):
    assignment = SimpleNamespace(
        architect_model="not-registered",
        frontend_model=None,
        backend_model=None,
        reviewer_model=None,
        fallback_model=None,
    )

    class _Router:
        async def get_assignment_with_learning(self):
            return assignment

    async def _get_router():
        return _Router()

    import app.agent.dynamic_model_router as dmr

    monkeypatch.setattr(dmr, "get_dynamic_router", _get_router)
    model = await m.ModelRouter.get_role_model(m.AgentRole.ARCHITECT)
    assert model.key == "deepseek-r1-qwen3-8b"


@pytest.mark.asyncio
async def test_get_role_model_router_failure_uses_static_fallback(monkeypatch):
    async def _boom():
        raise RuntimeError("router down")

    import app.agent.dynamic_model_router as dmr

    monkeypatch.setattr(dmr, "get_dynamic_router", _boom)
    model = await m.ModelRouter.get_role_model(m.AgentRole.BACKEND, "UNKNOWN")
    assert model.key == "qwen3.5-4b"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role,expected",
    [
        (m.AgentRole.ARCHITECT, "qwen3-8b"),
        (m.AgentRole.FRONTEND, "qwen2.5-7b"),
        (m.AgentRole.BACKEND, "qwen3.5-4b"),
        (m.AgentRole.REVIEWER, "glm-z1-9b"),
        (m.AgentRole.FALLBACK, "glm-z1-9b"),
    ],
)
async def test_get_role_model_static_fallbacks(monkeypatch, role, expected):
    async def _boom():
        raise RuntimeError("down")

    import app.agent.dynamic_model_router as dmr

    monkeypatch.setattr(dmr, "get_dynamic_router", _boom)
    model = await m.ModelRouter.get_role_model(role)
    assert model.key == expected


@pytest.mark.asyncio
async def test_get_role_model_unknown_role_uses_default(monkeypatch):
    class _Role:
        pass

    async def _boom():
        raise RuntimeError("down")

    import app.agent.dynamic_model_router as dmr

    monkeypatch.setattr(dmr, "get_dynamic_router", _boom)
    model = await m.ModelRouter.get_role_model(_Role())
    assert model.key == "deepseek-r1-qwen3-8b"


@pytest.mark.parametrize(
    "content,files,expected",
    [
        ("anything", ["a.png"], m.TaskType.VISUAL_UNDERSTANDING),
        ("anything", ["a.txt"], m.TaskType.FAST_RESPONSE),
        ("帮我生成图片", None, m.TaskType.IMAGE_GENERATION),
        ("识别文字", None, m.TaskType.OCR),
        ("分析这张图片", None, m.TaskType.VISUAL_UNDERSTANDING),
        ("帮我审查代码", None, m.TaskType.CODE_REVIEW),
        ("请解释这段逻辑", None, m.TaskType.REASONING),
        ("打开文件读取内容", None, m.TaskType.FILE_OPERATION),
        ("写一个函数", None, m.TaskType.CODE_GENERATION),
        ("hi", None, m.TaskType.FAST_RESPONSE),
        (
            "please provide a long general answer about many topics without keywords",
            None,
            m.TaskType.GENERAL,
        ),
    ],
)
def test_route_by_content(content, files, expected):
    assert m.ModelRouter.route_by_content(content, files) is expected


def test_route_by_content_general_long_text():
    long_text = "x" * 40
    assert m.ModelRouter.route_by_content(long_text) is m.TaskType.GENERAL


@pytest.mark.asyncio
async def test_get_role_model_missing_attribute_uses_static_fallback(monkeypatch):
    class _Router:
        async def get_assignment_with_learning(self):
            return SimpleNamespace()

    async def _get_router():
        return _Router()

    import app.agent.dynamic_model_router as dmr

    monkeypatch.setattr(dmr, "get_dynamic_router", _get_router)
    model = await m.ModelRouter.get_role_model(m.AgentRole.ARCHITECT)
    assert model.key == "qwen3-8b"


def test_route_by_content_keyword_selection_is_stable():
    assert m.ModelRouter.route_by_content("请分析并解释") is m.TaskType.REASONING
