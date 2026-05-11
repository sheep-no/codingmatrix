# Docker Compose 部署指南

## 环境要求

- Docker 20.10+
- Docker Compose 2.0+
- 2 CPU 核心, 4GB RAM 最低配置

## 目录结构

```
codingmatrix/
├── docker-compose.yml
├── .env
├── app/                    # 后端代码
├── src/                    # 前端代码
└── data/                   # 持久化数据
    ├── db/                 # SQLite 数据库
    ├── uploads/            # 上传文件
    └── logs/               # 日志
```

## 环境变量 (.env)

```env
SECRET_KEY=your-secret-key-here
SILICONFLOW_API_KEY=your-api-key
DATABASE_URL=sqlite+aiosqlite:///./data/db/app.db
MAX_PROJECT_SESSIONS_PER_USER=1
NGINX_AI_MODEL=Qwen/Qwen2.5-Coder-7B-Instruct
```

## docker-compose.yml

```yaml
version: '3.8'

services:
  app:
    build: .
    ports:
      - "8000:8000"
    env_file: .env
    volumes:
      - ./data:/app/data
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/api/v1/health"]
      interval: 30s
      timeout: 10s
      retries: 3
```

## Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

## 启动命令

```bash
# 构建并启动
docker-compose up -d --build

# 查看日志
docker-compose logs -f app

# 停止
docker-compose down

# 重启
docker-compose restart
```

## 验证部署

```bash
# 健康检查
curl http://localhost:8000/api/v1/health

# API 文档
open http://localhost:8000/docs
```

## 数据持久化

- SQLite 数据库: `data/db/app.db`
- 上传文件: `data/uploads/`
- 日志: `data/logs/`

## 反向代理 (可选)

使用 Nginx 反向代理到 FastAPI:

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```
