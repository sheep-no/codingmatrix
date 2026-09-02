# VS Code 本地验证插件实施任务清单

## 阶段 1：协议与契约

### VSCODE-001 验证动作与结果 Schema

- 状态：`completed`
- 优先级：`P0`
- 修改：插件协议模型、云端 StateGraph 验证契约
- 消费：VS Code 插件、`app/agent/nodes/validation.py`
- 契约：`PendingAction`、`LocalValidationResult`、`MessageEnvelope`
- 测试：动作解析、版本、scope 和结果序列化测试
- 验证范围：`cloud_syntax` + `local_runtime`
- 验收证据：`npm --prefix vscode-extension test` 通过（6/6），覆盖 Schema round-trip、非法 scope 拒绝、未知版本错误和工作区越界路径校验。

### VSCODE-002 插件连接与认证

- 状态：`completed`
- 优先级：`P0`
- 修改：插件连接层、云端插件接入 API
- 消费：PendingAction 拉取、结果回传和连接状态视图
- 契约：认证会话、Envelope、task/revision/event 标识
- 测试：连接、重连、断线缓存和认证失败测试
- 验证范围：`cloud_syntax` + `local_runtime`
- 验收证据：`npm --prefix vscode-extension test` 通过（10/10），覆盖 Bearer 认证、认证失败不重试、临时错误重试、断线结果缓存和恢复回传。

## 阶段 2：本地执行与安全

### VSCODE-003 工作区授权与路径校验

- 状态：`completed`
- 优先级：`P0`
- 修改：插件工作区授权和动作校验模块
- 消费：所有本地验证动作
- 契约：workspace identity、路径规范化、授权状态
- 测试：授权、撤销、工作区外路径、符号链接和多工作区测试
- 验证范围：`local_runtime`
- 验收证据：`npm --prefix vscode-extension test` 通过（15/15），覆盖授权路径、多工作区、绝对路径、未知工作区、父目录遍历、符号链接越界和授权撤销。

### VSCODE-004 验证执行器

- 状态：`completed`
- 优先级：`P0`
- 修改：插件 ValidationRunner
- 消费：依赖检查、构建、单元测试、E2E 和服务检查动作
- 契约：operation 白名单、命令参数数组、timeout、cancel
- 测试：成功、非零退出、超时、取消、输出上限和进程树清理测试
- 验证范围：`local_runtime` + `local_e2e`
- 验收证据：`npm --prefix vscode-extension test` 通过（22/22），覆盖参数数组启动、shell 禁用、非零退出、超时、取消和输出上限。

### VSCODE-005 结果脱敏与本地缓存

- 状态：`completed`
- 优先级：`P0`
- 修改：插件 ResultSanitizer、ResultStore
- 消费：结果回传和断线恢复
- 契约：LocalValidationResult、脱敏字段和本地缓存记录
- 测试：密钥、密码、Cookie、连接串、环境变量和多行日志测试
- 验证范围：`local_runtime`
- 验收证据：`npm --prefix vscode-extension test` 通过（26/26），覆盖密钥、Bearer token、密码、Cookie、私钥脱敏，event_id 去重、跨实例持久化和确认删除。

## 阶段 3：云端合并与状态闭环

### VSCODE-006 本地结果适配与 revision 门禁

- 状态：`completed`
- 优先级：`P0`
- 修改：`app/agent/local_validation_adapter.py`、相关测试和插件适配层
- 消费：StateReducer、ValidationNode、插件结果提交
- 契约：task、revision、schema version、scope、source
- 测试：`tests/unit/test_local_validation_adapter.py`、`tests/unit/test_agent_state.py`，覆盖 revision 冲突和验证结果幂等
- 验证范围：`cloud_syntax` + `local_runtime`
- 验收证据：`python3 -m pytest tests/unit/test_local_validation_adapter.py tests/unit/test_agent_state.py -q` 通过（10/10）；`npm --prefix vscode-extension test` 通过（26/26）。覆盖协议字段映射、source/session 校验、非法 status、revision 门禁、同一 delta 内重复 event_id 和重复回传 no-op；插件真实 E2E 待补充。

### VSCODE-007 多验证范围终态推导

