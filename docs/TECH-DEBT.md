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
| 6 | 无时区 `datetime.utcnow()` | 已解决 | 非 Agent 子系统 62 处全部迁移：新增 `app/core/time.py:utcnow_naive()`，naive 列用该函数、`DateTime(timezone=True)` 列用 `datetime.now(timezone.utc)`；Agent 子系统按归属裁定不在本轮范围 |
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
| P2 | lifespan 与 startup hook 并存 | `app/main.py` | 已解决；全 `app` 无 `on_event`/`add_event_handler`，启动与关闭统一由 `lifespan` 承担 |
| P2 | 多 API worker 下进程内 scheduler 可能重复执行 | `app/main.py`、`app/db/scheduler.py` | 已解决；生产 api 服务 `ENABLE_SCHEDULER=false`，调度改由独立服务 `python -m app.db.scheduler_runner` 承担；本地 compose 为 `--workers 1` 不构成重复；直接 `docker run` 时 `ENABLE_SCHEDULER` 默认 `False`。补 1 项编排守卫 |
| P2 | `/api/v1/health` 与部署侧 `/health` 契约分裂 | `app/api/v1/health.py`、部署配置 | 已解决；`Dockerfile` `HEALTHCHECK` 与两个 compose 的 `healthcheck` 均指向 `/api/v1/health`，与应用挂载路径一致。补 1 项编排守卫 |
| P2 | health 响应版本来源分裂 | `app/api/v1/health.py`、`app/services/health_checker.py`、`CHANGELOG.md` | 已解决；两处端点统一读 `app.core.version.APP_VERSION` |
| P2 | StateGraph 生产入口仍以单节点 legacy wrapper 为主 | `app/agent/state/`、`app/agent/workflow_registry.py` | 仍在 |
| P2 | 统一检索尚未接入生产 Agent 主链 | `app/agent/retrieval/` | 仍在 |
| P2 | 跨工作台续跑与多 worker 恢复缺独立验收 | `app/api/v1/agent_host.py`、`app/agent/state/` | 仍在 |
| P3 | 无时区时间调用在模型、状态、PPT 和 Skill 模块仍有残留 | `app/models/`、`app/services/` | 已解决（非 Agent 范围）；非 Agent 子系统 62 处全部迁移到 `utcnow_naive()` / `datetime.now(timezone.utc)`，剩余调用均在 Agent 子系统（`agent_memory_service`、`skill_registry`、`unified_state_service`、`state_migration_service` 等），按归属裁定不在本轮范围 |
| P3 | VS Code 发布元数据与真实状态栏适配仍需收尾 | `vscode-extension/package.json`、`vscode-extension/src/status-view.ts` | 部分解决；构建、Node 测试和 Host E2E 已通过 |
| P3 | Makefile `clean` 指向已归档脚本 | `Makefile`、`scripts/_archive/cleanup.sh` | 已解决；`clean` 目标改指 `./scripts/_archive/cleanup.sh` |
| P3 | ModelAdapter 注释引用已删除函数 | `app/adapter/model_adapter.py` | 已解决；注释与警告改为说明真实调用位置，不再引用已删除的 `call_siliconflow` |
| P3 | 已实现的安全审计能力未接线：`log_security_event` 与 `log_login_success`/`log_login_failed`/`log_permission_change`/`log_token_refresh`/`log_sensitive_operation` 全库零调用，登录与权限变更链不产生审计记录 | `app/utils/security_audit.py`、`app/api/v1/auth.py`、`app/api/v2/user_manage.py` | 已解决；登录成功/失败（含用户不存在）、Token 刷新、权限变更（记录新旧级别）、删除用户与重置密码均已接线，`log_security_event`/`log_login_failed` 的 `user_id` 放宽为可选以承载未识别用户，PR #347 |

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
| P3 | 私钥为无口令明文 PEM，仅靠文件权限（`0o600`）保护 | `app/utils/crypto.py`、`app/utils/encryption.py` | 已解决；新增可选 `RSA_KEY_PASSPHRASE`，设置后私钥以 `BestAvailableEncryption` 加密落盘、未设置保持原行为，既有明文密钥在配置口令后自动升级，私钥写入改临时文件 + `os.replace` 原子替换，两个 Compose 透传该变量，补 7 项口令化单测与 1 项编排守卫（见「2026-09-26 生产就绪复核新增项」）。更进一步的只读卷挂载 / KMS 仍作为生产部署建议保留 |
| P3 | `tests/e2e/` 下有大量一次性诊断脚本与依赖外部模型的在线探针，无法全部纳入 CI 门禁 | `tests/e2e/` | 部分解决；3 个零 Agent 引用的草稿探针与 1 个失效 spec 已移入 `tests/archive/playwright/`（该目录不在 `playwright.config.js` 的 `testDir` 内），当前 `tests/e2e/` 下 94 个 spec。`e2e.yml` 门禁由 5 个扩到 13 个稳定非 Agent spec：新增 `theme-switcher`/`10-admin`/`tools`/`capability-center`（串行与默认并行各跑一遍，`28 passed`），修复后复跑全绿的 `tools-panel`（11 项）与 `admin-panel-scenarios`（2 项），以及重写后复跑全绿的 `system-monitor`（7 项）与 `upload-file`（6 项）。**剩余非 Agent spec 的失败已逐条定性**：`03-chat.spec.js` 的 6 项失败为纯负载型 flaky（本机负载 7.5 时超时；负载 1.8 时 11 项全过），非产品缺陷；`tools-panel`（2 项过期工具清单选择器）、`admin-panel-scenarios`（错误断言 `模型管理` 不存在，实为 superadmin 有意保留）已修复；`system-monitor`、`upload-file` 两个「断言不存在功能」的过期 spec 已按真实功能重写并纳入门禁；`sprint-1-rbac`（17 项，断言产品未实现的高级 RBAC）已归档（详见下方说明）；2026-09-26 复核：对 5 个额外非 Agent 候选（`smoke`、`smoke-test-simple`、`auth`、`api-endpoint-validation`、`chart-editor`）与门禁 13 spec 合并串行跑得 `117 passed, 3 skipped, 0 failed`，但候选断言偏弱（`smoke` 多数 `catch` 后 `test.skip`）、`api-endpoint-validation` 内嵌大量 Agent 硬编码路由、`chart-editor` 曾在大批次 flake，故不纳入门禁 |
| P3 | `dynamic_package_manager.py` 全库零生产引用，但含「AI 评估安全性后安装包」能力，语义与 Agent 相邻 | `app/utils/dynamic_package_manager.py`、`tests/unit/test_service_dependency*.py` | 已裁定保留；判定为 Agent 相邻的预留能力，按本轮「不触碰 Agent 子系统」的范围约定保留，不计入死代码，其 3 个相关测试一并保留 |
| P2 | Alembic 与 `migrations/runner.py` 双轨并存且互相冲突 | `migrations/env.py`、`migrations/runner.py`、`migrations/versions/`、`configs/alembic.ini` | 已解决；首次接入契约收敛到 `Base.metadata`：库内无 `alembic_version` 时建全量表并登记 head、不重放历史修订，已有版本走标准迁移，空库与 runner.py 管理过的库均可 `upgrade head`。`Makefile`/`scripts/migrate.sh` 补齐 `-c configs/alembic.ini` 并修正无效的 `history -n`。补 3 项引导回归用例。残留：`versions/` 下的历史修订不再被执行（仅供已有版本库的增量），认知负担仍在 |
| P3 | 2 个 uvicorn worker + celery + scheduler 共用单个 SQLite 文件 | `docker-compose.prod.yml`、`app/db/database.py` | 已缓解；`app/db/database.py` 对 SQLite 连接统一开启 `journal_mode=WAL`、`busy_timeout=30000` 与 `connect_args timeout=30`，抑制 `database is locked`。结构性缺口仍在（单写者模型），高并发生产仍建议改用 Postgres |
| P3 | compose 的 `command` 覆盖 Dockerfile 的 `CMD`，绕过其中 `su appuser` 的非 root 启动 | `docker-compose.yml`、`docker-compose.prod.yml`、`Dockerfile` | 已解决；`docker-compose.prod.yml` 的 api/celery/scheduler 显式 `user: appuser`，Dockerfile 已 `chown -R appuser:appuser /app` 并预建全部挂载点、bind mount 源文件 644 可读。本地 `docker-compose.yml` 因 bind mount 属主保持 root 并加注释。补 2 项守卫用例。注意：既有 root 属主的 named volume 需重建或手工 `chown` |
| P3 | 生产镜像安装全量 `configs/requirements.txt`，其中 Django、Scrapy 全依赖链（Twisted/parsel/w3lib/itemadapter/itemloaders/Protego/PyDispatcher/queuelib/cssselect/Automat/constantly/hyperlink/Incremental/service-identity/zope.interface/pyasn1-modules）、Flask 全链（Werkzeug/Jinja2/itsdangerous/blinker）、pandas、opencv-python 在代码中零引用，且无任何硬反向依赖 | `configs/requirements.txt`、`Dockerfile` | 已解决；裁剪 33 个包：`Django`、`Scrapy` 及其依赖链、`Flask`/`Werkzeug`/`Jinja2`/`itsdangerous`/`blinker`、`pandas`、`opencv-python`，以及 `asgiref`/`sqlparse`/`defusedxml`/`tldextract`/`filelock`/`requests-file`/`jmespath`/`pyOpenSSL`/`w3lib` 等传递依赖，并顺带删除一行重复的 `slowapi`。保留 `passlib`（Agent 子系统 `code_validator.py`/`code_reviewer.py` 引用）、`email-validator`/`dnspython`（pydantic `EmailStr`）、`aiosqlite`（SQLAlchemy 方言）、`python-multipart`（FastAPI 表单/上传）——这些按需动态加载，静态 import 扫描不到。三重验证：①静态零 `import` 且零硬反向依赖；②把 33 个包从 site-packages 物理移走后 `from app.main import app` 成功，全量测试 `5044 passed, 2 skipped`（唯一失败为高负载下 `test_aicloud_execution_regressions` 的 10s 执行超时 flake，单体复跑 0.39s 通过）；③`pip install --dry-run --ignore-installed -r configs/requirements.txt` 的解析结果不含任何被删包。生产镜像预计减重约 215 MB |
| P3 | `ecdsa 0.19.2` 存在 `PYSEC-2026-1325` 且无上游修复版本，被 `python-jose` 硬依赖 | `configs/requirements.txt`、`app/utils/security.py`、`app/api/v1/auth.py` | 已评估，不可达；`python-jose` 确为生产依赖（`app/utils/security.py`、`app/middleware/rate_limiter.py`、`app/api/v1/auth.py` 三处 `from jose import jwt`），但 JWT 签名算法固定为 `HS256`（`settings.ALGORITHM`），且全部 `jwt.decode` 调用传入 `algorithms=["HS256"]` 白名单，攻击者无法通过算法混淆触发 ecdsa 的 ECDSA 验证路径。按「不可达风险」接受，不为此移除 python-jose |

## 2026-09-25 生产就绪复核新增项

### 本轮已修复

| 优先级 | 问题 | 实际位置 | 状态 |
|---|---|---|---|
| P2 | Celery broker 可达但无 worker 响应时，`/health/detailed` 的 celery 项仍报 `healthy`，掩盖调度中断 | `app/services/health_checker.py` | 已解决；`inspect.stats()` 为空时报 `degraded`「未发现可用的 Celery worker」，补 1 项回归，PR #274 |
| P2 | `GET /api/v1/aicloud/history` 空结果返回 `None`，与单个 `SessionResponse` 的 `response_model` 冲突，任何无历史的用户都触发 500 | `app/api/v1/aicloud.py` | 已解决；`response_model` 改 `list[SessionResponse]` 并返回会话列表（前端本就按数组消费 `sessions.find`），PR #280 |
| P2 | `GET /api/v1/pptx/templates/{id}/preview/{page}` 未捕获 `select_template` 的 `KeyError`，未知模板冒泡成 500；别名（`business` → `business_report`）未解析还会命中错误目录 | `app/api/v1/aiGeneratorPptx.py` | 已解决；先解析别名，未知模板返回 404，PR #280 |
| P2 | `GET /api/v2/Controller/admin/docker/containers` 把可选依赖 `import docker` 与业务逻辑同放一个 `try`，SDK 缺失被泛化 `except` 转成 500 | `app/api/v2/guardian_router.py` | 已解决；`ImportError` 返回 503「Docker SDK 未安装」，其余异常仍为 500，PR #281 |
| P2 | `GET /api/v2/Controller/admin/backup` 有副作用：写入备份文件并按 mtime 淘汰第 5 个以外的历史备份，预取/重试/监控探测都会触发轮转 | `app/api/v2/guardian_router.py`、`src/utils/api/admin.js` | 已解决；创建备份改为 `POST`（前端 `client.post` 自动带 `X-CSRF-Token`），补路由方法守卫用例，PR #283 |

上述前四项由对全部非 Agent GET 端点（87 个）与选定变更端点（61 个）的运行时冒烟定位：GET 冒烟初测出 2 处 500，修复后 61 个变更端点探测结果为 `404×33 / 422×22 / 200×4 / 400×2`，0 个 5xx。备份端点副作用则通过比对 `data/backups/` 冒烟前后的新增文件发现。

### 非 Agent E2E spec 失败定性（2026-09-25）

对本机全量跑中出现失败的非 Agent spec 逐条复跑定性，结论分三类：

| spec | 失败项 | 定性 | 证据 |
|---|---|---|---|
| `03-chat.spec.js` | 6 | 负载型 flaky，非产品缺陷 | 系统负载 7.5 时输入框 `click()` 超时；负载 1.8 时 11 项全过（1.9m） |
| `tools-panel.spec.js` | 2 | 过期断言，已修 | 断言的工具清单含 5 个已下线工具（`系统检测`/`任务队列`/`AI 云助手`/`系统监控`，`AI 虚拟姬` 实为 `虚拟姬`）；`新建会话` 断言的 `.chat-messages` 首页从无此类。改按真实菜单（12 项）与待机区域断言，现 11 项全过 |
| `admin-panel-scenarios.spec.js` | 1 | 过期断言，已修 | 断言 superadmin 不应看到 `模型管理`，而该入口自 2026-07 起即由 `isSuperUser` 有意保留；改为断言其存在，现 2 项全过 |
| `system-monitor.spec.js` | 7 | 断言不存在功能 | 入口 `工具集 > 系统监控` 已从产品移除（系统监控现在 AdminPanel 内）；7 项全部卡在该点击 |
| `upload-file.spec.js` | 5 | 断言不存在功能 | 断言 `.upload-preview`/`.upload-progress`/`.upload-error`/`.upload-cancel-btn` 与 `aria-label="上传文件"`（真实为 `上传文件或图片`），首页均不存在 |
| `sprint-1-rbac.spec.js` | 17 | 断言不存在功能 | 断言角色管理/部门管理/多租户/审计日志/安全设置/2FA/密码策略，产品仅实现 `permission_level`（normal/admin/superadmin），全库无这些页面；其「通过」的 14 项也多为 `readyState` 或 `if count>0` 的空断言 |

处置（2026-09-26）：`system-monitor`、`upload-file` 断言的功能仍在（只是入口或选择器变了），已按真实 UI 重写并纳入门禁；`sprint-1-rbac` 断言的高级 RBAC 产品未实现，已移入 `tests/archive/playwright/`。

## 2026-09-26 生产就绪复核新增项

### 本轮已修复

| 优先级 | 问题 | 实际位置 | 状态 |
|---|---|---|---|
| P2 | 首页输入区上传附件后永久停留在「上传中」：`processFile` 把普通对象 push 进 `ref([])` 后直接改原始对象字段，未触发 Vue 响应式更新，父组件与 `FilePreview` 子组件都收不到 | `src/components/bottominput.vue` | 已解决；待上传的对象改用 `reactive()` 包装，上传成功或失败都会离开中间态。补 `upload-file.spec.js` 回归（修复前失败、修复后通过），已纳入门禁 |
| P3 | 全仓库非 Agent 子系统仍在用 `datetime.utcnow()`（62 处 / 23 文件），Python 3.12 起弃用且返回值无时区 | `app/models`、`app/services`、`app/utils`、`app/db`、`app/core`、`app/api/v1` | 已解决；新增 `app/core/time.py:utcnow_naive()`（语义等同 `utcnow()`），按列类型配对迁移：naive 列用 `utcnow_naive()`，`DateTime(timezone=True)` 列用 `datetime.now(timezone.utc)`。补 `tests/unit/test_time_utils.py`（3 项）。Agent 子系统按归属裁定不动 |
| P3 | AJP12（`85208591`）从 `aiGeneratorPptx.py` 移除图片搜索消费时漏删本体 `app/utils/pptx/image_search.py`（183 行）；`app/utils/structured_logging.py`（170 行）被 `app/utils/logging.py` 取代后残留。两模块均 0% 覆盖、零外部引用 | `app/utils/pptx/image_search.py`、`app/utils/structured_logging.py` | 已解决；删除两个死模块，删除后全量 unit/integration `4987 passed, 2 skipped` 不变 |
| P3 | RSA 私钥以无口令明文 PEM 落盘，仅靠文件权限（`0o600`/`0o700`）保护，私钥文件或备份泄露即等同私钥泄露 | `app/utils/crypto.py`、`app/utils/encryption.py` | 已解决；新增可选 `RSA_KEY_PASSPHRASE`：设置后私钥以 `BestAvailableEncryption` 加密落盘，未设置则保持原有明文行为；既有明文密钥在配置口令后自动升级为加密存储；私钥写入改为临时文件 + `os.replace` 原子替换；两个 Compose 透传该变量并在示例 env 登记；补 7 项口令化单元测试与 1 项编排守卫 |

