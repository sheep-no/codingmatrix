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

### SDD 澄清沟通方式
- Date: 2026-08-31
- Context: 用户澄清 SDD 需求讨论方式
- Instructions:
  - SDD 需求澄清阶段采用一问一答方式。
  - Agent 每轮只提出一个问题，等待用户回答后再继续下一项澄清。

### 方案与改代码分开；模型参数保持能力
- Date: 2026-09-11
- Context: 用户确认智谱三角色问题是工程接线，并要求先给方案
- Instructions:
  - 用户只要方案时只给方案，明确说「开始」后再改代码。
  - 智谱/Agent 排障保持模型 max_tokens、thinking、温度和角色分工，修契约、限流和热更新。

### Playwright 依赖解析冲突排查
- Date: 2026-08-29
- Context: Agent 在验证前端聊天路由迁移时发现
- Category: 测试方法
- Instructions:
  - 根目录与 `src/node_modules` 同时安装 Playwright 时，使用 `src/playwright.config.js` 执行位于 `tests/e2e/` 的测试会触发 `Requiring @playwright/test second time`。
  - 前端单元测试可在 `src/` 目录执行 `npx vitest run`；Playwright E2E 需要统一 CLI 与测试文件解析到同一份 Playwright 依赖后再运行。
  - 根配置 `playwright.config.js` 的 `testDir` 为 `./tests/e2e`；运行时用根 CLI + `src/node_modules/@playwright/test`，并设置 `PLAYWRIGHT_EXECUTABLE_PATH` 指向 ms-playwright chromium。
  - 智谱免费档并发：`glm-4.7-flash=1`，`glm-4-flash-250414=20`，`glm-z1-flash` 未单独限流（代码默认 6，受全局 LLM 信号量 6 约束）。
  - Agent 实测用 `TEST_API_KEY`（供应商 `glm`）+ 超管 `mr_yang@example.com` 改角色；流式请求走 `preferredAgentKey`，测完恢复 YAML 角色。
  - `tests/e2e/agent-semi-import-live.spec.js` 的增量架构师用 `glm-4.7-flash`，该模型易触发上游 429（code 1305），会在 `_analyze_changes_with_architect` 硬失败而非降级；重跑前需冷却数分钟。
  - 切角色做实测前先备份角色快照：`set_roles.py` 的 `set` 模式会用「当前角色」覆盖 `orig_roles.json`，连续两次 `set` 后快照变成 GLM 值，`restore` 就回不到默认值。默认值为 architect `qwen3-8b` / frontend `deepseek-r1` / backend `qwen3.5-4b` / reviewer `glm-z1-9b` / fallback `qwen3-8b`；跑全量 unit 前必须处于默认值，否则 `test_multi_model_agent` 会多一条失败。
  - 活管线重试要把上游 429（code 1305）、流式 180s 超时、架构师输出缺 `project_spec` 都按瞬时错误处理，否则单次抖动就会中断实测。

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
  - 项目使用自定义 pytest 标记：`unit`, `integration`, `database`, `security`, `agent`, `monitoring`, `logging`, `guardian`；这些标记未在 `pyproject.toml` 注册，只产生警告不影响执行。
  - 测试目录：单元 `tests/unit/`、集成 `tests/integration/`、E2E `tests/e2e/`、前端配置 `tests/frontend/`（需 Vitest）；测试状态报告在 `testing/TEST-STATUS-UPDATE-*.md`。

