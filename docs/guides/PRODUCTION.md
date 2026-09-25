# 生产部署指南

**最后核验**: 2026-09-23 | **适用范围**: 当前仓库实现

本文档描述仓库中已经存在的生产部署配置、运行命令和已知阻塞。配置核验范围包括 `docker-compose.yml`、`docker-compose.prod.yml`、`Dockerfile`、`configs/nginx.conf`、`src/vite.config.js`、`app/api/v1/health.py`、`configs/alembic.ini`、`configs/requirements.txt` 和 `configs/requirements-test.txt`。

## 当前结论

当前 Docker 生产链路的编排层缺口（密钥注入、数据库路径、运行期配置）、镜像层文档转换工具与 Alembic/runner.py 双轨冲突均已修复：

> 2026-09-20 更新：原第 1、2 条前端产物路径冲突已修复。`src/vite.config.js` 的 `build.outDir` 统一为 `dist`（即 `src/dist`），`app/main.py` 的 `DIST_PATH`、`Dockerfile` 的 COPY 与软链、两份 Compose、`configs/nginx.conf`、`scripts/start.sh`、`scripts/check-performance-budget.js` 与 CI 上传路径现在全部指向同一目录。

1. ~~Vite 从 `src/` 执行 `npm run build`，`src/vite.config.js` 的 `build.outDir` 是 `../dist`，因此输出目录为仓库根目录 `dist/`。~~ 已修复：输出目录改为 `src/dist`。
2. ~~`docker-compose.yml`、`docker-compose.prod.yml` 和 `configs/nginx.conf` 都使用 `src/dist`；`Dockerfile` 的前端阶段实际会生成 `/app/dist`，后续却执行 `COPY --from=frontend-builder /app/src/dist ./src/dist`。~~ 已修复：前端阶段产物即 `/app/src/dist`，COPY 与 `ln -sfn /app/src/dist /workspace/src/dist` 指向同一目录。
3. ~~两份 Compose 都向 API 设置 `ENV=production`，但没有 `env_file` 或 `SECRET_KEY` 环境项。~~ 已修复：两份 Compose 都以 `${SECRET_KEY:?...}` 强制注入 `SECRET_KEY`，未设置时编排在启动前即报错。
4. ~~两份 Compose 都没有向 API 传递 `DATABASE_URL`。~~ 已修复：两份 Compose 都以 `${DATABASE_URL:-sqlite+aiosqlite:////app/data/app.db}` 注入，默认落在 `api-data` 卷内，API 与 celery/scheduler 连接同一持久化数据库。
5. ~~`Dockerfile` 运行时只安装 `curl` 和 `nginx`，没有安装 `libreoffice-impress` 或 `poppler-utils`。~~ 已修复：镜像新增文档转换工具链层，安装 `libreoffice-impress`、`poppler-utils`、`fonts-noto-cjk`，PPT 转 PDF 与 PDF 转 PNG 预览/质量复审在容器内可用。该层使镜像增大约 0.7-1 GB。

运行期配置已补齐：两份 Compose 的 api/celery/scheduler 统一设置 `RSA_KEY_DIR=/app/keys` 并共享 `api-keys` 卷，避免各容器各自生成密钥导致密文不可互通；同时显式挂载 `data/unified_model_config.yaml`、`data/agent_model_config.yaml` 和 `configs/system_config.json`（`api-data` 空卷会遮蔽镜像内 `data/`）。`app/main.py` 在生产环境缺失这些配置文件时抛出 `RuntimeError` 拒绝启动，避免静默回退到硬编码默认模型。`Dockerfile` 另将 `configs/system_config.json` 打进镜像作为兜底。

镜像层的文档转换工具链已就位；Alembic 与 `migrations/runner.py` 的首次接入契约已收敛，见下文"数据库迁移"。

## 部署拓扑

### 基础 Compose

`docker-compose.yml` 的 `services` 实际包含 4 个服务：

