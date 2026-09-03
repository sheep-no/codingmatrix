# 快速开始

> 最后更新：2026-09-03

## 环境要求

- Python 3.11 用于当前开发与测试；Dockerfile 使用 Python 3.10
- Node.js 20 与 npm；Docker 前端构建镜像为 `node:20-alpine`
- SQLite 默认可用；运行时迁移器也支持 MySQL
- Redis 用于用户 API Key、共享缓存和 Celery
- Docker Compose 用于容器化服务，可选

## 安装依赖

仓库包含 `src/package-lock.json`，前端使用 npm。

```bash
# 安装后端依赖
python3 -m pip install -r configs/requirements.txt

# 安装前端依赖
cd /workspace/src
npm ci
```

## 配置环境

`app.main` 从仓库根目录读取 `.env`，并使用 `override=False`，因此进程环境变量优先。

```bash
ENV=development
DATABASE_URL=sqlite+aiosqlite:////workspace/app.db
REDIS_URL=redis://127.0.0.1:6379/0
SECRET_KEY=<至少16字符的随机密钥>
SILICONFLOW_API_KEY=<可选的供应商API_KEY>
```

所有凭据应由部署环境或本地 `.env` 提供。示例和文档统一使用占位符。

## 初始化数据库

FastAPI 启动时会运行 `migrations.runner.run_async_migrations()`，创建缺失表并补齐已有 `tasks` 表的统一状态字段。

Alembic 当前 head 为 `20260902_ppt_quality_state`，且 `migrations/env.py` 固定指向仓库根目录 `app.db`。

```bash
# 查看迁移状态
alembic -c configs/alembic.ini heads
alembic -c configs/alembic.ini current

# 已具备当前结构的既有 app.db 首次登记基线
alembic -c configs/alembic.ini stamp 20260902_ppt_quality_state

# 后续升级
alembic -c configs/alembic.ini upgrade head
```

`stamp` 适用于结构已存在的数据库。新数据库应通过迁移链创建结构，或先由应用运行时迁移器初始化并核对结构后登记基线。

## 启动开发服务

```bash
# 终端 1：启动后端
cd /workspace
PYTHONPATH=/workspace python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# 终端 2：启动前端
cd /workspace/src
npm run dev
```

访问地址：

- 前端：`http://localhost:3000`
- 后端健康检查：`http://localhost:8000/api/v1/health`
- Swagger UI：`http://localhost:8000/api/docs`
- OpenAPI：`http://localhost:8000/api/openapi.json`

Vite 将 `/api/v1`、`/api/v2` 和 WebSocket 请求代理到 `http://localhost:8000`。

## 首次认证

登录、注册和刷新端点均使用 CSRF 依赖。客户端先获取 CSRF Cookie，再在请求头中回传同一 Token。

```bash
# 获取 Cookie 和响应中的 CSRF Token
curl -c cookies.txt http://localhost:8000/api/v1/csrf-token

# 登录请求需要 X-CSRF-Token；凭据载荷由 Web 前端加密生成
curl -b cookies.txt -X POST http://localhost:8000/api/v1/login \
  -H "Content-Type: application/json" \
  -H "X-CSRF-Token: <CSRF_TOKEN>" \
  -d '{"encrypted_data":"<BASE64_CIPHERTEXT>","encrypted_key":"<BASE64_RSA_CIPHERTEXT>"}'
```

Web 前端使用 `/api/v1/public-key` 获取 RSA-2048 公钥，以 AES-256-CBC 加密登录 JSON，并以 RSA-OAEP/SHA-256 加密 AES Key。后端当前仍接受明文 `email` 与 `password` 兼容载荷。

## 用户模型 Key

内置供应商 Key 通过 `/api/v1/agent/apikey/*` 管理。前端先读取 `/api/v1/agent/apikey/public-key`，再用 RSA-OAEP 加密 Key；后端解密后将 Key 与元数据按 TTL 保存到 Redis。支持 `siliconflow`、`openai`、`anthropic`、`bailian`、`glm` 和 `deepseek`。

动态供应商使用 `/api/v1/providers`，支持 OpenAI 兼容协议和 Anthropic 协议。详细配置见 [多供应商配置](MULTI-PROVIDER-SETUP.md) 与 [API Key 指南](API-KEY-GUIDE.md)。

## 验证

```bash
# 后端单元测试
python3 -m pytest tests/unit -q

# 前端单元测试
cd /workspace/src
npm run test:run

# 前端生产构建
cd /workspace/src
npm run build
```

前端构建产物位于仓库根目录 `dist/`。容器/Nginx 的产物路径差异记录在 [服务与端口指南](SERVICES.md)。

## 相关文档

- [服务与端口指南](SERVICES.md)
- [生产部署](PRODUCTION.md)
- [多供应商配置](MULTI-PROVIDER-SETUP.md)
- [API Key 指南](API-KEY-GUIDE.md)
- [安全概览](../security/SECURITY-OVERVIEW.md)
