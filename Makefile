.PHONY: help dev test lint format clean migrate install

# 默认目标
help:
	@echo "======================================"
	@echo "Makefile - 项目快捷命令"
	@echo "======================================"
	@echo ""
	@echo "可用命令:"
	@echo "  make install     - 安装依赖"
	@echo "  make dev         - 启动开发服务器"
	@echo "  make prod        - 启动生产服务器"
	@echo "  make test        - 运行测试"
	@echo "  make test-cov    - 运行测试并生成覆盖率报告"
	@echo "  make lint        - 代码检查"
	@echo "  make format      - 代码格式化"
	@echo "  make migrate     - 数据库迁移"
	@echo "  make clean       - 清理缓存和临时文件"
	@echo "  make logs        - 查看日志"
	@echo ""

# 安装依赖
install:
	pip install -r configs/requirements.txt

# 启动开发服务器
dev:
	@echo "启动开发服务器..."
	python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 启动生产服务器
prod:
	@echo "启动生产服务器..."
	gunicorn app.main:app \
		-w 4 \
		-k uvicorn.workers.UvicornWorker \
		--bind 0.0.0.0:8000

# 运行测试
test:
	pytest tests/ -v

# 运行测试并生成覆盖率报告
test-cov:
	pytest tests/ --cov=app --cov-report=html
	@echo "覆盖率报告已生成：htmlcov/index.html"

# 代码检查
lint:
	flake8 app/ tests/
	@echo "✅ 代码检查通过"

# 代码格式化
format:
	black app/ tests/
	isort app/ tests/
	@echo "✅ 代码格式化完成"

# 数据库迁移
migrate:
	alembic upgrade head
	@echo "✅ 数据库迁移完成"

# 创建新迁移
migrate-revision:
	@read -p "请输入迁移描述：" desc; \
	alembic revision -m "$$desc"

# 清理缓存
clean:
	@./scripts/cleanup.sh

# 查看日志
logs:
	tail -f logs/app.log

# 初始化项目
init: install migrate
	@echo ""
	@echo "✅ 项目初始化完成"
	@echo ""
	@echo "下一步:"
	@echo "  1. 编辑 .env 文件配置环境变量"
	@echo "  2. 运行 'make dev' 启动开发服务器"
	@echo "  3. 访问 http://localhost:8000/docs"
