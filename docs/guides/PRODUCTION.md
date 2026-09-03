# 生产部署指南

**最后核验**: 2026-09-03 | **适用范围**: 当前仓库实现

本文档描述仓库中已经存在的生产部署配置、运行命令和已知阻塞。配置核验范围包括 `docker-compose.yml`、`docker-compose.prod.yml`、`Dockerfile`、`configs/nginx.conf`、`src/vite.config.js`、`app/api/v1/health.py`、`configs/alembic.ini`、`configs/requirements.txt` 和 `configs/requirements-test.txt`。

## 当前结论

当前 Docker 生产链路存在以下关键阻塞，仓库内没有修复它们：

1. Vite 从 `src/` 执行 `npm run build`，`src/vite.config.js` 的 `build.outDir` 是 `../dist`，因此输出目录为仓库根目录 `dist/`。
2. `docker-compose.yml`、`docker-compose.prod.yml` 和 `configs/nginx.conf` 都使用 `src/dist`；`Dockerfile` 的前端阶段实际会生成 `/app/dist`，后续却执行 `COPY --from=frontend-builder /app/src/dist ./src/dist`。该路径冲突会使 Docker 镜像构建或静态文件装载失败。
3. `Dockerfile` 运行时只安装 `curl` 和 `nginx`，没有安装 `libreoffice-impress` 或 `poppler-utils`。PPT 转 PDF 调用 `libreoffice --headless --convert-to pdf`；仓库中没有可用的 LibreOffice/Poppler 运行时保障。
4. 两份 Compose 都向 API 设置 `ENV=production`，但没有 `env_file` 或 `SECRET_KEY` 环境项。`app/core/config.py` 会在生产环境缺少 `SECRET_KEY` 时拒绝启动。
5. 两份 Compose 都没有向 API 传递 `DATABASE_URL`。容器内 API 默认使用 `/app/app.db`，该路径没有挂载到持久化卷；生产 scheduler 默认使用 `/app/data/app.db`，因此 API 与 scheduler 会连接两个不同的 SQLite 文件。

因此，当前文档不提供“可直接成功”的 Docker 生产部署步骤。修复上述代码和配置属于部署实现变更，本次仅记录阻塞。

## 部署拓扑

### 基础 Compose

`docker-compose.yml` 的 `services` 实际包含 4 个服务：

| 服务 | 当前配置 |
|---|---|
| `api` | 使用 `Dockerfile` 构建；`uvicorn app.main:app --host 0.0.0.0 --port 8080 --workers 1`；宿主机绑定 `127.0.0.1:8080` |
| `celery` | 使用 `Dockerfile` 构建；Celery 并发 1；宿主机目录挂载 `./app`、`./logs` |
| `redis` | `redis:7-alpine`；宿主机绑定 `127.0.0.1:6379`；256 MB `allkeys-lru` |
| `nginx` | `nginx:alpine`；宿主机暴露 `80:80`；代理 `api:8080`；静态目录挂载为 `./src/dist:/workspace/src/dist:ro` |

基础 Compose 文件还声明了名为 `jaeger` 的网络映射项，未将 Jaeger 定义在 `services` 下。因此基础 Compose 当前不会启动 Jaeger 服务，实际服务数仍为 4。该网络映射中含有 `image`、`container_name`、`ports`、`environment` 等服务字段，Compose schema 校验会拒绝这些网络字段，基础 Compose 文件本身也会在配置解析阶段失败。

### 生产 Compose

`docker-compose.prod.yml` 的 `services` 实际包含 5 个服务：`api`、`celery`、`scheduler`、`redis`、`nginx`。

- `api` 使用 2 个 Uvicorn worker，绑定 `127.0.0.1:8080`，使用 `api-logs`、`api-data`、`ppt-artifacts` 命名卷。
- `celery` 使用 1 个 worker，健康检查显式禁用，使用 `api-logs`、`api-data`、`ppt-artifacts`。
- `scheduler` 执行 `python -m app.db.scheduler_runner`，健康检查显式禁用；它使用 `api-data` 和 `api-logs`。
- `redis` 使用 AOF、256 MB `allkeys-lru` 和 `redis-data`，健康检查为 `redis-cli ping`。
- `nginx` 等待 `api` 健康后启动，暴露 `80:80`，使用 `nginx-logs`；静态目录仍挂载为 `./src/dist:/workspace/src/dist:ro`。

生产 Compose 没有 Jaeger 服务。应用的 `app/agent/tracing.py` 支持 `OTEL_ENABLED`、`OTEL_EXPORTER`、`OTEL_JAEGER_ENDPOINT` 和 OTLP 配置，默认关闭追踪；当前 Compose 没有提供 Jaeger 或 OTEL Collector，因此仅设置 `OTEL_ENABLED=1` 不能形成完整的追踪链路。

