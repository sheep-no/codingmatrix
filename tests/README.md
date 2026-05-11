# 测试套件文档

## 目录结构

```
tests/
── conftest.py              # 测试夹具和固定配置
├── __init__.py
├── README.md                # 本文档
├── QUICKSTART.md            # 快速开始指南
├── e2e/                     # Playwright E2E 测试 (前端)
│   ├── auth.spec.js         # 认证流程测试 (7 个测试)
│   ├── chat.spec.js         # 聊天功能测试 (6 个测试)
│   ├── core.spec.js         # 核心功能测试 (7 个测试)
│   ├── tools.spec.js        # 工具面板测试 (7 个测试)
│   └── README.md            # E2E 测试说明
├── unit/                    # 单元测试 (后端)
│   ├── conftest.py
│   ├── test_aicloud.py
│   ├── test_comprehensive.py
│   ├── test_database_services.py
│   ├── test_executor.py
│   ├── test_graph_validator.py
│   ├── test_node_types.py
│   ├── test_result_aggregator.py
│   ├── test_small_model_optimization.py
│   ├── test_state_machine.py
│   ├── test_system_monitor.py
│   ├── test_task_decomposer.py
│   └── test_utils.py
├── integration/             # 集成测试 (后端)
│   ├── test_aicloud_api.py
│   ├── test_dynamic_model_router.py
│   ├── test_task_queue_integration.py
│   └── test_workflow_integration.py
└── archive/                 # 归档的历史测试文件
    ├── playwright/          # 旧版 Playwright 独立脚本
    └── legacy/              # 旧版 Python 测试文件
```

## 运行测试

### 前端 E2E 测试 (Playwright)

```bash
# 运行所有 E2E 测试
npx playwright test --project=chromium

# 运行特定测试文件
npx playwright test tests/e2e/auth.spec.js

# 以 UI 模式运行
npx playwright test --ui
```

### 后端测试 (Pytest)

```bash
# 运行所有后端测试
pytest tests -v

# 仅运行单元测试
pytest tests/unit -v

# 仅运行集成测试
pytest tests/integration -v

# 运行特定测试文件
pytest tests/unit/test_database_services.py -v
```

## 测试覆盖

### 前端 E2E (27 个测试)

| 模块 | 文件 | 测试数 | 覆盖内容 |
|------|------|--------|----------|
| 认证 | `auth.spec.js` | 7 | 登录、Token 刷新、登出、权限验证 |
| 聊天 | `chat.spec.js` | 6 | 发送消息、流式响应、会话管理、历史记录 |
| 核心 | `core.spec.js` | 7 | 页面加载、路由、错误边界、主题切换 |
| 工具 | `tools.spec.js` | 7 | 工具面板、快捷键、拖拽上传 |

### 后端单元测试

| 模块 | 覆盖内容 |
|------|----------|
| `test_database_services.py` | 用户查询、权限管理、历史记录 |
| `test_utils.py` | 安全工具、密码哈希、Token 验证 |
| `test_system_monitor.py` | 系统监控、日志过滤 |
| `test_aicloud.py` | AI Cloud 相关功能 |
| `test_executor.py` | 任务执行器 |
| `test_graph_validator.py` | 图结构验证 |
| `test_state_machine.py` | 状态机逻辑 |
| `test_task_decomposer.py` | 任务分解 |
| `test_task_queue.py` | 任务队列 |

### 后端集成测试

| 模块 | 覆盖内容 |
|------|----------|
| `test_aicloud_api.py` | AI Cloud API 集成 |
| `test_dynamic_model_router.py` | 动态模型路由 |
| `test_task_queue_integration.py` | 任务队列集成 |
| `test_workflow_integration.py` | 工作流集成 |

## 归档文件说明

`tests/archive/` 目录包含历史遗留的测试文件，已不再使用：

- **`archive/playwright/`**: 旧版 Playwright 独立测试脚本，功能已迁移至 `e2e/*.spec.js`
- **`archive/legacy/`**: 旧版 Python 测试文件，功能已整合至 `unit/` 和 `integration/` 目录

如需参考历史测试实现，可从归档目录中查找。
