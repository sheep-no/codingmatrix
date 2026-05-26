#!/bin/bash
# 服务管理脚本

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 日志目录
LOG_DIR="/workspace/logs"
BACKEND_PID_FILE="$LOG_DIR/backend.pid"
FRONTEND_PID_FILE="$LOG_DIR/frontend.pid"

# 创建日志目录
mkdir -p "$LOG_DIR"

# 显示帮助信息
show_help() {
    echo "服务管理脚本"
    echo "用法: $0 [命令]"
    echo ""
    echo "命令:"
    echo "  start     启动前后端服务"
    echo "  stop      停止前后端服务"
    echo "  restart  重启前后端服务"
    echo "  status    查看服务状态"
    echo "  logs      查看服务日志"
    echo "  health    健康检查"
    echo "  help      显示帮助信息"
    echo ""
    echo "示例:"
    echo "  $0 start      # 启动服务"
    echo "  $0 status     # 查看状态"
    echo "  $0 logs       # 查看日志"
}

# 检查服务状态
check_status() {
    echo "=== 服务状态检查 ==="
    echo ""

    # 检查后端
    if [ -f "$BACKEND_PID_FILE" ]; then
        BACKEND_PID=$(cat "$BACKEND_PID_FILE")
        if ps -p "$BACKEND_PID" > /dev/null 2>&1; then
            echo -e "${GREEN}✓ 后端服务运行中${NC} (PID: $BACKEND_PID, 端口: 8002)"
        else
            echo -e "${RED}✗ 后端服务未运行${NC} (PID文件存在但进程不存在)"
        fi
    else
        echo -e "${YELLOW}○ 后端服务未启动${NC}"
    fi

    echo ""

    # 检查前端
    if [ -f "$FRONTEND_PID_FILE" ]; then
        FRONTEND_PID=$(cat "$FRONTEND_PID_FILE")
        if ps -p "$FRONTEND_PID" > /dev/null 2>&1; then
            echo -e "${GREEN}✓ 前端服务运行中${NC} (PID: $FRONTEND_PID, 端口: 3000)"
        else
            echo -e "${RED}✗ 前端服务未运行${NC} (PID文件存在但进程不存在)"
        fi
    else
        echo -e "${YELLOW}○ 前端服务未启动${NC}"
    fi

    echo ""
}

# 停止服务
stop_services() {
    echo "=== 停止服务 ==="

    # 停止后端
    if [ -f "$BACKEND_PID_FILE" ]; then
        BACKEND_PID=$(cat "$BACKEND_PID_FILE")
        if ps -p "$BACKEND_PID" > /dev/null 2>&1; then
            echo "停止后端服务 (PID: $BACKEND_PID)..."
            kill -9 "$BACKEND_PID" 2>/dev/null
            rm -f "$BACKEND_PID_FILE"
            echo -e "${GREEN}✓ 后端服务已停止${NC}"
        else
            rm -f "$BACKEND_PID_FILE"
            echo -e "${YELLOW}○ 后端服务未运行${NC}"
        fi
    else
        echo -e "${YELLOW}○ 后端服务未启动${NC}"
    fi

    # 停止前端
    if [ -f "$FRONTEND_PID_FILE" ]; then
        FRONTEND_PID=$(cat "$FRONTEND_PID_FILE")
        if ps -p "$FRONTEND_PID" > /dev/null 2>&1; then
            echo "停止前端服务 (PID: $FRONTEND_PID)..."
            kill -9 "$FRONTEND_PID" 2>/dev/null
            rm -f "$FRONTEND_PID_FILE"
            echo -e "${GREEN}✓ 前端服务已停止${NC}"
        else
            rm -f "$FRONTEND_PID_FILE"
            echo -e "${YELLOW}○ 前端服务未运行${NC}"
        fi
    else
        echo -e "${YELLOW}○ 前端服务未启动${NC}"
    fi

    # 清理其他可能的进程
    pkill -9 -f "uvicorn.*8002" 2>/dev/null
    pkill -9 -f "vite.*3000" 2>/dev/null

    echo ""
    echo -e "${GREEN}所有服务已停止${NC}"
}

# 启动服务
start_services() {
    echo "=== 启动服务 ==="
    echo ""

    # 检查是否已有服务在运行
    check_status
    echo ""

    # 启动后端
    echo "启动后端服务..."
    cd /workspace
    nohup python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8002 --reload > "$LOG_DIR/backend.log" 2>&1 &
    echo $! > "$BACKEND_PID_FILE"
    BACKEND_PID=$(cat "$BACKEND_PID_FILE")
    echo -e "${GREEN}✓ 后端服务已启动${NC} (PID: $BACKEND_PID)"
    sleep 2

    # 启动前端
    echo "启动前端服务..."
    cd /workspace/src
    nohup npm run dev > "$LOG_DIR/frontend.log" 2>&1 &
    echo $! > "$FRONTEND_PID_FILE"
    FRONTEND_PID=$(cat "$FRONTEND_PID_FILE")
    echo -e "${GREEN}✓ 前端服务已启动${NC} (PID: $FRONTEND_PID)"
    sleep 3

    echo ""
    echo "等待服务启动完成..."
    sleep 2

    # 健康检查
    health_check
}

# 重启服务
restart_services() {
    echo "=== 重启服务 ==="
    echo ""
    stop_services
    echo ""
    start_services
}

# 健康检查
health_check() {
    echo "=== 健康检查 ==="
    echo ""

    # 检查后端
    BACKEND_STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8002/docs 2>/dev/null)
    if [ "$BACKEND_STATUS" = "200" ]; then
        echo -e "${GREEN}✓ 后端服务正常${NC} (http://localhost:8002)"
    else
        echo -e "${RED}✗ 后端服务异常${NC} (状态码: $BACKEND_STATUS)"
    fi

    # 检查前端
    FRONTEND_STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:3000 2>/dev/null)
    if [ "$FRONTEND_STATUS" = "200" ]; then
        echo -e "${GREEN}✓ 前端服务正常${NC} (http://localhost:3000)"
    else
        echo -e "${RED}✗ 前端服务异常${NC} (状态码: $FRONTEND_STATUS)"
    fi

    echo ""
    echo "后端API文档: http://localhost:8002/docs"
    echo "前端应用: http://localhost:3000"
    echo ""
}

# 查看日志
show_logs() {
    echo "=== 服务日志 ==="
    echo ""

    if [ -f "$LOG_DIR/backend.log" ]; then
        echo "后端日志 (最后20行):"
        echo "----------------------------------------"
        tail -20 "$LOG_DIR/backend.log"
        echo "----------------------------------------"
        echo ""
    else
        echo "后端日志文件不存在"
        echo ""
    fi

    if [ -f "$LOG_DIR/frontend.log" ]; then
        echo "前端日志 (最后20行):"
        echo "----------------------------------------"
        tail -20 "$LOG_DIR/frontend.log"
        echo "----------------------------------------"
        echo ""
    else
        echo "前端日志文件不存在"
        echo ""
    fi
}

# 主函数
main() {
    case "$1" in
        start)
            start_services
            ;;
        stop)
            stop_services
            ;;
        restart)
            restart_services
            ;;
        status)
            check_status
            ;;
        logs)
            show_logs
            ;;
        health)
            health_check
            ;;
        help|--help|-h)
            show_help
            ;;
        *)
            echo "未知命令: $1"
            echo ""
            show_help
            exit 1
            ;;
    esac
}

# 执行主函数
main "$@"