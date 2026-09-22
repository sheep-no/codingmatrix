"""Spec-First 的语言契约约束（SPFG5/SPFG6）。"""

import inspect
from types import SimpleNamespace

import pytest

from app.agent.adapters import LanguageAdapterRegistry
from app.agent.backend_engineer import BackendEngineer
from app.agent.dependency_graph import DependencyGraph
from app.agent.frontend_engineer import FrontendEngineer
from app.agent.orchestrator_generation import spec_first_generate as module
from app.agent.orchestrator_generation.spec_first_generate import SpecFirstGenerateMixin


class TestGenerateFileContract:
    """所有工程师的 generate_file 都是 async，调用方的协程探测是死代码。"""

    def test_generate_file_is_coroutine_function(self):
        assert inspect.iscoroutinefunction(BackendEngineer.generate_file)
        assert inspect.iscoroutinefunction(FrontendEngineer.generate_file)

    def test_no_runtime_coroutine_guard_remains(self):
        assert "iscoroutine" not in inspect.getsource(module)


class TestRefactorLanguageSelection:
    @pytest.mark.asyncio
    async def test_refactor_file_selects_adapter_by_target_file(self, tmp_path, monkeypatch):
        js_file = "web/app.js"
        js_adapter = LanguageAdapterRegistry.get_adapter_for_file(js_file)
        assert js_adapter is not None

        (tmp_path / "web").mkdir()
        (tmp_path / js_file).write_text("export const a = 1;\n", encoding="utf-8")

        graph = DependencyGraph(language_adapter=js_adapter)
        graph.add_file(js_file, file_type="frontend_component")

        calls = []
        real_get_adapter_for_file = LanguageAdapterRegistry.get_adapter_for_file

        def spy_get_adapter_for_file(file_path):
            calls.append(file_path)
            return real_get_adapter_for_file(file_path)

        monkeypatch.setattr(
            LanguageAdapterRegistry,
            "get_adapter_for_file",
            staticmethod(spy_get_adapter_for_file),
        )
        monkeypatch.setattr(
            DependencyGraph,
            "load",
            classmethod(lambda cls, path, language_adapter=None: graph),
        )

        async def fake_call_llm(**kwargs):
            return "不是 JSON"

        monkeypatch.setattr("app.utils.call_llm", fake_call_llm)

        obj = object.__new__(SpecFirstGenerateMixin)
        obj.output_dir = tmp_path
        obj.api_key_token = "token"
        obj.model_assignment = SimpleNamespace(backend_model="m")

        result = await SpecFirstGenerateMixin.refactor_file(obj, js_file, "拆分")

        # 适配器按待拆分文件推断；硬编码 "python" 时本断言失败
        assert calls == [js_file]
        assert result["success"] is False