### 误报类修复的验证与回归流程
- Date: 2026-09-15
- Context: Agent 在审计 Agent 生成管线误报（跨文件校验、内容门禁、依赖图、符号表）时总结
- Category: 测试方法
- Instructions:
  - 每处误报先写确定性探针复现（不依赖 LLM / Playwright），再用单测固化"正确产物不被拒 + 真实错误仍被拒"两类断言。
  - 用 `git stash push <源文件>` 回退源码后跑新增用例，必须确认新增误报用例失败，证明修复非空；恢复后再核对文件内容一致。
  - 每处修复跑定向测试 + 全量 `pytest tests/unit -q`，并把 `FAILED` 集合与失败基线做 `diff`，只允许失败集合不变。
  - 全量单测存在 Agent 验收范围外的既有失败基线（PPT 18 项、Flutter 3 项、Kolors 1 项，共 22 项），出现新失败必须归因到本次改动。
  - 内存紧张时用 API / 确定性探针替代 Playwright，不启动浏览器。
  - 每个 commit 单独切分支提交推送，合入 master 后重启后端（`PYTHONPATH=/workspace python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000`）并复核 `:8000/docs` 与 `:3000`。
  - 写前语法门禁调用 `node -c` / `tsc` 时，返回码为负表示 node 被信号终止（如 OOM），属环境异常而非源码语法错误；此类情况应退回括号平衡启发式，不能判生成代码语法失败。
  - `CodeValidator` 会在后端进程内 `exec` 生成项目代码做运行时校验。生成项目若与 Agent 自身包同名（如 `app/`），`sys.modules` 已缓存 Agent 同名包会导致假的 "cannot import name ... from 'app'"；排查此类报错时先确认校验是否受同名缓存影响。
  - 门禁类误报的高频模式是把「Agent 执行环境状态」当成「代码缺陷」：未安装的第三方 import、依赖清单中未安装的包、node 被信号终止都属环境状态，不计入代码有效性；只有项目内模块/符号缺失才算缺陷。修一处后要顺带核对同类检查（静态导入、运行时导入、node/tsc 门禁、依赖清单）是否一致。

### bcrypt 密码处理限制
- Date: 2026-05-12
- Context: Agent 在执行修复密码哈希测试时发现
- Category: 依赖关系
- Instructions:
  - bcrypt 算法限制密码最大 72 字节
  - `hash_password` 和 `verify_password` 都需要对密码进行 `[:72]` 截断
  - 未截断会抛出 `ValueError: password cannot be longer than 72 bytes`

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

### Agent 工程能力实测
- Date: 2026-09-13
  - Context: 用户要求用当前模型配置做 Agent 实测；纠正管线不得写死语言和技术栈；并明确验收范围只看 Agent
  - Instructions:
    - 实测使用当前已配置的模型分工，评估工程能力上限。
    - 禁止为某个单一语言或技术栈新增或调整门禁。
    - 入口骨架仅在架构明确框架时生成；依赖扫描保留未映射的第三方包名；关键决策和 Spec-First 仅在需求或复杂度出现鉴权、后端、存储信号时触发。
    - 用户只要 Agent 验收时，关注 Agent 页、代码生成管线，以及 Agent 相关功能（工程师工具调用、MCP、沙箱、Skills、Host）。图表、能力中心独立页、PPT/绘画/工作流、超管面板不算进范围。

### 既有数据库接入 Alembic
- Date: 2026-09-03
- Context: Agent 在完成 PPT 状态迁移收尾时发现
- Category: 构建方法
- Instructions:
  - 应用已初始化过的既有数据库首次接入 Alembic 时，先执行 `alembic stamp 20260902_ppt_quality_state` 登记当前基线。
  - 基线登记后执行 `alembic upgrade head` 验证迁移可幂等通过。
### Core RAG 验证与全量测试
- Date: 2026-09-03
- Context: Agent 在推进多语言代码生成编排和 RAG 接入时发现
- Category: 测试方法
- Instructions:
  - Core 适配器在每个文件生成前通过本地 `RetrievalService` 装配需求、生成契约和架构上下文，并把来源数量、来源 ID 和降级状态写入 `retrieval_status`。
  - 外部 MCP Server 当前全部未启用；验证 Core RAG 时可使用本地 Retriever 独立确认上下文注入路径。
  - 全量测试命令为 `python3 -m pytest -q`；既有 `tests/unit/test_ppt_unified_generation.py` 的多模板生成用例可能超过 90 秒，排除该文件后全量集可在约 76 秒内完成。

