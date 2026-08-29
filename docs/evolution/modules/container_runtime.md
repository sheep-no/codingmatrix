# 容器运行时演化深扫文档

> 版本：v0.1 | 扫描日期：2026-08-29 | 状态：已完成
> 归属：部署系统 / 容器运行时
> 路径：`Dockerfile`、`docker-compose.yml`、`docker-compose.prod.yml`、`configs/nginx.conf`、`configs/alembic.ini`、`.env.example`
> 索引：[TASKS.md](../TASKS.md)，第 158 轮

## 1. 模块定位与状态判定

容器运行时由三层配置组成：`Dockerfile` 负责前端构建、Python 依赖和生产镜像；基础 Compose 定义 API、Celery、Redis、Nginx 以及可选观测服务；生产 Compose 定义 API、Redis、Nginx、持久化卷和健康依赖。`configs/nginx.conf` 负责静态文件、API、WebSocket 和健康路径代理，`configs/alembic.ini` 负责迁移脚本定位，`.env.example` 记录应用配置契约。

本次状态判定基于配置声明，运行中的容器、端口监听、健康探针结果和迁移执行记录未在本次扫描中验证。

| 配置面 | 状态 | 证据 |
|---|---|---|
| Dockerfile | 活跃候选运行入口 | 多阶段构建、运行时 `CMD` 和 `HEALTHCHECK`：`Dockerfile:8-18`、`:23-29`、`:34-91` |
| `docker-compose.yml` | 开发/通用部署拓扑 | `api`、`celery`、`redis`、`nginx`、`jaeger` 服务：`docker-compose.yml:6-108` |
| `docker-compose.prod.yml` | 生产部署拓扑 | `api`、`redis`、`nginx`、命名卷和网络：`docker-compose.prod.yml:5-126` |
| `configs/nginx.conf` | 活跃代理配置候选 | `server`、API、WebSocket、健康路由：`configs/nginx.conf:80-135` |
| `configs/alembic.ini` | 活跃迁移配置候选 | `script_location` 和数据库 URL 占位配置：`configs/alembic.ini:3-19`、`:84-87` |
| `.env.example` | 配置模板 | 应用、数据库、Redis、上传和模型配置项：`.env.example:5-145` |

## 2. 部署拓扑

### 2.1 生产拓扑

```text
外部客户端
    |
    | TCP 80
    v
Nginx 容器 ai-agent-nginx-prod
    | /api/、/ws/、/health
    | proxy_pass -> api_backend -> 127.0.0.1:8080
    v
API 容器 ai-agent-api-prod
    | TCP 127.0.0.1:8080（宿主机回环绑定）
    | REDIS_URL=redis://redis:6379/0
    v
Redis 容器 ai-agent-redis-prod
```

API 和 Redis 通过 Compose 网络 `ai-agent-prod-net` 通信，生产配置还声明 `api-logs`、`api-data`、`redis-data`、`nginx-logs` 四个命名卷：`docker-compose.prod.yml:24-31`、`:57-60`、`:85-92`、`:108-126`。Celery 仅存在于基础 Compose，生产 Compose 没有 Celery 服务定义；这是生产异步任务拓扑的未决差异，证据见 `docker-compose.yml:35-55` 与 `docker-compose.prod.yml:5-126`。

### 2.2 Dockerfile 单容器拓扑

Dockerfile 的运行时镜像同时安装 Nginx 和 Uvicorn，并以 shell 启动 Nginx 后启动两个 worker 的 Uvicorn：`Dockerfile:63-73`、`:90-91`。该模型要求 Nginx 在同一容器内访问 `127.0.0.1:8080`，与生产 Compose 中独立 Nginx 容器的服务发现模型形成双轨。生产 Compose 实际使用同一 Dockerfile 构建 API 容器，而 Nginx 使用 `nginx:alpine` 独立镜像：`docker-compose.prod.yml:9-13`、`:79-86`。

## 3. 端口、健康检查与服务状态

| 服务/入口 | 端口声明 | 健康检查 | 扫描结论 |
|---|---|---|---|
| API | 宿主机 `127.0.0.1:8080` -> 容器 `8080`：`docker-compose.prod.yml:15-16` | `GET /health`，30s 间隔、10s 超时、3 次重试：`:32-37` | 仅回环暴露，入口依赖 Nginx |
| Nginx | 宿主机 `80` -> 容器 `80`：`docker-compose.prod.yml:83-84` | 容器内 `GET http://localhost:80/health`：`:93-98` | 代理链可用性取决于上游地址 |
| Redis | 宿主机 `127.0.0.1:6379` -> 容器 `6379`：`docker-compose.prod.yml:54-55` | `redis-cli ping`：`:61-66` | API 启动等待 Redis healthy：`:27-30` |
| Celery | 基础 Compose 无宿主端口：`docker-compose.yml:35-55` | 未声明 | 生产 Compose 未定义该服务 |
| Dockerfile runtime | 暴露 `80`、`8080`：`Dockerfile:80-81` | `GET http://localhost:8080/health`：`Dockerfile:83-85` | 与独立 Nginx Compose 模型重复 |
| Jaeger | `127.0.0.1:16686/14268/14250`：`docker-compose.yml:95-102` | 未声明 | 注释标为可选，配置中始终定义服务 |

