# 自定义 Skill 系统

> 最后更新：2026-06-22 | API 端点：8 个 | 存储限制：100KB/Skill，50 个/用户

## 目录

- [概述](#概述)
- [架构设计](#架构设计)
- [API 端点](#api-端点)
- [Agent 集成](#agent-集成)
- [分类体系](#分类体系)
- [约束规则](#约束规则)
- [热重载机制](#热重载机制)
- [使用示例](#使用示例)

---

## 概述

自定义 Skill 系统允许用户上传和管理自定义提示词（Prompt），覆盖 Agent 系统中各角色的默认系统提示词。通过该系统，用户可以：

- **自定义 Agent 行为**：覆盖架构师、前端工程师、后端工程师、审查员等角色的默认提示词
- **热重载生效**：上传/更新后立即生效，无需重启服务
- **分类管理**：按 7 大分类组织 Skill，支持按分类/作者过滤
- **版本追踪**：每次更新自动递增版本号，记录更新时间

### 核心价值

| 场景 | 说明 |
|------|------|
| 定制架构风格 | 上传自定义 `architect_prompt`，让架构师按特定技术栈设计 |
| 特殊编码规范 | 上传自定义 `backend_engineer_prompt`，强制执行团队编码规范 |
| 审查标准调整 | 上传自定义 `code_reviewer_prompt`，调整代码审查侧重点 |
| 工作流定制 | 上传 `workflow` 类 Skill，定义特定业务流程 |

---

## 架构设计

### 组件关系

```
┌──────────────────────────────────────────────────────┐
│                    API 层 (skills.py)                  │
│   POST /upload  GET /list  PUT /{name}  DELETE /{name}│
└────────────────────────┬─────────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────────┐
│            CustomSkillManager (CRUD 管理)              │
│   upload_skill / update_skill / delete_skill / get    │
│   验证 → 存储文件 → 更新元数据 → 通知注册表             │
└────────────────────────┬─────────────────────────────┘
                         │ _notify_registry()
                         ▼
┌──────────────────────────────────────────────────────┐
│              SkillRegistry (全局注册表)                 │
│   register / unregister / get / list / reload         │
│   缓存管理 · Loader 函数 · 热重载                      │
└────────────────────────┬─────────────────────────────┘
                         │ get_skill("architect_prompt")
                         ▼
┌──────────────────────────────────────────────────────┐
│              Agent 角色 (Specialist)                   │
│   Architect · FrontendEngineer · BackendEngineer      │
│   CodeReviewer · PPTAgent                             │
│   SYSTEM_PROMPT 属性优先读取自定义 Skill                │
└──────────────────────────────────────────────────────┘
```

### 存储结构

```
/workspace/data/custom_skills/
├── _metadata.json                  # 元数据索引
├── orchestrator/
│   └── my_orchestrator.md
├── reviewer/
│   └── strict_reviewer.md
├── validation/
│   └── custom_validator.md
├── workflow/
│   └── deploy_workflow.md
├── api/
│   └── api_style_guide.md
├── tool/
│   └── custom_tool_spec.md
└── other/
    └── general_prompt.md
```

### 元数据格式 (`_metadata.json`)

```json
{
  "skills": [
    {
      "name": "architect_prompt",
      "category": "orchestrator",
      "file": "orchestrator/architect_prompt.md",
      "description": "自定义架构师提示词",
      "author": "api_user",
      "created_at": "2026-06-22T10:00:00Z",
      "updated_at": "2026-06-22T10:00:00Z",
      "version": 1
    }
  ]
}
```

### 核心类

| 类 | 文件 | 职责 |
|----|------|------|
| `SkillRegistry` | `app/services/skill_registry.py` | 全局单例，管理 Skill 注册、缓存、加载 |
| `CustomSkillManager` | `app/services/custom_skill_manager.py` | CRUD 操作，验证，文件存储，元数据管理 |
| `SkillInfo` | `app/services/skill_registry.py` | Skill 数据类，包含名称/分类/内容/缓存等 |

---

## API 端点

基础路径：`/api/v1/skills`

### 1. 上传 Skill（JSON）

```
POST /api/v1/skills/upload
```

**请求体：**

```json
{
  "name": "architect_prompt",
  "category": "orchestrator",
  "content": "# 自定义架构师提示词\n\n你是一位专注于微服务架构的资深架构师...",
  "description": "自定义架构师角色提示词"
}
```

**响应 (200)：**

```json
{
  "name": "architect_prompt",
  "category": "orchestrator",
  "file": "orchestrator/architect_prompt.md",
  "description": "自定义架构师角色提示词",
  "author": "api_user",
  "created_at": "2026-06-22T10:00:00Z",
  "updated_at": "2026-06-22T10:00:00Z",
  "version": 1
}
```

**错误响应 (400)：**

```json
{
  "detail": "名称无效，只允许字母、数字、下划线、连字符，且以字母开头，长度 1-64"
}
```

### 2. 通过文件上传 Skill

```
POST /api/v1/skills/upload-file
Content-Type: multipart/form-data
```

**表单字段：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `file` | File | 是 | `.md` 文件，UTF-8 编码 |
| `name` | string | 是 | Skill 名称 |
| `category` | string | 是 | 分类 |
| `description` | string | 否 | 描述 |

**curl 示例：**

```bash
curl -X POST http://localhost:8000/api/v1/skills/upload-file \
  -F "file=@my_prompt.md" \
  -F "name=architect_prompt" \
  -F "category=orchestrator" \
  -F "description=自定义架构师提示词"
```

### 3. 列出所有 Skill

```
GET /api/v1/skills/list
```

**查询参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `category` | string | 否 | 按分类过滤 |
| `author` | string | 否 | 按作者过滤 |

**请求示例：**

```
GET /api/v1/skills/list?category=orchestrator&author=api_user
```

**响应 (200)：**

```json
[
  {
    "name": "architect_prompt",
    "category": "orchestrator",
    "file": "orchestrator/architect_prompt.md",
    "description": "自定义架构师提示词",
    "author": "api_user",
    "created_at": "2026-06-22T10:00:00Z",
    "updated_at": "2026-06-22T12:00:00Z",
    "version": 3
  }
]
```

### 4. 获取 Skill 详情

```
GET /api/v1/skills/{name}
```

**响应 (200)：**

```json
{
  "name": "architect_prompt",
  "category": "orchestrator",
  "file": "orchestrator/architect_prompt.md",
  "description": "自定义架构师提示词",
  "author": "api_user",
  "created_at": "2026-06-22T10:00:00Z",
  "updated_at": "2026-06-22T12:00:00Z",
  "version": 3,
  "content": "# 自定义架构师提示词\n\n你是一位专注于微服务架构的资深架构师..."
}
```

**错误响应 (404)：**

```json
{
  "detail": "Skill 'architect_prompt' 不存在"
}
```

### 5. 更新 Skill

```
PUT /api/v1/skills/{name}
```

**请求体：**

```json
{
  "content": "# 更新后的架构师提示词\n\n你是一位专注于事件驱动架构的资深架构师...",
  "description": "更新后的描述"
}
```

**响应 (200)：**

```json
{
  "name": "architect_prompt",
  "category": "orchestrator",
  "file": "orchestrator/architect_prompt.md",
  "description": "更新后的描述",
  "author": "api_user",
  "created_at": "2026-06-22T10:00:00Z",
  "updated_at": "2026-06-22T14:00:00Z",
  "version": 4
}
```

### 6. 删除 Skill

```
DELETE /api/v1/skills/{name}
```

**响应 (200)：**

```json
{
  "message": "Skill 删除成功"
}
```

**错误响应 (404)：**

```json
{
  "detail": "Skill 'architect_prompt' 不存在"
}
```

### 7. 获取分类列表

```
GET /api/v1/skills/categories
```

**响应 (200)：**

```json
{
  "categories": [
    "orchestrator",
    "reviewer",
    "validation",
    "workflow",
    "api",
    "tool",
    "other"
  ],
  "descriptions": {
    "orchestrator": "编排器角色提示词",
    "reviewer": "审查角色提示词",
    "validation": "验证与修复提示词",
    "workflow": "工作流提示词",
    "api": "API 层提示词",
    "tool": "工具提示词",
    "other": "其他提示词"
  }
}
```

### 8. 重新加载提示词文档

```
POST /api/v1/skills/reload
```

触发提示词提取脚本，重新扫描所有 Skill（包括自定义 Skill）并更新 `PROMPTS.md` 文档。

**响应 (200)：**

```json
{
  "message": "提示词文档已更新",
  "output": "..."
}
```

---

## Agent 集成

### 优先级链

Agent 角色的 `SYSTEM_PROMPT` 属性采用**三级优先级链**：

```
自定义 Skill（最高优先级）
    ↓ 未找到
默认提示词文件（load_xxx_prompt()）
    ↓ 加载失败
兜底提示词（硬编码最小集）
```

### 实现模式

所有 Specialist 子类遵循统一的覆盖模式：

```python
class Architect(Specialist):
    @property
    def SYSTEM_PROMPT(self) -> str:
        # 第一级：从注册表获取用户自定义版本
        try:
            from app.services.skill_registry import get_skill
            custom_prompt = get_skill("architect_prompt")
            if custom_prompt:
                return custom_prompt
        except Exception:
            pass

        # 第二级：使用默认加载逻辑
        prompt = load_architect_prompt()
        if prompt is None:
            # 第三级：兜底提示词
            return self._fallback_prompt()
        return prompt
```

### 支持覆盖的角色

| 角色 | Skill 名称 | 文件位置 |
|------|-----------|----------|
| 架构师 | `architect_prompt` | `app/agent/architect.py:24` |
| 前端工程师 | `frontend_engineer_prompt` | `app/agent/frontend_engineer.py:20` |
| 后端工程师 | `backend_engineer_prompt` | `app/agent/backend_engineer.py:20` |
| 代码审查员 | `code_reviewer_prompt` | `app/agent/code_reviewer.py:20` |
| PPT Agent | `ppt_system_prompt` | `app/agent/ppt_agent.py:95` |

### 覆盖生效流程

```
用户上传 Skill (name="architect_prompt")
    │
    ▼
CustomSkillManager.upload_skill()
    │ 保存文件 → 更新元数据
    ▼
_notify_registry("architect_prompt", "create")
    │
    ▼
SkillRegistry.reload_custom_skills()
    │ 清除旧缓存 → 重新加载所有自定义 Skill
    ▼
下次 Agent 调用时：
    Architect.SYSTEM_PROMPT
    → get_skill("architect_prompt")
    → 返回自定义内容（缓存命中）
```

---

## 分类体系

| 分类 | 标识 | 说明 | 典型用途 |
|------|------|------|----------|
| **编排器** | `orchestrator` | 编排器角色提示词 | 覆盖 Orchestrator 的协调策略 |
| **审查员** | `reviewer` | 审查角色提示词 | 自定义代码审查标准和侧重点 |
| **验证** | `validation` | 验证与修复提示词 | 自定义验证规则和修复策略 |
| **工作流** | `workflow` | 工作流提示词 | 定义特定业务流程和步骤 |
| **API** | `api` | API 层提示词 | API 设计规范和风格指南 |
| **工具** | `tool` | 工具提示词 | 自定义工具使用说明 |
| **其他** | `other` | 其他提示词 | 不属于以上分类的通用提示词 |

---

## 约束规则

### 名称格式

```
^[a-zA-Z][a-zA-Z0-9_-]{0,63}$
```

| 规则 | 说明 |
|------|------|
| 首字符 | 必须是字母（`a-z` 或 `A-Z`） |
| 允许字符 | 字母、数字、下划线 `_`、连字符 `-` |
| 长度 | 1 - 64 个字符 |
| 唯一性 | 全局唯一，重复创建返回 400 |

**合法名称示例：**

- `architect_prompt`
- `backend-engineer-v2`
- `my_custom_reviewer`

**非法名称示例：**

- `123_prompt`（以数字开头）
- `_private`（以下划线开头）
- `my prompt`（包含空格）

### 文件大小

| 限制 | 值 |
|------|-----|
| 单个 Skill 最大内容 | **100 KB**（UTF-8 编码后） |
| 检查时机 | 创建和更新时 |

### 用户配额

| 限制 | 值 |
|------|-----|
| 每个用户最大 Skill 数量 | **50 个** |
| 检查时机 | 创建时 |
| 统计方式 | 按 `author` 字段计数 |

### 文件格式

| 限制 | 值 |
|------|-----|
| 存储格式 | `.md`（Markdown） |
| 编码 | UTF-8 |
| 文件上传 | 仅接受 `.md` 扩展名 |

---

## 热重载机制

### 工作原理

自定义 Skill 系统支持**即时生效**，无需重启服务：

```
用户操作（上传/更新/删除）
    │
    ▼
CustomSkillManager 处理 CRUD
    │
    ▼
_notify_registry(name, action)
    │
    ├─ action="create" 或 "update"
    │   → SkillRegistry.reload_custom_skills()
    │   → 清除所有非系统 Skill → 重新加载文件系统
    │
    └─ action="delete"
        → SkillRegistry.unregister(name)
        → 从内存注册表中移除
    │
    ▼
Agent 下次访问时获取最新内容
```

### 缓存机制

| 层级 | 说明 |
|------|------|
| `SkillInfo._cached_data` | Loader 函数返回值的内存缓存 |
| `SkillInfo._cache_valid` | 缓存有效标志 |
| 失效时机 | `reload_custom_skills()` 时自动清除 |
| 手动失效 | `invalidate_cache(name)` 或 `invalidate_all_cache()` |

### 重载方式

**自动重载（推荐）：** 通过 API 上传/更新/删除时自动触发。

**手动重载：** 调用 `POST /api/v1/skills/reload` 重新扫描并更新提示词文档。

**代码级重载：**

```python
from app.services.skill_registry import get_registry

registry = get_registry()
registry.reload_custom_skills()  # 重新加载所有自定义 Skill
# 或
registry.reload_skill("architect_prompt")  # 重新加载单个 Skill
```

---

## 使用示例

### 示例 1：创建自定义架构师提示词

```bash
curl -X POST http://localhost:8000/api/v1/skills/upload \
  -H "Content-Type: application/json" \
  -d '{
    "name": "architect_prompt",
    "category": "orchestrator",
    "content": "# 微服务架构师\n\n你是一位专注于微服务架构的资深架构师。\n\n## 设计原则\n\n1. 服务拆分按业务领域（DDD）\n2. API Gateway 统一入口\n3. 事件驱动异步通信\n4. 数据库 per-service\n\n## 输出要求\n\n- 必须包含服务拆分图\n- 必须定义 API 契约\n- 必须说明数据流向",
    "description": "微服务架构师专用提示词"
  }'
```

### 示例 2：通过文件上传

```bash
# 准备提示词文件
cat > /tmp/strict_reviewer.md << 'EOF'
# 严格代码审查员

你是一位严格的代码审查员，关注以下方面：

## 审查重点

1. **安全性**：SQL 注入、XSS、敏感信息泄露
2. **性能**：N+1 查询、内存泄漏、阻塞操作
3. **可维护性**：函数长度、圈复杂度、命名规范
4. **测试覆盖**：核心逻辑必须有单元测试

## 输出格式

对每个问题输出：
- 严重程度：P0/P1/P2/P3
- 文件路径和行号
- 问题描述
- 修复建议
EOF

# 上传文件
curl -X POST http://localhost:8000/api/v1/skills/upload-file \
  -F "file=@/tmp/strict_reviewer.md" \
  -F "name=strict_reviewer" \
  -F "category=reviewer" \
  -F "description=严格代码审查标准"
```

### 示例 3：按分类列出 Skill

```bash
curl "http://localhost:8000/api/v1/skills/list?category=orchestrator"
```

### 示例 4：更新已有 Skill

```bash
curl -X PUT http://localhost:8000/api/v1/skills/architect_prompt \
  -H "Content-Type: application/json" \
  -d '{
    "content": "# 更新后的架构师提示词\n\n...",
    "description": "更新为事件驱动架构"
  }'
```

### 示例 5：删除 Skill

```bash
curl -X DELETE http://localhost:8000/api/v1/skills/strict_reviewer
```

### 示例 6：Python 代码中直接使用

```python
from app.services.skill_registry import get_skill, register_skill

# 获取自定义 Skill（Agent 内部使用方式）
custom_prompt = get_skill("architect_prompt")
if custom_prompt:
    # 使用自定义提示词
    system_prompt = custom_prompt
else:
    # 使用默认提示词
    system_prompt = load_architect_prompt()

# 注册内置 Skill（代码中定义）
register_skill(
    name="my_tool_spec",
    category="tool",
    description="自定义工具说明",
    content="# 自定义工具\n\n...",
    author="system"
)
```

---

## 相关文件

| 文件 | 说明 |
|------|------|
| `app/services/skill_registry.py` | 全局 Skill 注册表（296 行） |
| `app/services/custom_skill_manager.py` | CRUD 管理器（292 行） |
| `app/api/v1/skills.py` | API 端点定义（241 行） |
| `app/agent/architect.py` | 架构师 Agent（Skill 集成示例） |
| `app/agent/frontend_engineer.py` | 前端工程师 Agent |
| `app/agent/backend_engineer.py` | 后端工程师 Agent |
| `app/agent/code_reviewer.py` | 代码审查员 Agent |
| `app/agent/ppt_agent.py` | PPT Agent |