- 状态：`completed`
- 优先级：`P1`
- 修改：`app/agent/nodes/validation.py`、StateGraph 状态测试
- 消费：插件回传的 `local_runtime` 和 `local_e2e` 结果
- 契约：PendingAction、ValidationResult、terminal status policy
- 测试：部分完成、全部通过、失败、重复结果和过期结果测试
- 验证范围：`cloud_syntax` + `local_runtime` + `local_e2e`
- 验收证据：`python3 -m pytest tests/unit/test_validation_nodes.py tests/unit/test_local_validation_adapter.py tests/unit/test_agent_state.py -q` 通过（19/19）；覆盖多个必需 scope 的等待、全部通过后的 `completed`、失败终态、等待确认、重复结果和过期 revision 门禁。

### VSCODE-008 断线恢复与 checkpoint

- 状态：`completed`
- 优先级：`P1`
- 修改：插件 ResultStore、云端 session/checkpoint 适配
- 消费：重连、sequence replay 和 snapshot recovery
- 契约：Checkpoint、MessageEnvelope、sequence、event_id
- 测试：断线、重启、序列缺口、snapshot recovery 和重复回传测试
- 验证范围：`local_runtime`
- 验收证据：`npm --prefix vscode-extension test` 通过（27/27），`python3 -m pytest tests/unit/test_state_checkpoint.py tests/unit/test_workflow_registry.py -q` 通过（8/8）。覆盖插件连接实例重启后的持久化结果恢复、云端 checkpoint round-trip、旧 payload 迁移、重复结果确认和 sequence gap 的 `snapshot_recovery`。

## 阶段 4：VS Code 体验与发布

### VSCODE-009 验证任务与诊断界面

- 状态：`completed`
- 优先级：`P1`
- 修改：插件 StatusView、通知、诊断和取消交互
- 消费：动作状态、执行进度和结果摘要
- 契约：状态枚举、诊断位置、用户确认操作
- 测试：授权、进度、取消、失败和多验证 scope 结果匹配测试
- 验证范围：`local_e2e`
- 验收证据：`npm --prefix vscode-extension test` 通过（31/31），覆盖授权等待、运行进度、用户取消、失败诊断、耗时展示和 session/revision/scope 结果匹配。真实 VS Code 工作区 E2E 仍待 `VSCODE-010` 发布验收阶段完成。

### VSCODE-010 版本兼容与发布验收

- 状态：`completed`
- 优先级：`P1`
- 修改：插件 manifest、协议协商和发布流水线
- 消费：云端版本检查、旧任务恢复和升级提示
- 契约：schema_version、插件版本、兼容矩阵
- 测试：兼容版本、未知版本、非法握手和 manifest 打包入口测试
- 验证范围：`cloud_syntax` + `local_e2e`
- 验收证据：`npm --prefix vscode-extension test` 通过（35/35），覆盖兼容 schema、插件版本上下界和非法握手；`npm --prefix vscode-extension run e2e` 通过，使用 VS Code `1.135.0`、临时 `fixtures` 工作区和真实 Extension Host 验证 manifest 发现、扩展激活及兼容性握手；manifest 声明 VS Code `>=1.90.0`、activation 入口及 `vsce package --no-dependencies` 脚本。

### VSCODE-011 双工作台 Agent Host

- 状态：`completed`
- 优先级：`P0`
- 目标：将 VS Code 插件从本地验证客户端升级为完整的 VS Code Agent 工作台和本地 Agent Host，与 Web 工作台共享会话、模型、Skills 和策略。
- 范围：会话握手、工作区能力声明、文件工具、终端工具、诊断工具、验证工具、Skills 下发、模型策略同步、审批、总开关和验证类型开关。
- 协议：版本化 `AgentHostEnvelope`，支持 `tool_action`、`progress_event`、`approval_request`、`policy_update`、`skill_revoke` 和 `session_control`。
- 当前进度：已实现 `agent-host.ts` 的 Envelope 解析、Host Hello 生成与解析、会话握手、能力声明和单调递增策略版本门禁；已实现 `ToolDispatcher` 的文件、终端、诊断和验证动作分发，`ApprovalBridge` 的审批请求与决定，以及 `WebviewBridge`、`AgentHostRuntime` 的云端动作轮询、策略更新、原生 Agent Webview 审批消息链路、真实本地 Host activation 接线和命令 E2E；后端已新增认证握手、session actions、Host events、policy 更新接口、StateGraph 自动动作入队、文件持久化 session store 和 `tool_result` 恢复 StateGraph，支持用户绑定 session、事件幂等、策略版本冲突、action 去重、进程重启恢复和本地结果驱动的 `completed` 终态；StateGraph 已支持等待动作时保存下一节点游标、结果回传后继续执行，以及通过 `register_recoverable_workflow_factory()` 跨进程重建 workflow definition；`CloudConnection.handshake()`、session 动作拉取和事件回传已接入，云端 handshake 返回的 session snapshot 会写回本地 runtime 会话；后端 Agent Host 接口单测 12/12 通过，VS Code 插件测试 60/60 通过，TypeScript build 和基础真实 VS Code Extension Host E2E 均通过；带真实后端配置的 Extension Host E2E 已加入 session 控制检查并通过。
- 安全：短期会话凭据、工作区绑定、策略版本、能力白名单、风险审批、审计事件和结果脱敏。
- 交互：Web 和 VS Code 工作台提供一致的对话、审批、进度、日志、诊断和结果体验；VS Code 扩展提供后台运行时和原生本地能力。
- 依赖：复用现有模型供应商接口、Skill 管理接口、StateGraph、checkpoint、事件适配器和本地验证执行器。
- 验收：用户从 Web 或 VS Code 工作台完成模型策略同步、Skill 下发与撤销、本地动作审批、验证开关控制、会话暂停/恢复/取消、执行进度展示和结果驱动的 Agent 继续执行，并可从另一工作台恢复同一会话。验收证据：后端历史单元测试 `1723 passed, 2 skipped`，本轮 Agent Host 接口单测 `12 passed`，真实 HTTP Agent Host 闭环通过，VS Code 插件测试 `60 passed`，TypeScript build、基础真实 Extension Host E2E 和关闭限流后的真实后端 Extension Host E2E 均通过；后端 E2E 使用临时进程级限流开关，测试结束后已停止临时后端。

