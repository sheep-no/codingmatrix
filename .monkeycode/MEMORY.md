# 用户指令记忆

本文件记录了用户的指令、偏好和教导，用于在未来的交互中提供参考。

## 格式

### 用户指令条目
用户指令条目应遵循以下格式：

[用户指令摘要]
- Date: [YYYY-MM-DD]
- Context: [提及的场景或时间]
- Instructions:
  - [用户教导或指示的内容，逐行描述]

### 项目知识条目
Agent 在任务执行过程中发现的条目应遵循以下格式：

[项目知识摘要]
- Date: [YYYY-MM-DD]
- Context: Agent 在执行 [具体任务描述] 时发现
- Category: [代码结构|代码模式|代码生成|构建方法|测试方法|依赖关系|环境配置]
- Instructions:
  - [具体的知识点，逐行描述]

## 去重策略
- 添加新条目前，检查是否存在相似或相同的指令
- 若发现重复，跳过新条目或与已有条目合并
- 合并时，更新上下文或日期信息
- 这有助于避免冗余条目，保持记忆文件整洁

## 条目

### 多模型 Agent 异常防护机制
- Date: 2026-05-29
- Context: Agent 在执行异常场景分析和防护实现时发现
- Category: 代码模式
- Instructions:
  - 防护模块位于 `app/utils/guardrails.py`
  - Prompt 注入检测：使用正则模式 + 关键词密度 + 结构异常检测
  - 会话 ID 验证：`^[-a-zA-Z0-9]{5,128}$` 格式，禁止保留前缀 `sys_/admin_/internal_/test_`
  - 路径安全检查：禁止绝对路径、父目录遍历、系统目录访问、配置文件访问
  - 磁盘空间监控：低于 1GB 或 10% 时拒绝新请求
  - 内存级速率限制：默认每用户每 60 秒最多 10 个 stream 请求
  - 会话所有权验证：所有 session action 端点必须验证 `user_id` 所有权
  - Schema 验证增强：`output_dir` 和 `project_path` 使用 `validate_path_safety()` 验证
  - 磁盘空间检查集成：stream 和 modify 端点启动前调用 `check_disk_space()`

### 测试框架配置
- Date: 2026-05-12
- Context: Agent 在执行修复单元测试任务时发现
- Category: 测试方法
- Instructions:
  - 后端测试使用 pytest + pytest-asyncio
  - Python 版本为 3.11+，需使用 `asyncio.run()` 替代 `asyncio.get_event_loop()`
  - async fixtures 必须使用 `@pytest_asyncio.fixture` 装饰器，不能用 `@pytest.fixture`
  - 集成测试需添加 `@pytest.mark.skipif` 检查服务器可用性
  - 测试运行命令：`python3 -m pytest tests/unit/ -v`

### bcrypt 密码处理限制
- Date: 2026-05-12
- Context: Agent 在执行修复密码哈希测试时发现
- Category: 依赖关系
- Instructions:
  - bcrypt 算法限制密码最大 72 字节
  - `hash_password` 和 `verify_password` 都需要对密码进行 `[:72]` 截断
  - 未截断会抛出 `ValueError: password cannot be longer than 72 bytes`

### 项目测试目录结构
- Date: 2026-05-12
- Context: Agent 在执行测试修复任务时发现
- Category: 代码结构
- Instructions:
  - 单元测试：`tests/unit/`
  - 集成测试：`tests/integration/`
  - E2E 测试：`tests/e2e/`
  - 前端测试配置：`tests/frontend/`（需要 Vitest 环境）
  - 测试状态报告：`testing/TEST-STATUS-UPDATE-*.md`

### pytest 自定义标记
- Date: 2026-05-12
- Context: Agent 在执行测试运行时发现
- Category: 测试方法
- Instructions:
  - 项目使用自定义 pytest 标记：`unit`, `integration`, `database`, `security`, `agent`, `monitoring`, `logging`, `guardian`
  - 这些标记未在 `pyproject.toml` 中注册，会产生警告但不影响测试执行
  - 建议在 `pyproject.toml` 中注册这些标记以消除警告

### Agent 增量修改与测试验证
- Date: 2026-05-13
- Context: Agent 在执行多模型 Agent 架构分析和增强时发现
- Category: 代码模式
- Instructions:
  - OrchestratorAgent 支持 `incremental=True` 增量修改模式
  - 增量修改通过 SessionManager 检测变更文件，CodePatcher 生成 unified diff patch
  - 测试验证优先使用 DockerRunner（容器化运行+自动释放资源），回退到 IsolatedTestRunner（venv隔离+白名单依赖+安全扫描）
  - IsolatedTestRunner 创建临时 venv 和项目副本运行测试，完成后删除所有临时资源
  - 每次生成/修改后自动 git commit 保存快照（_git_save_snapshot 方法）
  - 新增 `/api/v1/agent/modify` 端点连接上传项目到增量修改流程
  - DependencyGraph 新增 `build_from_existing_project()` 解析 Python import 和 JS require 语句构建真实依赖
  - 测试命令自动检测：pytest / npx playwright test / npm run test

### 文档管理规范
- Date: 2026-05-13
- Context: 用户要求整理文档，所有 md 文档集中在 docs/ 目录下
- Category: 代码结构
- Instructions:
  - 所有项目文档集中在 `docs/` 目录下
  - 功能文档统一放在 `docs/features/` 目录（agent.md, aicloud.md 等）
  - 测试文档合并为单一 `docs/testing/TESTING.md`
  - 模型和架构文档合并到 `docs/architecture/MODELS.md`
  - 指南文档放在 `docs/guides/`（GETTING-STARTED.md, PRODUCTION.md）
  - 项目知识合并到 `.monkeycode/MEMORY.md`，不在 docs/ 中维护副本
  - 规格设计文档保留在 `docs/specs/`（requirements.md + design.md 格式）
  - 过时文档（BADGES.md, COMPREHENSIVE-TEST-REPORT, GIRL_AI_V2_UPGRADE_COMPLETE 等）应删除

### 前端 AgentDashboard 重构模式
- Date: 2026-05-22
- Context: Agent 在执行前端组件重构任务时发现
- Category: 代码结构
- Instructions:
  - AgentDashboard.vue 从 5029 行重构为 ~572 行（减少 89%）
  - 使用 composables 模式分离逻辑：useAgentSession, useAgentGeneration, useAgentFiles, useAgentWorkspace, useAgentStreaming, useAgentBackend
  - Composables 放在 `src/composables/` 目录，按功能模块组织
  - UI 组件放在 `src/components/agent/` 和 `src/components/agent/modals/` 目录
  - 主组件只负责组装 composables 和传递 props/events 给子组件
  - Vue 3 模板中 ref 自动解包，不需要 `.value`；但 `<script setup>` 中操作 refs 需要 `.value`
  - 样式保留在主组件中（276 行），不提取到 composables

### PPT Agent 功能实现
- Date: 2026-05-29
- Context: Agent 在执行 PPT 增强功能开发时发现
- Category: 代码模式
- Instructions:
  - PPT Agent 位于 `app/agent/ppt_agent.py`，负责自然语言到结构化大纲的转换
  - 文本防溢出函数 `prevent_text_overflow()` 在 `app/api/v1/aiGeneratorPptx.py`
  - 自动搜图功能使用 DuckDuckGo 搜索，缓存到 `./static/images/cache/`
  - 配图自动插入到幻灯片右侧位置 (9, 2) 英寸，尺寸 3.5x2.5 英寸
  - API 端点：`/generate-text` (仅大纲) 和 `/generate-from-text` (端到端)
  - 前端支持两种模式：AI Agent 生成和手动输入大纲