### 非 Agent E2E 门禁扩展（2026-09-26）

门禁由 13 个 spec / 98 项扩展到 19 个 spec / 111 项，新增 6 个不依赖外部模型服务的 spec（自 mock 后端或只依赖本地后端与种子账号）。纳入前逐个排查失败原因，全部为随 UI 演进出现的**测试侧过期**，非产品缺陷：

| spec | 覆盖 | 修复内容 |
|---|---|---|
| `chart-editor` | 导入/编辑/撤销重做/导出/深色主题/草稿恢复 + 移动端无横向溢出（2 项） | 无需改；自 mock `csrf-token`/`refresh`，纯前端离线 |
| `chart-editor-scenarios` | 经首页工具集打开编辑器、返回后再进草稿保留、刷新后草稿恢复（2 项） | 无需改；真实登录 + 纯前端编辑 |
| `ppt-generation-mock` | PPT 三步生成（大纲→质量模式→生成）、质量报告、下载 PPTX（1 项） | 补全 `_token`/`_token_expiry` 存储与 `csrf-token`/`refresh` mock（`tokenManager.performRefresh` 要求合法三段 JWT）；`codingmatrix_apikeys` 补 `expires_at`（`isTokenExpired` 缺字段即判过期→`hasSiliconflowKey=false`→跳设置页）；断言改全角「生成成功！」与「需人工复核：第 1 页」（前端按页序渲染，非 `slide-1`） |
| `girlai-companion` | 伙伴状态 revision 恢复与降级、旧响应不覆盖当前状态、异步更新保文字链路（3 项） | 删除误设的 `test.use({ baseURL: ...8000 })`（后端 dist 无该入口，应为前端 dev server）；情绪断言改中文（`neutral→平静`、`focused→专注`）；工具集入口限定 `#toolkit-menu` 内定位，规避展开动画导致的 `element is not stable` |
| `ppt-preview-repairs` | 结构预览与质量报告同屏、自动模板选择（桌面/移动各 2 项） | 第二个用例补全 token 存储与 `expires_at`，否则 `/ppt-generate` 的 `requiresAuth` 守卫与 `hasSiliconflowKey` 判定使其跳设置页 |
| `homepage-responsive` | 首页在桌面/平板/移动端的主导航抽屉开合、焦点回归、输入区可见、移动端输入字号不小于 16px、无横向溢出（1 项） | 从 `workbench-responsive.spec.js` 拆出：该文件同时含 `/agent` 工作台用例（Agent 范围），拆出纯前端首页部分独立成 spec 以便纳入门禁，原文件保留 Agent 用例不进 CI |

共同根因：token 存储字段不完整、情绪标签本地化、标点全半角、页序文案。CI 门禁维持 `CI=1` 单 worker，本机以 `--workers=1` 串行复跑新增 6 个 spec 合计 `13 passed` 全绿。

已评估但排除：`girlai-companion-scenarios.spec.js` 的 `syncSiliconflowKeys` 要求后端 `/api/v1/agent/apikeys` 返回至少一条已配置 Key（CI 的 `seed_users` 不配置 Key），且第二个用例依赖真实模型回答，无法在离线 CI 稳定运行，故不纳入。

### 依赖安全审计与修复（2026-09-26）

对生产镜像依赖做完整漏洞审计。首轮策略为「升级到修复版本、不裁剪包」；随后按用户决定追加「裁剪零引用包」：

| 范围 | 审计前 | 审计后 | 处置 |
|---|---|---|---|
| 后端（`configs/requirements.txt`，`pip-audit --local`） | 77 CVE / 20 包 | 1 CVE / 1 包 | 升级 19 个包：`starlette` 1.0.0→1.3.1、`cryptography` 46.0.7→50.0.0、`pillow` 12.2.0→12.3.0、`python-multipart` 0.0.28→0.0.31、`aiohttp` 3.13.5→3.14.3、`lxml` 6.0.3→6.1.0、`urllib3` 2.6.3→2.7.0、`pyOpenSSL` 26.0.0→26.4.0、`Django` 5.2.13→5.2.17、`Scrapy` 2.15.0→2.17.0、`Twisted` 25.5.0→26.4.0，以及 `anyio`/`click`/`idna`/`json_repair`/`Protego`/`pyasn1`/`pydantic-settings`/`soupsieve`/`sqlparse` 补丁级升级；`fastapi` 声明 `starlette>=0.46.0`、`requests` 允许 `urllib3<3`、`matplotlib` 允许 `pillow>=8`，均在修复版本约束内；`pip check` 无冲突 |
| 前端生产依赖 | `xlsx` 0.18.5 两个 high（Prototype Pollution `GHSA-4r6h-8v6p-xvw6` + ReDoS `GHSA-5pgg-2g8v-p4x9`，npm 无修复版本） | 0 | `xlsx` 改用 SheetJS 官方 CDN tarball `0.20.3`（`package.json` 依赖源改为 `https://cdn.sheetjs.com/xlsx-0.20.3/xlsx-0.20.3.tgz`）；仅 `src/views/ChartEditorPage.vue` 一处使用，`XLSX.read`/`utils.sheet_to_json` API 不变。升级后重启 Vite（触发 `Re-optimizing dependencies because lockfile has changed`）并复跑 `chart-editor` + `chart-editor-scenarios` E2E `4 passed`，验证 Excel 导入链路正常 |
| 前端 dev/build/test 依赖 | 8（`js-cookie`/`undici`/`brace-expansion` high，`esbuild`/`postcss-selector-parser`/`@vitest/mocker` moderate） | 9 | 均位于开发期链路（`@vue/test-utils`→`js-beautify`→`js-cookie`、`jsdom`→`undici`、`glob`/`editorconfig`→`brace-expansion`、`vite`→`esbuild`），不进生产 bundle；`npm audit fix` 受 npm 10.9.4 `Cannot read properties of null (reading 'edgesOut')` bug 阻断，未处理 |

裁剪补充（第二轮）：后端 `configs/requirements.txt` 删除 33 个零引用且零硬反向依赖的包（`Django`、`Scrapy` 全依赖链、`Flask` 全链、`pandas`、`opencv-python` 等，详见上表第 87 行的 P3 项），`pip-audit` 剩余 CVE 数不变（仍为 `ecdsa` 不可达 1 项，因被删包在首轮升级后已无 CVE）；`requirements-test.txt` 的 `cryptography` 由 `46.0.7` 对齐到 `50.0.0`，避免 CI 先装 `requirements.txt` 再被测试依赖降级回有漏洞版本、导致测试环境与生产不一致。

### 非 Agent 过期 spec 处置（2026-09-26）

对上一轮定性的三个「断言不存在功能」spec 按「可重写则重写、失效则归档」处置：

| spec | 处置 | 说明 |
|---|---|---|
| `system-monitor.spec.js` | 重写 | 系统监控已迁入 AdminPanel `/admin` 默认菜单；改测真实监控看板（CPU/内存/磁盘资源卡片、网络状态、手动刷新、4 个 ECharts canvas），7 项全绿，纳入门禁 |
| `upload-file.spec.js` | 重写 | 改测首页输入区真实上传 UI（隐藏 file input、附件预览、多文件、离开上传中间态、移除附件、拖拽区），6 项全绿，纳入门禁 |
| `sprint-1-rbac.spec.js` | 归档 | 断言的高级 RBAC 能力（角色/部门/多租户/审计/2FA 等）产品未实现，移入 `tests/archive/playwright/` |

## 2026-09-27 生产就绪复核新增项

### 本轮已修复

| 优先级 | 问题 | 实际位置 | 状态 |
|---|---|---|---|
| P3 | 安全审计模块全库零调用：登录成功/失败、Token 刷新、权限变更、敏感操作均不产生审计记录 | `app/utils/security_audit.py`、`app/api/v1/auth.py`、`app/api/v2/user_manage.py` | 已解决；见上表 P3 项，PR #347 |

接线明细：登录失败区分 `user_not_found`（`user_id` 为 `None`）与 `wrong_password`（带用户 ID），均记录客户端 IP；登录成功与 Token 刷新记录用户 ID；`update_user` 仅在权限级别实际变化时记录 `permission_change`（含新旧级别与操作者）；`delete_user`、`reset_password` 记录 `sensitive_operation`。新增 `tests/unit/test_security_audit.py`（5 项，覆盖各便捷函数落盘载荷）与 `tests/unit/test_v2_user_manage_privilege.py` 的 4 项成功路径审计断言。回退接线后 4 项新用例如期失败；受影响测试集合 `36 passed`。

### 非 Agent 深扫剩余项最终判定（2026-09-27）

对 `docs/evolution/modules/` 下非 Agent 模块中标注为「仍在 / 待产品口径」的项逐条复核，结论为均已修复、判定不成立、所属模块已删除，或属设计取舍。后者的最终判定如下（保留现状，均非代码缺陷）：

| 项 | 位置 | 判定 |
|---|---|---|
| V2M1 `model_admin` 声明废弃仍挂载 | `app/api/v2/model_admin.py`、`app/main.py:346` | 保留；旧接口独有 `context-lengths` / `default` / `error-type-model` 能力，仍被活跃前端 `AdminModelManager.vue`（`Settings.vue` 的 admin tab）消费，新 `model_config_api` 未覆盖这些能力，退役会破坏功能。双 tab 是否合并属产品口径 |
| MM1 `/models` 四端点无认证 | `app/api/v1/model_manager.py` | 保留公开定位；返回仅模型元数据（`model_key` / 供应商 / 上下文长度），不含凭据，属公开模型目录，加认证会破坏匿名浏览 |
| MM2 v2.0 兼容分支 MEDIUM 缺失回退 LARGE | `app/api/v1/model_manager.py:177` | 保留；为 v2.0 `assignments` 格式的刻意兼容兜底，收紧会变更兼容语义 |
| GH10 三套 git 封装并存 | `app/api/v1/github.py`、`app/utils/git_operations.py`、`app/agent/orchestrator_utils.py` | 保留；收敛需统一提交消息 / 分支名 / 空提交语义，属架构级改动，风险高于收益 |
| SO2 review `raw_content` 原样入库与写回 | `app/utils/aicloud/review_queue.py`、`app/api/v1/aicloud.py` | 保留；审批者需原文才能审阅，批准后需按原文回写沙箱文件，仅展示层脱敏而存储层脱敏会破坏回写，改动涉及产品口径 |

SB1（`app/agent/specialist_base.py`）属 Agent 子系统，按范围约定不在本轮范围。

本轮同时补齐七处可修活跃缺陷与卫生项，均在 aicloud 执行链。

**安全类**（`app/utils/aicloud/code_executor.py`，前两处从 `POST /api/v1/aicloud/execute`（admin）可达）：

- **CE2 Go 沙箱逃逸**：Go 路径原仅禁 `net`/`os/exec`/`syscall`/`unsafe` 四个子串，`import "os"` 合法，可编译执行 `os.ReadFile`/`os.WriteFile` 任意读写宿主文件。现以 `GO_BANNED_IMPORTS` + `_find_banned_go_import()` 解析 import 声明（含反引号原始字符串与 cgo 伪包 `C`）并扩充禁用集，在调用 `go` 工具链前拦截。
- **CE5 Python 属性链逃逸**：AST 检查原先只在 Call 节点拦 `ast.Name` 直调与 `__builtins__` 前缀，`().__class__.__bases__[0].__subclasses__()` 等属性链可找回任意对象（实测回退后旧实现 `success=True`）。现新增 `DANGEROUS_PYTHON_ATTRS` 属性名拦截并把 `__builtins__` 检查提升到 `ast.Name` 层，逃逸链在解析阶段即被拒绝。
- **CI1 沙箱环境未生效**：`ContextIsolator.setup_sandbox` 声明的 `HOME`/`WORK_DIR` 从未落到任何子进程。现 `CodeExecutor._sandbox_dirs()` 按 workspace 根推导并注入三语言子进程环境（Python 原硬编码 `HOME=/tmp`，JS/Go 原未覆盖），与声明值 `/sandbox/{user_id}`、`/sandbox/{user_id}/workspace` 一致。

**代码卫生类**：

- **AE2 缺省 workspace 落裸 `/tmp`**：`CodeExecutor` 缺省目录由 `tempfile.gettempdir()` 改为 `tempfile.gettempdir()/aicloud_sandbox` 并自动创建，避免与宿主临时文件混放。
- **AE3 循环记录截断无标记**：`auto_executor` 内 `[:500]`/`[:200]` 等截断改为 `_clip()`，带丢失长度标记。
- **AE5 `conversation_history` 死数据**：轮次记录此前仅收集、无任何消费；现达到最大循环时写入审计日志。
- **KP4 旧版 `.doc` 误走 `python-docx`**（`app/utils/aicloud/knowledge_processor.py`）：`parse_document` 的 `.doc` 分支改为明确抛出 `ValueError`（提示另存为 `.docx`），不再让 `python-docx` 抛晦涩的 `PackageNotFoundError`。

新增用例共 22 项（CE2/CE5/CI1/AE2/AE3/AE5 计 21 项在 `tests/unit/test_aicloud_execution_regressions.py`，KP4 计 1 项在 `tests/unit/test_knowledge_upload_bounds.py`），回退后相关用例全失败；执行链 11 文件 + `test_tools.py` 248 passed，KP4 相关 5 文件 59 passed。黑名单沙箱固有的绕过面（Go 编译期 `//go:embed` 等）与 OS 级隔离（容器/namespace/seccomp）仍为架构级待办，见 `docs/evolution/modules/aicloud_execution.md` §六。

另更正一条过时结论：`docs/evolution/modules/aicloud_execution.md` 的 SB1（`SandboxFileOperator` 符号链接逃逸）判断不成立——`FileOperator._validate_path` 已用 `.resolve()` 解析符号链接并校验落点是否在 `base_path` 内，实际安全校验走基类，`get_absolute_path` 的 `normpath` 仅用于展示/拼接。

### aicloud 模块 P3 收敛与 PAPI2 补全（2026-09-28）

| 优先级 | 问题 | 实际位置 | 状态 |
|---|---|---|---|
| P3 | `DynamicProviderManager.list()` 返回对象与内部共享同一 `models` 列表引用，外部 append 可污染管理器内部状态 | `app/utils/aicloud/dynamic_provider.py` | 已解决；改为 `models=list(p.models)` 浅拷贝，新增 `test_dynamic_provider.py` 1 项，回退后失败 |
| P3 | 磁盘过期缓存清理触发条件 `len(_embedding_memory_cache) % 100 == 0` 不可达：内存缓存封顶 512 后长度恒定，`512 % 100 != 0` 恒成立 | `app/utils/AiCodeUtil.py` | 已解决；改为模块级 `_disk_cache_cleanup_counter`（每次新写入递增，满 100 清理），新增 `test_aicode_util.py` 1 项，回退后失败 |
| P2 | `test_connection` 端点未做 SSRF 出站校验（PAPI2 原判定点名 sync 与 test 两点，此前只补了 `fetch_models_openai`） | `app/api/v1/providers.py` | 已解决；构造 URL 后调用 `check_outbound_url`，命中非公网地址直接返回失败且不发请求，新增 `tests/unit/test_providers_endpoint_ssrf.py` 1 项，回退后 httpx 被调用、用例失败 |

`ADT4`（`audit_logger.py` 的 `cleanup_old_audit_logs` 仅清 `status=="success"`）判定保留：行内注释显式声明「只清理成功的操作日志」属失败日志长期保留的审计策略，且该函数全库零调用方，改动无运行影响；`AIU8`（磁盘缓存无大小上限）保留，容量硬上限属部署策略。相关结论已同步至 `docs/evolution/modules/aicloud_core.md` §七 与 `docs/evolution/modules/aicode_util.md` §六。

`aicloud_core.md` 剩余 P3 项（PR2/DP1/DP4/DP5/PR3/PR4/PR5/PRV1/PAPI4/PERM1/ADT3/HC4）本轮逐条核实后判定保留，理由见该文档 §八：DP4 更正为设计取舍（Anthropic 无公开模型列表 API，`fetch_models_anthropic` 不发网络请求），PR2 更正配置路径为 `.yaml` 且生产缺失即拒启动，其余为架构级（DP1/PR5/HC4）或设计取舍/零消费公开导出。

### PROJECTS_BASE_DIR 绝对化与双轨消除（2026-09-28）

| 优先级 | 问题 | 实际位置 | 状态 |
|---|---|---|---|
| P3 | `PROJECTS_BASE_DIR = "./projects"` 相对路径依赖 CWD：api/scheduler/celery 多进程入口工作目录可能各不相同，CWD 漂移时生成物目录不可预测（AIC1/GRD3 关联） | `app/core/paths.py`、`app/api/v1/AiProjectCode.py`、`app/api/v1/ai_agent/orchestrate_endpoints.py` | 已解决；`core.paths` 改为基于 `__file__` 的绝对路径，`AiProjectCode.py` 与 `project_config.py` 的双轨定义消除（统一 import core.paths），`resolve_stream_output_dir` 前缀归一化兼容历史 `./projects/` 前缀与绝对 BASE 前缀。回归 `tests/unit/test_output_dir_resolution.py::TestProjectsBaseDirAbsolutePath`（5 项），回退后「绝对性」「双轨消除」两项精确失败；关联面 `test_evaluation_runner`/`test_import_project_files`/`test_flutter_project_delivery`/`test_project_lifecycle_api`/`test_ai_project_code_*` 全绿（`test_evaluation_runner` 补显式 patch `app.agent.orchestrator.PROJECTS_BASE_DIR`，原靠双模块同值巧合生效） |

### vulture 反向死代码清理：死 import 与死函数（2026-09-28）

