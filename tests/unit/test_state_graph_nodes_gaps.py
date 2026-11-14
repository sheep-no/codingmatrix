"""Spec-first StateGraph 节点的类型守卫补测。"""

import pytest

from app.agent.nodes import dependency_graph_node, specification_node, topology_schedule_node
from app.agent.state import State


@pytest.mark.asyncio
async def test_specification_node_rejects_non_dict_result():
    with pytest.raises(TypeError, match="specification generator must return a dictionary"):
        await specification_node(State("s1", "t1"), lambda _state: ["not", "a", "dict"])


@pytest.mark.asyncio
async def test_dependency_graph_node_rejects_non_dict_result():
    with pytest.raises(TypeError, match="dependency graph builder must return a dictionary"):
        await dependency_graph_node(State("s1", "t1"), lambda _state: "graph")


@pytest.mark.asyncio
async def test_topology_schedule_node_rejects_non_dict_result():
    with pytest.raises(TypeError, match="topology scheduler must return a dictionary"):
        await topology_schedule_node(State("s1", "t1"), lambda _state: None)
