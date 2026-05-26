#!/bin/bash
# 查看 AI Agent 服务状态

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

echo "=========================================="
echo "AI Agent 服务状态"
echo "=========================================="

# 检查 Celery 进程
if [ -f "$PROJECT_DIR/celery.pid" ]; then
    PID=$(cat "$PROJECT_DIR/celery.pid")
    if ps -p $PID &>/dev/null; then
        echo "[RUNNING] Celery Worker PID: $PID"
    else
        echo "[STOPPED] Celery Worker PID 文件存在但进程已退出"
    fi
fi

# 检查 gunicorn 进程
if [ -f "$PROJECT_DIR/gunicorn.pid" ]; then
    PID=$(cat "$PROJECT_DIR/gunicorn.pid")
    if ps -p $PID &>/dev/null; then
        echo "[RUNNING] Gunicorn PID: $PID"
    else
        echo "[STOPPED] Gunicorn PID 文件存在但进程已退出"
    fi
fi

# 检查端口
if lsof -i :8080 &>/dev/null; then
    echo "[LISTENING] 端口 8080:"
    lsof -i :8080 | grep -v "^COMMAND" | head -5
else
    echo "[STOPPED] 端口 8080 未监听"
fi

# 内存使用
echo ""
echo "[MEMORY] 进程内存使用:"
ps aux | grep -E "gunicorn|celery" | grep -v grep | head -5 || echo "  无运行中的进程"

# Redis 检查
echo ""
echo "[REDIS] 连接状态:"
if command -v redis-cli &> /dev/null; then
    redis-cli -u "${REDIS_URL:-redis://localhost:6379/0}" ping 2>/dev/null && echo "  Redis 正常" || echo "  Redis 不可用"
else
    echo "  redis-cli 未安装"
fi

echo ""
echo "[LOG] 最近错误日志 (最后10行):"
tail -10 "$PROJECT_DIR/logs/error.log" 2>/dev/null || echo "  无日志文件"