### VSCODE-012 下一阶段：multi-root 授权与 Workspace capability

- 状态：`completed`
- 优先级：`P0`
- 修改：VS Code activation 的 multi-root 全量授权、Workspace 根目录查询动作及对应测试。
- 契约：`workspace` capability 支持 `inspect` 和 `list_roots`，返回当前已授权 workspace roots。
- 验收证据：`npm --prefix vscode-extension test` 通过（58/58），覆盖两个 workspace roots 的授权查询和非法操作拒绝。

### VSCODE-013 下一阶段：VS Code Agent 对话工作台

- 状态：`completed`
- 优先级：`P0`
- 目标：在 VS Code 中提供需求输入、Agent 流式事件、会话消息、进度、审批和结果恢复的基础工作台。
- 修改：CloudConnection 增加 Agent SSE 请求与事件解析；Agent Workbench 增加需求输入、事件消息展示和云端错误展示；会话 ID 按后端约束规范化。
- 验收证据：`npm --prefix vscode-extension test` 通过（60/60），覆盖流式事件解析、Bearer 认证、需求转发、Webview 消息展示、handshake session snapshot 接入和会话控制请求；`npm --prefix vscode-extension run e2e` 通过，使用 VS Code `1.135.0` 和真实 Extension Host 验证扩展构建、加载和激活。

### VSCODE-014 真实后端账号与模型配置流程

- 状态：`completed`
- 优先级：`P1`
- 范围：测试账号初始化、登录、API Key 管理、模型调用和降级策略配置。
- 验收证据：`tests/manual/test_apikey_flow.py` 报告 `13/13` 通过；后端 Agent Host 接口单测 `python3 -m pytest tests/unit/test_agent_host_api.py -q` 报告 `12 passed`。
- 环境边界：测试 API Key 仅通过进程环境变量注入并在流程结束后清理；本轮提供的 Key 连接校验成功，模型调用成功，用户 Key 阻塞项已解除。

### VSCODE-015 云端旧沙盒路径边界修复

- 状态：`in_progress`
- 优先级：`P0`
- 目标：将旧生成流程中的运行时沙盒调用收敛为 `cloud_syntax`，把运行时、依赖、构建、单元测试和 E2E 验证交给 VS Code Agent Host。
- 修改：`app/agent/utils.py` 的验证范围分流、云端沙盒缺失策略和对应单元测试。
- 验收证据：相关回归测试通过（22 passed）；覆盖云端 `bwrap` 缺失时跳过运行时沙盒、Agent Host 发布 `local_validation` 动作、Host 回传 `tool_result`、checkpoint 恢复和 `completed` 状态归并；真实模型生成请求已成功完成并生成 10 个文件，日志确认云端语法验证跳过 `bwrap`；真实 HTTP Agent Host 握手成功；`npm --prefix vscode-extension run e2e` 通过（退出码 0）。剩余验收是使用已绑定 Host 会话重新触发生成，并由 VS Code Host 实际拉取、执行和回传本地结果。
