# CodingMatrix 文档中心

> 最后更新：2026-05-26 | 版本：v5.9.0（API Key 全局化 + Token 统计）

## 快速导航

### 入门必读
- [快速开始](guides/GETTING-STARTED.md) - 环境配置、快速启动
- [多供应商配置](guides/MULTI_PROVIDER_SETUP.md) - 7 个 LLM 供应商配置
- [测试文档](testing/TESTING.md) - 111+ 测试文件，850+ 测试用例

### 核心架构
- [系统架构](architecture/ARCHITECTURE.md) - v5.9.0 完整架构
- [模块说明](architecture/MODULES.md) - 代码结构、职责划分
- [模型系统](architecture/MODELS.md) - 多供应商 LLM 适配器

### API 与功能
- [API 文档](api/) - 25+ 个 API 端点完整文档
- [Agent 系统](features/agent.md) - 多角色协作、项目生成
- [AI 云管理](features/aicloud.md) - 模型切换、故障转移

### 部署运维
- [生产部署](guides/PRODUCTION.md) - Docker Compose、服务管理
- [后端端口](#端口说明) - 重要：8000 端口统一服务

## 项目概览

### 技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| 后端 | FastAPI + Python 3.11 | 异步 Web 框架 |
| 数据库 | SQLAlchemy + SQLite | 异步 ORM |
| 缓存 | Redis | 会话、API Key 存储 |
| 任务队列 | Celery | 异步任务处理 |
| 前端 | Vue 3 + Vite + Pinia | 响应式 SPA |
| 测试 | Playwright + pytest | E2E + 单元测试 |
| 部署 | Docker + Nginx | 容器化部署 |

### 代码统计

| 模块 | 文件数 | 说明 |
|------|--------|------|
| 后端 API | 19+ | FastAPI 路由 |
| Agent 系统 | 58 | 多角色协作编排 |
| 数据库模型 | 24 | SQLAlchemy ORM |
| 前端视图 | 7 | 主页面组件 |
| 前端组件 | 44 | 可复用组件 |
| Pinia Store | 6 | 状态管理 |
| 测试文件 | 111+ | 850+ 测试用例 |

### v5.9.0 核心特性

- **API Key 全局化**: 所有前端功能（项目生成、代码对话、PPT、图像生成、AI Cloud）均使用用户自定义 API Key
- **Token 使用统计**: 设置页面展示今日/本月/总计 Token 消耗量，按模型分类
- **RSA-2048 加密**: API Key 通过 RSA 加密传输，Redis 内存存储，支持 TTL 自动过期
- **7 供应商支持**: SiliconFlow（必填）、阿里百炼、智谱 GLM、DeepSeek、OpenAI、Anthropic、Ollama
- **智能故障转移**: 主供应商失败自动切换备用供应商

### v5.8.x 核心特性

- **KV Cache 命中率优化**: 静态前缀缓存、动态变量清理、JSON 键固定顺序
  - 缓存命中率：~0% → 75-97%
  - 延迟降低：≥20%
- **多角度审查系统**: 3 个专业审查角色并行执行
  - 性能师：N+1 查询/大数据量/缓存策略/内存泄漏/并发问题
  - 安全师：SQL 注入/XSS/越权/敏感数据/认证缺陷/输入验证
  - 可维护性师：代码清晰度/模块耦合/代码重复/设计模式/测试友好性

### 功能模块

| 模块 | 端点 | 功能 |
|------|------|------|
| Agent 系统 | `/api/v1/agent/*` | 项目生成、代码审查、快照管理 |
| AI 代码 | `/api/v1/code` | 代码生成、流式输出 |
| PPT 生成 | `/api/v1/pptx/*` | 异步任务、多格式输出 |
| 图像生成 | `/api/v1/kolors/*` | 文生图、图生图 |
| AI Cloud | `/api/v1/aicloud/*` | 沙箱执行、审查队列 |
| 文件管理 | `/api/v1/files/*` | 分片上传、去重、解析缓存 |
| 工作流 | `/api/v1/workflow/*` | DAG 编排、9 种节点、重试机制 |
| 用户管理 | `/api/v2/Controller/*` | CRUD、权限管理 |
| 健康检查 | `/api/v1/health` | Prometheus 指标 |

## 文档结构

```
docs/
├── INDEX.md                     # 文档索引
├── README.md                    # 本文件
├── TECH-DEBT.md                 # 技术债务跟踪
├── PERMISSION-SPEC.md           # 权限规范
├── SERVICES.md                  # 服务架构
├── architecture/                # 架构设计
├── api/                         # API 文档
├── features/                    # 功能模块
├── guides/                      # 开发指南
├── security/                    # 安全文档
├── observability/               # 可观测性
├── testing/                     # 测试文档
├── prompts/                     # AI 提示词
├── skills/                      # Skills 文档
├── specs/                       # 规格设计
└── versions/                    # 版本历史
```

## 端口说明

重要：后端服务统一在 8000 端口提供前后端服务

```bash
# 启动后端 (包含前端 dist)
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000

# 访问前端
http://localhost:8000

# API 端点
http://localhost:8000/api/v1/health
```

## 测试说明

### E2E 测试 (Playwright)

- 48 个测试文件，200+ 测试用例
- 冒烟测试 5/5 通过 (100%)
- 执行时间：18.3 秒

```bash
# 运行冒烟测试 (推荐日常使用)
npx playwright test tests/e2e/smoke-test-simple.spec.js

# 运行所有 E2E
npx playwright test tests/e2e/

# 查看报告
npx playwright show-report
```

### 单元测试 (Pytest)

- 40+ 测试文件，500+ 测试用例
- 覆盖率：~95%

```bash
# 运行单元测试
pytest tests/unit/ -v

# 运行特定测试
pytest tests/unit/test_aicloud.py -v
```

### 集成测试

- 20+ 测试文件，150+ 测试用例
- 覆盖率：~90%

```bash
# 运行集成测试
pytest tests/integration/ -v
```

## 已知问题

### 严重 Bug

1. **启动时清空 history 表**: `on_startup()` 调用 `clear_history_table()` 会删除所有对话历史
2. **权限检查值不匹配**: `require_superadmin` 检查 `"super"` 但系统定义为 `"superadmin"`
3. **路由器重复注册**: `adminConfigRouter` 被注册两次导致路由冲突
4. **缺少导入**: `drain_mode_middleware` 使用 `JSONResponse` 但未导入

### 高危问题

5. **Celery 信号中错误使用 asyncio**: 同步函数中调用 `asyncio.create_task()` 无事件循环
6. **datetime.utcnow() 无时区**: 多处使用已弃用的无时区时间函数
7. **WebSocket 单连接限制**: 同一用户新连接会覆盖旧连接
8. **CORS 正则构造错误**: 主机名点号未转义

详见 [TECH-DEBT.md](TECH-DEBT.md)

## 版本历史

| 版本 | 日期 | 主要更新 |
|------|------|----------|
| v5.9.0 | 2026-05-26 | API Key 全局化 + Token 统计 |
| v5.8.1 | 2026-05-23 | KV Cache 优化 + 多角度审查系统 |
| v5.7.0 | 2026-05-23 | 批量操作 + 审计日志 |
| v5.6.0 | 2026-05-23 | CI/CD集成 |
| v5.5.0 | 2026-05-23 | 多供应商 API Key 管理 |
| v5.4.0 | 2026-05-22 | 多供应商模型 + E2E 测试完成 |

详细版本历史见 [versions/](versions/) 目录

## 相关资源

- [完整文档索引](INDEX.md)
- [技术债务](TECH-DEBT.md)
- [权限规范](PERMISSION-SPEC.md)
- [服务架构](SERVICES.md)

---

最后更新：2026-05-26
