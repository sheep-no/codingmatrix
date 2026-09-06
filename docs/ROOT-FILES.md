# 根目录文件说明

> 最后核对：2026-09-03

## 目录结构

```
/workspace/
├── app/                         # 后端 FastAPI 应用
├── src/                         # 前端 Vue 3 应用
├── tests/                       # 测试 (Pytest + Playwright)
│   ├── unit/                    # 单元测试
│   ├── integration/             # 集成测试
│   ├── e2e/                     # Playwright 端到端测试
│   └── manual/                  # 需要运行服务的手工接口流程测试
├── docs/                        # 文档
├── scripts/                     # 运维脚本
│   ├── *.sh                     # Linux/Mac脚本
│   ├── *.bat                    # Windows 批处理
│   └── _archive/                # 归档的旧脚本
│
├── configs/                     # 配置文件
│   ├── alembic.ini              # 数据库迁移配置
│   ├── requirements.txt         # Python 依赖
│   ├── requirements-test.txt    # 测试依赖
│   ├── pytest.ini               # Pytest 配置
│   ├── .coveragerc              # 覆盖率配置
│   ├── nginx.conf               # Nginx 配置
│   ├── prometheus.yml           # Prometheus 配置
│   └── playwright.config.js     # Playwright 多浏览器配置
│
├── .git/                        # Git 仓库
├── .claude/                     # AI Agent 配置
├── .monkeycode/                 # MonkeyCode 项目文档
├── .github/                     # GitHub CI/CD
│
├── cache/                       # 缓存目录
├── data/                        # 数据目录 (SQLite)
├── keys/                        # 密钥目录 (RSA)
├── logs/                        # 日志目录
├── migrations/                  # Alembic 迁移
├── projects/                    # 用户项目上传
├── sessions/                    # Agent 会话数据
├── skills/                      # Workflow planner Skill
├── vscode-extension/            # VS Code Agent Host 扩展
├── pptx_output/                 # PPT 运行产物
└── uploads/                     # 上传文件
```

## 根目录文件清单

### 环境配置文件

| 文件 | 说明 |
|------|------|
| `.env` | 当前本地环境变量配置，属于敏感运行数据 |
| `.env.test` | 本地测试账号与测试环境配置，属于敏感运行数据 |
| `.env.example` | 开发环境变量模板 |
| `.env.production.example` | 生产环境变量模板 |

### Docker 配置

| 文件 | 说明 |
|------|------|
| `docker-compose.yml` | Docker Compose 开发配置 |
| `docker-compose.prod.yml` | Docker Compose 生产配置 |
| `Dockerfile` | Docker 镜像构建文件 |

### 项目配置

| 文件 | 说明 |
|------|------|
| `pyproject.toml` | pytest 与 coverage 主配置 |
| `package.json`、`package-lock.json` | 根目录 Playwright E2E 工程，只定义 `test:e2e` |
| `playwright.config.js` | 根目录默认 Chromium E2E 配置 |
| `src/package.json` | Vue、Vite、Vitest、lint 和前端构建脚本 |
| `Makefile` | 开发、测试、覆盖率、迁移等快捷命令 |
| `.gitignore` | Git 忽略规则 |

### 根文档与生成索引

| 文件 | 说明 |
|------|------|
| `README.md` | 项目根目录说明 |
| `CHANGELOG.md` | 版本变更日志 |
| `PROMPTS.md` | prompts extractor 生成的根目录提示词索引 |
| `data.json` | 当前根目录数据文件；用途由消费代码或运行流程确认 |

### 当前根运行数据

| 文件 | 说明 |
|------|------|
| `app.db` | 默认 SQLite 数据库 |

缓存、日志、测试报告、生成图片、PPT、上传文件和用户项目分别位于 `cache/`、`logs/`、`playwright-report/`、`test-results/`、`generated_images/`、`pptx_output/`、`uploads/` 和 `projects/`。这些目录的保留策略由运行环境决定。

---

## Scripts 目录整理

### 保留的脚本 (scripts/)

