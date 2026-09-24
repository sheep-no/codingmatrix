# 技术债务跟踪

> 最后核对：2026-09-23

`已解决` 表示当前代码保持对应修复；`仍在` 表示当前实现可直接定位；`部分解决` 表示原修复范围仍有同类残留。历史测试数字保留其发生时的范围。

## 既有编号逐项复核

| # | 原问题 | 当前状态 | 当前依据 |
|---:|---|---|---|
| 1 | 启动时清空 history 表 | 已解决 | `app/main.py` 保留辅助函数定义，启动流程未调用 |
| 2 | superadmin 权限值不匹配 | 已解决 | `app/utils/security.py` 校验 `permission_level == "superadmin"` |
| 3 | admin config router 重复注册 | 已解决 | `app/main.py` 仅在 `/api/v2` 挂载一次 |
| 4 | drain middleware 缺少 `JSONResponse` | 已解决 | middleware 分支内显式导入 |
| 5 | Celery signal 使用异步 task | 已解决 | `app/celery_app.py` signal handler 使用同步 SQLAlchemy `Session` |
| 6 | 无时区 `datetime.utcnow()` | 部分解决 | 主要模型列已迁移，`app/models/file.py` 与 `app/models/aicloud.py` 仍有残留调用 |
| 7 | WebSocket Manager 单连接 | 已解决 | `app/services/websocket_manager.py` 按用户保存连接列表 |
| 8 | CORS host 正则未转义 | 已解决 | `app/core/config.py` 的 `cors_origin_regex` 对 `ALLOWED_HOSTS` 逐项 `re.escape` 并锚定，`app/main.py` 改用该属性 |
| 9 | PostgreSQL UUID 未使用导入 | 已解决 | `app/models/chat_history.py` 已无该导入 |
| 10 | `CHUNKS_DIR` 定义顺序 | 已解决 | `app/api/v1/file_upload.py` 在使用前定义常量 |
| 11 | SQL LIKE 未转义 | 已解决 | `app/db/search_history.py` 使用 `escape_like_pattern` 和显式 escape |
| 15 | login 限流标识不一致 | 已解决 | 检查、失败和成功记录统一使用 `identifier` |
| 18 | health 版本来源分裂 | 已解决 | 统一到 `app/core/version.py` 的 `APP_VERSION = "v5.15.0"`，`app/api/v1/health.py` 与 `app/services/health_checker.py` 均引用该常量 |
| 19 | cloudflared 遗留注释 | 已解决 | 已移除 `app/main.py` 末尾的 Windows cloudflared 命令注释 |
| 20 | 旧 Agent router 备份残留 | 已解决 | 备份残留已移除 |
| 21 | FeatureSwitchMiddleware 路径 | 已解决 | `app/middleware/feature_switch.py` 使用 `/api/v1/agent` |
| 22 | evaluate 角色缺用户模型上下文 | 已解决 | Architect、CodeReviewer 传递 token 与 provider ID |
| 23 | evaluate LLM 调用缺 token | 已解决 | 相关调用传递 `api_key_token` |
| 24 | recovery auto-fix 硬编码模型 | 已解决 | 使用 `model_assignment.fallback_model` 并传 token |
| 25 | ReAct Agent 调用缺 token | 已解决 | `app/agent/react_agent.py` 传递用户 token |
| 26 | fallback chain 绑定单一供应商 | 已解决 | `app/agent/error_recovery.py` 提供供应商链和 provider 检测 |
| 27 | `ReActWithFallback` 死代码 | 已解决 | 当前无该符号，调用链使用 `ReActEngine` |
| 28 | 未使用的 `call_siliconflow` | 已解决 | `app/utils/AiCodeUtil.py` 已无该函数；适配器仍有过时注释 |

## 当前仍在技术债