| 优先级 | 问题 | 实际位置 | 状态 |
|---|---|---|---|
| P3 | 死 import 15 处（vulture 90% 置信，逐符号全库引用核实，零 re-export 风险） | `AiProjectCode.py`（BackgroundTask/GenerateResponse/ProjectFileManager/TaskStatusEnum）、`workflow.py`（WorkflowStatusResponse/WorkflowStreamEvent）、`file_upload.py`（FileListResponse）、`mcp_admin.py`（MCPClientManager）、`model_admin.py`（get_current_default_model_id/_orig 函数内死 import 整行）、`nginx_api.py`（NginxConf）、`logging_config.py`（jsonlogger，dictConfig 动态路径独立加载）、`main.py`（State）、`visual_analyzer.py`（render_slide_preview）、`visual_modifier.py`（parse_modify_intent/modify_ppt）、`security.py`（WebSocketException） | 已解决（删除）；复扫 90% 置信 unused import 归零；`from app.main import app` 冒烟通过，关联 7 测试文件 193 passed |
| P3 | 死函数/死 schema 7 处（vulture 60% 置信 + AST 装饰器过滤后人工核实，全库零引用零测试） | `vision_api.py`（AnalyzeImageRequest/CodeFromImageRequest 死 schema）、`file_upload.py`（calculate_file_hash）、`aiGeneratorPptx.py`（add_decorative_header/add_bullet_with_icon/style_title_shape/add_decorative_corner 4 个死装饰函数） | 已解决（删除）；vision/pptx/upload 关联 6 测试文件 35 passed。保留项：`validate_file_content`（测试保护）、`deprecated`/`get_version_router`/`create_versioned_app_setup`（`__init__.py` 版本化公开 API）、`Config` 内嵌类（Pydantic 配置机制，vulture 假阳性）、graceful_shutdown 扩展点、AiProjectCode 废弃面（AIC7 归档判定）、workflow 零消费公开 API 家族（既有固化判定） |
| P3 | 整类零消费死代码 4 符号（60% 置信候选中深挖「整类零引用」，区别于单方法预留；排除有测试保护的 ImageGenerationMetrics 等） | `aicloud/http_client.py`（RateLimitedClient）、`log_archiver.py`（LogRotationHandler，logging.Handler 动态注册亦零引用）、`visual/visual_analyzer.py`（FontStyle/FontWeight/TextAlignment 三个枚举，`visual/__init__.py` 导出列表亦不含） | 已解决（删除）；log_archiver/visual/metrics 关联测试 15+26 passed，三模块导入冒烟通过 |

### 死代码删除：content_analyzer 危险扩展名检查（CA7，2026-09-28）

| 优先级 | 问题 | 实际位置 | 状态 |
|---|---|---|---|
| P3 | CA7：`check_dangerous_extensions` 与 `SAFE_FILE_EXTENSIONS` 在 `app/` 内零生产消费，文件类型检查形同虚设 | `app/utils/aicloud/content_analyzer.py`、`tests/unit/test_aicloud.py` | 已解决（删除）；Agent 消费链复核：`sandbox_operator.py` 仅 import `analyze_content`/`deep_content_analysis`。删除两个定义与测试 import + 4 用例（66→62），`DANGEROUS_FILE_EXTENSIONS` 保留（测试消费其内容作配置哨兵）。回归 62 passed，aicloud 关联 4 文件 64 passed，消费链导入冒烟通过 |

### 死代码删除：sentry.py 与 startup_alert.py（2026-09-28）

| 优先级 | 问题 | 实际位置 | 状态 |
|---|---|---|---|
| P2 | SNT1/STA1：Sentry 错误追踪与启动失败告警两模块完备封装但全库零业务消费，从未接入 main.py | `app/utils/sentry.py`、`app/utils/startup_alert.py` | 已解决（删除）；全库符号级复核零消费（`set_user` 命中均为 `set_user_limit`/`set_user_id` 无关同名），requirements 无 `sentry-sdk` 且 sentry.py 为延迟 import——真实接入会因缺依赖失败，印证从未接线。连同唯一消费者 `tests/unit/test_startup_alert_and_sentry.py` 一并删除（备份 `/tmp/opencode/cleanup_alerting_20260928/`），SNT2-SNT5/STA2-STA5 随模块消解。`from app.main import app` 正常，全库无残留引用 |

### workflow 条件分支与卡死判定修复（2026-09-28）

| 优先级 | 问题 | 实际位置 | 状态 |
|---|---|---|---|
| P2 | CON1 条件分支不参与调度：`branch_path` 只是结果字段，`true_branch`/`false_branch` 对后续执行路径零影响，两类分支只要依赖条件节点完成就都会执行 | `app/utils/workflow/executor.py`、`state_machine.py`、`result_aggregator.py`、`app/api/v1/workflow.py`、`src/views/Workflow.vue` | 已解决；条件完成后按 `branch_path` 跳过未选中分支及下游（传递性：任一依赖被跳过即无法执行），新增 `skip_node`/`get_skipped_nodes`/`record_skipped` 与 `node_skipped` 事件，PR #408 |
| P2 | STM4 变体：`_check_workflow_stuck` 只统计 PENDING 可执行节点，未考虑 RUNNING 节点。`A(失败) → B(依赖 A)` + `C(独立)` 场景下，`fail_node(A)` 触发检查时 C 在运行 → 可执行节点为空 → 工作流被提前落定 `FAILED`，C 成为无人回收的孤儿任务 | `app/utils/workflow/state_machine.py` | 已解决；存在 RUNNING 节点时不再判定卡死，PR #408 |

回归 `tests/unit/test_executor.py` 新增 3 项（真/假分支跳过、传递性跳过、失败节点不提前卡死），回退源码后精确失败。`HA1`（审批回调恒未注册，HUMAN_APPROVAL 恒 auto_reject）经复核维持保留：`human_approval.py:140-150` 无回调时按安全策略自动拒绝、不挂起，落地真实审批需新增审批端点 + 会话态审批存储 + 恢复执行，属功能开发。`RSA2`/`RSA5`/`TDC3`/`TDC7`/`STM2` 维持原「零消费公开 API / 死代码」判定，均有回归测试保护。

### 后端缺陷扫描修复（2026-11-09）

| 优先级 | 问题 | 实际位置 | 状态 |
|---|---|---|---|
| P1 | 快照/回滚/差异三个端点只在 `orchestrator/{session_id}` 或 `user_uploads/{session_id}` 找项目目录，而编排实际写入 `projects/{user_id}/{session_id}`，任何真实生成会话都返回 404「项目目录不存在」（插件「文件版本」tab 不可用） | `app/api/v1/ai_agent/orchestrate_endpoints.py` | 已解决；`_authorize_snapshot_access` 返回会话记录，`_locate_snapshot_project_dir` 优先用 `ProjectSession.output_dir` 解析（复用 `_resolve_project_dir` 兼容绝对/相对路径），缺失时才回退历史两个固定目录。回归 `tests/unit/test_ai_agent_endpoint_blocking_io.py` 新增 2 项（优先 output_dir、缺失回退），`test_ai_agent_endpoint_authz.py` 同步新返回契约 |
| P1 | `.py` 无扩展名兜底：`EXTENSION_TYPE_MAP` 缺 `.py`，非常规命名的 Python 文件（`hello.py`、`vue.py`）推断为 `unknown`，触发 `_infer_unknown_file_types` 的 `RuntimeError`，整轮编排中止 | `app/agent/dependency_rules.py` | 已解决；补充 `'.py': 'utils'`。回归 `tests/unit/test_dependency_graph_file_type.py` 新增 2 项（无适配器/带 Python 适配器），及 `test_dependency_graph.py`、`test_orchestrator_files.py` 相关用例前提同步（显式 unknown 或不可识别扩展名以保留原语义） |
| P2 | PPT 下载/幻灯片/PDF 三个端点未做 `ppt_id` 格式校验，仅靠归属文件存在性间接防护；同文件预览端点已调用 `_validate_ppt_id`，口径不一致 | `app/api/v1/aiGeneratorPptx.py` | 已解决；`download_ppt`、`get_ppt_slides`、`download_ppt_as_pdf` 入口前置 `_validate_ppt_id`（UUID 正则，拒绝 `/`、`..`）。回归 `tests/unit/test_ppt_endpoints.py` 新增参数化 3 项，非 UUID 返回 400 |
| P2 | 项目下载 zip 用 `shutil.make_archive` 原样打包整个目录，混入 `.dep_graph.json`、`__pycache__/*.pyc` 等平台内部产物与构建残留，与 `generate/files` 列表接口的过滤口径不一致 | `app/api/v1/ai_agent/helpers.py` | 已解决；`_create_zip_archive_safe` 改为 `zipfile` 逐文件写入，跳过点号路径段与 `SKIP_DIRS`，与 `_collect_files_sync` 同口径。回归 `tests/unit/test_ai_agent_helpers_session_cleanup.py` 新增 1 项 |
| P2 | `TaskManager._get_task_from_redis` 只在 Redis 抛异常时回退内存；Redis 恢复但键不存在（创建时 Redis 不可用）时返回 None，`_execute_task` 随后的 `_update_status` 会对 None 取下标 | `app/utils/task_manager.py` | 已解决；读取失败或无键均回退 `self._tasks`。回归 `tests/unit/test_task_manager_progress.py` 新增 1 项 |
| P1 | `migrations/env.py` 只导入部分模型，`Base.metadata` 缺 7 张表（`github_user_configs`、`project_sessions`、`workflow_history`、`image_generation_history`、`conversation_messages`、`saved_projects`、`server_config`）。空库执行 `alembic upgrade head`（`make migrate`）会漏建这些表，随后 `GET /github/config`、会话/历史相关端点因表不存在而报错 | `migrations/env.py` | 已解决；补齐 7 个模型导入。回归 `tests/unit/test_alembic_bootstrap.py` 的 `KEY_TABLES` 由 3 张扩到 10 张，空库与 runner 库两条路径均覆盖 |
| P2 | `GET /github/config` 的 `verified` / `verification_status` 硬编码为 `false` / `not_performed`，`POST /github/verify` 结果不落库，重开设置页永远显示「尚未验证」，Flutter `github_settings_page.dart:147` 直接读取该字段 | `app/services/github_config_service.py`、`app/api/v1/github.py`、`app/models/github_config.py` | 已解决；新增 `GithubUserConfig.verified_at`，verify 端点按结果落库，改用户名/换 Token 时失效；响应新增 `verified_at`。迁移 `migrations/versions/20261109_add_github_verified_at.py` + `migrations/runner.py` 补列。回归 `tests/unit/test_github_readonly_api.py` 新增 4 项，`tests/unit/test_migration_runner.py` 新增 1 项 |
| P1 | 路径包含校验用 `str.startswith`，项目目录 `desktop-session` 的前缀兄弟 `desktop-session-evil` 判为「在项目内」，可越界读取与删除项目外文件 | `app/api/v1/ai_agent/generate_endpoints.py`（`read_project_file`、`delete_project_file`） | 已解决；改用 `Path.is_relative_to`。回归 `tests/unit/test_flutter_project_delivery.py` 新增 3 项（read 前缀穿越参数化、反斜杠字面名、delete 前缀穿越），回退源码后 read/delete 两用例精确失败 |
| P2 | 同类前缀校验：`ProjectFileManager`、`FileContract.validate_path`、`PathSecurityChecker.check` 也把前缀兄弟目录当合法范围 | `app/utils/agent_core.py`、`app/agent/file_contract.py`、`app/utils/guardrails.py` | 已解决；统一改 `Path.is_relative_to`。回归 `tests/unit/test_file_contract.py`、`tests/unit/test_guardrails.py` 各新增 1 项，回退源码后精确失败 |
| P3 | `TaskManager.get_task_info_async` 用裸 `except` 吞掉 datetime 解析异常 | `app/utils/task_manager.py` | 已解决；收窄为 `except (TypeError, ValueError)` |
| P1 | `20260425_add_user_management_indexes.py` 结尾调用全仓库不存在的 `if_exists_exists(op, 'system_logs')`。空库靠 `env.py` 的 metadata 旁路绕过整条历史链，测试测不到；任何 `alembic_version` 停在 `a1b2c3d4e5f6` 的既有库执行 `alembic upgrade head` 会 `NameError` 中断，后续迁移全部无法应用 | `migrations/versions/20260425_add_user_management_indexes.py` | 已解决；改为 `_has_table('system_logs')` 显式判断后再建/删索引（离线 `--sql` 按存在处理）。回归 `tests/unit/test_alembic_bootstrap.py` 新增 2 项（含 `system_logs` 与不含），回退源码后两条均失败 |
| P2 | 多条迁移在 `--sql` 离线模式下调用 `sa.inspect(op.get_bind())`，`MockConnection` 无反射能力，`alembic upgrade head --sql` 在 `20260908_add_github_user_config` 处抛 `NoInspectionAvailable`，CI/审计无法导出变更 SQL | `migrations/versions/20260908_add_github_user_config.py`、`20260918_add_knowledge_tags.py`、`20260918_unique_tasks_task_id.py`、`20261109_add_github_verified_at.py` | 已解决；四处补 `op.get_context().as_sql` 分支，离线只产出 DDL，在线保留反射判断。回归 `tests/unit/test_alembic_bootstrap.py` 新增 1 项参数化（MySQL/PostgreSQL 两方言），断言脚本含 `github_user_configs`、`verified_at` 与 head；回退源码后两条均报 `NoInspectionAvailable` 失败 |

回归：补齐本地依赖后，`PYTHONPATH=/workspace REDIS_URL=redis://localhost:6379/0 python3 -m pytest tests/unit tests/integration -q -p no:randomly --timeout=300` → `5463 passed, 2 skipped, 0 failed`（收集 5465，186s，第十轮补测后）。剩余 2 项为 `tests/unit/test_dynamic_adapter.py` 中显式 `@pytest.mark.skip` 的流式响应 mock，属设计性跳过。

补齐的本地测试依赖：`redis-server 7.0.15`（`127.0.0.1:6379`，测试使用 db 0 与 db 15）、`faiss-cpu 1.16.0`、`libreoffice-impress 7.4.7.2`、`poppler-utils 22.12.0`。补齐前无 Redis 时 unit 有 6 项失败、integration 有 5 项跳过；补 faiss 前 `test_v5_1_requirement_deep.py` 1 项跳过；补 LibreOffice/poppler 前 `test_ppt_feature_repairs.py` 1 项跳过。

### 后端缺陷扫描第二轮：认证授权与错误处理（2026-11-10）

| 优先级 | 问题 | 实际位置 | 状态 |
|---|---|---|---|
| P1 | 登录用户不存在分支直接返回，跳过 bcrypt 校验；该路径比「密码错误」快一个数量级，可据响应耗时枚举已注册邮箱 | `app/api/v1/auth.py`、`app/utils/security.py` | 已解决；新增 `DUMMY_PASSWORD_HASH`，用户不存在时也执行一次等价校验。回归 `tests/unit/test_auth_login_timing_enumeration.py` 2 项，回退源码后精确失败 |
| P1 | `nginx.deploy` 把请求体 `nginx_path` 直接拼进写入路径，未做目录白名单；同文件读取/删除/列表端点均有 `_is_allowed_nginx_config_path`，部署端点可写到任意目录 | `app/api/v2/nginx_api.py` | 已解决；写入前复用 `_is_allowed_nginx_config_path`，越界 403 |
| P2 | async 端点内直接调用阻塞 `subprocess.run`，等待外部进程期间冻结整个事件循环 | `app/api/v1/skills.py`、`app/api/v2/nginx_api.py` | 已解决；改用 `asyncio.to_thread`。回归 `tests/unit/test_event_loop_subprocess_blocking.py`、`tests/unit/test_skills_reload_auth.py` 断言 subprocess 不在主线程执行，回退源码后 3 项失败 |
| P2 | `/skills/reload` 提取失败时回显完整 `result.stderr`，泄露脚本路径与内部输出 | `app/api/v1/skills.py` | 已解决；stderr 只进日志，响应为通用文案。回归同上（`test_reload_hides_extract_stderr`），回退后失败 |
| P2 | 多组 500 分支 `detail=f"...{str(e)}"` 回显底层异常（路径、SQL、命令输出） | `app/api/v2/guardian_router.py`(6)、`app/api/v2/nginx_api.py`(3)、`app/api/v1/vision_api.py`(4)、`app/api/v1/file_upload.py`(1)、`app/api/v1/aiGeneratorPptx.py`(5)、`app/api/v1/ai_agent/generate_endpoints.py`(2)、`app/api/v1/ai_agent/orchestrate_endpoints.py`(3) | 已解决；统一通用文案 + `exc_info=True`。回归 `tests/unit/test_api_500_detail_not_leaked.py` 7 项，逐文件回退后对应项精确失败 |

分页上限（`auth.get_conversations`、`aicloud.get_history`/`get_audit_logs`/`search_history`）与本轮 500 文案同批提交，回归见 `tests/unit/test_pagination_bounds.py` 9 项。

### 后端缺陷扫描第三轮：资源无界增长与检索内存放大（2026-11-10）

