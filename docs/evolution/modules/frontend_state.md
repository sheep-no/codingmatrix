# Frontend State 与 Composables 演化深扫文档

> 版本：v0.1 | 扫描日期：2026-08-29 | 状态：已完成
> 归属：前端 / 状态层与 AgentDashboard 组装链
> 路径：`src/stores/`、`src/composables/`（9 个 store、13 个 composable）
> 索引：`docs/evolution/TASKS.md`（本次未修改）

## 扫描边界与证据标记

- 本文只分析 `src/stores/` 全部 9 个文件、`src/composables/` 全部 13 个文件，并使用全库 `rg` 验证导入、实例化、方法调用和测试引用。
- `实码可证`：由当前代码和调用关系即可确定。
- `实测`：已有运行或测试证据。
- `待实测`：代码显示风险，需要浏览器、真实后端或针对性测试确认。
- 状态三态：`活跃` 表示存在生产消费方；`未接入` 表示实现存在但没有生产链路；`废弃` 表示被当前实现替代的残留入口。

## 1. 模块作用与功能

### 1.1 Store 清单与状态判定

| 文件 | 模块定位与主要入口 | 状态 | 真实消费方 |
|---|---|---|---|
| `src/stores/user.js:5` | 登录状态、权限、tokenManager 委托、用户资料恢复 | 活跃 | `src/main.js:9,28`、`src/router/index.js:2,105`、多个视图/组件、`useAuth` |
| `src/stores/apikey.js:16` | API Key token 元数据、公钥、模型覆盖、后端同步 | 活跃 | `AgentDashboard.vue:127`、`components/index.vue:158`、设置页、图片/PPT/Aicloud/项目生成器 |
| `src/stores/navigation.js:36` | 工具面板、折叠状态及 localStorage 导航状态 | 活跃 | `components/index.vue:156`、`bottominput.vue:230`、`ImageGenerator.vue:481` |
| `src/stores/providers.js:14` | 动态供应商列表、模型同步、离线缓存 | 活跃 | `AgentDashboard.vue:128`、`DynamicProviderManager.vue:123` |
| `src/stores/logs.js:4` | 系统日志、过滤器、连接状态、日志 localStorage | 活跃 | `SystemLogs.vue:159` |
| `src/stores/github.js:31` | GitHub 用户名/token/开关配置 | 活跃 | `GithubConfigPanel.vue:81`、`ProjectGenerator.vue` 导入链 |
| `src/stores/task.js:9` | 任务 Map、活动/完成/失败列表、任务通知连接 | 未接入 | 全库生产代码没有 `useTaskStore`；`TaskQueue.vue:141` 自己维护 `tasks` 并直接调用 API |
| `src/stores/agentSession.js:10` | Agent 会话历史、阶段、决策、角色和模型分配 | 未接入/旧实现 | 仅被 `useAgentSession.js:2,9` 包装；Dashboard 通过包装器间接消费 |
| `src/stores/agentWorkspace.js:6` | Agent 文件、日志、结果、后端设置的一体化 store | 废弃/旧实现 | 全库无 `useAgentWorkspaceStore`；当前 Dashboard 使用 `useAgentFiles`、`useAgentWorkspace`、`useAgentBackend` |

### 1.2 Composable 清单与状态判定

