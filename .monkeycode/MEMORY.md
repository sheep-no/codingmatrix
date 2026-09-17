# 用户指令记忆

本文件记录用户指令、偏好与项目知识，供后续交互参考。

## 格式

### 用户指令条目

用户指令条目应遵循以下格式：

[用户指令摘要]
- Date: [YYYY-MM-DD]
- Context: [提及的场景或时间]
- Instructions:
  - [用户教导或指示的内容，逐行描述]

### 项目知识条目

Agent 在执行任务过程中发现的条目应遵循以下格式：

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
  - `tests/e2e/agent-semi-import-live.spec.js` 的增量架构师用 `glm-4.7-flash`，会在 `_analyze_changes_with_architect` 硬失败而非降级；重跑前需冷却数分钟。
  - `glm-4.7-flash` 被上游全局限流时（独立单请求也 429 code 1305），可用同族可用免费档 `glm-4-flash-250414` 临时顶替 architect 角色跑活管线验证；同族模型同样能产出含 `project_spec` 的架构。测完必须恢复默认角色。
  - 模型级并发上限在 `app/agent/llm_client.py`：`MODEL_CONCURRENCY_LIMITS` 定义上限，`get_model_semaphore` 提供信号量，缓存键必须与 `concurrency_limit_for` 同源归一化（小写、去 provider 前缀），否则同一模型的不同写法会各建一个信号量，上限形同虚设。
  - 流式调用的并发额度必须覆盖整个消费期：迭代器一返回上游连接仍在持续输出 token。若只在获取迭代器时持有额度，第二个请求会立即插入，免费档必现 429（code 1305）。排查 429 时先确认本地并发是否真的被压到上限，再怀疑上游拥塞。
  - 切角色做实测前先备份角色快照：`set_roles.py` 的 `set` 模式会用「当前角色」覆盖 `orig_roles.json`，连续两次 `set` 后快照变成 GLM 值，`restore` 就回不到默认值。默认值为 architect `qwen3-8b` / frontend `deepseek-r1` / backend `qwen3.5-4b` / reviewer `glm-z1-9b` / fallback `qwen3-8b`；跑全量 unit 前必须处于默认值，否则 `test_multi_model_agent` 会多一条失败。
  - 活管线重试要把上游 429（code 1305）、流式 180s 超时、架构师输出缺 `project_spec` 都按瞬时错误处理，否则单次抖动就会中断实测。
  - `tests/unit/test_tools.py::TestWriteSyntaxWarning::test_real_defects_are_still_reported` 在内存紧张的全量 run 中会偶发失败：`check_js_source` 依赖 `node -c` 子进程，node 被信号终止时退回的括号启发式抓不到 `const x = ;`。单独复跑通过即属环境性偶发，不是回归。
  - 架构师输出缺 `project_spec` 时 `architect.py` 硬抛是被测试固定的契约（`test_canonicalize_missing_project_spec_raises`、`test_design_architecture_missing_project_spec_raises`），不要当误报门禁改掉；`_build_default_project_spec` 只服务「架构完全失败」的默认路径。

