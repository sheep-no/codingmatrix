"""TSK14/TSK15 回归：依赖图影响分析与测试映射的匹配语义。

- TSK14：``reverse_index`` 按被依赖文件精确匹配，禁止子串误命中。
- TSK15：测试映射模式支持 glob（``app/models/*.py``），并避免子串假阳性。
"""

import yaml

from app.tasks import code_tasks
from app.tasks.code_tasks import _find_affected_files, _get_related_tests


def test_find_affected_files_matches_exact_key_only():
    """短键不得通过子串命中其他文件（旧实现 ``target in file_path`` 会误加 b.py）。"""
    dep_graph = {
        "reverse_index": {
            "app/models/user.py": ["app/api/users.py"],
            "models": ["app/api/false_positive.py"],
        }
    }

    assert _find_affected_files(dep_graph, ["app/models/user.py"]) == ["app/api/users.py"]


def test_find_affected_files_normalizes_separators_and_dot_prefix():
    dep_graph = {"reverse_index": {"./app/models/user.py": ["app\\api\\users.py"]}}

    assert _find_affected_files(dep_graph, ["app/models/user.py"]) == ["app/api/users.py"]


def test_find_affected_files_excludes_targets():
    dep_graph = {
        "reverse_index": {
            "app/models/user.py": ["app/api/users.py", "app/models/user.py"]
        }
    }

    assert _find_affected_files(dep_graph, ["app/models/user.py"]) == ["app/api/users.py"]


def test_find_affected_files_empty_graph_returns_empty():
    assert _find_affected_files({}, ["app/models/user.py"]) == []
    assert _find_affected_files({"reverse_index": {}}, ["app/models/user.py"]) == []


def _write_map(tmp_path, mapping, global_tests=None):
    path = tmp_path / "file_to_test_map.yaml"
    path.write_text(
        yaml.safe_dump({"mapping": mapping, "global_tests": global_tests or []}),
        encoding="utf-8",
    )
    return path


def test_get_related_tests_matches_glob_pattern(tmp_path, monkeypatch):
    """旧实现 ``pattern.replace('*', '')`` 使 ``app/models/*.py`` 永不命中。"""
    path = _write_map(tmp_path, {"app/models/*.py": ["tests/unit/test_models.py"]})
    monkeypatch.setattr(code_tasks.settings, "FILE_TO_TEST_MAP_PATH", str(path))

    assert _get_related_tests(["app/models/user.py"]) == ["tests/unit/test_models.py"]


def test_get_related_tests_matches_exact_pattern(tmp_path, monkeypatch):
    path = _write_map(tmp_path, {"app/api/v1/auth.py": ["tests/unit/test_auth.py"]})
    monkeypatch.setattr(code_tasks.settings, "FILE_TO_TEST_MAP_PATH", str(path))

    assert _get_related_tests(["app/api/v1/auth.py"]) == ["tests/unit/test_auth.py"]


def test_get_related_tests_rejects_substring_false_positive(tmp_path, monkeypatch):
    """无扩展名的短模式不得子串命中 ``user_profile.py``。"""
    path = _write_map(tmp_path, {"app/models/user": ["tests/unit/test_user.py"]})
    monkeypatch.setattr(code_tasks.settings, "FILE_TO_TEST_MAP_PATH", str(path))

    assert _get_related_tests(["app/models/user_profile.py"]) == []


def test_get_related_tests_includes_global_tests(tmp_path, monkeypatch):
    path = _write_map(
        tmp_path,
        {"app/models/*.py": ["tests/unit/test_models.py"]},
        ["tests/unit/test_security.py"],
    )
    monkeypatch.setattr(code_tasks.settings, "FILE_TO_TEST_MAP_PATH", str(path))

    assert _get_related_tests(["app/models/user.py"]) == [
        "tests/unit/test_models.py",
        "tests/unit/test_security.py",
    ]
