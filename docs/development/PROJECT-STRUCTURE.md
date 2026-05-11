# 项目结构

> 最后更新: 2026-05-11

## 根目录

```
codingmatrix/
├── app/                    # 后端 (FastAPI, Python 3.11)
├── src/                    # 前端 (Vue 3, Vite 5)
├── tests/                  # 测试 (Pytest + Playwright)
├── docs/                   # 文档 (全部 Markdown)
├── configs/                # 配置文件 (system_config.json 等)
├── data/                   # 数据目录 (SQLite 数据库等)
├── keys/                   # 密钥目录 (RSA 密钥对)
├── logs/                   # 日志目录
├── migrations/             # Alembic 数据库迁移
├── projects/               # 用户项目上传目录
├── sessions/               # Agent 会话数据
├── spec_cache/             # 规范缓存
├── embedding_cache/        # 嵌入向量缓存
├── learning_data/          # 反馈学习数据
├── scripts/                # 运维脚本
│
├── .claude/                # AI Agent 配置 (Skills/Rules)
├── .monkeycode/            # MonkeyCode 项目文档
├── .github/                # GitHub CI/CD 配置
│
├── app/main.py             # FastAPI 应用入口
├── main.py                 # 项目启动入口
├── Makefile                # Make 命令集
├── pyproject.toml          # Python 项目配置
├── alembic.ini             # Alembic 配置
├── requirements.txt        # Python 依赖
├── requirements-test.txt   # 测试依赖
├── pytest.ini              # Pytest 配置
├── .coveragerc             # 覆盖率配置
│
├── package.json            # Node.js 依赖 (前端)
├── package-lock.json       # 依赖锁定
├── playwright.config.js    # Playwright E2E 测试配置
│
├── docker-compose.yml      # Docker Compose (开发)
├── docker-compose.prod.yml # Docker Compose (生产)
├── Dockerfile              # Docker 镜像
├── nginx.conf              # Nginx 配置
├── prometheus.yml          # Prometheus 监控配置
│
├── .env.example            # 环境变量模板
├── .env.production.example # 生产环境变量模板
├── .gitignore              # Git 忽略规则
│
├── start.sh / start.bat    # 启动脚本
├── stop.sh / stop.bat      # 停止脚本
├── status.sh / status.bat  # 状态检查脚本
├── logs.sh / logs.bat      # 日志查看脚本
│
├── cookies.txt             # Cookie 文件
├── src.rar                 # 前端源码备份
├── dependency_graph.json   # 依赖图数据
│
├── test_agent.py           # Agent 测试
├── test_agent_capabilities.py  # Agent 能力测试
├── test_orchestrator.py    # Orchestrator 测试
├── test_json_parsing.py    # JSON 解析测试
├── test_output/            # 测试输出
└── test-results/           # Playwright 测试结果
```

## 后端 (app/)

