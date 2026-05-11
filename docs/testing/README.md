# 测试文档

## 测试概述

| 类型 | 通过 | 失败 | 总计 |
|------|------|------|------|
| 单元测试 | 345 | 0 | 345 |
| 集成测试 | 149 | 2 (已知) | 151 |
| **总计** | **494** | **2** | **496** |

## 目录结构

```
tests/
├── conftest.py              # 测试夹具和固定配置
├── __init__.py
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

## 测试文件

### 单元测试 (tests/unit/)

| 文件 | 测试数 | 描述 |
|------|--------|------|
| test_utils.py | 40 | 工具函数 |
| test_state_machine.py | 23 | 状态机 |
| test_task_queue.py | 27 | 任务队列 |
| test_security_services.py | 24 | 安全服务 |
| test_middleware_services.py | 7 | 中间件 |
| test_node_types.py | 28 | 节点类型 |
| test_graph_validator.py | 14 | 图验证 |
| test_executor.py | 17 | 执行器 |
| test_database_services.py | 23 | 数据库 |
| test_comprehensive.py | 13 | 综合测试 |
| test_aicloud.py | 47 | AI 云 |
| test_result_aggregator.py | 21 | 结果聚合 |
| test_small_model_optimization.py | 37 | 小模型优化 |
| test_system_monitor.py | 12 | 系统监控 |
| test_task_decomposer.py | 12 | 任务分解 |

### 集成测试 (tests/integration/)

| 文件 | 测试数 | 描述 |
|------|--------|------|
| test_auth_api.py | 6 | 认证 |
| test_ai_agent_api.py | 8 | AI Agent |
| test_aicode_api.py | 4 | AI 代码 |
| test_kolors_api.py | 6 | 图像生成 |
| test_ppt_api.py | 6 | PPT |
| test_file_upload_api.py | 5 | 文件上传 |
| test_vision_api.py | 8 | 视觉分析 |
| test_user_management_api.py | 6 | 用户管理 |
| test_security_api.py | 5 | 安全 |
| test_task_queue_api.py | 4 | 任务队列 |
| test_workflow_integration.py | 10 | 工作流 |
| test_health_api.py | 6 | 健康检查 |
| test_girlai_api.py | 5 | 虚拟 AI |
| test_aiprojectcode_api.py | 12 | AI 项目 |
| test_preview_api.py | 3 | 预览 |
| test_kolors_history_api.py | 6 | 图像历史 |
| test_v2_admin_api.py | 12 | v2 管理 |
| test_v2_nginx_api.py | 7 | v2 Nginx |
| test_v2_guardian_api.py | 5 | v2 守护 |
| test_v2_nginx_ai_api.py | 3 | v2 Nginx AI |

### 前端 E2E (tests/e2e/)

| 模块 | 文件 | 测试数 | 覆盖内容 |
|------|------|--------|----------|
| 认证 | auth.spec.js | 7 | 登录、Token 刷新、登出、权限验证 |
| 聊天 | chat.spec.js | 6 | 发送消息、流式响应、会话管理、历史记录 |
| 核心 | core.spec.js | 7 | 页面加载、路由、错误边界、主题切换 |
| 工具 | tools.spec.js | 7 | 工具面板、快捷键、拖拽上传 |

## 运行测试

```bash
# 全部测试
python3 -m pytest tests/ --ignore=tests/archive -v

# 单元测试
python3 -m pytest tests/unit/ -v

# 集成测试
python3 -m pytest tests/integration/ -v

# 前端 E2E 测试
npx playwright test --project=chromium

# 单个文件
python3 -m pytest tests/integration/test_health_api.py -v
```

## 已知问题

| 测试 | 原因 |
|------|------|
| test_task_queue_integration.py | `get_db()` 异步生成器误用 |
| test_ai_agent_api.py | 测试环境 DB 表未初始化 |

## 归档文件说明

`tests/archive/` 目录包含历史遗留的测试文件，已不再使用：

- **`archive/playwright/`**: 旧版 Playwright 独立测试脚本，功能已迁移至 `e2e/*.spec.js`
- **`archive/legacy/`**: 旧版 Python 测试文件，功能已整合至 `unit/` 和 `integration/` 目录

如需参考历史测试实现，可从归档目录中查找。

## CI/CD

- CI/CD 配置: `.github/workflows/`
- 触发条件: push / pull_request
- 检查项: lint + test + build