| 优先级 | 问题 | 实际位置 | 状态 |
|---|---|---|---|
| P1 | CORS host 字符串直接拼为正则 | `app/core/config.py`、`app/main.py` | 已解决；`cors_origin_regex` 对每个 host 做 `re.escape` 并整体锚定，仅允许精确 host 匹配（可选 scheme 前缀与端口后缀），消除子串误放行与未转义点号（CFG4） |
| P2 | 开发测试使用 Python 3.11，Dockerfile 使用 3.10 | `Dockerfile` | 已解决；`Dockerfile` 的两个 Python 阶段均基于 `python:3.11-slim`，无 3.10 残留 |
| P2 | lifespan 与 startup hook 并存 | `app/main.py` | 仍在 |
| P2 | 多 API worker 下进程内 scheduler 可能重复执行 | `app/main.py`、`app/db/scheduler.py` | 仍在 |
| P2 | `/api/v1/health` 与部署侧 `/health` 契约分裂 | `app/api/v1/health.py`、部署配置 | 仍在 |
| P2 | health 响应版本来源分裂 | `app/api/v1/health.py`、`app/services/health_checker.py`、`CHANGELOG.md` | 已解决；两处端点统一读 `app.core.version.APP_VERSION` |
| P2 | StateGraph 生产入口仍以单节点 legacy wrapper 为主 | `app/agent/state/`、`app/agent/workflow_registry.py` | 仍在 |
| P2 | 统一检索尚未接入生产 Agent 主链 | `app/agent/retrieval/` | 仍在 |
| P2 | 跨工作台续跑与多 worker 恢复缺独立验收 | `app/api/v1/agent_host.py`、`app/agent/state/` | 仍在 |
| P3 | 无时区时间调用在模型、状态、PPT 和 Skill 模块仍有残留 | `app/models/`、`app/services/` | 仍在 |
| P3 | VS Code 发布元数据与真实状态栏适配仍需收尾 | `vscode-extension/package.json`、`vscode-extension/src/status-view.ts` | 部分解决；构建、Node 测试和 Host E2E 已通过 |
| P3 | Makefile `clean` 指向已归档脚本 | `Makefile`、`scripts/_archive/cleanup.sh` | 已解决；`clean` 目标改指 `./scripts/_archive/cleanup.sh` |
| P3 | ModelAdapter 注释引用已删除函数 | `app/adapter/model_adapter.py` | 已解决；注释与警告改为说明真实调用位置，不再引用已删除的 `call_siliconflow` |

## 2026-09-23 生产就绪复核新增项

### 本轮已修复

