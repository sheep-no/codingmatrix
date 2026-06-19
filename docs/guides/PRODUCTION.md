# 生产部署指南

**最后更新**: 2026-06-09 | **版本**: v5.15.0

本文档反映当前实际部署架构（2 核 4G 优化版）。**旧版 v3.8 单容器架构已废弃**。

## 部署架构

当前为 **4 容器** + 反向代理架构：
- `api` (uvicorn, 1.5G/1.5CPU)
- `celery` (异步任务 worker, 512M/0.5CPU)
- `redis` (缓存 + 消息队列, 320M/0.25CPU, 256MB LRU)
- `nginx` (反向代理 + 静态文件, 128M/0.25CPU, 端口 80)
- `jaeger` (可选, OTEL 追踪)

API 监听 `127.0.0.1:8080`（仅本机，不直接对外暴露），Nginx 监听 80 暴露公网。

## Docker 部署

### docker-compose.yml (开发环境, 2核4G优化)

```yaml
# 当前实际配置 (docker-compose.yml)
services:
  api:                            # AI Agent API 服务
    build: { context: ., dockerfile: Dockerfile }
    container_name: ai-agent-api
    restart: unless-stopped
    ports: ["127.0.0.1:8080:8080"]
    environment:
      - ENV=production
      - REDIS_URL=redis://redis:6379/0
      - DB_POOL_SIZE=3
      - DB_MAX_OVERFLOW=5
      - WS_MAX_CONNECTIONS=50
      - LOG_LEVEL=WARNING
    volumes:
      - ./app:/workspace/app
      - ./logs:/workspace/logs
      - ./data:/workspace/data
    depends_on: [redis]
    networks: [ai-agent-net]
    mem_limit: 1.5g
    memswap_limit: 2g
    cpus: 1.5

  celery:                         # Celery Worker
    build: { context: ., dockerfile: Dockerfile }
    container_name: ai-agent-celery
    restart: unless-stopped
    command: celery -A app.celery_app worker --loglevel=warning --concurrency=1 --max-tasks-per-child=50
    environment: [ENV=production, REDIS_URL=redis://redis:6379/0, LOG_LEVEL=WARNING]
    volumes: [./app:/workspace/app, ./logs:/workspace/logs]
    depends_on: [redis]
    mem_limit: 512m
    cpus: 0.5

  redis:                          # Redis 缓存/消息队列
    image: redis:7-alpine
    container_name: ai-agent-redis
    restart: unless-stopped
    ports: ["127.0.0.1:6379:6379"]
    command: redis-server --maxmemory 256mb --maxmemory-policy allkeys-lru
    mem_limit: 320m
    cpus: 0.25

  nginx:                          # Nginx 反向代理 + 静态文件
    image: nginx:alpine
    container_name: ai-agent-nginx
    restart: unless-stopped
    ports: ["80:80"]
    volumes:
      - ./configs/nginx.conf:/etc/nginx/nginx.conf:ro
      - ./src/dist:/workspace/src/dist:ro
    depends_on: [api]
    mem_limit: 128m
    cpus: 0.25

  jaeger:                         # 可选：OpenTelemetry 追踪
    image: jaegertracing/all-in-one:latest
    container_name: ai-agent-jaeger
    ports: ["127.0.0.1:16686:16686"]
    # ... 默认不启用，设置 OTEL_ENABLED=1 启用
```

### docker-compose.prod.yml (生产环境, 资源限制+健康检查)

```yaml
# 生产版本 (docker-compose.prod.yml)
services:
  api:
    container_name: ai-agent-api-prod
    restart: always
    ports: ["127.0.0.1:8080:8080"]
    environment:
      - DB_POOL_SIZE=5
      - DB_MAX_OVERFLOW=10
      - WS_MAX_CONNECTIONS=100
    volumes:
      - api-logs:/app/logs       # 命名卷（非目录挂载）
      - api-data:/app/data
    depends_on:
      redis: { condition: service_healthy }
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 15s
    deploy:
      resources:
        limits: { cpus: '1.5', memory: 1.5G }
        reservations: { cpus: '0.5', memory: 512M }

  redis:
    command: redis-server --maxmemory 256mb --maxmemory-policy allkeys-lru --appendonly yes
    volumes: [redis-data:/data]
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 3
    deploy:
      resources:
        limits: { cpus: '0.25', memory: 320M }
        reservations: { cpus: '0.1', memory: 128M }

  # nginx 配置同 dev
```

### Dockerfile (3 阶段构建)

```dockerfile
# Stage 1: Frontend Build
FROM node:20-alpine AS frontend-builder
WORKDIR /app/src
COPY src/package.json src/package-lock.json ./
RUN npm ci
COPY src/ .
RUN npm run build

# Stage 2: Backend Dependencies
FROM python:3.10-slim AS backend-deps
WORKDIR /app
COPY configs/requirements.txt configs/requirements-test.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Stage 3: Production Runtime
FROM python:3.10-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ENV=production
WORKDIR /app

# 安装 curl + 创建非 root 用户
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/* && \
    groupadd -r appuser && \
    useradd -r -g appuser -d /app -s /sbin/nologin appuser

# 复制后端依赖 + 代码 + 前端 dist
# 启动命令: nginx & uvicorn app.main:app --port 8080 --workers 2
# HEALTHCHECK: curl -f http://localhost:8080/health
```

