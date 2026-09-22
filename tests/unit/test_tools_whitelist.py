"""依赖图写入白名单的任务隔离（T5）。"""

import asyncio

import pytest

from app.agent import tools


@pytest.fixture(autouse=True)
def _reset_whitelist():
    tools.set_allowed_file_paths(None)
    yield
    tools.set_allowed_file_paths(None)


def test_default_is_unset():
    tools.set_allowed_file_paths(None)
    assert tools._allowed_file_paths.get() is None


def test_set_and_clear():
    tools.set_allowed_file_paths({"a.py"})
    assert tools._allowed_file_paths.get() == frozenset({"a.py"})

    tools.set_allowed_file_paths(None)
    assert tools._allowed_file_paths.get() is None


def test_set_copies_input():
    source = {"a.py"}
    tools.set_allowed_file_paths(source)
    source.add("b.py")

    assert tools._allowed_file_paths.get() == frozenset({"a.py"})


@pytest.mark.asyncio
async def test_concurrent_tasks_are_isolated():
    barrier = asyncio.Barrier(2)
    seen = {}

    async def worker(name, paths):
        tools.set_allowed_file_paths(paths)
        # 两个任务都设置完再读，排除顺序执行造成的假象
        await barrier.wait()
        seen[name] = tools._allowed_file_paths.get()

    await asyncio.gather(
        asyncio.create_task(worker("a", {"a/main.py"})),
        asyncio.create_task(worker("b", {"b/main.py"})),
    )

    # 模块级全局时后设置者会覆盖前一个，两个任务读到同一集合
    assert seen["a"] == frozenset({"a/main.py"})
    assert seen["b"] == frozenset({"b/main.py"})


@pytest.mark.asyncio
async def test_child_task_inherits_parent_whitelist():
    tools.set_allowed_file_paths({"parent.py"})
    seen = {}

    async def child():
        seen["allowed"] = tools._allowed_file_paths.get()

    await asyncio.create_task(child())

    assert seen["allowed"] == frozenset({"parent.py"})


@pytest.mark.asyncio
async def test_child_set_does_not_leak_to_parent():
    tools.set_allowed_file_paths({"parent.py"})

    async def child():
        tools.set_allowed_file_paths({"child.py"})
        return tools._allowed_file_paths.get()

    assert await asyncio.create_task(child()) == frozenset({"child.py"})
    assert tools._allowed_file_paths.get() == frozenset({"parent.py"})
