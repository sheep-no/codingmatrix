#!/bin/bash
# 数据库迁移脚本

set -e

echo "======================================"
echo "数据库迁移脚本"
echo "======================================"

# 检查 alembic 是否安装
if ! command -v alembic &> /dev/null; then
    echo "错误：alembic 未安装，请先安装依赖"
    exit 1
fi

# 执行迁移
echo "执行数据库迁移..."
alembic upgrade head

echo "✅ 迁移完成"
echo ""
echo "数据库文件：app.db"
echo "迁移历史:"
alembic history -n 3
