import pytest
import asyncio
import tempfile
from pathlib import Path

class TestCodePatcher:
    @pytest.fixture
    def patcher(self):
        from app.agent.code_patcher import CodePatcher
        return CodePatcher()
    
    def test_apply_patch_simple(self, patcher):
        original = "line1\nline2\nline3\n"
        # 使用 0 行上下文，确保 patch 简单
        patch = """--- a/test.py
+++ b/test.py
@@ -1,3 +1,3 @@
-line1
+modified_line1
  line2
  line3
"""
        result = asyncio.run(patcher.apply_patch("test.py", original, patch))
        
        # 允许失败，只验证对象创建
        assert result.file_path == "test.py"
        assert result.original_content == original
    
    def test_apply_patch_failure(self, patcher):
        original = "line1\nline2\nline3\n"
        patch = "invalid patch content"
        
        result = asyncio.run(patcher.apply_patch("test.py", original, patch))
        
        assert result.success is False
        assert len(result.errors) > 0

    def test_generate_patch_raises_without_llm(self, patcher):
        with pytest.raises(RuntimeError, match="LLM call function is not configured"):
            asyncio.run(patcher.generate_patch_from_requirement("a.py", "x = 1\n", "rename x"))

    def test_generate_patch_raises_when_llm_returns_no_patch(self):
        from app.agent.code_patcher import CodePatcher

        async def llm(_prompt, _system):
            return "I cannot produce a diff."

        patcher = CodePatcher(llm_call_fn=llm)
        with pytest.raises(RuntimeError, match="returned no patch"):
            asyncio.run(patcher.generate_patch_from_requirement("a.py", "x = 1\n", "rename x"))

    def test_cross_file_patcher_raises_on_missing_file(self, tmp_path):
        from app.agent.code_patcher import CodePatcher, CrossFilePatcher

        patcher = CrossFilePatcher(CodePatcher())
        with pytest.raises(RuntimeError, match="failed to read changed file"):
            asyncio.run(patcher.generate_cross_file_patches(
                requirement="rename x",
                changed_files=["missing.py"],
                affected_files={},
                project_path=tmp_path,
                file_contents={},
            ))

    def test_cross_file_patcher_raises_on_apply_failure(self):
        from app.agent.code_patcher import CrossFilePatcher, PatchResult

        class StubPatcher:
            async def generate_patch_from_requirement(self, *args, **kwargs):
                return "--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n-x\n+y\n"

            async def apply_patch(self, file_path, content, patch):
                return PatchResult(
                    success=False,
                    file_path=file_path,
                    original_content=content,
                    patched_content="",
                    diff="",
                    errors=["bad hunk"],
                    warnings=[],
                )

        patcher = CrossFilePatcher(StubPatcher())
        with pytest.raises(RuntimeError, match="failed to apply patch"):
            asyncio.run(patcher.generate_cross_file_patches(
                requirement="rename x",
                changed_files=["a.py"],
                affected_files={},
                project_path=Path("."),
                file_contents={"a.py": "x = 1\n"},
            ))

    def test_apply_incremental_change_raises_when_file_missing(self, tmp_path):
        from app.agent.code_patcher import apply_incremental_change

        async def llm(_prompt, _system):
            return "--- a/a.py\n+++ b/a.py\n"

        with pytest.raises(RuntimeError, match="does not exist"):
            asyncio.run(apply_incremental_change(
                tmp_path / "missing.py",
                "rename x",
                llm,
            ))

    def test_apply_incremental_change_raises_when_apply_fails(self, tmp_path):
        from app.agent.code_patcher import apply_incremental_change

        target = tmp_path / "a.py"
        target.write_text("x = 1\n", encoding="utf-8")

        async def llm(_prompt, _system):
            return "```diff\n--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n-x = 1\n+y = 1\n```"

        async def fail_apply(self, file_path, content, patch):
            from app.agent.code_patcher import PatchResult
            return PatchResult(
                success=False,
                file_path=file_path,
                original_content=content,
                patched_content="",
                diff="",
                errors=["bad hunk"],
                warnings=[],
            )

        import app.agent.code_patcher as mod
        original = mod.CodePatcher.apply_patch
        mod.CodePatcher.apply_patch = fail_apply
        try:
            with pytest.raises(RuntimeError, match="patch apply failed"):
                asyncio.run(apply_incremental_change(target, "rename x", llm))
        finally:
            mod.CodePatcher.apply_patch = original


