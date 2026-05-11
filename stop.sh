#!/bin/bash
# 停止 AI Agent 服务

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

echo "[INFO] 停止 AI Agent 服务..."

# 停止 Celery Worker
if [ -f "$PROJECT_DIR/celery.pid" ]; then
    celery -A app.celery_app control shutdown --pidfile="$PROJECT_DIR/celery.pid" 2>/dev/null || true
    kill $(cat "$PROJECT_DIR/celery.pid") 2>/dev/null && echo "[INFO] Celery Worker 已停止" || true
    rm -f "$PROJECT_DIR/celery.pid"
fi

# 强制停止 Celery
pkill -f "celery.*app.celery_app" 2>/dev/null || true

# 停止 gunicorn
if [ -f "$PROJECT_DIR/gunicorn.pid" ]; then
    kill $(cat "$PROJECT_DIR/gunicorn.pid") 2>/dev/null && echo "[INFO] Gunicorn 已停止" || true
    rm -f "$PROJECT_DIR/gunicorn.pid"
fi

# 强制停止
pkill -f "gunicorn.*app.main:app" 2>/dev/null || true

# 停止可能的 uvicorn 进程
pkill -f "uvicorn app.main:app" 2>/dev/null || true

echo "[INFO] 服务已停止"