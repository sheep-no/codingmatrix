"""架构约束：app 内不得存在模块级（导入期）循环依赖。

函数体内延迟导入是公开认可的断环手段，因此这里只统计模块顶层 import。
循环依赖会让导入顺序决定行为，并让包初始化变成隐式的两阶段过程。
"""

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = REPO_ROOT / "app"


def _module_name(path: Path, root: Path) -> str:
    parts = list(path.relative_to(root.parent).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _module_level_imports(path: Path, root: Path) -> set[str]:
    """模块顶层 import 的绝对模块名；忽略函数体内的延迟导入。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    module = _module_name(path, root)
    package = module if path.name == "__init__.py" else module.rsplit(".", 1)[0]
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package.split(".") if package else []
                base = base[: len(base) - (node.level - 1)]
                target = ".".join([*base, node.module]) if node.module else ".".join(base)
            else:
                target = node.module or ""
            if target:
                names.add(target)
    return names


def _resolve(imported: str, modules: dict[str, Path]) -> str | None:
    """把导入名收敛到实际存在的模块，去掉末尾的属性名。"""
    candidate = imported
    while candidate:
        if candidate in modules:
            return candidate
        if "." not in candidate:
            return None
        candidate = candidate.rsplit(".", 1)[0]
    return None


def _build_graph(root: Path) -> dict[str, set[str]]:
    modules = {
        _module_name(path, root): path
        for path in root.rglob("*.py")
        if "__pycache__" not in path.parts
    }
    graph: dict[str, set[str]] = {}
    for name, path in modules.items():
        dependencies = set()
        for imported in _module_level_imports(path, root):
            resolved = _resolve(imported, modules)
            if resolved is not None and resolved != name:
                dependencies.add(resolved)
        graph[name] = dependencies
    return graph


def _find_cycle(graph: dict[str, set[str]]) -> list[str]:
    WHITE, GREY, BLACK = 0, 1, 2
    color = {name: WHITE for name in graph}
    stack: list[str] = []

    def visit(node: str) -> list[str] | None:
        color[node] = GREY
        stack.append(node)
        for dependency in sorted(graph.get(node, ())):
            if color[dependency] == GREY:
                return stack[stack.index(dependency):] + [dependency]
            if color[dependency] == WHITE:
                found = visit(dependency)
                if found:
                    return found
        stack.pop()
        color[node] = BLACK
        return None

    for node in sorted(graph):
        if color[node] == WHITE:
            found = visit(node)
            if found:
                return found
    return []


def test_app_has_no_module_level_import_cycles():
    cycle = _find_cycle(_build_graph(APP_ROOT))
    assert not cycle, "存在模块级循环依赖: " + " -> ".join(cycle)
