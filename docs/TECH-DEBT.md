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
| P3 | `tests/e2e/` 下有大量一次性诊断脚本与依赖外部模型的在线探针，无法全部纳入 CI 门禁 | `tests/e2e/` | 部分解决；3 个零 Agent 引用的草稿探针与 1 个失效 spec 已移入 `tests/archive/playwright/`（该目录不在 `playwright.config.js` 的 `testDir` 内），当前 `tests/e2e/` 下 94 个 spec。`e2e.yml` 门禁由 5 个扩到 13 个稳定非 Agent spec：新增 `theme-switcher`/`10-admin`/`tools`/`capability-center`（串行与默认并行各跑一遍，`28 passed`），修复后复跑全绿的 `tools-panel`（11 项）与 `admin-panel-scenarios`（2 项），以及重写后复跑全绿的 `system-monitor`（7 项）与 `upload-file`（6 项）。**剩余非 Agent spec 的失败已逐条定性**：`03-chat.spec.js` 的 6 项失败为纯负载型 flaky（本机负载 7.5 时超时；负载 1.8 时 11 项全过），非产品缺陷；`tools-panel`（2 项过期工具清单选择器）、`admin-panel-scenarios`（错误断言 `模型管理` 不存在，实为 superadmin 有意保留）已修复；`system-monitor`、`upload-file` 两个「断言不存在功能」的过期 spec 已按真实功能重写并纳入门禁；`sprint-1-rbac`（17 项，断言产品未实现的高级 RBAC）已归档（详见下方说明）；2026-09-26 复核：对 5 个额外非 Agent 候选（`smoke`、`smoke-test-simple`、`auth`、`api-endpoint-validation`、`chart-editor`）与门禁 13 spec 合并串行跑得 `117 passed, 3 skipped, 0 failed`，但候选断言偏弱（`smoke` 多数 `catch` 后 `test.skip`）、`api-endpoint-validation` 内嵌大量 Agent 硬编码路由、`chart-editor` 曾在大批次 flake，故不纳入门禁 |
| P3 | `dynamic_package_manager.py` 全库零生产引用，但含「AI 评估安全性后安装包」能力，语义与 Agent 相邻 | `app/utils/dynamic_package_manager.py`、`tests/unit/test_service_dependency*.py` | 已裁定保留；判定为 Agent 相邻的预留能力，按本轮「不触碰 Agent 子系统」的范围约定保留，不计入死代码，其 3 个相关测试一并保留 |
| P2 | Alembic 与 `migrations/runner.py` 双轨并存且互相冲突 | `migrations/env.py`、`migrations/runner.py`、`migrations/versions/`、`configs/alembic.ini` | 已解决；首次接入契约收敛到 `Base.metadata`：库内无 `alembic_version` 时建全量表并登记 head、不重放历史修订，已有版本走标准迁移，空库与 runner.py 管理过的库均可 `upgrade head`。`Makefile`/`scripts/migrate.sh` 补齐 `-c configs/alembic.ini` 并修正无效的 `history -n`。补 3 项引导回归用例。残留：`versions/` 下的历史修订不再被执行（仅供已有版本库的增量），认知负担仍在 |
| P3 | 2 个 uvicorn worker + celery + scheduler 共用单个 SQLite 文件 | `docker-compose.prod.yml`、`app/db/database.py` | 已缓解；`app/db/database.py` 对 SQLite 连接统一开启 `journal_mode=WAL`、`busy_timeout=30000` 与 `connect_args timeout=30`，抑制 `database is locked`。结构性缺口仍在（单写者模型），高并发生产仍建议改用 Postgres |
| P3 | compose 的 `command` 覆盖 Dockerfile 的 `CMD`，绕过其中 `su appuser` 的非 root 启动 | `docker-compose.yml`、`docker-compose.prod.yml`、`Dockerfile` | 已解决；`docker-compose.prod.yml` 的 api/celery/scheduler 显式 `user: appuser`，Dockerfile 已 `chown -R appuser:appuser /app` 并预建全部挂载点、bind mount 源文件 644 可读。本地 `docker-compose.yml` 因 bind mount 属主保持 root 并加注释。补 2 项守卫用例。注意：既有 root 属主的 named volume 需重建或手工 `chown` |
| P3 | 生产镜像安装全量 `configs/requirements.txt`，其中 Django、Scrapy 全依赖链（Twisted/parsel/w3lib/itemadapter/itemloaders/Protego/PyDispatcher/queuelib/cssselect/Automat/constantly/hyperlink/Incremental/service-identity/zope.interface/pyasn1-modules）、Flask、Werkzeug、pandas、opencv-python 在代码中零引用，且无任何硬反向依赖 | `configs/requirements.txt`、`Dockerfile` | 待决策；已确认这些包可安全裁剪（同时消除其携带的 CVE 与镜像体积），但属生产依赖结构变更，本轮按「升级到修复版本、不裁剪包」策略保留 |
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

### 依赖安全审计与修复（2026-09-26）

对生产镜像依赖做完整漏洞审计，策略为「升级到修复版本、不裁剪包」：

