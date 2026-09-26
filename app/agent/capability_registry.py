"""已声明能力登记表。

竞品对比报告发现一批能力「已实现但零生产消费」，容易被误当成已完成能力。
本表为这些能力登记明确归宿：

- ``wired``：已被生产代码调用，测试会校验确实存在非测试调用点。
- ``experimental``：无生产消费，未接入默认路径；测试会校验它的确零消费，
  从而在有人接线时强制更新本表。

新增可复用模块或导出符号时，要么让它被生产代码调用，要么在此登记为
``experimental`` 并写明原因，避免未接线能力继续静默累积。

登记表同时是**整模块清单**：``tests/unit/test_capability_registry.py`` 会扫描
``app/agent``，要求每个没有任何生产引用的模块都在本表中有条目（或属于豁免项），
因此新增此类模块必须同步登记。
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class DeclaredCapability:
    """一项已声明能力的归宿。"""

    name: str
    module: str
    status: str
    rationale: str


DECLARED_CAPABILITIES: tuple[DeclaredCapability, ...] = (
    DeclaredCapability(
        name="MultiModelAgent",
        module="app/agent/multi_model_agent.py",
        status="experimental",
        rationale=(
            "五角色路由与全局信号量已实现，但生产代码只有导入与包导出，无调用点；"
            "多模型协同尚未接入主链路。"
        ),
    ),
    DeclaredCapability(
        name="ModelGateway",
        module="app/agent/orchestration/model_gateway.py",
        status="experimental",
        rationale=(
            "预算感知与取消感知的模型调用网关已实现并单测覆盖，但 Core 边界目前仍"
            "委托旧生成器执行模型调用，网关没有可包裹的生产调用点。"
        ),
    ),
    DeclaredCapability(
        name="register_recoverable_workflow_factory",
        module="app/agent/workflow_registry.py",
        status="experimental",
        rationale=(
            "跨进程恢复工厂注册入口无生产调用方；旧版单节点工作流经 checkpoint 恢复"
            "后不会重跑处理函数，暂不需要重建定义。"
        ),
    ),
    DeclaredCapability(
        name="CandidateValidationRouter",
        module="app/agent/synthesis_validation.py",
        status="experimental",
        rationale="V0-V6 分层候选验证最完整的验证设计未参与生成，仅单测引用。",
    ),
    DeclaredCapability(
        name="validate_model_operation_v0",
        module="app/agent/synthesis_validation.py",
        status="experimental",
        rationale="V0 模型操作校验为分层验证入口，无生产调用方。",
    ),
    DeclaredCapability(
        name="route_generation",
        module="app/agent/orchestration/engine_router.py",
        status="experimental",
        rationale=(
            "旧/新引擎分流与影子对比入口无生产调用方；端点分流目前由 "
            "build_legacy_workflow 的 core_handler 承担。"
        ),
    ),
    DeclaredCapability(
        name="compare_shadow_results",
        module="app/agent/orchestration/engine_router.py",
        status="experimental",
        rationale="影子结果对比只被路由入口使用，路由入口本身未接线。",
    ),
    DeclaredCapability(
        name="ContextAssembler",
        module="app/agent/context_assembler.py",
        status="wired",
        rationale="上下文装配已接在 Core 适配器与三条生成路径上。",
    ),
    DeclaredCapability(
        name="ExecutionBudget",
        module="app/agent/orchestration/budget.py",
        status="wired",
        rationale="四级预算已在调度层与网关中强制生效。",
    ),
    # 整模块无生产引用：以下模块没有任何生产代码导入或调用，仅由单测维持。
    # 它们由 capability-consumer-gate 门禁纳入清单，接线后需改为 wired。
    DeclaredCapability(
        name="CloudLearningHub",
        module="app/agent/cloud_learning_hub.py",
        status="experimental",
        rationale="云端模式学习中心整模块无生产引用，仅单测覆盖。",
    ),
    DeclaredCapability(
        name="ConsistencyChecker",
        module="app/agent/consistency_checker.py",
        status="experimental",
        rationale="跨文件 schema 漂移检查整模块无生产引用，仅单测覆盖。",
    ),
    DeclaredCapability(
        name="FastApiCrudRenderer",
        module="app/agent/constrained_generation.py",
        status="experimental",
        rationale="受约束的 FastAPI CRUD 渲染器整模块无生产引用，仅单测覆盖。",
    ),
    DeclaredCapability(
        name="build_report_from_file",
        module="app/agent/evaluation_runner.py",
        status="experimental",
        rationale="评估报告文件入口无生产引用，矩阵目前只经 tests/manual 运行。",
    ),
    DeclaredCapability(
        name="FixPatternCache",
        module="app/agent/fix_pattern_cache.py",
        status="experimental",
        rationale="修复模式缓存整模块无生产引用，仅单测覆盖。",
    ),
    DeclaredCapability(
        name="validation_targets_for_workflow",
        module="app/agent/framework_profiles/validation.py",
        status="experimental",
        rationale="工作流验证目标解析无生产引用，仅单测覆盖。",
    ),
    DeclaredCapability(
        name="parse_multi_review_response",
        module="app/agent/multi_angle_review.py",
        status="experimental",
        rationale="多角度审查解析整模块无生产引用，仅单测覆盖。",
    ),
    DeclaredCapability(
        name="project_change_plan",
        module="app/agent/orchestration/ir_projection.py",
        status="experimental",
        rationale="变更计划投影无生产引用，WorkflowIR 投影目前仍由 runtime 承担。",
    ),
    DeclaredCapability(
        name="StrategyLearner",
        module="app/agent/strategy_learner.py",
        status="experimental",
        rationale="策略学习器整模块无生产引用，仅单测覆盖。",
    ),
    DeclaredCapability(
        name="UserPreferenceLearner",
        module="app/agent/user_preference_learner.py",
        status="experimental",
        rationale="用户偏好学习器整模块无生产引用，仅单测覆盖。",
    ),
)
