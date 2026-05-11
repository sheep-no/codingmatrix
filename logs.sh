#!/bin/bash
# 查看 AI Agent 日志

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

if [ "$1" = "error" ]; then
    echo "========== Error Log =========="
    tail -100 "$PROJECT_DIR/logs/error.log" 2>/dev/null || echo "无错误日志"
elif [ "$1" = "access" ]; then
    echo "========== Access Log =========="
    tail -100 "$PROJECT_DIR/logs/access.log" 2>/dev/null || echo "无访问日志"
elif [ "$1" = "full" ]; then
    echo "========== Full Error Log =========="
    cat "$PROJECT_DIR/logs/error.log" 2>/dev/null || echo "无错误日志"
else
    echo "用法: $0 [error|access|full]"
    echo "  error  - 查看最近错误日志 (默认)"
    echo "  access - 查看最近访问日志"
    echo "  full   - 查看完整错误日志"
    echo ""
    tail -50 "$PROJECT_DIR/logs/error.log" 2>/dev/null || echo "无错误日志"
fi