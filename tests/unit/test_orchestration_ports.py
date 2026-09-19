"""架构约束：适配器只通过端口访问引擎，agent 层不依赖 Web 层。

这三条约束曾经被破坏：适配器直接调用引擎私有方法、引擎反向导入 Web 层、
适配器使用未在契约中声明的成员。把它们固化为测试，避免修复后回流。
"""

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
APP = REPO_ROOT / "app"
ADAPTERS = APP / "agent" / "orchestration" / "adapters.py"
PORTS = APP / "agent" / "orchestration" / "ports.py"


def _is_self_agent(node):
    """判断节点是否是 self.agent 这个属性链。"""
    return (
        isinstance(node, ast.Attribute)
        and node.attr == "agent"
        and isinstance(node.value, ast.Name)
        and node.value.id == "self"
    )


def _self_agent_member(node):
    """返回 self.agent.<name> 中的 <name>，否则 None。"""
    if isinstance(node, ast.Attribute) and _is_self_agent(node.value):
        return node.attr
    return None


def _getattr_self_agent_member(node):
    """返回 getattr(self.agent, "<name>") 中的 <name>，否则 None。"""
    if not isinstance(node, ast.Call):
        return None
    func = node.func
    if not (isinstance(func, ast.Name) and func.id == "getattr"):
        return None
    if len(node.args) < 2 or not _is_self_agent(node.args[0]):
        return None
    name_arg = node.args[1]
    if isinstance(name_arg, ast.Constant) and isinstance(name_arg.value, str):
        return name_arg.value
    return None


def _adapter_engine_members(path):
    """适配器通过 self.agent 访问到的全部成员名。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    members = set()
    for node in ast.walk(tree):
        name = _self_agent_member(node)
        if name is None:
            name = _getattr_self_agent_member(node)
        if name is not None:
            members.add(name)
    return members


def _declared_port_members(path, class_name):
    """GenerationAgentPort 声明的成员名（注解属性与方法）。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            members = set()
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    members.add(item.name)
                elif isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                    members.add(item.target.id)
            return members
    raise AssertionError(class_name + " not found in " + str(path))


def test_adapter_never_calls_private_engine_members():
    offenders = sorted(
        name for name in _adapter_engine_members(ADAPTERS) if name.startswith("_")
    )
    assert not offenders, (
        "编排适配器直接访问了引擎私有成员，请改为 GenerationAgentPort 契约方法："
        + str(offenders)
    )


def test_adapter_engine_members_are_declared_on_the_port():
    used = _adapter_engine_members(ADAPTERS)
    declared = _declared_port_members(PORTS, "GenerationAgentPort")
    undeclared = sorted(used - declared)
    assert not undeclared, (
        "适配器使用了未在 GenerationAgentPort 中声明的成员："
        + str(undeclared)
        + "；请在 ports.py 补齐契约。"
    )


def test_agent_layer_does_not_import_the_web_layer():
    offenders = []
    for path in (APP / "agent").rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        relative = path.relative_to(REPO_ROOT).as_posix()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("app.api"):
                        offenders.append(relative + ":" + alias.name)
            elif (
                isinstance(node, ast.ImportFrom)
                and not node.level
                and (node.module or "").startswith("app.api")
            ):
                offenders.append(relative + ":" + node.module)
    assert not offenders, (
        "agent 层反向依赖 Web 层，请把共享内容下沉到 core/services：" + str(offenders)
    )
