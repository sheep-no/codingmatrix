"""GraphValidator 回归测试（GV3：节点 ID 唯一性检查去 O(N^2)）"""
from app.schema.workflow import TaskGraph, TaskNode, TaskType
from app.utils.workflow.graph_validator import GraphValidator


def _node(node_id, depends_on=None):
    return TaskNode(
        id=node_id,
        type=TaskType.LLM_CALL,
        params={"prompt": "hi"},
        depends_on=depends_on or [],
    )


class TestNodeIdUniqueness:

    def test_duplicate_node_ids_reported(self):
        graph = TaskGraph(
            workflow_id="w1",
            nodes=[_node("a"), _node("b"), _node("a"), _node("b"), _node("a")],
        )

        valid, errors = GraphValidator().validate(graph)

        assert valid is False
        message = " ".join(errors)
        assert "Duplicate node ID" in message
        assert "'a'" in message
        assert "'b'" in message

    def test_unique_node_ids_pass(self):
        nodes = [
            _node(f"n{i}", depends_on=[f"n{i - 1}"] if i else [])
            for i in range(500)
        ]

        valid, errors = GraphValidator().validate(
            TaskGraph(workflow_id="w2", nodes=nodes)
        )

        assert valid is True
        assert errors == []