```
app/
├── main.py                     # FastAPI 应用入口 (311 行)
├── celery_app.py               # Celery 异步任务配置
│
├── api/                        # API 层 (22 个模块)
│   ├── v1/                     # 业务 API (16 模块)
│   │   ├── auth.py             # 认证 (登录/注册/Token/RSA)
│   │   ├── Aicode.py           # AI 代码生成
│   │   ├── AiProjectCode.py    # AI 项目生成
│   │   ├── ai_agent.py         # Agent 核心
│   │   ├── GirlAi.py           # 虚拟 AI 角色对话
│   │   ├── kolors_api.py       # 图像生成
│   │   ├── kolors_history.py   # 图像历史
│   │   ├── aiGeneratorPptx.py  # PPT 生成
│   │   ├── file_upload.py      # 文件上传
│   │   ├── task_queue.py       # 任务队列
│   │   ├── vision_api.py       # 视觉分析
│   │   ├── workflow.py         # 工作流引擎
│   │   ├── aicloud.py          # AI 云服务
│   │   ├── aicloud_knowledge.py # 知识库
│   │   ├── health.py           # 健康检查
│   │   └── preview.py          # 文件预览
│   └── v2/                     # 管理 API (6 模块)
│       ├── Controller.py       # 系统控制器
│       ├── nginx_api.py        # Nginx 配置
│       ├── nginx_ai.py         # Nginx AI
│       ├── guardian_router.py  # 服务守护/熔断
│       ├── user_manage.py      # 用户管理
│       └── admin_config.py     # 系统配置
│
├── agent/                      # AI Agent 引擎 (23 模块)
│   ├── __init__.py
│   ├── orchestrator.py         # 总指挥
│   ├── multi_model_agent.py    # 多模型协调器
│   ├── react_agent.py          # ReAct Agent
│   ├── executor.py             # 执行器
│   ├── specialists.py          # 专家角色
│   ├── memory.py               # 记忆系统
│   ├── dynamic_model_router.py # 动态路由
│   ├── spec_first_generator.py # 规范优先生成
│   ├── refinement_loop.py      # 迭代修复
│   ├── cross_validator.py      # 交叉验证
│   ├── dependency_graph.py     # 依赖图
│   ├── code_validator.py       # 代码验证
│   ├── code_patcher.py         # 代码补丁
│   ├── error_recovery.py       # 错误恢复
│   ├── complexity.py           # 复杂度分析
│   ├── session_manager.py      # 会话管理
│   ├── spec_cache.py           # 规范缓存
│   ├── feedback_learner.py     # 反馈学习
│   ├── test_runner.py          # 测试运行器
│   ├── shared_context.py       # 共享上下文
│   └── api_contract_checker.py # API 契约检查
│
├── core/                       # 核心配置
│   ├── config.py               # 全局配置
│   ├── logging_config.py       # 日志配置
│   └── graceful_shutdown.py    # 优雅关闭
│
├── db/                         # 数据库层
│   ├── base.py                 # SQLAlchemy 基类
│   ├── database.py             # 异步引擎/会话
│   └── scheduler.py            # APScheduler
│
├── middleware/                  # 中间件 (4 个)
│   ├── rate_limiter.py         # 速率限制
│   ├── security_headers.py     # 安全响应头
│   ├── feature_switch.py       # 功能开关
│   └── input_validator.py      # 输入验证
│
├── models/                     # SQLAlchemy 模型 (12 个)
│   ├── __init__.py
│   ├── base.py                 # 模型基类
│   ├── user.py                 # 用户
│   ├── history.py              # 历史
│   ├── file.py                 # 文件
│   ├── task.py                 # 任务
│   ├── saved_project.py        # 保存项目
│   ├── agent_memory.py         # Agent 记忆
│   ├── aicloud.py              # AI 云
│   ├── aicloud_knowledge.py    # 知识库
│   ├── server_config.py        # 服务器配置
│   ├── chat_history.py         # 对话历史
│   └── Permission.py           # 权限
│
├── schema/                     # Pydantic Schema
├── scripts/                    # 运维脚本
├── services/                   # 业务服务层
├── tasks/                      # Celery 任务
├── test/                       # 后端测试
│
└── utils/                      # 工具层 (45+ 模块)
    ├── security.py             # JWT/密码
    ├── encryption.py           # RSA/AES
    ├── csrf.py                 # CSRF
    ├── rate_limiter.py         # 限流
    ├── circuit_breaker.py      # 熔断器
    ├── cache.py                # 缓存
    ├── cache_decorator.py      # 缓存装饰器
    ├── logging.py              # 请求日志
    ├── structured_logging.py   # 结构化日志
    ├── error_handler.py        # 异常处理
    ├── error_codes.py          # 错误码
    ├── system_config.py        # 系统配置
    ├── system_monitor.py       # 系统监控
    ├── performance_monitor.py  # 性能监控
    ├── web_search.py           # 搜索
    ├── vision.py               # 视觉
    ├── docker_runner.py        # Docker
    ├── file_operator.py        # 文件操作
    ├── project_validator.py    # 项目验证
    ├── pptxGenerateUtil.py     # PPT 工具
    ├── AiCodeUtil.py           # AI 代码工具
    ├── agent_core.py           # Agent 核心
    ├── agent_skills.py         # Agent 技能
    ├── json_parser.py          # JSON 解析
    ├── retry.py                # 重试
    ├── hot_reload.py           # 热重载
    ├── sentry.py               # Sentry
    ├── startup_alert.py        # 启动告警
    ├── log_archiver.py         # 日志归档
    ├── pagination.py           # 分页
    ├── http_client.py          # HTTP 客户端
    ├── prompt_loader.py        # 提示词加载
    ├── security_audit.py       # 安全审计
    ├── service_config_manager.py  # 服务配置
    ├── async_enhanced_guard.py # 异步守卫
    ├── guard_contracts.py      # 守卫合约
    ├── process_guard.py        # 进程守卫
    ├── image_generation.py     # 图像生成
    ├── task_dispatcher.py      # 任务分发
    ├── task_manager.py         # 任务管理
    ├── api_response.py         # API 响应
    ├── math_utils.py           # 数学工具
    ├── aicloud/                # AI 云工具
    ├── review/                 # 代码审查
    ├── validators/             # 数据验证
    ├── workflow/               # 工作流
    └── visual/                 # 视觉处理
```