| 文件 | 核心功能与主要入口 | 状态 | 真实消费方 |
|---|---|---|---|
| `useAgentSession.js:8` | Pinia 会话 store 的兼容包装 | 活跃但有废弃接口 | `AgentDashboard.vue:107,136` |
| `useAgentGeneration.js:14` | Agent 阶段、进度、角色分配、ETA、重置 | 活跃 | `AgentDashboard.vue:108,137` |
| `useAgentFiles.js:74` | 文件列表、分类、过滤、差异、高亮、模板 | 活跃 | `AgentDashboard.vue:109,138` |
| `useAgentWorkspace.js:5` | 日志、thinking、决策、ZIP 导入、版本和下载 | 活跃 | `AgentDashboard.vue:110,139` |
| `useAgentStreaming.js:6` | SSE 消费、事件归并、生成请求、并发限制处理 | 活跃 | `AgentDashboard.vue:111,140` |
| `useAgentBackend.js:4` | 保存/下载/删除、快照、性能、设置、决策提交 | 活跃 | `AgentDashboard.vue:112,141` |
| `useAuth.js:6` | 登录、注册、退出、刷新 token、资料更新 | 活跃 | `LoginDialog.vue:3,11` |
| `useToast.js:9` | 全局 toast 队列及定时移除 | 活跃 | 多个组件、`ToastContainer.vue:4` |
| `useKeyboardShortcuts.js:27` | 键盘快捷键注册和序列状态 | 活跃 | `components/index.vue:161,1164-1218` |
| `useFileDrop.js:3` | 全局/元素拖放监听、类型和大小校验 | 活跃 | `FileDropZone.vue:35,50`、`bottominput.vue:103,560-566` |
| `useOfflineQueue.js:6` | 网络状态监听、localStorage 队列、恢复后发送 | 未接入 | `components/index.vue:139,160` 仅实例化，未调用队列 API |
| `useMarkdown.js:25` | Markdown 渲染、代码高亮、DOMPurify 清洗 | 未接入 | 全库无生产调用 |
| `useClipboard.js:3` | 安全上下文 clipboard 与 execCommand 兜底 | 未接入 | 全库无生产调用；各组件自行复制或调用后端 composable 内部逻辑 |

### 1.3 AgentDashboard 组装链

```text
AgentDashboard.vue:136-141
  useAgentSession() -> useAgentSessionStore()
  useAgentGeneration()
  useAgentFiles()
  useAgentWorkspace({ session, files, generation })
  useAgentStreaming(projectApi, workspace, files, generation, session)
  useAgentBackend(projectApi, workspace, files, generation)

UI 子组件
  TopBar/Sidebar/Workspace/InputBar/FilePanel/Modals
  -> Dashboard action wrappers
  -> streaming / backend / workspace / files / session
```

- 输入生成链：`AgentInputBar:65` -> `generateProject:194` -> `streamGenerate:411` -> `buildStreamParams:318` -> `projectApi.generateProjectStream:434` -> `processSseResponse:284` -> `handleSseMessage:29`。
- SSE 状态链：`file/file_diff` 写入 `files`；`thinking/test_results/validation_results/cost_update/performance_metrics/decisions` 写入 `workspace`；`progress/model_info/done` 写入 `generation` 或 `workspace.currentProjectPath`。
- 后端操作链：Dashboard 的保存、设置、性能、快照、文件删除、决策提交动作统一进入 `useAgentBackend`。
- 会话链：Dashboard 调用 `useAgentSession` 的 `createNewSession/switchSession/deleteSession`，并在 `AgentDashboard.vue:334-352,360-377` 试图自动保存完整 Agent 状态。

## 2. 依赖与被依赖

### 2.1 导入依赖

- Store 层依赖 Pinia/Vue；`apikey` 依赖 API client、RSA 加密；`user` 依赖 `tokenManager`；`task` 依赖 `taskNotificationService`；`providers` 依赖 `utils/api/index`；Agent stores 额外依赖 Element Plus、JSZip、highlight.js。
- Agent composables 通过 `reactive()` 返回包含 refs 的对象，调用方依赖 Vue 的自动解包行为；`useAgentStreaming` 直接依赖 `apikey`、phase 常量和 Element Plus；`useAuth/useClipboard/useOfflineQueue` 依赖 `useToast`。
- 全库未发现针对这些 store/composable 的有效单元测试消费。现有命中主要位于 `tests/e2e/` 和 `tests/archive/playwright/`，没有直接验证状态契约。