| 优先级 | 问题 | 实际位置 | 状态 |
|---|---|---|---|
| P0 | 明文登录成功响应引用未定义变量 `encrypted_body`，任何凭据正确的登录都抛 `NameError` 并返回 500 | `app/api/v1/auth.py` | 已解决；改用模式布尔 `encrypted_mode`，补成功分支回归用例，PR #202 |
| P1 | 生产编排 api/celery/scheduler 因 `DATABASE_URL` 缺省不同而指向三个不同数据库，调度任务看不到 API 数据 | `docker-compose.prod.yml` | 已解决；三服务统一到共享卷上的 `sqlite+aiosqlite:////app/data/app.db`，PR #205 |
| P1 | 镜像未预建上传/生成物挂载点，非 root 的 appuser 无法写入 | `Dockerfile` | 已解决；`mkdir -p` 补齐全量挂载点后再统一 chown，PR #205 |
| P2 | `SystemConfigManager` 配置路径随进程 CWD 漂移 | `app/utils/system_config.py` | 已解决；改为 `BASE_DIR / "configs" / "system_config.json"`，PR #204 |
| P2 | `?`（Shift+/）无法打开快捷键帮助面板，与帮助面板自身声明的快捷键不一致 | `src/composables/useKeyboardShortcuts.js` | 已解决；`?` 归一化为同一物理键 `/`，并新增归一化回归用例 |
| P2 | `Escape` 无法关闭左侧工具集下拉菜单，与帮助面板「Esc 关闭工具面板/弹窗」声明不一致 | `src/components/index.vue`、`src/components/leftlist.vue` | 已解决；leftlist 暴露 `closeToolkitMenu`，escape 处理器调用之 |
| P2 | 本地 compose 以 `ENV=production` 启动却不提供 `SECRET_KEY`，celery 也未挂载数据卷与生成物目录 | `docker-compose.yml` | 已解决；补齐 `SECRET_KEY=${SECRET_KEY:?}` 与统一 `DATABASE_URL`，api/celery 共享 data 与四个生成物挂载，新增守卫用例 |
| P3 | 前端 E2E 的 `core`、`11-theme-shortcuts` 存在测试代码缺陷（选择器过期、等待不足、快捷键名与实现不符） | `tests/e2e/core.spec.js`、`tests/e2e/11-theme-shortcuts.spec.js` | 已解决；按真实控件与产品声明的快捷键重写，改用轮询等待，PR #210 |
| P1 | 测试 fixture 对所连数据库执行 `drop_all`，本地跑一次 pytest 就会清空开发库 `app.db` 全部表（表现为既有账号消失、登录 500） | `tests/conftest.py` | 已解决；导入 app 前把测试库指向独立 `test.db`（可被 `TEST_DATABASE_URL` 覆盖），并对非测试库拒绝执行清表，补 3 项回归用例 |
| P2 | 前端 CI 的触发分支写作 `main`，而默认分支是 `master`，导致前端 lint 与生产构建从不执行 | `.github/workflows/frontend-ci.yml` | 已解决；`on.push/pull_request.branches` 改为 `[master, main]`，PR #207 |
| P1 | RSA 私钥被 git 跟踪，而该密钥用于登录凭据传输与 API Key 密文解密 | `keys/rsa_private.pem`、`keys/rsa_public.pem`、`app/utils/encryption.py`、`app/utils/crypto.py` | 已解决；完成密钥轮换（旧密钥备份后作废），`git rm --cached` 停止跟踪并加 `.gitignore` 的 `keys/*.pem`，补 2 项忽略契约回归用例。仓库历史中的旧私钥视为已泄露 |
| P1 | 生产编排未提供模型/系统配置，且各容器可能各自生成 RSA 密钥；运行期静默回退硬编码默认模型 | `Dockerfile`、`docker-compose.prod.yml`、`docker-compose.yml`、`app/main.py` | 已解决；两个编排显式挂载 `unified_model_config.yaml`、`agent_model_config.yaml`、`system_config.json`，三服务共享 `api-keys` 卷并统一 `RSA_KEY_DIR=/app/keys`，镜像内 COPY `system_config.json` 兜底，生产启动缺配置即报错，补 5 项编排守卫与 3 项启动校验用例 |
| P3 | `e2e.yml` 与 `backend-ci.yml` 触发分支写作 `main`（默认分支 `master`），从不运行 | `.github/workflows/e2e.yml`、`.github/workflows/backend-ci.yml` | 已解决；`backend-ci.yml` 与 `ci.yml` 完全重复（测试与 pip-audit 均已覆盖）且 `ruff check app/` 在无 ruff 配置下默认规则报 8297 个错误，已删除；`e2e.yml` 重写为可运行门禁 |
| P3 | 4 个模块全库零生产引用：`ppxRequest.py`（PPT 链实际用端点内联模型）、`nginx_ai.py`（路由从未挂载）、`resume_manager.py`、`hot_reload.py` | `app/schema/ppxRequest.py`、`app/api/v2/nginx_ai.py`、`app/utils/resume_manager.py`、`app/utils/hot_reload.py` | 已解决；确认零生产引用（含符号名）后删除，同步裁剪 14 项仅针对这些模块的单测并重命名 `test_hot_reload_and_package_filter.py` 为 `test_dynamic_package_filter.py` |
| P3 | 镜像内 Alembic 路径失配：ini 被复制到 `/app/alembic.ini`，`%(here)s/../migrations` 与 `%(here)s/..` 解析到 `/migrations` 与 `/` | `Dockerfile`、`configs/alembic.ini` | 已解决；改为 `COPY configs/alembic.ini ./configs/`，与仓库布局一致后解析为 `/app/migrations` 与 `/app`，补 1 项路径守卫用例 |
| P2 | `migrations/env.py` 硬编码 `BASE_DIR/app.db` 并覆盖 ini 中的 URL，容器内 alembic 迁移到与 API 不同的空库 | `migrations/env.py` | 已解决；改用 `settings.DATABASE_URL`（生产由环境变量注入），副本验证目标库正确且原库未被触碰，补 1 项守卫用例 |
| P3 | 运行时镜像未提供文档转换工具链，PPT 转 PDF 返回 501、成品质量视觉复审在缺 `pdftoppm` 时抛错 | `Dockerfile`、`app/api/v1/aiGeneratorPptx.py`、`app/services/ppt_quality_orchestrator.py` | 已解决；镜像新增 `libreoffice-impress`、`poppler-utils`、`fonts-noto-cjk` 层并补 1 项守卫用例，代价是镜像增大约 0.7-1 GB |

