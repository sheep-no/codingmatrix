# Agent 子系统架构复核

复核分支：`260919-review-agent-quality`（基线 `master@7790338`）
范围：`app/agent`、`app/agent/orchestration`、生成入口分层与状态归属。

## 核心判断

新的 `orchestration` 层在结构上是旧引擎之上的一层控制面，依赖方向朝内指向旧实现。
它被当作「新架构」，但它没有承担生成职责，也没有替代旧引擎。
由此派生出本仓库最主要的架构风险：同一职责存在两套并行实现，且新实现依赖旧实现。

## 一、依赖方向是反的

`orchestration/adapters.py` 是 core 的适配层，却直接读写被包装 agent 的私有成员，
共 12 处：

```
adapters.py:214   self.agent._initialize_components(...)
adapters.py:330   self.agent._generate_single_file(...)
adapters.py:349   self.agent._select_model_for_file(...)
adapters.py:672   self.agent._select_model_for_file(...)
adapters.py:770   self.agent._select_engineer(...)
adapters.py:771   self.agent._generate_file_with_model(...)
adapters.py:785   self.agent._generate_single_file(...)
adapters.py:848   self.agent._validate_content_syntax(...)
adapters.py:917   self.agent._initialize_components(...)
adapters.py:1099  self.agent._initialize_components_fast(...)
adapters.py:1131  self.agent._build_project_summary_from_graph(...)
adapters.py:1132  self.agent._analyze_changes_with_architect(...)
```

反向依赖（`runtime.py:87-88` 从外部写入适配器私有字段）同样存在：

```python
if hasattr(adapter, "_shared_context"):
    adapter._shared_context = context
```

这构成一个倒置的迁移边界：新层通过私有接口调用旧层。
旧层的内部重构会直接击穿新层，而新层的存在并不能降低旧层的复杂度。

另外 `agent` 反向依赖上层 Web 层，破坏了分层方向（4 处）：

```
app.agent.orchestrator      -> app.api.v1.ai_agent.project_config
app.agent.workflow_registry -> app.api.v1.agent_host
```

## 二、同一职责两套并行实现

| 职责 | 实现 A | 实现 B | 现状 |
| --- | --- | --- | --- |
| 生成 agent 基类 | `app/utils/agent_core.py`（2628 行） | `app/agent/orchestrator.py` + 6 mixin（约 10k 行，210 方法） | `/generate` 用 A，`/orchestrate` 与 `/modify` 用 B |
| 文件调度 | `app/agent/topology_scheduler.py`（`max_retries=2`） | `app/agent/orchestration/generation_scheduler.py`（`max_retries=2`） | 两者都做依赖序生成与重试；core 调度器再逐文件调回旧 agent |
| 任务状态 | `SharedContext`（`files` / `dependencies` / `phases`） | `OrchestrationState`（`metadata` / `diagnostics`） | 同一次运行同时存在 |
| 代码校验 | `app/agent/code_validator.py` | `app/utils/agent_core.py` 内另一份 | 两份并存 |
| 多角度审查 | `app/agent/multi_angle_review.py` | `app/utils/agent_skills.py` 内同步版 | 前者生产零引用 |

引擎分流由 `orchestration/routing.py` 决定，默认值是 legacy：

```python
value = (requested or os.getenv("AGENT_ORCHESTRATION_ENGINE", LEGACY_ENGINE)).strip().lower()
```

`/generate` 上的 `core_handler` 是直通实现，不经过 `OrchestratorCore`
（`generate_endpoints.py:91-93`）：

```python
async def run_core(_state):
    # The core route keeps the established generator behind the new boundary
    return await run_generate(_state)
```

于是 `engine_router.route_generation` 与 `compare_shadow_results` 这套影子对比能力，
在最大的一条生成入口上比较的是同一段逻辑。

## 三、状态权威缺失

同一次生成任务的状态分散在至少五处，且各自持久化：

| 载体 | 位置 | 现有文件量 |
| --- | --- | --- |
| 旧 agent 内存态 | `OrchestratorAgent._generated_contents` / `generated_files` | 进程内 |
| `SharedContext` | 内存对象，core 与适配器共享同一实例 | 进程内 |
| `OrchestrationState` | `data/orchestration_core_checkpoints/` | 430 |
| 旧检查点 | `data/agent_state_checkpoints/` | 1325 |
| Agent Host 会话 | `data/agent_host_sessions/` | 2063 |

