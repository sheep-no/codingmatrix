# Agent 系统

> 最后核对：2026-09-03
> 状态：Web Agent、legacy 编排、StateGraph 包装、统一状态落库、Mobile Agent 与 VS Code Agent Host 活跃

## 概述

Agent 系统从自然语言需求生成或修改项目，覆盖架构规划、Spec-first 生成、依赖分析、多模型角色协作、文件输出、测试验证、会话恢复和用户审批。

当前架构处于渐进迁移阶段：成熟的 `OrchestratorAgent` 继续执行主要业务流程，API 通过 `build_legacy_workflow` 将它包装为单节点 `StateGraph`。图运行结果同时保存本地 checkpoint 和统一数据库状态，为后续拆分细粒度节点提供稳定状态契约。

## 能力状态

| 能力 | 状态 | 说明 |
| --- | --- | --- |
| `/api/v1/agent/orchestrate/stream` | 活跃 | Web Agent 主流式入口 |
| `/api/v1/agent/orchestrate` | 活跃 | 同步编排入口 |
| `/api/v1/agent/modify` | 活跃 | 增量修改入口 |
| Spec-first 生成 | 活跃 | legacy Orchestrator 内部执行 |
| `DependencyGraph` 与 shadow scan | 活跃 | 生产依赖分析链路 |
| ReAct 工具调用 | 活跃 | Orchestrator 内部能力，通过 Agent SSE 展示 |
| StateGraph | 活跃迁移层 | 生产入口使用 legacy 单节点 wrapper |
| 统一状态落库 | 活跃 | 保存 Session、Task、Checkpoint、Event、Artifact |
| 模型上下文持久化 | 活跃 | 独立 Task/revision 和 GET/PUT API |
| Mobile Agent | 活跃 | `/agent` 同页响应式工作台 |
| VS Code Agent Host | 活跃 | 本地 action、策略、验证、Skills 和会话控制 |
| `POST /api/v1/agent/react` | 废弃文档路径 | 路由未实现，ReAct 由编排入口内部使用 |
| 多语言依赖解析器 | 独立未接入 | 生产图使用 `dependency_graph.py` 自身解析器 |
| Web 搜索增强模块 | 独立未接入 | 生产搜索未导入增强模块 |

## 运行架构

### API 层

`app/api/v1/ai_agent/router.py` 以 `/agent` 为前缀，组合生成、编排、关联、知识、性能和模型上下文子路由。`app/main.py` 再以 `/api/v1` 挂载，因此完整前缀为 `/api/v1/agent`。

### 编排层

`OrchestratorAgent` 仍是主要执行器。它组合以下能力：

- 架构师、前端工程师、后端工程师和代码审查角色
- `DynamicModelRouter` 与 `MultiModelAgent`
- `SpecFirstGenerator`
- `DependencyGraph`、验证器和拓扑调度
- `CodePatcher` 与 `CrossFilePatcher`
- ReAct 工具调用
- Docker 或隔离测试 runner
- 进度、成本、性能、文件和审批回调

默认 `spec_first=True`。新项目生成进入 `generate_with_spec_first`；增量模式加载已有依赖图、分析影响范围并调用增量生成逻辑。

### StateGraph 迁移层

核心状态契约位于 `app/agent/state/models.py`：

- `State`：session、task、revision、status、消息、计划变更、生成文件、验证结果、待执行动作、错误和 metadata
- `StateDelta`：带 `expected_revision` 的增量更新
- `MessageEnvelope`：带 schema、event、session、task、revision、sequence、source 和 payload 的事件信封

`workflow_registry.py` 注册并运行具名图。当前 API 使用 `build_legacy_workflow` 创建单个 `legacy_agent` 节点，保持原 handler 的响应结构。仓库内已有 specification、dependency graph 和 topology 节点实现，生产入口尚未将完整业务流程拆成这些节点。

## 生成流程

### 流式生成

1. API 验证 Token、请求参数、用户并发额度和目标目录。
2. 根据 `project_path`、`session_id`、`project_name` 解析输出目录和会话标识。
3. 创建或恢复 `ProjectSession` 与 legacy `SessionState`。
4. 构造 legacy workflow 并通过 `run_workflow` 执行 Orchestrator。
5. Orchestrator 执行 Spec、依赖图、拓扑调度、角色生成、验证和修复。
6. 回调事件进入队列并编码为 SSE。
7. 图状态写入本地 checkpoint 和统一数据库。
8. 完成时更新会话、结果、成本和性能信息。

### 增量修改

`POST /api/v1/agent/modify` 读取已有项目和会话上下文。`SessionManager` 比较需求与文件 hash，可结合 embedding 判断小幅语义变化；`DependencyGraph` 计算受影响文件，增量生成逻辑复用可保留文件。

### 依赖分析

当前生产 `DependencyGraph.build_from_existing_project()`：