### 2.2 持久化与离线链路

| 状态 | 写入 | 恢复 | 结论 |
|---|---|---|---|
| 用户资料 | `user.js:51-53` + Pinia persist `:152-157` | `useAuth.js:11-13` -> `restoreUser` | 活跃，存在双重持久化 |
| API Key 元数据/公钥/模型覆盖 | `apikey.js:67-83` | store 初始化 `:37`，Dashboard/设置页再次显式调用 | 活跃，重复加载 |
| 动态供应商 | `providers.js:31-33` | `loadFromStorage:19-27`，Dashboard `:355-357` | 活跃，网络失败返回空数组会掩盖缓存语义 |
| 导航 | `navigation.js:177-194` + Pinia persist `:270-275` | `restoreNavigationFromStorage:201-223` | 活跃，双重持久化；项目生成器状态不写入自定义 storage |
| 系统日志 | `logs.js:90-107` | `SystemLogs.vue:357-363` | 活跃，但组件 watcher 的 ref 访问错误，自动保存失效 |
| Agent 会话 | `agentSession.js:47-53` 只保存 `sessionHistory` | Dashboard 调用 `useAgentSession` 的 no-op 保存接口 | 会话骨架可保存，生成状态无法恢复 |
| 离线消息 | `useOfflineQueue.js:61-79` | mounted 恢复后立即移除 key | 未接入，当前页面没有发送回调和入队调用 |

## 3. 已探明 Bug

### FESTATE-01 [P1] Agent 会话自动保存链落入 no-op 包装器

- **定位**：`src/composables/useAgentSession.js:17-25`、`src/views/AgentDashboard.vue:334-383`。
- **调用链**：Dashboard `watch`/`onMounted` -> `session.saveSessionState(...)`、`session.startAutoSave(...)`；包装器分别执行空函数；`switchSession` 只恢复 `prompt`（`useAgentSession.js:14-16`、`agentSession.js:91-99`）。
- **功能**：Dashboard 试图保存 workflow stages、文件、日志、thinking、决策、模型分配和恢复次数。
- **缺陷**：包装器导出 `saveSessionState`、`restoreSessionState`、`startAutoSave`、`stopAutoSave`，其中保存/自动保存/恢复均为空实现或固定返回 `null`；传入 `createNewSession/switchSession/deleteSession` 的完整状态参数也被底层 store 忽略。
- **影响**：刷新、切换会话、组件卸载后，已生成文件、阶段、日志、决策和模型统计无法从会话历史恢复。会话列表仍显示，形成状态存在但内容丢失的假持久化。
- **证据**：实码可证；已有历史记忆记录该 wrapper 为薄包装，但当前代码进一步直接证明关键方法是 no-op。完整浏览器刷新恢复待实测。
- **建议**：统一由 Pinia store 保存完整快照并实现恢复，或移除兼容包装器后让 Dashboard 直接使用 store；为 `create/switch/delete` 定义单一快照契约。

### FESTATE-02 [P1] 离线队列没有接入实际消息发送链

- **定位**：`src/composables/useOfflineQueue.js:13-15,42-59`、`src/components/index.vue:139-160,370-383`。
- **调用链**：`components/index.vue` 仅执行 `useOfflineQueue()`；全库无 `setSendCallback`、`queueMessage`、`flushQueue` 的消费调用。
- **功能**：网络恢复时应将 localStorage 中的消息按序发送，并在失败后重试。
- **缺陷**：`sendCallback` 初始为 `null`，`flushQueue` 在无 callback 时直接返回；实际 `handleSendMessage` 不检查 `offlineQueue.isOnline`，也不调用 `queueMessage`。
- **影响**：断网期间消息不会进入队列，恢复网络时也没有可执行的发送函数；用户看到的“自动发送”提示与实际行为不符。
- **证据**：实码可证；浏览器断网交互效果待实测。
- **建议**：将 `handleSendMessage` 的请求函数注册为回调，在网络不可用或请求失败时统一入队；恢复队列时保留顺序、处理重复提交并加入上限/重试退避。

