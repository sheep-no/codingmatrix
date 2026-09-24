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
# alembic.ini 位于 configs/，其 script_location 与 prepend_sys_path 以 %(here)s
# 相对定位，从仓库根执行时必须显式指定，否则 alembic 找不到配置文件
alembic -c configs/alembic.ini upgrade head

echo "✅ 迁移完成"
echo ""
echo "数据库：${DATABASE_URL:-(由 app/core/config.py 的 DATABASE_URL 决定)}"
echo "当前版本:"
# 迁移链含分支与 merge，history 的 rev-range 回溯会报 Ambiguous walk，用 current
alembic -c configs/alembic.ini current
