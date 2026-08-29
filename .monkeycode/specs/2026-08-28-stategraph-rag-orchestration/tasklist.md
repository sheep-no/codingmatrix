# Implementation Task List

## Phase 1: Contracts

### SG-001 State and Message Schemas

- 状态：`completed`
- 优先级：`P0`
- 修改：`app/agent/state/models.py`、`app/agent/state/reducer.py`、`app/agent/state/__init__.py`、`tests/unit/test_agent_state.py`
- 消费：Agent adapters、SSE、WebSocket、checkpoint
- 契约：State、StateDelta、MessageEnvelope、ValidationResult
- 测试：`tests/unit/test_state_machine.py`、新增 schema/reducer tests
- 验证范围：`cloud_syntax` + `local_runtime`
- 验收标准：序列化、反序列化、幂等合并、revision 冲突均有自动化证据。
- 证据：`python3 -m compileall -q app/agent/state tests/unit/test_agent_state.py` 已通过；`python3 -m pytest tests/unit/test_agent_state.py tests/unit/test_state_machine.py -q` 通过（26/26）；当前全量单元测试通过（1690 passed、2 skipped）。

### SG-002 Checkpoint and Migration Readers

- 状态：`completed`
- 优先级：`P0`
- 修改：`app/agent/state/checkpoint.py`、`app/agent/state/migrations.py`、`tests/unit/test_state_checkpoint.py`
- 消费：`session_manager.py`、任务队列、插件适配器
- 契约：Checkpoint schema and schema_version
- 测试：新增 checkpoint round-trip tests
- 验证范围：`cloud_syntax` + `local_runtime`
- 验收标准：旧版本状态可确定性读取，重复恢复不会重复应用事件。
- 证据：`python3 -m compileall -q app/agent/state tests/unit/test_agent_state.py tests/unit/test_state_checkpoint.py` 已通过；`python3 -m pytest tests/unit/test_state_checkpoint.py -q` 通过（4/4），覆盖 round-trip、旧 payload 迁移、重复恢复幂等、版本拒绝和路径校验；全量单元测试通过（1690 passed、2 skipped）。

## Phase 2: Retrieval and Adapters

### SG-003 Unified Retrieval Interface

- 状态：`completed`
- 优先级：`P1`
- 修改：`app/agent/retrieval/models.py`、`app/agent/retrieval/service.py`、`app/agent/retrieval/__init__.py`、`tests/unit/test_retrieval_service.py`
- 消费：Spec-first、ReAct、review、validation nodes
- 契约：RetrievalRequest、RetrievalChunk、RetrievalResult
- 测试：新增 source provenance、deduplication、degraded mode tests
- 验证范围：`cloud_syntax` + `local_runtime`
- 验收标准：五类知识来源通过统一接口返回可追溯结果。
- 证据：`python3 -m compileall -q app/agent/retrieval tests/unit/test_retrieval_service.py` 已通过；`python3 -m pytest tests/unit/test_retrieval_service.py -q` 通过（6/6），覆盖来源溯源、hash 去重、排序限制、scope/source 过滤、同步异步来源和降级模式；全量单元测试通过（1693 passed、2 skipped）。现有知识源通过 `CallableRetriever` 逐步接入，业务入口接线归入 SG-004/后续节点迁移。

### SG-004 Legacy Endpoint Adapters

- 状态：`completed`
- 优先级：`P1`
- 修改：`app/agent/adapters/legacy_agent_adapter.py`、`app/agent/adapters/spec_first_adapter.py`、`app/agent/adapters/event_adapter.py`、`app/agent/adapters/__init__.py`、`tests/unit/test_agent_adapters.py`
- 消费：三个 Agent API 入口、现有进度事件出口
- 契约：StateDelta、MessageEnvelope
- 测试：现有 Agent endpoint tests、新增 adapter tests
- 验证范围：`cloud_syntax` + `local_runtime`
- 验收标准：旧入口结果具备统一 status、artifacts、messages 和 errors。
- 证据：`python3 -m compileall -q app/agent/adapters tests/unit/test_agent_adapters.py` 已通过；`python3 -m pytest tests/unit/test_agent_adapters.py tests/unit/test_workflow_registry.py tests/unit/test_state_graph_runtime.py tests/unit/test_state_graph_nodes.py -q` 通过（11/11），覆盖旧 Agent 结果、文件/验证/错误映射、进度事件 Envelope、Spec-first 阶段产物和 legacy workflow 入口保留原响应；全量单元测试通过（1693 passed、2 skipped）。

## Phase 3: Graph Execution

### SG-005 Minimal StateGraph Runtime