| 服务 | 当前配置 |
|---|---|
| `api` | 使用 `Dockerfile` 构建；`uvicorn app.main:app --host 0.0.0.0 --port 8080 --workers 1`；宿主机绑定 `127.0.0.1:8080` |
| `celery` | 使用 `Dockerfile` 构建；Celery 并发 1；宿主机目录挂载 `./app`、`./logs` |
| `redis` | `redis:7-alpine`；宿主机绑定 `127.0.0.1:6379`；256 MB `allkeys-lru` |
| `nginx` | `nginx:alpine`；宿主机暴露 `80:80`；代理 `api:8080`；静态目录挂载为 `./src/dist:/workspace/src/dist:ro` |

基础 Compose 还定义了 `jaeger` 服务，通过 `profiles: ["observability"]` 门控，默认不启动。执行 `docker compose --profile observability up` 才会拉起，因此默认服务数为 4。

### 生产 Compose

`docker-compose.prod.yml` 的 `services` 实际包含 5 个服务：`api`、`celery`、`scheduler`、`redis`、`nginx`。

- `api` 使用 2 个 Uvicorn worker，绑定 `127.0.0.1:8080`，使用 `api-logs`、`api-data`、`api-keys`、`ppt-artifacts` 命名卷。
- `celery` 使用 1 个 worker，健康检查显式禁用，使用 `api-logs`、`api-data`、`ppt-artifacts`。
- `scheduler` 执行 `python -m app.db.scheduler_runner`，健康检查显式禁用；它使用 `api-data` 和 `api-logs`。
- `redis` 使用 AOF、256 MB `allkeys-lru` 和 `redis-data`，健康检查为 `redis-cli ping`。
- `nginx` 等待 `api` 健康后启动，暴露 `80:80`，使用 `nginx-logs`；静态目录仍挂载为 `./src/dist:/workspace/src/dist:ro`。

生产 Compose 没有 Jaeger 服务。应用的 `app/agent/tracing.py` 支持 `OTEL_ENABLED`、`OTEL_EXPORTER`、`OTEL_JAEGER_ENDPOINT` 和 OTLP 配置，默认关闭追踪；当前 Compose 没有提供 Jaeger 或 OTEL Collector，因此仅设置 `OTEL_ENABLED=1` 不能形成完整的追踪链路。

## 当前 Docker 配置

`Dockerfile` 是三阶段文件：Node 20 Alpine 前端构建、Python 3.11 slim 后端依赖、Python 3.11 slim 运行时。运行时创建 `appuser`，安装 `curl` 和 `nginx`，暴露 80、8080，并以内置命令启动 Nginx 和 2 个 Uvicorn worker（CMD 内以 `su appuser` 降权）。

两份编排的 `command` 都会覆盖该 CMD，其中的 `su appuser` 不再执行，因此非 root 启动需要编排显式声明：`docker-compose.prod.yml` 的 api/celery/scheduler 均设置 `user: appuser`。本地 `docker-compose.yml` 使用 bind mount（`./logs`、`./data`、`./uploads` 等属主为宿主用户），切到 `appuser` 会失去写权限，故保持默认 root 运行。

后端依赖来自 `configs/requirements.txt`。该文件包含 FastAPI、Uvicorn、Celery、Redis、SQLAlchemy、Alembic、OpenTelemetry、`python-pptx`、Pillow、OpenCV、Matplotlib、NumPy、Pandas、Scrapy 等依赖。它没有 `gunicorn`、`asyncpg`、`pdf2image`；文档转换能力由镜像的系统包层提供（`libreoffice-impress`、`poppler-utils`），不来自 pip。`configs/requirements-test.txt` 是测试工具补充依赖，不会被当前 Dockerfile 安装。