`OrchestrationCheckpointStore` 每次只保留一份快照，且 schema 版本不匹配直接抛错，
没有迁移路径。核心问题是：没有单一权威状态，任何恢复、审计、并发控制
都需要同时对齐多个载体，这是竞态修复反复出现的结构性原因。

## 四、抽象没有闭环

`WorkflowIR` 被写入 `state.metadata`，下游只有 `runtime.py:_workflow_projection`
把它投影给 API。系统内部没有读取方，因此 IR 是「写出来给人看的」，
没有参与调度决策或恢复，不构成约束。

`capability_registry.py` 自身生产零引用，靠测试维持。它记录「哪些能力没接线」，
这是一份清单，不是一种约束：登记为 `experimental` 的模块依旧可以在主链外继续增长。

`app/agent` 175 个模块（不含 `__init__`）中，13 个生产零引用：

```
app.agent.synthesis_validation        app.agent.consistency_checker
app.agent.constrained_generation      app.agent.multi_angle_review
app.agent.multi_language_parser       app.agent.strategy_learner
app.agent.cloud_learning_hub          app.agent.user_preference_learner
app.agent.fix_pattern_cache           app.agent.evaluation_runner
app.agent.capability_registry         app.agent.orchestration.ir_projection
app.agent.framework_profiles.validation
```

`OrchestratorAgent` 用 6 个 mixin 拆成多文件，但拆的是文件而非职责：
类仍是 210 个方法、约 10k 行的单一实体，`_PlannedAgentAdapter` 又把它 20 多个方法
重新暴露一遍。继承被用来规避单文件长度，而不是建立稳定接口。

模块级双向依赖 5 组：

```
app.agent.dynamic_model_router <-> app.agent.models
app.agent.framework_profiles  <-> app.agent.framework_profiles.workspace
app.agent.workflow_registry   <-> app.api.v1.agent_host
app.api.v1.aiGeneratorPptx    <-> app.services.ppt_quality_orchestrator
app.api.v1.aiGeneratorPptx    <-> app.services.ppt_template_samples
```

## 五、这些结构造成的可观测后果

1. 修复无法在一个地方完成。同一个语义缺陷需要在 legacy agent、core 适配器、
   两套调度器之间同步，这正是近期 fix 提交密集且无收敛的机制来源
   （近 60 天 fix 186 / feat 85，90 天内无 revert）。
2. 新架构不承担主路径风险。默认引擎是 legacy，`/generate` 的 core 是直通，
   因此新层的正确性从未在真实流量下被验证，测试也只覆盖接线。
3. 并发与恢复问题的修复只能逐点加固。多份状态载体没有权威，
   `orchestration` 的检查点、旧检查点与 Host 会话各写一份，难以一次性收敛。

## 六、优先级建议

1. 反转依赖方向。为 core 定义生成端口接口，让适配器依赖端口，
   由旧 agent 去实现端口，消除 `adapters.py` 的 12 处私有调用与
   `runtime.py` 的私有字段写入。这是让新层真正成为架构边界的前提。
2. 选定单一默认引擎并让 core 承担主路径，legacy 只保留兼容入口。
   否则影子对比与引擎分流只会持续增加分支数量。
3. 合并调度与状态。一个调度器、一份权威任务状态，
   其余载体退化为投影或缓存。
4. 收敛 agent 基类。`/generate` 与 `/orchestrate` 应共用同一 agent 抽象，
   消除「两个类都叫 agent」的分裂。
5. 消解 `agent -> api` 反向依赖。把 `PROJECTS_BASE_DIR`、
   `agent_host` 这类上层产物下沉到领域层，或在装配点注入。

## 附录：复核命令

```bash
# 适配器跨越边界访问私有成员
grep -n 'self\.agent\._' app/agent/orchestration/adapters.py

# 默认引擎
grep -n 'LEGACY_ENGINE\|CORE_ENGINE' app/agent/orchestration/routing.py

# /generate 的 core 直通
sed -n '85,95p' app/api/v1/ai_agent/generate_endpoints.py

# 两套调度器
grep -n 'max_retries' app/agent/topology_scheduler.py app/agent/orchestration/generation_scheduler.py

# 状态载体文件量
for d in data/orchestration_core_checkpoints data/agent_state_checkpoints data/agent_host_sessions; do
  echo "$d: $(ls "$d" | wc -l)"
done

# agent 反向依赖上层
grep -rn 'from app.api' app/agent --include='*.py' | grep -v __pycache__
```
