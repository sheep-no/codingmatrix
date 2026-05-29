# CodingMatrix 项目功能介绍

> 最后更新：2026-05-27 | 版本：v5.10.0

CodingMatrix 是一个基于 AI 的智能代码生成平台，支持多供应商集成、智能项目生成、Agent 协作开发等功能。

## 核心功能

### 1. 智能对话与代码生成

- **AI 对话助手**：支持多轮对话，自动理解需求生成代码
- **多语言支持**：Python、JavaScript、TypeScript、Go、Rust 等主流语言
- **在线测试验证**：支持 Python 和 JavaScript 代码在线执行（基于 AI Cloud 沙箱）
- **流式输出**：实时展示生成进度，支持中途取消

### 2. 项目生成与开发

- **一键项目生成**：输入需求自动生成完整项目结构
- **Agent 协作开发**：多 Agent 分工合作（决策、执行、审查、修复、反思）
- **Git 集成**：支持 GitHub 推送、分支管理、PR 创建
- **工作流管理**：可视化 DAG 工作流，支持审批和执行

### 3. 多供应商支持

- **内置供应商**：硅基流动 (SiliconFlow)、阿里百炼 (DashScope)、智谱 GLM、DeepSeek、OpenAI、Anthropic 等
- **动态供应商**：支持自定义 base_url + 协议类型（OpenAI 兼容 / Anthropic 原生）
- **自动模型拉取**：添加供应商后自动获取可用模型列表
- **故障转移机制**：主供应商不可用时自动切换到备用供应商
- **供应商健康检查**：实时监控供应商可用性和响应速度

### 4. API Key 管理

- **RSA 加密传输**：API Key 使用 RSA-2048 加密，确保传输安全
- **Redis 内存存储**：不落数据库，TTL 自动过期
- **多 Key 管理**：支持多个供应商 Key 同时配置
- **Token 使用统计**：展示今日、本月、总计 Token 使用量
- **按需选择模型**：设置页面可选择不同环节使用的模型和 Key

### 5. 特色功能

- **PPT 自动生成**：基于内容智能生成演示文稿
  - 自然语言输入：输入主题描述自动生成结构化大纲
  - 文本防溢出：自动拆分长文本、调整字号、截断处理
  - 自动搜图配图：根据关键词搜索图片并自动插入
  - 智能排版布局：根据内容类型自动选择最佳版式
  - 支持 8 种模板风格（现代、商务、创意、极简、学术、科技、教育、医疗）
  - 详见 [PPT Agent 文档](PPT-AGENT.md)
- **图像生成 (Kolors)**：文生图、图生图、智能修复
- **GirlAI 虚拟助手**：个性化 AI 伴侣
- **知识库管理**：上传文档构建项目知识库
- **文件管理与预览**：支持多种文件格式在线预览
- **任务队列**：异步任务处理，支持重试和状态监控
- **系统监控**：服务器资源监控、日志查看、服务管理
- **管理面板**：用户管理、速率限制、系统配置

## 技术架构

### 后端技术栈

- **框架**：FastAPI + Python 3.11+
- **数据库**：SQLite + SQLAlchemy ORM + Alembic 迁移
- **缓存**：Redis（API Key 存储、会话缓存、速率限制）
- **异步任务**：Celery + Redis Broker
- **安全**：JWT 认证、RSA 加密、CSRF Token、速率限制
- **监控**：OpenTelemetry 链路追踪、Prometheus 指标

### 前端技术栈

- **框架**：Vue 3 + Composition API
- **构建工具**：Vite 5
- **状态管理**：Pinia + pinia-plugin-persistedstate
- **UI 组件库**：Element Plus
- **路由**：Vue Router 4
- **图表**：ECharts 6
- **测试**：Vitest + Playwright (E2E)
- **实时通信**：WebSocket + SSE

## 相关文档

- [快速开始](../guides/GETTING-STARTED.md) - 环境配置和开发流程
- [架构设计](../architecture/ARCHITECTURE.md) - 系统架构和各组件职责
- [API 文档](../api/API-DOCUMENTATION.md) - 完整的 API 端点文档
- [安全说明](../security/SECURITY-OVERVIEW.md) - 安全机制和数据保护措施