### FESTATE-03 [P1] SystemLogs 自动保存 watcher 永远读取 Pinia 自动解包后的 `.value`

- **定位**：`src/components/SystemLogs.vue:376-390`、`src/stores/logs.js:6-7,90-103`。
- **调用链**：SystemLogs watcher -> `logsStore.systemLogs.value` 等表达式 -> Pinia setup store 自动解包 ref 后的普通数组/字符串。
- **功能**：日志变化、过滤器变化时自动调用 `saveLogsToStorage()`。
- **缺陷**：Pinia store 对外暴露的 setup-store refs 会自动解包，组件中应读取 `logsStore.systemLogs`；当前 `.value` 为 `undefined`，watch source 对这些状态不会随真实变化更新。
- **影响**：挂载和卸载仍可能保存一次，运行期间新增日志、过滤器变更和显示设置变更不会自动持久化；刷新可能丢失最近日志及过滤状态。
- **证据**：实码可证；实际刷新丢失需浏览器实测。
- **建议**：使用 `storeToRefs(logsStore)` 后监听 refs，或直接监听解包后的 store 属性，并补充深度监听测试。

### FESTATE-04 [P2] SSE 解析器对合法帧格式和尾帧处理过于严格

- **定位**：`src/composables/useAgentStreaming.js:284-315`。
- **调用链**：`streamGenerate:434` -> `processSseResponse` -> 按换行拆分 -> 仅处理 `trimmed.startsWith('data: ')` 的行。
- **功能**：解析后端流式事件并更新文件、阶段、日志、结果和完成状态。
- **缺陷**：解析条件要求 `data:` 后必须有一个空格；SSE 允许 `data:` 后直接跟数据。读取结束时只尝试处理 `buffer` 中的单行尾帧，尾部没有换行且包含多行字段时会被整体 JSON 解析失败并静默丢弃。
- **影响**：后端或代理改变 SSE 空格格式、连接以未换行尾帧结束时，事件可能完全不更新，`isGenerating` 也可能保持错误状态。
- **证据**：实码可证，具体后端帧格式兼容性待实测。
- **建议**：按 SSE 字段规则解析 `data:`，聚合连续 data 行并处理空行事件边界；流结束前统一 flush decoder/buffer，并对未完成 JSON 记录可见错误。

### FESTATE-05 [P2] 复制设置未等待 Promise，失败会逃逸 try/catch

- **定位**：`src/composables/useAgentBackend.js:239-246`。
- **功能**：将 Agent 设置 JSON 复制到剪贴板。
- **缺陷**：`navigator.clipboard.writeText(...)` 返回 Promise，函数未声明 async 且未 `await`；同步 `try/catch` 无法捕获权限拒绝或不安全上下文造成的异步 rejection。
- **影响**：复制失败时用户看不到“复制失败”提示，控制台可能出现未处理 rejection。
- **证据**：实码可证；权限拒绝场景待实测。
- **建议**：改为 async/await 或显式 `.catch()`，并复用已有 `useClipboard` 的兜底策略。

### FESTATE-06 [P2] navigation.activeTool 未覆盖已暴露的 projectGenerator 状态

- **定位**：`src/stores/navigation.js:45,71-76,229-240`。
- **功能**：统一报告当前打开的工具。
- **缺陷**：`showTool('projectGenerator')` 会将 `showProjectGenerator` 设为 true，但 `activeTool` 的计算分支没有检查它，因此该状态下返回 `null`。
- **影响**：任何依赖 `activeTool` 做当前工具识别、埋点或恢复的调用方会得到错误结果。当前全库没有生产消费 `activeTool`，因此属于未接入契约缺陷。
- **证据**：实码可证；当前影响范围待接入方出现后实测。
- **建议**：将 `projectGenerator` 纳入 activeTool，或删除未使用的统一状态接口并保留单一导航来源。

