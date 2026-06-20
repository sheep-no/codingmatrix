# Prompts Extractor Skill

自动提取项目中所有 AI 提示词，生成统一的提示词文档。支持用户自定义 Skill。

## 使用方式

```bash
python3 /workspace/.claude/skills/prompts-extractor/extract.py
```

## 功能

1. **扫描 .md 文件** - 从 `.claude/skills/` 目录提取角色提示词
2. **扫描 Python 代码** - 提取内联的系统提示词和工具提示词
3. **扫描自定义 Skill** - 从 `data/custom_skills/` 目录提取用户上传的提示词
4. **分类整理** - 按类型分组（编排器、审查、规范、验证、工具等）
5. **格式化输出** - 生成 Markdown 文档，支持折叠长内容
6. **来源追踪** - 记录每个提示词的原始文件位置

## 提示词来源

### .md 文件来源（22个）

| 目录 | 提示词类型 |
|------|------------|
| `.claude/skills/orchestrator/` | 架构师、前端工程师、后端工程师、代码审查员等角色提示词 |
| `.claude/skills/project_generation/` | 项目生成系统提示词、继续生成提示词 |
| `.claude/skills/validation/` | 代码补丁、代码修复、交叉验证提示词 |
| `.claude/skills/skills/` | 认知技能提示词 |
| `skills/workflow-planner/` | 工作流规划器提示词 |

### Python 代码来源（24个）

| 文件 | 提示词 |
|------|--------|
| `app/agent/spec_first_generator.py` | OPENAPI, TYPES, DB_SCHEMA, CONFIG |
| `app/agent/refinement_loop.py` | RefinementLoop.SYSTEM_PROMPT |
| `app/agent/cross_validator.py` | CrossValidator.JUDGE_SYSTEM_PROMPT |
| `app/agent/code_patcher.py` | CodePatcher.system_prompt |
| `app/agent/error_classifier.py` | ErrorClassifier.system_prompt |
| `app/agent/error_recovery.py` | ErrorRecovery.system_prompt (2个场景) |
| `app/agent/dependency_graph_validator.py` | DependencyGraphValidator._build_system_prompt |
| `app/agent/react_engine.py` | ReActEngine._build_system_prompt |
| `app/adapter/model_adapter.py` | ModelAdapter.build_system_prompt |
| `app/api/v1/Aicode.py` | GENERAL_PROMPT, CODE_PROMPT, REASONING_PROMPT |
| `app/api/v1/aicloud.py` | AICloud.system_prompt (2个版本) |
| `app/api/v1/GirlAi.py` | CHARACTER_* (5个角色) |
| `app/agent/orchestrator_requirements/llm_prompts.py` | llm_system_prompt |

### 用户自定义 Skill

用户可以通过 API 上传自定义的提示词 Skill，存储在 `data/custom_skills/` 目录。

**API 端点**：

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/v1/skills/upload` | POST | 上传自定义 Skill |
| `/api/v1/skills/list` | GET | 列出所有自定义 Skill |
| `/api/v1/skills/{name}` | GET | 获取 Skill 详情 |
| `/api/v1/skills/{name}` | PUT | 更新 Skill |
| `/api/v1/skills/{name}` | DELETE | 删除 Skill |
| `/api/v1/skills/reload` | POST | 重新扫描并更新 PROMPTS.md |

**上传示例**：

```bash
curl -X POST "http://localhost:8000/api/v1/skills/upload" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "my_architect",
    "category": "orchestrator",
    "content": "# 我的自定义架构师提示词\n\n...",
    "description": "自定义架构师角色提示词"
  }'
```

**支持的分类**：

| 分类 | 描述 |
|------|------|
| `orchestrator` | 编排器角色提示词 |
| `reviewer` | 审查角色提示词 |
| `validation` | 验证与修复提示词 |
| `workflow` | 工作流提示词 |
| `api` | API 层提示词 |
| `tool` | 工具提示词 |
| `other` | 其他提示词 |

## 提示词分类

| 分类 | 图标 | 描述 |
|------|------|------|
| **orchestrator** | 🎯 | 编排器角色提示词 - 项目生成流程中各角色的系统提示词 |
| **reviewer** | 🔍 | 审查角色提示词 - 代码审查和质量评估相关提示词 |
| **spec** | 📋 | 规范生成提示词 - API/类型/数据库/配置规范生成提示词 |
| **validation** | ✅ | 验证与修复提示词 - 代码验证、交叉评审、修复循环提示词 |
| **workflow** | ⚙️ | 工作流提示词 - 任务分解和工作流控制提示词 |
| **api** | 🌐 | API 层提示词 - 对外 API 接口使用的提示词模板 |
| **tool** | 🔧 | 工具提示词 - 内联的简短工具提示词 |
| **other** | 📦 | 其他提示词 - 未分类的提示词 |

## 输出

- **提示词文档**: `/workspace/PROMPTS.md`

## 运行示例

```
$ python3 /workspace/.claude/skills/prompts-extractor/extract.py

============================================================
提示词提取器 v5 (支持自定义 Skill)
============================================================

【1/3】扫描 .md 文件提示词...
  共提取 22 个内置 .md 文件提示词
  共提取 3 个用户自定义 skill

【2/3】扫描 Python 代码提示词...
  从 app/agent/spec_first_generator.py 提取了 4 个提示词
  从 app/agent/refinement_loop.py 提取了 1 个提示词
  ...
  共提取 24 个 Python 代码提示词

【3/3】生成提示词文档...
  提示词文档已保存到: /workspace/PROMPTS.md

============================================================
提取完成！共 49 个提示词
============================================================
```

## 扩展

### 添加内置提示词源

如需添加新的提示词源文件：

1. 在 `extract.py` 中定义新的 `extract_xxx_prompts(content, file_rel)` 函数
2. 在 `extract_python_prompts()` 函数的 `scan_targets` 列表中添加新的文件和提取函数
3. 运行脚本重新提取

### 添加自定义 Skill

用户可以通过以下方式添加自定义 Skill：

1. **API 上传**: 使用 `/api/v1/skills/upload` 端点
2. **文件上传**: 使用 `/api/v1/skills/upload-file` 端点上传 .md 文件
3. **直接放置**: 将 .md 文件放入 `data/custom_skills/{category}/` 目录

## 提示词架构

本项目采用**分层加载**架构管理提示词：

1. **.md 文件层** (`.claude/skills/orchestrator/*.md`) - 提示词的权威来源
2. **加载器层** (`app/utils/prompt_loader.py`) - 提供 `load_xxx_prompt()` 函数
3. **Agent 层** (`app/agent/*.py`) - 通过 `SYSTEM_PROMPT` property 调用加载器
4. **内联层** - 简短的工具提示词直接以字符串字面量写在代码中
5. **自定义层** (`data/custom_skills/`) - 用户上传的自定义提示词

### 提示词加载流程

```
Agent 初始化
  ↓
访问 self.SYSTEM_PROMPT (property)
  ↓
调用 load_xxx_prompt() 函数
  ↓
读取 .md 文件内容
  ↓
失败时使用 _fallback_prompt() 兜底
```

### 自定义 Skill 存储结构

```
data/custom_skills/
├── orchestrator/          # 编排器类
│   ├── my_architect.md
│   └── my_engineer.md
├── reviewer/              # 审查类
│   └── my_reviewer.md
├── validation/            # 验证类
│   └── my_validator.md
└── _metadata.json         # 索引文件
```
