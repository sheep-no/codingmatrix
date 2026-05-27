# Agent 系统文档

> 最后更新：2026-05-27 | 版本：v5.10.0

### v5.10.0 更新

- **工作流节点扩展**: 新增 5 种节点类型（llm_call、conditional、human_approval、http_request、data_transform）
- **重试机制**: 每个节点可配置 RetryConfig（max_retries、retry_delay、backoff_factor）
- **失败策略**: 支持 fail（中断）和 skip（跳过继续）两种策略
- **条件分支**: conditional 节点支持 12 种运算符
- **资源限制**: 适配 8C8G 服务器（最大并发 4 节点，节点超时 300s，内存 512MB）

### v5.9.0 更新

- **API Key 全局化**: 所有前端功能均使用用户自定义 API Key（SiliconFlow 必填）
- **Token 使用统计**: `/agent/token-usage` 端点，展示今日/本月/总计 Token 消耗及按模型分布
- **Orchestrator 端点**: `POST /agent/orchestrate/stream` 流式生成，`POST /agent/modify` 增量修改，`POST /agent/evaluate` 需求评价
- **会话管理**: `POST /agent/session/{id}/action` 暂停/恢复/取消，`POST /agent/session/{id}/decision` 提交人工决策
- **快照管理**: `GET /agent/snapshots/{id}` 快照列表，`POST /agent/rollback/{id}` 回滚，`GET /agent/snapshot/diff` 对比
- **知识库**: `POST /agent/knowledge` 添加知识，`GET /agent/knowledge` 查询
- **需求联想**: `POST /agent/requirement-association` 需求关联分析
- **性能监控**: `GET /agent/performance` 性能指标统计

### v5.1.2 更新

- **API 客户端统一**: 移除 vision.js，统一通过 window.api Proxy 导出，新增 5 个缺失 API 方法
- **Vision 集成聊天**: 图片附件通过 files 字段传递给 /code 端点，后端自动识别处理
- **增量修改修复**: 按钮真正调用 modifyProjectStream，复用 sessionId 保持上下文
- **文件预览修复**: AgentDashboard 调用 readProjectFile 从后端获取文件内容
- **需求联想集成**: 输入框自动联想 (20+ 字符触发)，800ms 防抖，最多显示 5 条
- **AiCloud 审查开关**: toggleReview 调用后端 /aicloud/reviews/toggle 端点
- **内存泄漏修复**: AdminPanel setInterval/addEventListener 在 onBeforeUnmount 中正确清理
- **空指针防护**: file.path.split 添加安全保护 (ProjectGenerate.vue, AgentDashboard.vue)
- **死代码清理**: 删除 22 个未使用文件 (~5600 行)
- **功能完整性验证**: 250+ 事件处理方法均已定义，v-model 绑定完整，构建无错误

### v5.1.0 更新

- **Agent 401 修复**: 解决 Agent Dashboard 请求因 Token 丢失导致的 401 Unauthorized 错误
- **API 客户端代理导出**: 新增 Proxy 模式导出 `api`，确保命名导入也能获取到初始化后的实例
- **Token 获取增强**: `getValidToken()` 增加 `window.userStore`、`window.api._userStore`、`sessionStorage`、`localStorage` 多级回退
- **静态文件路由修复**: FastAPI `/static` 挂载路径从 `dist/` 修正为 `dist/static/`
- **调试日志清理**: 移除 `base.js`、`tokenManager.js`、`useAuth.js`、`user.js` 中的 console.log 调试语句

### v4.9.0 更新

- **代码结构重构**: Orchestrator 拆分为 6 个模块（orchestrator_progress.py、orchestrator_generation.py、orchestrator_files.py、orchestrator_testing.py、orchestrator_utils.py），Specialists 拆分为 5 个模块（specialist_base.py、architect.py、frontend_engineer.py、backend_engineer.py、code_reviewer.py）
- **性能优化**: LRU 缓存 500MB 硬限制、学习模型路由（80% 最优 +20% 探索）、并行生成
- **用户体验**: 用户偏好服务（SQLite JSON 存储）、ResourceGuard 动态并发（CPU/内存>70% 时降级）
- **测试覆盖**: 33 个新增单元测试，100% 通过

---

## 目录