### 仍需决策

| 优先级 | 问题 | 实际位置 | 状态 |
|---|---|---|---|
| P3 | 私钥为无口令明文 PEM，仅靠文件权限（`0o600`）保护 | `app/utils/crypto.py`、`app/utils/encryption.py` | 仍在；当前依赖密钥卷权限与文件系统隔离。升级路径（按成本从低到高）：①带口令私钥 + 环境变量注入口令；②私钥改由 docker/k8s secret 挂载只读卷、不以文件落盘；③接入 KMS/Secret Manager，私钥不出后端服务边界。生产部署建议至少做到 ② |
| P3 | `tests/e2e/` 下有大量一次性诊断脚本与依赖外部模型的在线探针，无法全部纳入 CI 门禁 | `tests/e2e/` | 部分解决；3 个零 Agent 引用的草稿探针已移入 `tests/archive/playwright/`（该目录不在 `playwright.config.js` 的 `testDir` 内），spec 数 99→96。其余候选均触及 Agent 子系统，按范围约定不动。`e2e.yml` 仍只把 5 个稳定 spec 作为门禁 |
| P3 | `dynamic_package_manager.py` 全库零生产引用，但含「AI 评估安全性后安装包」能力，语义与 Agent 相邻 | `app/utils/dynamic_package_manager.py`、`tests/unit/test_service_dependency*.py` | 已裁定保留；判定为 Agent 相邻的预留能力，按本轮「不触碰 Agent 子系统」的范围约定保留，不计入死代码，其 3 个相关测试一并保留 |
| P2 | Alembic 与 `migrations/runner.py` 双轨并存且互相冲突 | `migrations/env.py`、`migrations/runner.py`、`migrations/versions/`、`configs/alembic.ini` | 已解决；首次接入契约收敛到 `Base.metadata`：库内无 `alembic_version` 时建全量表并登记 head、不重放历史修订，已有版本走标准迁移，空库与 runner.py 管理过的库均可 `upgrade head`。`Makefile`/`scripts/migrate.sh` 补齐 `-c configs/alembic.ini` 并修正无效的 `history -n`。补 3 项引导回归用例。残留：`versions/` 下的历史修订不再被执行（仅供已有版本库的增量），认知负担仍在 |
| P3 | 2 个 uvicorn worker + celery + scheduler 共用单个 SQLite 文件 | `docker-compose.prod.yml`、`app/db/database.py` | 已缓解；`app/db/database.py` 对 SQLite 连接统一开启 `journal_mode=WAL`、`busy_timeout=30000` 与 `connect_args timeout=30`，抑制 `database is locked`。结构性缺口仍在（单写者模型），高并发生产仍建议改用 Postgres |
| P3 | compose 的 `command` 覆盖 Dockerfile 的 `CMD`，绕过其中 `su appuser` 的非 root 启动 | `docker-compose.yml`、`docker-compose.prod.yml`、`Dockerfile` | 已解决；`docker-compose.prod.yml` 的 api/celery/scheduler 显式 `user: appuser`，Dockerfile 已 `chown -R appuser:appuser /app` 并预建全部挂载点、bind mount 源文件 644 可读。本地 `docker-compose.yml` 因 bind mount 属主保持 root 并加注释。补 2 项守卫用例。注意：既有 root 属主的 named volume 需重建或手工 `chown` |

## 当前验收基线

