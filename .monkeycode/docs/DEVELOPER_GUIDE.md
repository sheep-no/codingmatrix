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
```

历史云端验证记录为：排除 Redis、数据库和 FAISS 外部条件的单元测试 1605 passed、2 skipped。当前本地环境已安装 FAISS 并启动 Redis，完整单元测试结果为 1697 passed、2 skipped；该结果覆盖单元测试与本地基础依赖，生产入口和本地插件验证闭环仍需独立验收。

## StateGraph 开发约定

- 节点只读取快照并返回 StateDelta。
- 文件状态使用路径、hash、摘要和诊断字段。
- 云端状态不能把本地构建、依赖安装或 E2E 标记为完成。
- legacy endpoint 迁移保留原响应和事件结构，便于渐进式回归。
- 修改后执行 `git diff --check` 和相关测试。
- 验证节点通过 `State.metadata.required_validation_scopes` 声明 `local_runtime` 或 `local_e2e`；云端验证保持 `cloud_syntax`，本地结果按 scope 回传。
- 会话回放使用 `replay_session()`；发现 sequence 缺口时，调用方应执行返回的 `snapshot_recovery` action。
- VS Code 插件包位于 `vscode-extension/`；修改 `src/protocol.ts` 或 `src/connection.ts` 后执行 `npm --prefix vscode-extension test`，该命令会先进行严格 TypeScript 构建，再运行 Node 原生测试。
- 工作区授权策略位于 `src/workspace-authorization.ts`；测试通过注入 `realpath` 适配器覆盖符号链接越界和多工作区隔离场景。
- 验证执行器位于 `src/validation-runner.ts`；真实 VS Code 适配层应注入 `child_process` 的参数数组 spawn 实现，保持 `shell=false` 并复用现有超时、取消和输出限制测试。
- 结果脱敏和缓存分别位于 `src/result-sanitizer.ts` 与 `src/result-store.ts`；持久化适配层实现 `ResultStorage` 的 `get` 和 `update`，云端确认后调用 `acknowledge(event_id)`。

## 运行时验证边界

- `/api/v1/health` 是 API 健康路由，`/health` 只可作为部署配置中的显式别名核对。
- 健康检查覆盖数据库和 Redis，当前不能代表 Celery worker 已在线。
- `verify-integration.sh` 主要执行静态文件、源码文本和语法检查；ASGI 健康测试使用进程内传输，Celery 测试主要验证配置和任务注册。
- 真实端口、worker、broker、数据库迁移、Nginx upstream、Nginx 权限和多 worker scheduler 行为需要本地运行环境验证；RC1-RC2 已完成代码配置修复。
- StateGraph 当前通过单节点 legacy wrapper 接入生产入口；RAG、checkpoint 自动恢复、统一事件出口和 VS Code 本地验证回传仍属于迁移中的能力。验证节点和会话 replay 已完成云端契约层实现，真实插件 E2E 仍需本地环境验收。
