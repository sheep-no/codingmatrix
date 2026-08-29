# Developer Guide

## 环境

开发与测试约定使用 Python 3.11。当前 Dockerfile 使用 Python 3.10，部署前需要统一版本或明确兼容矩阵。测试依赖至少包含 `pytest`、`pytest-asyncio`、`aiofiles`、`PyJWT` 和 `apscheduler`。Redis、数据库和 FAISS 相关测试还需要对应本地服务或可选组件。

## 验证命令

```bash
# 运行完整单元测试
python3 -m pytest tests/unit -q

# 运行 StateGraph 和入口迁移相关测试
python3 -m pytest tests/unit/test_workflow_registry.py tests/unit/test_agent_state.py tests/unit/test_state_checkpoint.py tests/unit/test_retrieval_service.py tests/unit/test_agent_adapters.py tests/unit/test_state_graph_runtime.py tests/unit/test_state_graph_nodes.py tests/unit/test_validation_nodes.py tests/unit/test_local_validation_adapter.py -q

# 执行语法编译检查
python3 -m compileall -q app/agent app/api

# 构建并测试 VS Code 插件协议包
npm --prefix vscode-extension test

# 在真实 VS Code Extension Host 中运行插件 E2E
npm --prefix vscode-extension run e2e
```

历史云端验证记录为：排除 Redis、数据库和 FAISS 外部条件的单元测试 1605 passed、2 skipped。当前本地环境已安装 FAISS 并启动 Redis，完整单元测试结果为 1697 passed、2 skipped；该结果覆盖单元测试与本地基础依赖，生产入口和本地插件验证闭环仍需独立验收。

## StateGraph 开发约定

- 节点只读取快照并返回 StateDelta。
- 文件状态使用路径、hash、摘要和诊断字段。
- 云端状态不能把本地构建、依赖安装或 E2E 标记为完成。
- legacy endpoint 迁移保留原响应和事件结构，便于渐进式回归。
- 修改后执行 `git diff --check` 和相关测试。
- 验证节点通过 `State.metadata.required_validation_scopes` 声明 `local_runtime` 或 `local_e2e`；云端验证保持 `cloud_syntax`，本地结果按 scope 回传。
- 本地结果协议使用 `validation_scope`、`status` 和 `source=local`；`local_result_to_delta()` 负责映射为内部字段并执行 task/session/revision/schema 校验。StateReducer 按验证结果 `event_id` 去重，重复回传保持状态和 revision 不变。
- 会话回放使用 `replay_session()`；发现 sequence 缺口时，调用方应执行返回的 `snapshot_recovery` action。
- VS Code 插件包位于 `vscode-extension/`；修改 `src/protocol.ts` 或 `src/connection.ts` 后执行 `npm --prefix vscode-extension test`，该命令会先进行严格 TypeScript 构建，再运行 Node 原生测试。
- 工作区授权策略位于 `src/workspace-authorization.ts`；测试通过注入 `realpath` 适配器覆盖符号链接越界和多工作区隔离场景。
- 验证执行器位于 `src/validation-runner.ts`；真实 VS Code 适配层应注入 `child_process` 的参数数组 spawn 实现，保持 `shell=false` 并复用现有超时、取消和输出限制测试。
- 结果脱敏和缓存分别位于 `src/result-sanitizer.ts` 与 `src/result-store.ts`；持久化适配层实现 `ResultStorage` 的 `get` 和 `update`，云端确认后调用 `acknowledge(event_id)`。
- `CloudConnection` 可注入 `ResultStore`，网络中断时持久化结果，恢复连接后调用 `flushPendingResults()`；新连接实例可继续刷新同一存储中的待回传队列。
- `ValidationStatusView` 位于 `src/status-view.ts`，当前以纯 TypeScript 快照承载状态、通知和诊断数据；修改后通过 `npm --prefix vscode-extension test` 验证，真实 VS Code StatusBar、通知和 DiagnosticCollection 适配层在发布验收阶段接入。
- `compatibility.ts` 负责 schema 和插件版本握手校验；插件 manifest 位于 `vscode-extension/package.json`，构建后入口是 `dist/extension.js`。本地安装 `vsce` 后可运行 `npm --prefix vscode-extension run package` 生成 VSIX。
- `agent-host.ts` 负责版本化 Agent Host Envelope、Host Hello、能力声明、会话握手和策略版本门禁；该模块保持纯 TypeScript，可在接入 VS Code Webview 和原生 API 前独立测试。
- `tool-dispatcher.ts` 负责将 Agent Host 动作路由到工作区文件、诊断和验证适配器；文件动作必须通过 `WorkspaceAuthorization`，验证动作必须通过 `ValidationRunner`，策略关闭时拒绝新的本地动作。
- 终端 Agent Host 动作沿用 `PendingAction` 的操作白名单和工作区目录约束，并通过 `ValidationRunner` 执行；新增终端能力时保持参数数组和 `shell=false`。
- `webview-bridge.ts` 和 `agent-host-runtime.ts` 组成 Webview 消息层与 Agent Host 动作运行层；两者保持 VS Code API 解耦，使用 `npm --prefix vscode-extension test` 验证请求关联、超时、会话门禁和结果事件。
- `agent-workbench.ts` 和 `extension.ts` 提供原生 Webview 面板及 `codingmatrix.openAgentWorkbench` activation 命令；真实 Extension Host E2E 通过 `npm --prefix vscode-extension run e2e` 验证命令注册和面板打开。
- `approval-bridge.ts` 管理 Host 动作的审批请求和决定；`AgentHostRuntime` 通过会话策略的 `auto_approve` 开关控制动作暂停、批准继续和拒绝结果。
- 真实插件 E2E 位于 `vscode-extension/e2e/`，由 `@vscode/test-electron` 启动 VS Code `1.135.0` 和 `fixtures` 临时工作区；无头 Linux 环境需要 `xvfb`，脚本已通过 `xvfb-run` 提供 DISPLAY。测试覆盖工作区打开、manifest 发现、扩展激活和兼容性握手。

## 运行时验证边界

- `/api/v1/health` 是 API 健康路由，`/health` 只可作为部署配置中的显式别名核对。
- 健康检查覆盖数据库和 Redis，当前不能代表 Celery worker 已在线。
- `verify-integration.sh` 主要执行静态文件、源码文本和语法检查；ASGI 健康测试使用进程内传输，Celery 测试主要验证配置和任务注册。
- 真实端口、worker、broker、数据库迁移、Nginx upstream、Nginx 权限和多 worker scheduler 行为需要本地运行环境验证；RC1-RC2 已完成代码配置修复。
- StateGraph 当前通过单节点 legacy wrapper 接入生产入口；RAG、checkpoint 自动恢复、统一事件出口和 VS Code 本地验证回传仍属于迁移中的能力。验证节点和会话 replay 已完成云端契约层实现，真实插件 E2E 已在 VS Code `1.135.0` Extension Host 中通过。
