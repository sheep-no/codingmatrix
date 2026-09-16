import pytest
import asyncio
import tempfile
from pathlib import Path

class TestRefinementLoop:
    @pytest.fixture
    def loop(self):
        from app.agent.refinement_loop import RefinementLoop
        from app.agent.shared_context import SharedContext
        
        with tempfile.TemporaryDirectory() as tmpdir:
            ctx = SharedContext("test requirement", Path(tmpdir))
            ctx.model_assignment = {"backend_model": "test-model"}
            yield RefinementLoop(ctx)
    
    def test_refine_success(self, loop):
        initial_content = "def hello(): pass"
        
        result = asyncio.run(loop.refine(
            file_path="test.py",
            file_type="backend",
            description="test",
            initial_content=initial_content,
            model_name="test-model",
            project_context={}
        ))
        
        assert result is not None
        assert hasattr(result, 'final_content')
        assert hasattr(result, 'success')
        assert hasattr(result, 'attempts')


def test_refinement_loop_requires_model_assignment(tmp_path):
    from app.agent.refinement_loop import RefinementLoop
    from app.agent.shared_context import SharedContext

    ctx = SharedContext("test requirement", tmp_path)
    with pytest.raises(RuntimeError, match="model assignment is required for refinement"):
        RefinementLoop(ctx)


class TestJsFamilyValidation:
    """`_validate_code` 必须覆盖 JS/TS 家族全部扩展名，且不误报 SFC/JSX。"""

    @pytest.fixture
    def loop(self):
        from app.agent.refinement_loop import RefinementLoop
        from app.agent.shared_context import SharedContext

        with tempfile.TemporaryDirectory() as tmpdir:
            ctx = SharedContext("test requirement", Path(tmpdir))
            ctx.model_assignment = {"backend_model": "test-model"}
            yield RefinementLoop(ctx)

    @pytest.mark.asyncio
    async def test_vue_single_file_component_is_not_a_syntax_error(self, loop):
        content = (
            "<template><div>hi</div></template>\n"
            "<script>export default { name: 'A' }</script>\n"
        )

        issues = await loop._validate_code("src/App.vue", content, "frontend")

        assert issues == []

    @pytest.mark.asyncio
    async def test_jsx_and_tsx_jsx_syntax_is_not_a_syntax_error(self, loop):
        assert await loop._validate_code(
            "src/App.jsx", "export default function App() { return <div>hi</div> }\n", "frontend"
        ) == []
        assert await loop._validate_code(
            "src/App.tsx", "export const A = (): JSX.Element => <div>hi</div>\n", "frontend"
        ) == []

    @pytest.mark.asyncio
    async def test_js_family_extensions_reject_python_code(self, loop):
        python_source = "def main():\n    return 1\n"

        for path in ("src/a.mjs", "src/a.cjs", "src/App.jsx", "src/App.tsx"):
            issues = await loop._validate_code(path, python_source, "frontend")
            assert issues, path

    @pytest.mark.asyncio
    async def test_mjs_and_cjs_real_syntax_errors_are_flagged(self, loop):
        for path in ("src/a.mjs", "src/a.cjs"):
            issues = await loop._validate_code(path, "const x = ;\n", "frontend")
            assert issues, path

    @pytest.mark.asyncio
    async def test_vue_script_block_syntax_error_is_flagged(self, loop):
        content = "<script>const x = ;</script>\n"

        issues = await loop._validate_code("src/App.vue", content, "frontend")

        assert issues
        assert issues[0].type == "syntax"


class TestWarningDoesNotBlockRefinement:
    """warning 是诊断信息：不应触发修复轮次，也不应把文件判为失败。"""

    @pytest.fixture
    def loop(self):
        from app.agent.refinement_loop import RefinementLoop
        from app.agent.shared_context import SharedContext

        with tempfile.TemporaryDirectory() as tmpdir:
            ctx = SharedContext("test requirement", Path(tmpdir))
            ctx.model_assignment = {"backend_model": "test-model"}
            yield RefinementLoop(ctx)

    @pytest.mark.asyncio
    async def test_warning_only_issues_pass_without_extra_llm_calls(self, loop, monkeypatch):
        from app.agent.refinement_loop import ValidationIssue

        async def warning_only(self, file_path, content, file_type):
            return [ValidationIssue(
                type="spec_mismatch",
                severity="warning",
                message="类型定义文件应使用 Pydantic BaseModel",
            )]

        calls = []

        async def fail_if_called(**kwargs):
            calls.append(kwargs)
            raise AssertionError("warning 不应触发修复调用")

        monkeypatch.setattr("app.agent.refinement_loop.RefinementLoop._validate_code", warning_only)
        monkeypatch.setattr("app.agent.refinement_loop.call_llm", fail_if_called)

        result = await loop.refine(
            file_path="app/models.py",
            file_type="model",
            description="模型",
            initial_content="class User:\n    pass\n",
            model_name="test-model",
        )

        assert result.success is True
        assert result.attempts == 1
        assert calls == []
        assert [issue.severity for issue in result.remaining_issues] == ["warning"]

    @pytest.mark.asyncio
    async def test_environment_import_absence_is_not_reported(self, loop):
        content = "import torch\n\n\ndef run():\n    return torch.tensor(1)\n"

        issues = await loop._validate_code("app/model.py", content, "model")

        assert issues == []