| 优先级 | 问题 | 实际位置 | 状态 |
|---|---|---|---|
| P2 | `LoginAttemptTracker.failed_attempts` 以客户端可控的 email/IP 为键，只在被查询的键上清理过期记录；攻击者用大量不同邮箱登录失败可制造永不回收的键，内存无界增长 | `app/middleware/rate_limiter.py` | 已解决；新增 `_prune_stale_keys`，`record_failed_attempt` 时按窗口全量清扫（限速每秒一次），`is_blocked` 改用 `dict.get` 不再为未知键创建空列表。回归 `tests/unit/test_middleware_rlm_and_request_id.py` 新增 3 项，回退源码后 `test_login_tracker_prunes_unqueried_stale_keys` 精确失败 |
| P3 | `POST /knowledge/search` 把用户全部知识库分块一次读入内存逐条计算余弦相似度，`top_k` 无上界；超大知识库可造成内存放大 | `app/api/v1/aicloud_knowledge.py` | 已解决；`top_k` 约束 `1..50`，候选分块查询加 `MAX_SEARCH_CHUNKS=5000` 上限。回归 `tests/unit/test_knowledge_search_bounds.py` 3 项，回退源码后全部失败 |

### 后端缺陷扫描第四轮：越权访问、zip 炸弹与代理感知限流（2026-11-10）

| 优先级 | 问题 | 实际位置 | 状态 |
|---|---|---|---|
| P1 | `POST /aicloud/chat` 与 `/aicloud/chat/stream` 按客户端提供的 `session_id` 查会话时不带 `user_id` 过滤，命中他人会话后读取全部历史消息并追加新消息，可越权读取与污染他人会话 | `app/api/v1/aicloud.py` | 已解决；查询限定 `user_id`，ID 已被他人占用时返回 404。回归 `tests/unit/test_aicloud_session_isolation.py` 3 项，回退源码后 2 项精确失败 |
| P1 | `POST /projects/upload-zip` 只校验条目路径与扩展名，未限制解压后体积；50MB 的 zip 可膨胀到数十 GB 占满磁盘（zip bomb） | `app/api/v1/AiProjectCode.py` | 已解决；新增单文件 20MB 与解压后总量 200MB 上限，按 `ZipInfo.file_size` 在写盘前拒绝。回归 `tests/unit/test_AIprojectcode_zip_bomb.py` 4 项，回退源码后 2 项体积用例失败 |
| P2 | 登录限流键取自 `request.client.host`，nginx 反向代理后直连 peer 恒为代理地址，所有用户共用同一个 `127.0.0.1:email` 限流键，跨账号暴力破解失去 IP 维度限流 | `app/api/v1/auth.py` | 已解决；改用 `app.utils.rate_limiter.get_client_ip`（仅在受信代理时采信 `X-Real-IP`/`X-Forwarded-For` 末段）。回归 `tests/unit/test_rate_limiter.py` 新增 1 项，回退源码后精确失败 |
| P3 | `request.client` 为 `None`（测试客户端/部分 ASGI 环境）时直接取 `.host` 抛 `AttributeError`，登录返回 500 | `app/api/v1/auth.py` | 已解决；回退值 `unknown`。回归 `tests/unit/test_auth_login_timing_enumeration.py` 新增 1 项，回退源码后精确失败 |
| P2 | `_generation_http_exception` 兜底 500 仍把 `str(error)` 拼进响应，与第二轮「500 统一通用文案」策略冲突，可泄露路径/SQL/命令输出 | `app/api/v1/ai_agent/orchestrate_endpoints.py` | 已解决；返回通用文案，异常只进日志。回归 `tests/unit/test_agent_endpoint_persistence_contract.py` 断言更新，回退源码后失败 |
| P2 | PPT 进度 WebSocket 异常分支把 `str(e)` 推给客户端 | `app/api/v1/aiGeneratorPptx.py` | 已解决；推送通用文案 + `logger.exception`。回归 `tests/unit/test_api_500_detail_not_leaked.py` 新增静态守卫，回退源码后失败 |
| P3 | `_cleanup_session_queues` 在 `cancel_event` 已被其它路径清理时不回收 `_pending_stream_owners`，且删除队列发生在归属确认之前，旧任务可能误删新任务资源 | `app/api/v1/ai_agent/orchestrate_endpoints.py` | 已解决；先做归属判定再删队列/事件，owner 始终回收。回归 `tests/unit/test_stream_cancel_reconnect.py` 新增 2 项，回退源码后均失败 |

### 后端缺陷扫描第五轮：路径穿越删除、事务回滚与落盘一致性（2026-11-10）

| 优先级 | 问题 | 实际位置 | 状态 |
|---|---|---|---|
| P1 | `DELETE /ai-agent/sessions/{session_id}` 把 `session_id` 直接拼进 `shutil.rmtree` 路径；`GenerateRequest.session_id` 无格式校验，客户端提交 `../../victim` 可越界删除任意目录 | `app/schema/codeRequest.py`、`app/api/v1/ai_agent/orchestrate_endpoints.py` | 已解决；`GenerateRequest` 限制 `[A-Za-z0-9_-]{1,128}`，删除端点再按基准目录 `is_relative_to` 防御。回归 `tests/unit/test_generate_session_id_traversal.py` 10 项，回退源码后 6 项校验 + 1 项越界删除失败 |
| P2 | 知识库上传失败分支在事务可能已失效时直接 `commit` 失败状态，二次异常会掩盖原始错误 | `app/api/v1/aicloud_knowledge.py` | 已解决；先 `rollback` 再重新加载文档写失败状态。回归 `tests/unit/test_aicloud_embedding_failure.py` 新增 1 项，回退源码后失败 |
| P2 | 知识库删除先删文件再删记录，commit 失败会留下「记录指向不存在文件」；且 `file_path` 未校验范围 | `app/api/v1/aicloud_knowledge.py` | 已解决；先提交记录删除再删文件，并限定在存储根目录内。回归 `tests/unit/test_aicloud_embedding_failure.py` 新增 2 项，回退源码后越界删除项失败 |
| P2 | 单文件上传在 `os.replace` 落盘后若 DB commit 失败，不回滚也不删文件，磁盘累积孤儿文件 | `app/api/v1/file_upload.py` | 已解决；commit 失败 `rollback` + `unlink`。回归 `tests/unit/test_file_upload_orphan_cleanup.py` 新增 2 项，回退源码后提交失败项失败 |
| P2 | 分片合并在合并文件落盘后若 DB commit 失败，同样遗留孤儿文件 | `app/api/v1/file_upload.py` | 已解决；同上。回归 `tests/unit/test_file_upload_orphan_cleanup.py` 新增 1 项，回退源码后失败 |

### 后端缺陷扫描第六轮：N+1 查询、无界素材与过期会话回收（2026-11-10）

| 优先级 | 问题 | 实际位置 | 状态 |
|---|---|---|---|
| P2 | `GET /aicloud/history` 对每个会话各发一条消息查询，`limit` 最大 100 时单次请求最多 101 次数据库往返 | `app/api/v1/aicloud.py` | 已解决；改为 `session_id IN (...)` 一次取回再按会话分组。回归 `tests/unit/test_aicloud_history_batch_query.py` 新增 2 项，回退源码后批量查询项失败 |
| P2 | `POST /ai-agent/generate` 的 500 兜底仍把 `str(e)` 拼进 `detail.error`，泄露路径/SQL/命令输出，与全局通用文案策略冲突 | `app/api/v1/ai_agent/generate_endpoints.py` | 已解决；移除 `error` 字段，完整异常进日志。回归 `tests/unit/test_api_500_detail_not_leaked.py` 新增 1 项，回退源码后失败 |
| P2 | `PPTGenerationRequest.material_file_ids` 无数量上限，`_build_material_context` 逐 ID 查库并可能解析文件；10MB 请求体可放大为大量数据库查询与文件解析 | `app/api/v1/aiGeneratorPptx.py` | 已解决；请求模型限制 50 项，上下文函数对非模型入口同样截断。回归 `tests/unit/test_ppt_material_content_usage.py` 新增 2 项，回退源码后均失败 |
| P2 | Agent Host 每次握手写入 30 分钟会话到内存与 `data/agent_host_sessions/*.json`，过期后从不清理，内存与磁盘持续增长 | `app/api/v1/agent_host.py` | 已解决；握手时按 60 秒节流清扫过期内存项与 JSON 文件。回归 `tests/unit/test_agent_host_api.py` 新增 2 项，回退源码后握手清扫项失败 |
| P2 | `MetricsCollector` 的慢调用告警与覆盖率告警按次 `append` 且无裁剪，长运行服务下 `alerts` 无限增长（既有 PMC3 只处理了缓存命中率重复告警） | `app/utils/performance_metrics.py` | 已解决；统一走 `_append_alert` 并保留最近 100 条。回归 `tests/unit/test_performance_metrics.py` 新增 1 项，回退源码后失败 |

### 后端缺陷扫描第七轮：编排入口路径越权（2026-11-10）

| 优先级 | 问题 | 实际位置 | 状态 |
|---|---|---|---|
| P1 | `POST /ai-agent/modify` 把客户端 `project_path`/`output_dir` 直接交给 `_resolve_project_dir`，绝对路径与 `PROJECTS_BASE_DIR` 之外目录均被接受；分析分支读取该目录、修改分支把编排器输出写进该目录，等于任意路径读写 | `app/api/v1/ai_agent/orchestrate_endpoints.py`、`app/api/v1/ai_agent/schemas.py` | 已解决；`ModifyRequest` 两个字段加长度与 `..` 校验，端点改用 `_validate_project_path`（范围 + 归属 + 存在性）。回归 `tests/unit/test_modify_project_path_boundary.py` 7 项，回退源码后全部失败 |
| P1 | 同步 `POST /ai-agent/orchestrate` 的 `output_dir` 未做范围与归属校验，可指定任意可写目录作为生成目标 | `app/api/v1/ai_agent/orchestrate_endpoints.py` | 已解决；解析后调用 `_validate_project_target`。同一回归文件覆盖绝对路径越界 |
| P1 | `POST /ai-agent/orchestrate/stream` 的 `project_path` 虽拒绝绝对路径与 `..`，但仍可传 `2/foreign` 指向其他用户已存在的项目，读取并覆盖其文件 | `app/api/v1/ai_agent/orchestrate_endpoints.py` | 已解决；入口先做归属校验。同一回归文件覆盖跨用户拒绝 |
| P2 | `POST /ai-agent/evaluate` 的 `output_dir` 同样未校验，评价流程会以该目录构造编排器 | `app/api/v1/ai_agent/orchestrate_endpoints.py` | 已解决；统一调用 `_validate_project_target` |

`_validate_project_target` 不要求目录已存在，供会新建目录的编排入口使用；`_validate_project_path` 在其上追加存在性与目录类型检查。归属允许 `{user_id}/name`、`{timestamp}_{uid}_{user_id}` 与 `user_uploads/{user_id}/name` 三种既有布局，前端 `ProjectGenerator.vue` 与 Flutter 客户端传入的相对路径均兼容。

### 后端缺陷扫描第八轮：路由声明顺序遮蔽（2026-11-10）

| 优先级 | 问题 | 实际位置 | 状态 |
|---|---|---|---|
| P2 | `PUT /api/v2/Controller/admin/config/batch` 声明在 `PUT /admin/config/{key}` 之后。FastAPI 按声明顺序匹配，`batch` 被当作 `key="batch"` 进入单点更新，请求体结构不符恒返回 422，批量配置接口实际不可用 | `app/api/v2/guardian_router.py` | 已解决；`batch_update_configs` 上移到路径参数路由之前。回归 `tests/unit/test_v2_api_hardening.py::test_batch_config_endpoint_is_reachable`，回退声明顺序后用例以 422 失败 |
| P2 | `ConversationHistoryRequest.limit` 为裸 `int`，负数在 SQLite 中等于取消 `LIMIT`，`POST /api/v1/conversation/history` 可一次物化整段对话；超大值同样放大查询 | `app/schema/history.py` | 已解决；约束 `1..100`。回归 `tests/unit/test_backend_hardening_round8.py` 边界用例，回退后 3 项越界用例失败 |
| P3 | `GET /api/v1/agent/saved` 的 `offset`/`limit` 与 `GET /api/v1/agent/sessions` 的 `limit` 均为裸 `int`，负值或超大值直达 SQL | `app/api/v1/ai_agent/generate_endpoints.py`、`app/api/v1/ai_agent/orchestrate_endpoints.py` | 已解决；分别约束 `offset>=0`、`limit 1..100` 与 `limit 1..50`。回归同上文件查询参数断言 |
| P3 | `ConcurrentLimitManager._change_log` 每次热调整都 `append` 且永不裁剪，`GET /concurrent-limits/history?limit=` 无上界，长期运行内存与响应体持续增长 | `app/utils/dynamic_concurrent.py`、`app/api/v1/ai_agent/orchestrate_endpoints.py` | 已解决；日志保留最近 500 条，读取时再按 `1..500` 钳制，端点加同样约束。回归同上文件，回退后日志上限用例失败 |

扫描方式：用 AST 提取全部路由的 (method, path) 声明序列，按方法逐条比对「后续同方法路径可被前面的 `{param}` 模式命中」的形态。修复后全应用命中 0 处；跨方法同名路径（如 `DELETE /pptx/history/{task_id}` 与 `GET /pptx/history/stats`）不构成遮蔽。

### 后端缺陷扫描第九轮：静态产物缺失导致根路径 500（2026-11-11）

| 优先级 | 问题 | 实际位置 | 状态 |
|---|---|---|---|
| P2 | `src/dist/index.html` 不存在（前端未构建）时，`GET /`、SPA 历史路由 `GET /{full_path:path}` 均返回 500。`FileResponse` 构造阶段不校验文件存在，缺失在 ASGI 发送阶段抛 `RuntimeError`，把可预期的「未构建」状态变成服务端错误 | `app/main.py`（`serve_vue`、`serve_vue_routes`） | 已解决；新增 `_dist_index_or_404()`，缺失产物时抛 404（`前端静态资源未构建`），API 路由不受影响。回归 `tests/unit/test_static_spa_path_traversal.py` 新增 2 项（端到端 `/`、`/some/spa/route`、`/missing-asset.js` 均 404 + 协程直调），回退源码后 2 项精确失败 |

真实验证：Uvicorn `:8000` 下 `/`、`/some/spa/route`、`/missing.js` 由 500 变为 404，`/api/v1/health`、`/api/docs` 仍 200。

### 后端缺陷扫描第十轮：覆盖率补测暴露的生成与安全缺陷（2026-11-11）

以「提高覆盖率并修复补测中暴露的真实缺陷」为目标，对 0%–30% 覆盖的纯逻辑模块补测，修复 5 处缺陷：

| 优先级 | 问题 | 实际位置 | 状态 |
|---|---|---|---|
| P1 | 确定性 CRUD 渲染器生成的 `models.py` / `schemas.py` 首行即 `IndentationError`：`_render_model` / `_render_schema` 用 `dedent` 拼接多行字段块，字段行缩进未被统一，生成项目无法导入 | `app/agent/constrained_generation.py` | 已解决；改为显式行列表拼接。回归 `tests/unit/test_constrained_generation.py` 23 项（含真实生成六文件并执行其自带 CRUD 测试），回退后 5 项失败 |
| P1 | 安全检测漏掉经典 bash fork bomb：`MALICIOUS_PATTERNS` 写死无空格形态 `:(){:\|:&\};:`，带空格的 `:(){ :\|:& };:` 与自定义函数名变体均不命中，沙箱读写内容检查可被绕过 | `app/utils/aicloud/content_analyzer.py` | 已解决；正则改用反向引用匹配自递归 `name(){ name\|name& };`，并排除 `foo() { bar \| baz & }` 误报。回归 `tests/unit/test_aicloud_content_analyzer.py` 40 项（含误报防护），回退后 3 项失败 |
| P2 | `truncate_text(text, max_length<3)` 用 `text[:max_length-3]` 负切片，结果反而变长（`max_length=2` 返回 8 字符） | `app/utils/pptx/text_processor.py` | 已解决；`max_length<=0` 返回空串，`<=3` 只返回对应数量的点。回归 `tests/unit/test_pptx_text_processor.py` 25 项，回退后 3 项失败 |
| P2 | `smart_split_line` 遇到超长英文单词只保留前 `max_chars` 个字符，剩余内容直接丢弃 | `app/utils/pptx/text_processor.py` | 已解决；按 `max_chars` 分段保留整词。回归同上文件，回退后 1 项失败 |
| P2 | 人工审批回调返回 dict 但缺 `option` 键时，`selected_option = result.get("option", result)` 回退成整个 dict，下游按字符串处理拿到非预期结构 | `app/utils/workflow/node_types/human_approval.py` | 已解决；按 `approved` 推导 `approve`/`reject` 字符串选项。回归 `tests/unit/test_human_approval_node.py` 16 项，回退后 1 项失败 |

覆盖率变化（`--cov=app`，unit + integration）：`67.56% → 68.06%`，覆盖语句 42964 → 43377，新增 104 个用例（`5359 → 5463 passed`）。四个目标模块：`constrained_generation.py` 0% → 97.9%，`content_analyzer.py` 20.75% → 100%，`text_processor.py` 12.5% → 96.3%，`human_approval.py` 18.2% → 97.4%。

### 后端缺陷扫描第十一轮：布局、项目指纹与配图缓存缺陷（2026-11-11）

继续对 20%–35% 覆盖的纯逻辑模块补测，修复补测中暴露的 6 处真实缺陷：

