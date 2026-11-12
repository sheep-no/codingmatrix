"""Branch coverage for app/agent/code_patcher.py."""

from pathlib import Path

import pytest

from app.agent import code_patcher as cp
from app.agent.code_patcher import (
    CodePatcher,
    CrossFilePatcher,
    PatchResult,
    _atomic_write_text,
    apply_incremental_change,
)


def _patch(old: str, new: str) -> str:
    return (
        "--- a/file.py\n"
        "+++ b/file.py\n"
        "@@ -1 +1 @@\n"
        f"-{old}\n"
        f"+{new}\n"
    )


# ---------------------------------------------------------------------------
# _atomic_write_text failure cleanup
# ---------------------------------------------------------------------------


def test_atomic_write_text_cleans_temp_on_failure(tmp_path, monkeypatch) -> None:
    def broken_fdopen(fd, *args, **kwargs):
        raise RuntimeError("cannot open")

    monkeypatch.setattr(cp.os, "fdopen", broken_fdopen)

    with pytest.raises(RuntimeError, match="cannot open"):
        _atomic_write_text(tmp_path / "out.txt", "data")

    assert list(tmp_path.iterdir()) == []


def test_atomic_write_text_tolerates_unlink_failure(tmp_path, monkeypatch) -> None:
    def broken_fdopen(fd, *args, **kwargs):
        raise RuntimeError("cannot open")

    monkeypatch.setattr(cp.os, "fdopen", broken_fdopen)
    monkeypatch.setattr(
        Path, "unlink", lambda self, *args, **kwargs: (_ for _ in ()).throw(OSError())
    )

    with pytest.raises(RuntimeError, match="cannot open"):
        _atomic_write_text(tmp_path / "out.txt", "data")


# ---------------------------------------------------------------------------
# Patch generation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_patch_includes_project_context() -> None:
    captured = {}

    async def llm(prompt, system):
        captured["prompt"] = prompt
        return "```diff\n--- a/file.py\n+++ b/file.py\n@@ -1 +1 @@\n-a\n+b\n```"

    patch = await CodePatcher(llm).generate_patch_from_requirement(
        "file.py", "a\n", "change", project_context={"requirement": "add feature"}
    )

    assert patch.startswith("--- a/file.py")
    assert "add feature" in captured["prompt"]


@pytest.mark.asyncio
async def test_generate_patch_wraps_unexpected_error(monkeypatch) -> None:
    async def llm(prompt, system):
        raise ValueError("provider down")

    logged = []
    monkeypatch.setattr(cp.logger, "error", logged.append)

    with pytest.raises(RuntimeError, match="LLM patch generation failed: provider down"):
        await CodePatcher(llm).generate_patch_from_requirement("file.py", "a\n", "change")

    assert logged


@pytest.mark.asyncio
async def test_generate_patch_no_context() -> None:
    async def llm(prompt, system):
        return "--- a/file.py\n+++ b/file.py\n@@ -1 +1 @@\n-a\n+b\n"

    patch = await CodePatcher(llm).generate_patch_from_requirement(
        "file.py", "a\n", "change"
    )

    assert patch == "--- a/file.py\n+++ b/file.py\n@@ -1 +1 @@\n-a\n+b\n"


def test_generate_diff_from_content() -> None:
    diff = CodePatcher().generate_diff_from_content("file.py", "a\nb\n", "a\nc\n")

    assert "--- a/file.py" in diff
    assert "-b" in diff
    assert "+c" in diff


# ---------------------------------------------------------------------------
# apply_patch exception path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_apply_patch_swallows_unexpected_exception(monkeypatch) -> None:
    def boom(self, patch):
        raise ValueError("parser exploded")

    monkeypatch.setattr(CodePatcher, "_parse_patch", boom)
    logged = []
    monkeypatch.setattr(cp.logger, "exception", logged.append)

    result = await CodePatcher().apply_patch("file.py", "a\n", _patch("a", "b"))

    assert result.success is False
    assert "parser exploded" in result.errors[0]
    assert logged


# ---------------------------------------------------------------------------
# apply_patch_to_file
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_apply_patch_to_file_missing(tmp_path) -> None:
    result = await CodePatcher().apply_patch_to_file(
        tmp_path / "missing.py", _patch("a", "b")
    )

    assert result.success is False
    assert "文件不存在" in result.errors[0]


@pytest.mark.asyncio
async def test_apply_patch_to_file_writes_backup(tmp_path) -> None:
    target = tmp_path / "file.py"
    target.write_text("a\n", encoding="utf-8")

    result = await CodePatcher().apply_patch_to_file(
        target, _patch("a", "b"), output_dir=tmp_path
    )

    assert result.success is True
    assert target.read_text(encoding="utf-8") == "b"
    assert (tmp_path / "file.py.bak").read_text(encoding="utf-8") == "a\n"


