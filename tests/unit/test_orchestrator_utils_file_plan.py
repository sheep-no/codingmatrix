"""UtilsMixin._validate_file_plan 路径校验测试（OU2 回归防线）。"""

import pytest

from app.agent.orchestrator_utils import UtilsMixin


class _Host(UtilsMixin):
    """仅提供 _validate_file_plan 所需宿主属性的最小宿主。"""

    def __init__(self):
        self.warnings = []


def _validate(paths):
    host = _Host()
    plan = [{"path": p} for p in paths]
    return host, host._validate_file_plan(plan)


def test_utf8_chinese_path_is_accepted() -> None:
    host, valid = _validate(["src/模块/工具.py"])
    assert [f["path"] for f in valid] == ["src/模块/工具.py"]
    assert host.warnings == []


def test_backslash_path_is_normalized() -> None:
    host, valid = _validate(["src\\utils\\helper.py"])
    assert [f["path"] for f in valid] == ["src/utils/helper.py"]
    assert host.warnings == []


def test_leading_slash_is_stripped() -> None:
    _, valid = _validate(["/app/main.py"])
    assert [f["path"] for f in valid] == ["app/main.py"]


def test_path_traversal_is_rejected() -> None:
    host = _Host()
    with pytest.raises(ValueError):
        host._validate_file_plan([{"path": "../secret.py"}])
    assert any("非法路径" in w for w in host.warnings)


def test_illegal_char_is_still_rejected() -> None:
    host = _Host()
    with pytest.raises(ValueError):
        host._validate_file_plan([{"path": "a b.py"}])
    assert any("非法路径" in w for w in host.warnings)


def test_too_deep_path_is_rejected() -> None:
    host = _Host()
    with pytest.raises(ValueError):
        host._validate_file_plan([{"path": "a/b/c/d/e/f/g.py"}])
    assert any("过深路径" in w for w in host.warnings)