Dockerfile 将 `configs/alembic.ini` 复制为 `/app/alembic.ini`，同时将迁移脚本复制到 `/app/migrations`。配置内的 `script_location = %(here)s/../migrations` 在这个新位置会解析为 `/migrations`；镜像内也不存在 `/app/configs/alembic.ini`。因此要求的 `alembic -c configs/alembic.ini ...` 命令当前只能在仓库目录结构中使用，镜像内迁移路径需要部署实现修复。

Dockerfile 的前端路径关系（2026-09-20 修复后）可用以下静态关系核验：

```text
src/vite.config.js: build.outDir = dist
Dockerfile frontend-builder WORKDIR = /app/src
Vite 输出目录 = /app/src/dist
Dockerfile COPY 源 = /app/src/dist
Compose/Nginx 静态目录 = src/dist / /workspace/src/dist
```

## Docker 命令

以下命令反映仓库中的预期入口。编排层配置已修复，可在具备 Docker CLI 的主机执行：

```bash
# 构建基础镜像
docker build -t codingmatrix:latest .

# 两份 Compose 都要求显式提供 SECRET_KEY
export SECRET_KEY=$(openssl rand -hex 32)

# 启动基础 Compose
docker compose up -d

# 启动生产 Compose
docker compose -f docker-compose.prod.yml up -d
```

当前环境未安装 Docker CLI，无法在本工作区执行 `docker compose config` 或构建验证。服务数与字段来自 YAML 文件内容核验，镜像改动的守卫由 `tests/unit/test_prod_compose_consistency.py` 静态锁定。

## 非 Docker 运行

后端默认配置位于 `app/core/config.py`，默认数据库是仓库根目录的 `app.db`，默认 `REDIS_URL` 为空，默认 `ENV=development`。生产环境必须设置长度至少 16 个字符的 `SECRET_KEY`；供应商 API Key、`DATABASE_URL`、`ALLOWED_HOSTS` 和 `CORS_ORIGINS` 按实际环境设置。

安装 Python 依赖：

```bash
pip install -r configs/requirements.txt
```

前端构建命令在 `src/package.json` 中定义：

```bash
cd src
npm ci
npm run build
```

该命令按当前 Vite 配置生成 `src/dist`。`app/main.py` 的 `DIST_PATH`、Nginx 的 `/workspace/src/dist`、Compose 挂载与 CI 上传路径现已一致（2026-09-20 修复）。

启动 API 的当前仓库命令：

```bash
PYTHONPATH=/workspace python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8080
```

启动 Celery：

```bash
celery -A app.celery_app worker --loglevel=info --concurrency=1
```

启用调度器时使用：

```bash
PYTHONPATH=/workspace python3 -m app.db.scheduler_runner
```

`Makefile` 中的 `make prod` 使用 `gunicorn`，但 `configs/requirements.txt` 未声明 `gunicorn`，因此不能视为当前依赖已满足的生产命令。

## 数据库迁移

`configs/alembic.ini` 将迁移脚本定位到 `migrations/`（`script_location = %(here)s/../migrations`），`migrations/env.py` 读取统一的 `settings.DATABASE_URL`：生产由环境变量注入、本地默认仓库根 `app.db`。镜像将 ini 复制到 `/app/configs/alembic.ini`，与 `COPY migrations/ ./migrations/` 配套，因此容器内 alembic 命中与 API 相同的库。当前 Alembic 头为 `20260918_unique_tasks_task_id`。

应用启动由 `migrations/runner.py` 依据 `Base.metadata` 幂等建表并补列。`migrations/env.py` 的首次接入契约以同一份 metadata 为 schema 真相来源：

- 库内没有 `alembic_version` 时，先按 metadata 建全量表，再把版本登记为 head，不重放历史修订。从零建库的历史链本身无法自洽——起点 `56882bedb846` 是空迁移，紧随的 `a1b2c3d4e5f6_add_performance_indexes` 就假设 `user` 等基础表已存在。
- 库内已有 `alembic_version` 时走标准迁移，只执行尚未应用的新修订。