@pytest.mark.asyncio
async def test_apply_patch_to_file_failure_leaves_no_backup(tmp_path) -> None:
    target = tmp_path / "file.py"
    target.write_text("a\n", encoding="utf-8")

    result = await CodePatcher().apply_patch_to_file(
        target, "garbage", output_dir=tmp_path
    )

    assert result.success is False
    assert not (tmp_path / "file.py.bak").exists()


# ---------------------------------------------------------------------------
# estimate_patch_impact
# ---------------------------------------------------------------------------


def test_estimate_patch_impact_counts_files_and_lines() -> None:
    patch = (
        "--- a/one.py\n"
        "+++ b/one.py\n"
        "@@ -1 +1 @@\n"
        "-old\n"
        "+new\n"
        "--- a/two.py\n"
        "+++ b/two.py\n"
        "@@ -1 +1 @@\n"
        "-x\n"
        "+y\n"
    )

    impact = CodePatcher().estimate_patch_impact(patch)

    assert impact["lines_added"] == 2
    assert impact["lines_deleted"] == 2
    assert impact["total_changes"] == 4
    assert sorted(impact["files_affected"]) == ["one.py", "two.py"]
    assert impact["is_small_patch"] is True


def test_estimate_patch_impact_medium_and_large() -> None:
    medium = "\n".join(f"+line{i}" for i in range(25))
    large = "\n".join(f"+line{i}" for i in range(120))

    assert CodePatcher().estimate_patch_impact(medium)["is_medium_patch"] is True
    assert CodePatcher().estimate_patch_impact(large)["is_large_patch"] is True


# ---------------------------------------------------------------------------
# _extract_patch_from_response branches
# ---------------------------------------------------------------------------


def test_extract_patch_without_language_marker() -> None:
    response = "```\n--- a/file.py\n+++ b/file.py\n```"

    patch = CodePatcher()._extract_patch_from_response(response)

    assert patch is not None
    assert patch.startswith("--- a/file.py")


def test_extract_patch_returns_none_when_absent() -> None:
    assert CodePatcher()._extract_patch_from_response("no patch here") is None


def test_parse_patch_skips_non_hunk_lines() -> None:
    hunks = CodePatcher()._parse_patch(
        "--- a/file.py\ncontext not hunk\n@@ -1 +1 @@\n-a\n+b\n"
    )

    assert len(hunks) == 1
    assert hunks[0]["old_count"] == 1


def test_parse_patch_defaults_counts_when_omitted() -> None:
    hunks = CodePatcher()._parse_patch("@@ -3 +4 @@\n-a\n+b\n")

    assert hunks[0]["old_count"] == 1
    assert hunks[0]["new_count"] == 1


def test_parse_patch_stops_at_unrecognized_body_line() -> None:
    hunks = CodePatcher()._parse_patch("@@ -1,2 +1,2 @@\n-a\nnot a diff line\n")

    assert len(hunks[0]["lines"]) == 1


# ---------------------------------------------------------------------------
# Hunk application branches
# ---------------------------------------------------------------------------


def test_apply_hunks_out_of_range_returns_none() -> None:
    hunks = [{"old_start": 10, "old_count": 1, "lines": ["-a", "+b"]}]

    assert CodePatcher()._apply_hunks(["x"], hunks) is None


def test_apply_hunks_negative_start_returns_none() -> None:
    hunks = [{"old_start": 0, "old_count": 1, "lines": ["-a", "+b"]}]

    assert CodePatcher()._apply_hunks(["x"], hunks) is None


def test_apply_hunks_fuzzy_offset_match() -> None:
    hunks = [{
        "old_start": 2,
        "old_count": 2,
        "lines": [" a", "-b", "+c"],
    }]
    original = ["preamble", "a", "b"]

    result = CodePatcher()._apply_hunks_fuzzy(original, hunks, max_offset=2)

    assert result == ["preamble", "a", "c"]


def test_apply_hunks_fuzzy_no_match_returns_none() -> None:
    hunks = [{"old_start": 1, "old_count": 1, "lines": [" zzz", "+b"]}]

    assert CodePatcher()._apply_hunks_fuzzy(["a"], hunks) is None


def test_apply_hunks_fuzzy_skips_out_of_range_offsets() -> None:
    hunks = [{"old_start": 2, "old_count": 1, "lines": ["-a", "+b"]}]

    assert CodePatcher()._apply_hunks_fuzzy(["a"], hunks, max_offset=5) == ["b"]


def test_apply_hunks_new_file_zero_start() -> None:
    hunks = [{
        "old_start": 0,
        "old_count": 0,
        "lines": ["+new"],
    }]

    assert CodePatcher()._apply_hunks([], hunks) == ["new"]