## 前端 (src/)

```
src/
├── App.vue                     # 根组件
├── main.js                     # 入口文件
├── index.html                  # HTML 模板
├── vite.config.js              # Vite 配置
├── package.json                # Node 依赖
├── eslint.config.js            # ESLint 配置
├── .prettierrc                 # Prettier 配置
├── .prettierignore
├── fix-theme-colors.sh         # 主题颜色修复脚本
│
├── router/
│   └── index.js               # 路由配置 (8 路由)
│
├── stores/                     # Pinia 状态管理 (5 Store)
│   ├── user.js                # 用户状态
│   ├── task.js                # 任务状态
│   ├── logs.js                # 日志状态
│   ├── navigation.js          # 导航状态
│   └── counter.js             # 计数器
│
├── views/                      # 视图页面 (5 个)
│   ├── ProjectGenerate.vue    # 项目生成
│   ├── Workflow.vue           # 工作流
│   ├── PPTGenerate.vue        # PPT 生成
│   ├── PPTPreview.vue         # PPT 预览
│   └── ImageGenerate.vue      # 图像生成
│
├── components/                 # Vue 组件 (51 个)
│   ├── index.vue              # 首页
│   ├── centerContent.vue      # 主内容区
│   ├── leftlist.vue           # 侧边栏
│   ├── bottominput.vue        # 底部输入
│   ├── LoginDialog.vue        # 登录弹窗
│   ├── AdminPanel.vue         # 管理面板
│   ├── AiAgent.vue            # Agent 交互
│   ├── Aicloud.vue            # AI 云服务
│   ├── ImageGenerator.vue     # 图像生成
│   ├── PPTGenerator.vue       # PPT 生成
│   ├── ProjectGenerator.vue   # 项目生成
│   ├── TaskQueue.vue          # 任务队列
│   ├── WorkflowDAG.vue        # 工作流 DAG
│   ├── EphemeralWorkflow.vue  # 临时工作流
│   ├── WorkflowEditor.vue     # 工作流编辑器
│   ├── WorkflowLogViewer.vue  # 工作流日志
│   ├── WorkflowDiffViewer.vue # 工作流对比
│   ├── WorkflowFilePreview.vue # 工作流预览
│   ├── AgentCodeViewer.vue    # Agent 代码
│   ├── AgentFileTree.vue      # Agent 文件树
│   ├── AgentKnowledgePanel.vue # Agent 知识
│   ├── AgentProjectActions.vue # Agent 操作
│   ├── AgentProjectPreview.vue # Agent 预览
│   ├── AgentReActSteps.vue    # Agent ReAct
│   ├── AgentSessionSidebar.vue # Agent 会话
│   ├── AgentStatsPanel.vue    # Agent 统计
│   ├── AgentWorkflowPanel.vue # Agent 工作流
│   ├── ChartEditor.vue        # 图表编辑
│   ├── DiffViewer.vue         # 差异查看
│   ├── Dockerfile.vue         # Dockerfile
│   ├── EmptyState.vue         # 空状态
│   ├── ErrorBoundary.vue      # 错误边界
│   ├── FileDropZone.vue       # 文件拖放
│   ├── FileManager.vue        # 文件管理
│   ├── FilePreview.vue        # 文件预览
│   ├── FilePreviewCenter.vue  # 预览中心
│   ├── HistoryItem.vue        # 历史条目
│   ├── KeyboardShortcutsHelp.vue # 快捷键
│   ├── MessageEditor.vue      # 消息编辑
│   ├── NginxConfig.vue        # Nginx 配置
│   ├── ResourceControl.vue    # 资源控制
│   ├── ServiceManager.vue     # 服务管理
│   ├── ShareDialog.vue        # 分享弹窗
│   ├── SkeletonLoader.vue     # 骨架屏
│   ├── SystemInfo.vue         # 系统信息
│   ├── SystemLogs.vue         # 系统日志
│   ├── SystemMonitor.vue      # 系统监控
│   ├── ToastContainer.vue     # Toast 通知
│   ├── UserManagement.vue     # 用户管理
│   ├── VirtualGirl.vue        # 虚拟 AI
│   ├── VirtualHistoryList.vue # 虚拟历史
│   └── AppLoading.vue         # 加载动画
│
├── utils/                      # 前端工具
│   ├── api/                   # API 客户端
│   │   └── ppt.js             # PPT API
│   ├── chatDatabase.js        # IndexedDB 聊天存储
│   ├── csrf.js                # CSRF Token
│   ├── encryption.js          # RSA 加密
│   ├── streamManager.js       # SSE 流管理
│   ├── taskNotification.js    # 浏览器通知
│   ├── theme.js               # 主题管理
│   ├── tokenManager.js        # Token 管理
│   ├── websocketManager.js    # WebSocket
│   └── websocketPool.js       # WebSocket 池
│
├── composables/                # 组合式函数
├── styles/                     # 样式文件
├── assets/                     # 静态资源
├── img/                        # 图片资源
├── public/                     # 公共资源
└── test-results/              # 前端测试结果
```

