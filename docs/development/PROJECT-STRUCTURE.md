# 项目结构

## 根目录

```
codingmatrix/
├── app/                    # 后端 (FastAPI)
├── src/                    # 前端 (Vue 3)
├── tests/                  # 测试
├── docs/                   # 文档
├── .claude/                # AI Agent 配置
├── requirements.txt        # Python 依赖
├── package.json            # Node.js 依赖 (前端)
├── pytest.ini              # pytest 配置
└── .env                    # 环境变量 (不在版本控制)
```

## 后端 (app/)

```
app/
├── main.py                 # FastAPI 应用入口
├── core/
│   └── config.py           # 全局配置
├── db/
│   └── base.py             # 数据库引擎/会话
├── api/
│   ├── v1/                 # v1 API (15 模块)
│   │   ├── auth.py
│   │   ├── Aicode.py
│   │   ├── AiProjectCode.py
│   │   ├── ai_agent.py
│   │   ├── GirlAi.py
│   │   ├── kolors_api.py
│   │   ├── kolors_history.py
│   │   ├── aiGeneratorPptx.py
│   │   ├── file_upload.py
│   │   ├── task_queue.py
│   │   ├── vision_api.py
│   │   ├── workflow.py
│   │   ├── aicloud.py
│   │   ├── aicloud_knowledge.py
│   │   └── health.py
│   └── v2/                 # v2 API (5 模块)
│       ├── Controller.py
│       ├── nginx_api.py
│       ├── nginx_ai.py
│       ├── guardian_router.py
│       └── user_manage.py
├── models/                 # SQLAlchemy 模型
│   ├── __init__.py
│   ├── base.py
│   ├── user.py
│   ├── history.py
│   ├── file.py
│   ├── task.py
│   ├── saved_project.py
│   ├── agent_memory.py
│   ├── aicloud.py
│   ├── aicloud_knowledge.py
│   ├── server_config.py
│   ├── chat_history.py
│   └── Permission.py
├── schema/                 # Pydantic Schema
└── utils/                  # 工具层
    ├── security.py         # JWT/密码
    ├── encryption.py       # RSA/AES
    ├── csrf.py             # CSRF
    ├── rate_limiter.py     # 限流
    ├── circuit_breaker.py  # 熔断器
    ├── cache.py            # 缓存
    ├── logging.py          # 日志
    ├── error_handler.py    # 异常处理
    ├── permissions.py      # 权限
    ├── web_search.py       # 搜索
    ├── vision.py           # 视觉
    ├── docker_runner.py    # Docker
    └── workflow/           # 工作流
```

## 前端 (src/)

```
src/
├── App.vue
├── main.js
├── router/
│   └── index.js
├── stores/                 # Pinia
│   ├── user.js
│   ├── chat.js
│   └── task.js
├── components/             # Vue 组件
│   ├── MainLayout.vue
│   ├── Login.vue
│   ├── CodeGenerator.vue
│   ├── ProjectGenerator.vue
│   ├── GirlAiChat.vue
│   ├── PptGenerator.vue
│   ├── ImageGenerator.vue
│   ├── WorkflowEditor.vue
│   ├── FileUpload.vue
│   ├── SystemMonitor.vue
│   ├── PreviewPanel.vue
│   └── ...
├── views/
├── composables/
├── utils/
│   ├── api.js
│   ├── sse.js
│   └── crypto.js
├── assets/
└── styles/
```

## 测试 (tests/)

```
tests/
├── unit/                   # 单元测试
│   ├── test_utils.py
│   ├── test_state_machine.py
│   ├── test_task_queue.py
│   └── ...
├── integration/            # 集成测试
│   ├── test_auth_api.py
│   ├── test_ai_agent_api.py
│   ├── test_health_api.py
│   └── ...
└── archive/                # 遗留测试 (不运行)
```

## 文档 (docs/)

```
docs/
├── README.md               # 项目概述
├── INDEX.md                # 文档索引
├── MODULES.md              # 模块说明
├── FRONTEND.md             # 前端架构
├── PERMISSION-SPEC.md      # 权限规范
├── API_INTEGRATION_CHECKLIST.md
├── api/
│   └── API-DOCUMENTATION.md
├── architecture/
│   ├── ARCHITECTURE.md
│   ├── AGENT-OPTIMIZATION.md
│   └── api-responsibility-matrix.md
├── development/
│   ├── DEVELOPER_GUIDE.md
│   ├── PROJECT_STATUS.md
│   ├── PROJECT-STRUCTURE.md
│   └── README.md
├── deployment/
│   └── DOCKER-COMPOSE-DEPLOYMENT.md
├── feature/                # 功能文档
├── guides/                 # 操作指南
├── implementation/         # 实施记录
├── model-adapter/          # 模型适配
├── security/               # 安全文档
├── specs/                  # 规格设计
└── testing/                # 测试报告
```