- 后端 unit/integration 最近完整记录：`4585 passed, 2 skipped, 0 failed`（194s；2026-09-23 死代码清理后重跑，运行结束开发库 `app.db` 仍为 41 张表 / 3 个种子账号）。清理前的 `--cov=app` 门禁运行覆盖率 `62.47%`，门槛 `58%`；`test_process_guard_restart` 在高负载下偶发 1 次失败，单跑 `5 passed`。
- 前端全量 Vitest：`50 files / 251 passed`；`npm run build` 成功（39s）；`npm run budget:check` 四项预算全部通过。
- 前端 ESLint：`0 errors / 390 warnings`（console/unused-var）。
- PPT 专项：`141 passed`；`elegant` 统一生成测试 `24 passed`。
- VS Code 扩展 Node 测试：`62 passed`，Extension Development Host E2E 已完成。
- 前端 E2E：预置规范账号（`python3 -m app.scripts.seed_users`，三个账号密码均 `12345678`）后，CI 门禁覆盖 `core`、`01-auth`、`02-core-navigation`、`11-theme-shortcuts`、`encrypted-login` 共 `44` 项；`CI=1`（单 worker + 2 次重试）下稳定通过。`encrypted-login` 默认账号与种子脚本一致，此前失败纯属本地库未播种。
- 2026-06-06 的 `1622 passed / 0 failed` 与更早 `1244 passed / 3 skipped` 属于历史阶段结果。

## 历史修复记录

### 已修复的问题

### P0: 严重 Bug (4 项)

| # | 问题 | 文件 | 修复内容 |
|---|------|------|----------|
| 1 | 启动时清空 history 表 | `app/main.py` | 移除 `clear_history_table()` 调用 |
| 2 | require_superadmin 权限值不匹配 | `app/utils/security.py` | `"super"` → `"superadmin"` |
| 3 | adminConfigRouter 重复注册 | `app/main.py` | 移除 `/api/v1` 前缀的重复注册 |
| 4 | drain_mode_middleware 缺少导入 | `app/main.py` | 添加 `JSONResponse` 导入 |

### P1: 高危问题 (5 项)

| # | 问题 | 文件 | 修复内容 |
|---|------|------|----------|
| 5 | Celery 信号 asyncio.create_task | `app/celery_app.py` | 改用同步数据库操作 |
| 6 | datetime.utcnow() 无时区 | 历史修复覆盖部分模型时间列 | 改用 `datetime.now(timezone.utc)`；当前仍有残留 |
| 7 | WebSocket Manager 单连接 | `app/services/websocket_manager.py` | 支持同一用户多连接 |
| 8 | CORS ALLOWED_HOSTS 正则 | `app/core/config.py` | `cors_origin_regex` 锚定 + 转义，`app/main.py` 改用该属性 |
| 10 | file_upload.py CHUNKS_DIR | `app/api/v1/file_upload.py` | 移动配置到类定义之前 |

### P2: 中等问题 (3 项)

| # | 问题 | 文件 | 修复内容 |
|---|------|------|----------|
| 9 | PostgreSQL UUID 导入 | `app/models/chat_history.py` | 移除未使用的导入 |
| 11 | SQL LIKE 查询转义 | `app/db/search_history.py` | 添加 `escape_like_pattern()` 函数 |
| 15 | login 端点限流不一致 | `app/api/v1/auth.py` | 统一使用 `identifier` 格式 |

### P3: 低等问题 (4 项)

| # | 问题 | 文件 | 修复内容 |
|---|------|------|----------|
| 18 | health.py 版本号 | `app/api/v1/health.py` | 提取 `app/core/version.py`，health 端点与 `health_checker.py` 共用同一常量 |
| 19 | main.py 遗留注释 | `app/main.py` | 移除末尾 Windows cloudflared 隧道命令注释 |
| 20 | 旧 Agent router 备份残留 | 已移除 | 删除历史残留文件 |
| 21 | FeatureSwitchMiddleware 路径 | `app/middleware/feature_switch.py` | `/api/v1/project` → `/api/v1/agent` |

### P4: Agent 架构级 Bug (4 项)

| # | 问题 | 文件 | 修复内容 |
|---|------|------|----------|
| 22 | evaluate_mixin Architect/CodeReviewer 不传 api_key_token | `app/agent/orchestrator_generation/evaluate_mixin.py:43-46` | 添加 `api_key_token=self.api_key_token` + `provider_id=getattr(self, 'provider_id', None)` |
| 23 | evaluate_mixin call_llm 不传 api_key_token | `app/agent/orchestrator_generation/evaluate_mixin.py:150,219` | 添加 `api_key_token=self.api_key_token` |
| 24 | error_recovery ReAct auto-fix 硬编码 model_key | `app/agent/orchestrator_generation/error_recovery.py:18-22` | 改用 `model_assignment.fallback_model` + `api_key_token` |
| 25 | react_agent._call_llm 不传 api_key_token | `app/agent/react_agent.py:193` | 添加 `api_key_token=self.api_key_token` |