## 测试 (tests/)

```
tests/
├── __init__.py
├── conftest.py                # 测试夹具
├── e2e/                       # Playwright E2E 测试 (前端)
│   ├── auth.spec.js           # 认证流程 (7 测试)
│   ├── chat.spec.js           # 聊天功能 (6 测试)
│   ├── core.spec.js           # 核心功能 (7 测试)
│   ├── tools.spec.js          # 工具面板 (7 测试)
│   └── README.md
├── unit/                      # 单元测试 (后端)
│   ├── conftest.py
│   ├── test_utils.py          # 工具函数 (40 测试)
│   ├── test_state_machine.py  # 状态机 (23 测试)
│   ├── test_task_queue.py     # 任务队列 (27 测试)
│   ├── test_security_services.py  # 安全服务 (24 测试)
│   ├── test_node_types.py     # 节点类型 (28 测试)
│   ├── test_graph_validator.py # 图验证 (14 测试)
│   ├── test_executor.py       # 执行器 (17 测试)
│   ├── test_database_services.py  # 数据库 (23 测试)
│   ├── test_comprehensive.py  # 综合测试 (13 测试)
│   ├── test_aicloud.py        # AI 云 (47 测试)
│   ├── test_result_aggregator.py  # 结果聚合 (21 测试)
│   ├── test_small_model_optimization.py  # 小模型优化 (37 测试)
│   ├── test_system_monitor.py # 系统监控 (12 测试)
│   └── test_task_decomposer.py # 任务分解 (12 测试)
├── integration/               # 集成测试 (后端)
│   ├── test_auth_api.py       # 认证 API
│   ├── test_ai_agent_api.py   # Agent API
│   ├── test_aicode_api.py     # 代码生成 API
│   ├── test_kolors_api.py     # 图像 API
│   ├── test_ppt_api.py        # PPT API
│   ├── test_file_upload_api.py # 文件上传 API
│   ├── test_vision_api.py     # 视觉 API
│   ├── test_user_management_api.py  # 用户管理 API
│   ├── test_security_api.py   # 安全 API
│   ├── test_task_queue_api.py # 任务队列 API
│   ├── test_workflow_integration.py  # 工作流集成
│   ├── test_health_api.py     # 健康检查 API
│   ├── test_girlai_api.py     # GirlAi API
│   ├── test_aiprojectcode_api.py  # 项目生成 API
│   ├── test_preview_api.py    # 预览 API
│   ├── test_kolors_history_api.py  # 图像历史 API
│   ├── test_v2_admin_api.py   # v2 管理 API
│   ├── test_v2_nginx_api.py   # v2 Nginx API
│   ├── test_v2_guardian_api.py # v2 守护 API
│   └── test_v2_nginx_ai_api.py  # v2 Nginx AI API
└── archive/                   # 归档历史测试 (不运行)
    ├── playwright/            # 旧版 Playwright
    └── legacy/                # 旧版 Python 测试
```