def test_apply_hunks_fuzzy_new_file_zero_start() -> None:
    hunks = [{"old_start": 0, "old_count": 0, "lines": ["+new"]}]

    assert CodePatcher()._apply_hunks_fuzzy([], hunks) == ["new"]


@pytest.mark.asyncio
async def test_apply_patch_succeeds_after_fuzzy_fallback() -> None:
    original = "preamble\na\n"
    patch = (
        "--- a/file.py\n"
        "+++ b/file.py\n"
        "@@ -1,2 +1,2 @@\n"
        " preamble\n"
        "-zzz\n"
        "+preamble\n"
    )

    result = await CodePatcher().apply_patch("file.py", original, patch)

    assert result.success is True
    assert result.warnings


# ---------------------------------------------------------------------------
# apply_incremental_change success + no-patch branches
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_apply_incremental_change_success(tmp_path) -> None:
    target = tmp_path / "file.py"
    target.write_text("a\n", encoding="utf-8")

    async def llm(prompt, system):
        return "```diff\n" + _patch("a", "b") + "```"

    result = await apply_incremental_change(target, "change", llm)

    assert result.success is True


@pytest.mark.asyncio
async def test_apply_incremental_change_empty_patch_raises(tmp_path) -> None:
    target = tmp_path / "file.py"
    target.write_text("a\n", encoding="utf-8")

    async def llm(prompt, system):
        return "no patch"

    with pytest.raises(RuntimeError, match="returned no patch"):
        await apply_incremental_change(target, "change", llm)


@pytest.mark.asyncio
async def test_apply_incremental_change_falsy_patch_raises(tmp_path, monkeypatch) -> None:
    target = tmp_path / "file.py"
    target.write_text("a\n", encoding="utf-8")

    async def empty_generate(self, **kwargs):
        return ""

    monkeypatch.setattr(CodePatcher, "generate_patch_from_requirement", empty_generate)

    with pytest.raises(RuntimeError, match="returned no patch"):
        await apply_incremental_change(target, "change", lambda *_: None)


# ---------------------------------------------------------------------------
# CrossFilePatcher dependent loop
# ---------------------------------------------------------------------------


class _StubPatcher:
    def __init__(self, *, fail: set[str] = frozenset(), empty: set[str] = frozenset()):
        self.fail = fail
        self.empty = empty
        self.calls = []

    async def generate_patch_from_requirement(self, file_path, content, requirement, context=None):
        self.calls.append(file_path)
        if file_path in self.empty:
            return ""
        return _patch("old", "new")

    async def apply_patch(self, file_path, content, patch):
        return PatchResult(
            success=file_path not in self.fail,
            file_path=file_path,
            original_content=content,
            patched_content=content.replace("old", "new"),
            diff=patch,
            errors=[] if file_path not in self.fail else ["bad"],
            warnings=[],
        )


@pytest.mark.asyncio
async def test_cross_file_patches_dependent_success() -> None:
    patcher = CrossFilePatcher(_StubPatcher())

    result = await patcher.generate_cross_file_patches(
        requirement="change",
        changed_files=["main.py"],
        affected_files={"main.py": ["helper.py"]},
        project_path=Path("."),
        file_contents={"main.py": "old\n", "helper.py": "old\n"},
    )

    assert len(result.dependent_results) == 1
    assert result.dependent_results[0].file_path == "helper.py"


@pytest.mark.asyncio
async def test_cross_file_patches_skips_dependent_that_is_changed() -> None:
    patcher = CrossFilePatcher(_StubPatcher())

    result = await patcher.generate_cross_file_patches(
        requirement="change",
        changed_files=["main.py"],
        affected_files={"main.py": ["main.py"]},
        project_path=Path("."),
        file_contents={"main.py": "old\n"},
    )

    assert result.dependent_results == []


@pytest.mark.asyncio
async def test_cross_file_patches_empty_changed_file_raises(tmp_path) -> None:
    (tmp_path / "main.py").write_text("", encoding="utf-8")
    patcher = CrossFilePatcher(_StubPatcher())

    with pytest.raises(RuntimeError, match="empty or missing"):
        await patcher.generate_cross_file_patches(
            requirement="change",
            changed_files=["main.py"],
            affected_files={},
            project_path=tmp_path,
            file_contents={},
        )


@pytest.mark.asyncio
async def test_cross_file_patches_empty_changed_file_read_from_disk(tmp_path) -> None:
    (tmp_path / "main.py").write_text("old\n", encoding="utf-8")
    patcher = CrossFilePatcher(_StubPatcher())

    result = await patcher.generate_cross_file_patches(
        requirement="change",
        changed_files=["main.py"],
        affected_files={},
        project_path=tmp_path,
        file_contents={},
    )

    assert result.primary_result is not None


