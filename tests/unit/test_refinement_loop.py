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
