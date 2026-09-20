"""架构约束：包 ``__all__`` 声明的符号必须真的能从该包导入。

``__all__`` 是对外契约。若某个名字只写进 ``__all__`` 而缺少对应的 import，
``from pkg import name`` 会 ImportError，``from pkg import *`` 会 AttributeError，
但只有真正有人这样用的时候才暴露。若门禁测试从子模块直接导入，就会绕开包出口，
缺陷可以长期潜伏（历史上 ``orchestration`` 包漏导 ``DEFAULT_ENGINE`` 即此类）。
这里遍历全部包，直接校验出口本身。
"""

import importlib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = REPO_ROOT / "app"


def _package_name(path: Path) -> str:
    parts = list(path.relative_to(REPO_ROOT).with_suffix("").parts)
    # 去掉末尾的 __init__
    return ".".join(parts[:-1])


def _packages() -> list[str]:
    names = []
    for path in APP_ROOT.rglob("__init__.py"):
        if "__pycache__" in path.parts:
            continue
        names.append(_package_name(path))
    return sorted(names)


def test_declared_exports_are_importable():
    problems = []
    for name in _packages():
        module = importlib.import_module(name)
        declared = getattr(module, "__all__", None)
        if not declared:
            continue
        missing = [symbol for symbol in declared if not hasattr(module, symbol)]
        if missing:
            problems.append(f"{name}: {missing}")
    assert not problems, "包的 __all__ 声明了无法导入的符号: " + "; ".join(problems)