@pytest.mark.asyncio
async def test_cross_file_patches_empty_patch_raises() -> None:
    patcher = CrossFilePatcher(_StubPatcher(empty={"main.py"}))

    with pytest.raises(RuntimeError, match="empty patch"):
        await patcher.generate_cross_file_patches(
            requirement="change",
            changed_files=["main.py"],
            affected_files={},
            project_path=Path("."),
            file_contents={"main.py": "old\n"},
        )


@pytest.mark.asyncio
async def test_cross_file_patches_changed_apply_failure_raises() -> None:
    patcher = CrossFilePatcher(_StubPatcher(fail={"main.py"}))

    with pytest.raises(RuntimeError, match="failed to apply patch to main.py"):
        await patcher.generate_cross_file_patches(
            requirement="change",
            changed_files=["main.py"],
            affected_files={},
            project_path=Path("."),
            file_contents={"main.py": "old\n"},
        )


@pytest.mark.asyncio
async def test_cross_file_patches_dependent_read_from_disk(tmp_path) -> None:
    (tmp_path / "helper.py").write_text("old\n", encoding="utf-8")
    patcher = CrossFilePatcher(_StubPatcher())

    result = await patcher.generate_cross_file_patches(
        requirement="change",
        changed_files=["main.py"],
        affected_files={"main.py": ["helper.py"]},
        project_path=tmp_path,
        file_contents={"main.py": "old\n"},
    )

    assert len(result.dependent_results) == 1


@pytest.mark.asyncio
async def test_cross_file_patches_dependent_missing_raises() -> None:
    patcher = CrossFilePatcher(_StubPatcher())

    with pytest.raises(RuntimeError, match="failed to read dependent file"):
        await patcher.generate_cross_file_patches(
            requirement="change",
            changed_files=["main.py"],
            affected_files={"main.py": ["helper.py"]},
            project_path=Path("missing"),
            file_contents={"main.py": "old\n"},
        )


@pytest.mark.asyncio
async def test_cross_file_patches_dependent_empty_raises(tmp_path) -> None:
    (tmp_path / "helper.py").write_text("", encoding="utf-8")
    patcher = CrossFilePatcher(_StubPatcher())

    with pytest.raises(RuntimeError, match="dependent file is empty or missing"):
        await patcher.generate_cross_file_patches(
            requirement="change",
            changed_files=["main.py"],
            affected_files={"main.py": ["helper.py"]},
            project_path=tmp_path,
            file_contents={"main.py": "old\n"},
        )


@pytest.mark.asyncio
async def test_cross_file_patches_dependent_empty_patch_raises() -> None:
    patcher = CrossFilePatcher(_StubPatcher(empty={"helper.py"}))

    with pytest.raises(RuntimeError, match="empty patch for helper.py"):
        await patcher.generate_cross_file_patches(
            requirement="change",
            changed_files=["main.py"],
            affected_files={"main.py": ["helper.py"]},
            project_path=Path("."),
            file_contents={"main.py": "old\n", "helper.py": "old\n"},
        )


@pytest.mark.asyncio
async def test_cross_file_patches_dependent_apply_failure_raises() -> None:
    patcher = CrossFilePatcher(_StubPatcher(fail={"helper.py"}))

    with pytest.raises(RuntimeError, match="failed to apply patch to helper.py"):
        await patcher.generate_cross_file_patches(
            requirement="change",
            changed_files=["main.py"],
            affected_files={"main.py": ["helper.py"]},
            project_path=Path("."),
            file_contents={"main.py": "old\n", "helper.py": "old\n"},
        )


@pytest.mark.asyncio
async def test_cross_file_patches_empty_changed_files_primary_is_blank() -> None:
    result = await CrossFilePatcher(_StubPatcher()).generate_cross_file_patches(
        requirement="change",
        changed_files=[],
        affected_files={},
        project_path=Path("."),
        file_contents={},
    )

    assert result.primary_file == ""


@pytest.mark.asyncio
async def test_cross_file_patches_failed_list_raises(monkeypatch) -> None:
    original = cp.CrossFilePatchResult

    def factory(*args, **kwargs):
        result = original(*args, **kwargs)
        result.failed_patches.append("main.py")
        return result

    monkeypatch.setattr(cp, "CrossFilePatchResult", factory)

    with pytest.raises(RuntimeError, match="cross-file patch failed for 1 file"):
        await CrossFilePatcher(_StubPatcher()).generate_cross_file_patches(
            requirement="change",
            changed_files=["main.py"],
            affected_files={},
            project_path=Path("."),
            file_contents={"main.py": "old\n"},
        )
