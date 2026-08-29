# 根目录文件说明

> 最后更新：2026-08-29 | 版本：v5.10.0

## 📁 目录结构

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
```

## 根目录文件清单

### 环境配置文件 (保留)

| 文件 | 大小 | 说明 |
|------|------|------|
| `.env` | 4KB | 当前环境变量配置 (已 gitignore) |
| `.env.example` | 5KB | 开发环境变量模板 |
| `.env.production.example` | 1KB | 生产环境变量模板 |

### Docker 配置 (保留)

| 文件 | 大小 | 说明 |
|------|------|------|
| `docker-compose.yml` | 3KB | Docker Compose 开发配置 |
| `docker-compose.prod.yml` | 3KB | Docker Compose 生产配置 |
| `Dockerfile` | 3KB | Docker 镜像构建文件 |

### 项目配置 (保留)

| 文件 | 大小 | 说明 |
|------|------|------|
| `pyproject.toml` | 1KB | Python 项目配置 (PEP 518) |
| `configs/playwright.config.js` | 2KB | Playwright 多浏览器测试配置 |
| `src/package.json` | 2KB | 前端 Node.js 依赖和 Vite 脚本 |
| `Makefile` | 2KB | Make 命令集 |
| `.gitignore` | 1KB | Git 忽略规则 |

### 文档文件 (保留)

| 文件 | 大小 | 说明 |
|------|------|------|
| `README.md` | 4KB | 项目根目录说明 |
| `CHANGELOG.md` | 9KB | 版本变更日志 |

### 数据库文件 (gitignore)

| 文件 | 状态 | 说明 |
|------|------|------|
| `app.db` | 315KB | SQLite 数据库 |
| `dev.db` | 0KB | 开发数据库 (空) |
| `dump.rdb` | <1KB | Redis 数据快照 |
| `cookies.txt` | <1KB | 测试 Cookies |

### 临时文件 (gitignore)

| 文件 | 状态 | 说明 |
|------|------|------|
| `frontend_diagnosis.json` | <1KB | 前端诊断输出 |
| `main.py` | <1KB | 临时入口 (已不使用) |

---

## Scripts 目录整理

### 保留的脚本 (scripts/)

| 脚本 | 平台 | 说明 |
|------|------|------|
| `start.sh` | Linux/Mac | 主启动脚本 (前后端一起启动) |
| `start-backend.sh` | Linux/Mac | 仅启动后端 |
| `stop.sh` | Linux/Mac | 停止服务 |
| `logs.sh` | Linux/Mac | 查看日志 |
| `status.sh` | Linux/Mac | 查看服务状态 |
| `migrate.sh` | Linux/Mac | 数据库迁移 |
| `dev.sh` | Linux/Mac | 开发模式启动 |
| `test.sh` | Linux/Mac | 运行测试 |
| `verify-integration.sh` | Linux/Mac | 集成验证 |
| `start.bat` | Windows | Windows 启动脚本 |
| `stop.bat` | Windows | Windows 停止脚本 |
| `logs.bat` | Windows | Windows 日志查看 |
| `status.bat` | Windows | Windows 状态查看 |

### 已归档的脚本 (scripts/_archive/)

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
# 开发环境 (推荐)
./scripts/start.sh

# 仅启动后端
./scripts/start-backend.sh

# Docker Compose 启动
docker-compose up -d
```

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
# 运行迁移
./scripts/migrate.sh

# 或直接使用 Alembic
cd configs && alembic upgrade head
```

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

## 清理建议

### 可安全删除的文件

```bash
# 临时文件
rm -f frontend_diagnosis.json
rm -f main.py

# 空数据库
rm -f dev.db

# 过期日志
./scripts/logs.sh --clean
```

### 不可删除的文件

- `.env` - 当前配置 (删除前请备份)
- `app.db` - 生产数据库
- `dump.rdb` - Redis 持久化数据
- `cookies.txt` - 测试凭证

---

## 配置文件说明

### pyproject.toml

```toml
[project]
name = "codingmatrix"
version = "5.8.0"
requires-python = ">=3.11"

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests/unit", "tests/integration"]
```

### playwright.config.js

```javascript
module.exports = {
  testDir: './tests/e2e',
  timeout: 30000,
  retries: 2,
  workers: 4,
  reporter: [['html'], ['list']],
}
```

---

最后更新：2026-05-23
