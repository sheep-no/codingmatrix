# 用户指令记忆

本文件记录用户指令、偏好与项目知识，供后续交互参考。条目按主题归并；新增前先查重，重复则合并并更新日期。用户指令条目注明场景，项目知识条目注明类别。

## 协作与沟通

### 需求澄清与方案边界
- Date: 2026-08-31 / 2026-09-11
- Instructions:
  - SDD 需求澄清采用一问一答，每轮只提一个问题，等回答后再继续下一项。
  - 用户只要方案时只给方案，明确说「开始」后再改代码。

### 任务推进与澄清时机
- Date: 2026-08-29
- Instructions:
  - 任务范围内明确的后续步骤持续推进。
  - 遇到会改变任务方向或结果的真实歧义时再请求澄清。

### 协作范围与前端优先
- Date: 2026-09-09 / 2026-08-29 / 2026-09-16
- Instructions:
  - 负责范围为除 Agent 子系统、Flutter、VS Code 插件以外的全部模块，这三类不主动改动、不清理、不重构。
  - 「Agent」指所有 Agent 子系统，不限于 `app/agent/` 目录。已知归属：`app/agent/**`、`app/utils/agent_core.py`、`app/utils/review/code_review_agent.py`、`app/utils/agent_skills.py`、`app/services/agent_memory_service.py`、`src/components/agent/**`、`src/composables/useAgent*`、`src/stores/agentSession.js`、`src/stores/agentWorkspace.js`、`src/views/AgentDashboard.vue`、`tests/e2e/agent-*.spec.js`、`.claude/skills/` 下 Agent 能力相关 Skill。判断存疑时按「属于 Agent 子系统」处理并先问。
  - 前端优先指功能实现的侧重方向，重点是设置页、供应商与 API Key 状态、模型选择、流式展示、错误反馈、响应式布局、前端测试；范围上限不是前端，后端（非 Agent 部分，含 `app/utils/`）同样在范围内。
  - 前端深扫分入口认证、状态组合逻辑、视图 API、构建测试部署四批；每批用全库引用、后端路由与配置交叉核验，最后跨批去重并修订优先级。
  - 修改前读项目记忆和 Git 状态，保留已有改动；手动编辑一律用 apply_patch。
  - 测试/构建前先 `background_terminal_list`，用受控后台终端执行；未明确要求不提交、不推送。

### 技能与 RAG 按需加载
- Date: 2026-09-04
- Instructions:
  - Skill 依据当前需求的明确匹配结果按需加载，禁止批量注入无关 Skill 正文。
  - RAG 查询用用户原始需求，结合目标文件、职责与生成阶段构造。

### Agent 工程能力实测
- Date: 2026-09-11
- Instructions:
  - 用当前已配置的模型分工做实测，评估工程能力上限。
  - 禁止为单一语言或技术栈新增/调整门禁。
  - 入口骨架仅在架构明确框架时生成；依赖扫描保留未映射的第三方包名；关键决策与 Spec-First 仅在需求或复杂度出现鉴权、后端、存储信号时触发。

## 提交与推送

### 提交推送规范
- Date: 2026-05-29
- Instructions:
  - 推送用 `git push -u origin HEAD -o merge_request.create -o merge_request.title="..." -o merge_request.description="..."` 的简洁写法。
  - 每个 commit 单独分支提交推送，推完删除本地和远程分支（如 `260529-fix-batch-7`）。

## 术语与文案

### 产品术语中英并列
- Date: 2026-09-13
- Instructions:
  - 用户可见的产品/技术术语用「英文/中文」并列，如 Skills/技能、Agent Host/主会话、API Key/接口密钥、OCR/文字识别、Token/令牌、Key/密钥。
  - 保留用户已熟悉的英文原名，同时给出中文释义。

## 测试方法