因此空库、runner.py 管理过的库、已有版本记录的库都可直接执行同一条命令：

```bash
# 建库或升级到最新
alembic -c configs/alembic.ini upgrade head

# 复核
alembic -c configs/alembic.ini current
```

`make migrate` 与 `scripts/migrate.sh` 执行同一命令，均已显式带上 `-c configs/alembic.ini`。迁移前备份实际使用的 `app.db`。

修改 schema 时须同时更新模型定义：metadata 是首次接入与 runner.py 的共同真相源，迁移链不承担从零建库。

## 健康检查端点

健康路由由 `app/main.py` 以 `/api/v1` 挂载，`app/api/v1/health.py` 内部前缀为 `/health`。Nginx 将 `/health` 代理到 `/api/v1/health`；`/api/v1/health` 由 Nginx 代理到 API。

| 端点 | 当前实现 |
|---|---|
| `GET /api/v1/health` | 快速检查数据库和 Redis；返回 `status`、UTC `timestamp`、`version`。数据库或 Redis 失败时返回 `unhealthy`，函数仍返回 HTTP 200。Redis 未配置时快速检查视为通过。`version` 与 `/health/detailed` 同源，均取自 `app.core.version.APP_VERSION`。 |
| `GET /api/v1/health/live` | 只返回 `status: alive` 和 UTC `timestamp`，不检查外部依赖。 |
| `GET /api/v1/health/ready` | 检查数据库和 Redis，并返回 `status: ready/not_ready`、`checks.database`、`checks.redis` 和 UTC `timestamp`。Redis 未配置时快速检查视为通过。 |
| `GET /api/v1/health/detailed` | 返回 `health_checker.check_all()` 结果，包含 `api`、`database`、`redis`、`celery`、`websocket`、`system` 六类检查、各项状态和整体状态。`version` 与 `/health` 同源。Celery 在 broker 不可达、inspect 抛错，或 broker 可达但无任何 worker 响应时标记为 `degraded`。 |
| `GET /api/v1/health/metrics` | 返回 `text/plain; charset=utf-8` 的自定义 Prometheus 文本；更新 API 和进程内存状态。当前源码对同步方法 `get_connection_count()` 使用 `await`，异常会被捕获并把 WebSocket 健康状态写为 0，活跃连接数不会更新。源码还创建 GC 计数器，但当前文本生成器只输出部分计数器和 gauge。 |
| `GET /api/v1/health/models` | 调用动态模型路由器的 `get_model_health_report()`，返回 `status: success`、`models`、UTC 时间戳；模型报告具体字段由动态路由器实现决定。 |

通过 Nginx 验证入口：

```bash
curl -i http://localhost/health
curl -i http://localhost/api/v1/health/live
curl -i http://localhost/api/v1/health/ready
curl -i http://localhost/api/v1/health/detailed
curl -i http://localhost/api/v1/health/metrics
curl -i http://localhost/api/v1/health/models
```

API 直连端口仅绑定本机：

```bash
curl -i http://127.0.0.1:8080/api/v1/health
```

基础健康和 ready 端点只通过响应体表达 `unhealthy` 或 `not_ready`，HTTP 状态仍为 200。Dockerfile 和生产 Compose 使用 `curl -f` 检查 `/api/v1/health`，因此数据库或 Redis 故障不会单独使容器探针失败。

## Nginx 与 Vite

`configs/nginx.conf` 使用 `/workspace/src/dist` 作为静态根目录，80 端口提供 SPA fallback；`/api/` 和 `/ws/` 代理到 `api_backend`。Compose 上游为 `api:8080`，Dockerfile 内置 Nginx 使用的本地上游为 `127.0.0.1:8080`。Nginx 设置 100 MB 请求体上限、Gzip、常见安全响应头和隐藏文件拒绝规则。

