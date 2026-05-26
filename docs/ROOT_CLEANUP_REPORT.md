# 根目录与 Scripts 目录整理报告

> 整理日期：2026-05-23 | 版本：v5.8.0

## 整理成果

### 1. Scripts 目录整理

#### 保留的脚本 (12 个)

| 脚本 | 平台 | 大小 | 说明 |
|------|------|------|------|
| `start.sh` | Linux/Mac | 7.6K | **主启动脚本** (前后端一起启动) |
| `start-backend.sh` | Linux/Mac | 623B | 仅启动后端 (uvicorn) |
| `start.bat` | Windows | 3.0K | Windows 启动脚本 |
| `stop.sh` | Linux/Mac | 934B | 停止服务 (kill 进程) |
| `stop.bat` | Windows | 819B | Windows 停止脚本 |
| `logs.sh` | Linux/Mac | 873B | 查看日志 (tail) |
| `logs.bat` | Windows | 1.4K | Windows 日志查看 |
| `status.sh` | Linux/Mac | 1.6K | 查看服务状态 (ps/port) |
| `status.bat` | Windows | 1.3K | Windows 状态查看 |
| `migrate.sh` | Linux/Mac | 489B | 数据库迁移 (Alembic) |
| `dev.sh` | Linux/Mac | 514B | 开发模式启动 |
| `test.sh` | Linux/Mac | 416B | 运行测试 (pytest) |
| `verify-integration.sh` | Linux/Mac | 4.6K | 集成验证脚本 |

#### 已归档的脚本 (_archive/)

**归档原因**: 这些脚本已过时、重复或功能已集成到主代码中。

| 脚本 | 类型 | 大小 | 归档原因 |
|------|------|------|----------|
| `build_dependency_graph.py` | Python | 15K | 已集成到 `app/agent/dependency_graph.py` |
| `check_guard.py` | Python | 8.8K | 已迁移到 `app/services/` |
| `manage_logs.py` | Python | 8.2K | 功能由 `logs.sh` 替代 |
| `trigger_keyword.py` | Python | 6.6K | 已弃用的触发器功能 |
| `migrate_add_conversation_id.py` | Python | 1.8K | 一次性迁移脚本 (已完成) |
| `migrate_history_metadata.py` | Python | 1.5K | 一次性迁移脚本 (已完成) |
| `verify-dependencies.py` | Python | 3.4K | 功能由 `verify-integration.sh` 替代 |
| `cleanup.sh` | Shell | 1.3K | 功能由 `stop.sh` + 手动清理替代 |
| `manage-services.sh` | Shell | 6.4K | 功能由 `docker-compose` 替代 |
| `run-e2e-tests.sh` | Shell | 2.4K | 统一使用 `npx playwright test` |
| `test_api_endpoints.sh` | Shell | 1.8K | 已弃用的 API 测试 |
| `monitor_api.sh` | Shell | 1.9K | 功能已由监控系统替代 |
| `playwright.config.js` | Config | 740B | 已升级为`playwright.config.ts` |
| `windows/` | Directory | - | Windows 脚本已整理到 scripts/根目录 |

**归档目录**: `scripts/_archive/` (13 个文件)

### 2. 根目录整理

#### 删除的临时文件

| 文件 | 大小 | 删除原因 |
|------|------|----------|
| `frontend_diagnosis.json` | 363B | 临时诊断输出 |
| `main.py` | 919B | 临时入口 (已不使用) |

#### 保留的根目录文件

##### 环境配置 (3 个)

| 文件 | 大小 | 说明 |
|------|------|------|
| `.env` | 4KB | 当前环境变量配置 (**已 gitignore**) |
| `.env.example` | 5KB | 开发环境变量模板 |
| `.env.production.example` | 1KB | 生产环境变量模板 |

##### Docker 配置 (3 个)

| 文件 | 大小 | 说明 |
|------|------|------|
| `docker-compose.yml` | 3KB | Docker Compose 开发配置 |
| `docker-compose.prod.yml` | 3KB | Docker Compose 生产配置 |
| `Dockerfile` | 3KB | Docker 镜像构建文件 |

##### 项目配置 (5 个)

| 文件 | 大小 | 说明 |
|------|------|------|
| `pyproject.toml` | 1KB | Python 项目配置 (PEP 518) |
| `playwright.config.ts` | 2KB | Playwright E2E 测试配置 |
| `package.json` | <1KB | Node.js 依赖 (仅 Playwright) |
| `package-lock.json` | 8KB | Node.js 依赖锁定 |
| `Makefile` | 2KB | Make 命令集 |

