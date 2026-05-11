#!/bin/bash
# =============================================================================
# AI Agent 服务启动脚本（2核4G 优化版）
# =============================================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

# 加载环境变量
if [ -f "$PROJECT_DIR/.env" ]; then
    log_info "加载环境变量..."
    export $(grep -v '^#' "$PROJECT_DIR/.env" | xargs) 2>/dev/null || true
fi

# 默认配置
export DB_POOL_SIZE=${DB_POOL_SIZE:-3}
export DB_MAX_OVERFLOW=${DB_MAX_OVERFLOW:-5}
export WS_MAX_CONNECTIONS=${WS_MAX_CONNECTIONS:-50}
export LOG_LEVEL=${LOG_LEVEL:-INFO}
export REDIS_URL=${REDIS_URL:-redis://localhost:6379/0}
export CELERY_CONCURRENCY=${CELERY_CONCURRENCY:-1}

mkdir -p "$PROJECT_DIR/logs"
mkdir -p "$PROJECT_DIR/data"

# 检查 Redis
check_redis() {
    log_info "检查 Redis..."
    if command -v redis-cli &> /dev/null; then
        if redis-cli -u "$REDIS_URL" ping &>/dev/null; then
            log_info "Redis 连接正常"
        else
            log_warn "Redis 连接失败，请确保 Redis 已启动"
        fi
    fi
}

# 停止服务
stop_all() {
    log_info "停止所有服务..."
    [ -f "$PROJECT_DIR/gunicorn.pid" ] && kill $(cat "$PROJECT_DIR/gunicorn.pid") 2>/dev/null || true
    [ -f "$PROJECT_DIR/celery.pid" ] && kill $(cat "$PROJECT_DIR/celery.pid") 2>/dev/null || true
    pkill -f "gunicorn.*app.main:app" 2>/dev/null || true
    pkill -f "celery.*app.celery_app" 2>/dev/null || true
    pkill -f "nginx" 2>/dev/null || true
    sleep 1
}

# 构建前端
build_frontend() {
    if [ -d "$PROJECT_DIR/src" ] && [ -f "$PROJECT_DIR/src/package.json" ]; then
        log_info "构建前端..."
        cd "$PROJECT_DIR/src"
        if command -v npm &> /dev/null; then
            npm install --silent 2>/dev/null || npm install
            npm run build
            if [ -d "$PROJECT_DIR/src/dist" ]; then
                log_info "前端构建成功: $PROJECT_DIR/src/dist"
            else
                log_warn "前端构建可能失败，dist 目录不存在"
            fi
        else
            log_warn "npm 未安装，跳过前端构建"
        fi
        cd "$PROJECT_DIR"
    fi
}

# 启动 API 服务
start_api() {
    log_info "启动 Gunicorn API 服务..."
    WORKER_COUNT=2
    THREAD_COUNT=2

    gunicorn app.main:app \
        --bind 0.0.0.0:8080 \
        --workers $WORKER_COUNT \
        --threads $THREAD_COUNT \
        --worker-class uvicorn.workers.UvicornH11Worker \
        --timeout 120 \
        --keep-alive 5 \
        --max-requests 500 \
        --max-requests-jitter 50 \
        --access-logfile "$PROJECT_DIR/logs/access.log" \
        --error-logfile "$PROJECT_DIR/logs/error.log" \
        --log-level "${LOG_LEVEL,,}" \
        --capture-output \
        --daemon \
        --pid "$PROJECT_DIR/gunicorn.pid"

    sleep 2
    if curl -s http://127.0.0.1:8080/health &>/dev/null; then
        log_info "API 服务启动成功 (PID: $(cat $PROJECT_DIR/gunicorn.pid))"
    else
        log_error "API 服务启动失败"
        return 1
    fi
}

# 启动 Celery
start_celery() {
    log_info "启动 Celery Worker..."
    celery -A app.celery_app worker \
        --loglevel="${LOG_LEVEL,,}" \
        --concurrency=$CELERY_CONCURRENCY \
        --max-tasks-per-child=50 \
        --logfile="$PROJECT_DIR/logs/celery.log" \
        --pidfile="$PROJECT_DIR/celery.pid" \
        --detach
    sleep 1
    log_info "Celery Worker 启动成功 (PID: $(cat $PROJECT_DIR/celery.pid 2>/dev/null || echo 'N/A'))"
}

# 启动 Nginx
start_nginx() {
    log_info "启动 Nginx..."

    if ! command -v nginx &> /dev/null; then
        log_warn "nginx 未安装，请先安装: apt-get install nginx"
        return 1
    fi

    if [ ! -f "$PROJECT_DIR/nginx.conf" ]; then
        log_warn "nginx.conf 不存在，使用默认配置"
        nginx
    else
        nginx -c "$PROJECT_DIR/nginx.conf"
    fi

    sleep 1
    if pgrep -x nginx > /dev/null; then
        log_info "Nginx 启动成功"
    else
        log_error "Nginx 启动失败"
    fi
}

# 检查端口
check_port() {
    if netstat -tuln 2>/dev/null | grep -q ":80 " || ss -tuln 2>/dev/null | grep -q ":80 "; then
        log_warn "端口 80 已被占用"
        read -p "是否关闭现有进程? (y/n): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            pkill -f nginx || true
            sleep 1
        else
            log_warn "跳过 Nginx 启动"
            return 1
        fi
    fi
}

# 检查所有服务状态
check_status() {
    echo ""
    log_info "=========================================="
    log_info "服务状态"
    log_info "=========================================="

    # API
    if curl -s http://127.0.0.1:8080/health &>/dev/null; then
        echo -e "[${GREEN}RUNNING${NC}] API (Gunicorn)"
    else
        echo -e "[${RED}STOPPED${NC}] API (Gunicorn)"
    fi

    # Celery
    if [ -f "$PROJECT_DIR/celery.pid" ] && ps -p $(cat "$PROJECT_DIR/celery.pid") &>/dev/null; then
        echo -e "[${GREEN}RUNNING${NC}] Celery Worker"
    else
        echo -e "[${RED}STOPPED${NC}] Celery Worker"
    fi

    # Nginx
    if pgrep -x nginx &>/dev/null; then
        echo -e "[${GREEN}RUNNING${NC}] Nginx (端口 80)"
    else
        echo -e "[${RED}STOPPED${NC}] Nginx (端口 80)"
    fi

    # Redis
    if command -v redis-cli &> /dev/null && redis-cli -u "$REDIS_URL" ping &>/dev/null; then
        echo -e "[${GREEN}RUNNING${NC}] Redis"
    else
        echo -e "[${YELLOW}UNKNOWN${NC}] Redis (请检查是否已启动)"
    fi
}

# 主菜单
case "${1:-menu}" in
    start)
        stop_all
        check_redis
        build_frontend
        start_api
        start_celery
        check_port || true
        start_nginx || true
        check_status
        ;;

    api)
        stop_all
        check_redis
        start_api
        check_status
        ;;

    celery)
        check_redis
        start_celery
        check_status
        ;;

    nginx)
        check_port
        build_frontend
        start_nginx
        check_status
        ;;

    build)
        build_frontend
        ;;

    status|menu)
        check_status
        ;;

    stop)
        stop_all
        log_info "所有服务已停止"
        ;;

    restart)
        stop_all
        check_redis
        build_frontend
        start_api
        start_celery
        start_nginx || true
        check_status
        ;;

    *)
        echo ""
        echo "=========================================="
        echo "AI Agent 服务管理"
        echo "=========================================="
        echo ""
        echo "用法: $0 <命令>"
        echo ""
        echo "命令:"
        echo "  start    - 启动全部服务 (推荐)"
        echo "  api      - 仅启动 API 服务"
        echo "  celery   - 仅启动 Celery Worker"
        echo "  nginx    - 仅启动 Nginx"
        echo "  build    - 构建前端"
        echo "  status   - 查看服务状态"
        echo "  stop     - 停止所有服务"
        echo "  restart  - 重启所有服务"
        echo ""
        echo "Nginx 将监听端口 80，反向代理到:"
        echo "  /        -> 前端静态文件 (src/dist)"
        echo "  /api/    -> API 服务 (127.0.0.1:8080)"
        echo "  /ws/     -> WebSocket"
        echo ""
        check_status
        ;;
esac