## 文档 (docs/)

```
docs/
├── README.md                  # 项目概述
├── INDEX.md                   # 文档索引
├── MODULES.md                 # 模块说明
├── FRONTEND.md                # 前端架构
├── PERMISSION-SPEC.md         # 权限规范
├── API_INTEGRATION_CHECKLIST.md
│
├── agent/                     # Agent 文档
│   └── AGENT-FLOW.md          # Agent 流程文档
│
├── api/                       # API 文档
│   ├── API-DOCUMENTATION.md   # API 文档
│   └── API-VERSIONS.md        # API 版本管理
│
├── architecture/              # 架构文档
│   ├── ARCHITECTURE.md        # 系统架构
│   ├── AGENT-OPTIMIZATION.md  # Agent 优化
│   └── api-responsibility-matrix.md
│
├── deployment/                # 部署文档
│   └── DOCKER-COMPOSE-DEPLOYMENT.md
│
├── development/               # 开发文档
│   ├── README.md
│   ├── DEVELOPER_GUIDE.md
│   ├── PROJECT_STATUS.md
│   ├── PROJECT-STRUCTURE.md   # 项目结构 (本文档)
│   ├── DEPENDENCY-AUDIT-REPORT.md
│   └── project-cleanup-report.md
│
├── feature/                   # 功能文档
│   ├── aicloud/               # AI 云功能
│   ├── docker_implementation.md
│   ├── file-upload-detailed-guide.md
│   ├── file-upload-task-guide.md
│   ├── free-search-guide.md
│   ├── ppt-generator-guide.md
│   ├── scheduler-cleanup-guide.md
│   ├── vision-integration-guide.md
│   ├── web-search-deep-fetch.md
│   └── web-search-guide.md
│
├── guides/                    # 操作指南
│   ├── QUICK_START_WINDOWS.md
│   ├── production-ready.md
│   └── security-first.md
│
├── implementation/            # 实施记录
│   ├── IMPLEMENTATION-SUMMARY.md
│   ├── INTEGRATION-GUIDE.md
│   └── ENHANCED-FEATURES-README.md
│
├── model-adapter/             # 模型适配
│   ├── README.md
│   ├── MODEL-CONFIG-GUIDE.md
│   └── QUICKSTART.md
│
├── models/                    # 模型文档
│   └── MODELS.md
│
├── prompts/                   # 提示词文档
│   └── PROMPTS.md             # AI 提示词 (22 个)
│
├── security/                  # 安全文档
│   ├── CSRF-IMPLEMENTATION-COMPLETE.md
│   ├── ENCRYPTED_LOGIN.md
│   └── FINAL-CSRF-SUMMARY.md
│
├── skills/                    # Skills 文档
│   ├── SKILLS-MIGRATION-REPORT.md
│   └── SKILLS-UPDATE-REPORT.md
│
├── specs/                     # 规格设计
│   ├── admin-resource-control/
│   ├── aicloud/
│   ├── ephemeral-workflow/
│   ├── production-ready/
│   ├── task-queue-improvements/
│   └── GIRL_AI_V2_UPGRADE_COMPLETE.md
│   └── new-features-integration-complete.md
│
└── testing/                   # 测试文档
    ├── README.md              # 测试文档索引
    ├── TEST-QUICKSTART.md     # 快速开始
    ├── BADGES.md              # CI/CD 徽章
    ├── COMPREHENSIVE-TEST-REPORT-20260508.md
    ├── ci-cd-complete-report.md
    ├── ci-cd-setup-guide.md
    └── test_agent_core_selfcheck.py
```

## 关键统计

| 类别 | 数量 | 说明 |
|------|------|------|
| 后端 API 模块 | 22 | v1 (16) + v2 (6) |
| Agent 模块 | 23 | AI 引擎核心 |
| 工具模块 | 45+ | utils/ 目录 |
| 数据模型 | 12 | SQLAlchemy models |
| 中间件 | 8 | 请求处理链 |
| 前端组件 | 51 | Vue SFC 组件 |
| 前端视图 | 5 | 页面级组件 |
| Pinia Store | 5 | 状态管理 |
| 路由 | 8 | Vue Router |
| 测试文件 | 35+ | 单元 + 集成 + E2E |
| 文档文件 | 50+ | Markdown 文档 |