基础 Compose 的 API、Celery 和 Nginx 没有 `healthcheck`，`depends_on` 仅表达启动顺序：`docker-compose.yml:23-30`、`:47-53`、`:77-83`。基础 Compose 的 API/Celery bind mount 使用 `/workspace/app`，而 Dockerfile 的工作目录和代码位置是 `/app`：`docker-compose.yml:23-25`、`:47-50`、`Dockerfile:41-58`；运行时是否消费挂载代码取决于容器启动路径，当前定义存在路径漂移风险。

## 4. 迁移与版本问题

### 4.1 迁移执行链

- Alembic 脚本目录解析为相对于配置文件的 `migrations`：`configs/alembic.ini:3-8`；Dockerfile 将该配置复制到 `/app/alembic.ini`，将 `migrations/` 复制到 `/app/migrations/`：`Dockerfile:41`、`:55-58`，路径关系一致。
- `sqlalchemy.url` 仍是 `driver://user:pass@localhost/dbname` 占位值：`configs/alembic.ini:84-87`。真实数据库连接由 `migrations/env.py` 或运行环境提供的配置是否覆盖，单凭本次指定文件无法确认。
- 两份 Compose 都没有 migration service、entrypoint migration 命令或 `command` 前置迁移步骤：`docker-compose.yml:6-108`、`docker-compose.prod.yml:5-126`。部署启动链无法从这些文件确认数据库迁移会自动执行。

### 4.2 版本和镜像漂移

- 前端构建使用 `node:20-alpine`，后端构建和运行使用 `python:3.10-slim`：`Dockerfile:8`、`:23`、`:34`。项目运行时 Python 版本与仓库记忆中 Python 3.11+ 测试约定存在版本漂移风险，需由依赖和测试矩阵确认兼容性。
- 生产 Nginx 使用未固定 tag 的 `nginx:alpine`，基础 Compose 的 Jaeger 使用 `all-in-one:latest`：`docker-compose.prod.yml:80`、`docker-compose.yml:95-96`。镜像内容会随拉取时间变化，部署可复现性下降。
- `configs/requirements-test.txt` 被复制到依赖构建阶段，但只执行生产 `requirements.txt` 安装：`Dockerfile:27-29`。测试依赖在最终镜像中是否存在无法由该 Dockerfile 保证。
- 生产 Compose 使用 Compose `deploy.resources` 声明资源限制：`docker-compose.prod.yml:38-45`、`:67-74`、`:99-106`；实际是否生效取决于运行器是否支持该字段，需部署环境验证。

## 5. 已探明问题

### CR1 [P2] 独立 Nginx 容器的上游指向自身回环地址

- **现象**：生产 Compose 将 Nginx 和 API 分为两个容器，但 Nginx 配置的 `api_backend` 指向 `127.0.0.1:8080`：`docker-compose.prod.yml:79-92`、`configs/nginx.conf:80-84`。
- **根因**：容器内 `127.0.0.1` 只指向当前 Nginx 容器；API 的容器名为 `ai-agent-api-prod`，Compose 服务名为 `api`，配置没有使用 Compose DNS 服务名。
- **影响**：`/api/`、`/ws/` 和 `/health` 代理请求可能连接 Nginx 自身的 8080 端口并失败，外部 80 端口无法稳定到达 API。
- **证据**：代理位置为 `configs/nginx.conf:106-125`；API 监听和服务名为 `docker-compose.prod.yml:9-16`、`:30-31`。
- **建议**：为独立 Nginx 拓扑将上游改为 Compose 服务名 `api:8080`，并分别验证 HTTP、WebSocket 和健康路径；单容器 Dockerfile 拓扑保留 `127.0.0.1:8080` 时，应明确两种入口的适用边界。

### CR2 [P2] 生产部署未声明数据库迁移步骤

- **现象**：镜像包含 Alembic 配置和迁移目录，但两个 Compose 文件均未定义迁移服务或启动前迁移命令。
- **根因**：迁移资产已打包，执行契约未接入容器生命周期。
- **影响**：新版本启动时数据库 schema 是否与应用代码匹配依赖人工操作或外部流程；迁移遗漏可能在 API 运行后才暴露。
- **证据**：`Dockerfile:55-58`、`configs/alembic.ini:3-8`、`docker-compose.yml:6-108`、`docker-compose.prod.yml:5-126`。
- **建议**：确定单一迁移责任方，使用一次性 migration job 或受控发布步骤，并在 API 启动前完成成功状态检查。

### CR3 [P2] Dockerfile 与 Compose 采用相互冲突的运行模型