### 扫描文件先定作用与状态再深入
- Date: 2026-08-26
- Context: 深扫 app/api/v1/AiProjectCode.py 时用户纠正——该文件实际已废弃；随后用户明确每次扫描前须先确定文件作用
- Instructions:
  - 每个待扫描文件先弄清「在项目中的实际作用」，结合当前代码库状态判定三态：**活跃**（路由已挂载且有生产消费方）/ **未接入**（设计存在但路由未挂载或符号零消费，属能力未接线）/ **废弃**（被新体系取代的残留）
  - 三态决定缺陷定级与修复方向：活跃面缺陷正常定 P 级；未接入/废弃面缺陷不按活跃定 P 级，标注「未接入/废弃代码内逻辑缺陷」，修复方向是接线或迁移仍活跃的部分后整体退役，而非逐条修缺陷
  - 判定要点：router 是否被 main.py 或上游 router include、文件内定义符号全库引用数、是否存在新副本（双轨）、文件头注释路径与实际路径是否一致（如 `# /api/agent.py` vs 实际 AiProjectCode.py）、是否被新体系取代
  - 前端零引用确认：grep 无引用不足以下结论，需再排除 `import.meta.glob`、`require()`、自动导入插件（unplugin-auto-import/components）与额外构建入口；最终以生产构建产物检索该文件独有的字符串字面量为准，并用确定存活模块的字面量做阳性对照（压缩会重命名符号，符号名不可作判据）。
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
  - `pyproject.toml` 的 `testpaths` 只收集 `tests/unit/` 与 `tests/integration/`，放在被测模块旁的测试文件（如 `app/utils/aicloud/test_*.py`）永远不会被执行；新增测试一律放 `tests/unit/`，迁移后用 `python3 -m pytest <路径> -q` 确认已被收集。

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
- Date: 2026-05-29
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
- Date: 2026-06-09
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
- Date: 2026-05-29
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
  - 用户明确了 `--set-upstream` 的快捷方式：`git push -u origin <branch> -o merge_request.create -o merge_request.title="..." -o merge_request.description="..."`（GitLab 远端可用）。
  - 用户演示了正确用法：`git push -u origin HEAD`（使用 HEAD 而不是完整分支名）
  - 这条是行为指令：以后推送到远程时使用 `-u origin HEAD` 的简洁写法
  - GitHub 远端不支持 GitLab 风格的字符串 push options（会 500）；推 GitHub 用 `git push -u origin HEAD`，PR 走 GitHub API 创建。

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

### Flutter 桌面客户端验证
- Date: 2026-09-08
- Context: 用户要求保留既有修改，并明确 Flutter 开发验证流程
- Category: 测试方法
- Instructions:
  - 客户端位于 `flutter_client/`，验证命令为 `FLUTTER_ALLOW_ROOT=1 flutter analyze` 和 `FLUTTER_ALLOW_ROOT=1 flutter test`。
  - 当前客户端测试覆盖 Widget workbench、SSE 分帧解析、认证客户端和统一模型序列化；静态分析与测试均已通过。

### 协作范围与前端优先
- Date: 2026-09-09 / 2026-08-29 / 2026-09-16
- Context: 用户明确负责范围与优先方向
- Instructions:
  - 负责范围为除 Agent 子系统、Flutter、VS Code 插件以外的全部模块，这三类不主动改动、不清理、不重构。
  - 「Agent」指所有 Agent 子系统，不限于 `app/agent/` 目录。已知归属：`app/agent/**`、`app/utils/agent_core.py`、`app/utils/review/code_review_agent.py`、`app/utils/agent_skills.py`、`app/services/agent_memory_service.py`、`src/components/agent/**`、`src/composables/useAgent*`、`src/stores/agentSession.js`、`src/stores/agentWorkspace.js`、`src/views/AgentDashboard.vue`、`tests/e2e/agent-*.spec.js`、`.claude/skills/` 下 Agent 能力相关 Skill。判断存疑时按「属于 Agent 子系统」处理并先问。
  - 前端优先是功能实现的侧重方向：设置页、供应商与 API Key 状态、模型选择、流式展示、错误反馈、响应式布局、前端测试；范围上限不是前端，后端（非 Agent 部分，含 `app/utils/`）同样在范围内。
  - 合并上游后，若 Agent 子系统文件已含功能修复或全局文案规范落地（如 `app/agent/ppt_agent.py` 的 PPT 修复、`app/agent/tools.py` 的无 Key 检索、Agent 界面中英并列文案），保留现状不回退；冲突文件仍取上游。
  - 修改前读取项目记忆和 Git 状态，保留已有改动；所有手动编辑使用 apply_patch。
  - 测试前调用 background_terminal_list，测试和构建通过受控后台终端执行；未经用户明确要求不提交或推送。