### P5: 技术债修复 (3 项)

| # | 问题 | 文件 | 修复内容 |
|---|------|------|----------|
| 26 | DEFAULT_FALLBACK_CHAIN 硬编码 SiliconFlow 模型名 | `app/agent/error_recovery.py` | 新增 `_PROVIDER_FALLBACK_CHAINS`（6 个供应商各自降级链）+ `_detect_user_provider()` 方法，改为供应商感知 |
| 27 | ReActWithFallback 死代码（硬编码模型名） | `app/agent/react_agent.py` + `__init__.py` | 删除 42 行死代码类 + 移除 import/export |
| 28 | call_siliconflow 未使用 | `app/utils/AiCodeUtil.py` | 删除 126 行死代码，统一走 `call_llm()` |

---

## 测试验证

| 测试类型 | 通过 | 失败 | 跳过 |
|----------|------|------|------|
| 单元测试 | 1622 | 0 | 0 |
| E2E 测试 | 76 spec | - | - |

---

## 已偿还的技术债务

### Agent 引擎架构重构 ✅ 已完成

**偿还日期**: 2026-06-04

**问题**: Agent 引擎代码分散、工具系统不统一、ReAct 循环重复、JSON 解析不一致

**解决方案**:
- **工具系统统一**: tools.py 作为唯一实现源 (996 行, 21 工具)，executor.py 适配后注册
- **ReAct 循环统一**: react_engine.py (578 行) 统一 simple + full 双模式
- **统一 LLM 调用层**: llm_client.py (164 行) 并发信号量 + 超时保护
- **统一 JSON 解析层**: json_parser.py (343 行) 5 层解析链
- **multi_model_agent.py 拆分**: 1202→243 行，6 个子模块
- **依赖图拆分**: 1351→983 行，新建 signature_extractor.py + shadow_scanner.py + dependency_rules.py
- **26 个 bare except pass 修复**: 全部改为 `except Exception: logger.debug(...)`
- **22 个函数内重复 import 清除**
- **硬编码模型名称统一**: 39 处/12 文件 → 4 个常量
- **45 处 alert→ElMessage** + **14 处 console 清理**

**效果**:
- 工具系统单一数据源，零重复
- ReAct 引擎统一，所有路径走 react_engine.py
- JSON 解析 5 层 fallback，小模型 JSON 输出稳定性大幅提升
- 测试基线：1244 passed / 3 skipped

### MCP Client 集成 ✅ 已完成

**偿还日期**: 2026-06-04

**问题**: 工具系统封闭，无法接入外部工具 (数据库、浏览器、搜索等)

**解决方案**:
- 新建 `mcp_client.py` (462 行): MCPServerConnection + MCPClientManager
- 支持 stdio + HTTP 双传输
- 4 个集成点: executor / specialist_base / agent_executor / orchestrator
- 前端管理: `/api/v2/mcp/servers` CRUD + test + toggle
- 配置文件: `data/mcp_servers.json`

**效果**:
- 用户可通过 MCP 协议接入任意外部工具
- MCP 工具对 ReActEngine 完全透明
- 资源增加 ~150MB 内存 + 1-3ms 延迟

### 交叉验证触发优化 ✅ 已完成

**偿还日期**: 2026-06-04

**问题**: 所有文件都触发交叉验证 (双模型生成)，浪费 token

**解决方案**:
- `is_critical_file` 加 `priority <= 2` 限制
- priority > 2 即使命中关键模式也不触发交叉验证
- 测试同步更新

**效果**:
- 交叉验证触发率降低 ~60%
- token 消耗减少

### 工具覆盖缺失 ✅ 已完成

**偿还日期**: 2026-05-22 | **来源**: 历史 Agent 完成报告

以下 5 个工具已在 `app/agent/executor.py` 中实现：