- 解析 Python import
- 解析 JavaScript、TypeScript、JSX、TSX 和 Vue import/require
- 处理通用文件关系和索引文件候选
- 调用 `shadow_scanner` 补充动态、配置或隐式依赖

`app/agent/multi_language_parser.py` 是独立正则解析器，目前只有单元测试消费。详细边界见 `docs/features/MULTI-LANGUAGE-DEPENDENCY-PARSER.md`。

## 模型路由与上下文

`DynamicModelRouter` 根据角色配置、运行状态和学习数据分配模型，`MultiModelAgent` 协调多角色执行。模型信息通过 `model_info` 和 `react_generating` 事件到达前端。

模型上下文保存在独立的 `agent_model_context` Task 中，字段包括配置版本、角色映射、当前模型、当前 Agent、分配统计和最近 50 条 fallback 历史。它拥有独立 revision，更新支持乐观并发控制。

接口：

- `GET /api/v1/agent/sessions/{session_id}/model-context`
- `PUT /api/v1/agent/sessions/{session_id}/model-context`

模型上下文只持久化模型标识和统计信息，不包含 API 凭据。

## 状态持久化与恢复

### Legacy 会话

`SessionManager` 使用内存与 `./sessions/{session_id}.json` 保存文件级进度、增量信息和审批状态。默认 TTL 为 30 天，活跃会话内存上限为 500。

### ProjectSession

数据库 `ProjectSession` 保存用户所有权、输出目录、总体状态、文件计数和活动时间。API 操作会在执行前验证会话归属。

### 统一状态

`persist_agent_state` 执行以下写入：

- legacy session ID 到统一 Session 的兼容映射
- `agent_graph` Task
- 完整 State Checkpoint
- Message Event
- generated file Artifact
- 模型运行上下文

本地 `CheckpointStore` 默认目录为 `data/agent_state_checkpoints`。Host 工具结果可通过 task 和 revision 合并回图状态并继续运行。

完整生命周期见 `docs/features/SESSION-LIFECYCLE.md`。

## Web Agent 与 Mobile Agent

前端入口为 `src/views/AgentDashboard.vue`，由以下 composable 分担状态：

- `useAgentSession`
- `useAgentGeneration`
- `useAgentFiles`
- `useAgentWorkspace`
- `useAgentStreaming`
- `useAgentBackend`

浏览器 `agentSession` store 将有限会话历史写入 localStorage，并保存阶段、日志、文件和模型上下文 revision。切换会话时会从后端补充模型上下文。

Mobile Agent 使用同一 `/agent` 页面、API 和 store。768px 以下启用会话与文件抽屉、遮罩、焦点管理和移动工具栏；它没有独立后端服务。

## VS Code Agent Host

Agent Host 将需要本地 workspace 权限的动作交给 VS Code 扩展。协议版本当前为 1，能力包括：

- `workspace`
- `file`
- `terminal`
- `diagnostics`
- `validation`
- `skill_runtime`

Host 会话默认保存到 `data/agent_host_sessions`，使用临时文件替换方式原子写 JSON。握手会话有效期为 30 分钟，服务端按用户校验所有访问。

主要接口：

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `POST` | `/api/v1/agent/host/handshake` | 协议、能力和 workspace 握手 |
| `GET` | `/api/v1/agent/host/sessions` | 列出当前用户会话 |
| `GET` | `/api/v1/agent/host/sessions/{session_id}/actions` | 拉取待执行 action |
| `POST` | `/api/v1/agent/host/sessions/{session_id}/events` | 回传事件和 tool result |
| `PUT` | `/api/v1/agent/host/sessions/{session_id}/policy` | 以版本检查更新策略 |
| `PUT` | `/api/v1/agent/host/sessions/{session_id}/skills` | 同步 Skill |
| `DELETE` | `/api/v1/agent/host/sessions/{session_id}/skills/{skill_name}` | 撤销 Skill |
| `POST` | `/api/v1/agent/host/sessions/{session_id}/control` | `pause`、`resume` 或 `cancel` |

本地验证 operation 为 `syntax_check`、`dependency_install`、`dependency_check`、`build`、`unit_test`、`e2e_test` 和 `service_check`。Host policy 决定各 operation 是否可执行，扩展还会校验 workspace 授权和相对路径边界。

## 沙箱运行控制

代码沙箱默认启用，默认语言为 `python` 和 `javascript`。超级管理员可通过以下接口读取或更新配置：

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `GET` | `/api/v2/admin/sandbox-config` | 读取沙箱开关和语言列表 |
| `PUT` | `/api/v2/admin/sandbox-config` | 更新 `enable_code_sandbox` 或 `sandbox_languages` |

配置更新返回 `restart_required=true`，重启服务后才对运行时生效。

## 自定义 Skills