| 优先级 | 问题 | 实际位置 | 状态 |
|---|---|---|---|
| P1 | 装饰图片被当成正文主图：`get_main_image()` 在无「非装饰图」时回退 `images[0]`，`need_image` 又只判断 `image_type != NONE`。只有角落装饰图的页面被判为需要配图，同一张图标既渲染成主图又渲染成装饰图 | `app/utils/visual/visual_analyzer.py` | 已解决；`get_main_image()` 无合格主图返回 `None`，`need_image` 排除 `is_decoration`。回归 `tests/unit/test_layout_decider.py`，回退后 2 项失败 |
| P1 | 外部传入的 `width_ratio` 未约束，`0`/负数/`1.5`/超大值/nan/非数字会把文本框宽高算成负数或把内容推到画布外（`width_ratio=5` 时文本宽 -49.6 英寸） | `app/utils/visual/layout_decider.py` | 已解决；新增 `_safe_width_ratio` 约束到 0.1–0.7，非法值回退 0.4。回归同上，回退后 10 项失败 |
| P2 | 居中/行内/顶部图片布局的内容框超出画布：内容高度只按内容区高度计算，未减去实际起始位置，`CENTER` 页面内容框底边 8.5 英寸 > 7.5 英寸画布 | `app/utils/visual/layout_decider.py` | 已解决；按 `slide_height - bottom_margin - content_top` 再夹取，最小 0.3 英寸。回归同上，回退后 3 项失败 |
| P2 | 分隔线颜色非法（如 `#GGGGGG`）时 `int(color[i:i+2], 16)` 直接抛 `ValueError`，整页渲染中断 | `app/utils/visual/layout_decider.py` | 已解决；复用 `_parse_color` 并对 tuple 长度做校验，非法值回退深灰。回归同上，回退后 1 项失败 |
| P2 | 项目根目录位于隐藏目录时（如 CI 的 `.workspace/project`），`_iter_source_files` 用绝对路径 `path.parts` 判断隐藏段，导致该根下所有文件被跳过，指纹恒为空 | `app/agent/project_profiler.py` | 已解决；改用 `path.relative_to(root)` 只检查项目内路径。回归 `tests/unit/test_project_profiler_branches.py`，回退后 1 项失败 |
| P2 | 相对导入被当作外部模块过滤：`from .helpers import x` 得到 `.helpers`，随后被「首字符 `.` 视为项目内」的规则计数成假模块 `.foo`/`.`，`high_dependency` 出现 `/foo.py`、`/.py` 等不存在文件 | `app/agent/project_profiler.py` | 已解决；新增 `_resolve_relative_module` 解析为 `pkg.helpers`，`from . import x` 指向包本身时跳过。回归同上，回退后 3 项失败 |

同批修复的低风险判定缺陷（均由新增用例覆盖）：

- 分层目录名由任意子串改为词元匹配，`rapid`/`capital`/`metadata` 不再命中 `api`/`data`；同时支持复数与 `-ies`。
- JS `require('x')` 仅在独立语句时匹配，`const x = require('x')` 不再漏计；`node:`、`std::` 前缀识别为标准库。
- JS/Python/Go/Java 测试文件匹配统一小写化，`FooIT.java`、`*.spec.tsx` 可被识别。
- `ImageStrategy` 搜索缓存写入用 `order=...` 键、读取用无 `order` 键，缓存永远未命中；统一为同一键。

覆盖率变化（`--cov=app --cov-branch`，unit + integration）：`68.06% → 69.71%`，覆盖语句 43377 → 46407，新增 288 个用例（`5463 → 5751 passed`）。本轮四个目标模块：`layout_decider.py` 29.34% → 95.90%，`visual_analyzer.py` 26.52% → 57.53%，`project_profiler.py` 33.06% → 98.22%，`image_upgrader.py` 9.93% → 91.65%。

覆盖率采集需显式带 `--cov-branch`：`tests/unit/test_toolchain.py` 会在临时项目里真实启动 `python3 -m pytest`，pytest-cov 只在该参数下向子进程注入 `COV_CORE_BRANCH=enabled`。缺失时子进程写出 statement-only 碎片，主进程 `combine()` 抛 `DataError: Can't combine statement coverage data with branch data`。

### 后端缺陷扫描第十二轮：视觉分析解析兜底缺陷（2026-11-11）

继续补测 `visual_analyzer.py`（26.52% → 57.53% 后的第一缺口），修复解析兜底 4 处真实缺陷：

