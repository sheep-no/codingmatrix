# Agent SSE 展示

> 最后核对：2026-09-03
> 状态：`/agent` 工作台链路活跃；旧首页聊天展示链路作为兼容实现保留

## 当前链路

Agent 主页面为 `src/views/AgentDashboard.vue`。页面通过 `src/composables/useAgentStreaming.js` 请求 `/api/v1/agent/orchestrate/stream`，逐行读取 `data: {json}` 帧，并将事件分发到 workspace、generation、files 和 session 状态模块。

核心展示组件按职责拆分：

- 会话和项目导航：Agent sidebar 组件
- 对话、阶段和审批：Agent conversation 组件
- 文件树与预览：Agent file panel 组件
- 流式协议：`useAgentStreaming.js`
- 阶段标签：`src/constants/agentPhases.js`
- 布局：`src/styles/agent-layout.css`

## 后端帧协议

Agent 流使用 SSE data frame：

```text
data: {"type":"thinking","data":{"message":"..."}}

```

后端回调事件存在两种编码路径：

- 直通事件保留原 `type` 和 payload。
- 其他回调事件包装为 `type: "progress"`，原数据位于 `data`。

生命周期还会直接产生 `log`、`done` 和 `error`。消费者需要允许未知事件，以便后端扩展事件类型时保持连接稳定。

## 当前直通事件

`PASSTHROUGH_SSE_EVENTS` 当前包含：

| 事件 | 前端用途 |
| --- | --- |
| `thinking` | 合并同一 Agent 的流式思考文本，记录阶段信息 |
| `model_info` | 更新当前 Agent、模型、角色调用次数和 fallback 历史 |
| `file` | 增加或更新生成文件 |
| `file_diff` | 展示文件变更 |
| `test_results` | 保存通过、失败、跳过、覆盖率和耗时 |
| `validation_results` | 保存检查项与问题 |
| `cost_update` | 更新 token、费用和模型统计 |
| `performance_metrics` | 更新生成速度、耗时、调用和重试统计 |
| `warning` | 写入警告日志和详情 |
| `file_rejected` | 标记用户拒绝的文件 |
| `step_detail` | 添加可读步骤详情 |
| `react_tool_call` | 展示 ReAct 工具和轮次 |
| `react_tool_result` | 展示工具返回摘要 |
| `react_generating` | 更新最终生成阶段的 Agent 和模型 |

## 其他前端事件

`useAgentStreaming.js` 还处理：

- `progress`
- `critical_decisions`
- `pause_for_approval`
- `log`
- `error`
- `done`

`critical_decisions` 填充待回答的架构决策；`pause_for_approval` 打开文件审批状态；`done` 完成所有未失败阶段并保存项目输出路径、性能和成本摘要。

ReAct 引擎还会产生内部 `react_error` 和 `react_timeout`。这两个类型当前未列入后端直通集合，前端也没有同名 case。

## 流式解析

`processSseResponse` 使用 `ReadableStream` 和 `TextDecoder` 累积 buffer，以换行拆分帧，并保留最后一段不完整数据。只有以 `data: ` 开头的行会进入 JSON 解析。

这套实现适用于当前 Agent SSE。Workflow 接口返回 `application/x-ndjson`，每行直接是 JSON 对象，需使用独立解析方式。

## 思考与阶段展示

流式 `thinking` 会尝试合并同一 Agent 的最后一条消息，减少 token 片段造成的卡片抖动。事件中的 `phase` 同时写入阶段详情，`model` 用于当前模型展示。

`progress` 中的 `step`、`current`、`total`、`percentage`、`current_file` 和 `current_model` 驱动总体进度。前端对字段缺失保持容错，后端事件生产方应尽量发送稳定字段。

## Mobile Agent

Mobile Agent 是 `/agent` 同一页面的响应式形态。`AgentDashboard.vue` 在窄屏下提供会话与文件工具栏、抽屉、遮罩、焦点恢复和 Escape 关闭行为。

主要断点位于 `agent-layout.css`：

- 1200px：压缩桌面布局
- 1024px：进一步调整面板
- 768px：启用移动工具栏与抽屉
- 420px：适配更窄屏幕

移动端和桌面端共享同一 SSE、store、会话与审批状态，没有独立 Mobile Agent 后端。

## 旧首页链路

`src/components/index.vue`、`centerContent.vue` 和 `ProjectGenerator.vue` 中仍有历史聊天与项目生成事件展示逻辑。它们服务旧页面或兼容入口，当前 `/agent` 文档应以 `AgentDashboard.vue` 和 `useAgentStreaming.js` 为准。

维护事件时需要分别检查两条消费者链路，避免修复 `/agent` 后遗漏兼容页面。

## 故障定位

1. 浏览器 Network 中确认响应类型和 `data:` 帧边界。
2. 检查后端事件是否位于 `PASSTHROUGH_SSE_EVENTS`。
3. 检查 `handleSseMessage` 是否包含对应 case。
4. 检查 payload 是否多包了一层 `data`。
5. 检查 store 字段更新后是否被目标组件消费。
6. 移动端额外检查 drawer、scrim 和焦点状态。

## 代码索引

- `app/api/v1/ai_agent/orchestrate_endpoints.py`
- `app/agent/orchestrator_progress.py`
- `app/agent/react_engine.py`
- `src/views/AgentDashboard.vue`
- `src/composables/useAgentStreaming.js`
- `src/constants/agentPhases.js`
- `src/styles/agent-layout.css`
- `src/components/ProjectGenerator.vue`