### FESTATE-07 [P2] GitHub token 同时以可逆编码和 Pinia 明文状态持久化

- **定位**：`src/stores/github.js:20-36,43-50,93-99`。
- **功能**：保存 GitHub 配置供项目生成器使用。
- **缺陷**：自定义 hex 编码可直接逆向；同时 Pinia persist 配置包含 `githubToken`，会将 token 以 `github-store` 状态写入 localStorage。该路径绕过了“仅保存编码 token”的意图。
- **影响**：任意能够读取当前站点 localStorage 的脚本或浏览器扩展可取得 GitHub token，造成账户权限泄露风险。
- **证据**：实码可证；实际 localStorage 内容可用浏览器实测确认。
- **建议**：优先改为后端托管/短期凭证；至少移除 persist 中的 token 字段，避免把可逆编码当作保护措施。

## 4. 潜在问题与未知点

- **竞态待实测**：`useAgentStreaming.streamGenerate:411-451` 没有 composable 内部的并发锁；若 UI 事件绕过按钮禁用或重复触发，多个 SSE 消费者会共同写入同一组 files/workspace/generation 状态。
- **竞态待实测**：Dashboard 的 `watch(..., { deep: true })` 与 `onMounted` 的后端加载并行执行；会话 ID、生成阶段和文件数组的快照时序需要浏览器刷新/快速切换场景确认。
- **错误吞噬待实测**：未知 SSE 类型在 `useAgentStreaming.js:278-280` 静默忽略；`handleSseMessage` 多个事件字段使用 `|| 0`，合法的空值/零值语义可能被覆盖。
- **数据一致性待实测**：`providers.listProviders:35-45` 网络失败直接返回 `[]`，调用方可能将已有离线缓存视为无供应商；应确认 UI 是否在失败时保留缓存。
- **状态双轨**：`agentSession` store 与六个 Agent composable 之间存在重复的阶段、模型分配和工作区概念；`agentWorkspace` store 仍保存另一份同名字段。当前全库消费结果支持“旧 store 废弃、composable 轨道活跃”，迁移完成度需要结合版本历史确认。
- **资源边界待实测**：`useToast` 的定时器、`useFileDrop` 的 body 级拖放监听和 `useKeyboardShortcuts` 的全局监听都有组件生命周期清理，但重复挂载/热更新下的行为尚未有自动化覆盖。

## 5. 修改建议

| # | 优先级 | 修改动作 | 达成目的 | 涉及位置 | 对应缺陷 |
|---|---|---|---|---|---|
| 1 | P1 | 统一 Agent 会话快照结构，实现保存、恢复、自动保存和切换恢复 | 保证刷新/切换不丢文件与运行状态 | `useAgentSession.js`、`agentSession.js`、`AgentDashboard.vue` | FESTATE-01 |
| 2 | P1 | 将离线队列接入实际发送函数，增加入队、恢复、顺序和重试策略 | 使离线消息具备可执行链路 | `useOfflineQueue.js`、`components/index.vue` | FESTATE-02 |
| 3 | P1 | 修正 Pinia setup store 的 watcher 访问方式并补充过滤/新增日志测试 | 恢复运行期间日志持久化 | `SystemLogs.vue`、`logs.js` | FESTATE-03 |
| 4 | P2 | 按 SSE 标准处理字段、空行事件、尾帧和解析错误 | 提升流式状态更新的协议鲁棒性 | `useAgentStreaming.js` | FESTATE-04 |
| 5 | P2 | 统一剪贴板 helper 的 async 错误处理 | 保证失败可提示且无未处理 rejection | `useAgentBackend.js`、`useClipboard.js` | FESTATE-05 |
| 6 | P2 | 收敛导航工具枚举，补齐 `projectGenerator` 或移除未消费 activeTool | 消除导航状态契约分裂 | `navigation.js` | FESTATE-06 |
| 7 | P2 | 取消客户端 token 持久化，迁移到后端/短期凭证机制 | 降低 GitHub 凭证泄露面 | `github.js`、相关 API | FESTATE-07 |
| 8 | P3 | 删除或明确退役 `task.js`、`agentWorkspace.js`、`useMarkdown.js`、`useClipboard.js` 等零消费轨道 | 降低双轨维护和误接线风险 | 对应文件、文档/变更记录 | 状态治理 |