### 构建与启动

```bash
# 构建镜像
docker build -t codingmatrix:latest .

# 启动开发环境
docker compose up -d

# 启动生产环境
docker compose -f docker-compose.prod.yml up -d

# 查看日志
docker compose logs -f api
docker compose logs -f nginx

# 健康检查
curl http://localhost/health           # Nginx 入口
curl http://localhost:8080/health      # API 直连
```

### 不使用 Docker 的部署 (推荐轻量场景)

```bash
# 1. 安装依赖
pip install -r configs/requirements.txt

# 2. 数据库迁移
alembic upgrade head
# 或: make migrate

# 3. 启动后端 (gunicorn 2 workers)
gunicorn app.main:app \
  --bind 0.0.0.0:8080 \
  --workers 2 --threads 2 \
  --worker-class uvicorn.workers.UvicornH11Worker \
  --timeout 120 --keep-alive 5

# 4. 启动 Celery
celery -A app.celery_app worker --loglevel=info --concurrency=1

# 5. Nginx 静态文件
# src/dist 由前端 npm run build 生成
```

## 关键环境变量

完整环境变量清单见 `configs/.env.example`（145 行）。**生产环境必填**：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `SECRET_KEY` | dev 自动生成 (生产必填) | JWT 密钥 |
| `SILICONFLOW_API_KEY` | - | 硅基流动 API Key (默认供应商) |
| `ENV` | development | development / production |
| `ALLOWED_HOSTS` | localhost,127.0.0.1 | 允许的 host (逗号分隔) |
| `CORS_ORIGINS` | http://localhost:3000 | CORS 源 (逗号分隔) |
| `DATABASE_URL` | sqlite+aiosqlite:///./app.db | 数据库连接 (生产建议 PostgreSQL) |
| `DB_POOL_SIZE` | 3 (dev) / 5 (prod) | 数据库连接池大小 |
| `DB_MAX_OVERFLOW` | 5 (dev) / 10 (prod) | 连接池溢出 |
| `REDIS_URL` | redis://localhost:6379/0 | Redis 连接 (可降级内存) |
| `WS_MAX_CONNECTIONS` | 50 (dev) / 100 (prod) | WebSocket 最大连接数 |
| `LOG_LEVEL` | WARNING | 日志级别 |
| `LOG_RETENTION_DAYS` | 7 | 日志保留天数 |
| `MAX_UPLOAD_SIZE_MB` | 50 | 上传文件大小限制 |
| `GRACEFUL_SHUTDOWN_TIMEOUT` | 30 | 优雅关闭超时 (秒) |
| `WEBSOCKET_DRAIN_TIMEOUT` | 10 | WebSocket 排空超时 |
| `CELERYD_SIGTERM_TIMEOUT` | 20 | Celery SIGTERM 超时 |
| `ALLOWED_MODELS` | 10 个模型 | 允许的 LLM 模型白名单 |
| `SENTRY_DSN` | (可选) | Sentry DSN |

**多供应商** (可选, 设置后启用): `DASHSCOPE_API_KEY` / `ZHIPU_API_KEY` / `DEEPSEEK_API_KEY` / `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `OLLAMA_BASE_URL`

**`MAX_CONCURRENT_LLM_CALLS=6`** (硬编码于 `app/agent/llm_client.py:25`): 全局 LLM 并发信号量。

## 健康检查

| 端点 | 用途 | 备注 |
|------|------|------|
| `GET /health` | 基础健康 (Nginx → API 代理) | 200 OK 即可 |
| `GET /api/v1/health` | 详细健康 (Prometheus 指标) | API/DB/Redis/Celery/WS/系统资源六项 |
| `GET /api/docs` | Swagger UI | OpenAPI 3.0 |
| `GET /api/redoc` | ReDoc | OpenAPI 3.0 |
| `GET /api/openapi.json` | OpenAPI JSON Schema | - |

> 注意：历史文档中提到的 `/health/live`、`/health/ready`、`/metrics` 端点**已废弃**，当前统一为 `/health`（Nginx 入口）和 `/api/v1/health`（API 详细）。

## 性能优化

### 后端优化

1. **数据库连接池**（已在 `app/db/database.py` 配置）
   ```python
   from sqlalchemy.ext.asyncio import create_async_engine
   engine = create_async_engine(
       DATABASE_URL,
       pool_size=DB_POOL_SIZE,         # dev 3 / prod 5
       max_overflow=DB_MAX_OVERFLOW,   # dev 5 / prod 10
       pool_pre_ping=True,
   )
   ```
   生产环境建议改用 PostgreSQL（`DATABASE_URL=postgresql+asyncpg://...`），`.env.production.example` 提供模板。

2. **缓存策略**（双 backend）
   - `app/utils/cache.py` (349 行): `MemoryCache` (LRU) + `RedisCache`
   - Redis 未配置时自动降级到内存 (`App.state.cache.backend`)
   - `cache_decorator.py` 提供 `@cache` 装饰器

