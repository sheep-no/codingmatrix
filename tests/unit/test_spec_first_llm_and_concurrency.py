"""Spec-First 的并发限流、LLM 统一层与重构默认动作（SPFG7/SPFG10/SPFG17）。"""

import asyncio
import json
from types import SimpleNamespace

import pytest

from app.agent.orchestrator_generation import spec_first_generate as module
from app.agent.orchestrator_generation.spec_first_generate import (
    LAYER_CONCURRENCY_LIMIT,
    SpecFirstGenerateMixin,
    gather_with_limit,
)


class TestGatherWithLimit:
    @pytest.mark.asyncio
    async def test_bounds_concurrency_and_keeps_order(self):
        active = 0
        peak = 0

        async def job(i):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0.01)
            active -= 1
            return i

        results = await gather_with_limit([job(i) for i in range(20)], 3)

        assert results == list(range(20))
        assert peak <= 3

    @pytest.mark.asyncio
    async def test_exceptions_returned_as_results(self):
        async def boom():
            raise ValueError("x")

        async def ok():
            return 1

        results = await gather_with_limit([boom(), ok()], 2)

        assert isinstance(results[0], ValueError)
        assert results[1] == 1

    def test_default_limit_is_positive(self):
        assert LAYER_CONCURRENCY_LIMIT >= 1


class TestQuickLlmCheck:
    @pytest.mark.asyncio
    async def test_routes_through_llm_client(self, monkeypatch):
        created = {}

        class FakeClient:
            def __init__(self, **kwargs):
                created.update(kwargs)

            async def call(self, prompt, system_prompt=""):
                created["prompt"] = prompt
                created["system_prompt"] = system_prompt
                return "  YES  "

        monkeypatch.setattr("app.agent.llm_client.LLMClient", FakeClient)

        mixin = object.__new__(SpecFirstGenerateMixin)
        mixin.model_assignment = SimpleNamespace(backend_model="backend-x")
        mixin.api_key_token = "tok"
        mixin.cancel_event = None

        assert await mixin._quick_llm_check("is python?") == "YES"
        assert created["model_name"] == "backend-x"
        assert created["task_type"] == "review"
        assert created["api_key_token"] == "tok"
        assert created["prompt"] == "is python?"


class _FakeGraph:
    def __init__(self, old_path):
        self.nodes = {old_path: SimpleNamespace(description="old")}

    def refactor_file(self, old_path, new_files, import_mapping):
        paths = [nf["path"] for nf in new_files]
        for path in paths:
            self.nodes[path] = SimpleNamespace(description="new")
        return paths

    def get_context_for_file(self, *_args, **_kwargs):
        return ""

    def save(self, _path):
        pass


class _CapturingGraph(_FakeGraph):
    """记录 get_context_for_file 的调用实参，用于校验 DG7 的接线。"""

    def __init__(self, old_path):
        super().__init__(old_path)
        self.context_calls = []

    def get_context_for_file(self, file_path, generated_files, **kwargs):
        self.context_calls.append(
            {"file_path": file_path, "generated_files": dict(generated_files), **kwargs}
        )
        return ""


class _FakeValidator:
    def __init__(self, **_kwargs):
        pass

    async def validate(self, *_args, **_kwargs):
        return SimpleNamespace(passed=True, issues=[])


class _FakeEngineer:
    async def generate_file(self, *_args, **_kwargs):
        return "const a = 1;\n"


def _prepare_refactor(monkeypatch, tmp_path, old_path, plan, graph_factory=_FakeGraph):
    full_path = tmp_path / old_path
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_text("export const a = 1;\n", encoding="utf-8")

    graph = graph_factory(old_path)
    monkeypatch.setattr(
        module.DependencyGraph, "load", classmethod(lambda cls, path, language_adapter=None: graph)
    )
    monkeypatch.setattr(
        module, "DependencyGraphValidator", lambda **kwargs: _FakeValidator(**kwargs)
    )
    monkeypatch.setattr(module, "write_file_atomic", lambda *a, **k: None)

    async def fake_call_llm(**_kwargs):
        return json.dumps(plan)

    monkeypatch.setattr("app.utils.call_llm", fake_call_llm)

    async def fake_extract(content, *_args, **_kwargs):
        return content

    monkeypatch.setattr("app.agent.utils.extract_engineer_content", fake_extract)

    mixin = object.__new__(SpecFirstGenerateMixin)
    mixin.output_dir = tmp_path
    mixin.api_key_token = "tok"
    mixin.model_assignment = SimpleNamespace(backend_model="backend-x")
    mixin.cancel_event = None
    mixin._select_engineer = lambda path: _FakeEngineer()
    mixin._select_model_for_file = lambda path: "backend-x"
    mixin._create_validator_llm_caller = lambda: None
    mixin._report_progress = lambda *a, **k: None
    mixin._test_graph = graph
    return mixin, full_path


class TestRefactorDependencyContext:
    @pytest.mark.asyncio
    async def test_context_uses_path_content_map_and_model_window(self, monkeypatch, tmp_path):
        old_path = "web/app.js"
        plan = {
            "new_files": [
                {"path": "web/a.js", "file_type": "frontend_component", "description": "a"},
                {"path": "web/b.js", "file_type": "frontend_component", "description": "b"},
            ],
            "import_mapping": {},
        }
        mixin, _ = _prepare_refactor(
            monkeypatch, tmp_path, old_path, plan, graph_factory=_CapturingGraph
        )

        result = await mixin.refactor_file(old_path, "拆分")

        assert result["success"] is True
        calls = mixin._test_graph.context_calls
        # 第一份文件生成前没有已生成内容，第二份应带上第一份的路径 -> 内容
        assert calls[0]["generated_files"] == {}
        assert calls[1]["generated_files"] == {"web/a.js": "const a = 1;\n"}
        # 必须传入模型窗口，否则预算退回固定兜底（DG7）
        assert all(call.get("model_context_length", 0) > 0 for call in calls)


class TestRefactorOldFileAction:
    @pytest.mark.asyncio
    async def test_defaults_to_keep(self, monkeypatch, tmp_path):
        old_path = "web/app.js"
        plan = {
            "new_files": [
                {"path": "web/part.js", "file_type": "frontend_component", "description": "d"}
            ],
            "import_mapping": {},
        }
        mixin, full_path = _prepare_refactor(monkeypatch, tmp_path, old_path, plan)

        result = await mixin.refactor_file(old_path, "拆分")

        assert result["success"] is True
        # 方案未指定 old_file_action，默认保守保留原文件
        assert full_path.exists()

    @pytest.mark.asyncio
    async def test_explicit_delete_still_removes(self, monkeypatch, tmp_path):
        old_path = "web/app.js"
        plan = {
            "new_files": [
                {"path": "web/part.js", "file_type": "frontend_component", "description": "d"}
            ],
            "import_mapping": {},
            "old_file_action": "delete",
        }
        mixin, full_path = _prepare_refactor(monkeypatch, tmp_path, old_path, plan)

        result = await mixin.refactor_file(old_path, "拆分")

        assert result["success"] is True
        assert not full_path.exists()
