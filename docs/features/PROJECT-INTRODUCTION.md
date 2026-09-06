# CodingMatrix 项目功能介绍

> 最后更新：2026-09-03

CodingMatrix 是一个基于 FastAPI 与 Vue 3 的 AI 开发平台，覆盖智能对话、项目生成、多 Agent 协作、模型配置、演示文稿生成、AI Cloud 沙箱和知识库等能力。

## 核心能力

### 智能开发与 Agent 协作

- 支持流式 AI 对话、代码生成、任务取消和会话管理。
- 多 Agent 流程按 architect、frontend、backend、reviewer、fallback 五类角色分配模型。
- 动态模型路由可依据调用成功率、近期延迟和活动请求数选择候选模型，并在连续失败时使用配置的降级模型。
- 项目生成流程包含任务状态、检查点和产物记录；具体能力以对应 API 和 Agent 实现为准。

### 模型与供应商

- 用户端模型浏览接口位于 `/api/v1/models`。
- 超级管理员统一配置接口位于 `/api/v2/model-config`，管理模型、供应商、Agent 角色和降级链。
- 管理面配置保存在 `data/unified_model_config.yaml`，保存后派生 `data/agent_model_config.yaml` 并刷新运行时映射。
- `/api/v1/providers` 支持添加 OpenAI 兼容或 Anthropic 原生动态供应商、同步模型、测试连接和启停。该接口使用进程内存储，服务重启后配置需要重新添加。

### PPT Agent

- 支持创建、版本化编辑和批准用户作用域的大纲，再从已批准快照创建生成任务。
- 生成任务按 planning、assets、rendering、rule_qa、reflow、vision_qa、completed 阶段编排。
- 提供规则质量检查、自动 reflow、可选视觉复审、质量报告和单页重生成。
- 语义页面描述包含页面类型、叙事角色、核心信息、内容块、素材意图和证据来源。
- 代码提供 9 种渲染主题；模板预设与渲染主题属于两个独立层次。

详见 [PPT Agent](PPT-AGENT.md)。

### GirlAI

- 提供 5 个预设角色和用户自定义角色。
- 支持对话、分页历史、搜索、导出、历史清理、偏好提取和偏好删除。
- 对话同时维护旧版聊天记录与统一会话状态，归档任务会生成摘要检查点并清理已归档消息。
- 前端支持角色管理、历史搜索、拖拽缩放、最小化、自动隐藏和 Document Picture-in-Picture。

详见 [GirlAI](GIRLAI.md)。

### AI Cloud

- 管理员可使用同步或流式聊天、沙箱文件读写、历史搜索与导出、审查队列、审计日志、模型浏览和代码执行。
- 知识库支持文档上传、解析、分块、向量化、检索、列表和删除，并按用户隔离数据。
- 聊天数据同时写入 AI Cloud 旧版表与统一会话/消息状态。

详见 [AI Cloud](AICLOUD.md)。

## 技术架构

### 后端

- FastAPI、SQLAlchemy 异步会话和 Alembic 迁移。
- SQLite 为默认关系型存储；Redis 用于 API Key、缓存、限流及 Celery Broker 等运行时能力。
- Celery 处理异步任务，PPT API 与 Worker 通过共享产物目录交换生成文件。
- JWT、角色权限、CSRF 组件、路径保护和速率限制组成安全边界。
- 健康检查和 Prometheus 文本指标位于 `/api/v1/health`；OpenTelemetry 追踪由运行时配置决定是否启用。

### 前端

- Vue 3、Vite 5、Vue Router、Pinia 和 Element Plus。
- ECharts 用于图表，Vitest 与 Playwright 用于测试。
- SSE 和 WebSocket 用于流式响应与任务进度。

## 当前边界

- 动态供应商、统一模型供应商和用户 API Key 供应商是三条独立配置链，生命周期和持久化方式不同。
- 模型健康路由的实时指标保存在进程内；学习路由的历史统计保存在 `/tmp/model_performance.db`。
- PPT 的 PDF 转换接口直接调用 LibreOffice，缺失时返回 HTTP 501；Poppler 不能替代该转换命令。当前容器定义未安装 LibreOffice。

## 相关文档

- [快速开始](../guides/GETTING-STARTED.md)
- [架构设计](../architecture/ARCHITECTURE.md)
- [API 文档](../api/API-DOCUMENTATION.md)
- [安全说明](../security/SECURITY-OVERVIEW.md)