3. **异步 IO**
   - FastAPI + asyncio 全链路异步
   - `app/utils/http_client.py` 统一 HTTP 客户端 (启动时建池, 关闭时清理)
   - SQLAlchemy 2.0 async 引擎

4. **LLM 并发控制**
   - `app/agent/llm_client.py:25` `MAX_CONCURRENT_LLM_CALLS=6` 全局信号量
   - 防止多用户并发导致供应商 rate limit 触发

5. **优雅关闭**（`app/core/graceful_shutdown.py`, 287 行）
   - 4 状态机: RUNNING → DRAINING → SHUTTING_DOWN → TERMINATED
   - SIGTERM/SIGINT 信号处理
   - 排空进行中请求 + WebSocket drain (10s) + Celery SIGTERM (20s)
   - 总超时 `GRACEFUL_SHUTDOWN_TIMEOUT=30s`

### 前端优化

1. **代码分割**: Vite 5 + `manual chunks` (`src/vite.config.js`)
2. **资源压缩**: 213 处 `console.*` 调用应通过 terser 清理 (当前未做)
3. **SSE 流式渲染**: 18 种消息类型在 `useAgentStreaming.js` 中处理
4. **CDN**: Element Plus / ECharts 等大型库通过 CDN 加载

## 监控

### 健康检查命令

```bash
# 基础存活（通过 Nginx）
curl http://localhost/health

# API 详细健康
curl http://localhost/api/v1/health

# 业务监控
curl http://localhost/api/v1/agent/performance
curl http://localhost/api/v1/agent/token-usage
```

### 日志

- **应用日志**: `logs/app.log`, `logs/error.log` (`CompressedRotatingFileHandler`, 10MB × 10)
- **Nginx 访问日志**: `/var/log/nginx/access.log`
- **敏感信息脱敏**: `app/core/logging_config.py:SensitiveDataFilter` 自动过滤 password/token/api_key/jwt/email/phone/id_card/credit_card 等 10 类
- **日志保留**: `LOG_RETENTION_DAYS=7`

### 可选：OpenTelemetry / Jaeger

```yaml
# docker-compose.yml 中 jaeger 服务默认不启用
# 启用方法: 设置 OTEL_ENABLED=1
# 访问: http://localhost:16686 查看 Jaeger UI
```

详见 [observability/TRACING.md](../observability/TRACING.md)。

### Sentry (可选)

```bash
SENTRY_DSN=https://...@sentry.io/...
SENTRY_ENVIRONMENT=production
```

## 备份策略

### 数据库备份

```bash
#!/bin/bash
# backup.sh
BACKUP_DIR="/backups"
DATE=$(date +%Y%m%d_%H%M%S)

# SQLite 备份 (生产建议改用 PostgreSQL pg_dump)
cp /workspace/app.db ${BACKUP_DIR}/app_${DATE}.db
tar -czf ${BACKUP_DIR}/app_${DATE}.tar.gz ${BACKUP_DIR}/app_${DATE}.db

# 用户项目备份
tar -czf ${BACKUP_DIR}/projects_${DATE}.tar.gz /workspace/projects/

# 清理旧备份（保留 7 天）
find ${BACKUP_DIR} -name "*.tar.gz" -mtime +7 -delete
```

### 日志轮转

日志系统已自动处理（`CompressedRotatingFileHandler`），无需手动配置。

### 优雅重启

```bash
# 通过 scripts/stop.sh 触发优雅关闭（4 状态机）
./scripts/stop.sh

# 或直接发送 SIGTERM
kill -TERM <pid>
```

## 安全加固

### SSL/TLS (Nginx)

```nginx
server {
    listen 443 ssl;
    server_name your-domain.com;

    ssl_certificate /etc/ssl/certs/cert.pem;
    ssl_certificate_key /etc/ssl/private/key.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    location / {
        proxy_pass http://localhost:80;
    }
}
```

### 定期安全审计

```bash
# 后端依赖
pip-audit -r configs/requirements.txt

# 前端依赖
npm audit

# 运行时防护（已内置）
# - app/utils/guardrails.py: Prompt 注入检测
# - app/middleware/rate_limiter.py: 多级速率限制
# - app/middleware/security_headers.py: CSP/X-Frame-Options
# - app/middleware/input_validator.py: SQL 注入 + XSS
# - app/utils/csrf.py: 双重提交 Cookie
```

### 防火墙

```bash
# 允许 HTTP/HTTPS
ufw allow 80/tcp
ufw allow 443/tcp

# 允许 SSH
ufw allow 22/tcp
ufw enable
```

## 相关文档

- [文档首页](../README.md) - 文档导航
- [系统架构](../architecture/ARCHITECTURE.md) - 整体架构
- [安全架构](../security/SECURITY-OVERVIEW.md) - 安全架构
- [分布式追踪](../observability/TRACING.md) - OpenTelemetry
- [服务管理](SERVICES.md) - 启停脚本

---

最后更新：2026-06-09