### 多语言 Profile 项目验证
- Date: 2026-09-04
- Context: Agent 在补齐 Core 多语言生成成功门禁时发现
- Category: 构建与编译
- Instructions:
  - 声明式 `FrameworkProfile` 的 `build_command`、`test_command` 和 `validation_steps` 是项目级验证的统一来源。
  - Go `stdlib` Profile 使用 `go build ./...` 与 `go test ./...` 作为生成成功门禁。
  - 运行 Profile 验证前需确认生成目录可作为命令工作目录，并保留命令输出用于诊断。

### 产品术语中英并列
- Date: 2026-09-13
- Context: 用户要求用户可见文案中产品与技术术语保持中英并列
- Instructions:
  - 用户可见的产品/技术术语用「英文/中文」并列，如 Skills/技能、Agent Host/主会话、API Key/接口密钥、OCR/文字识别、Token/令牌、Key/密钥。
  - 保留用户已熟悉的英文原名，同时给出中文释义。

### PPT 生成页真实端到端验收
- Date: 2026-09-16
- Context: Agent 在验收 PPT 大纲与成片内容质量时发现；2026-09-17 按 Key 失效修复更新
- Category: 测试方法
- Instructions:
  - `/ppt-generate` 点「一键生成 PPT」会先校验前端 SiliconFlow Key 状态，缺失时直接跳转 `/settings`，脚本会误判为「点击无效」；须在 `addInitScript` 中写入 `localStorage.codingmatrix_apikeys`（`provider=siliconflow`、`enabled=true`、`expires_at` 未过期）才能进入大纲流程。
  - 不传 `api_key_token`（字段缺省或 `null`）时后端跳过用户 Key 分支，回退到系统默认路由，无需真实供应商 Key 即可完成大纲与成片验收；真实大纲约 10 秒、成片约数秒。
  - 传了无效/过期 `api_key_token`（如少于 30 字符的探针值）时后端返回 401，SSE 给出 `{"type":"error","message":"用户 API Key 未找到或已过期，请重新配置"}`，前端弹出对应错误且不生成大纲；这是预期契约，不要再据此预期「静默成功」。
  - 验收 Key 失效路径时用反向探针：断言 SSE 含 `"type": "error"`、`.outline-slide-editor` 数量为 0、错误提示 3 秒左右即出现（无 3 次重试）。
  - 生成完成后 `workflowStep` 仍为 3，进度是否「不丢」以外层容器判断：生成中为 `.generation-live`，完成为 `.success-container`。

### 本地服务重启
- Date: 2026-09-14
- Context: Agent 在迭代后端代码时明确本地服务重启方式
- Category: 环境配置
- Instructions:
  - 后端 Uvicorn：`cd /workspace && PYTHONPATH=/workspace python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000`。
  - 改后端代码需重启 Uvicorn：用 `background_terminal_kill` 停旧终端后再 `background_terminal_create` 起新的，不要 `pkill`。
  - 重启 Uvicorn 时不要动 Vite（:3000）、Redis（:6379）、Celery（-Q ppt）这些常驻服务。

### 知识库上传的阻塞与死循环陷阱
- Date: 2026-09-17
- Context: Agent 在核查非 Agent 范围已建档缺陷（知识库上传同步阻塞）时总结
- Category: 排查与调试
- Instructions:
  - `app/utils/aicloud/knowledge_processor.chunk_text` 用 `start = end - chunk_overlap` 推进，`chunk_size <= 0` 或 `chunk_overlap >= chunk_size` 时起始位置不前进会原地死循环；调用方必须先校验分块参数，分块器自身也做了钳制（`chunk_size <= 0` 抛 `ValueError`，overlap 收敛到 `chunk_size - 1`）。
  - `parse_document`、`chunk_text` 是同步函数，放进 async 端点时用 `asyncio.to_thread` 包裹；`embed_chunks` 本身已是 async，不要重复包裹。
  - 上传大小上限按 1MB 分块写入时累计校验，超限删除半成品文件；范式参考 `app/api/v1/aiGeneratorPptx.py` 的 `_stream_upload_to_path(file, destination, max_size)`。
  - 验证死循环类防护做回退验证时给 pytest 加 `--timeout=5`，让旧代码的挂起表现为超时失败，避免卡死整个测试进程。
