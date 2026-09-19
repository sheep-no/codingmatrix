"""声明能力必须有生产消费方，或显式登记为实验性。

竞品对比报告的核心结论是「已经建成的能力零消费」，容易被当作已完成能力。
本测试把登记表变成契约：``wired`` 必须有非测试调用点，``experimental``
必须确实零消费，接线后需同步更新登记表。

判定只看真实代码引用：``import`` / ``from ... import`` 语句不算消费方，
因为它们可能只是未使用的导出；定义模块与各包 ``__init__.py`` 的再导出
同样不算。
"""

import ast
from collections import defaultdict
from pathlib import Path

import pytest

from app.agent.capability_registry import DECLARED_CAPABILITIES

PRODUCTION_ROOT = Path(__file__).resolve().parents[2] / "app"


def _identifier_uses(path: Path) -> set[str]:
    """返回文件里被实际使用（非导入语句）的标识符。"""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return set()
    used: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        if isinstance(node, ast.Name):
            used.add(node.id)
        elif isinstance(node, ast.Attribute):
            used.add(node.attr)
    return used


@pytest.fixture(scope="module")
def production_symbol_index() -> dict[str, list[str]]:
    """一次性扫描生产代码，得到「标识符 -> 使用它的文件」索引。"""
    index: dict[str, list[str]] = defaultdict(list)
    for path in PRODUCTION_ROOT.rglob("*.py"):
        if "__pycache__" in path.parts or path.name == "__init__.py":
            continue
        relative = path.relative_to(PRODUCTION_ROOT.parent).as_posix()
        for symbol in _identifier_uses(path):
            index[symbol].append(relative)
    return index


@pytest.mark.parametrize(
    "capability", DECLARED_CAPABILITIES, ids=lambda c: f"{c.status}:{c.name}"
)
def test_declared_capability_has_a_destination(capability, production_symbol_index):
    consumers = sorted(
        path
        for path in production_symbol_index.get(capability.name, [])
        if path != capability.module
    )

    if capability.status == "wired":
        assert consumers, (
            f"{capability.name} 登记为 wired，但生产代码里找不到非测试调用点。"
            "如已退役请改为 experimental 或从登记表移除。"
        )
    elif capability.status == "experimental":
        assert not consumers, (
            f"{capability.name} 已出现生产消费方 {consumers}，"
            "请把它在登记表中改为 wired。"
        )
    else:
        pytest.fail(f"{capability.name} 的 status 非法: {capability.status}")