- 状态：`completed`
- 优先级：`P0`
- 修改：`app/agent/state/graph.py`、`app/agent/state/__init__.py`、`tests/unit/test_state_graph_runtime.py`
- 消费：所有 graph nodes
- 契约：GraphNode、StateReducer、conditional route
- 测试：新增 sequential、conditional、retry、conflict tests
- 验证范围：`cloud_syntax` + `local_runtime`
- 验收标准：节点快照读取、增量返回、统一合并、失败路由具备测试证据。
- 证据：`python3 -m compileall -q app/agent/state tests/unit/test_state_graph_runtime.py` 已通过；`python3 -m pytest tests/unit/test_state_graph_runtime.py -q` 通过（6/6），覆盖顺序节点、条件路由、失败恢复、快照隔离、revision 冲突和 max_steps 保护；全量单元测试通过（1696 passed、2 skipped）。

### SG-006 Spec-first and Topology Nodes

- 状态：`completed`
- 优先级：`P1`
- 修改：`app/agent/nodes/specification.py`、`app/agent/nodes/dependency_graph.py`、`app/agent/nodes/topology.py`、`app/agent/nodes/_utils.py`、`tests/unit/test_state_graph_nodes.py`
- 消费：`spec_first_generate.py`、`topology_scheduler.py`、validators
- 契约：graph artifact、generation layer、node status
- 测试：`tests/unit/test_dependency_graph.py`、`test_spec_first_generator.py`、新增 mapping tests
- 验证范围：`cloud_syntax` + `local_runtime`
- 验收标准：规范、依赖、拓扑、生成和验证共享同一 State revision。
- 证据：阶段节点记录 artifact hash、依赖图节点/邻接/反向邻接/语言适配决策、拓扑层/节点状态/跳过原因和 cycle diagnostics；`python3 -m pytest tests/unit/test_state_graph_nodes.py tests/unit/test_dependency_graph.py tests/unit/test_spec_first_generator.py -q` 通过（17/17），覆盖同步异步处理和共享输入 revision；`python3 -m compileall -q app/agent/state app/agent/retrieval app/agent/adapters app/agent/nodes app/agent/local_validation_adapter.py app/agent/workflow_registry.py` 已通过；全量单元测试通过（1697 passed、2 skipped）。

### SG-007 Validation and Local Action Nodes

- 状态：`waiting_local_validation`
- 优先级：`P1`
- 修改：`app/agent/nodes/validation.py`、`app/agent/local_validation_adapter.py`、`tests/unit/test_validation_nodes.py`、`tests/unit/test_local_validation_adapter.py`
- 消费：`code_validator.py`、`integrity_validator.py`、VS Code 插件
- 契约：ValidationResult、PendingAction、validation scope
- 测试：云端验证和待本地验证状态测试；插件 E2E 待实现
- 验证范围：`cloud_syntax` + `local_runtime` + `local_e2e`
- 验收标准：云端结果不会将本地依赖、构建或 E2E 标记为完成。
- 证据：云端结果强制 `source=cloud` 与 `scope=cloud_syntax`，按 State 中的必需本地 scope 创建待执行动作；插件结果校验 task、revision、schema version 和本地 scope，并按 scope 保留未完成动作；验证相关测试通过（10/10 专项测试，包含云端边界、本地 scope、身份校验和终态推导）。

## Phase 4: Incremental Cutover

### SG-008 Event and Session Cutover

- 状态：`waiting_local_validation`
- 优先级：`P1`
- 修改：`app/agent/adapters/event_adapter.py`、`app/agent/adapters/session_adapter.py`、`tests/unit/test_workflow_registry.py`
- 消费：前端、VS Code 插件、任务队列
- 契约：MessageEnvelope、Checkpoint
- 测试：现有 SSE passthrough、session tests、新增 replay tests
- 验证范围：`cloud_syntax` + `local_runtime` + `local_e2e`
- 验收标准：旧事件和新 Envelope 在迁移期间可关联到同一 task/revision。
- 证据：旧事件已支持 Envelope 转换，session summary 和 sequence replay 已提供；新增序列缺口检测和 snapshot recovery action；同步/流式入口均保留原事件出口，相关测试通过（157/157 本轮相关测试）；插件 E2E 验证仍待完成。

### SG-009 Full Entry Migration Gate

- 状态：`waiting_local_validation`
- 优先级：`P2`
- 修改：`app/agent/workflow_registry.py`、`tests/unit/test_workflow_registry.py`
- 消费：全部 Agent API consumers
- 契约：workflow registry、terminal status policy
- 测试：全量 Agent API、回归和本地 E2E
- 验证范围：`cloud_syntax` + `local_runtime` + `local_e2e`
- 验收标准：所有入口的状态、消息、验证范围和错误恢复可回放。
- 证据：已提供命名 workflow registry；`generate`、`modify`、同步 `orchestrate` 和流式 `orchestrate/stream` 均已通过 legacy workflow wrapper 执行并保留原响应结构；本轮相关测试通过（157/157），完整单元回归通过（1702 passed、2 skipped）；入口本地运行和插件 E2E 验证仍待完成。