- **现象**：Dockerfile 启动同一容器内的 Nginx+Uvicorn：`Dockerfile:63-91`；Compose 又创建独立 Nginx 容器，且 API 容器使用该 Dockerfile：`docker-compose.prod.yml:9-13`、`:79-86`。
- **根因**：镜像职责未收敛为“API 运行时”或“全栈单容器”之一。
- **影响**：API 容器携带并启动多余 Nginx，健康检查和代理拓扑分别覆盖 8080 与 80；故障定位、日志归属和资源预算变复杂。
- **证据**：Dockerfile `EXPOSE 80 8080` 与复合 `CMD`：`Dockerfile:80-91`；生产 Nginx 独立运行：`docker-compose.prod.yml:79-103`。
- **建议**：生产 Compose 选定独立代理模型后，使 API 镜像只启动 Uvicorn，并将 Nginx 配置、静态文件和健康检查绑定到对应服务职责。

### CR4 [P3] 基础 Compose 的应用挂载目录与镜像工作目录不一致

- **现象**：基础 Compose 将 `./app` 挂载到 `/workspace/app`，Dockerfile 的工作目录为 `/app`，源代码复制到 `/app/app`：`docker-compose.yml:23-25`、`Dockerfile:41`、`:55`。
- **影响**：开发/通用 Compose 中挂载代码可能无法覆盖实际启动的 `app.main:app`，代码热更新和容器内运行版本可能与预期不一致。
- **建议**：统一工作目录和挂载目标，并用容器内路径验证 Uvicorn 实际加载的源代码位置。

### CR5 [P3] 基础 Compose 将可选 Jaeger 作为无条件服务声明

- **现象**：注释写明 OTEL/Jaeger 可选并以环境变量启用，服务定义没有 `profiles` 或条件开关：`docker-compose.yml:91-108`。
- **影响**：按该 Compose 文件启动时 Jaeger 会参与服务编排，占用端口和资源；`OTEL_ENABLED` 对服务是否创建没有配置层效果。
- **建议**：使用 Compose profile 或拆分观测覆盖文件，并让启用条件与应用 OTEL 配置保持一致。

### CR6 [P3] 关键镜像版本未锁定

- **现象**：生产 Nginx 和 Jaeger 使用浮动 tag：`docker-compose.prod.yml:80`、`docker-compose.yml:95-96`。
- **影响**：同一提交在不同时间构建或拉取可能得到不同镜像内容，回滚和问题复现成本增加。
- **建议**：锁定经过验证的具体版本，生产环境进一步记录 digest，并建立定期升级流程。

## 6. 未知点与验证项

- 本次扫描未连接 Docker daemon，无法确认容器当前是否运行、端口是否监听、健康检查是否通过以及实际资源限制是否生效。
- Nginx 上游配置需要在与 Compose 网络一致的容器环境中验证；静态检查已确认回环地址与独立容器拓扑不匹配。
- 需要确认应用是否在 API 启动流程、发布脚本或外部 CI/CD 中执行 Alembic；指定文件中没有该证据。
- 需要确认 `migrations/env.py` 是否读取环境变量覆盖 `sqlalchemy.url`，以及 SQLite/Redis 持久化目录是否与生产卷一致。
- 需要确认生产部署是否需要 Celery；基础 Compose 有 Celery，生产 Compose 缺少该服务定义。
- `.env.example` 包含密钥类配置项和供应商配置项，本文件只记录其存在及用途类别，不记录任何配置值。

## 7. 修改建议

| # | 优先级 | 修改动作 | 达成目的 | 涉及位置 | 对应问题 |
|---|---|---|---|---|---|
| 1 | P2 | 将独立 Nginx 上游改为 Compose 服务名并验证三类代理路径 | 恢复 80 -> API 的 HTTP/WebSocket/健康链路 | `configs/nginx.conf:80-125` | CR1 |
| 2 | P2 | 明确并接入一次性数据库迁移责任方 | 让 schema 版本随发布受控推进 | `docker-compose*.yml`、发布流程 | CR2 |
| 3 | P2 | 收敛为独立代理或单容器运行模型 | 消除重复进程、健康检查和日志职责 | `Dockerfile:63-91`、`docker-compose.prod.yml:79-103` | CR3 |
| 4 | P3 | 统一 `/app` 与 `/workspace/app` 路径 | 保证挂载代码与 Uvicorn 加载代码一致 | `Dockerfile:41-58`、`docker-compose.yml:23-25` | CR4 |
| 5 | P3 | 用 profile/覆盖文件管理 Jaeger | 使可选观测服务真正按需启动 | `docker-compose.yml:91-108` | CR5 |
| 6 | P3 | 固定 Nginx、Jaeger 版本或 digest | 提高构建和回滚可复现性 | `docker-compose.yml:95-96`、`docker-compose.prod.yml:80` | CR6 |

## 8. 演化方向关联

- **拆分解耦**：优先选择 API 镜像与 Nginx 代理职责分离，移除 API 镜像中与生产 Compose 重复的 Nginx 进程。
- **统一收敛**：统一容器路径、服务命名、健康检查入口和资源限制声明，建立单一生产拓扑。
- **平台化**：把迁移、健康检查、镜像版本和回滚策略纳入发布流水线，并将 Celery 是否属于生产拓扑形成明确契约。
- **存在与可运行性对齐**：Dockerfile 中已存在的迁移目录、健康检查和 Nginx 配置需要与 Compose 实际服务链路逐项验证，配置存在本身不代表运行时已接线。