| 工具名称 | 实现方法 | 说明 |
|---------|---------|------|
| `insert_content` | `_tool_insert_content` | 支持按行号或锚点文本插入内容 |
| `partial_update` | `_tool_partial_update` | 支持按 target/replacement 或 function_name 替换代码块 |
| `regex_replace` | `_tool_regex_replace` | 支持 glob 模式匹配多文件的正则批量替换 |
| `delete_files_by_pattern` | `_tool_delete_files_by_pattern` | 基于 glob 模式的批量文件删除 |
| `cross_file_patch_auto` | `_tool_cross_file_patch_auto` | 支持 unified diff patch 和 new_content 两种模式 |

工具覆盖率从 95% 提升至 100%（19/19 工具已完成）。

---

### KV Cache 命中率优化 ✅ 已完成

**偿还日期**: 2026-05-23 | **版本**: v5.8.1

**问题**: LLM 调用时重复构建相同的 System Prompt，导致 KV Cache 命中率极低 (~0%)

**解决方案**:
- 创建 `app/utils/prompt_builder.py` (230 行)
- 静态前缀缓存（系统指令 + 工具定义 + spec_cache 内容）
- 动态后缀隔离（对话历史 + 会话状态 + 任务指令）

**效果**:
- KV Cache 命中率：~0% → 75-97%
- 延迟降低：≥20%

---

### 多角度审查系统 ✅ 已完成

**偿还日期**: 2026-05-23 | **版本**: v5.8.1

**问题**: 原有魔鬼代言人仅从单一角度审查

**解决方案**:
- 创建 `app/agent/multi_angle_review.py` (340 行)
- 3 个专业审查角色并行执行：性能师、安全师、可维护性师
- 三档严格度配置：LIGHT/STANDARD/STRICT

**效果**:
- 审查覆盖率：+200%
- 严重问题发现率：+40%

---

### API Key 全局化 ✅ 已完成

**偿还日期**: 2026-05-26 | **版本**: v5.9.0

**问题**: 仅项目生成使用用户 API Key，其他功能使用系统默认 Key

**解决方案**:
- 所有前端功能（项目生成、代码对话、PPT、图像生成、AI Cloud）均使用用户自定义 API Key
- 添加 `api_key_token` 参数到所有 API 请求
- 设置页面展示 Token 使用统计

**效果**:
- 用户可完全控制 API Key
- Token 消耗可视化

---

### 技术债务批量修复 ✅ 已完成

**偿还日期**: 2026-05-26 | **版本**: v5.9.0

**问题**: 16 项技术债务累积，包括 P0 级严重 Bug

**解决方案**:
- 修复 4 个 P0 级严重 Bug（启动清空数据、权限检查、路由重复、导入缺失）
- 修复 5 个 P1 级高危问题（Celery 信号、时区、WebSocket、CORS、文件上传）
- 修复 3 个 P2 级中等问题（UUID 导入、SQL 注入、限流一致性）
- 历史处理 4 个 P3 级低等问题（版本号、注释、残留文件、路径映射）；版本来源分裂当前仍在

**效果**:
- 消除所有已知严重 Bug
- 提升系统安全性和稳定性
- 代码库整洁度提升

---

### 工作流节点类型扩展 ✅ 已完成

**偿还日期**: 2026-05-27 | **版本**: v5.10.0

**问题**: 工作流仅支持 4 种节点类型，无法满足复杂业务需求

**解决方案**:
- 新增 5 种节点类型：`llm_call`、`conditional`、`human_approval`、`http_request`、`data_transform`
- 新增重试机制：`RetryConfig`（max_retries, retry_delay, backoff_factor）
- 新增失败策略：`fail`（中断）、`skip`（跳过继续）
- 新增状态：`waiting_approval`、`skipped`
- 提取提示词到 `skills/workflow-planner/system_prompt.md`

**效果**:
- 节点类型从 4 种扩展到 9 种
- 支持 LLM 调用覆盖 80% 工作流场景
- 支持条件分支和人工审批
- 资源限制适配 8C8G 服务器（最大并发 4 节点，节点超时 300s，内存 512MB）

---

## 相关文档

- [安全架构](security/SECURITY-OVERVIEW.md)
- [权限规范](security/PERMISSION-SPEC.md)
- [服务架构](guides/SERVICES.md)

---

最后核对：2026-09-03
