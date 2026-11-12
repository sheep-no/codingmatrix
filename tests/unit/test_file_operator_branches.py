"""Branch coverage for app/utils/file_operator.py."""

import os
import stat
from pathlib import Path

import pytest

from app.utils.file_operator import (
    FileOperator,
    FileOperatorError,
    PathSecurityError,
)


def _op(root: Path, **kwargs) -> FileOperator:
    kwargs.setdefault("base_path", str(root))
    kwargs.setdefault("allow_protected_paths", True)
    return FileOperator(**kwargs)


# ---------------------------------------------------------------------------
# Path validation
# ---------------------------------------------------------------------------


def test_base_path_rejects_escape(tmp_path) -> None:
    operator = FileOperator(base_path=str(tmp_path / "root"), allow_protected_paths=True)
    (tmp_path / "root").mkdir()

    with pytest.raises(PathSecurityError, match="路径超出允许范围"):
        operator._validate_path("../outside.txt")


def test_base_path_accepts_base_itself(tmp_path) -> None:
    operator = FileOperator(base_path=str(tmp_path), allow_protected_paths=True)

    assert operator._validate_path(".") == tmp_path.resolve()


def test_protected_system_path_rejected() -> None:
    with pytest.raises(PathSecurityError, match="禁止访问系统路径"):
        FileOperator()._validate_path("/etc/passwd", check_extension=False)


def test_must_exist_raises_file_not_found(tmp_path) -> None:
    operator = _op(tmp_path)

    with pytest.raises(FileNotFoundError, match="路径不存在"):
        operator._validate_path("missing.py", must_exist=True)


def test_unsupported_extension_uses_name_fallback(tmp_path) -> None:
    operator = _op(tmp_path)

    # Path.suffix for "Makefile.weird" is ".weird" but name fallback also fails.
    with pytest.raises(PathSecurityError):
        operator._validate_path("Makefile.weird")


def test_protected_file_with_path_segment_match() -> None:
    assert FileOperator._is_protected_file(
        Path("/srv/app/.git/config"), "/srv/app/.git/config", ".git/config"
    ) is True


# ---------------------------------------------------------------------------
# _collect_files
# ---------------------------------------------------------------------------


def test_collect_files_skips_symlinks(tmp_path) -> None:
    (tmp_path / "real.txt").write_text("x\n", encoding="utf-8")
    (tmp_path / "link.txt").symlink_to(tmp_path / "real.txt")
    operator = _op(tmp_path)

    collected = {str(p) for p in operator._collect_files(tmp_path)}

    assert "real.txt" in collected
    assert "link.txt" not in collected


def test_collect_files_ignores_permission_error(tmp_path, monkeypatch) -> None:
    operator = _op(tmp_path)

    def boom(self, *args, **kwargs):
        raise PermissionError()

    monkeypatch.setattr(Path, "rglob", boom)

    assert operator._collect_files(tmp_path) == []


def test_should_skip_protected_non_hidden_file(tmp_path) -> None:
    operator = _op(tmp_path)

    assert operator._should_skip_entry(Path("id_rsa")) is True
    assert operator._should_skip_entry(Path("notes.txt")) is False


# ---------------------------------------------------------------------------
# read
# ---------------------------------------------------------------------------


def test_read_rejects_symlink(tmp_path, monkeypatch) -> None:
    (tmp_path / "real.txt").write_text("x\n", encoding="utf-8")
    (tmp_path / "link.txt").symlink_to(tmp_path / "real.txt")
    operator = _op(tmp_path)

    monkeypatch.setattr(Path, "is_symlink", lambda self: True)

    with pytest.raises(PermissionError, match="不允许读取符号链接"):
        operator.read("link.txt")


def test_read_rejects_directory(tmp_path) -> None:
    (tmp_path / "dir").mkdir()
    operator = _op(tmp_path)

    with pytest.raises(FileNotFoundError, match="不是文件"):
        operator.read("dir")