##### 文档 (3 个)

| 文件 | 大小 | 说明 |
|------|------|------|
| `README.md` | 4KB | 项目根目录说明 |
| `CHANGELOG.md` | 9KB | 版本变更日志 |
| `README.ROOT.md` | 7KB | 根目录文件详细说明 (**新增**) |

##### 数据库与缓存 (gitignore, 4 个)

| 文件 | 大小 | 说明 |
|------|------|------|
| `app.db` | 315KB | SQLite 数据库 (**生产数据**) |
| `dev.db` | 0KB | 开发数据库 (空) |
| `dump.rdb` | 231B | Redis 数据快照 |
| `cookies.txt` | 221B | 测试 Cookies |

##### Git 配置 (1 个)

| 文件 | 大小 | 说明 |
|------|------|------|
| `.gitignore` | 1KB | Git 忽略规则 |

---

## 整理前后对比

| 项目 | 整理前 | 整理后 | 改善 |
|------|--------|--------|------|
| scripts/ 目录下 Python 脚本 | 7 个 | 0 个 | ✅ 全部归档 |
| scripts/ 目录下一次性脚本 | 4 个 | 0 个 | ✅ 全部归档 |
| 根目录临时文件 | 2 个 | 0 个 | ✅ 全部删除 |
| 重复 Playwright 配置 | 2 个 | 1 个 | ✅ 保留.ts 版本 |
| Windows 脚本分散 | 3 个 (scripts/windows/) | 0 个 | ✅ 集中到 scripts/ |
| 归档文件数量 | - | 14 个 | ✅ 有序归档 |

---

## 使用指南

### 快速启动

```bash
# 推荐：使用主启动脚本
./scripts/start.sh

# 仅启动后端
./scripts/start-backend.sh

# Docker Compose 启动
docker-compose up -d
```

### 常用命令

```bash
# 查看服务状态
./scripts/status.sh

# 查看日志
./scripts/logs.sh

# 数据库迁移
./scripts/migrate.sh

# 运行测试
./scripts/test.sh
npx playwright test tests/e2e/

# 停止服务
./scripts/stop.sh
```

---

## 目录结构

```
/workspace/
├── app/                         # 后端 FastAPI
├── src/                         # 前端 Vue 3
├── tests/                       # 测试
├── docs/                        # 文档
├── scripts/                     # 运维脚本 ⭐ 已整理
│   ├── *.sh                     # Linux/Mac 脚本 (9 个)
│   ├── *.bat                    # Windows 脚本 (4 个)
│   └── _archive/                # 归档的旧脚本 (14 个)
├── configs/                     # 配置文件
├── .env                         # 环境变量 (已 gitignore)
├── .env.example                 # 环境变量模板
├── docker-compose.yml           # Docker 配置
├── pyproject.toml               # Python 配置
├── playwright.config.ts         # Playwright 配置
├── Makefile                     # Make 命令
├── README.md                    # 项目说明
├── README.ROOT.md               # 根目录说明 ⭐ 新增
└── CHANGELOG.md                 # 变更日志
```

---

## 后续建议

### 可进一步优化的项目

1. **dev.db** (0KB): 空的开发数据库，如无特殊用途可删除
2. **cookies.txt** (221B): 测试凭证，如不再使用可删除
3. **app.db** (315KB): 生产数据库，删除前需备份数据

### 归档文件处理

`scripts/_archive/` 中的文件可以：
- **保留**: 作为历史参考
- **删除**: 如确认不再需要，可定期清理
- **版本控制**: 建议提交到 Git，便于追溯历史

---

## 配置文件说明

### pyproject.toml (Python 配置)

```toml
[project]
name = "codingmatrix"
version = "5.8.0"
requires-python = ">=3.11"

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests/unit", "tests/integration"]
```

### playwright.config.ts (E2E 测试配置)

```typescript
export default {
  testDir: './tests/e2e',
  timeout: 30000,
  retries: 2,
  workers: 4,
  reporter: [['html'], ['list']],
}
```

### docker-compose.yml (开发环境)

```yaml
version: '3.8'
services:
  backend:
    build: .
    ports:
      - "8000:8000"
    volumes:
      - ./data:/app/data
    environment:
      - DATABASE_URL=sqlite+aiosqlite:///data/app.db
  redis:
    image: redis:alpine
    ports:
      - "6379:6379"
```

---

整理完成时间：2026-05-23  
整理执行者：AI Assistant
