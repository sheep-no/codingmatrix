import pytest

from app.agent.workflow_ir import (
    ScopeRef,
    TechnologyProfile,
    ToolGrant,
    WorkflowIR,
    WorkflowNode,
    WorkflowNodeKind,
)
from app.agent.orchestration.budget import ExecutionBudget


def budget():
    return ExecutionBudget(task_seconds=60, stage_seconds=30, file_seconds=20, model_call_seconds=10)


def node(node_id, *, depends_on=()):
    return WorkflowNode(
        node_id=node_id,
        kind=WorkflowNodeKind.GENERATE,
        handler_ref="orchestration.generate",
        depends_on=depends_on,
    )


def make_workflow(nodes=(node("plan"), node("generate", depends_on=("plan",)))):
    return WorkflowIR.build(
        workflow_id="task-1",
        name="code-generation",
        mode="generate",
        entry_node="plan",
        nodes=nodes,
        budgets=budget(),
    )


def test_build_calculates_stable_digest_and_serializes():
    workflow = make_workflow()

    assert len(workflow.digest) == 64
    assert WorkflowIR.model_validate(workflow.model_dump(mode="json")) == workflow
    assert workflow.digest == make_workflow().digest


def test_rejects_missing_dependency():
    with pytest.raises(ValueError, match="missing dependencies"):
        make_workflow((node("plan"), node("generate", depends_on=("missing",))))


def test_rejects_cycle():
    with pytest.raises(ValueError, match="DAG"):
        make_workflow((node("plan", depends_on=("generate",)), node("generate", depends_on=("plan",))))


def test_rejects_unreachable_node():
    with pytest.raises(ValueError, match="reachable"):
        make_workflow((node("plan"), node("generate", depends_on=("plan",)), node("orphan")))


def test_execute_grant_requires_scope():
    with pytest.raises(ValueError, match="scope"):
        ToolGrant(tool="shell", capability="command", operations=("execute",))


def test_execute_grant_accepts_scoped_access():
    grant = ToolGrant(
        tool="shell",
        capability="command",
        operations=("execute",),
        scopes=(ScopeRef(kind="task", ref="task-1"),),
    )
    assert grant.scopes[0].ref == "task-1"


def test_symbol_contract_fields_are_language_neutral():
    workflow = WorkflowIR.build(
        workflow_id="task-1",
        name="polyglot-generation",
        mode="generate",
        language="rust",
        framework="axum",
        runtime="tokio",
        languages=("rust", "sql"),
        frameworks=("axum", "sqlx"),
        runtimes=("tokio", "postgres"),
        entry_node="plan",
        nodes=(
            WorkflowNode(
                node_id="plan",
                kind=WorkflowNodeKind.PLAN,
                handler_ref="orchestration.plan",
            ),
            WorkflowNode(
                node_id="file:service",
                kind=WorkflowNodeKind.GENERATE,
                handler_ref="orchestration.generate_file",
                depends_on=("plan",),
                provided_symbols=("Service",),
                required_symbols=("Repository",),
                required_fixtures=("service_client",),
                technology=TechnologyProfile(
                    language="rust",
                    framework="axum",
                    runtime="tokio",
                ),
            ),
        ),
        budgets=budget(),
    )

    assert workflow.nodes[1].required_symbols == ("Repository",)
    assert (workflow.language, workflow.framework, workflow.runtime) == ("rust", "axum", "tokio")
    assert workflow.languages == ("rust", "sql")


def test_rejects_node_technology_outside_declared_workflow_set():
    with pytest.raises(ValueError, match="outside the workflow technology set"):
        WorkflowIR.build(
            workflow_id="task-1",
            name="mixed-stack",
            mode="generate",
            language="go",
            languages=("go",),
            entry_node="plan",
            nodes=(
                WorkflowNode(
                    node_id="plan",
                    kind=WorkflowNodeKind.PLAN,
                    handler_ref="orchestration.plan",
                    technology=TechnologyProfile(language="java"),
                ),
            ),
            budgets=budget(),
        )