- [概述](#概述)
- [架构组成](#架构组成)
- [前端 Agent 工作台](#前端-agent-工作台)
- [后端 API 端点](#后端-api-端点)
- [OrchestratorAgent 核心流程](#orchestratoragent-核心流程)
- [工具集与模型路由](#工具集与模型路由)
- [会话管理与增量修改](#会话管理与增量修改)
- [依赖图与跨文件分析](#依赖图与跨文件分析)
- [测试验证](#测试验证)
- [Git 保存](#git-保存)
- [六大优化方向](#六大优化方向)
- [分布式追踪](#分布式追踪)
- [提示词增强](#提示词增强)
- [GitHub 集成](#github-集成)
- [安全与权限](#安全与权限)

---

## 概述

CodingMatrix Agent 是一个基于 ReAct (Reasoning + Acting) 模式的智能任务处理与项目生成系统。它支持从简单对话到复杂项目生成的全场景覆盖，采用多层 Agent 架构，通过模型能力金字塔、审查层次深化、修复策略模式化等六大优化方向，实现了从粗放到精细化的演进。

### 支持的项目类型

| 类型 | 描述 | 示例 |
|------|------|------|
| SIMPLE | 单文件脚本 | Hello World、简单工具 |
| SMALL | 小型项目 (<=5 文件) | CLI 工具、简单 API |
| MEDIUM | 中型项目 (6-15 文件) | Web 应用、数据处理 |
| LARGE | 大型项目 (16-30 文件) | 完整前后端分离项目 |
| ENTERPRISE | 企业级项目 (>30 文件) | 复杂业务系统 |

---

## 架构组成

```
┌─────────────────────────────────────────────────────────┐
│ OrchestratorAgent │
│ (总指挥: 复杂度分析 -> 模型分配 -> 角色协作 -> 验证审查) │
├─────────────────────────────────────────────────────────┤
│ Architect │ FrontendEngineer │ BackendEngineer │
│ (架构师) │ (前端工程师) │ (后端工程师) │
├─────────────────────────────────────────────────────────┤
│ MultiModelAgent │
│ (多模型协调: 任务路由 -> 规划 -> 执行 -> 审查) │
├─────────────────────────────────────────────────────────┤
│ ModelRegistry │ ModelRouter │ TaskPlanner │
│ (模型注册表) │ (模型路由) │ (任务规划器) │
├─────────────────────────────────────────────────────────┤
│ AgentExecutor │ ToolRegistry │ AIReviewer │
│ (执行器) │ (工具注册表) │ (AI审查器) │
├─────────────────────────────────────────────────────────┤
│ ReActAgent │ EnhancedExecutor │ StreamingExecutor │
│ (ReAct模式) │ (增强执行器) │ (流式执行器) │
└─────────────────────────────────────────────────────────┘
```

```
┌─────────────────────────────────────────────────────────┐
│ Orchestrator │
│ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ │
│ │ 模型金字塔 │ │ 依赖图并发 │ │ 审查链调度 │ │
│ │ (智能路由) │ │ (动态调度) │ │ (串行分工) │ │
│ └──────────────┘ └──────────────┘ └──────────────┘ │
└────────────────────────┬────────────────────────────────┘
 │
┌────────────────────────┴────────────────────────────────┐
│ Specialist Agents │
│ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ │
│ │ 架构师 │ │ 前端工程师 │ │ 后端工程师 │ │
│ └──────────────┘ └──────────────┘ └──────────────┘ │
└────────────────────────┬────────────────────────────────┘
 │
┌────────────────────────┴────────────────────────────────┐
│ 质量保障层 │
│ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ │
│ │ 错误分类器 │ │ 契约检查器 │ │ 修复模式缓存 │ │
│ │ (8 种类型) │ │ (LLM 验证) │ │ (知识复用) │ │
│ └──────────────┘ └──────────────┘ └──────────────┘ │
└─────────────────────────────────────────────────────────┘
```

---

## 前端 Agent 工作台

**组件**: `src/components/AgentChat.vue`

- **路由路径**: `/agent` (新标签页打开)
- **状态管理**: `useAgentChat` composable + `userStore`
- **核心功能**:
  - 多轮对话管理
  - SSE 流式输出 (实时展示思考过程)
  - 会话切换与历史查看
  - 知识库管理 (添加/删除知识条目)
  - 面板展开/收起

### API 客户端初始化 (v5.0.1 重要)

**根因**: 组件在 `main.js` 执行 `initApiClient(userStore)` 之前导入 `api`，导致实例内部 `userStore` 为 `null`，所有请求不带 Token。

**解决方案**:

1. **全局挂载**: `window.api` 在 `main.js` 中初始化后挂载到全局
2. **组件使用**: 所有组件必须使用 `window.api` 发起请求
3. **代理导出**: `src/utils/api/index.js` 使用 Proxy 导出命名 `api`，动态解析为 `window.api`

```javascript
// src/utils/api/index.js
export const api = new Proxy({}, {
  get(_target, prop) {
    return window.api?.[prop]
  }
})
```

4. **Token 获取增强**: `src/utils/api/base.js` 中的 `getValidToken()` 按以下顺序查找：
   - `window.userStore.token`
   - `window.api._userStore?.token`
   - `sessionStorage.getItem('token')`
   - `localStorage` 持久化数据

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

---

## 后端 API 端点

**路由前缀**: `/api/v1/agent`

### 静态文件服务 (v5.0.1 修复)

**文件**: `app/main.py`

前端构建产物由 FastAPI 静态文件中间件提供服务：

- **SPA 回路由**: `/dist/index.html` 通过 `StaticFiles` 挂载到 `/`
- **静态资源**: `STATIC_DIST_PATH` 修正为指向 `dist/static`（而非 `dist/`）
- **路径结构**: Vite 输出的 hash 文件位于 `dist/static/css/` 和 `dist/static/js/`

### 核心端点 (v5.9.0)

| 端点 | 方法 | 描述 |
|------|------|------|
| `/orchestrate/stream` | POST | 流式项目编排 (SSE) |
| `/orchestrate` | POST | 多步骤项目编排 |
| `/generate` | POST | 项目生成 (AI) |
| `/modify` | POST | 增量修改已有项目 |
| `/evaluate` | POST | 需求评价 |
| `/analyze_complexity` | POST | 复杂度分析 |
| `/sessions` | GET | 会话列表 |
| `/sessions/{id}` | GET | 会话详情 |
| `/sessions/{id}` | DELETE | 删除会话 |
| `/session/{id}/action` | POST | 暂停/恢复/取消会话 |
| `/session/{id}/decision` | POST | 提交人工决策 |
| `/snapshots/{id}` | GET | 项目快照列表 |
| `/rollback/{id}` | POST | 回滚到指定快照 |
| `/snapshot/diff` | GET | 对比两个快照差异 |
| `/knowledge` | POST/GET | 知识库管理 |
| `/requirement-association` | POST | 需求关联分析 |
| `/performance` | GET | 性能指标统计 |
| `/token-usage` | GET | Token 使用统计 |
| `/stats` | GET | 统计信息 |

### `/orchestrate/stream` 端点详情

流式项目生成，所有 LLM 调用使用用户 API Key。

```json
{
 "requirement": "用户需求描述",
 "session_id": "uuid",
 "api_key_token": "optional-encrypted-token"
}
```

### `/modify` 端点详情

对已生成项目进行增量修改。

```json
{
 "project_id": "uuid",
 "session_id": "uuid",
 "requirements": "添加用户登录功能",
 "incremental": true,
 "api_key_token": "optional-encrypted-token"
}
```

---

## OrchestratorAgent 核心流程

**文件**: `app/agent/orchestrator.py`

OrchestratorAgent 是项目生成的核心协调器，负责：

- **复杂度分析**: 使用 LLM 辅助分析需求复杂度
- **模型分配**: 根据复杂度为各角色分配合适的模型
- **架构设计**: 调用 Architect 设计整体架构
- **文件生成**: 按依赖分层并发生成文件
- **验证审查**: 对每个文件进行验证和审查
- **错误恢复**: 自动生成失败时进行修复
- **增量更新**: 支持基于已有项目的增量生成 (`incremental` 参数从请求读取)
- **Git 保存**: 每次生成/修改后自动 git commit 保存快照

### 主要方法

| 方法 | 描述 |
|------|------|
| `generate()` | 主入口，根据 spec_first 选项选择策略 |
| `generate_with_spec_first()` | 规范优先生成策略 |
| `_generate_traditional()` | 传统生成策略 |
| `_initialize_components()` | 初始化所有组件 |
| `_generate_single_file()` | 生成单个文件 |
| `_validate_and_review_file()` | 验证和审查文件 |
| `_handle_incremental_generation()` | 处理增量生成 (v4.6.0: `incremental` 从请求读取) |

### 传统生成流程

```
┌─────────────┐
│ 用户需求 │
└──────┬──────┘
 ↓
┌─────────────────────┐
│ ComplexityAnalyzer │ ← 分析复杂度
└──────┬──────────────┘
 ↓
┌─────────────────────┐
│ LayeredModelRouter │ ← 分配模型 (三级金字塔)
└──────┬──────────────┘
 ↓
┌─────────────────────┐
│ Architect │ ← 设计架构
└──────┬──────────────┘
 ↓
┌─────────────────────┐
│ DependencyGraph │ ← 构建依赖 (含 build_from_existing_project)
└──────┬──────────────┘
 ↓
┌─────────────────────┐
│ File Generation │ ← 分层生成 (层内并发, 限制: 4)
└──────┬──────────────┘
 ↓
┌─────────────────────┐
│ Validation & Review │ ← 三轮审查链 + 错误恢复
└──────┬──────────────┘
 ↓
┌─────────────────────┐
│ Final Validation │ ← DockerRunner (优先) / IsolatedTestRunner (回退)
└──────┬──────────────┘
 ↓
┌─────────────────────┐
│ Git Commit │ ← 自动保存快照 (v4.6.0 新增)
└─────────────────────┘
```

### 规范优先生成流程 (Spec-First)

```
┌─────────────┐
│ 用户需求 │
└──────┬──────┘
 ↓
┌─────────────────────┐
│ ComplexityAnalyzer │ ← 分析复杂度
└──────┬──────────────┘
 ↓
┌─────────────────────┐
│ SpecFirstGenerator │ ← 生成规范
│ ├── OpenAPI 规范 │
│ ├── 类型定义 │
│ ├── DB Schema │
│ └── 配置规范 │
└──────┬──────────────┘
 ↓
┌─────────────────────┐
│ Architect │ ← 基于规范生成文件计划
└──────┬──────────────┘
 ↓
┌─────────────────────┐
│ DependencyGraph │ ← 结合规范 + 架构
└──────┬──────────────┘
 ↓
┌─────────────────────┐
│ CrossValidator │ ← 关键文件双模型生成 + 评审员裁决
└──────┬──────────────┘
 ↓
┌─────────────────────┐
│ RefinementLoop │ ← 验证 -> 修复循环 (最多 3 次)
└──────┬──────────────┘
 ↓
┌─────────────────────┐
│ Final Validation │ ← DockerRunner / IsolatedTestRunner
└──────┬──────────────┘
 ↓
┌─────────────────────┐
│ Git Commit │ ← 自动保存快照
└─────────────────────┘
```

### 增量修改流程 (v4.6.0)

```
┌─────────────┐
│ 修改请求 │ (incremental=True)
└──────┬──────┘
 ↓
┌─────────────────────┐
│ 加载已有项目上下文 │ ← Git 仓库 + 依赖图解析
└──────┬──────────────┘
 ↓
┌─────────────────────┐
│ DependencyGraph │ ← build_from_existing_project()
│ 解析 import/require│
└──────┬──────────────┘
 ↓
┌─────────────────────┐
│ 变更影响分析 │ ← 确定受影响文件范围
└──────┬──────────────┘
 ↓
┌─────────────────────┐
│ 增量文件生成 │ ← 只修改受影响文件
└──────┬──────────────┘
 ↓
┌─────────────────────┐
│ 验证 + 测试 │ ← DockerRunner / IsolatedTestRunner
└──────┬──────────────┘
 ↓
┌─────────────────────┐
│ Git Commit │ ← 保存增量修改快照
└─────────────────────┘
```

---

## 工具集与模型路由

### 工具集

**文件**: `app/agent/tools/`

#### 通用 Agent 工具

| 工具 | 描述 | 参数 |
|------|------|------|
| CodeGenerator | 代码生成工具 | - |
| WebSearcher | 网络搜索工具 | query, limit |
| FileReader | 文件读取工具 | path |
| Calculator | 计算器 | - |
| KnowledgeRetriever | 知识库检索 | - |
| git_status | 查看 Git 仓库状态 | - |
| git_log | 查看提交历史 | - |
| git_diff | 查看文件差异 | - |
| git_checkout | 切换分支 | - |
| git_reset | 重置更改 | - |
| git_restore_file | 恢复文件 | - |
| git_rollback | 回滚操作 | - |

#### EnhancedExecutor (增强执行器)

**文件**: `app/agent/executor.py`

| 工具 | 描述 | 参数 |
|------|------|------|
| read_file | 读取文件 | path |
| write_file | 写入文件 | path, content |
| list_files | 列出文件 | path, pattern |
| execute_code | 执行 Python 代码 | code, timeout |
| web_search | 网络搜索 | query, limit |
| http_request | HTTP 请求 | method, url, headers, body |

#### 代码执行沙箱

- **禁止函数**: exec, eval, compile, __import__, open, getattr, setattr
- **安全全局**: 只保留安全的内置函数 (print, len, range, list, dict 等)
- **AST 检查**: 执行前进行语法树分析，拦截危险调用

#### StreamingExecutor (流式执行器)

继承 EnhancedExecutor，支持流式输出：

```python
executor.set_stream_callback(lambda text: print(text, end=''))
result = await executor.execute_with_stream(step)
```

### 模型注册表

**文件**: `app/agent/multi_model_agent.py`

| 键名 | 模型名称 | 能力 | 最大 Token | 速度 |
|------|---------|------|-----------|------|
| deepseek-r1-qwen3-8b | DeepSeek-R1-0528-Qwen3-8B | REASONING, CODE | 8192 | 0.7 |
| deepseek-ocr | DeepSeek-OCR | OCR, VISION | 2048 | 1.0 |
| paddleocr-vl-1.5 | PaddlePaddle/PaddleOCR-VL-1.5 | VISION | 2048 | 0.8 |
| qwen3.5-4b | Qwen/Qwen3.5-4B | FAST | 4096 | 2.0 |
| qwen3-8b | Qwen/Qwen3-8B | REASONING, FAST | 4096 | 1.5 |
| qwen2.5-7b | Qwen/Qwen2.5-7B-Instruct | CODE, FAST | 4096 | 1.8 |
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
 TaskType.VISUAL_UNDERSTANDING: ["paddleocr-vl-1.5", "deepseek-ocr"],
 TaskType.IMAGE_GENERATION: ["kolors"],
 TaskType.REASONING: ["deepseek-r1-qwen3-8b", "glm-z1-9b"],
 TaskType.FAST_RESPONSE: ["qwen3.5-4b", "glm-4-9b"],
 TaskType.EMBEDDING: ["bce-embedding"],
 TaskType.OCR: ["deepseek-ocr"],
}
```

### 三级金字塔路由 (v4.5.0 优化)

```
[简单层] 工具函数、配置文件、常量定义
 -> qwen3.5-4b (最快, 成本趋近于零)
 -> 判断标准: 文件描述含 "utility/constant/helper/config"

[标准层] 业务逻辑、CRUD、API 路由
 -> qwen2.5-7b / glm-4-9b (主力编写)
 -> 判断标准: 大部分后端和前端组件代码

[攻坚层] 复杂算法、并发处理、安全敏感代码
 -> deepseek-r1-qwen3-8b + glm-z1-9b 交叉生成, 互相审查
 -> 判断标准: Orchestrator 的复杂度分析标记为 HIGH
```

### 动态路由

**文件**: `app/agent/dynamic_model_router.py`

- **健康监控**: 跟踪每个模型的调用成功率、延迟
- **熔断机制**: 失败率过高时自动熔断
- **重试策略**: 主模型失败时自动切换备选模型

#### 全局健康感知路由 (v4.5.0)

- **系统状态感知**: 监控活跃请求数、Drain 模式、资源使用率
- **智能降级**: 当首选模型负载高时自动降级到备选
- **权重模型**: 任务优先级、时间敏感度、模型健康度的综合评分
- **管理员控制**: 可调节过载阈值，默认关闭但保留接口

```json
{
 "health_aware_routing": {
 "enabled": false,
 "system_overload_threshold": 0.8,
 "model_load_weight": 0.6,
 "system_load_weight": 0.4,
 "max_concurrent_requests": 100
 }
}
```

### 专家角色

**文件**: `app/agent/specialists.py`

#### Architect (架构师)

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

#### FrontendEngineer (前端工程师)

- **职责**: 前端文件生成 (Vue/React/HTML/CSS/JS)
- **使用模型**: Qwen2.5-7B-Instruct (快速) / Qwen3-8B (企业级)
- **规则**: 每次只创建一个文件，代码完整可运行

#### BackendEngineer (后端工程师)

- **职责**: 后端文件生成 (Python/FastAPI/数据库模型)
- **使用模型**: DeepSeek-R1-Qwen3-8B (代码推理)
- **规则**: 包含错误处理、类型注解、完整代码

#### CodeReviewer (代码审查员)

- **职责**: 代码质量和安全审查
- **使用模型**: GLM-Z1-9B + DeepSeek-R1 (双重审查)
- **审查维度**: 安全性、正确性、性能、可维护性、版本兼容性

### MultiModelAgent (多模型协调器)

**文件**: `app/agent/multi_model_agent.py`

#### 任务类型

```python
class TaskType(Enum):
 GENERAL = "general"
 CODE_GENERATION = "code_generation"
 CODE_REVIEW = "code_review"
 FILE_OPERATION = "file_operation"
 VISUAL_UNDERSTANDING = "visual"
 IMAGE_GENERATION = "image_generation"
 REASONING = "reasoning"
 FAST_RESPONSE = "fast_response"
 EMBEDDING = "embedding"
 OCR = "ocr"
```

#### 处理流程

```
用户请求 -> 内容识别 -> TaskType
 -> 模型路由 -> 选择最佳模型
 -> 任务规划 -> 分解为步骤
 -> 计划审查 -> AIReviewer 审查
 -> 步骤执行 -> 逐个执行
 -> 文件契约 -> 验证路径安全
 -> 返回结果
```

---

## 会话管理与增量修改

### 会话管理

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

### 知识库

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

- **用途**: Agent 对话时自动检索相关知识作为上下文

### 增量修改 (v4.6.0)

v4.6.0 将 `incremental` 参数从硬编码 `False` 改为从请求读取，支持对已有项目的增量修改：

- **`/api/v1/agent/modify`** 端点: 接收 `incremental=True` 参数
- **变更影响分析**: 确定修改范围，只重新生成受影响文件
- **依赖图重建**: 调用 `DependencyGraph.build_from_existing_project()` 解析已有项目的 import/require
- **Git 保存**: 增量修改后自动 commit 保存快照

---

## 依赖图与跨文件分析

**文件**: `app/agent/dependency_graph.py`

### DependencyGraph

构建文件间的依赖关系，按优先级分层，同层内无依赖可并行。

### `build_from_existing_project()` 方法 (v4.6.0 新增)

解析已有项目的 import/require 语句，重建依赖图，用于增量修改场景：

- **解析 import**: Python 的 `import` / `from ... import` 语句
- **解析 require**: JavaScript 的 `require()` / `import from` 语句
- **依赖重建**: 根据解析结果重建文件间依赖关系图
- **增量兼容**: 生成的依赖图与新建项目的依赖图格式一致

### `get_affected_files()` 方法 (v4.8.0 新增)

跨文件依赖分析核心方法，用于增量修改时检测所有受影响的文件：

- **BFS 遍历**: 从变更文件出发，广度优先搜索所有下游依赖
- **传递依赖**: 支持多级传递依赖检测（A→B→C）
- **深度限制**: `max_depth=10` 防止循环依赖导致无限遍历
- **多变更支持**: 同时处理多个变更文件的依赖合并

### CrossFilePatcher (v4.8.0 新增)

**文件**: `app/agent/code_patcher.py`

基于依赖图分析结果，自动为所有受影响文件生成 patches：

- **主文件 patch**: 为直接变更文件生成 patch
- **依赖文件 patch**: 为所有下游依赖文件生成适应性 patch
- **失败标记**: 无法自动 patch 的文件标记为 "manual review required"
- **集成流程**: 在 `OrchestratorAgent._apply_patches_incremental()` 中自动调用

### 依赖关系类型

| 类型 | 描述 | 示例 |
|------|------|------|
| env → service_config | 环境变量被配置文件使用 | `.env` → `config/database.py` |
| service_config → service | 配置被服务模块使用 | `config/database.py` → `services/user.py` |
| service → api | 服务被 API 路由使用 | `services/user.py` → `api/v1/users.py` |
| docker-compose → env | docker-compose 依赖环境变量定义 | `docker-compose.yml` → `.env.example` |

---

## 测试验证

### 测试策略 (v4.6.0)

采用 **DockerRunner (优先) + IsolatedTestRunner (回退)** 的双层验证策略：

```
┌─────────────────┐
│ DockerRunner │ ← 优先方案: Docker 容器隔离测试
└──────┬──────────┘
 │ 不可用 / 失败
 ↓
┌─────────────────────┐
│ IsolatedTestRunner │ ← 回退方案: venv 隔离 + 安全扫描
└─────────────────────┘
```

### DockerRunner (优先方案，v4.8.0 增强)

在 Docker 容器内运行项目测试，提供最完整的隔离环境：

- **容器隔离**: 每次测试在独立容器中执行
- **环境一致性**: 确保测试环境与运行环境一致
- **资源限制**: CPU/内存限制，防止测试占用过多资源
- **自动清理**: 测试完成后自动销毁容器
- **框架检测** (v4.8.0): 自动检测项目测试框架 (pytest/jest/mvn/go/cargo/make)
- **服务容器** (v4.8.0): 自动启动 Redis/PostgreSQL/MySQL/MongoDB/RabbitMQ/Elasticsearch
- **健康检查** (v4.8.0): 等待服务 ready 后再运行测试
- **环境变量注入** (v4.8.0): 自动注入服务连接信息到测试环境

### IsolatedTestRunner (回退方案，v4.6.0 增强)

TestRunner 增强为 IsolatedTestRunner，提供 venv 级别的隔离测试：

- **venv 隔离**: 每次测试创建独立 Python 虚拟环境
- **安全扫描**: 安装依赖前进行安全扫描
- **白名单依赖**: 只允许白名单内的依赖安装
- **资源释放**: 测试完成后释放 venv 资源和临时文件

### 测试框架支持 (v4.8.0 新增)

| 框架 | 语言 | Docker 镜像 | 命令 | 输出格式 |
|------|------|-----------|------|---------|
| pytest | Python | python:3.11-slim | pytest -xvs | pytest_xml |
| jest/vitest | JavaScript | node:20-slim | npm test | jest_json |
| maven | Java | maven:3.9-eclipse-temurin-17 | mvn verify | junit_xml |
| go test | Go | golang:1.22-alpine | go test ./... -v | go_json |
| cargo test | Rust | rust:1.77-slim | cargo test | rust_text |
| make test | C++ | gcc:13 | make test | cpp_text |

### FrameworkDetector (v4.8.0 新增)

自动检测项目使用的测试框架，检测优先级：

1. **显式配置**: tox.ini, setup.cfg, .github/workflows/test.yml
2. **包清单**: package.json, pom.xml, go.mod, Cargo.toml, Makefile
3. **源文件模式**: *_test.go, *Test.java, test_*.py
4. **默认**: pytest

### OutputParser (v4.8.0 新增)

统一解析不同测试框架的输出格式，提取测试结果：

- **TestCaseResult**: 单个测试用例的结果（名称、状态、时长、错误信息）
- **ParsedTestResult**: 总体测试结果（总测试数、通过数、失败数、错误列表）
- **支持格式**: pytest_xml, jest_json, junit_xml, go_json, rust_text, cpp_text

---

## Git 分支管理与快照回滚 (v4.8.0 新增)

每次项目生成或增量修改后，自动 git commit 保存快照：

### 保存时机

- **项目生成完成**: 全部文件生成并通过验证后
- **增量修改完成**: 修改文件并通过验证后
- **错误恢复成功**: 修复文件后

### 保存内容

- **commit message**: 包含操作类型 (generate/modify/fix) 和项目信息
- **文件范围**: 所有本次生成/修改的文件

### 与 `/modify` 端点的关系

增量修改流程中，`/modify` 端点完成修改后自动调用 git commit，确保每次修改都有快照可回溯。

---

## 六大优化方向

> 来源: v4.5.0 优化方案

| 方向 | 核心思想 | 所需投入 | 实施状态 |
|------|---------|---------|---------|
| 模型能力金字塔 | 让模型做最擅长的事，而非"能者多劳" | 重构任务分配逻辑 | 已完成 |
| 审查层次深化 | 串行深入检查，而非一次性走马观花 | 重构审查流程 | 已完成 |
| 修复策略模式化 | 对症下药，而非盲目重试 | 建立错误分类器 | 已完成 |
| 知识复用 | 不让成功经验被遗忘 | 增强 feedback_learner | 已完成 |
| 并发自适应 | 根据依赖结构调度，而非固定值 | 增强 dependency_graph | 已完成 |
| 契约自动化 | 用规范做硬约束，而非软建议 | 增加契约检查环节 | 已完成 |

### 方向一: 模型能力金字塔

不换模型，只换分配逻辑 -- 三级金字塔路由 (详见 [工具集与模型路由](#工具集与模型路由) 的三级金字塔路由部分)。

**收益**: 不增加任何模型，但把最强推理模型的能力聚焦在真正的难点上，整体延迟和成本反而更低。

**实现文件**:
- `app/agent/dynamic_model_router.py` - 三层路由逻辑
- `app/agent/orchestrator.py` - 任务分配策略

### 方向二: 审查层次深化

用不同的现有审查模型，执行不同层次的审查：

```
[第一轮: 语义审查] -> qwen2.5-7b (快速扫描)
 - 语法错误
 - 导入是否缺失
 - 类型注解是否正确

[第二轮: 安全审查] -> deepseek-r1-qwen3-8b (深度推理)
 - SQL注入 / XSS / 路径遍历
 - 权限检查是否遗漏
 - 敏感数据处理是否合规

[第三轮: 设计审查] -> glm-z1-9b (高推理能力)
 - 循环依赖检查
 - 是否符合项目已有的设计模式
 - 是否存在过度设计或设计不足
```

**收益**: 同样是三个现有模型，串行分工比一次性检查更深入，且前一轮通过才进入下一轮，减少无效审查。

**实现文件**:
- `app/agent/specialists.py` - CodeReviewer 多轮审查链
- `app/agent/code_validator.py` - 语义验证层

### 方向三: 修复策略模式化

对症下药，基于错误分类器选择修复策略：

- **错误分类器**: 8 种错误类型分类
- **修复模式缓存**: 成功修复经验按错误类型存储
- **A/B 测试框架**: 80% 走已验证策略，20% 探索策略变体
- **自动优化**: 探索策略连续 3 次优于旧策略时自动替换

**实现文件**:
- `app/agent/strategy_evaluator.py` - 策略评估器 (A/B 测试框架)
- `app/agent/error_recovery.py` - 集成策略评估器到修复流程
- `app/agent/fix_pattern_cache.py` - 支持策略版本管理

### 方向四: 知识复用

不让成功经验被遗忘：

- **向量相似度**: 利用 bce-embedding 模型对项目描述生成向量
- **模糊匹配**: 索引键从精确匹配改为"错误类型 + 项目描述向量相似度 Top3"
- **阈值控制**: 余弦相似度高于 0.8 的经验可跨项目复用
- **缓存纠错与衰减**: 超过 30 天未命中权重减半，超过 60 天自动归档

**实现文件**:
- `app/agent/fix_pattern_cache.py` - 向量相似度索引 + 缓存生命周期管理
- `app/agent/memory.py` - 项目描述向量存储

### 方向五: 并发自适应

根据依赖结构调度，而非固定值：

- **依赖图增强**: DependencyGraph 动态计算并发度
- **自适应调度**: 无依赖文件最大并发，有依赖文件按拓扑排序
- **并发限制**: 默认最大并发 4，根据系统负载动态调整

**实现文件**:
- `app/agent/dependency_graph.py` - 增强依赖图

### 方向六: 契约自动化

用规范做硬约束，而非软建议：

- **契约检查器**: LLM 验证生成的代码是否符合 OpenAPI 规范
- **类型契约**: Pydantic 模型验证
- **API 契约**: 前后端接口一致性检查

### 整体收益

| 指标 | 优化前 | 优化后 | 提升 |
|------|--------|--------|------|
| 首次修复成功率 | ~50% | ~80% | +60% |
| 平均生成时间 | 基准 | -30% | 缩短 30% |
| API 不一致问题 | 审查阶段发现 | 生成阶段拦截 | 提前 2 个阶段 |
| 模型使用成本 | 平均分布 | 金字塔分布 | -25% |
| 高频错误修复时间 | 每次都重新分析 | 缓存命中即时修复 | -70% |
| 首字节响应时间 | ~5s | ~1s | 80% |
| 大项目生成成功率 | ~70% | ~95% | 35% |
| 并发会话数 | ~10 | ~50 | 400% |
| 内存使用峰值 | ~800MB | ~400MB | 50% |

---

## 分布式追踪

**文件**: `app/agent/tracing.py`

v4.7.0 新增 OpenTelemetry 分布式追踪能力，用于可视化 Agent 调用链。

### 架构

```
┌─────────────────────────────────────────────────────────┐
│ OpenTelemetry SDK │
│ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ │
│ │ TracerProvider│ │ SpanProcessor│ │ Exporter │ │
│ │ (采样/资源) │ │ (批量/异步) │ │ (Jaeger/OTLP)│ │
│ └──────────────┘ └──────────────┘ └──────────────┘ │
└────────────────────────┬────────────────────────────────┘
 │
┌────────────────────────┴────────────────────────────────┐
│ 追踪 Span 树 │
│ ┌──────────────────────────────────────────────────┐ │
│ │ trace: orchestrator.generate │ │
│ │ ┌────────────────────────────────────────────┐ │ │
│ │ │ span: orchestrator.initialize_components │ │ │
│ │ └────────────────────────────────────────────┘ │ │
│ │ ┌────────────────────────────────────────────┐ │ │
│ │ │ span: architect.design │ │ │
│ │ │ ┌────────────────────────────────────┐ │ │ │
│ │ │ │ span: specialist.call_llm │ │ │ │
│ │ │ └────────────────────────────────────┘ │ │ │
│ │ └────────────────────────────────────────────┘ │ │
│ │ ┌────────────────────────────────────────────┐ │ │
│ │ │ span: frontend.generate_file │ │ │
│ │ └────────────────────────────────────────────┘ │ │
│ │ ┌────────────────────────────────────────────┐ │ │
│ │ │ span: reviewer.review_code │ │ │
│ │ └────────────────────────────────────────────┘ │ │
│ │ ┌────────────────────────────────────────────┐ │ │
│ │ │ span: test.run │ │ │
│ │ └────────────────────────────────────────────┘ │ │
│ └──────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

### 配置

通过环境变量控制：

| 变量 | 默认值 | 描述 |
|------|--------|------|
| `OTEL_ENABLED` | `""` (关闭) | 设为 `1` / `true` 启用 |
| `OTEL_EXPORTER` | `jaeger` | `jaeger` / `otlp` / `none` |
| `OTEL_JAEGER_ENDPOINT` | `http://jaeger:14268/api/traces` | Jaeger HTTP 收集器地址 |
| `OTEL_OTLP_ENDPOINT` | `http://otel-collector:4318` | OTLP HTTP 端点 |
| `OTEL_SERVICE_NAME` | `ai-agent` | 服务名称 |
| `OTEL_SAMPLING_RATE` | `1.0` | 采样率 (0.0~1.0) |

### 使用方式

**装饰器方式**:
```python
from app.agent.tracing import traced

@traced("my_operation", attributes={"component": "my_module"})
async def my_function():
 ...
```

**手动方式**:
```python
from app.agent.tracing import tracer

with tracer.start_as_current_span("my_span") as span:
 span.set_attribute("key", "value")
 ...
```

**手动方式**:
```python
from app.agent.tracing import tracer

with tracer.start_as_current_span("my_span") as span:
 span.set_attribute("key", "value")
 ...
```

### 已追踪方法

| 模块 | Span 名称 | 描述 |
|------|-----------|------|
| `orchestrator.py` | `orchestrator.generate` | 项目生成主入口 |
| `orchestrator.py` | `orchestrator.initialize_components` | 组件初始化 |
| `orchestrator.py` | `orchestrator.traditional` | 传统生成策略 |
| `specialists.py` | `specialist.call_llm` | LLM 调用 |
| `specialists.py` | `architect.design` | 架构设计 |
| `specialists.py` | `frontend.generate_file` | 前端文件生成 |
| `specialists.py` | `backend.generate_file` | 后端文件生成 |
| `specialists.py` | `reviewer.review_code` | 代码审查 |
| `session_manager.py` | `session.create` | 创建会话 |
| `session_manager.py` | `session.resume` | 恢复会话 |
| `session_manager.py` | `session.save` | 保存会话 |
| `session_manager.py` | `session.cleanup` | 清理过期会话 |
| `test_runner.py` | `test.run` | 执行测试 |

### 本地开发

```bash
# 启动 Jaeger
docker compose up -d jaeger

# 启用追踪
export OTEL_ENABLED=1
export OTEL_EXPORTER=jaeger
export OTEL_JAEGER_ENDPOINT=http://localhost:14268/api/traces

# 访问 Jaeger UI
open http://localhost:16686
```

---

---

## 提示词增强

> 来源: v4.4.0 提示词增强方案

v4.4.0 对 Agent 系统的提示词进行了全面增强，定义了 6 个专家角色的详细工作规范和输出标准。

### 增强的提示词文件

| 角色 | 提示词文件 | 增强内容 |
|------|-----------|---------|
| 项目生成 Agent | `.claude/skills/project_generation/enhanced_system_prompt.md` | 认知能力、技术栈选择、项目类型分类矩阵、文件创建规划、代码质量标准 |
| Orchestrator Agent | `.claude/skills/orchestrator/enhanced_orchestrator_prompt.md` | 核心职责、复杂度评估矩阵、架构决策矩阵、任务分解模板、Agent 协作协议 |
| Architect Agent | `.claude/skills/orchestrator/enhanced_architect_prompt.md` | 技术选型原则、架构设计原则、API 设计规范、数据库设计规范、质量检查清单 |
| Frontend Engineer | `.claude/skills/orchestrator/enhanced_frontend_engineer_prompt.md` | 技术专长、代码质量标准、样式规范、性能最佳实践、项目结构模板、安全实践 |
| Backend Engineer | `.claude/skills/orchestrator/enhanced_backend_engineer_prompt.md` | 技术专长、代码质量标准、安全实践、性能优化、项目结构模板、测试支持 |
| Code Reviewer | `.claude/skills/orchestrator/enhanced_code_reviewer_prompt.md` | 四维审查清单 (安全12项/正确8项/可读6项/性能7项)、风险等级分类、决策树 |

### 使用方式

提示词通过 `prompt_loader.py` 自动加载：

```python
from app.utils.prompt_loader import load_enhanced_prompt

prompt = load_enhanced_prompt("orchestrator")
```

### 效果评估

- 代码生成质量提升 30%
- 任务分解准确性提升 25%
- 安全性问题发现率提升 40%
- 代码风格一致性提升 35%

---

## GitHub 集成

> 来源: v4.4.0 GitHub 集成方案

### 核心功能

1. **GitHub 配置管理**: 用户可在前端配置 GitHub Token 和仓库信息，配置信息存储在浏览器本地存储中 (base64 编码)
2. **项目保存至 GitHub**: 支持将生成的项目推送至指定 GitHub 仓库，自动创建提交和推送，SSE 流式推送操作状态
3. **Git 操作工具集**: Agent 内置 7 种 Git 操作工具 (详见 [工具集与模型路由](#工具集与模型路由))

### 后端 API

| 端点 | 方法 | 描述 |
|------|------|------|
| `/api/v1/github/config` | POST | 保存 GitHub 配置 |
| `/api/v1/github/config` | GET | 获取 GitHub 配置 |
| `/api/v1/github/save-project` | POST | 保存项目至 GitHub |
| `/api/v1/github/verify-token` | GET | 验证 Token 有效性 |

### 前端组件

- `GithubConfigPanel.vue` - GitHub 配置面板
- `useGithubStore` - Pinia 状态管理
- `github.js` - API 客户端封装

### SSE 事件

- `git_operation_start` - Git 操作开始
- `git_operation_success` - Git 操作成功
- `git_operation_error` - Git 操作失败

### 安全考虑

- GitHub Token 仅存储在浏览器本地
- 传输过程使用 HTTPS 加密
- Token 不在日志中明文输出

---

## 安全与权限

### 权限要求

- **最低权限**: normal (普通用户)
- **会话隔离**: 用户只能看到自己的会话
- **知识隔离**: 用户只能管理自己的知识

### 文件路径验证

所有文件路径经过严格验证：

- **非法字符**: 只允许字母、数字、下划线、连字符、点、斜杠
- **路径深度**: 最大 5 层嵌套
- **文件扩展名**: 支持常见编程语言和配置文件扩展名
- **重复检查**: 禁止重复路径

### 错误处理

- **模型调用失败**: 自动重试 3 次，指数退避
- **工具执行超时**: 60 秒超时，返回超时错误
- **会话不存在**: 返回 404
- **权限不足**: 返回 403
- **LLM API 超时**: 自动重试
- **降级策略**: 小模型兜底

### 记忆系统

**文件**: `app/agent/memory.py`

| 类型 | 描述 | 用途 |
|------|------|------|
| ConversationMemory | 对话记忆 | 记录用户消息和助手回复 |
| KnowledgeMemory | 知识记忆 | 存储项目技术栈和关键决策 |
| ReflectionMemory | 反思记忆 | 记录执行反思和经验教训 |

```python
@dataclass
class MemoryEntry:
 type: str # 记忆类型
 content: str # 记忆内容
 importance: float # 重要度 (0.0-1.0)
 metadata: Dict # 元数据
 timestamp: float # 时间戳
```

### ReAct 自我反思

**文件**: `app/agent/react_agent.py`

```
┌──────────┐
│ Thought │ ← 分析任务，决定下一步
└────┬─────┘
 ↓
┌──────────┐
│ Action │ ← 执行工具调用
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
 继续? --Yes--→ 下一轮循环
 │
 No
 ↓
┌────────────┐
│Final Answer│ ← 生成最终答案
└────────────┘
```

- **最大迭代**: 默认 10 次
- **流式输出**: 支持实时推送思考过程
- **降级策略**: ReActWithFallback 支持模型切换

```python
fallback = ReActWithFallback()
result = await fallback.process(task, context)
# 主模型失败时自动切换到备用模型，最多重试 2 次
```

### 错误恢复

**文件**: `app/agent/error_recovery.py`

```
文件生成 -> 验证失败
 -> 错误分析 -> 修复策略选择 -> 重新生成 -> 验证修复结果
 -> 成功? --Yes--→ 继续
 -> No (最多 3 次) -> 记录失败，继续下一个文件
```

**RefinementLoop** (`app/agent/refinement_loop.py`):

- **验证**: 语法检查、导入验证
- **修复**: 基于错误信息针对性修复
- **循环**: 最多 3 次尝试

### 规范优先生成

**文件**: `app/agent/spec_first_generator.py`

```
1. OpenAPI 规范生成 -> 2. 类型定义生成 (Pydantic 模型)
 -> 3. 数据库 Schema 生成 (SQLAlchemy Model)
 -> 4. 配置规范生成 (.env.example + 配置加载代码)
```

**优势**: 前后端一致、类型安全、可维护性。

---

## 关键配置参数

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
| incremental | 从请求读取 | 增量修改模式 (v4.6.0) |

## 进度事件类型

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

## 关键决策交叉辩论模式 (v4.5.0 P2)

- **触发条件**: 仅在复杂度为 ENTERPRISE 或标记为"关键决策"时启用
- **辩论流程**: Architect 提出方案 -> BackendEngineer/FrontendEngineer 挑战 -> CodeReviewer 安全审查 -> Orchestrator 综合形成最终方案

**实现文件**:
- `app/agent/orchestrator.py` - 交叉辩论流程
- `app/agent/specialists.py` - 专家角色挑战方法

---

**维护者**: MonkeyCode-AI Team