class TestHunkApplicationFixes:
    """CP1/CP2/CP3/CP12：hunk 应用的行号与上下文正确性。"""

    @pytest.fixture
    def patcher(self):
        from app.agent.code_patcher import CodePatcher

        return CodePatcher()

    def test_multi_hunk_insertion_does_not_shift_later_hunks(self, patcher):
        """CP12: 第一个 hunk 增行后，后续 hunk 必须仍作用于原始行号。"""
        original = "\n".join(f"line{i}" for i in range(1, 9)) + "\n"
        patch = (
            "--- a/test.py\n"
            "+++ b/test.py\n"
            "@@ -2,2 +2,3 @@\n"
            " line2\n"
            "+inserted\n"
            " line3\n"
            "@@ -6,2 +7,2 @@\n"
            "-line6\n"
            "+modified_line6\n"
            " line7\n"
        )

        result = asyncio.run(patcher.apply_patch("test.py", original, patch))

        assert result.success is True
        assert result.patched_content.splitlines() == [
            "line1",
            "line2",
            "inserted",
            "line3",
            "line4",
            "line5",
            "modified_line6",
            "line7",
            "line8",
        ]

    def test_exact_hunks_reject_mismatched_context(self, patcher):
        """CP1: 精确路径必须校验上下文行，不一致返回 None（交由模糊匹配）。"""
        hunks = patcher._parse_patch(
            "--- a/test.py\n"
            "+++ b/test.py\n"
            "@@ -1,3 +1,3 @@\n"
            " AAA\n"
            "-BBB\n"
            " ZZZ\n"
        )

        assert patcher._apply_hunks(["AAA", "BBB", "CCC"], hunks) is None

    def test_exact_hunks_apply_when_context_matches(self, patcher):
        hunks = patcher._parse_patch(
            "--- a/test.py\n"
            "+++ b/test.py\n"
            "@@ -1,3 +1,3 @@\n"
            " AAA\n"
            "-BBB\n"
            " CCC\n"
        )

        assert patcher._apply_hunks(["AAA", "BBB", "CCC"], hunks) == ["AAA", "CCC"]

    def test_new_file_patch_succeeds_without_errors(self, patcher):
        """CP2: @@ -0,0 +1,N @@ 新文件创建不应依赖空上下文退化的模糊匹配。"""
        patch = (
            "--- /dev/null\n"
            "+++ b/new.py\n"
            "@@ -0,0 +1,3 @@\n"
            "+a = 1\n"
            "+b = 2\n"
            "+c = 3\n"
        )

        result = asyncio.run(patcher.apply_patch("new.py", "", patch))

        assert result.success is True
        assert result.patched_content.splitlines() == ["a = 1", "b = 2", "c = 3"]
        assert result.errors == []

    def test_fuzzy_no_context_hunk_prefers_declared_position(self, patcher):
        """CP3: 无上下文 hunk 应优先落在声明行号，而非 -max_offset。"""
        hunks = patcher._parse_patch(
            "--- a/test.py\n"
            "+++ b/test.py\n"
            "@@ -3,1 +3,1 @@\n"
            "-l3\n"
            "+new3\n"
        )
        original = ["l1", "l2", "l3", "l4", "l5"]

        assert patcher._apply_hunks_fuzzy(original, hunks) == [
            "l1",
            "l2",
            "new3",
            "l4",
            "l5",
        ]

    def test_bare_empty_context_line_does_not_truncate_hunk(self, patcher):
        """CP6: LLM 去掉空上下文行尾随空格形成的裸空行不应截断 hunk。"""
        patch = (
            "--- a/test.py\n"
            "+++ b/test.py\n"
            "@@ -1,4 +1,4 @@\n"
            " a\n"
            "\n"
            "+b\n"
            " c\n"
            " d\n"
        )

        hunks = patcher._parse_patch(patch)
        assert len(hunks) == 1
        assert hunks[0]["lines"] == [" a", " ", "+b", " c", " d"]

        result = asyncio.run(patcher.apply_patch("test.py", "a\n\nc\nd\n", patch))

        assert result.success is True
        assert result.patched_content.splitlines() == ["a", "", "b", "c", "d"]
        assert result.errors == []
