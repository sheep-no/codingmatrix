"""GraphValidator 回归测试。

覆盖 docs/evolution/modules/workflow_core.md 中核实的缺陷：
- GV3：节点 ID 唯一性检查由 O(N^2) 改为 Counter 单次遍历
- GV1：check_semantics=True 时校验节点 params 的必填项与取值
- GV4：图规模上限校验
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

        # 该用例关注唯一性而非规模上限，显式放宽上限以保留 500 节点构造
        valid, errors = GraphValidator(max_nodes=1000).validate(
            TaskGraph(workflow_id="w2", nodes=nodes)
        )

        assert valid is True
        assert errors == []


class TestGraphSizeLimit:
    """GV4：超大图应被拒绝，避免校验/调度资源耗尽"""

    def test_graph_over_limit_rejected(self):
        nodes = [_node(f"n{i}") for i in range(5)]

        valid, errors = GraphValidator(max_nodes=3).validate(
            TaskGraph(workflow_id="w6", nodes=nodes)
        )

        assert valid is False
        assert any("exceeding the limit" in err for err in errors)

    def test_graph_at_limit_passes(self):
        nodes = [_node(f"n{i}") for i in range(3)]

        valid, errors = GraphValidator(max_nodes=3).validate(
            TaskGraph(workflow_id="w7", nodes=nodes)
        )

        assert valid is True
        assert errors == []

    def test_default_limit_is_generous_for_real_graphs(self):
        nodes = [_node(f"n{i}") for i in range(50)]

        valid, errors = GraphValidator().validate(
            TaskGraph(workflow_id="w8", nodes=nodes)
        )

        assert valid is True


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
