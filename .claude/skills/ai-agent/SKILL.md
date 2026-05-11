# AI Agent - 多模型 Agent

## 功能说明

多模型 Agent 架构，集成项目生成、记忆系统、ReAct 反思能力。

## 架构

```
AI Agent System
├── AI Agent (app/agent/)
│   ├── MultiModelAgent     - 多模型路由
│   ├── ReActAgent          - 自我反思
│   ├── AgentMemory         - 记忆系统
│   │   ├── ConversationMemory - 对话记忆
│   │   ├── KnowledgeMemory    - 知识库
│   │   └── ReflectionMemory  - 反思记忆
│   └── EnhancedExecutor     - 增强执行器
│
├── AiProjectCode (app/api/v1/AiProjectCode.py)
│   ├── 项目生成
│   ├── 文件管理
│   └── 项目管理
│
└── 数据库模型 (app/models/agent_memory.py)
    ├── AgentSession        - 会话记录
    ├── MemoryEntry         - 记忆条目
    ├── AgentReflection      - 反思记录
    ├── KnowledgeEntry       - 知识条目
    ├── ToolExecutionLog     - 工具日志
    └── ModelUsageStats      - 模型统计
```

## 模块职责

| 模块 | 职责 | 端点前缀 |
|------|------|----------|
| **AI Agent** | 多模型路由、ReAct 反思、记忆、知识库 | `/api/v1/ai_agent/*` |
| **AiProjectCode** | 项目生成、文件操作、项目管理 | `/api/v1/agent/*` |

## 模型配置

| 模型 | 用途 | 速度 |
|------|------|------|
| deepseek-ai/DeepSeek-R1-0528-Qwen3-8B | 深度推理、代码审查 | 0.7x |
| Qwen/Qwen2.5-7B-Instruct | 代码生成 | 1.8x |
| Qwen/Qwen3.5-4B | 快速响应 | 2.0x |
| THUDM/GLM-4.1V-9B-Thinking | 视觉理解 | 0.8x |
| deepseek-ai/DeepSeek-OCR | OCR识别 | 1.0x |
| Kwai-Kolors/Kolors | 图像生成 | 0.5x |

## 任务类型

| 类型 | 路由关键词 | 模型 |
|------|-----------|------|
| code_generation | 代码、编写、写一个 | Qwen 2.5 7B |
| code_review | 审查、检查、优化 | DeepSeek R1 |
| visual | 图片、图像+分析 | GLM-4.1V |
| ocr | OCR、识别文字 | DeepSeek OCR |
| image_generation | 生成图片、画 | Kolors |
| reasoning | 推理、思考、分析 | DeepSeek R1 |
| fast_response | 短文本(<30字) | Qwen 3.5 4B |

## API 接口

### AI Agent 端点 (`/api/v1/ai_agent/`)

#### 核心处理

| 接口 | 方法 | 说明 |
|------|------|------|
| `process` | POST | 标准模式处理任务 |
| `react/process` | POST | ReAct 模式处理 |
| `react/stream` | POST | ReAct 流式处理 |
| `models` | GET | 模型列表 |
| `review` | POST | 内容审查 |

#### 会话与记忆

| 接口 | 方法 | 说明 |
|------|------|------|
| `sessions` | POST | 创建会话 |
| `sessions` | GET | 会话列表 |
| `sessions/{id}` | GET | 会话详情 |
| `sessions/{id}` | DELETE | 删除会话 |
| `memory/{session_id}` | GET | 获取记忆 |
| `memory/clear` | POST | 清除记忆 |

#### 知识库

| 接口 | 方法 | 说明 |
|------|------|------|
| `knowledge` | POST | 添加知识 |
| `knowledge` | GET | 知识列表 |
| `knowledge/search` | GET | 搜索知识 |

#### 统计

| 接口 | 方法 | 说明 |
|------|------|------|
| `stats/models` | GET | 模型使用统计 |

### AiProjectCode 端点 (`/api/v1/agent/`)

#### 项目生成

| 接口 | 方法 | 说明 |
|------|------|------|
| `generate` | POST | 生成项目（非流式） |
| `generate_stream` | POST | 生成项目（流式） |
| `generate_task` | POST | 异步任务生成 |
| `generate/status/{task_id}` | GET | 查询生成状态 |
| `generate/download/{path}` | GET | 下载项目 |

