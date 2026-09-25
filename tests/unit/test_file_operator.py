"""FileOperator 路径安全规则回归。

覆盖已建档缺陷：
- FO1 PROTECTED_FILES 子串匹配误伤：".env" 命中任意含该子串的路径，
  导致 SAFE_EXTENSIONS 明确允许的 ".env.example" 模板被拒。
- FO7 grep/search 以 errors='ignore' 读取：含非法字节的文件内容被静默
  丢弃，搜索结果不完整且无任何提示。
"""

from pathlib import Path

import pytest

from app.utils.file_operator import FileOperator, PathSecurityError


def test_env_file_is_rejected():
    with pytest.raises(PathSecurityError):
        FileOperator()._validate_path("/srv/app/.env", must_exist=False)


def test_env_example_template_is_allowed():
    """SAFE_EXTENSIONS 白名单内的 .env.example 模板不应被敏感文件规则拦截。"""
    target = FileOperator()._validate_path("/srv/app/.env.example", must_exist=False)

    assert target.name == ".env.example"


def test_env_substring_path_is_not_misflagged():
    """路径含 ".env" 子串但文件名不同名时不应被误判为敏感文件。"""
    assert (
        FileOperator._is_protected_file(
            Path("/srv/app/.envrc"), "/srv/app/.envrc", ".env"
        )
        is False
    )
    assert (
        FileOperator._is_protected_file(
            Path("/srv/app/notes.env.bak"), "/srv/app/notes.env.bak", ".env"
        )
        is False
    )


def test_env_named_file_is_protected():
    assert (
        FileOperator._is_protected_file(
            Path("/srv/app/.env"), "/srv/app/.env", ".env"
        )
        is True
    )


def test_git_config_is_rejected():
    with pytest.raises(PathSecurityError):
        FileOperator()._validate_path("/srv/app/.git/config", must_exist=False)


def test_private_key_file_is_rejected():
    with pytest.raises(PathSecurityError):
        FileOperator()._validate_path("/srv/app/id_rsa", must_exist=False)


def test_git_config_substring_path_is_not_misflagged():
    """.git/config 按路径尾段匹配，普通 config 文件不受影响。"""
    assert (
        FileOperator._is_protected_file(
            Path("/srv/app/config"), "/srv/app/config", ".git/config"
        )
        is False
    )


def _make_undecodable(root: Path) -> Path:
    """写入含非法 UTF-8 字节的文本文件（内容中含可搜索的 ASCII 关键字）。"""
    bad = root / "broken.txt"
    bad.write_bytes("needle here\n".encode("utf-8") + b"\xff\xfe\x80 invalid\n")
    return bad


def test_grep_reports_undecodable_file(tmp_path):
    """FO7：grep 不应静默跳过无法解码的文件。"""
    _make_undecodable(tmp_path)
    operator = FileOperator(base_path=str(tmp_path), allow_protected_paths=True)

    result = operator.grep("needle", path=".")

    assert result["undecodable_files"] == ["broken.txt"]
    assert result["matched_files"] == 0


def test_search_reports_undecodable_file(tmp_path):
    """FO7：search 不应静默跳过无法解码的文件。"""
    _make_undecodable(tmp_path)
    operator = FileOperator(base_path=str(tmp_path), allow_protected_paths=True)

    result = operator.search("needle", path=".")

    assert result["undecodable_files"] == ["broken.txt"]
    assert result["matches_found"] == 0


def test_grep_reports_no_undecodable_for_valid_files(tmp_path):
    """FO7：正常 UTF-8 文件不进入 undecodable 列表。"""
    (tmp_path / "ok.txt").write_text("needle here\n", encoding="utf-8")
    operator = FileOperator(base_path=str(tmp_path), allow_protected_paths=True)

    result = operator.grep("needle", path=".")

    assert result["undecodable_files"] == []
    assert result["matched_files"] == 1