`src/vite.config.js` 的开发服务器监听 `0.0.0.0:3000`，允许 `localhost`、`127.0.0.1` 和 `.monkeycode-ai.online`，Vite `/api/v1`、`/api/v2` 代理目标是 `http://localhost:8000`。该开发代理与 Compose API 的 8080 端口属于不同运行拓扑，不能混用。

## 日志、备份与关闭

应用日志目录是 `logs/`，当前日志文件包括 `app.log`、`error.log`、`debug.log`、`process_guard.log` 和 `security.log`。Nginx 日志位于 `/var/log/nginx/access.log` 和 `/var/log/nginx/error.log`；生产 Compose 将 Nginx 日志保存到 `nginx-logs`。

生产 Compose 的持久化卷为 `api-data`、`api-keys`、`api-logs`、`ppt-artifacts`、`redis-data` 和 `nginx-logs`。API 与 celery/scheduler 的默认数据库同为 `api-data` 卷内的 `/app/data/app.db`。备份范围至少包含该数据库、`data/`、PPT 输出目录和日志。备份任务的保留周期、权限和异地副本由部署环境负责配置。

对停止写入后的仓库根目录 SQLite 数据库执行文件备份：

```bash
mkdir -p backups
BACKUP_TIMESTAMP=$(date +%Y%m%d_%H%M%S)
cp app.db "backups/app-${BACKUP_TIMESTAMP}.db"
tar -czf "backups/data-${BACKUP_TIMESTAMP}.tar.gz" data/
```

优雅关闭脚本是 `scripts/stop.sh`，脚本会停止 Celery、Gunicorn 和 Uvicorn，并清理 PID 文件。脚本包含按进程名停止的逻辑，生产环境使用前应确认进程匹配范围。

## 安全核验

- 生产环境设置强随机 `SECRET_KEY`，不要将密钥写入仓库。
- API 和 Redis 的 Compose 宿主机端口当前只绑定 `127.0.0.1`；公网入口是 Nginx 的 80 端口。
- `CORS_ORIGINS` 被传入 CORS 精确来源列表；`ALLOWED_HOSTS` 经 `Settings.cors_origin_regex` 逐项转义并锚定后作为 CORS origin 正则。应用没有注册 `TrustedHostMiddleware`，因此 `ALLOWED_HOSTS` 当前不提供独立的 Host 头校验。
- Nginx 拒绝隐藏文件、`.env`、`.git` 和 README 路径，并设置 `X-Frame-Options`、`X-Content-Type-Options`、`X-XSS-Protection`。
- 应用包含 Prompt 注入检测、速率限制、输入校验、CSRF 和敏感信息日志过滤实现，具体代码位于 `app/utils/guardrails.py`、`app/middleware/rate_limiter.py`、`app/middleware/input_validator.py`、`app/utils/csrf.py` 和 `app/core/logging_config.py`。

依赖审计命令：

```bash
pip-audit -r configs/requirements.txt
cd src
npm audit
```

TLS 终止、证书、外部防火墙和备份存储属于部署环境配置；当前仓库的 Nginx 配置只监听 HTTP 80 端口。

## 排障

确认前端实际输出目录：

```bash
test -f src/dist/index.html
```

按当前配置，构建成功后该检查应通过。

核验 Compose 服务和 schema：

```bash
docker compose config --services
docker compose -f docker-compose.prod.yml config --services
```

基础 Compose 应列出 `api`、`celery`、`redis`、`nginx` 四个服务（`jaeger` 需追加 `--profile observability`）；生产 Compose 应列出 `api`、`celery`、`scheduler`、`redis`、`nginx`。当前工作区缺少 Docker CLI，这两条命令需要在 Docker 主机执行。

查看生产服务日志：

```bash
docker compose -f docker-compose.prod.yml logs api
docker compose -f docker-compose.prod.yml logs celery
docker compose -f docker-compose.prod.yml logs scheduler
docker compose -f docker-compose.prod.yml logs nginx
```

