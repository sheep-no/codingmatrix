"""写工具白名单必须覆盖全部落盘路径，而不只是 write_file。"""

import pytest

from app.agent import tools


@pytest.fixture(autouse=True)
def _reset_whitelist():
    tools.set_allowed_file_paths(None)
    yield
    tools.set_allowed_file_paths(None)


@pytest.fixture
def project(tmp_path):
    (tmp_path / "allowed.py").write_text("def greet():\n    return 'hi'\n", encoding="utf-8")
    (tmp_path / "blocked.py").write_text("def greet():\n    return 'hi'\n", encoding="utf-8")
    tools.set_allowed_file_paths({"allowed.py"})
    return tmp_path


def test_partial_update_rejects_path_outside_whitelist(project):
    result = tools._tool_partial_update(
        str(project), "blocked.py", function_name="greet", replacement="def greet():\n    return 'pwned'\n"
    )

    assert result["success"] is False
    assert "不在依赖图" in result["error"]
    assert "pwned" not in (project / "blocked.py").read_text(encoding="utf-8")


def test_insert_content_rejects_path_outside_whitelist(project):
    result = tools._tool_insert_content(str(project), "blocked.py", "INJECTED = 1\n")

    assert result["success"] is False
    assert "INJECTED" not in (project / "blocked.py").read_text(encoding="utf-8")


def test_regex_replace_rejects_path_outside_whitelist(project):
    result = tools._tool_regex_replace(str(project), "blocked.py", r"hi", "pwned")

    assert result["success"] is False
    assert "pwned" not in (project / "blocked.py").read_text(encoding="utf-8")


def test_regex_replace_glob_only_touches_whitelisted_files(project):
    result = tools._tool_regex_replace(str(project), "*.py", r"hi", "pwned")

    assert result["success"] is True
    assert result["files_modified"] == 1
    assert "pwned" in (project / "allowed.py").read_text(encoding="utf-8")
    assert "pwned" not in (project / "blocked.py").read_text(encoding="utf-8")


def test_delete_files_by_pattern_rejects_outside_whitelist(project):
    result = tools._tool_delete_files_by_pattern(str(project), ".", "blocked.py")

    assert result["success"] is False
    assert (project / "blocked.py").exists()


def test_write_paths_still_allowed_inside_whitelist(project):
    result = tools._tool_partial_update(
        str(project), "allowed.py", function_name="greet", replacement="def greet():\n    return 'updated'\n"
    )

    assert result["success"] is True
    assert "updated" in (project / "allowed.py").read_text(encoding="utf-8")


def test_whitelist_unset_allows_any_write(project):
    tools.set_allowed_file_paths(None)

    result = tools._tool_regex_replace(str(project), "blocked.py", r"hi", "free")

    assert result["success"] is True
    assert "free" in (project / "blocked.py").read_text(encoding="utf-8")