## 6. 测试缺口

- **Store 单元测试**：补充 user token 恢复/清理、apikey 同步失败和过期判断、providers 缓存回退、navigation projectGenerator/activeTool、logs watcher 持久化、github token 持久化策略。
- **AgentDashboard 组装测试**：验证生成 -> SSE 事件 -> files/workspace/generation 的字段映射，验证完成、失败、停止、重生成和快速重复提交。
- **会话恢复测试**：在生成中途刷新、切换两个会话、删除当前会话、卸载组件时验证完整快照及文件版本。
- **SSE 测试**：覆盖 `data:{json}`、`data: {json}`、多 data 行、无换行尾帧、分片 JSON、解析失败和未知事件；确认失败后 `isGenerating` 最终归零。
- **离线队列测试**：覆盖断网入队、刷新恢复、网络恢复顺序发送、单条失败后的剩余队列、无 callback、localStorage 损坏和容量异常。
- **Composable 生命周期测试**：验证 toast 定时器、keyboard shortcuts、body/元素双层 drag listener 的挂载卸载与重复挂载行为。
- 当前 `tests/` 中未发现针对 `src/stores/` 或 `src/composables/` 的直接单元测试；可沿用项目既有 Vitest 前端测试目录约定 `tests/frontend/`，并增加浏览器级网络模拟用例。

## 7. 演化方向关联

- **拆分解耦**：当前 AgentDashboard 已完成 UI 与逻辑拆分，但 `useAgentSession`、`agentSession`、`agentWorkspace` 仍形成旧 store 与新 composable 双轨，应建立单一状态契约。
- **统一收敛**：优先收敛会话快照、日志持久化和离线队列入口；所有异步请求应返回统一的成功/失败语义，避免 `[]`、`null` 和吞错混用。
- **智能增强**：SSE 事件应使用显式 schema/事件版本，角色别名和阶段映射由共享契约提供，减少 `useAgentStreaming` 内硬编码。
- **平台化**：状态持久化、凭证保存、离线队列和流式恢复需要统一生命周期与存储策略；GitHub/API Key 等凭证逐步迁移到后端托管或短期令牌。

## 8. 第 163 轮分批重扫修订

- FESTATE-01 至 FESTATE-07 全部保留；`switchSession` 未导出、首页 `/code` 流跨 chunk 丢数据和 Agent SSE 重连队列竞争形成新增证据。
- 会话审批归属、删除会话清理、跨 worker 创建锁和生成并发幂等问题见 [frontend_batch_rescan.md](frontend_batch_rescan.md) 的 FRESCAN-05 至 FRESCAN-11。
- `FESTATE-04` 的主路径当前兼容后端单行帧，标准 SSE 多行、空行和尾帧场景仍需运行验证。

## 9. 第 164 轮复扫修订

- 新增 `FRESCAN-46` 至 `FRESCAN-48`：Agent 会话、API Key/供应商/模型覆盖和管理日志使用固定 localStorage 键，注销流程未清理，形成跨账户复用风险。
- 新增 `FRESCAN-49`：`WebSocketManager.disconnect()` 没有手动关闭标记，异步 `onclose` 仍会安排自动重连。
- `FRESCAN-05` 的 SSE 队列竞争与本轮 `FRESCAN-49` 的 WebSocket 生命周期竞态属于不同传输实现，保持独立登记。
