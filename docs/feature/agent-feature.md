# Agent 功能特性文档

## 概述

CodingMatrix Agent 是一个基于 ReAct (Reasoning + Acting) 模式的智能任务处理系统。它允许用户通过自然语言与 AI 进行多轮对话，Agent 会自动分析问题、选择工具、执行任务并返回结果。

## 架构组成

### 1. 前端 Agent 工作台 (`src/components/AgentChat.vue`)

- **路由路径**: `/agent` (新标签页打开)
- **状态管理**: `useAgentChat` composable + `userStore`
- **核心功能**:
  - 多轮对话管理
  - SSE 流式输出 (实时展示思考过程)
  - 会话切换与历史查看
  - 知识库管理 (添加/删除知识条目)
  - 面板展开/收起

### 2. 后端 Agent 模块 (`app/api/agent.py`)

- **路由前缀**: `/api/v1/agent`
- **核心端点**:
  - `POST /process` - 处理任务 (同步)
  - `POST /chat` - Agent 对话 (同步)
  - `POST /chat/stream` - 流式对话 (SSE)
  - `GET /sessions` - 会话列表
  - `GET /sessions/{id}` - 会话详情
  - `DELETE /sessions/{id}` - 删除会话
  - `GET/POST /knowledge` - 知识管理
  - `GET /stats` - 统计信息

### 3. Orchestrator (`app/agent/orchestrator.py`)

- **核心职责**: 任务分解、工具路由、结果聚合
- **ReAct 循环**:
  1. **Thought**: 分析问题，决定下一步动作
  2. **Action**: 选择并调用工具
  3. **Observation**: 获取工具执行结果
  4. **Final Answer**: 综合所有信息生成回答

### 4. 工具集 (`app/agent/tools/`)

Agent 可以调用的工具包括:
- `CodeGenerator` - 代码生成工具
- `WebSearcher` - 网络搜索工具
- `FileReader` - 文件读取工具
- `Calculator` - 计算器
- `KnowledgeRetriever` - 知识库检索

## 模型路由

Agent 使用 `ModelRouter` 根据任务类型自动选择最合适的 AI 模型:

| 任务类型 | 模型 | 说明 |
|----------|------|------|
| 通用对话 | Qwen Turbo | 快速响应 |
| 代码生成 | Qwen Plus | 代码理解强 |
| 复杂推理 | Qwen Max | 推理能力强 |
| 视觉分析 | Qwen VL | 支持图片理解 |

## 会话管理

- **存储**: JSON 文件 (`data/agent-sessions/`)
- **格式**:
  ```json
  {
    "session_id": "uuid",
    "user_id": "user_id",
    "created_at": "ISO 8601",
    "updated_at": "ISO 8601",
    "messages": [
      {"role": "user", "content": "..."},
      {"role": "assistant", "content": "..."}
    ],
    "knowledge_ids": ["uuid1", "uuid2"]
  }
  ```
- **过期策略**: 30 天未活跃的会话自动清理

## 知识库

- **存储**: JSON 文件 (`data/agent-knowledge/`)
- **格式**:
  ```json
  {
    "id": "uuid",
    "user_id": "user_id",
    "title": "知识标题",
    "content": "知识内容",
    "created_at": "ISO 8601"
  }
  ```
- **用途**: Agent 对话时会自动检索相关知识作为上下文

## 使用流程

1. 登录系统 (normal 及以上权限)
2. 点击左侧导航 "Agent 工作台" 或访问 `/agent`
3. 在输入框输入问题或任务描述
4. Agent 自动分析问题并执行任务
5. 实时查看 Agent 的思考过程和结果
6. 可切换会话、查看历史、管理知识库

## 权限要求

- **最低权限**: normal (普通用户)
- **会话隔离**: 用户只能看到自己的会话
- **知识隔离**: 用户只能管理自己的知识

## 技术实现细节

### SSE 流式输出格式

```
event: thought
data: {"content": "我需要查询用户信息..."}

event: action
data: {"tool": "knowledge_retriever", "input": "用户管理"}

event: observation
data: {"result": "找到 3 条相关知识..."}

event: final
data: {"content": "完整的回答内容..."}
```

### 错误处理

- **模型调用失败**: 自动重试 3 次，指数退避
- **工具执行超时**: 60 秒超时，返回超时错误
- **会话不存在**: 返回 404
- **权限不足**: 返回 403

## 未来扩展

- 支持更多工具类型 (数据库查询、API 调用等)
- 支持多 Agent 协作
- 支持 Agent 技能插件系统
- 支持对话质量评估和反馈
