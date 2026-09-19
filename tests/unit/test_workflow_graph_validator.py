"""GraphValidator 回归测试。

覆盖 docs/evolution/modules/workflow_core.md 中核实的缺陷：
- GV3：节点 ID 唯一性检查由 O(N^2) 改为 Counter 单次遍历
- GV1：check_semantics=True 时校验节点 params 的必填项与取值
"""
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


class TestSemanticValidation:
    """check_semantics=True 时按节点类型校验 params"""

    def test_missing_required_param_reported(self):
        graph = TaskGraph(
            workflow_id="w3",
            nodes=[TaskNode(id="s1", type=TaskType.WEB_SEARCH, params={})],
        )

        valid, errors = GraphValidator().validate(graph, check_semantics=True)

        assert valid is False
        assert any("Missing required parameter: query" in err for err in errors)

    def test_valid_params_pass(self):
        graph = TaskGraph(
            workflow_id="w4",
            nodes=[
                TaskNode(
                    id="s1",
                    type=TaskType.WEB_SEARCH,
                    params={"query": "python"},
                ),
                TaskNode(
                    id="c1",
                    type=TaskType.CODE_EXECUTION,
                    params={"code": "print(1)"},
                    depends_on=["s1"],
                ),
            ],
        )

        valid, errors = GraphValidator().validate(graph, check_semantics=True)

        assert valid is True
        assert errors == []

    def test_semantic_check_disabled_by_default(self):
        """默认保持纯结构校验契约，不因缺 params 而失败"""
        graph = TaskGraph(
            workflow_id="w5",
            nodes=[TaskNode(id="s1", type=TaskType.WEB_SEARCH, params={})],
        )

        valid, errors = GraphValidator().validate(graph)

        assert valid is True
        assert errors == []