### 技能与 RAG 按需求匹配
- Date: 2026-09-04
- Context: 用户指出生成任务不应加载无关 Skill，RAG 查询应绑定当前需求
- Category: 工作流与协作
- Instructions:
  - Skill 必须依据用户当前需求的明确匹配结果按需加载，禁止批量注入无关 Skill 正文。
  - RAG 查询必须使用用户原始需求，并结合目标文件、文件职责和当前生成阶段构造。

### Agent 模型路由限流约束
- Date: 2026-09-03
- Context: 用户审查 Agent 多阶段模型调整方案时强调
- Category: 环境配置
- Instructions:
  - Spec-First 已连续使用 `Qwen/Qwen3-8B` 生成多份规范并执行架构设计，其他阶段避免继续集中路由到该模型，以降低限流风险。
  - 调整模型分工时同时考虑模型质量、跨模型负载分散和供应商限流。
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
  - 动态供应商添加走同一条加密链路：`app/api/v1/providers.py` 的 `POST /api/v1/providers` 只认 `encrypted_api_key`（`AddProviderRequest` 必填），客户端必须先用 `/api/v1/agent/apikey/public-key` 的公钥加密再提交；发明文 `api_key` 会因缺字段被拒。客户端与测试都要按加密字段名断言。

### 前端优先协作范围
- Date: 2026-09-08 / 2026-09-09
- Context: 用户要求保留既有修改，并明确后续工作重点与 Flutter 验证流程
- Instructions:
  - 客户端位于 `flutter_client/`，也可以用 `FLUTTER_ALLOW_ROOT=1 flutter analyze` / `FLUTTER_ALLOW_ROOT=1 flutter test` 直接验证。
  - 后续功能分析和实现以前端为主，重点关注设置页、供应商与 API Key 状态、模型选择、流式展示、错误反馈、响应式布局和前端测试。
  - 后端改动控制在前端链路必需的最小范围。
  - 修改前读取项目记忆和 Git 状态，保留已有改动；所有手动编辑使用 apply_patch。
  - 测试前调用 background_terminal_list，测试和构建通过受控后台终端执行，命令先进入 `/workspace/flutter_client`。
  - 修改后执行 dart format、flutter analyze、定向测试和全量 flutter test，修复失败后再返回；未经用户明确要求不提交或推送。
  - `dart format` 只格式化本次改动的文件；对整个 `lib test` 运行会因本地 SDK 与仓库既有格式不一致产生无关改动，并触发新的 `curly_braces_in_flow_control_structures` 告警。
  - 账号切换竞态的统一守卫是自增 epoch 快照：`NotifierProvider` 重建时复用 notifier 实例，在 `ref.onDispose` 里置位的一次性布尔（如 `_disposed`）会永久生效并静默屏蔽后续请求；`StateNotifierProvider` 重建会新建实例，`mounted` 判断即可。
  - 服务端枚举型契约要按「字段各自独立」校验：`critical_decisions` 的 `default` 与 `options[].label` 不同源，`app/agent/critical_decision.py` 的 `state_management` 模板默认 `Pinia` 而选项只有 `Pinia/Vuex`，客户端下拉直接拿 `default` 当选中值会触发 Flutter 断言。
  - FastAPI 路由的参数位置和字段名都要和客户端保持一致：`app/api/v1/kolors_api.py` 的 `/text-to-image`、`/image-to-image`、`/inpaint` 用 Pydantic 模型收 JSON body，而 `/avatar`、`/landscape`、`/icon` 把 `prompt`、`style` 声明成标量参数（即 query 参数），客户端给这三个快捷路由发 JSON body 会直接 422。
  - Pydantic 模型只有显式声明 `alias` + `populate_by_name` 才接受别名：`aiGeneratorPptx.py` 的 `PPTGenerationRequest.topic` 带 `alias="prompt"`，发 `prompt` 或 `topic` 都通过；而 `app/schema/ppt_outline.py` 的 `OutlineCreateRequest.topic` 无别名，客户端发 `prompt` 会 422，必须发 `topic`。核对 body 字段名时要区分这两种模型。
  - 响应字段名要对照后端返回结构：`GET /pptx/history` 返回 `records`，客户端只读 `items` 会永远得到空列表；`POST /api/v1/history` 和 `POST /api/v1/conversation/history` 返回 `items`，且每条记录是 `prompt` + `response`（没有 `role`/`content`），会话详情必须展开成提问与回答两条消息，否则历史会话只剩提问。测试 fixture 要用后端真实 payload，伪造字段会让缺陷逃过测试。
  - 下载路由要区分「取已有文件」和「按需转换」：`GET /api/v1/pptx/download/{ppt_id}?format=pdf` 只服务于已存在的 `.pdf`，而本应用创建任务时固定 `output_format: 'pptx'`（`aiGeneratorPptx.py:2525` 仅在 `output_format == PDF` 时才生成 PDF），因此该分支必然 404；PDF 必须走专用转换端点 `GET /api/v1/pptx/download/{ppt_id}/pdf`。
  - 后端会用 HTTP 200 + `error` 字段表达「业务失败但请求成功」：`POST /api/v1/chat` 在模型回复为空时返回 `{response: "", conversation_id: null, error: "AI 生成响应为空，未保存历史记录"}`，流式分支同样以 `{"error": ...}` 帧表达。客户端必须读取 `error` 并展示；只读 `response` 会得到一个空白气泡且错误被静默吞掉。
  - 文件上传响应是 `File.to_dict()`（字段 `id`/`filename`/`file_size`/`content_type`/`created_at`/`download_url`），既没有 `server_path` 也没有 `name`；分片续传的 `/upload/init`（命中秒传时把文件放在 `existing_file` 下）和 `/upload/merge`（把文件放在 `file` 下）都带一层信封，客户端应统一展平成同样结构。下载按数据库 `id`（后端契约是 `GET /files/{file_id}/download` 的整型 id），切不可用分片 uuid。附件发给 `/chat` 时，`FileAttachment.server_path` 可填 `filename`，后端 `verify_file_access` 在精确匹配 `file_path` 失败后按 `File.filename == Path(server_path).name` 兜底。
  - 页面级 `_resetAccount()` 的职责是「清本地草稿 + 重新拉取当前账号数据」：切账号会重建 `watch(accessTokenRef)` 的 controller 并清空其 state，因此依赖列表数据的页面在 `_resetAccount()` 里除了清 controller 之外，还要重新调用 `load()`（见 `model_list_page`、`task_queue_page`、`project_files_page`、`mcp_admin_page`、`dynamic_provider_page`、`provider_settings_page`）；漏掉重载会让列表在切账号或改 baseUrl 后一直为空（`virtual_girl_page` 曾遗漏角色列表重载）。