用户 Skill 保存于 `/workspace/data/custom_skills`，由元数据记录所有权。注册表内部键为 `user:{owner_user_id}:{name}`，Agent 提示词使用 `[user:{name}]` 标记。

Skills API 更新后会广播到当前用户的活跃 Host 会话；Host 通过 `skill_runtime` capability 应用同步。单个 Skill 上限 100 KB，每用户上限 50 个。详细接口与 `/reload` 运维边界见 `docs/features/CUSTOM-SKILLS.md`。

## ReAct 工具调用

`ReActEngine` 支持读取、搜索、编辑、执行、Git、Web 和 HTTP 工具。工具清单来自 `SPECIALIST_TOOLS`，上层角色和策略可缩小可用范围。

客户端通过编排 SSE 接收 `react_tool_call`、`react_tool_result` 和 `react_generating`。内部 `react_error` 与 `react_timeout` 当前未以同名事件直通前端。详细说明见 `docs/features/REACT-TOOL-CALLING.md`。

## Agent SSE

`/orchestrate/stream` 使用 `data: {json}` 帧。当前直通类型：

- `thinking`
- `model_info`
- `file`
- `file_diff`
- `test_results`
- `validation_results`
- `cost_update`
- `performance_metrics`
- `warning`
- `file_rejected`
- `step_detail`
- `react_tool_call`
- `react_tool_result`
- `react_generating`

其他回调通常包装为 `progress`；生命周期还会发送 `log`、`done`、`error`、`critical_decisions` 和 `pause_for_approval`。前端消费详情见 `docs/features/SSE-DISPLAY-OPTIMIZATION.md`。

## 会话控制

Web Agent 会话 action：

```text
POST /api/v1/agent/session/{session_id}/action?action=cancel|resume|approve|reject
```

`cancel` 会停止任务并尝试清理输出目录；`resume`、`approve`、`reject` 用于恢复暂停或完成文件审批。架构决策通过 `/session/{session_id}/decision` 提交。

Task Queue 另有统一任务恢复接口 `/api/v1/tasks/{task_id}/recover`，服务于统一 Task 生命周期。它与 Agent legacy session action 具有不同标识和状态契约。

## 主要 API

以下端点均位于 `/api/v1/agent`：

| 类别 | 端点 |
| --- | --- |
| 生成 | `POST /generate`、文件读取/下载、项目保存和已保存项目管理 |
| 编排 | `POST /orchestrate`、`POST /orchestrate/stream`、`POST /modify` |
| 运行控制 | `/stop/{session_id}`、`/complete/{session_id}`、session action/decision |
| 恢复与快照 | `/search_sessions`、`/snapshots/{session_id}`、`/rollback/{session_id}`、`/snapshot/diff` |
| 分析 | `/analyze_complexity`、`/evaluate`、学习与缓存统计 |
| 限额 | `/concurrent-limits` 及 recommended/history |
| 知识 | `/knowledge` 与 `/knowledge/search` |
| 需求关联 | `/requirement-association` 及 confirm/helpfulness/stats |
| 观测 | `/performance`、`/performance/trends`、`/performance/export`、`/token-usage` |
| 模型上下文 | `/sessions/{session_id}/model-context` GET/PUT |

所有权、认证方式和请求结构以对应 FastAPI schema 为准。

## 测试与验证

Orchestrator 测试层会优先尝试 Docker runner，并在不可用时使用 `IsolatedTestRunner`。测试、验证、成本和性能结果分别通过 SSE 事件返回。

VS Code Host 的本地验证属于独立执行面，适合依赖安装、构建、单测、E2E 和服务检查。云端流程通过 pending action 等待本地结果，再合并 StateDelta 继续图执行。

## 已知迁移边界

- StateGraph 生产入口当前为 legacy 单节点，节点目录中的细粒度图能力尚未完整接管编排。
- Legacy JSON、`ProjectSession` 和统一状态共同存在，排障时需要按层检查。
- Web Agent 与 Agent Host 使用不同的会话 ID 与控制端点。
- Workflow Engine 拥有独立 `/api/v1/workflow` API 和进程内注册表。
- Web 搜索增强和多语言解析器均是独立模块，生产主链路尚未消费。
- 旧版本文档中的固定模块数量、测试数量和性能收益缺少当前运行证据，本页不再作为这些指标的来源。

## 代码索引

- `app/api/v1/ai_agent/`
- `app/agent/orchestrator.py`
- `app/agent/orchestrator_generation/`
- `app/agent/state/`
- `app/agent/workflow_registry.py`
- `app/services/agent_state_adapter.py`
- `app/services/model_context_service.py`
- `app/agent/session_manager.py`
- `app/api/v1/agent_host.py`
- `src/views/AgentDashboard.vue`
- `src/composables/useAgentStreaming.js`
- `src/stores/agentSession.js`
- `vscode-extension/src/`