def test_read_negative_offset_clamps_to_zero(tmp_path) -> None:
    (tmp_path / "f.txt").write_text("a\nb\n", encoding="utf-8")
    operator = _op(tmp_path)

    result = operator.read("f.txt", offset=-5, limit=1)

    assert result["offset"] == 0
    assert result["content"] == "a\n"


# ---------------------------------------------------------------------------
# write / create / delete / move / copy
# ---------------------------------------------------------------------------


def test_write_with_backup(tmp_path) -> None:
    (tmp_path / "f.py").write_text("old\n", encoding="utf-8")
    operator = _op(tmp_path)

    result = operator.write("f.py", "new content\n", create_backup=True)

    assert result["backup"] == "f.py.bak"
    assert (tmp_path / "f.py.bak").read_text(encoding="utf-8") == "old\n"


def test_create_existing_path_raises(tmp_path) -> None:
    (tmp_path / "f.py").write_text("x\n", encoding="utf-8")
    operator = _op(tmp_path)

    with pytest.raises(FileExistsError, match="路径已存在"):
        operator.create("f.py")


def test_create_directory(tmp_path) -> None:
    operator = _op(tmp_path)

    result = operator.create("nested/dir", is_directory=True)

    assert result["type"] == "directory"
    assert (tmp_path / "nested" / "dir").is_dir()


def test_delete_file(tmp_path) -> None:
    (tmp_path / "f.py").write_text("x\n", encoding="utf-8")
    operator = _op(tmp_path)

    assert operator.delete("f.py")["deleted"] is True
    assert not (tmp_path / "f.py").exists()


def test_delete_empty_directory(tmp_path) -> None:
    (tmp_path / "d").mkdir()
    operator = _op(tmp_path)

    assert operator.delete("d")["success"] is True
    assert not (tmp_path / "d").exists()


def test_delete_directory_recursive(tmp_path) -> None:
    (tmp_path / "d").mkdir()
    (tmp_path / "d" / "f.txt").write_text("x\n", encoding="utf-8")
    operator = _op(tmp_path)

    assert operator.delete("d", recursive=True)["success"] is True
    assert not (tmp_path / "d").exists()


def test_move_file(tmp_path) -> None:
    (tmp_path / "a.py").write_text("x\n", encoding="utf-8")
    operator = _op(tmp_path)

    result = operator.move("a.py", "sub/b.py")

    assert result["destination"] == "sub/b.py"
    assert (tmp_path / "sub" / "b.py").read_text(encoding="utf-8") == "x\n"


