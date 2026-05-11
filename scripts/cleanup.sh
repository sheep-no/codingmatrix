#!/bin/bash
# 清理脚本 - 清理缓存和临时文件

set -e

echo "======================================"
echo "清理项目"
echo "======================================"

# 清理 Python 缓存
echo "清理 Python 缓存..."
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find . -type f -name "*.pyc" -delete 2>/dev/null || true
find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true

# 清理测试缓存
echo "清理测试缓存..."
rm -rf htmlcov/ .coverage .tox/ .nox/ 2>/dev/null || true

# 清理 IDE 配置
echo "清理 IDE 配置..."
rm -rf .idea/ .vscode/ 2>/dev/null || true

# 清理日志
echo "清理日志文件..."
rm -rf logs/*.log 2>/dev/null || true

# 清理上传文件
echo "清理上传文件..."
rm -rf uploads/* 2>/dev/null || true

# 清理工作区
echo "清理工作区..."
rm -rf workspace/* 2>/dev/null || true

# 清理输出目录
echo "清理输出目录..."
rm -rf output/* 2>/dev/null || true

echo ""
echo "✅ 清理完成"
echo ""
echo "注意：以下文件未被清理:"
echo "  - app.db (数据库)"
echo "  - .env (环境配置)"
echo "  - .git/ (Git 仓库)"
echo "  - docs/ (文档)"
