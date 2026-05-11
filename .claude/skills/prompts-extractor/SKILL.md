# Prompts Extractor Skill

自动提取项目中所有 AI 提示词，生成统一的提示词文档。

## 使用方式

```bash
python3 /workspace/.claude/skills/prompts-extractor/extract.py
```

## 功能

1. **扫描 Python 源文件** - 自动识别提示词定义
2. **分类整理** - 按类型分组（系统、角色、架构、验证等）
3. **格式化输出** - 生成 Markdown 文档
4. **来源追踪** - 记录每个提示词的原始文件位置

## 提示词来源

| 文件 | 提示词 |
|------|--------|
| `app/utils/agent_core.py` | system_prompt, resume_prompt |
| `app/api/v1/GirlAi.py` | CHARACTER_* (5个角色) |
| `app/api/v1/Aicode.py` | GENERAL_PROMPT, CODE_PROMPT, REASONING_PROMPT |
| `app/api/v1/aicloud.py` | aicloud_system_prompt |
| `app/utils/workflow/task_decomposer.py` | TaskDecomposer.SYSTEM_PROMPT |
| `app/agent/cross_validator.py` | CrossValidator.JUDGE_SYSTEM_PROMPT |
| `app/agent/refinement_loop.py` | RefinementLoop.SYSTEM_PROMPT |
| `app/agent/orchestrator.py` | Architect, FrontendEngineer, BackendEngineer, CodeReviewer |
| `app/agent/spec_first_generator.py` | OPENAPI, TYPES, DB_SCHEMA, CONFIG |

## 提示词分类

1. **系统提示词 (system)** - Agent 系统级提示词
2. **继续生成提示词 (continue)** - 暂停后继续生成的提示词
3. **角色提示词 (character)** - 虚拟角色配置（5个角色）
4. **通用提示词 (general)** - 通用问答
5. **代码提示词 (code)** - 代码生成相关
6. **推理提示词 (reasoning)** - 深度推理
7. **AI Cloud 提示词 (aicloud)** - AI Cloud 智能助手
8. **工作流提示词 (workflow)** - 任务分解
9. **验证提示词 (validation)** - 代码交叉评审
10. **迭代提示词 (refinement)** - 代码修复循环
11. **架构提示词 (architecture)** - 项目架构设计
12. **前端提示词 (frontend)** - 前端代码生成
13. **后端提示词 (backend)** - 后端代码生成
14. **审查提示词 (review)** - 代码质量审查
15. **规范提示词 (spec)** - API/类型/数据库/配置规范

## 输出

- **提示词文档**: `/workspace/PROMPTS.md`

## 运行示例

```
$ python3 /workspace/.claude/skills/prompts-extractor/extract.py

==================================================
提示词提取器 v3
==================================================

  从 app/utils/agent_core.py 提取了 2 个提示词
  从 app/api/v1/GirlAi.py 提取了 5 个提示词
  从 app/api/v1/Aicode.py 提取了 3 个提示词
  从 app/api/v1/aicloud.py 提取了 1 个提示词
  从 app/utils/workflow/task_decomposer.py 提取了 1 个提示词
  从 app/agent/cross_validator.py 提取了 1 个提示词
  从 app/agent/refinement_loop.py 提取了 1 个提示词
  从 app/agent/orchestrator.py 提取了 4 个提示词
  从 app/agent/spec_first_generator.py 提取了 4 个提示词

共提取 22 个提示词

提示词文档已保存到: /workspace/PROMPTS.md
```

## 扩展

如需添加新的提示词源文件：

1. 在 `extract.py` 的 `extract_all_prompts()` 函数中添加新的 extractor 函数
2. 创建对应的 `extract_from_xxx()` 函数，使用正则表达式提取提示词
3. 运行脚本重新提取