## 当前 Docker 配置

`Dockerfile` 是三阶段文件：Node 20 Alpine 前端构建、Python 3.10 slim 后端依赖、Python 3.10 slim 运行时。运行时创建 `appuser`，安装 `curl` 和 `nginx`，暴露 80、8080，并以内置命令启动 Nginx 和 2 个 Uvicorn worker。

后端依赖来自 `configs/requirements.txt`。该文件包含 FastAPI、Uvicorn、Celery、Redis、SQLAlchemy、Alembic、OpenTelemetry、`python-pptx`、Pillow、OpenCV、Matplotlib、NumPy、Pandas、Scrapy 等依赖。它没有 `gunicorn`、`asyncpg`、`poppler`、`pdf2image` 或 LibreOffice 包。`configs/requirements-test.txt` 是测试工具补充依赖，不会被当前 Dockerfile 安装。

Dockerfile 将 `configs/alembic.ini` 复制为 `/app/alembic.ini`，同时将迁移脚本复制到 `/app/migrations`。配置内的 `script_location = %(here)s/../migrations` 在这个新位置会解析为 `/migrations`；镜像内也不存在 `/app/configs/alembic.ini`。因此要求的 `alembic -c configs/alembic.ini ...` 命令当前只能在仓库目录结构中使用，镜像内迁移路径需要部署实现修复。

Dockerfile 的前端路径问题可用以下静态关系核验：

```text
src/vite.config.js: build.outDir = ../dist
Dockerfile frontend-builder WORKDIR = /app/src
Vite 输出目录 = /app/dist
Dockerfile COPY 源 = /app/src/dist
Compose/Nginx 静态目录 = src/dist / /workspace/src/dist
```

## 不可直接执行的 Docker 命令

以下命令反映仓库中的预期入口，当前会受到前述镜像构建或静态目录阻塞，执行前需要先修复代码和配置：

```bash
# 构建基础镜像
docker build -t codingmatrix:latest .

# 启动基础 Compose
docker compose up -d

# 启动生产 Compose
docker compose -f docker-compose.prod.yml up -d
```

当前环境未安装 Docker CLI，无法在本工作区执行 `docker compose config` 或构建验证。服务数和字段来自 YAML 文件内容核验。

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

该命令按当前 Vite 配置生成仓库根目录 `dist/`。`app/main.py` 和当前 Nginx 配置分别使用 `/workspace/dist`、`/workspace/src/dist` 体系，路径不一致，静态前端访问仍属于已知阻塞。

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

`configs/alembic.ini` 将迁移脚本定位到 `migrations/`，`migrations/env.py` 会把数据库 URL 固定为仓库根目录 `app.db` 的 SQLite 异步 URL，并覆盖 `configs/alembic.ini` 中的占位 URL。该迁移实现不读取 `DATABASE_URL`。当前 Alembic 头为 `20260902_ppt_quality_state`，该迁移包含 PPT 大纲、质量报告和任务字段变更。

所有迁移命令必须显式指定配置文件：

```bash
# 查看当前迁移头
alembic -c configs/alembic.ini heads

# 查看当前数据库版本
alembic -c configs/alembic.ini current

# 已由应用初始化的既有数据库首次接入 Alembic 时登记基线
alembic -c configs/alembic.ini stamp 20260902_ppt_quality_state

# 登记基线后执行幂等升级校验，或用于普通数据库升级
alembic -c configs/alembic.ini upgrade head
```

`make migrate` 当前仍调用未带 `-c configs/alembic.ini` 的 `alembic upgrade head`，因此不作为本文档的迁移命令。`stamp 20260902_ppt_quality_state` 只适用于数据库表结构已经与当前 ORM 模型一致、仅缺少 Alembic 版本记录的既有数据库；普通旧库直接执行 `upgrade head`。迁移前备份实际使用的 `app.db`。

## 健康检查端点

健康路由由 `app/main.py` 以 `/api/v1` 挂载，`app/api/v1/health.py` 内部前缀为 `/health`。Nginx 将 `/health` 代理到 `/api/v1/health`；`/api/v1/health` 由 Nginx 代理到 API。

