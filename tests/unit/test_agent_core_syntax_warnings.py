"""`agent_core.CodeValidator._check_syntax_warnings` 循环变量误报回归。

原实现对每个 `for` 循环无条件追加「循环变量 X 可能未使用」，即使变量在
循环体中被正常读取，也产生全量误报。修复后仅在循环体（含 else 子句）
确实未读取该名字时才提示。
"""
import ast

from app.utils.agent_core import CodeValidator


def _warnings(source: str):
    # _check_syntax_warnings 不使用实例状态，绕过 __init__ 的 pip 探测
    validator = object.__new__(CodeValidator)
    return validator._check_syntax_warnings(ast.parse(source))


def test_used_loop_variable_does_not_warn():
    assert _warnings("for i in range(3):\n    print(i)\n") == []


def test_loop_variable_used_in_else_does_not_warn():
    assert _warnings("for i in range(3):\n    pass\nelse:\n    print(i)\n") == []


def test_unused_loop_variable_still_warns():
    warnings = _warnings("for i in range(3):\n    pass\n")
    assert any("循环变量 i" in w for w in warnings)