#### 项目管理

| 接口 | 方法 | 说明 |
|------|------|------|
| `save` | POST | 保存项目 |
| `saved` | GET | 项目列表 |
| `saved/{id}` | GET | 加载项目 |
| `saved/{id}` | DELETE | 删除项目 |
| `search` | POST | 搜索项目 |

#### 文件操作

| 接口 | 方法 | 说明 |
|------|------|------|
| `read_paginated` | POST | 分页读取 |
| `grep` | POST | 搜索文件内容 |
| `edit` | POST | 编辑文件 |
| `create` | POST | 创建文件/目录 |
| `rename` | POST | 重命名 |
| `upload` | POST | 上传文件 |
| `delete/file` | DELETE | 删除文件 |
| `tree` | GET | 文件树 |
| `diff` | POST | 文件对比 |
| `stats` | GET | 项目统计 |
| `batch` | POST | 批量操作 |
| `copy` | POST | 复制项目 |

## 数据模型

### AgentSession

记录每个项目生成会话：

```python
{
    "id": "uuid",
    "user_id": 1,
    "session_type": "code_generation",
    "model_key": "deepseek-r1-qwen3-8b",
    "context_summary": "用户请求生成...",
    "total_steps": 5,
    "total_tokens": 12345,
    "success": True,
    "created_at": "2024-01-01T00:00:00Z"
}
```

### ToolExecutionLog

记录每次工具执行：

```python
{
    "session_id": "uuid",
    "tool_name": "generate_project",
    "tool_params": {"requirement": "...", "output_dir": "..."},
    "tool_result": "...",
    "success": True,
    "execution_time": 12.34
}
```

### ModelUsageStats

模型使用统计：

```python
{
    "user_id": 1,
    "model_key": "deepseek-r1-qwen3-8b",
    "request_count": 100,
    "total_tokens": 500000,
    "success_count": 95,
    "failure_count": 5,
    "avg_execution_time": 5.2
}
```

## ReAct 模式

ReAct (Reasoning + Acting) 循环：

```
Thought → Action → Observation → Reflection → ...
```

特点：
- 自我反思能力
- 自动回退和重试
- 状态跟踪
- 流式输出支持

### 请求示例

```json
POST /api/v1/ai_agent/react/process
{
    "task": "帮我创建一个 Python Web 服务器",
    "enable_streaming": false,
    "max_iterations": 10,
    "use_fallback": true
}
```

### 响应示例

```json
{
    "success": true,
    "final_answer": "已创建 Python Web 服务器...",
    "total_steps": 5,
    "execution_time": 12.34,
    "reflection_summary": "成功完成了任务",
    "steps": [
        {"type": "thought", "content": "需要创建...", "success": true},
        {"type": "action", "tool": "create_file", "success": true},
        {"type": "observation", "content": "文件创建成功", "success": true},
        {"type": "reflection", "content": "任务完成", "success": true}
    ]
}
```

## 安全机制

### FileContract

验证文件操作的路径和内容安全性。

### 路径保护

禁止访问：
- `/etc`, `/root`, `/proc`, `/sys`, `/boot`, `/dev`
- `/var/log`, `/var/cache`, `/var/run`, `/tmp`

### 敏感文件保护

禁止操作：
- `.env`, `.git/config`
- `id_rsa`, `id_ed25519`
- `known_hosts`, `authorized_keys`

### 危险模式检测

- `rm -rf /` - 递归删除
- `fork()` - Fork炸弹
- `exec()` - 危险命令执行
- `subprocess.call()` - 子进程调用
- `os.system()` - 系统命令执行

## 代码位置

| 模块 | 文件 |
|------|------|
| 多模型 Agent | `app/agent/multi_model_agent.py` |
| ReAct Agent | `app/agent/react_agent.py` |
| 记忆系统 | `app/agent/memory.py` |
| 执行器 | `app/agent/executor.py` |
| 数据库模型 | `app/models/agent_memory.py` |
| Memory Service | `app/services/agent_memory_service.py` |
| Agent API | `app/api/v1/ai_agent.py` |
| 项目 API | `app/api/v1/AiProjectCode.py` |
| 前端组件 | `src/components/AiAgent.vue` |
| Skill 文档 | `.claude/skills/ai-agent/SKILL.md` |