def test_move_existing_destination_raises(tmp_path) -> None:
    (tmp_path / "a.py").write_text("x\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("y\n", encoding="utf-8")
    operator = _op(tmp_path)

    with pytest.raises(FileExistsError, match="目标路径已存在"):
        operator.move("a.py", "b.py")


def test_copy_file_and_directory(tmp_path) -> None:
    (tmp_path / "a.py").write_text("x\n", encoding="utf-8")
    (tmp_path / "srcdir").mkdir()
    (tmp_path / "srcdir" / "f.txt").write_text("y\n", encoding="utf-8")
    operator = _op(tmp_path)

    file_result = operator.copy("a.py", "sub/a.py")
    dir_result = operator.copy("srcdir", "dst")

    assert file_result["size"] == 2
    assert dir_result["success"] is True
    assert (tmp_path / "dst" / "f.txt").read_text(encoding="utf-8") == "y\n"


def test_copy_invalid_source_raises(tmp_path) -> None:
    operator = _op(tmp_path)

    with pytest.raises(FileNotFoundError):
        operator.copy("missing.py", "dst.py")


# ---------------------------------------------------------------------------
# list_dir
# ---------------------------------------------------------------------------


def test_list_dir_rejects_file(tmp_path) -> None:
    (tmp_path / "f.py").write_text("x\n", encoding="utf-8")
    operator = _op(tmp_path)

    with pytest.raises(NotADirectoryError, match="不是目录"):
        operator.list_dir("f.py")


def test_list_dir_recursive_and_pattern(tmp_path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("x\n", encoding="utf-8")
    (tmp_path / "src" / "notes.txt").write_text("y\n", encoding="utf-8")
    operator = _op(tmp_path)

    recursive = operator.list_dir(".", recursive=True)
    filtered = operator.list_dir(".", recursive=True, pattern=r".*\.py")

    assert recursive["count"] >= 3
    assert all(
        entry["name"].endswith(".py") for entry in filtered["entries"]
    )


def test_list_dir_skips_skipped_entries(tmp_path) -> None:
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "dep.js").write_text("x\n", encoding="utf-8")
    (tmp_path / "keep.py").write_text("x\n", encoding="utf-8")
    operator = _op(tmp_path)

    result = operator.list_dir(".")

    names = {entry["name"] for entry in result["entries"]}
    assert "keep.py" in names
    assert "node_modules" not in names


def test_list_dir_permission_error_is_swallowed(tmp_path, monkeypatch) -> None:
    operator = _op(tmp_path)

    def boom(self):
        raise PermissionError()

    monkeypatch.setattr(Path, "iterdir", boom)

    result = operator.list_dir(".")

    assert result["entries"] == []


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------


def test_search_invalid_regex_raises(tmp_path) -> None:
    operator = _op(tmp_path)

    with pytest.raises(ValueError, match="无效的正则表达式"):
        operator.search("(")


def test_search_skips_name_that_does_not_match(tmp_path) -> None:
    (tmp_path / "a.py").write_text("needle\n", encoding="utf-8")
    operator = _op(tmp_path)

    result = operator.search("needle", file_pattern=r".*\.js$")

    assert result["matches_found"] == 0
    assert result["files_searched"] == 0


def test_search_finds_matches_and_respects_max(tmp_path) -> None:
    (tmp_path / "a.txt").write_text("needle\nneedle\nneedle\n", encoding="utf-8")
    operator = _op(tmp_path)

    result = operator.search("needle", max_results=1)

    assert result["matches_found"] == 1
    assert result["results"][0]["match"] == "needle"


def test_search_skips_oversized_file(tmp_path, monkeypatch) -> None:
    (tmp_path / "big.txt").write_text("needle\n", encoding="utf-8")
    operator = _op(tmp_path)

    real_stat = Path.stat

    def fake_stat(self, *args, **kwargs):
        result = real_stat(self, *args, **kwargs)
        if self.name == "big.txt":
            class _S:
                st_size = 11 * 1024 * 1024
                st_mode = result.st_mode
            return _S()
        return result

    monkeypatch.setattr(Path, "stat", fake_stat)

    result = operator.search("needle")

    assert result["matches_found"] == 0


def test_search_ignores_oserror(tmp_path, monkeypatch) -> None:
    (tmp_path / "a.txt").write_text("needle\n", encoding="utf-8")
    operator = _op(tmp_path)

    real_open = open

    def fake_open(path, *args, **kwargs):
        if str(path).endswith("a.txt"):
            raise OSError("cannot read")
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr("builtins.open", fake_open)

    result = operator.search("needle")

    assert result["matches_found"] == 0


def test_search_case_insensitive(tmp_path) -> None:
    (tmp_path / "a.txt").write_text("NEEDLE\n", encoding="utf-8")
    operator = _op(tmp_path)

    result = operator.search("needle", case_sensitive=False)

    assert result["matches_found"] == 1


# ---------------------------------------------------------------------------
# grep
# ---------------------------------------------------------------------------


def test_grep_filters_by_file_type(tmp_path) -> None:
    (tmp_path / "a.py").write_text("needle\n", encoding="utf-8")
    (tmp_path / "b.txt").write_text("needle\n", encoding="utf-8")
    operator = _op(tmp_path)

    result = operator.grep("needle", file_types=".py")

    assert result["matched_files"] == 1


def test_grep_no_match_does_not_append(tmp_path) -> None:
    (tmp_path / "a.py").write_text("other\n", encoding="utf-8")
    operator = _op(tmp_path)

    result = operator.grep("needle")

    assert result["matched_files"] == 0
    assert result["files_searched"] == 1


def test_grep_preview_caps_at_five_lines(tmp_path) -> None:
    (tmp_path / "a.py").write_text("needle\n" * 8, encoding="utf-8")
    operator = _op(tmp_path)

    result = operator.grep("needle")

    assert len(result["results"][0]["preview"]) == 5
    assert result["results"][0]["total_matches"] == 8


def test_grep_ignores_oserror(tmp_path, monkeypatch) -> None:
    (tmp_path / "a.py").write_text("needle\n", encoding="utf-8")
    operator = _op(tmp_path)

    def boom(self, *args, **kwargs):
        raise OSError("unreadable")

    monkeypatch.setattr(Path, "read_text", boom)

    result = operator.grep("needle")

    assert result["matched_files"] == 0


def test_grep_stops_after_fifty_files(tmp_path) -> None:
    for index in range(55):
        (tmp_path / f"f{index}.py").write_text("needle\n", encoding="utf-8")
    operator = _op(tmp_path)

    result = operator.grep("needle")

    assert result["matched_files"] == 50


def test_grep_case_insensitive(tmp_path) -> None:
    (tmp_path / "a.py").write_text("NEEDLE\n", encoding="utf-8")
    operator = _op(tmp_path)

    result = operator.grep("needle", case_sensitive=False)

    assert result["matched_files"] == 1


# ---------------------------------------------------------------------------
# tree
# ---------------------------------------------------------------------------


def test_tree_respects_max_depth(tmp_path) -> None:
    deep = tmp_path / "a" / "b" / "c"
    deep.mkdir(parents=True)
    (deep / "f.txt").write_text("x\n", encoding="utf-8")
    operator = _op(tmp_path)

    result = operator.tree(".", max_depth=1)

    assert result["tree"]["children"]
    assert "children" not in result["tree"]["children"][0]


def test_tree_skips_skipped_entries(tmp_path) -> None:
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "keep").mkdir()
    operator = _op(tmp_path)

    result = operator.tree(".")

    names = {child["name"] for child in result["tree"]["children"]}
    assert "node_modules" not in names
    assert "keep" in names


