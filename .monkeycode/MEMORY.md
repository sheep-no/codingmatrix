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

### Playwright 依赖解析冲突排查
- Date: 2026-08-29
- Context: Agent 在验证前端聊天路由迁移时发现
- Category: 测试方法
- Instructions:
  - 根目录与 `src/node_modules` 同时安装 Playwright 时，使用 `src/playwright.config.js` 执行位于 `tests/e2e/` 的测试会触发 `Requiring @playwright/test second time`。
  - 前端单元测试可在 `src/` 目录执行 `npx vitest run`；Playwright E2E 需要统一 CLI 与测试文件解析到同一份 Playwright 依赖后再运行。

### 扫描文件先定作用与状态再深入
- Date: 2026-08-26
- Context: 深扫 app/api/v1/AiProjectCode.py 时用户纠正——该文件实际已废弃；随后用户明确每次扫描前须先确定文件作用
- Instructions:
  - 每个待扫描文件先弄清「在项目中的实际作用」，结合当前代码库状态判定三态：**活跃**（路由已挂载且有生产消费方）/ **未接入**（设计存在但路由未挂载或符号零消费，属能力未接线）/ **废弃**（被新体系取代的残留）
  - 三态决定缺陷定级与修复方向：活跃面缺陷正常定 P 级；未接入/废弃面缺陷不按活跃定 P 级，标注「未接入/废弃代码内逻辑缺陷」，修复方向是接线或迁移仍活跃的部分后整体退役，而非逐条修缺陷
  - 判定要点：router 是否被 main.py 或上游 router include、文件内定义符号全库引用数、是否存在新副本（双轨）、文件头注释路径与实际路径是否一致（如 `# /api/agent.py` vs 实际 AiProjectCode.py）、是否被新体系取代
  - 每个文件建档时先写明「模块定位与状态判定」，再列活跃面/未接入面/废弃面，最后才是缺陷清单
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

### 推送快捷方式
- Date: 2026-05-29
- Context: 用户在审查 git log 时发现推送到远程的命令过长
- Instructions:
  - 用户明确了 `--set-upstream` 的快捷方式：`git push -u origin <branch> -o merge_request.create -o merge_request.title="..." -o merge_request.description="..."`
  - 用户演示了正确用法：`git push -u origin HEAD`（使用 HEAD 而不是完整分支名）
  - 这条是行为指令：以后推送到远程时使用 `-u origin HEAD` 的简洁写法

### 每个 commit 单独分支推送
- Date: 2026-05-29
- Context: 用户在第七批 Bug 修复完成后要求继续扫描
- Instructions:
  - 每个 commit 必须单独分支提交并推送到远程仓库
  - 推完后删除分支
  - 例如：创建分支 `260529-fix-batch-7`，提交，push -u，然后删除本地和远程分支

### 项目代码结构与规模
- Date: 2026-06-09
- Context: Agent 在执行 docs 更新任务时通读全部代码后整理
- Category: 代码结构
- Instructions:
  - 后端: 356 个 Python 文件 / 99,618 行 / 25 个 include_router / 226+ 端点
  - 前端: 9 个 Pinia stores (v5.14.0 文档写 8 个, 漏了 `providers`)、13 个 composables (含 1 个 `useAgentSession` 包装死代码)、16 个 API 客户端、9 个视图 (含 `Docs.vue`)
  - Agent 引擎: 76 模块 + 3 子包 (orchestrator_generation/、orchestrator_requirements/、adapters/) / 34,166 行
  - 单文件 1000+ 行需拆分: agent_core.py (2,393), aiGeneratorPptx.py (1,723), orchestrate_endpoints.py (1,302), cross_validator.py (1,361), dependency_graph.py (1,007), tools.py (1,079)
  - 测试: 88 单元文件 / 1376 用例, 集成测试从 20+ 萎缩到 2 个 (其余归档), 77 E2E spec / 409 用例
  - 部署: 4 容器 (api/celery/redis/nginx), api 仅 127.0.0.1:8080 绑定, nginx 80 暴露
  - 集成测试目录从 v5.11.0 报告的 20+ 文件**缩减到 2 个**，归档到 `tests/archive/integration_old/`
  - Playwright baseURL 已从 8000 改为 3000 (前端 Vite 端口, 经 Nginx 代理到后端 8080)
  - 文档统一: docs/README.md、docs/architecture/ARCHITECTURE.md、docs/architecture/MODULES.md、docs/testing/TESTING.md、docs/guides/PRODUCTION.md、CHANGELOG.md 均更新到 2026-06-09
  - 重复实现: `app/utils/rate_limiter.py` (slowapi) vs `app/middleware/rate_limiter.py` (自研); `app/db/models.py` vs `app/models/`; `src/utils/crypto.js` vs `src/utils/encryption.js`; `src/composables/useAgentSession.js` 是 `stores/agentSession.js` 的薄包装
  - 废弃前端组件: `AgentHeader.vue` 与 `AgentTopBar.vue` 重叠; `AgentInputPanel.vue` 与 `AgentInputBar.vue` 重叠

