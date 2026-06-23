# Skills 系统文档

## 概述

本项目的 Skill 系统分为两个层面：

| 层面 | 说明 | 形态 |
|------|------|------|
| **提示词 Skill** | 定义 Agent 角色的系统提示词，控制 Agent 的行为和输出格式 | Markdown 文件 + 用户自定义上传 |
| **认知 Skill** | 为 Agent 注入运行时认知能力（检测、审查、学习、自检、评估） | Python 程序化实现 |

两者协同工作：提示词 Skill 定义"Agent 是谁"，认知 Skill 定义"Agent 能做什么"。

---

## 内置提示词 Skill

所有内置提示词文件位于 `.claude/skills/orchestrator/` 目录：

### 基础角色提示词

| 文件名 | 用途 | 加载函数 |
|--------|------|----------|
| `architect_prompt.md` | 架构师基础提示词 | `load_architect_prompt()` |
| `backend_engineer_prompt.md` | 后端工程师基础提示词 | `load_backend_engineer_prompt()` |
| `frontend_engineer_prompt.md` | 前端工程师基础提示词 | `load_frontend_engineer_prompt()` |
| `code_reviewer_prompt.md` | 代码审查员基础提示词 | `load_code_reviewer_prompt()` |

### 增强角色提示词（实际生效版本）

| 文件名 | 用途 | 加载函数 |
|--------|------|----------|
| `enhanced_orchestrator_prompt.md` | 增强编排器提示词 | `load_orchestrator_prompt()` |
| `enhanced_architect_prompt.md` | 增强架构师提示词 | `load_architect_prompt()` |
| `enhanced_backend_engineer_prompt.md` | 增强后端工程师提示词 | `load_backend_engineer_prompt()` |
| `enhanced_frontend_engineer_prompt.md` | 增强前端工程师提示词 | `load_frontend_engineer_prompt()` |
| `enhanced_code_reviewer_prompt.md` | 增强代码审查员提示词 | `load_code_reviewer_prompt()` |

### 专项审查提示词

| 文件名 | 用途 |
|--------|------|
| `security_reviewer_prompt.md` | 安全审查提示词 |
| `performance_reviewer_prompt.md` | 性能审查提示词 |
| `maintainability_reviewer_prompt.md` | 可维护性审查提示词 |
| `complexity_analysis_prompt.md` | 复杂度分析提示词 |

> **注意**：`app/utils/prompt_loader.py` 中的加载函数实际指向 `enhanced_*` 版本，增强版本是默认生效的。

---

## 认知 Agent Skill

5 个程序化认知 Skill 实现于 `app/utils/agent_skills.py`，由 `AgentSkillsManager` 统一管理。

### Skill 1: 关键词检测（KeywordDetectionSkill）

- **功能**：检测用户输入中的关键词，自动触发规格书生成
- **配置文件**：`configs/keyword_triggers.yaml`（由 `settings.KEYWORD_TRIGGERS_PATH` 指定）
- **触发时机**：用户输入处理时自动调用
- **返回**：触发类型、匹配关键词、引导问题列表

### Skill 2: 多角度审查（MultiAngleReviewSkill）

- **功能**：修改前从兼容性、安全、性能、测试、文档、运维 6 个角度审查变更
- **配置文件**：`configs/review_checklist.yaml`（由 `settings.REVIEW_CHECKLIST_PATH` 指定）
- **触发时机**：`pre_modify_review()` 调用时
- **返回**：各角度检查项及审查状态

### Skill 3: 对比学习（ComparativeLearningSkill）

- **功能**：对比修改前后的代码差异，检测变更模式（新增依赖/函数/类/路由、异步化改造等）
- **配置文件**：无（硬编码模式识别规则）
- **触发时机**：`post_modify_check()` 调用时
- **返回**：变更行数、检测到的模式、改进建议

### Skill 4: 反模式自检（AntiPatternSelfCheckSkill）

- **功能**：修改后自动检查常见错误模式（正则匹配）
- **配置文件**：`configs/anti_patterns.yaml`（由 `settings.ANTI_PATTERNS_PATH` 指定）
- **触发时机**：`post_modify_check()` 调用时
- **返回**：匹配的错误模式列表（含严重等级、修复建议）

### Skill 5: 风险自评（RiskSelfAssessmentSkill）

- **功能**：根据文件路径、变更类型、依赖数量评估修改风险等级（low/medium/high）
- **配置文件**：无（基于规则计算）
- **触发时机**：`pre_modify_review()` 调用时
- **返回**：风险分数、风险等级、风险因素、建议操作

### AgentSkillsManager 统一接口

```python
class AgentSkillsManager:
    def process_user_input(user_input) -> Dict      # 应用关键词检测
    def pre_modify_review(file_path, desc) -> Dict   # 修改前审查（多角度 + 风险）
    def post_modify_check(code, file_path) -> Dict   # 修改后自检（反模式 + 对比学习）
    def get_all_skills_context() -> Dict             # 获取所有技能上下文供 Agent 加载
```

---

## 自定义 Skill 系统

### 架构组件

| 组件 | 文件 | 职责 |
|------|------|------|
| `SkillRegistry` | `app/services/skill_registry.py` | 全局注册表，统一 Skill 注册、加载、缓存 |
| `CustomSkillManager` | `app/services/custom_skill_manager.py` | 用户自定义 Skill 的 CRUD 管理 |
| API Router | `app/api/v1/skills.py` | RESTful API 端点 |

