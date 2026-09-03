# ReAct 工具调用

> 最后核对：2026-09-03
> 状态：Agent 内部执行能力活跃；独立 HTTP 端点未接入

## 概述

`app/agent/react_engine.py` 实现 Agent 的 Reason-Act-Observe 循环。模型可先读取项目结构和符号，再按需修改文件、运行受限命令或查询外部信息。工具结果会回填下一轮上下文，直到模型生成最终结果、达到轮次边界、取消或超时。

ReAct 当前通过 Orchestrator 和工程师角色的内部调用进入生产链路。路由中没有 `POST /api/v1/agent/react`，旧文档中的该公开端点描述已经废弃。

## 执行链路

1. Orchestrator 为角色构造目标、项目上下文和可用工具。
2. `ReActEngine` 请求模型生成内容或结构化工具调用。
3. 引擎校验工具名和参数，再执行 `SPECIALIST_TOOLS` 中的函数。
4. 工具结果与错误写回对话上下文。
5. 引擎发出工具调用、结果或生成阶段事件。
6. 最终文本由上层工程师和 Orchestrator 转换为文件、差异或结果事件。

引擎支持取消事件和心跳监控。默认 heartbeat timeout 为 600 秒，单次工具执行默认 timeout 为 120 秒。

## 当前工具注册表

工具来源为 `app/agent/tools.py` 的 `SPECIALIST_TOOLS`：

| 类别 | 工具 |
| --- | --- |
| 读取与分析 | `read_file`、`list_files`、`read_symbols`、`read_imports`、`summarize_file`、`search_files` |
| 精确编辑 | `partial_update`、`insert_content`、`regex_replace` |
| 文件写入 | `write_file`、`create_file` |
| 执行 | `execute_code`、`run_command` |
| Git | `git_status`、`git_diff`、`git_commit`、`git_log` |
| 网络 | `web_search`、`http_request` |
| 清理 | `delete_files_by_pattern` |

`create_file` 与 `write_file` 指向同一个实现。`run_command` 受允许前缀和危险命令规则约束；`http_request` 带 SSRF 防护。上层运行环境仍应通过审批和 policy 控制具有写入、执行、Git、网络或删除副作用的工具。

MCP 工具可由引擎动态参与执行，连接异常会产生内部 `react_error` 事件。

## 编辑协议

每轮最多调用一个工具，工具调用必须是单个 JSON 对象：

```json
{"tool":"工具名","params":{}}
```

`tool` 是注册工具名，`params` 是该工具参数对象。解析到普通文本时结束工具循环并将文本作为最终结果；工具结果返回后，模型可继续下一轮工具调用或输出普通文本。

工程师可通过结构化工具调用直接修改文件。部分 legacy 响应还使用 edit marker 表达目标替换，上层负责识别目标文件、验证旧文本、应用变更并报告差异。

优先选择范围最小的工具：

- 已知完整目标块时使用 `partial_update`。
- 已知锚点或行位置时使用 `insert_content`。
- 需要多个机械替换时使用 `regex_replace`。
- 创建完整新文件时使用 `create_file`。
- 覆盖完整文件时使用 `write_file`。

## 事件

引擎产生以下 ReAct 事件：

| 事件 | 含义 | Agent SSE 当前直通 |
| --- | --- | --- |
| `react_tool_call` | 即将调用工具，包含轮次和工具信息 | 是 |
| `react_tool_result` | 工具完成，包含摘要或结果 | 是 |
| `react_generating` | 角色进入最终内容生成 | 是 |
| `react_error` | MCP 或工具链内部异常 | 否 |
| `react_timeout` | 某轮 heartbeat 超时 | 否 |

`orchestrate_endpoints.py` 的 `PASSTHROUGH_SSE_EVENTS` 只列出前三种 ReAct 事件。`react_error` 与 `react_timeout` 目前由引擎产生，但不会作为同名事件直接到达 Agent 前端；上层错误处理可能转换为通用 `progress` 或 `error`。

前端 `src/composables/useAgentStreaming.js` 已消费前三种直通事件，用于工具日志、轮次详情和当前 Agent/模型展示。

## 与 Agent Host 的关系

云端 ReAct 工具和本地 Agent Host action 使用不同协议。需要本地 workspace、terminal、diagnostics 或 validation 的 StateGraph action 会进入 Host 待执行队列，由 VS Code 扩展执行并回传 `tool_result`。

本地验证支持 `dependency_install`，且每个 operation 受 Host policy 控制。Host 结果带 session、task、revision 和 message ID，服务器据此去重并恢复图状态。

## 运行边界

- ReAct 是内部编排能力，客户端通过 `/api/v1/agent/orchestrate/stream` 观察事件。
- 工具注册表示可调用能力清单，具体角色、策略和环境可进一步缩小清单。
- 文件和命令工具应在项目目录边界内运行。
- 工具结果可能很大，上层应保留摘要并限制回填上下文规模。
- 心跳超时表示一段时间内缺少 LLM 活动，和单工具 timeout 是两套计时机制。

## 代码索引

- `app/agent/react_engine.py`
- `app/agent/tools.py`
- `app/agent/orchestrator.py`
- `app/api/v1/ai_agent/orchestrate_endpoints.py`
- `src/composables/useAgentStreaming.js`
- `app/api/v1/agent_host.py`
- `vscode-extension/src/tool-dispatcher.ts`