| 脚本 | 平台 | 说明 |
|------|------|------|
| `start.sh` | Linux/Mac | **当前不可用入口**：将 `scripts/` 误作项目根，且无参数时只显示状态 |
| `start-backend.sh` | Linux/Mac | 仅启动后端 |
| `stop.sh` | Linux/Mac | 停止服务 |
| `logs.sh` | Linux/Mac | 查看日志 |
| `status.sh` | Linux/Mac | 查看服务状态 |
| `migrate.sh` | Linux/Mac | **当前不可用入口**：未指定实际配置 `configs/alembic.ini` |
| `dev.sh` | Linux/Mac | 开发模式启动 |
| `test.sh` | Linux/Mac | 运行测试 |
| `verify-integration.sh` | Linux/Mac | 集成验证 |
| `start.bat` | Windows | Windows 启动脚本 |
| `stop.bat` | Windows | Windows 停止脚本 |
| `logs.bat` | Windows | Windows 日志查看 |
| `status.bat` | Windows | Windows 状态查看 |

### 已归档的脚本（`scripts/_archive/`）

| 脚本 | 类型 | 归档原因 |
|------|------|----------|
| `build_dependency_graph.py` | Python | 已集成到 app/agent/dependency_graph.py |
| `check_guard.py` | Python | 已迁移到 app/services/ |
| `manage_logs.py` | Python | 功能由 logs.sh 替代 |
| `trigger_keyword.py` | Python | 已弃用的触发器功能 |
| `migrate_add_conversation_id.py` | Python | 一次性迁移脚本 |
| `migrate_history_metadata.py` | Python | 一次性迁移脚本 |
| `verify-dependencies.py` | Python | 功能由 verify-integration.sh 替代 |
| `cleanup.sh` | Shell | 功能由 stop.sh + 手动清理替代 |
| `run-e2e-tests.sh` | Shell | 统一使用 `npx playwright test` |
| `test_api_endpoints.sh` | Shell | 已弃用的 API 测试 |
| `monitor_api.sh` | Shell | 功能已由监控系统替代 |
| `manage-services.sh` | Shell | 功能由 docker-compose 替代 |
| `playwright.config.js` | Config | E2E 默认配置入口；详细多浏览器配置位于 `configs/` |
| `windows/` | Windows | 已整理到 scripts/ 根目录 |

---

## 常用命令

### 启动服务

```bash
# 启动后端（在仓库根目录执行）
PYTHONPATH=/workspace python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# 另开终端启动前端；Vite 将 /api/v1 和 /api/v2 代理到 8000
npm --prefix src run dev

# Docker Compose 启动
docker-compose up -d
```

`scripts/start.sh` 当前无法作为启动入口：脚本用自身目录计算 `PROJECT_DIR`，因此会在 `scripts/` 下查找 `.env`、`src/` 和 `configs/`；直接调用时默认进入 `menu/status` 分支。

### 查看日志

```bash
# 查看所有日志
./scripts/logs.sh

# 查看实时日志
tail -f logs/app.log

# Docker 日志
docker-compose logs -f
```

### 数据库迁移

```bash
# 从仓库根目录运行迁移
alembic -c configs/alembic.ini upgrade head
```

`scripts/migrate.sh` 当前未传 `-c configs/alembic.ini`，仓库根目录也没有默认 `alembic.ini`，因此不能作为迁移入口。既有数据库首次接入当前迁移链时，先执行 `alembic -c configs/alembic.ini stamp 20260902_ppt_quality_state`，再执行上述升级命令。

### 运行测试

```bash
# 单元测试
pytest tests/unit/ -v

# E2E 测试
npx playwright test tests/e2e/

# 冒烟测试 (推荐)
npx playwright test tests/e2e/smoke-test-simple.spec.js
```

### 查看状态

```bash
# 服务状态
./scripts/status.sh

# 进程检查
ps aux | grep uvicorn

# 端口检查
lsof -i :8000
```

---

## 配置文件说明

### pyproject.toml

```toml
[tool.coverage.run]
branch = true
source = ["app", "src"]

[tool.pytest.ini_options]
testpaths = ["tests/unit", "tests/integration"]
python_files = ["test_*.py"]
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "function"

[tool.coverage.report]
fail_under = 70
show_missing = true
precision = 2
```

### playwright.config.js

```javascript
module.exports = {
  testDir: './tests/e2e',
  fullyParallel: true,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: 'html',
  use: { baseURL: process.env.BASE_URL || 'http://127.0.0.1:3000' },
}
```

---

最后核对：2026-09-03
