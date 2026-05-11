---
name: project-wiki
description: 根据现有代码仓库，递归分析项目结构和代码内容，生成 DeepWiki 风格的完整项目文档。支持三种模式：新项目规划、完整生成、同步/刷新。
arguments:
  - name: workspace
    description: 项目工作目录的绝对路径
    required: false
---

# Project Wiki

根据现有代码仓库，递归分析，**尽可能细致地**理解其项目结构、代码结构、代码内容，帮助用户生成 DeepWiki 风格的完整项目文档。

## Detection Logic

自动检测运行模式，按以下顺序判断：

1. **检查 Git Submodules**
   - 检查 `.gitmodules` 文件是否存在
   - 如果有则执行 `git submodule update --init --recursive --depth 1`

2. **新项目规划模式**
   - 触发条件：项目为空（无源代码文件）
   - 触发关键词："新项目"、"从零开始"、"规划项目"
   - 详见 [new-project-plan.md](./new-project-plan.md)

3. **同步/刷新模式**
   - 触发条件：存在 `{{workspace}}/docs/ai-generated/` 目录
   - 触发关键词："同步文档"、"更新文档"、"刷新wiki"
   - 详见 [sync-code-docs.md](./sync-code-docs.md)

4. **完整生成模式**（默认）
   - 触发条件：已有代码但不存在文档结构
   - 触发关键词："生成文档"、"创建文档"、"构建wiki"
   - 详见 [existing-code-docs.md](./existing-code-docs.md)

## Workflow

```
1. 检测运行模式
   ├── 检查 .gitmodules → 拉取 submodules
   ├── 项目为空？ → 新项目规划模式
   ├── 存在 ARCHITECTURE.md？ → 同步模式
   └── 否则 → 完整生成模式

2. 执行对应工作流
   ├── 新项目规划：交互式问答收集需求 → 生成文档
   ├── 完整生成：分析仓库 → 创建文档结构 → 填充内容
   └── 同步/刷新：检测变更 → 增量更新

3. 提交文档
   ├── git commit
   ├── git push
   └── 向用户确认并收集反馈
```

## Output Structure

生成的文档结构：

```
{{workspace}}/docs/
├── INDEX.md              # 文档索引
├── ARCHITECTURE.md       # 系统架构文档
├── INTERFACES.md         # 接口文档
├── DEVELOPER_GUIDE.md    # 开发者指南
├── ai-generated/         # AI 生成的文档
│   ├── 专有概念/           # 核心概念页面
│   │   ├── [Concept1].md
│   │   └── [Concept2].md
│   └── 模块/              # 模块 README
│       ├── [Module1].md
│       └── [Module2].md
└── [其他项目文档...]
```

## Specs Directory Structure

功能规格目录结构：

```
{{workspace}}/.monkeycode/specs/
├── DEPRECATED.md              # 废弃功能说明
├── deprecated/                 # 废弃的功能规格
│   ├── sketch-to-code/
│   └── prompt-art-gallery/
├── ephemeral-workflow/         # 已完成：临时工作流
│   ├── requirements.md
│   ├── design.md
│   └── tasklist.md
└── aicloud/                   # 规划中：AI 云助手
    ├── requirements.md
    └── design.md
```

**废弃功能处理**：
- `DEPRECATED.md` 记录废弃原因和替代方案
- 不为废弃功能生成或更新文档
- 只为活跃功能和规划中的功能生成文档

## Constraints

**源代码只读**:
- 可以分析仓库中的任何文件
- **绝不**修改源代码文件
- **只能**创建/更新文档文件（Markdown）
- 默认文档位置: `{{workspace}}/docs/ai-generated/`（如果存在现有约定则遵循）

**禁止臆造**:
- 文档必须严格基于实际代码、配置和测试
- 绝不编造代码中不存在的功能、API或行为
- 无法确定时说"无法确定"而不是猜测

**禁止泄露密钥**:
- 绝不在文档中包含 API 密钥、密码、令牌或凭证
- 在示例中使用占位符如 `<API_KEY>`

## Templates

文档模板参考 [templates.md](./templates.md)

## Notes

- 除非执行「新项目规划」工作流，否则在不与用户交互的前提下完成任务
- 如果 workspace 目录下存在多个子项目（类似 submodule），所有文档输出到 `{{workspace}}/docs/ai-generated/` 而不是子项目目录
- 完成后向用户确认是否满意，根据反馈迭代完善
