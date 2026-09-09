# 服务与端口指南

> 最后更新：2026-09-03

本文档以 `app/main.py`、`src/vite.config.js`、`Dockerfile`、`docker-compose.yml`、`docker-compose.prod.yml` 和 Nginx 配置为准。

## 服务拓扑

| 场景 | 服务 | 地址或端口 | 说明 |
|------|------|------------|------|
| 本地开发 | Vite | `http://localhost:3000` | 前端开发入口；代理 `/api/v1`、`/api/v2` 和 WebSocket 到后端 |
| 本地开发 | FastAPI | `http://localhost:8000` | 后端 API |
| 本地依赖 | Redis | `127.0.0.1:6379` | 配置 `REDIS_URL` 后用于缓存、API Key 和 Celery broker/backend |
| 容器 | FastAPI | 容器内 `8080`，宿主机 `127.0.0.1:8080` | Compose API 服务 |
| 容器 | Nginx | `http://localhost:80` | 对外静态资源与 API/WebSocket 入口 |
| 容器 | Redis | 容器内 `6379`，宿主机 `127.0.0.1:6379` | Compose Redis 服务 |
| 容器 | Celery | 无 HTTP 端口 | 异步任务 worker |
| 生产 Compose | scheduler | 无 HTTP 端口 | 独立执行 `python -m app.db.scheduler_runner` |

FastAPI 的文档入口是 `/api/docs`，OpenAPI JSON 是 `/api/openapi.json`。健康检查包括 `/api/v1/health`、`/api/v1/health/ready`、`/api/v1/health/live`、`/api/v1/health/detailed`、`/api/v1/health/metrics` 和 `/api/v1/health/models`。Nginx 额外将 `/health` 转发到 `/api/v1/health`。

## 本地开发

后端使用 Python 3.11 开发与测试；当前 Dockerfile 运行时是 Python 3.10。启动前应确认依赖与目标 Python 版本兼容。

```bash
# 启动后端 API
PYTHONPATH=/workspace python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# 启动前端开发服务器
cd /workspace/src
npm run dev
```

Vite 固定监听 `0.0.0.0:3000`。代理目标固定为 `http://localhost:8000`，并允许 `localhost`、`127.0.0.1` 和 `.monkeycode-ai.online` Host。

## 前端静态托管

`npm run build` 由 `src/vite.config.js` 输出到仓库根目录 `dist/`。`app/main.py` 同样从仓库根目录 `dist/` 提供 `/static`、`/` 和 Vue Router history fallback，因此本地单进程静态托管可使用：

```bash
# 构建前端到 /workspace/dist
cd /workspace/src
npm run build

# 由 FastAPI 托管构建产物与 API
cd /workspace
PYTHONPATH=/workspace python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

当前 Compose 的 Nginx 挂载源是 `./src/dist`，Dockerfile 也引用构建阶段的 `/app/src/dist`；这两处与 Vite 的实际输出目录 `/workspace/dist` 或构建容器内 `/app/dist` 不一致。使用 Nginx 或构建镜像前需要先统一产物路径。

## Docker Compose

基础 Compose 定义 `api`、`celery`、`redis` 和 `nginx`；生产 Compose 额外定义独立 `scheduler`。API upstream 为 `api:8080`，单镜像内 Nginx upstream 为 `127.0.0.1:8080`。

基础 `docker-compose.yml` 中的 Jaeger 服务字段当前位于顶层 `networks.jaeger`，Compose schema 会在解析阶段拒绝该文件。生产 Compose 还存在前端产物路径、生产密钥和数据库持久化阻塞。修复这些配置后，预期入口为：

```bash
# 启动基础服务
docker compose up -d api celery redis nginx

# 启动生产服务
docker compose -f docker-compose.prod.yml up -d api celery scheduler redis nginx
```

这些命令当前用于说明预期拓扑，尚不具备直接成功运行的条件。完整阻塞清单见 [生产部署指南](PRODUCTION.md)，追踪配置见 [分布式追踪](../observability/TRACING.md)。

## Celery 与 PPT

Celery 使用 `REDIS_URL` 作为 broker 和 backend。基础 Compose worker 未限制队列；本地仅处理 PPT 队列时使用：

```bash
cd /workspace
PYTHONPATH=/workspace REDIS_URL=redis://127.0.0.1:6379/0 celery -A app.celery_app worker --loglevel=info --concurrency=1 --pool=solo --queues=ppt
```

设置 `PPT_USE_CELERY=true` 后，PPT 创建接口通过 Celery 投递任务。生产 Compose 将 API、Celery 和 scheduler 的数据目录挂载到共享 `api-data` 卷，并为 API 与 Celery 共享 `ppt-artifacts` 卷。

## 数据库与迁移

应用 lifespan 启动时调用 `migrations.runner.run_async_migrations()`。该运行时迁移器支持 SQLite 和 MySQL，创建缺失表，并为已有 `tasks` 表补充统一状态字段；它不执行 Alembic 版本脚本中的全部结构变更。

Alembic 当前只有一个 head：`20260902_ppt_quality_state`。`migrations/env.py` 固定使用仓库根目录 `app.db`，不会读取运行时 `DATABASE_URL`。

```bash
# 查看 Alembic head 与当前版本
alembic -c configs/alembic.ini heads
alembic -c configs/alembic.ini current

# 已由运行时迁移器初始化的既有数据库首次接入 Alembic
alembic -c configs/alembic.ini stamp 20260902_ppt_quality_state

# 已纳入 Alembic 管理的数据库升级
alembic -c configs/alembic.ini upgrade head
```

执行 `stamp` 前应确认目标数据库已经包含该 head 所代表的表、索引和字段；`stamp` 只登记版本，不创建结构。

## 关键配置

```bash
DATABASE_URL=sqlite+aiosqlite:////workspace/app.db
REDIS_URL=redis://127.0.0.1:6379/0
SECRET_KEY=<至少16字符的随机密钥>
ENABLE_SCHEDULER=false
PPT_USE_CELERY=false
```

开发环境未设置 `SECRET_KEY` 时会生成进程级临时值；生产环境必须显式配置。`REDIS_URL` 默认为空，此时 API 缓存回退到内存；API Key 管理和 Celery 仍需要可用 Redis。

## 核验

```bash
# FastAPI 健康检查
curl http://localhost:8000/api/v1/health
curl http://localhost:8000/api/v1/health/ready

# 容器 Nginx 入口
curl http://localhost/api/v1/health

# API 文档
curl -I http://localhost:8000/api/docs
```

健康接口检查数据库和 Redis；它不检查 Celery worker 在线状态。

## 相关文档

- [快速开始](GETTING-STARTED.md)
- [生产部署](PRODUCTION.md)
- [多供应商配置](MULTI-PROVIDER-SETUP.md)
- [API Key 指南](API-KEY-GUIDE.md)
- [追踪指南](../observability/TRACING.md)