### Agent 断连与恢复契约
- Date: 2026-09-18
- Context: Agent 在核对聊天/Agent 流「断网中断」恢复语义时发现
- Category: 工作流与协作
- Instructions:
  - SSE 开流失败（后端非 200，例如 `POST /api/v1/agent/orchestrate/stream` 在恢复时返回 409「任务已结束或当前进程无可重连任务」/「任务仍有订阅连接」）必须在**打开阶段**抛出，不能只交给流的 `onError`：`AgentStreamClient` 提供 `open()` 返回已解码的事件流并在非 200 时抛 `AgentStreamException(statusCode)`，`generate()` 仅委托 `await open()` 以保持旧 API。
  - `WorkbenchController.startGeneration()` 先 await `open()`；失败时若仍是当前代则把任务置 `disconnected` 后 `rethrow`，被替代的尝试静默返回。调用方据此反馈：`agent_history_page.reconnect()` 捕获后显示「恢复未成功，请刷新详情后重试」，`workbench_page._startGeneration()` 捕获后忽略（controller 已记录断连），避免未处理的异步异常。
  - 后端 `_session_payload.reconnectable = 仅当前进程存活、未结束、且当前无订阅连接`；恢复只重放未消费事件，已消费事件/决策不可重放。工作台断连文案必须指向「会话历史 → 恢复 SSE 连接」，不要写成「恢复尚未接入」。