def test_tree_permission_error_is_swallowed(tmp_path, monkeypatch) -> None:
    operator = _op(tmp_path)

    def boom(self):
        raise PermissionError()

    monkeypatch.setattr(Path, "iterdir", boom)

    result = operator.tree(".")

    assert result["tree"]["children"] == []


# ---------------------------------------------------------------------------
# stats
# ---------------------------------------------------------------------------


def test_stats_counts_no_extension_files(tmp_path) -> None:
    (tmp_path / "Makefile").write_text("a\nb\n", encoding="utf-8")
    operator = _op(tmp_path)

    result = operator.stats(".")

    assert result["by_extension"]["(no extension)"]["count"] == 1
    assert result["total_lines"] == 2


def test_stats_ignores_ioerror(tmp_path, monkeypatch) -> None:
    (tmp_path / "a.txt").write_text("a\n", encoding="utf-8")
    operator = _op(tmp_path)

    real_open = open

    def fake_open(path, *args, **kwargs):
        if str(path).endswith("a.txt"):
            raise OSError("cannot read")
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr("builtins.open", fake_open)

    result = operator.stats(".")

    assert result["total_files"] == 1
    assert result["total_lines"] == 0


# ---------------------------------------------------------------------------
# async wrappers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_async_wrappers_delegate(tmp_path) -> None:
    (tmp_path / "a.py").write_text("needle\n", encoding="utf-8")
    operator = _op(tmp_path)

    read = await operator.read_async("a.py")
    written = await operator.write_async("b.py", "x = 1\n")
    listed = await operator.list_dir_async(".")
    searched = await operator.search_async("needle")

    assert read["content"] == "needle\n"
    assert written["success"] is True
    assert listed["count"] >= 2
    assert searched["matches_found"] == 1
