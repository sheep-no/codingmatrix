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

REPO_ROOT = Path(__file__).resolve().parents[2]
PRODUCTION_ROOT = REPO_ROOT / "app"
AGENT_ROOT = PRODUCTION_ROOT / "agent"

# 门禁自身的数据文件：只被测试导入，不对应任何可复用能力，故豁免清单校验。
INVENTORY_EXEMPT_MODULES = {"app.agent.capability_registry"}


def _module_name(path: Path) -> str:
    """返回仓库内文件的点分模块名，``__init__.py`` 归入其包。"""
    parts = list(path.relative_to(REPO_ROOT).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _imported_names(path: Path) -> set[str]:
    """返回文件导入或属性访问引用的点分名字（含相对导入解析）。"""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return set()
    package = _module_name(path) if path.name == "__init__.py" else _module_name(path).rsplit(".", 1)[0]
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package.split(".") if package else []
                base = base[: len(base) - (node.level - 1)]
                target = ".".join([*base, node.module]) if node.module else ".".join(base)
            else:
                target = node.module or ""
            if target:
                names.add(target)
                for alias in node.names:
                    names.add(f"{target}.{alias.name}")
        elif isinstance(node, ast.Attribute):
            parts, current = [], node
            while isinstance(current, ast.Attribute):
                parts.append(current.attr)
                current = current.value
            if isinstance(current, ast.Name):
                parts.append(current.id)
                names.add(".".join(reversed(parts)))
    return names


@pytest.fixture(scope="module")
def agent_modules() -> dict[str, Path]:
    """app/agent 下所有非 ``__init__`` 模块的「点分名 -> 路径」。"""
    return {
        _module_name(path): path
        for path in AGENT_ROOT.rglob("*.py")
        if "__pycache__" not in path.parts and path.name != "__init__.py"
    }


@pytest.fixture(scope="module")
def zero_reference_modules(agent_modules) -> set[str]:
    """返回在 app/ 内没有任何导入或属性引用的 app/agent 模块。"""
    referenced: set[str] = set()
    for path in PRODUCTION_ROOT.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        source = _module_name(path)
        for name in _imported_names(path):
            for module in agent_modules:
                if module != source and (name == module or name.startswith(module + ".")):
                    referenced.add(module)
    return set(agent_modules) - referenced


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


def test_zero_reference_modules_are_declared(zero_reference_modules):
    """整模块无生产引用的 app/agent 模块必须出现在登记表中。

    登记表按「单符号」消费判定，会漏掉整模块零引用的情况（例如仅被单测
    维持的模块）。这里补一道整模块清单，避免此类能力静默累积。
    """
    declared = {
        capability.module[:-3].replace("/", ".")
        for capability in DECLARED_CAPABILITIES
        if capability.module.endswith(".py")
    }
    undeclared = sorted(zero_reference_modules - declared - INVENTORY_EXEMPT_MODULES)
    assert not undeclared, (
        f"以下 app/agent 模块无任何生产引用，但未登记在 DECLARED_CAPABILITIES 中：{undeclared}。"
        "请让其被生产代码调用，或在登记表中显式登记为 experimental。"
    )