### 分批次前端扫描
- Date: 2026-08-29
- Context: 用户要求前端问题分多批次重新扫描
- Category: 工作流与协作
- Instructions:
  - 前端深扫按入口认证、状态组合逻辑、视图 API、构建测试部署四个批次执行。
  - 每个批次独立用全库引用、后端路由和配置交叉核验，最终跨批次去重并修订优先级。

### 任务推进与澄清
- Date: 2026-08-29
- Context: 用户要求在存在明确后续步骤时继续执行，只有不确定时才暂停澄清
- Instructions:
  - 对当前任务范围内的明确后续步骤持续推进。
  - 遇到会改变任务方向或结果的真实歧义时，再向用户请求澄清。

### 既有数据库接入 Alembic
- Date: 2026-09-03
- Context: Agent 在完成 PPT 状态迁移收尾时发现
- Category: 构建方法
- Instructions:
  - 应用已初始化过的既有数据库首次接入 Alembic 时，先执行 `alembic stamp 20260902_ppt_quality_state` 登记当前基线。
  - 基线登记后执行 `alembic upgrade head` 验证迁移可幂等通过。
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

- Date: 2026-06-09
- Context: Agent 在执行多语言技术栈锁定修复时发现
- Category: 代码模式
- Instructions:
  - `ProjectProfiler` (`app/agent/project_profiler.py`) 多语言版：python/javascript/go/rust/java 共 5 种 `LanguageProfile`
  - 调用方必须传 `language` 参数（或用 `detect_project_language()` 自动检测），否则默认 python
  - `_profile_project()` in `app/agent/orchestrator_utils.py:103` 现在接受可选 language 参数
  - 语言检测优先级：manifest 文件 > 扩展名计数（Cargo.toml/pom.xml/go.mod/package.json）
 - JS init_file 支持多个变体：index.{js,ts,jsx,tsx,mjs,cjs}

### 生图 Provider Key 加密链路
- Date: 2026-09-06
- Context: Agent 在验证 Kolors 生图资源缓存和 API Key 流程时发现
- Category: 环境配置
- Instructions:
  - 真实 Provider Key 流程为：获取 `/api/v1/agent/apikey/public-key`，使用 RSA OAEP SHA-256 加密原始 Key，提交 `/api/v1/agent/apikey`，再将返回的 `api_key_token` 传给生图接口。
  - 直接设置 `SILICONFLOW_API_KEY` 只验证原始 Provider Key 配置路径，不能证明前端加密提交和 Redis token 解析流程正常。
  - 生图端到端测试可使用 `512x512`、20 步、1 张图片；相同 fingerprint 的第二次请求应返回 `cached=true`，并在约毫秒级完成。

### Flutter 桌面客户端验证
- Date: 2026-09-06
- Context: Agent 在验证新增 Flutter 客户端时发现
- Category: 测试方法
- Instructions:
  - 客户端位于 `flutter_client/`，验证命令为 `FLUTTER_ALLOW_ROOT=1 flutter analyze` 和 `FLUTTER_ALLOW_ROOT=1 flutter test`。
  - 当前客户端测试覆盖 Widget workbench、SSE 分帧解析、认证客户端和统一模型序列化；静态分析与测试均已通过。
