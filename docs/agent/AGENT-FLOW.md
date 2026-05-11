# Agent 流程文档

> 最后更新: 2026-05-11 | 版本: v1.0

本文档详细描述项目中 AI Agent 的完整架构、工作流程和各组件的协作关系。

## 目录

- [架构概览](#架构概览)
- [核心组件](#核心组件)
- [工作流程](#工作流程)
- [模型注册与路由](#模型注册与路由)
- [专家角色](#专家角色)
- [执行器与工具](#执行器与工具)
- [ReAct 自我反思](#react-自我反思)
- [记忆系统](#记忆系统)
- [错误恢复](#错误恢复)
- [规范优先生成](#规范优先生成)

---

## 架构概览

项目采用多层 Agent 架构，支持从简单对话到复杂项目生成的全场景覆盖。

### 架构层次

```
┌─────────────────────────────────────────────────────────┐
│                    OrchestratorAgent                     │
│  (总指挥：复杂度分析 → 模型分配 → 角色协作 → 验证审查)      │
├─────────────────────────────────────────────────────────┤
│  Architect  │  FrontendEngineer  │  BackendEngineer      │
│  (架构师)    │  (前端工程师)       │  (后端工程师)          │
├─────────────────────────────────────────────────────────┤
│                    MultiModelAgent                       │
│  (多模型协调：任务路由 → 规划 → 执行 → 审查)                │
├─────────────────────────────────────────────────────────┤
│  ModelRegistry  │  ModelRouter  │  TaskPlanner           │
│  (模型注册表)     │  (模型路由)    │  (任务规划器)           │
├─────────────────────────────────────────────────────────┤
│  AgentExecutor  │  ToolRegistry  │  AIReviewer           │
│  (执行器)        │  (工具注册表)    │  (AI审查器)            │
├─────────────────────────────────────────────────────────┤
│  ReActAgent  │  EnhancedExecutor  │  StreamingExecutor   │
│  (ReAct模式)   │  (增强执行器)      │  (流式执行器)          │
└─────────────────────────────────────────────────────────┘
```

### 支持的项目类型

| 类型 | 描述 | 示例 |
|------|------|------|
| SIMPLE | 单文件脚本 | Hello World、简单工具 |
| SMALL | 小型项目（≤5 文件） | CLI 工具、简单 API |
| MEDIUM | 中型项目（6-15 文件） | Web 应用、数据处理 |
| LARGE | 大型项目（16-30 文件） | 完整前后端分离项目 |
| ENTERPRISE | 企业级项目（>30 文件） | 复杂业务系统 |

---

## 核心组件

### 1. OrchestratorAgent（总指挥）

**文件**: `app/agent/orchestrator.py`

OrchestratorAgent 是整个项目生成的核心协调器，负责：

- **复杂度分析**: 使用 LLM 辅助分析需求复杂度
- **模型分配**: 根据复杂度为各角色分配合适的模型
- **架构设计**: 调用 Architect 设计整体架构
- **文件生成**: 按依赖分层并发生成文件
- **验证审查**: 对每个文件进行验证和审查
- **错误恢复**: 自动生成失败时进行修复
- **增量更新**: 支持基于已有项目的增量生成

#### 主要方法

| 方法 | 描述 |
|------|------|
| `generate()` | 主入口，根据 spec_first 选项选择策略 |
| `generate_with_spec_first()` | 规范优先生成策略 |
| `_generate_traditional()` | 传统生成策略 |
| `_initialize_components()` | 初始化所有组件 |
| `_generate_single_file()` | 生成单个文件 |
| `_validate_and_review_file()` | 验证和审查文件 |
| `_handle_incremental_generation()` | 处理增量生成 |

#### 工作流程

```
1. 初始化组件
   ├── 分析复杂度 (ComplexityAnalyzer)
   ├── 分配模型 (LayeredModelRouter)
   └── 初始化角色 (Architect, Engineers, Reviewer)

2. 架构设计
   ├── Architect 设计架构
   ├── 生成文件计划
   └── 成本估算

3. 文件生成
   ├── 构建依赖图 (DependencyGraph)
   ├── 按分层并发生成
   └── 每个文件：生成 → 验证 → 审查 → 写入

4. 最终验证
   ├── 全项目验证 (CodeValidator)
   ├── 动态测试 (TestRunner)
   └── 保存记忆 (Memory)
```

### 2. MultiModelAgent（多模型协调器）

**文件**: `app/agent/multi_model_agent.py`

MultiModelAgent 提供通用的任务处理能力：

- **任务路由**: 根据内容自动识别任务类型
- **任务规划**: 将复杂任务分解为可执行步骤
- **执行审查**: 每步执行后进行质量审查
- **文件契约**: 确保文件操作安全

#### 任务类型

```python
class TaskType(Enum):
    GENERAL = "general"                    # 通用对话
    CODE_GENERATION = "code_generation"    # 代码生成
    CODE_REVIEW = "code_review"           # 代码审查
    FILE_OPERATION = "file_operation"      # 文件操作
    VISUAL_UNDERSTANDING = "visual"       # 视觉理解
    IMAGE_GENERATION = "image_generation" # 图像生成
    REASONING = "reasoning"               # 深度推理
    FAST_RESPONSE = "fast_response"      # 快速响应
    EMBEDDING = "embedding"               # 嵌入/相似度
    OCR = "ocr"                           # OCR识别
```

#### 处理流程

```
用户请求
  ↓
内容识别 → TaskType
  ↓
模型路由 → 选择最佳模型
  ↓
任务规划 → 分解为步骤
  ↓
计划审查 → AIReviewer 审查
  ↓
步骤执行 → 逐个执行
  ↓
文件契约 → 验证路径安全
  ↓
返回结果
```

---

## 工作流程

### 传统生成流程

```
┌─────────────┐
│  用户需求    │
└──────┬──────┘
       ↓
┌─────────────────────┐
│ ComplexityAnalyzer  │ ← 分析复杂度
│ (Simple/Small/      │
│  Medium/Large/      │
│  Enterprise)        │
└──────┬──────────────┘
       ↓
┌─────────────────────┐
│ LayeredModelRouter  │ ← 分配模型
│ (Architect/Qwen3-8B │
│  Frontend/Qwen2.5   │
│  Backend/DeepSeek   │
│  Reviewer/GLM-Z1)   │
└──────┬──────────────┘
       ↓
┌─────────────────────┐
│     Architect       │ ← 设计架构
│ (技术栈 + 文件计划   │
│  + API 规范          │
│  + DB Schema)       │
└──────┬──────────────┘
       ↓
┌─────────────────────┐
│  DependencyGraph    │ ← 构建依赖
│ (按优先级分层        │
│  同层内无依赖可并行)  │
└──────┬──────────────┘
       ↓
┌─────────────────────┐
│  File Generation    │ ← 分层生成
│ (按层顺序，层内并行   │
│  并发限制: 4)        │
└──────┬──────────────┘
       ↓
┌─────────────────────┐
│ Validation & Review │ ← 验证审查
│ (语法检查 + 质量审查 │
│  + 错误恢复)         │
└──────┬──────────────┘
       ↓
┌─────────────────────┐
│   Final Validation  │ ← 最终验证
│ (全项目验证 + 测试)  │
└─────────────────────┘
```

### 规范优先生成流程 (Spec-First)

```
┌─────────────┐
│  用户需求    │
└──────┬──────┘
       ↓
┌─────────────────────┐
│ ComplexityAnalyzer  │ ← 分析复杂度
└──────┬──────────────┘
       ↓
┌─────────────────────┐
│ SpecFirstGenerator  │ ← 生成规范
│ ├── OpenAPI 规范    │
│ ├── 类型定义        │
│ ├── DB Schema       │
│ └── 配置规范        │
└──────┬──────────────┘
       ↓
┌─────────────────────┐
│     Architect       │ ← 架构设计
│ (基于规范生成文件计划)│
└──────┬──────────────┘
       ↓
┌─────────────────────┐
│  DependencyGraph    │ ← 构建依赖
│ (结合规范 + 架构)    │
└──────┬──────────────┘
       ↓
┌─────────────────────┐
│ CrossValidator      │ ← 交叉验证
│ (关键文件双模型生成   │
│  + 评审员裁决)       │
└──────┬──────────────┘
       ↓
┌─────────────────────┐
│ RefinementLoop      │ ← 迭代修复
│ (验证 → 修复循环     │
│  最多 3 次尝试)      │
└──────┬──────────────┘
       ↓
┌─────────────────────┐
│   Final Validation  │ ← 最终验证
└─────────────────────┘
```

---

## 模型注册与路由

### 模型注册表

**文件**: `app/agent/multi_model_agent.py`

项目注册了以下模型：

| 键名 | 模型名称 | 能力 | 最大 Token | 速度 |
|------|---------|------|-----------|------|
| deepseek-r1-qwen3-8b | DeepSeek-R1-0528-Qwen3-8B | REASONING, CODE | 8192 | 0.7 |
| deepseek-ocr | DeepSeek-OCR | OCR, VISION | 2048 | 1.0 |
| qwen3.5-4b | Qwen/Qwen3.5-4B | FAST | 4096 | 2.0 |
| qwen3-8b | Qwen/Qwen3-8B | REASONING, FAST | 4096 | 1.5 |
| qwen2.5-7b | Qwen/Qwen2.5-7B-Instruct | CODE, FAST | 4096 | 1.8 |
| glm-4.1v-9b | THUDM/GLM-4.1V-9B-Thinking | VISION, REASONING | 4096 | 0.8 |
| glm-4-9b | THUDM/GLM-4-9B-0414 | FAST, CODE | 4096 | 1.6 |
| glm-z1-9b | THUDM/GLM-Z1-9B-0414 | REASONING | 4096 | 0.9 |
| kolors | Kwai-Kolors/Kolors | CREATIVE | 512 | 0.5 |
| bce-embedding | netease-youdao/bce-embedding-base_v1 | EMBEDDING | 512 | 1.0 |

### 静态路由策略

```python
TASK_MODEL_MAP = {
    TaskType.GENERAL: ["qwen3-8b", "deepseek-r1-qwen3-8b"],
    TaskType.CODE_GENERATION: ["qwen2.5-7b", "deepseek-r1-qwen3-8b"],
    TaskType.CODE_REVIEW: ["deepseek-r1-qwen3-8b", "glm-z1-9b"],
    TaskType.FILE_OPERATION: ["glm-4-9b", "qwen3.5-4b"],
    TaskType.VISUAL_UNDERSTANDING: ["glm-4.1v-9b", "deepseek-ocr"],
    TaskType.IMAGE_GENERATION: ["kolors"],
    TaskType.REASONING: ["deepseek-r1-qwen3-8b", "glm-z1-9b"],
    TaskType.FAST_RESPONSE: ["qwen3.5-4b", "glm-4-9b"],
    TaskType.EMBEDDING: ["bce-embedding"],
    TaskType.OCR: ["deepseek-ocr"],
}
```

### 动态路由

**文件**: `app/agent/dynamic_model_router.py`

动态路由基于实时健康指标选择模型：

- **健康监控**: 跟踪每个模型的调用成功率、延迟
- **熔断机制**: 失败率过高时自动熔断
- **重试策略**: 主模型失败时自动切换备选模型

---

## 专家角色

**文件**: `app/agent/specialists.py`

### Architect（架构师）

- **职责**: 技术选型、架构设计、API 规范、数据库 Schema
- **使用模型**: GLM-Z1-9B (深度推理) / Qwen3-8B (简单任务)
- **输出**: JSON 格式架构设计

```json
{
  "project_type": "fullstack",
  "tech_stack": ["FastAPI", "Vue3", "SQLite"],
  "directory_structure": {"src": ["main.py", "api/"]},
  "file_plan": [{"path": "main.py", "description": "入口", "priority": 1}],
  "api_spec": {"paths": {"/api/v1/health": {...}}},
  "db_schema": {"users": {"columns": {...}}},
  "dependencies": {"fastapi": ">=0.100.0"},
  "risks": ["并发处理"]
}
```

### FrontendEngineer（前端工程师）

- **职责**: 前端文件生成（Vue/React/HTML/CSS/JS）
- **使用模型**: Qwen2.5-7B-Instruct (快速) / Qwen3-8B (企业级)
- **规则**: 每次只创建一个文件，代码完整可运行

### BackendEngineer（后端工程师）

- **职责**: 后端文件生成（Python/FastAPI/数据库模型）
- **使用模型**: DeepSeek-R1-Qwen3-8B (代码推理)
- **规则**: 包含错误处理、类型注解、完整代码

### CodeReviewer（代码审查员）

- **职责**: 代码质量和安全审查
- **使用模型**: GLM-Z1-9B + DeepSeek-R1 (双重审查)
- **审查维度**: 安全性、正确性、性能、可维护性、版本兼容性

---

## 执行器与工具

### EnhancedExecutor（增强执行器）

**文件**: `app/agent/executor.py`

支持的工具类型：

| 工具 | 描述 | 参数 |
|------|------|------|
| read_file | 读取文件 | path |
| write_file | 写入文件 | path, content |
| list_files | 列出文件 | path, pattern |
| execute_code | 执行 Python 代码 | code, timeout |
| web_search | 网络搜索 | query, limit |
| http_request | HTTP 请求 | method, url, headers, body |

### 代码执行沙箱

执行 Python 代码时使用受限沙箱：

- **禁止函数**: exec, eval, compile, __import__, open, getattr, setattr
- **安全全局**: 只保留安全的内置函数（print, len, range, list, dict 等）
- **AST 检查**: 执行前进行语法树分析，拦截危险调用

### StreamingExecutor（流式执行器）

继承 EnhancedExecutor，支持流式输出：

```python
executor.set_stream_callback(lambda text: print(text, end=''))
result = await executor.execute_with_stream(step)
```

---

## ReAct 自我反思

**文件**: `app/agent/react_agent.py`

ReAct (Reasoning + Acting) 模式包含四个阶段：

### 循环流程

```
┌──────────┐
│ Thought  │ ← 分析任务，决定下一步
└────┬─────┘
     ↓
┌──────────┐
│  Action  │ ← 执行工具调用
└────┬─────┘
     ↓
┌────────────┐
│Observation │ ← 分析执行结果
└────┬───────┘
     ↓
┌───────────┐
│Reflection │ ← 判断是否继续或结束
└────┬──────┘
     ↓
  继续? ──Yes──→ 下一轮循环
   │
   No
   ↓
┌────────────┐
│Final Answer│ ← 生成最终答案
└────────────┘
```

### ReActAgent 特性

- **最大迭代**: 默认 10 次
- **记忆系统**: 集成 AgentMemory 记录反思
- **流式输出**: 支持实时推送思考过程
- **降级策略**: ReActWithFallback 支持模型切换

### ReActWithFallback

```python
fallback = ReActWithFallback()
result = await fallback.process(task, context)
# 主模型失败时自动切换到备用模型，最多重试 2 次
```

---

## 记忆系统

**文件**: `app/agent/memory.py`

### 记忆类型

| 类型 | 描述 | 用途 |
|------|------|------|
| ConversationMemory | 对话记忆 | 记录用户消息和助手回复 |
| KnowledgeMemory | 知识记忆 | 存储项目技术栈和关键决策 |
| ReflectionMemory | 反思记忆 | 记录执行反思和经验教训 |

### MemoryEntry 结构

```python
@dataclass
class MemoryEntry:
    type: str           # 记忆类型
    content: str        # 记忆内容
    importance: float   # 重要度 (0.0-1.0)
    metadata: Dict      # 元数据
    timestamp: float    # 时间戳
```

### 使用场景

- **项目生成**: 保存架构设计和技术栈到知识记忆
- **错误恢复**: 记录修复经验到反思记忆
- **上下文构建**: 为后续生成提供历史上下文

---

## 错误恢复

### ErrorRecoveryLoop

**文件**: `app/agent/error_recovery.py`

自动修复循环：

```
文件生成
  ↓
验证失败
  ↓
┌─────────────────┐
│ 错误分析        │ ← 分析错误类型
├─────────────────┤
│ 修复策略选择    │ ← 选择修复方法
├─────────────────┤
│ 重新生成        │ ← 调用 LLM 修复
├─────────────────┤
│ 验证修复结果    │ ← 再次验证
└────────┬────────┘
         ↓
    成功? ──Yes──→ 继续
     │
     No (最多 3 次)
     ↓
   记录失败，继续下一个文件
```

### RefinementLoop

**文件**: `app/agent/refinement_loop.py`

规范优先生成中的迭代修复：

- **验证**: 语法检查、导入验证
- **修复**: 基于错误信息针对性修复
- **循环**: 最多 3 次尝试

---

## 规范优先生成

**文件**: `app/agent/spec_first_generator.py`

### 生成流程

```
1. OpenAPI 规范生成
   ├── 分析需求
   ├── 定义 API 端点
   ├── 定义请求/响应 Schema
   └── 输出 OpenAPI 3.0 JSON

2. 类型定义生成
   ├── 基于 OpenAPI Schema
   ├── 生成 Pydantic 模型
   └── 输出 Python 类型文件

3. 数据库 Schema 生成
   ├── 基于实体关系
   ├── 生成 SQLAlchemy Model
   └── 输出数据库模型文件

4. 配置规范生成
   ├── 环境变量定义
   ├── .env.example 模板
   └── 配置加载代码
```

### 优势

- **前后端一致**: 基于统一规范生成，减少 API 不一致
- **类型安全**: 自动生成类型定义，减少运行时错误
- **可维护性**: 规范文档可作为后续开发参考

---

## 附录

### 关键配置参数

| 参数 | 默认值 | 描述 |
|------|--------|------|
| MAX_CONCURRENT_LLM_CALLS | 4 | 最大并发 LLM 调用数 |
| MAX_CONTENT_FOR_CONTEXT | 3000 | 依赖上下文最大内容长度 |
| enable_review | True | 启用代码审查 |
| enable_validation | True | 启用验证 |
| enable_error_recovery | True | 启用错误恢复 |
| memory_enabled | True | 启用记忆系统 |
| spec_first | True | 使用规范优先生成 |
| dependency_graph | True | 使用依赖图 |

### 进度事件类型

OrchestratorAgent 推送的进度事件：

```python
{
    "type": "progress",
    "step": "正在生成文件",
    "phase": "generating",
    "current": 5,
    "total": 10,
    "percentage": 50.0,
    "elapsed_seconds": 120.5,
    "eta_seconds": 120.5,
    "file_path": "src/api/user.py",
    "model": "deepseek-ai/DeepSeek-R1-0528-Qwen3-8B"
}
```

### 文件路径验证

所有文件路径经过严格验证：

- **非法字符**: 只允许字母、数字、下划线、连字符、点、斜杠
- **路径深度**: 最大 5 层嵌套
- **文件扩展名**: 支持常见编程语言和配置文件扩展名
- **重复检查**: 禁止重复路径

---

**维护者**: MonkeyCode-AI Team
**文档版本**: v1.0