| 端点 | 当前实现 |
|---|---|
| `GET /api/v1/health` | 快速检查数据库和 Redis；返回 `status`、UTC `timestamp`、`version`。数据库或 Redis 失败时返回 `unhealthy`，函数仍返回 HTTP 200。Redis 未配置时快速检查视为通过。当前源码版本字段为 `v5.10.0`。 |
| `GET /api/v1/health/live` | 只返回 `status: alive` 和 UTC `timestamp`，不检查外部依赖。 |
| `GET /api/v1/health/ready` | 检查数据库和 Redis，并返回 `status: ready/not_ready`、`checks.database`、`checks.redis` 和 UTC `timestamp`。Redis 未配置时快速检查视为通过。 |
| `GET /api/v1/health/detailed` | 返回 `health_checker.check_all()` 结果，包含 `api`、`database`、`redis`、`celery`、`websocket`、`system` 六类检查、各项状态和整体状态。该服务的版本字段当前为 `v3.0`。Celery 检查失败标记为 `degraded`。 |
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

生产 Compose 的持久化卷为 `api-data`、`api-logs`、`ppt-artifacts`、`redis-data` 和 `nginx-logs`。当前 API 默认数据库是容器内 `/app/app.db`，位于这些命名卷之外；scheduler 默认数据库是 `api-data` 卷内的 `/app/data/app.db`。完成数据库路径统一和持久化修复后，备份范围至少包含实际应用数据库、`data/`、PPT 输出目录和日志。备份任务的保留周期、权限和异地副本由部署环境负责配置。

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
- `CORS_ORIGINS` 被传入 CORS 精确来源列表；`ALLOWED_HOSTS` 当前被转换为 CORS origin 正则。应用没有注册 `TrustedHostMiddleware`，因此 `ALLOWED_HOSTS` 当前不提供独立的 Host 头校验。
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
test -f dist/index.html
test -f src/dist/index.html
```

按当前配置，构建成功后第一条应通过，第二条会失败。Dockerfile 构建日志若停在 `COPY --from=frontend-builder /app/src/dist ./src/dist`，对应同一目录冲突。

核验 Compose 服务和 schema：

```bash
docker compose config --services
docker compose -f docker-compose.prod.yml config --services
```

基础 Compose 应在 `networks.jaeger` schema 校验处报错；生产 Compose 应列出 `api`、`celery`、`scheduler`、`redis`、`nginx`。当前工作区缺少 Docker CLI，这两条命令需要在 Docker 主机执行。

查看生产服务日志：

```bash
docker compose -f docker-compose.prod.yml logs api
docker compose -f docker-compose.prod.yml logs celery
docker compose -f docker-compose.prod.yml logs scheduler
docker compose -f docker-compose.prod.yml logs nginx
```

API 启动时报 `生产环境必须设置 SECRET_KEY` 时，核对 Compose 的环境注入方案。API 与 scheduler 数据不一致时，分别核对 `/app/app.db` 和 `/app/data/app.db`，并在继续写入前统一数据库路径。健康响应体为 `unhealthy` 且容器探针仍通过时，依据 `checks` 内容判断数据库或 Redis 故障，不能只依赖 `curl -f` 的退出码。

## 已知问题清单

| 问题 | 证据 | 影响 |
|---|---|---|
| 前端输出目录冲突 | Vite 输出根 `dist/`；Compose、Nginx、Dockerfile 使用 `src/dist` | Docker 前端阶段复制失败或 Nginx 找不到静态文件 |
| 镜像缺少文档转换工具 | Dockerfile 运行时仅安装 `curl`、`nginx`；源码调用 LibreOffice | PPT 转 PDF 在镜像中不可用 |
| Poppler 未纳入镜像 | `configs/requirements.txt` 和 Dockerfile 均未提供 Poppler | PDF 页面渲染相关能力没有镜像级保障 |
| Compose Jaeger 状态不完整 | 基础文件的 `jaeger` 位于 `networks` 映射；生产文件没有 Jaeger | 当前 Compose 不会启动 Jaeger |
| 基础 Compose schema 错误 | `networks.jaeger` 下出现服务专用字段 | `docker compose up` 在配置解析阶段失败 |
| 生产密钥没有注入 | Compose 设置 `ENV=production`，但未声明 `SECRET_KEY` 或 `env_file` | API 配置初始化拒绝启动 |
| SQLite 路径分裂且持久化缺失 | API 默认 `/app/app.db`；scheduler 默认 `/app/data/app.db`；API 默认路径未挂卷 | 服务读取不同数据库，API 数据随容器替换丢失 |
| 容器内 Alembic 路径失配 | Dockerfile 将 ini 复制到 `/app/alembic.ini`，相对脚本路径解析到 `/migrations` | 镜像内无法按仓库标准命令执行迁移 |
| 运行时版本差异 | Dockerfile 使用 Python 3.10；项目说明和本地依赖上下文使用 Python 3.11+ | Docker 与本地运行时行为可能存在差异 |
| 迁移快捷命令路径不足 | `Makefile` 的 `make migrate` 未指定 Alembic 配置 | 命令依赖当前工作目录和默认配置发现行为 |

本次更新只记录这些事实，没有修改部署实现以清除阻塞。