| 优先级 | 问题 | 实际位置 | 状态 |
|---|---|---|---|
| P1 | 模型返回以 ```json 开头但缺结尾围栏时（输出被截断），`content.find("```", start)` 返回 -1，`content[start:-1]` 丢掉最后一个字符，合法尾部结构被破坏后解析失败 | `app/utils/visual/visual_analyzer.py`（`_parse_analysis_response`） | 已解决；`end == -1` 时取 `len(content)`。回归 `tests/unit/test_visual_analyzer_branches.py`，回退后 2 项失败 |
| P1 | JSON 修复仍失败时走正则兜底，但 `\{[^{}]*\}` 无法匹配含嵌套 `images` / `title_style` 的 slide 对象，正常响应被整段丢弃，视觉规划退化为全默认 | `app/utils/visual/visual_analyzer.py`（`_extract_json_by_regex`） | 已解决；改为括号配对切分（`_iter_balanced_objects`，跳过字符串内括号与转义）+ `JSONDecoder.raw_decode` 保类型。回归同上，回退后 4 项失败 |
| P2 | `keywords` / `highlight_words` 数组按 `[^,}]+` 取值，只拿到首个逗号前的 `["云`，关键词与高亮词退化成截断字符串 | `app/utils/visual/visual_analyzer.py`（`_extract_images`、`_extract_json_by_regex`） | 已解决；数组字段按 JSON 解析保留 `list`，非法数组回退空列表。回归同上，回退后 3 项失败 |
| P2 | `_extract_style` 的 `font_size` 正则取到带引号的 `"22"` 后 `float('"22"')` 抛错，恒回退 24，模型指定的字号全部丢失 | `app/utils/visual/visual_analyzer.py`（`_extract_style`） | 已解决；统一走 `_json_field_value` 解引用后转数值。回归同上，回退后 1 项失败 |

覆盖率变化（`--cov=app --cov-branch`，unit + integration）：`69.71% → 69.95%`，覆盖语句 46407 → 46574，新增 45 个用例（`5751 → 5796 passed`）。`visual_analyzer.py` 57.53% → 98.84%（无遗漏语句，剩余部分分支为循环回边）。

### 后端缺陷扫描第十三轮：自定义模板解析与装饰缺陷（2026-11-11）

补测 `app/utils/pptx/custom_template.py`（49.03%，缺失 287 行），修复模板解析链路的 6 处真实缺陷：

| 优先级 | 问题 | 实际位置 | 状态 |
|---|---|---|---|
| P1 | 占位符类型用 `str(ph.type)` 与 `"title"` / `"obj"` 精确比较，而真实值是 `"TITLE (1)"` / `"OBJECT (7)"`，真实模板全部被判为 `blank`，标题、正文、边距、必要元素、兼容性评分一并失效 | `app/utils/pptx/custom_template.py`（`extract_layout_info`、`_get_placeholder_info`、`_detect_margins`、`analyze_slide_master`、`check_required_elements`、`get_compatibility_score`） | 已解决；新增 `_placeholder_type_name()` 归一化枚举名，配套 `_TITLE_PLACEHOLDERS` / `_BODY_PLACEHOLDERS`。回归 `tests/unit/test_ppt_custom_template_branches.py`，回退后 7 项失败 |
| P1 | `SlideLayout.shapes`（`LayoutShapes`）没有 `add_shape` / `add_textbox`，装饰添加全部抛错后被 `except` 静默吞掉，页眉条、页脚条、页码、角标永不生效 | `app/utils/pptx/custom_template.py`（`TemplateConverter`） | 已解决；新增 `_add_layout_autoshape` / `_add_layout_textbox`，走 `layout.shapes._spTree.add_autoshape(...)` / `add_textbox(...)` 再包装 `Shape`。回归同上，回退后 1 项失败 |
| P2 | 页眉/页脚条检测用 `hasattr(shape, "position")` 探测，python-pptx 的 `Shape` 无该属性，条件恒为假 | `app/utils/pptx/custom_template.py`（`_analyze_shape_for_decoration`） | 已解决；改用 `shape.top` 与画布高度比较。回归同上，回退后 1 项失败 |
| P2 | 主题字体用 `el.find(qn("a:fontScheme"))` 只查直接子节点，真实结构是 `theme → themeElements → fontScheme`，主题字体永远取默认值 | `app/utils/pptx/custom_template.py`（`_extract_from_theme_fonts`） | 已解决；改为 `.//` 后代查找。回归同上，回退后 1 项失败 |
| P3 | 兼容性评分缺少边界用例：无母版、超大画布（部分尺寸得分）、主题缺失时评分路径未验证 | `app/utils/pptx/custom_template.py`（`get_compatibility_score`） | 已补充边界回归，无母版返回 0.2、15% 部分尺寸得分 0.08 |

覆盖率变化（`--cov=app --cov-branch`，unit + integration）：`69.95% → 70.47%`，覆盖行 46574 → 46859，语句总数 63623 → 63642，覆盖分支 12283 → 12447，新增 86 个用例（`5796 → 5882 passed`）。`custom_template.py` 49.03% → 93.00%。

### 后端缺陷扫描第十四轮：依赖图推断与重构缺陷（2026-11-11）

补测 `app/agent/dependency_graph.py`（1951 行、1065 语句，77.62%），修复补测暴露的 2 处真实缺陷：

| 优先级 | 问题 | 实际位置 | 状态 |
|---|---|---|---|
| P1 | `_infer_file_description` 的规则链挂在 `elif` 上：一旦进入语言适配器分支，`database` / `config` / `schema` / `core` 等规则全部被跳过。构造带适配器且文件不是包入口时，补齐的缺失文件描述恒为 `None` | `app/agent/dependency_graph.py`（`_infer_file_description`） | 已解决；规则链改为独立 `if`，仅包入口判定留在适配器分支内。回归 `tests/unit/test_dependency_graph_branches.py`，回退后 1 项失败 |
| P2 | `refactor_file` 对 `add_file` 拒绝的非法新路径仍追加到返回值，重构返回「成功」但该路径不在图中，随后入边被重定向到不存在的节点 | `app/agent/dependency_graph.py`（`refactor_file`） | 已解决；仅在 `nf_path in self.nodes` 时计入。回归同上，回退后 1 项失败 |

覆盖率变化（`--cov=app --cov-branch`，unit + integration）：`70.47% → 70.77%`，覆盖行 46859 → 47014，语句总数 63642 → 63643，覆盖分支 12447 → 12547，新增 87 个用例（`5882 → 5969 passed`）。`dependency_graph.py` 77.62% → 92.03%。

### 后端缺陷扫描第十五轮：交叉验证签名与契约缺陷（2026-11-11）

补测 `app/agent/cross_validator.py`（76.04%，缺失 184 行），修复补测暴露的 5 处真实缺陷：

| 优先级 | 问题 | 实际位置 | 状态 |
|---|---|---|---|
| P1 | 可变参数 `*args` / `**kwargs` 被当作必需参数：`def total(*values)` 的正常调用被报「缺少必需参数 values」，直接生成伪缺陷交给 LLM 修复 | `app/agent/cross_validator.py`（`_extract_function_params`、`_validate_function_signatures`） | 已解决；提取参数时跳过星号参数，并移除会连带放过前置必需参数的 `has_varargs` 短路。回归 `tests/unit/test_cross_validator.py`，回退后 2 项失败 |
| P1 | 调用实参含比较表达式时位置参数少算：`add(flag == 1, 2)` 中的 `flag == 1` 被 `'=' in arg` 当成关键字参数，`2` 之外少计一个位置参数，误报缺参 | `app/agent/cross_validator.py`（`_extract_call_params`、`_count_positional_args`） | 已解决；新增 `_keyword_arg_name()` 只识别顶层单个 `=`，比较与海象运算符按位置参数处理。回归同上并新增 `tests/unit/test_cross_validator_branches.py`，回退后 3 项失败 |
| P1 | axios 响应字段从未被识别：响应变量赋值写在调用之前，但扫描窗口只取调用点之后的 800 字符，`const res = await axios.get(...)` 恒查不到，API 契约校验被静默跳过 | `app/agent/cross_validator.py`（`_extract_frontend_api_calls`） | 已解决；窗口向前回看 200 字符。回归 `test_cross_validator_branches.py::test_axios_response_fields_use_data_prefix`，回退后 1 项失败 |
| P2 | 通用导入提取漏掉 `#include` 与行内 `require()`：注释过滤只按首字符 `#` 判断，`#include <stdio.h>` 被当成注释；`require(...)` 正则锚定行首，`const x = require('node:fs')` 永不命中 | `app/agent/cross_validator.py`（`_extract_imports_generic`） | 已解决；`#include` 放行，`require` 改为行内匹配。回归同上，回退后 1 项失败 |
| P2 | 批量修复兜底把无关内容写进目标文件：响应含 `===other.py===` 标记但无期望文件时，单文件兜底仍把整段响应（含标记）当作代码写入，覆盖原文件 | `app/agent/cross_validator.py`（`_parse_batch_fix_result`） | 已解决；仅当内容完全不含 `===` 标记时才走单文件兜底。回归同上，回退后 1 项失败 |

覆盖率变化（`--cov=app --cov-branch`，unit + integration）：`70.77% → 71.12%`，覆盖行 47014 → 47213，语句总数 63643 → 63670，覆盖分支 12547 → 12675，新增 102 个用例（`5969 → 6071 passed`）。`cross_validator.py` 76.04% → 96.64%。

### 后端缺陷扫描第十六轮：架构师路径重写与混合语言推断缺陷（2026-11-11）

补测 `app/agent/architect.py`（780 语句、69.12%、缺失 209 行），修复补测暴露的 6 处真实缺陷：

| 优先级 | 问题 | 实际位置 | 状态 |
|---|---|---|---|
| P1 | `_path_module_forms` 用 `lstrip("./")` 按字符集剥前缀：`.gitignore` 变成 `gitignore`、`../main.py` 变成 `main.py`。严格文件集生效后重写导入会指向错误文件 | `app/agent/architect.py`（`_path_module_forms`） | 已解决；改为仅循环剥离字面量 `./` 前缀。回归 `tests/unit/test_architect_branches.py`，回退后 1 项失败 |
| P1 | Python 模块形态与斜杠形态同长时顺序错误：单段路径的 `utils` 与 `app/utils` 冲突，导入语句被改写成斜杠路径 `from app/utils import x`，生成代码无法导入 | `app/agent/architect.py`（`_path_module_forms`） | 已解决；点号形态插到斜杠形态之前，让导入语句优先匹配。回归同上，回退后 1 项失败 |
| P1 | 混合项目所有文件都被填成前端语言：`构建 Vue 前端和 Python 后端` 只按首个关键词返回 javascript，`app/api.py` 也被标成 javascript，生成阶段按错误语言套模板 | `app/agent/language_detector.py`（`_detect_fullstack_languages`）、`app/agent/architect.py`（`_normalize_file_plan_item`、`_infer_language_from_path`） | 已解决；后端标记旁的 Python/Go 等语言词参与后端语言推断，文件语言按扩展名推断后再回退到计划默认值。回归 `tests/unit/test_languages.py` 与 `test_architect_branches.py`，回退后 1 项失败 |
| P2 | 包相对导入被当成绝对模块：`from .relative import x` 解析成 `.relative`，完整性补全据此虚构计划外文件 | `app/agent/architect.py`（`_parse_import_to_module`） | 已解决；前导点的相对导入返回 `None`。回归同上，回退后 1 项失败 |
| P2 | JSON 字符串形态的 `imports` 未解包：`"b.py"` 原样保留引号，依赖解析拿不到模块名 | `app/agent/architect.py`（`_parse_jsonish`、`_coerce_architecture_fields`） | 已解决；引号标量先经 `json.loads` 解包，字符串分支改用解包结果。回归同上，回退后 1 项失败 |
| P2 | 非数字的 `estimated_files` 被当作 0：`simple` + `"many"` 被判定为单文件项目，`_skip_boilerplate_files` 误跳过必要的样板文件 | `app/agent/architect.py`（`_skip_boilerplate_files`） | 已解决；无法转换成整数时直接返回 False。回归同上，回退后 1 项失败 |

覆盖率变化（`--cov=app --cov-branch`，unit + integration）：`71.12% → 71.56%`，覆盖行 47213 → 47458，语句总数 63670 → 63699，覆盖分支 12675 → 12831，新增 152 个用例（`6071 → 6223 passed`）。`architect.py` 69.12% → 96.78%，`language_detector.py` 79.68% → 83.18%。

### 后端缺陷扫描第十七轮：文件工具路径穿越与搜索解析缺陷（2026-11-11）

补测 `app/agent/tools.py`（657 语句、60.95%、缺失 247 行），修复补测暴露的 3 处真实缺陷：

| 优先级 | 问题 | 实际位置 | 状态 |
|---|---|---|---|
| P1 | `_tool_regex_replace` 路径穿越：`root/../outside.txt` 的 `Path` 只在词法层面比较字符串前缀，`relative_to(root)` 通过校验，实际读写落到项目外的文件 | `app/agent/tools.py`（`_tool_regex_replace`） | 已解决；先用 `os.path.normpath` 消掉 `..`，再对 glob 命中的每个文件按 `resolve()` 真实路径复核。回归 `tests/unit/test_tools_branches.py::test_regex_replace_rejects_traversal`，回退后失败 |
| P2 | grep 上下文行被整行丢弃：`grep -C` 输出的上下文行是 `file-line-content`，解析只按 `:` 切分，命中行之外的上下文永远进不了结果 | `app/agent/tools.py`（`_tool_search_files`） | 已解决；改用 `^(.*?)[:-](\d+)[:-](.*)$` 同时接受 `:` 与 `-` 分隔。回归 `test_search_skips_separator_lines_and_parses_context_numbers`，回退后失败 |
| P2 | 版本号文件名分支不可达：`filename.startswith('=')` 的通用非法名判定排在 `^=\d` 版本号判定之前，`=1.2.3` 永远拿不到版本号提示 | `app/agent/tools.py`（`_tool_write_file`） | 已解决；版本号判定前移。回归 `test_version_like_filename_is_rejected`，回退后失败 |

覆盖率变化（`--cov=app --cov-branch`，unit + integration）：`71.56% → 72.00%`，覆盖行 47458 → 47703，语句总数 63699 → 63693，覆盖分支 12831 → 12948，新增 113 个用例（`6223 → 6336 passed`）。`tools.py` 60.95% → 100.00%（657/657 行、262/262 分支）。

### 后端缺陷扫描第十八轮：多模型编排与响应解析缺陷（2026-11-11）

补测 `app/agent/multi_model_agent.py`（10.07%）与 `app/adapter/model_adapter.py`（15.79%），修复补测暴露的 3 处真实缺陷：

| 优先级 | 问题 | 实际位置 | 状态 |
|---|---|---|---|
| P1 | 工具调用缺 `id` 时被整条丢弃：`_extract_tool_calls` 只在 `call_id` 非空时保留，而 OpenAI 兼容流式响应常省略 `id`，解析结果永远为空 | `app/adapter/model_adapter.py`（`_extract_tool_calls`） | 已解决；无 `id` 的调用直接保留，有 `id` 的才参与去重。回归 `tests/unit/test_model_adapter_branches.py`，回退后 1 项失败 |
| P1 | `"tool_calls": [...]` 裸片段永远解析失败：该正则捕获的是数组内部元素，却按 `{...}` 对象解析，`isinstance(dict)` 不含 `tool_calls` 时整条丢弃 | `app/adapter/model_adapter.py`（`_extract_tool_calls`） | 已解决；数组体按 `[match]` 解析，并抽出 `absorb()` 统一吸收 dict/list。回归同上，回退后 1 项失败 |
| P2 | 代码块解析被嵌套 `}` 截断：非贪婪 `\{[\s\S]*?\}` 在第一个内层对象结束处截止，含完整工具调用的代码块无法解析 | `app/adapter/model_adapter.py`（`_extract_tool_calls`） | 已解决；改为整体提取代码块后 `json.loads`，同时支持对象与裸数组两种形态。回归同上，回退后 1 项失败 |

同时删除 `MultiModelAgent.process` 中第二处 `if task_type is None` 死分支：首个同条件块已赋值，该分支恒不执行（HEAD 版本覆盖率上限 97.84%，删除后可达 100%）。

覆盖率变化（`--cov=app --cov-branch`，unit + integration）：`72.00% → 72.29%`，覆盖行 47703 → 47891，语句总数 63693 → 63695，覆盖分支 12948 → 13011，新增 42 个用例（`6336 → 6378 passed`）。`multi_model_agent.py` 10.07% → 100.00%，`model_adapter.py` 15.79% → 100.00%。

### 后端缺陷扫描第十九轮：错误恢复契约与围栏解析缺陷（2026-11-11）

补测 `app/agent/error_recovery.py`（340 语句、46.06%、缺失 162 行），修复补测暴露的 2 处真实缺陷：

| 优先级 | 问题 | 实际位置 | 状态 |
|---|---|---|---|
| P1 | 降级链为空时返回字典缺 `success` 键：`fix_from_test_logs` 走「用户禁用/未配置降级链」早退路径时只返回 `total/fixed/failures`，调用方按统一契约读 `result["success"]` 直接 `KeyError` | `app/agent/error_recovery.py`（`fix_from_test_logs`） | 已解决；早退分支补齐 `success=False` 与 `message`。回归 `tests/unit/test_error_recovery_branches.py::test_empty_fallback_chain_returns_failure_summary`，回退后失败 |
| P2 | 外层 JSON 围栏误匹配内层代码块：` ```(?:json)?\s*([\s\S]*?)\s*``` ` 会把修复内容里的 ```python 代码块当成外层围栏，截出半截内容后 `json.loads` 失败，合法修复响应连续 3 次被判失败 | `app/agent/error_recovery.py`（`fix_from_test_logs`） | 已解决；围栏正则要求分隔符后换行、只接受 `json` 或无语言标记。回归 `test_fenced_content_is_unwrapped_before_write`，回退后失败 |

覆盖率变化（`--cov=app --cov-branch`，unit + integration）：`72.29% → 72.60%`，覆盖行 47891 → 48057，语句总数 63695 → 63697，覆盖分支 13011 → 13105，新增 61 个用例（`6378 → 6439 passed`）。`error_recovery.py` 46.06% → 98.97%（342/342 行，行覆盖 100%）。报告阶段 coverage 7.17.2 偶发报 `architect.py` AST 递归告警而漏计该文件，从同一份 `.coverage` 数据重新生成 JSON 后已包含 `architect.py`（800 语句），上表数值取自重新生成结果。

### 后端缺陷扫描第二十轮：规范解析丢规范与纯逻辑模块补测（2026-11-11）

补测 `app/utils/agent_skills.py`（176 语句、14.88%）、`app/utils/workflow/node_types/data_transform.py`（173 语句、38.10%）、`app/services/agent_memory_service.py`（129 语句、21.85%）与 `app/agent/spec_first_generator.py`（278 语句、38.13%），修复补测暴露的 1 处真实缺陷：

| 优先级 | 问题 | 实际位置 | 状态 |
|---|---|---|---|
| P1 | 返回列表首元素是无关 dict 时直接中断：`_generate_openapi_spec` 看到 `list[0]` 为 dict 就立即当作规范，后续元素里的有效 OpenAPI 对象永远扫描不到，`{"api": ...}` 之类的包裹响应会被整条丢弃 | `app/agent/spec_first_generator.py`（`_generate_openapi_spec`） | 已解决；首元素缺 `openapi` 字段时继续向后扫描，全部无命中才回退原值并返回失败。回归 `tests/unit/test_spec_first_generator_branches.py::TestOpenApiBranches::test_first_dict_without_openapi_scans_rest`，回退后失败 |

四个目标模块的最终覆盖：`agent_skills.py` 14.88% → 100.00%，`data_transform.py` 38.10% → 100.00%，`agent_memory_service.py` 21.85% → 99.34%（`304->309` 为 `update_model_stats` 先递增计数后不可达的防御性分支），`spec_first_generator.py` 38.13% → 100.00%（278/278 行、112/112 分支）。

覆盖率变化（`--cov=app --cov-branch`，unit + integration）：`72.60% → 73.46%`，覆盖行 48057 → 48549，语句总数 63697 → 63706，覆盖分支 13105 → 13350（总分支 20550 → 20556），新增 4 个测试文件共 190 项，全量 `6439 → 6628 passed, 2 skipped`。

### 后端缺陷扫描第二十一轮：关闭恢复与系统负载快照缺陷（2026-11-11）

补测 `app/core/graceful_shutdown.py`（153 语句、37.71%，此前无测试）与 `app/utils/system_load.py`（106 语句、52.34%），修复 2 处真实缺陷：

| 优先级 | 问题 | 实际位置 | 状态 |
|---|---|---|---|
| P1 | 健康感知路由取负载快照必然崩溃：`get_load_snapshot` 把 `is_draining` 当方法调用 `is_draining()`，而它是属性，稳定抛 `TypeError: 'bool' object is not callable`；`dynamic_model_router` 在 `enable_health_aware_routing` 开启时每轮路由都会走到这里 | `app/utils/system_load.py`（`get_load_snapshot`） | 已解决；改为直接读取属性。回归 `tests/unit/test_system_load.py::TestSnapshot::test_is_draining_property_is_not_called`，回退后 `TypeError` |
| P2 | `SIG_DFL` 原处理器无法还原：`restore_signal_handlers` 用真值判断 `if self._original_sigterm_handler:`，而 `signal.SIG_DFL` 等于 0，导致原本为「默认处理」的处理器恢复被静默跳过 | `app/core/graceful_shutdown.py`（`restore_signal_handlers`） | 已解决；改为 `is not None`。回归 `tests/unit/test_graceful_shutdown.py::TestSignalHandlers::test_restore_sigterm_with_default_handler`，回退后失败 |

覆盖率变化（`--cov=app --cov-branch`，unit + integration）：`73.46% → 73.66%`，覆盖行 48549 → 48687，语句总数 63706 不变，覆盖分支 13350 → 13384（总分支 20556 不变），新增 2 个测试文件共 67 项，全量 `6628 → 6692 passed, 2 skipped`。`graceful_shutdown.py` 37.71% → 100.00%（153/153 行、22/22 分支），`system_load.py` 52.34% → 100.00%（106/106 行、22/22 分支）。

### 后端缺陷扫描第二十二轮：文件节点必需参数契约不一致（2026-11-11）

补测 `app/utils/workflow/node_types/file_processing.py`（94 语句、38.10%，此前仅 2 个零散用例），修复 1 处真实缺陷：

| 优先级 | 问题 | 实际位置 | 状态 |
|---|---|---|---|
| P1 | `copy`/`move` 的必需参数声明与实际校验不一致：`get_required_params()` 对所有非 `read` 操作返回 `["path"]`，而 `validate_params()` 要求 `source`/`destination`；依赖声明做参数提示或前置校验的调用方会拿到错误的 `path` 字段，永远提示不到真正缺失的键 | `app/utils/workflow/node_types/file_processing.py`（`get_required_params`） | 已解决；`copy`/`move` 返回 `["source", "destination"]`，其余操作仍返回 `["path"]`。回归 `tests/unit/test_file_processing_node.py::TestParamsContract::test_copy_and_move_require_source_and_destination`，回退后失败 |

覆盖率变化（`--cov=app --cov-branch`，unit + integration）：`73.66% → 73.79%`，覆盖行 48687 → 48766，语句总数 63706 不变，覆盖分支 13384 → 13415（总分支 20556 不变），新增 1 个测试文件 36 项，全量 `6692 → 6728 passed, 2 skipped`。`file_processing.py` 38.10% → 99.21%（94/94 行；`73->82` 分支不可达，operation 白名单已排除未覆盖的 else 路径）。报告阶段 coverage 7.17.2 本轮改为漏计 `app/agent/adapters/python.py`（392 语句），从同一份 `.coverage` 重新生成 JSON 后已恢复计入，上表数值取自重新生成结果。

### 后端缺陷扫描第二十三轮：Python 服务临时名称取错路径段（2026-11-11）

补测 `app/utils/service_config_manager.py`（103 语句、37.98%），修复 1 处真实缺陷：

| 优先级 | 问题 | 实际位置 | 状态 |
|---|---|---|---|
| P1 | Python 服务临时名称取首个路径段：正则 `/([\w-]+)/` 命中紧邻根目录的一段，`/var/www/app/main.py` 得到「Python应用:var」、`/srv/my-app/main.py` 得到「Python应用:srv」，真正项目目录永远显示不出来；Windows 反斜杠路径完全不匹配，回退成 `python:8000` | `app/utils/service_config_manager.py`（`_generate_temp_name`） | 已解决；改为匹配脚本名之前的最后一段目录（`[\\/]([\w-]+)[\\/][^\\/]+$`），同时接受正反斜杠。回归 `tests/unit/test_service_config_manager.py::TestGetOrCreate` 中 3 项路径用例，回退后全部失败 |

覆盖率变化（`--cov=app --cov-branch`，unit + integration）：`73.79% → 73.89%`，覆盖行 48766 → 48825，语句总数 63706 不变，覆盖分支 13415 → 13432（总分支 20556 不变），新增 1 个测试文件 30 项，全量 `6728 → 6758 passed, 2 skipped`。`service_config_manager.py` 37.98% → 100.00%（103/103 行、26/26 分支）。

### 后端缺陷扫描第二十四轮：代码审查非字符串响应二次崩溃（2026-11-11）

补测 `app/agent/code_reviewer.py`（80 语句、38.60%），修复 1 处真实缺陷：

| 优先级 | 问题 | 实际位置 | 状态 |
|---|---|---|---|
| P1 | LLM 返回非字符串时审查流程二次崩溃：`review_code` 捕获 `TypeError` 后，异常处理分支里的 `response[:200]` 对 `None`/对象再次做切片，直接抛 `TypeError: 'NoneType' object is not subscriptable`；原本应降级为「需人工审查」，实际整个审查调用失败 | `app/agent/code_reviewer.py`（`review_code`） | 已解决；日志改用 `str(response)[:200]`。回归 `tests/unit/test_code_reviewer_branches.py::TestReviewResultParsing::test_non_string_response_requests_manual_review`，回退后抛 `TypeError` |

覆盖率变化（`--cov=app --cov-branch`，unit + integration）：`73.89% → 73.98%`，覆盖行 48825 → 48872，语句总数 63706 不变，覆盖分支 13432 → 13462（总分支 20556 不变），新增 1 个测试文件 19 项，全量 `6758 → 6777 passed, 2 skipped`。`code_reviewer.py` 38.60% → 100.00%（80/80 行、34/34 分支）。

### 后端缺陷扫描第二十五轮：中文页码退化为全部页（2026-11-11）

补测 `app/utils/pptx/visual_modifier.py`（90 语句、21.67%）与 `app/utils/pptx/modify_intent_parser.py`（146 语句），修复 1 处真实缺陷：

| 优先级 | 问题 | 实际位置 | 状态 |
|---|---|---|---|
| P1 | 中文页码被当成「所有页」：模块文档与错误提示示例都写「修改第三页的字体为微软雅黑」，但 `SLIDE_PATTERNS` 只匹配 `\d+`，中文数字页码解析结果为空，`parse` 走无页码分支生成 `slide_number=None`，`PPTModifier` 随即把字体/颜色改动应用到整份 PPT。用户明确要求改单页时会被全量改写 | `app/utils/pptx/modify_intent_parser.py`（`_extract_slide_numbers`） | 已解决；新增中文数字页码匹配与 `_chinese_to_int` 换算（覆盖一到九百九十九，支持「十」「十二」「二十」「一百零二」）。回归 `tests/unit/test_ppt_modify_intent_parser.py::TestModifyIntentParser::test_parse_slide_number_chinese_numerals` 与 `test_parse_slide_number_chinese_ten_forms`，回退后 3 项失败 |

覆盖率变化（`--cov=app --cov-branch`，unit + integration）：`73.98% → 74.10%`，覆盖行 48872 → 48958，语句总数 63706 → 63727，覆盖分支 13462 → 13504（总分支 20556 → 20566），新增 1 个测试文件 `test_visual_modifier.py`（21 项）并在既有解析器测试补 4 项，全量 `6777 → 6804 passed, 2 skipped`。`visual_modifier.py` 21.67% → 100.00%（90/90 行、30/30 分支），`modify_intent_parser.py` → 100.00%（146/146 行、72/72 分支）。

### 后端缺陷扫描第二十六轮：缓存淘汰重复删除崩溃（2026-11-11）

补测 `app/agent/fix_pattern_cache.py`（159 语句、45.32%，此前仅反模式判定被判过）与 `app/agent/strategy_evaluator.py`（158 语句、41.74%，此前仅数据类默认值被判过），修复 1 处真实缺陷：

| 优先级 | 问题 | 实际位置 | 状态 |
|---|---|---|---|
| P1 | 同一条目同时触发过期归档与容量淘汰时抛 `KeyError`：`_apply_decay_and_cleanup` 先把超过 60 天未命中的签名加入删除列表，容量超限时又把同一批低优先级条目追加进去，随后逐条 `del self.patterns[signature]`，第二次删除命中已删键直接崩溃；调用点 `add_pattern`/`update_pattern_success` 都没有捕获，写入失败会让本轮修复模式登记整体中断 | `app/agent/fix_pattern_cache.py`（`_apply_decay_and_cleanup`） | 已解决；删除前用 `dict.fromkeys` 对删除列表去重，日志按去重后数量统计。回归 `tests/unit/test_fix_pattern_cache.py::TestDecayAndCleanup::test_expired_entry_also_evicted_by_capacity_is_safe`，回退后抛 `KeyError: 'expired'` |

覆盖率变化（`--cov=app --cov-branch`，unit + integration）：`74.10% → 74.38%`，覆盖行 48958 → 49112，语句总数 63727 不变，覆盖分支 13504 → 13588（总分支 20566 不变），新增 2 个测试文件共 69 项，全量 `6804 → 6866 passed, 2 skipped`。`fix_pattern_cache.py` 45.32% → 100.00%（159/159 行、44/44 分支），`strategy_evaluator.py` 41.74% → 100.00%（158/158 行、60/60 分支）。

### 后端缺陷扫描第二十七轮：项目级审查语言分派失效（2026-11-11）

补测 `app/utils/review/code_review_agent.py`（153 语句、39.72%）与 `app/core/file_validator.py`（158 语句、48.39%），修复 1 处真实缺陷：

| 优先级 | 问题 | 实际位置 | 状态 |
|---|---|---|---|
| P1 | 项目级审查从不执行 Python/JS 规则：`get_review_report` 用 `ext[2:]` 得到 `py`、`js`、`ts`、`jsx`、`tsx` 传给 `review_file`，而分派只接受 `python`/`javascript`，全部落到通用检查；`eval`、硬编码密码、SQL 拼接、`console.log`、无障碍等规则在整项目审查中完全失效 | `app/utils/review/code_review_agent.py`（`review_file`） | 已解决；分派时小写归一化并接受 `py`/`js`/`ts`/`jsx`/`tsx` 别名。回归 `tests/unit/test_code_review_agent_branches.py::TestReport::test_project_report_uses_language_specific_rules` 等 10 项，回退后失败 |

覆盖率变化（`--cov=app --cov-branch`，unit + integration）：`74.38% → 74.69%`，覆盖行 49112 → 49266，语句总数 63727 → 63728，覆盖分支 13588 → 13692（总分支 20566 不变），新增 2 个测试文件共 123 项，全量 `6866 → 6987 passed, 2 skipped`。`code_review_agent.py` 39.72% → 100.00%（153/153 行、62/62 分支），`file_validator.py` 48.39% → 100.00%（158/158 行、90/90 分支）。报告阶段 coverage 7.17.2 抛 `SystemError: AST constructor recursion depth mismatch` 未写出 JSON，从同一份 `.coverage` 重新生成后取得上表数值。

### 后端缺陷扫描第二十八轮：任务快照缺失导致执行协程崩溃（2026-11-11）

补测 `app/utils/image_generation.py`（192 语句、36.78%）与 `app/utils/task_manager.py`（207 语句、55.98%），修复 1 处真实缺陷：

| 优先级 | 问题 | 实际位置 | 状态 |
|---|---|---|---|
| P1 | 任务快照缺失时执行协程崩溃：`_execute_task` 从 Redis 和内存都取不到任务（创建时 Redis 故障只写内存、Redis 恢复后内存快照被清理，或清理任务与执行并发），`task_info` 为 `None`，首个 `_update_status` 执行 `task_info["status"] = ...` 抛 `TypeError`；该异常又被外层 `except Exception` 捕获后再次调用 `_update_status`，二次抛错逃出协程，后台 asyncio 任务以 `Task exception was never retrieved` 结束，任务状态永久停留在初始值 | `app/utils/task_manager.py`（`_execute_task`） | 已解决；取不到快照时记录 `任务状态不存在，跳过执行` 并移除运行中条目后直接返回。回归 `tests/unit/test_task_manager_branches.py::TestExecuteTask::test_missing_task_info_does_not_crash`，回退后抛 `TypeError: 'NoneType' object does not support item assignment` |

覆盖率变化（`--cov=app --cov-branch`，unit + integration）：`74.69% → 75.01%`，覆盖行 49266 → 49470，语句总数 63728 → 63731，覆盖分支 13692 → 13760（总分支 20566 不变），新增 2 个测试文件共 93 项，全量 `6987 → 7080 passed, 2 skipped`。`image_generation.py` 36.78% → 100.00%（192/192 行、50/50 分支），`task_manager.py` 55.98% → 100.00%（210/210 行、52/52 分支）。

### 后端缺陷扫描第二十九轮：错误恢复为空时生成结果组装崩溃（2026-11-11）

补测 `app/agent/orchestrator_generation/traditional_generate.py`（206 语句、21.28%）与 `app/api/v2/Controller.py`（151 语句、12.71%），修复 1 处真实缺陷：

| 优先级 | 问题 | 实际位置 | 状态 |
|---|---|---|---|
| P1 | `fix_attempts` 的 `if` 保护失效：推导式写成 `for h in self.error_recovery.fix_history if self.error_recovery`，可迭代对象先于条件求值，`error_recovery` 为 `None`（未启用错误恢复、初始化失败或精简调用路径）时直接抛 `AttributeError: 'NoneType' object has no attribute 'fix_history'`。此时文件已全部生成、验证已完成，仅结果字典组装失败，整次生成以异常收场，已写盘产物与成功状态一并丢失 | `app/agent/orchestrator_generation/traditional_generate.py`（`_generate_traditional` 返回值） | 已解决；条件表达式改为 `self.error_recovery.fix_history if self.error_recovery else []`。回归 `tests/unit/test_traditional_generate_branches.py::TestDegradedPaths` 等 17 项，回退后全部失败并抛该 `AttributeError` |

覆盖率变化（`--cov=app --cov-branch`，unit + integration）：`75.01% → 75.46%`，覆盖行 49470 → 49756，语句总数 63731 不变，覆盖分支 13760 → 13858（总分支 20566 不变），新增 2 个测试文件共 58 项，全量 `7080 → 7138 passed, 2 skipped`。`traditional_generate.py` 21.28% → 100.00%（206/206 行、76/76 分支），`Controller.py` 12.71% → 100.00%（151/151 行、30/30 分支）。

### 后端缺陷扫描第三十轮：依赖升级、路径与状态收敛批次（2026-11-12）

本轮以覆盖率为线索逐个模块做缺陷复核，覆盖 API、Agent 编排、工具链与 PPT 服务，修复 18 处真实缺陷（2 处安全类、4 处 500/崩溃类、12 处功能与死代码类）：

| 优先级 | 问题 | 实际位置 | 状态 |
|---|---|---|---|
| P1 | `inpaint` 的 mask 权限校验被嵌在 `if not uploaded_temp_paths:` 内：multipart 上传原图后该条件为假，mask 路径完全跳过归属校验，可读取并使用他人文件 | `app/api/v1/kolors_api.py`（`inpaint_api`） | 已解决；mask 校验提升到上传分支之外，仅保留“上传文件本身免校验”。回归 `tests/unit/test_kolors_api_branches.py` |
| P1 | 图片缓存文件名直接拼接检索词，`../../escape` 一类关键词可把文件写到缓存目录之外 | `app/utils/visual/image_manager.py`（`_save_image_bytes`） | 已解决；关键词按字母数字与 ` -_` 白名单清洗并截断 40 字符，空串回退 `image`。回归 `tests/unit/test_image_manager_branches.py::test_save_image_bytes_sanitizes_keyword_path` |
| P1 | `delete_user_upload` 对 `project_name="."` 解析后等于用户上传根目录，`is_relative_to` 对相等路径返回真，删除操作会清空该用户全部上传项目 | `app/api/v1/AiProjectCode.py`（`delete_user_upload`） | 已解决；拒绝 `.`/`..`，并在 `is_relative_to` 之外显式拒绝 `target_dir == user_uploads_base`。回归 `tests/unit/test_ai_project_code_branches.py` |
| P1 | `ProbabilitySampler` 在 opentelemetry-sdk 1.29 已移除，import 失败被外层 `except ImportError` 当作“包未安装”吞掉，追踪整体静默禁用 | `app/agent/tracing.py`（provider 初始化） | 已解决；新增 `_make_sampler`，优先 `ParentBasedTraceIdRatio`，旧版回退 `ProbabilitySampler`。回归 `tests/unit/test_tracing_branches.py`（含模块重载用例） |
| P1 | `create_project_file` 的锁清理写在 `async with lock` 块内的 `finally`，此时锁仍被持有，`locked()` 恒为真，锁永不删除；并发写同一路径会持续累积 `asyncio.Lock` | `app/utils/agent_core.py`（`create_project_file`） | 已解决；`try/finally` 移到 `async with` 之外，并校验字典中的锁对象仍是当前实例后再删除。回归 `tests/unit/test_agent_core_branches.py` |
| P1 | `create_project_file` 工具调用的 `arguments` 常为 JSON 字符串，直接 `.get()` 抛 `AttributeError`，参数校验尚未执行就中断整轮生成 | `app/utils/agent_core.py`（`ProjectGeneratorAgent` 工具分派） | 已解决；字符串先 `json.loads` 并校验为 dict，非字符串 `file_path` 交给后续 pydantic 校验。回归 `tests/unit/test_agent_core_generate_branches.py` |
| P2 | 会话搜索评分正则 `\{[^{}]*"scores"[^{}]*\}` 无法跨过内层花括号，提示词要求的 `{"scores": {...}}` 恒解析失败，全部相关性分数被丢弃 | `app/api/v1/ai_agent/orchestrate_endpoints.py`（`search_sessions`） | 已解决；先整体 `json.loads`，失败再退化为贪婪正则，两层都校验 dict 形状。回归 `tests/unit/test_orchestrate_endpoints_branches.py::test_search_sessions_scores_and_sorts` |
| P2 | 同步 PDF 返回 `preview_url=None`，而响应模型声明 `preview_url: str`，pydantic 校验失败使成功生成变成 500 | `app/api/v1/aiGeneratorPptx.py`（`PPTGenerationResponse`） | 已解决；改为 `Optional[str] = None`。回归 `tests/unit/test_ppt_api_extra_branches.py` |
| P2 | `SyncResponse.message` 为必填，同步失败分支只传 `count`/`error`，失败路径本身抛响应校验错误 | `app/api/v1/providers.py`（`sync_models`） | 已解决；失败分支补齐 `message`。回归 `tests/unit/test_providers_api_branches.py::test_sync_failure_records_error` |
| P2 | 导入工作流执行从未把记录置为 running，记录状态永久停留在初始值；客户端断开后执行任务继续运行，done 回调还会覆盖记录状态 | `app/api/v1/workflow.py`（`execute_imported_workflow`） | 已解决；加锁标记 running，`add_done_callback` 只更新仍属于当前执行器的记录，generator 关闭时取消 executor 与任务。回归 `tests/unit/test_workflow_api_branches.py` |
| P2 | `close_http_client` 在客户端已关闭时跳过清空，模块继续持有失效实例；后续复用会拿到已关闭连接池 | `app/utils/aicloud/http_client.py`（`close_http_client`） | 已解决；无论是否已关闭都清空实例与事件循环引用。回归 `tests/unit/test_aicloud_http_client_branches.py` |
| P2 | `context_lengths` 为 `None` 时先归一化为 `{}` 再入参，但日志仍对原始参数取 `keys()`，抛 `AttributeError` 使配置更新在保存后失败 | `app/services/apikey_manager.py`（`update_context_lengths`） | 已解决；日志改用已归一化的 `meta.context_lengths`。回归 `tests/unit/test_apikey_manager_branches.py` |
| P3 | `bool` 是 `int` 子类，`isinstance(var_value, int)` 先命中，布尔分支永远不可达；布尔变量与字符串比较被按整数解析 | `app/utils/workflow/node_types/conditional.py`（`_coerce_compare_value`） | 已解决；布尔判断前置。回归 `tests/unit/test_workflow_node_types_branches.py::test_int_float_bool_convert` |
| P3 | 备份列表只匹配 `*.backup` 后缀，实际部署产物 `app.conf.backup.YYYYMMDD_HHMMSS` 全部不可见 | `app/api/v2/nginx_api.py`（`list_backups`） | 已解决；改为名字含 `.backup`。回归 `tests/unit/test_nginx_api_branches.py` |
| P3 | `#include`/`#import` 被注释过滤规则吞掉，C/C++ 依赖图缺失；`from pkg import x` 先被裸 import 规则命中，模块名取成 `x` | `app/agent/adapters/generic.py`（`parse_imports`） | 已解决；预处理指令排除在注释之外，`from ... import` 规则前置。回归 `tests/unit/test_generic_adapter_branches.py` |
| P3 | Rust `use core::mem` 的路径分隔符未参与标准库判定，`core`/`std` 前缀漏判；带返回类型标注或 `:` 的通用函数声明无法识别 | `app/agent/adapters/generic.py`（`_looks_like_stdlib`/`extract_definitions`） | 已解决；先按 `::` 切分，函数声明正则加入 `:` 结尾。回归 `tests/unit/test_generic_adapter_branches.py` |
| P3 | 前端文件类型推断只认 `.js/.ts/.jsx/.tsx`，`.mjs`/`.cjs`/`.vue`/`.svelte` 一律归为 unknown | `app/agent/frontend_engineer.py`（`_infer_file_type`） | 已解决；扩展名集合补齐。回归 `tests/unit/test_frontend_engineer_branches.py` |
| P3 | 用户偏好提取丢弃超过 100 字符的值，长偏好被静默忽略 | `app/api/v1/GirlAi.py`（`_extract_user_preferences`） | 已解决；保留完整值。回归 `tests/unit/test_girlai_api_branches.py` |

死代码清理（覆盖率复核中确认不可达或重复，删除后行为不变）：`app/utils/json_parser.py` 的 `_looks_like_json_array`（平衡括号定位后字符串必然以 `[` 开头、以 `]` 结尾）、`app/api/v1/AiProjectCode.py` 的隐藏文件二次判断（外层已按路径段过滤）与 `avg_execution_time` 的 `total_requests > 0` 守卫（自增后总数至少为 1）、`app/agent/models.py` 中位于首个 REASONING 分支之后的重复 REASONING 判断。

覆盖率变化（`--cov=app --cov=src --cov-branch`，unit + integration）：`83.41% → 88.54%`，覆盖行 54679 → 57598，语句总数 63775 不变，覆盖分支 15676 → 17087（总分支 20578 不变），新增 67 个测试文件共 1472 项，全量 `8752 → 10224 passed, 2 skipped, 0 failed`。本轮重点模块：`tracing.py` 63.07% → 100.00%，`consistency_checker.py` 52.29% → 100.00%，`github_remote.py` 52.63% → 100.00%，`resource_config.py` 53.57% → 100.00%，`conditional.py` 54.29% → 100.00%，`llm_call.py` 52.89% → 100.00%，`http_request.py` 55.84% → 100.00%，`orchestrator_files.py` 79.37% → 100.00%，`session_manager.py` 60.31% → 100.00%，`ppt_state_service.py` 69.43% → 100.00%，`aiGeneratorPptx.py` 59.93% → 96.67%，`agent/utils.py` 69.81% → 99.64%，`web_search.py` 74.12% → 99.30%，`incremental_modify.py` 62.96% → 99.83%，`dynamic_model_router.py` 73.58% → 99.23%。

新增测试暴露并修复了一处测试间污染：`test_dynamic_model_router_branches.py` 的非 `monkeypatch` 断言依赖模块级 `MODEL_ID_TO_KEY`/`MODEL_PROVIDER_MAP` 缓存，测试结束后未还原，导致后续成本用例读到空映射、单价为 0。该文件已加 autouse fixture 保存并还原五个模块级映射全局，合跑 `107 passed`。

### 后端缺陷扫描第三十一轮：编排容错与评估链路收敛批次（2026-11-12）

本轮继续以覆盖率为线索逐个模块复核，覆盖 Agent 编排、语言适配、PPT 任务与工具链，修复 5 处真实缺陷（4 处崩溃/状态类、1 处评估链路不可达）：

| 优先级 | 问题 | 实际位置 | 状态 |
|---|---|---|---|
| P1 | 拓扑调度就绪队列存在竞态：`qsize() > 0` 之后 `get_nowait()` 可能先被其他协程取空，`asyncio.wait(self._running_tasks)` 对空集合直接抛 `ValueError`，整轮拓扑调度以异常结束 | `app/agent/topology_scheduler.py`（`run` 主循环） | 已解决；等待前检查 `_running_tasks` 是否为空，空则让出一次事件循环后重试。回归 `tests/unit/test_topology_scheduler_branches.py`，回退后抛 `ValueError: Set of Tasks/Futures is empty` |
| P1 | `ReActEngine` 在两处返回点调用 `_build_final_result(task)` 漏掉 `await`，协程对象被直接当作最终结果返回，调用方拿到 coroutine 而非结果字典，序列化或字段访问时崩溃并触发 `coroutine was never awaited` | `app/agent/react_engine.py`（`run` 正常结束、`_should_stop` 早停分支） | 已解决；两处补齐 `await`。回归 `tests/unit/test_react_engine_branches.py`，回退后断言失败 |
| P1 | 流式用量统计把上游 chunk 的 `data` 反序列化后直接当 dict 使用，`choices`/字符串/数组形态的合法 SSE 负载会命中 `AttributeError: ... has no attribute 'get'`，整条流式响应中断 | `app/utils/aicloud/llm_caller.py`（`_stream_usage_tokens`） | 已解决；反序列化结果非 dict 时按 0 token 返回。回归 `tests/unit/test_llm_caller_branches.py` |
| P2 | `GenerationScheduler` 的失败诊断使用 `str(exc)` 直接构造 `ArtifactDiagnostic.message`，而该字段有 pydantic `min_length=1`；部分异常（如 `TimeoutError()`、`RuntimeError()`）的字符串表示为空，诊断构造再次抛 `ValidationError`，掩盖原始失败原因并使节点状态停在中间态 | `app/agent/orchestration/generation_scheduler.py`（节点失败分支） | 已解决；消息为空时回退到异常类名，同时统一 `code` 的默认值。回归 `tests/unit/test_orchestration_generation_scheduler_branches.py`，回退后抛 `ValidationError` |
| P2 | `DynamicPackageManager._ai_evaluate_package` 的 prompt 是 f-string，但正文包含未转义的 JSON 示例花括号，格式化阶段就抛 `ValueError: Invalid format specifier`，LLM 安全评估从未真正调用，且被外层 `except Exception` 静默降级为启发式评估 | `app/utils/dynamic_package_manager.py`（`_ai_evaluate_package`） | 已解决；JSON 示例花括号转义为 `{{`/`}}`。回归 `tests/unit/test_dynamic_package_manager_branches.py`，回退后 4 项失败 |

另有契约收敛一处：`IntegrityValidator` 在无适配器时回退分支仍通过 `self.language_adapter.extensions` / `get_package_init_file` 取值，而该分支的成立前提正是适配器缺失，等价于把 `None` 当适配器用；现统一收敛为 Python 约定（`.py`、包内模块前缀）。回归 `tests/unit/test_integrity_validator_branches.py`。

覆盖率变化（`--cov=app --cov=src --cov-branch`，unit + integration）：`88.54% → 91.42%`，覆盖行 57598 → 59153，语句总数 63775 → 63778，覆盖分支 17087 → 17962（总分支 20578 不变），新增 27 个测试文件共 1182 项，全量 `10224 → 11406 passed, 2 skipped, 0 failed`。本轮重点模块：`topology_scheduler.py` 66.49% → 100.00%，`integrity_validator.py` 65.95% → 100.00%，`react_engine.py` 75.62% → 100.00%，`llm_caller.py` 78.53% → 100.00%，`agent_host.py` 84.14% → 100.00%，`skill_registry.py` 53.80% → 100.00%，`ppt_tasks.py` 56.74% → 100.00%，`custom_skill_manager.py` 60.53% → 100.00%，`dynamic_package_manager.py` 65.84% → 100.00%，`pptx/templates/base.py` 58.52% → 100.00%，`code_patcher.py` 77.17% → 99.75%，`synthesis_validation.py` 87.72% → 100.00%，`api_contract_checker.py` 85.90% → 99.74%，`boilerplate.py` 74.23% → 99.74%。

全部修复均按备份法完成反向验证（`/tmp/opencode/vbak_r31/` 保存修改后源码，`git show HEAD:<path>` 回退后先确认回归用例失败，再恢复）。`chat_archiver.py`（98.59%）、`log_archiver.py`（98.12%）剩余缺失为循环回边与循环后不可达兜底；`json_parser.py`（99.53%）剩余 1 行为 `raw_decode` 从 `{` 起必得 dict 的不可达防护。

### 后端缺陷扫描第三十二轮：测试隔离与静态资源分支批次（2026-11-12）

本轮以覆盖率为线索复核 `spec_first_generate`、文档/PPT 工具链、容器编排、任务队列与 API 端点，修复 3 处真实缺陷（2 处运行期崩溃、1 处配置兼容），并标注 1 处不可达回退：

| 优先级 | 问题 | 实际位置 | 状态 |
|---|---|---|---|
| P1 | `TextAnalyzer.analyze_text_density("")` 的空返回字典缺少 `chinese_count`/`ascii_count`/`effective_length` 三个键，而分栏与截断路径按固定键名取值，空文本一旦进入布局优化即抛 `KeyError: 'effective_length'` | `app/utils/pptx/layout_engine.py`（`TextAnalyzer.analyze_text_density`） | 已解决；空返回补齐全部键并归零。回归 `tests/unit/test_pptx_layout_engine_branches.py`，回退后 3 项失败 |
| P1 | `LayoutOptimizer.optimize_slide_content` / `optimize_whitespace` 只支持模板配置对象，传入等价的 dict 时 `getattr(dict, 'title_size', 24)` 恒取默认值，用户配置的标题字号、行距、边距全部静默失效 | `app/utils/pptx/layout_engine.py`（`LayoutOptimizer` 配置读取） | 已解决；统一 `get_cfg` 同时支持 dict 与对象。回归 `tests/unit/test_pptx_layout_engine_branches.py::test_optimize_slide_content_dict_config_branch` |
| P2 | `optimize_whitespace` 用 `'title' in optimized` 判断区域存在性，标题为字符串、正文为字符串（跳过内容优化后的原始值）时按 dict 下标访问 `optimized['title']['font_size']` 抛 `TypeError` | `app/utils/pptx/layout_engine.py`（`optimize_whitespace`） | 已解决；改为 `isinstance(..., dict)`。回归 `tests/unit/test_pptx_layout_engine_branches.py::test_optimize_whitespace_non_dict_layout_and_parts` |
| P2 | `SlideRenderer` 的图像文字版式回退分支不可达：外层已保证 `has_text`/`has_image` 同时成立且两列表非空，最后的裸 `"image_text"` 属于兜底死代码 | `app/utils/pptx/slide_renderer.py`（版式判定末尾） | 已标注 `# pragma: no cover`，行为不变。回归 `tests/unit/test_pptx_slide_renderer_branches.py` |

本轮同时修正两处测试自身的环境隔离缺陷，避免全量跑批时串扰：`test_resource_guard_branches.py` 的 `get_resource_status` 用例只打桩了 `psutil`，仍读取真实 `os.getloadavg()`，高负载机器上并发档位从 4 降到 3；`test_service_container_manager_branches.py` 直接 `monkeypatch.setattr(scm.time, "time", ...)`，改动的是进程级 `time` 模块，日志记录时间戳会消耗有限迭代器，使健康检查循环提前结束。两处分别改为打桩 `rg.os.getloadavg` 与用 `SimpleNamespace` 替换模块级 `time` 引用。

覆盖率变化（`--cov=app --cov=src --cov-branch`，unit + integration）：`91.42% → 94.22%`，覆盖行 59153 → 60858，语句总数 63778 → 63767，覆盖分支 17962 → 18603（总分支 20578 → 20568）。本轮新增 15 个测试文件、508 个 test 函数定义（含 batch 1 的 `test_spec_first_generate_branches2.py` 149 个与本批 14 个文件的 359 个；参数化展开后全量通过数 +520），全量 `11406 → 11926 passed, 2 skipped, 0 failed`。本轮重点模块：`file_upload.py` 77.20% → 100.00%，`main.py` 71.00% → 99.61%，`task_queue.py` 71.81% → 100.00%，`user_manage.py` 63.21% → 100.00%，`git_operations.py` 66.22% → 100.00%，`process_guard.py` 66.24% → 100.00%，`pptx/layout_engine.py` 64.67% → 100.00%，`pptx/visual_analyzer.py` 31.85% → 100.00%，`pptx/slide_renderer.py` 70.62% → 100.00%，`pptx/animation_engine.py` 68.03% → 100.00%，`aicloud/code_executor.py` 67.32% → 100.00%，`service_container_manager.py` 71.00% → 100.00%，`scaffolding/__init__.py` 68.69% → 100.00%，`dependency_graph.py` 92.45% → 98.01%，`spec_first_generate.py` 96.02%。

全部源码修复均按备份法完成反向验证（`/tmp/opencode/vbak_r32/` 保存修改后源码，`git show HEAD:<path>` 回退后先确认回归用例失败，再恢复）。剩余缺口为平台分支与不可达防御弧：`main.py` 的 `.env` 存在性/打包运行/缓存管理器真值分支（运行环境相关）、`dependency_graph.py` 的 12 处防御 `continue` 与 21 条循环/提前返回弧。`animation_engine.py` 单文件运行残余 `568->574` 循环回边，全量运行已被其他用例覆盖至 100%。

### 后端缺陷扫描第三十三轮：依赖图死代码收敛与覆盖率收口（2026-11-12）

本轮以「可覆盖性实测」复核上一轮列出的残余弧，逐条写探针确认后再处理。`dependency_graph.py` 有两处结构性死代码：`_import_to_file_path` 在 `language_adapter` 存在时已在函数前半段直接 `return None`，后半段「有适配器就用适配器包入口」的分支永远不可达；`build_from_architecture` 的第一个循环里 `if not path: continue` 也是重复防御，因为上游清理循环已把空路径从 `file_plan` 中剔除，且 `add_file` 自身对空路径直接返回。两处按最小改动收敛，行为保持不变。

| 优先级 | 问题 | 实际位置 | 状态 |
|---|---|---|---|
| P3 | 不可达的适配器包入口回退分支长期占用覆盖率缺口，掩盖真实缺口 | `app/agent/dependency_graph.py`（`_import_to_file_path`） | 已解决；删除 4 行不可达分支，改为统一的 `__init__.py` 回退。回归 `tests/unit/test_dependency_graph_branches2.py::test_import_to_file_path_without_adapter_resolves_init_and_module` |
| P3 | 重复的空路径防御 `continue` 与 `add_file` 自身判空重叠 | `app/agent/dependency_graph.py`（`build_from_architecture`） | 已解决；删除重复防御，空路径仍由 `add_file` 拦截。回归 `tests/unit/test_dependency_graph_branches2.py::test_non_list_dependency_and_import_fields_are_ignored` |
| P3 | 两处入度初始化 `if node not in in_degree` 恒真（`nodes` 与 `in_degree` 同源），属冗余分支 | `app/agent/dependency_graph.py`（`get_generation_order` / `get_generation_layers`） | 已解决；直接赋值 `in_degree[node_path] = 0`。回归同一文件拓扑排序与分层用例 |

补充的 9 项依赖图回归用例覆盖：契约图复用既有层间边、数据库→模型反向边预置后清理、无服务路径的 OpenAPI 规格、环检测删除 `dependencies` 列表项、分层排序忽略幽灵依赖、空 project_spec 跳过、空依赖摘要、类型规则拒绝成环、非 list imports。`main.py` 补 1 项 `_cache_manager is None` 的生命周期用例，消除全量运行时的跨文件状态弧。

覆盖率变化（`--cov=app --cov=src --cov-branch`，unit + integration）：`94.22% → 94.26%`，覆盖行 60858 → 60856，语句总数 63767 → 63753，覆盖分支 18603 → 18607（总分支 20568 → 20550）。全量 `11926 → 11936 passed, 2 skipped, 0 failed`。本轮目标模块：`dependency_graph.py` 98.01% → 100.00%，`main.py` 99.61% → 100.00%，`file_upload.py`、`pptx/animation_engine.py`、`scaffolding/__init__.py` 保持 100.00%。

### 后端缺陷扫描第三十四轮：PPT 长文本请求契约与生成上下文可测性（2026-11-13）

本轮以「先实测可覆盖性、再判定不可达」的方式收口 PPT 生成链路，修复 1 处真实缺陷，并把两处长期存在于闭包内的上下文拼装逻辑提取为模块级函数：

| 优先级 | 问题 | 实际位置 | 状态 |
|---|---|---|---|
| P1 | `generate_ppt_from_file` 把截断到 30000 字符的文件正文直接拼进 `topic` 再构造 `PPTGenerationRequest`，而该模型 `topic` 的 `max_length` 为 5000，长文件上传后必然返回 422，文件生成入口对真实长文档完全不可用 | `app/api/v1/aiGeneratorPptx.py`（`generate_ppt_from_file`） | 已解决；先按合法占位值构造请求，再对服务端拼装的 `topic` 赋值（赋值不触发字段校验）。回归 `tests/unit/test_ppt_api_branch_gaps.py::test_generate_from_file_truncates_long_content` 断言正文含截断提示 |
| P3 | `generate_ppt_task` 的会话历史/素材上下文拼装内嵌在任务闭包里，`TestClient` 启动的 portal 线程会让覆盖追踪对闭包后半段失效，缺口无法通过测试消除 | `app/api/v1/aiGeneratorPptx.py`（`run_ppt_generation`） | 已解决；抽出 `_build_generation_context`，端点只做一次调用与 topic 赋值，逻辑可直接单测 |
| P3 | `output_format` 的 `else` 回退在 `OutputFormat` 枚举与表单默认值共同约束下不可达；Pexels/Pixabay/Unsplash 三处 `for ... else` 的最后一次重试必然 `return`，`else` 分支永不可达；WebSocket `finally` 中 `close()` 的裸 `except` 仅在连接已断开时触发 | `app/api/v1/aiGeneratorPptx.py`、`app/utils/pptx/image_upgrader.py` | 已标注 `# pragma: no cover` 并保留原行为，静态推理确认不可覆盖 |

补测集中在三处：`aiGeneratorPptx.py` 新增取消清理、Markdown/HTML 输出、材料与历史上下文、模板与历史边界用例；`custom_template.py` 覆盖占位符几何缺失、主题字体缺失、颜色槽位缺失、兼容性评分各档位、装饰开关组合与配置合并回退；`image_upgrader.py` 覆盖缓存淘汰边界、三图源重试耗尽、质量分档位、批量生成单张失败与搜索降级链。另把 `extract_colors` 中恒真的 `len(sorted_colors) >= 1` 判断收敛为直接赋值。

覆盖率变化（`--cov=app --cov=src --cov-branch`，unit + integration）：`94.26% → 95.03%`，覆盖行 60856 → 61210，语句总数 63753 → 63742，覆盖分支 18607 → 18871（总分支 20550 → 20530）。全量 `11936 → 12173 passed, 2 skipped, 0 failed`（475.60s）。本轮目标模块：`api/v1/aiGeneratorPptx.py` 96.67% → 100.00%，`pptx/custom_template.py` 93.00% → 100.00%，`pptx/image_upgrader.py` 91.65% → 99.88%。`image_upgrader.py` 剩余 1 条弧（`731->755`）为随机图片重试循环回边，属循环结构伪影。

### 本轮逐文件验证（2026-09-27）

- 逐个测试文件独立进程运行 `tests/unit` + `tests/integration`（425 文件）：`5053 passed, 2 skipped, 0 failed`。唯一非通过文件 `tests/unit/test_agent_capabilities.py` 为脚本式文件、收集 0 用例，属 Agent 范围；跳过 2 项为 `test_dynamic_adapter.py` 标注需真实环境的流式 mock。
- 套件外逐文件补跑：`tests/frontend/test_components.py`（1 passed）、`tests/performance/test_smart_modifications.py`（4 passed）、`tests/archive/legacy/test_cache.py`（12 passed）、`tests/archive/integration_old/test_auth_api.py`（16 passed）、`tests/e2e`（`test_web_search_flow_e2e` 14 passed、`test_debug_search` 1 passed 全绿；其余失败均为平台 LLM Key 无效 `status=401` 与 DuckDuckGo 网络异常，非代码缺陷）。`tests/archive` 其余文件为损坏的遗留脚本（`IndentationError`）或脚本式文件，本就不在测试套件内。
- 服务健康：Uvicorn `:8000` 与 `/docs`、Vite `:3000` 均返回 200。

## 当前验收基线

- 后端 unit/integration：`4987 passed, 2 skipped, 0 failed`（415s，master `0c23233f` 时间点快照；测试数量随并发合入小幅增减，以 CI 为准）。此前在 `508b7f75` 测得 `4981 passed`、在 `739256d5` 测得 `4973 passed`，后者较更早的 `5022 passed` 少约 49 项，来自并发合入的 PR #326（清理零引用死代码）删除 `tests/unit/test_multi_language_parser.py`（52 个 test 定义，覆盖已删的 `app/agent/multi_language_parser.py`）及其清理的 `app/test/` 历史脚本，非测试能力退化；随后 PR #328（`fix(tasks)`）新增 8 项回到 4981，本轮删除两个零覆盖死模块未改变项数。`--cov=app` 门禁门槛 `58%`，最近一次成功汇总覆盖率 `63.92%`；本机 `make test-cov` 收尾会因工作区陈旧的 `.coverage.*` 并行数据报 `Can't combine statement coverage data with branch data`，CI 全新环境不受影响。`test_process_guard_restart` 在高负载下偶发失败，单跑 `5 passed`。
- 非 Agent 端点运行时冒烟：GET 87 个、选定变更端点 61 个（用不存在的资源 id + 空 body 探测），变更端点结果为 `404×33 / 422×22 / 200×4 / 400×2`，0 个 5xx。依赖升级后重启 Uvicorn/Celery 复跑一致：GET `200×55 / 404×22 / 422×7 / 400×2 / 503×1`（唯一 503 为 `/api/v2/Controller/admin/docker/containers` 的 Docker SDK 未安装预期降级）、变更端点 `404×33 / 422×22 / 200×4 / 400×2`，均 0 个 5xx/429。
- 可信覆盖率测量（绕开 pytest-cov 的并行碎片合并问题，用 `python3 -m coverage run --branch --source=app -m pytest tests/unit tests/integration` 单进程采集，测量于 `0c23233f`）：全部 `app` `68.76%` line / `54.90%` branch；**非 Agent `app` `67.10%` line / `49.43%` branch**（248 files / 28396 statements）；Agent 子系统 `70.12%`（34543 statements），按范围约定不计入结论。上轮文档记载的非 Agent `62.73%` 口径有误：`app/adapter/**` 仅被 `app/utils/agent_core.py` 引用，属 Agent 链，不应计入非 Agent。非 Agent 分模块：`middleware 92.51%`、`models 99.67%`、`schema 96.47%`、`celery_app 90.16%`、`services 76.18%`、`db 74.40%`、`main.py 72.17%`、`utils 67.12%`、`tasks 66.81%`、`core 64.04%`、`api 55.64%`。改进优先级最低三块：`api`、`core`、`tasks`。
- 前端全量 Vitest：`50 files / 251 passed`（47.4s）；前端覆盖率（v8，`npm run test:coverage`）`44.36% stmts / 38.68% branch / 35.48% funcs / 45.22% lines`，低位集中在 `utils/api`（19.16%）与网络凭据类工具（`crypto.js`/`encryption.js`/`auth.js`），后者主要由后端契约与 E2E 覆盖；`npm run build:budget` 成功，四项预算全部通过（依赖升级后首屏 JS 92.8/450 KiB、CSS 57.1/100 KiB、最大图 124.6/200 KiB、路由块 49.7/150 KiB，首屏增幅来自 `xlsx` 0.20.3）。
- 前端 ESLint：`0 errors / 382 warnings`（console/unused-var）。
- PPT 专项：`141 passed`；`elegant` 统一生成测试 `24 passed`。
- VS Code 扩展 Node 测试：`62 passed`，Extension Development Host E2E 已完成。
- 前端 E2E：预置规范账号（`python3 -m app.scripts.seed_users`，三个账号密码均 `12345678`）后，CI 门禁覆盖 `core`、`01-auth`、`02-core-navigation`、`11-theme-shortcuts`、`encrypted-login`、`theme-switcher`、`10-admin`、`tools`、`tools-panel`、`capability-center`、`admin-panel-scenarios`、`system-monitor`、`upload-file` 共 `98` 项；`CI=1`（单 worker + 2 次重试）下运行。所有纳入 spec 均经本机复跑确认全绿：前四批 `28 passed`（串行与默认并行各一遍），`tools-panel` `11 passed`，`admin-panel-scenarios` `2 passed`，`system-monitor` 与 `upload-file` 合计 `13 passed`（串行与默认并行各一遍）。`encrypted-login` 默认账号与种子脚本一致，此前失败纯属本地库未播种。
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
| 6 | datetime.utcnow() 无时区 | 非 Agent 全部时间列 | 迁移到 `utcnow_naive()` / `datetime.now(timezone.utc)`，按列类型配对；Agent 子系统不在范围 |
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