| 范围 | 审计前 | 审计后 | 处置 |
|---|---|---|---|
| 后端（`configs/requirements.txt`，`pip-audit --local`） | 77 CVE / 20 包 | 1 CVE / 1 包 | 升级 19 个包：`starlette` 1.0.0→1.3.1、`cryptography` 46.0.7→50.0.0、`pillow` 12.2.0→12.3.0、`python-multipart` 0.0.28→0.0.31、`aiohttp` 3.13.5→3.14.3、`lxml` 6.0.3→6.1.0、`urllib3` 2.6.3→2.7.0、`pyOpenSSL` 26.0.0→26.4.0、`Django` 5.2.13→5.2.17、`Scrapy` 2.15.0→2.17.0、`Twisted` 25.5.0→26.4.0，以及 `anyio`/`click`/`idna`/`json_repair`/`Protego`/`pyasn1`/`pydantic-settings`/`soupsieve`/`sqlparse` 补丁级升级；`fastapi` 声明 `starlette>=0.46.0`、`requests` 允许 `urllib3<3`、`matplotlib` 允许 `pillow>=8`，均在修复版本约束内；`pip check` 无冲突 |
| 前端生产依赖 | `xlsx` 0.18.5 两个 high（Prototype Pollution `GHSA-4r6h-8v6p-xvw6` + ReDoS `GHSA-5pgg-2g8v-p4x9`，npm 无修复版本） | 0 | `xlsx` 改用 SheetJS 官方 CDN tarball `0.20.3`（`package.json` 依赖源改为 `https://cdn.sheetjs.com/xlsx-0.20.3/xlsx-0.20.3.tgz`）；仅 `src/views/ChartEditorPage.vue` 一处使用，`XLSX.read`/`utils.sheet_to_json` API 不变 |
| 前端 dev/build/test 依赖 | 8（`js-cookie`/`undici`/`brace-expansion` high，`esbuild`/`postcss-selector-parser`/`@vitest/mocker` moderate） | 9 | 均位于开发期链路（`@vue/test-utils`→`js-beautify`→`js-cookie`、`jsdom`→`undici`、`glob`/`editorconfig`→`brace-expansion`、`vite`→`esbuild`），不进生产 bundle；`npm audit fix` 受 npm 10.9.4 `Cannot read properties of null (reading 'edgesOut')` bug 阻断，未处理 |

### 非 Agent 过期 spec 处置（2026-09-26）

对上一轮定性的三个「断言不存在功能」spec 按「可重写则重写、失效则归档」处置：

| spec | 处置 | 说明 |
|---|---|---|
| `system-monitor.spec.js` | 重写 | 系统监控已迁入 AdminPanel `/admin` 默认菜单；改测真实监控看板（CPU/内存/磁盘资源卡片、网络状态、手动刷新、4 个 ECharts canvas），7 项全绿，纳入门禁 |
| `upload-file.spec.js` | 重写 | 改测首页输入区真实上传 UI（隐藏 file input、附件预览、多文件、离开上传中间态、移除附件、拖拽区），6 项全绿，纳入门禁 |
| `sprint-1-rbac.spec.js` | 归档 | 断言的高级 RBAC 能力（角色/部门/多租户/审计/2FA 等）产品未实现，移入 `tests/archive/playwright/` |

## 当前验收基线

- 后端 unit/integration 最近完整记录：`5022 passed, 2 skipped, 0 failed`（335s；2026-09-26 含依赖升级后的复核）。`--cov=app` 门禁门槛 `58%`，最近一次成功汇总覆盖率 `63.92%`；本机 `make test-cov` 收尾会因工作区陈旧的 `.coverage.*` 并行数据报 `Can't combine statement coverage data with branch data`，CI 全新环境不受影响。`test_process_guard_restart` 在高负载下偶发失败，单跑 `5 passed`。
- 非 Agent 端点运行时冒烟：GET 87 个、选定变更端点 61 个（用不存在的资源 id + 空 body 探测），变更端点结果为 `404×33 / 422×22 / 200×4 / 400×2`，0 个 5xx。依赖升级后重启 Uvicorn/Celery 复跑一致：GET `200×55 / 404×22 / 422×7 / 400×2 / 503×1`（唯一 503 为 `/api/v2/Controller/admin/docker/containers` 的 Docker SDK 未安装预期降级）、变更端点 `404×33 / 422×22 / 200×4 / 400×2`，均 0 个 5xx/429。
- 可信覆盖率测量（绕开 pytest-cov 的并行碎片合并问题，用 `python3 -m coverage run --branch --source=app -m pytest tests/unit tests/integration` 单进程采集，测量于 `750e976b`）：全部 `app` `67.99%`；**非 Agent `app` `62.73%`**（33711 statements；`app/agent/**` 29494 statements 占全部 `app` 的 46%，按范围约定不计入结论）。非 Agent 分模块：`services 75.20%`、`models 99.67%`、`schema 96.47%`、`db 74.32%`、`utils 64.84%`、`core 63.81%`、`api 55.04%`、`tasks 49.74%`、`adapter 25.45%`。改进优先级最低三块：`adapter`、`tasks`、`api`。
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