### 测试框架与运行
- Date: 2026-05-12 / 2026-09-03
- Instructions:
  - 后端测试用 pytest + pytest-asyncio；Python 3.11+ 用 `asyncio.run()` 替代 `asyncio.get_event_loop()`；async fixture 用 `@pytest_asyncio.fixture` 而非 `@pytest.fixture`。
  - 目录：单元 `tests/unit/`、集成 `tests/integration/`、E2E `tests/e2e/`、前端 `tests/frontend/`（需 Vitest）；运行 `python3 -m pytest tests/unit/ -v`。
  - 自定义标记：unit/integration/database/security/agent/monitoring/logging/guardian；未在 `pyproject.toml` 注册会产生告警但不影响执行。
  - 集成测试需加 `@pytest.mark.skipif` 检查服务器可用性。
  - 全量 `python3 -m pytest -q`；`tests/unit/test_ppt_unified_generation.py` 多模板用例可能超 90 秒，排除该文件后全量约 76 秒完成。
  - 前端单元测试在 `src/` 执行 `npx vitest run`。

### Playwright 依赖解析
- Date: 2026-08-29
- Instructions:
  - 根目录与 `src/node_modules` 同时安装 Playwright 时，用 `src/playwright.config.js` 跑 `tests/e2e/` 会触发 `Requiring @playwright/test second time`。
  - E2E 从仓库根目录跑：根 `playwright.config.js` 的 `testDir=./tests/e2e`，用根 CLI + `src/node_modules/@playwright/test`，并设 `PLAYWRIGHT_EXECUTABLE_PATH` 指向 ms-playwright chromium。

### Flutter 客户端验证
- Date: 2026-09-08
- Instructions:
  - 客户端位于 `flutter_client/`，验证用 `FLUTTER_ALLOW_ROOT=1 flutter analyze` 与 `FLUTTER_ALLOW_ROOT=1 flutter test`。
  - 命令先进入 `/workspace/flutter_client`；修改后执行 dart format、flutter analyze、定向测试和全量 flutter test，修复失败后再返回。

### PPT 生成页真实端到端验收
- Date: 2026-09-16
- Instructions:
  - `/ppt-generate` 点「一键生成 PPT」会先校验前端 SiliconFlow Key 状态，缺失时直接跳转 `/settings`，脚本会误判为「点击无效」；须在 `addInitScript` 中写入 `localStorage.codingmatrix_apikeys`（`provider=siliconflow`、`enabled=true`、`expires_at` 未过期）才能进入大纲流程。
  - 后端在没有有效 `api_key_token` 时会回退到全局模型配置，因此无需真实供应商 Key 即可完成大纲与成片验收；真实大纲约 10 秒、成片约数秒。
  - 生成完成后 `workflowStep` 仍为 3，进度是否「不丢」以外层容器判断：生成中为 `.generation-live`，完成为 `.success-container`。

## 环境与运维

### 本地服务重启
- Date: 2026-09-14
- Instructions:
  - 后端 Uvicorn：`cd /workspace && PYTHONPATH=/workspace python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000`。
  - 改后端代码需重启 Uvicorn：用 `background_terminal_kill` 停旧终端后再 `background_terminal_create` 起新的，不要 `pkill`。
  - 重启 Uvicorn 时不要动 Vite（:3000）、Redis（:6379）、Celery（-Q ppt）这些常驻服务。

### 模型路由与 Key 流程
- Date: 2026-09-03 / 2026-09-06
- Instructions:
  - Spec-First 已连续使用 `Qwen/Qwen3-8B`，其他阶段避免继续集中路由到该模型，以降低限流风险；调整分工需兼顾模型质量、跨模型负载分散和供应商限流。
  - 智谱免费档并发：`glm-4.7-flash=1`、`glm-4-flash-250414=20`、`glm-z1-flash` 未单独限流（默认 6，受全局 LLM 信号量 6 约束）。
  - Agent 实测用 `TEST_API_KEY`（供应商 glm）+ 超管 `mr_yang@example.com` 改角色；流式请求走 `preferredAgentKey`，测完恢复 YAML 角色。
  - 生图真实 Provider Key 流程：取 `/api/v1/agent/apikey/public-key` → RSA OAEP SHA-256 加密原始 Key → 提交 `/api/v1/agent/apikey` → 把返回的 `api_key_token` 传给生图接口。
  - 直接设置 `SILICONFLOW_API_KEY` 只验证原始 Provider Key 配置路径，不能证明前端加密提交与 Redis token 解析正常。
  - 生图端到端可用 `512x512`、20 步、1 张；相同 fingerprint 第二次请求应 `cached=true` 且毫秒级返回。

## 构建与迁移