### 流式响应超时契约
- Date: 2026-09-18
- Context: Agent 在核对聊天/Agent 流「断网中断」语义时发现
- Category: 工作流与协作
- Instructions:
  - 流式响应的空闲超时必须和普通请求超时分离：`AuthenticatedClient.sendJsonStream` 走独立的 `streamTimeout`（默认 5 分钟，逐事件重置），不能复用 `auth.timeout`（20s）。否则 `POST /api/v1/chat` 在服务端准备上下文或等待首个 token 静默 >20s 时会被 `_checked` 误判为「响应连接中断，请确认任务状态后手动恢复」。
  - 测试坑：`Stream.timeout` 在底层是「`async*` 生成器阻塞在永不完成的 await、且从未 yield」时不会触发（纯 `dart run` 可复现）；流超时测试必须用真实 `StreamController` 作为响应体，否则表现为测试永久挂起。
  - 区分度测试（`git stash push -- <源码>` 回退后仍要通过/失败的那条）应只使用默认参数构造被测对象；若用了新增命名参数（如 `streamTimeout`），旧代码会编译失败而不是干净地失败，掩盖真实断言。
### 多语言 Profile 项目验证
- Date: 2026-09-04
- Context: Agent 在补齐 Core 多语言生成成功门禁时发现
- Category: 构建与编译
- Instructions:
  - 声明式 `FrameworkProfile` 的 `build_command`、`test_command` 和 `validation_steps` 是项目级验证的统一来源。
  - Go `stdlib` Profile 使用 `go build ./...` 与 `go test ./...` 作为生成成功门禁。
  - 运行 Profile 验证前需确认生成目录可作为命令工作目录，并保留命令输出用于诊断。

### 编排请求生成开关契约
- Date: 2026-09-18
- Context: Agent 在实现 Flutter 工作台生成开关面板时发现
- Category: 工作流与协作
- Instructions:
  - `POST /api/v1/agent/orchestrate/stream` 的请求体含七个布尔生成开关，默认全为 `true`：`enable_review`、`enable_validation`、`enable_error_recovery`、`enable_memory`、`enable_skills`、`spec_first`、`dependency_graph`（契约见 `app/api/v1/ai_agent/schemas.py` 的 `OrchestratorRequest`）。客户端此前硬编码前六个且从不发送 `enable_skills`；核对编排请求体时必须包含全部七项。
  - 开关在生成开始时取值写入请求体，生成进行中修改不影响本次请求；客户端按 `<baseUrl>|<username>` 作用域持久化，账号切换载入对应作用域。
  - Flutter 工作台已改为能力注册表外壳：模块入口来自 `lib/application/capability_registry.dart`，不再是 `workbench_page` 的弹出菜单；组件测试打开模块用 `capabilityNav_<id>` 键（窄屏先点 `Icons.menu` 打开抽屉）。

### 提交拆分与尾注钩子
- Date: 2026-09-19
- Context: Agent 在把未推送的 Flutter 改动按主题拆分成本地提交时发现
- Category: 工作流与协作
- Instructions:
  - 仓库的 `.git/hooks/prepare-commit-msg` 会为每个提交自动追加 `Co-authored-by: monkeycode-ai <monkeycode-ai@chaitin.com>`；手写同一条会重复，`git commit --amend` 和 `git rebase` 重放提交也会再追加一次，尾注去重要用 `git filter-branch --msg-filter` 归一（该步骤不经过钩子）。
  - 拆分提交时，测试文件里对 UI 文案 / `Key` 的断言必须和引入该文案的源码改动放在同一个提交，否则中间提交测试失败、无法 bisect；逐个提交核对测试里的 `find.text` / `byKey` 字面量是否存在于该提交的 `lib/`。
  - 中间提交还要检查导入不悬空：提交 A 引用的模块不能由提交 B 才新增。