API 启动时报 `生产环境必须设置 SECRET_KEY` 时，核对 Compose 的环境注入方案。API 启动报缺少必需配置文件时，核对 `data/` 与 `configs/` 的挂载项。健康响应体为 `unhealthy` 且容器探针仍通过时，依据 `checks` 内容判断数据库或 Redis 故障，不能只依赖 `curl -f` 的退出码。

## 已知问题清单

| 问题 | 证据 | 影响 |
|---|---|---|
| ~~前端输出目录冲突~~ | 2026-09-20 已修复：Vite、Dockerfile、Compose、Nginx、start.sh、CI 统一使用 `src/dist` | 已消除 |
| ~~镜像缺少文档转换工具~~ | 2026-09-23 已修复：镜像新增 `libreoffice-impress`、`poppler-utils`、`fonts-noto-cjk` 层 | 已消除（镜像增大约 0.7-1 GB） |
| ~~Poppler 未纳入镜像~~ | 2026-09-23 已修复：`poppler-utils` 提供 `pdftoppm`，PDF 转 PNG 有镜像级保障 | 已消除 |
| ~~Compose Jaeger 状态不完整~~ | 2026-09-23 已修复：基础文件的 `jaeger` 已是带 `profiles` 的 service，生产链路可另配 Collector | 已消除 |
| ~~基础 Compose schema 错误~~ | 2026-09-23 已修复：`jaeger` 不再出现在 `networks` 映射中 | 已消除 |
| ~~生产密钥没有注入~~ | 2026-09-23 已修复：两份 Compose 以 `${SECRET_KEY:?...}` 强制注入 | 已消除 |
| ~~SQLite 路径分裂且持久化缺失~~ | 2026-09-23 已修复：两份 Compose 注入 `DATABASE_URL`，默认落在 `api-data` 卷内 | 已消除 |
| ~~运行期模型与系统配置缺失~~ | 2026-09-23 已修复：显式挂载模型/系统配置，生产启动缺文件即报错 | 已消除 |
| ~~各容器各自生成 RSA 密钥~~ | 2026-09-23 已修复：三服务共享 `api-keys` 卷并统一 `RSA_KEY_DIR` | 已消除 |
| ~~容器内 Alembic 路径失配~~ | 2026-09-23 已修复：ini 复制到 `/app/configs/alembic.ini`，`%(here)s` 相对解析恢复为 `/app/migrations` 与 `/app` | 已消除 |
| ~~Alembic 忽略 `DATABASE_URL`~~ | 2026-09-23 已修复：`migrations/env.py` 改用 `settings.DATABASE_URL`，容器内 alembic 与 API 命中同一库 | 已消除 |
| ~~Alembic 与 runner.py 双轨冲突~~ | 2026-09-24 已修复：`migrations/env.py` 在库内无 `alembic_version` 时以 `Base.metadata` 建全量表并登记 head，已有版本走标准迁移；空库与 runner.py 管理过的库均可 `upgrade head` | 已消除（新增 3 项引导回归用例） |
| ~~运行时版本差异~~ | 已修复：`Dockerfile` 的两个 Python 阶段均基于 `python:3.11-slim`，无 Python 3.10 残留 | 已消除 |
| ~~生产服务以 root 运行~~ | 2026-09-24 已修复：`docker-compose.prod.yml` 的 api/celery/scheduler 显式 `user: appuser`，本地 compose 因 bind mount 属主保持 root 并加注释 | 已消除 |
| ~~迁移快捷命令路径不足~~ | 2026-09-24 已修复：`Makefile` 的 `migrate`/`migrate-revision` 与 `scripts/migrate.sh` 显式带上 `-c configs/alembic.ini`；脚本内 `history -n 3` 的无效参数改为 `current` | 已消除 |

本次更新核对并修复了编排层、镜像层与迁移层的遗留问题。