### 既有数据库接入 Alembic
- Date: 2026-09-03
- Instructions:
  - 已初始化过的既有库首次接入 Alembic：先 `alembic stamp 20260902_ppt_quality_state` 登记基线，再 `alembic upgrade head` 验证迁移幂等通过。

### 多语言 Profile 验证
- Date: 2026-09-04
- Instructions:
  - 声明式 `FrameworkProfile` 的 `build_command`、`test_command`、`validation_steps` 是项目级验证的统一来源。
  - Go `stdlib` Profile 用 `go build ./...` 与 `go test ./...` 作为生成成功门禁。
  - 运行 Profile 验证前确认生成目录可作为命令工作目录，并保留命令输出用于诊断。

### bcrypt 密码限制
- Date: 2026-05-12
- Instructions:
  - bcrypt 密码上限 72 字节；`hash_password` 与 `verify_password` 都需 `[:72]` 截断，否则抛 `ValueError: password cannot be longer than 72 bytes`。

## 代码扫描与结构

### 扫描文件先定作用与状态
- Date: 2026-08-26 / 2026-09-16
- Instructions:
  - 每个待扫描文件先弄清「在项目中的实际作用」，结合当前代码库判定三态：活跃（路由已挂载且有生产消费方）/ 未接入（设计存在但路由未挂载或符号零消费）/ 废弃（被新体系取代的残留）。
  - 三态决定缺陷定级与修复方向：活跃面缺陷正常定 P 级；未接入/废弃面缺陷标注「未接入/废弃代码内逻辑缺陷」，修复方向是接线或迁移仍活跃的部分后整体退役。
  - 判定要点：router 是否被 main.py 或上游 include、文件内符号全库引用数、是否存在新副本（双轨）、文件头注释路径与实际路径是否一致。
  - 前端零引用确认：grep 无引用不足以下结论，需再排除 `import.meta.glob`、`require()`、自动导入插件（unplugin-auto-import/components）与额外构建入口；最终以生产构建产物检索该文件独有的字符串字面量为准，并用确定存活模块的字面量做阳性对照（压缩会重命名符号，符号名不可作判据）。
  - 建档先写「模块定位与状态判定」，再列活跃面/未接入面/废弃面，最后列缺陷清单。

### 项目结构与关键模块
- Date: 2026-05-13 / 2026-06-09
- Instructions:
  - 文档集中 `docs/`：功能 `docs/features/`、测试 `docs/testing/TESTING.md`、架构 `docs/architecture/MODELS.md`、指南 `docs/guides/`；项目知识只在 `.monkeycode/MEMORY.md` 维护一份，docs 不重复。
  - 前端 AgentDashboard 已用 composables 拆分：`src/composables/` 按功能模块组织，UI 组件在 `src/components/agent/` 与 `src/components/agent/modals/`，主组件只组装 props/events。
  - Agent 增量修改：OrchestratorAgent `incremental=True` 经 SessionManager 检测变更文件、CodePatcher 生成 unified diff patch；测试优先 DockerRunner，回退 IsolatedTestRunner；每次生成/修改后 `_git_save_snapshot` 自动 commit。
  - 防护模块 `app/utils/guardrails.py`：Prompt 注入用正则 + 关键词密度 + 结构异常检测；会话 ID 格式 `^[-a-zA-Z0-9]{5,128}$` 且禁止 `sys_/admin_/internal_/test_` 前缀；路径禁止绝对路径、父目录遍历、系统目录与配置文件访问；磁盘低于 1GB 或 10% 拒绝新请求；内存级限速默认每用户每 60 秒最多 10 个 stream 请求；session action 端点必须校验 `user_id` 所有权。
  - PPT Agent 在 `app/agent/ppt_agent.py`（自然语言 → 结构化大纲）；文本防溢出 `prevent_text_overflow()` 在 `app/api/v1/aiGeneratorPptx.py`；自动搜图缓存到 `./static/images/cache/`；端点 `/generate-text`（仅大纲）与 `/generate-from-text`（端到端）。
  - `ProjectProfiler` 多语言版支持 python/javascript/go/rust/java；调用方须传 `language`（或用 `detect_project_language()` 自动检测），否则默认 python；检测优先级 manifest 文件 > 扩展名计数。