### 支持的 7 个分类

| 分类 | 说明 |
|------|------|
| `orchestrator` | 编排器角色提示词 |
| `reviewer` | 审查角色提示词 |
| `validation` | 验证与修复提示词 |
| `workflow` | 工作流提示词 |
| `api` | API 层提示词 |
| `tool` | 工具提示词 |
| `other` | 其他提示词 |

### CRUD 操作

| 操作 | API 端点 | 说明 |
|------|----------|------|
| 创建 | `POST /api/v1/skills/upload` | 上传 Skill（JSON body） |
| 创建 | `POST /api/v1/skills/upload-file` | 通过文件上传 Skill（multipart） |
| 读取 | `GET /api/v1/skills/{name}` | 获取 Skill 详情和内容 |
| 列表 | `GET /api/v1/skills/list` | 列出所有 Skill（支持按分类/作者过滤） |
| 分类 | `GET /api/v1/skills/categories` | 获取支持的分类列表 |
| 更新 | `PUT /api/v1/skills/{name}` | 更新 Skill 内容和描述 |
| 删除 | `DELETE /api/v1/skills/{name}` | 删除指定 Skill |
| 重载 | `POST /api/v1/skills/reload` | 重新扫描并更新 PROMPTS.md 文档 |

### 热重载机制

自定义 Skill 支持运行时热重载，无需重启服务：

1. **写入触发**：`CustomSkillManager` 执行 CRUD 操作后自动调用 `_notify_registry()`
2. **注册表更新**：`SkillRegistry.reload_custom_skills()` 清除旧的自定义 Skill 并重新扫描文件系统
3. **缓存失效**：`invalidate_cache()` / `invalidate_all_cache()` 清除已缓存的 Skill 数据
4. **存储目录**：自定义 Skill 文件存储于 `/workspace/data/custom_skills/{category}/{name}.md`
5. **元数据**：所有自定义 Skill 的元信息记录在 `/workspace/data/custom_skills/_metadata.json`

### Agent 提示词覆盖机制

每个 Agent（Architect、BackendEngineer、FrontendEngineer、CodeReviewer）的 `SYSTEM_PROMPT` 属性采用三级优先级加载：

```python
@property
def SYSTEM_PROMPT(self) -> str:
    # 优先级 1：从注册表获取用户自定义版本
    custom_prompt = get_skill("architect_prompt")
    if custom_prompt:
        return custom_prompt

    # 优先级 2：从文件系统加载内置提示词
    prompt = load_architect_prompt()
    if prompt:
        return prompt

    # 优先级 3：硬编码兜底提示词
    return self._fallback_prompt()
```

---

## Skill 加载优先级

```
自定义 Skill（用户上传，SkillRegistry）
    ↓ 未找到
内置文件（.claude/skills/orchestrator/*.md，PromptLoader）
    ↓ 未找到
硬编码兜底（Agent._fallback_prompt()）
```

| 优先级 | 来源 | 存储位置 | 更新方式 |
|--------|------|----------|----------|
| 1（最高） | 用户自定义 Skill | `/workspace/data/custom_skills/` | API 上传 / 文件编辑 |
| 2 | 内置提示词文件 | `.claude/skills/orchestrator/` | 编辑 Markdown 文件 |
| 3（最低） | 硬编码兜底 | Agent 源码 `_fallback_prompt()` | 修改代码 |

---

## 相关文件

### 核心模块

| 文件 | 说明 |
|------|------|
| `app/services/skill_registry.py` | 全局 Skill 注册表（SkillRegistry） |
| `app/services/custom_skill_manager.py` | 自定义 Skill 管理器（CustomSkillManager） |
| `app/api/v1/skills.py` | Skill 管理 API 端点 |
| `app/utils/agent_skills.py` | 认知 Skill 实现（5 个 Skill + AgentSkillsManager） |
| `app/utils/prompt_loader.py` | 提示词文件加载器（PromptLoader） |
| `.claude/skills/prompts_loader.py` | 备用提示词加载器 |

### Agent 文件（使用 Skill 覆盖机制）

| 文件 | 说明 |
|------|------|
| `app/agent/architect.py` | 架构师 Agent |
| `app/agent/backend_engineer.py` | 后端工程师 Agent |
| `app/agent/frontend_engineer.py` | 前端工程师 Agent |
| `app/agent/code_reviewer.py` | 代码审查员 Agent |

### 提示词文件目录

| 目录 | 说明 |
|------|------|
| `.claude/skills/orchestrator/` | Agent 角色提示词（13 个文件） |
| `.claude/skills/project_generation/` | 项目生成提示词 |
| `.claude/skills/specs/` | 规格生成提示词 |
| `.claude/skills/validation/` | 验证修复提示词 |
| `.claude/skills/skills/` | 认知技能提示词 |

### 配置文件

| 文件 | 说明 |
|------|------|
| `configs/keyword_triggers.yaml` | 关键词触发配置 |
| `configs/review_checklist.yaml` | 审查清单配置 |
| `configs/anti_patterns.yaml` | 反模式规则配置 |

### 数据目录

| 目录 | 说明 |
|------|------|
| `/workspace/data/custom_skills/` | 自定义 Skill 存储根目录 |
| `/workspace/data/custom_skills/_metadata.json` | 自定义 Skill 元数据 |
| `/workspace/data/custom_skills/{category}/` | 按分类存储的 .md 文件 |
