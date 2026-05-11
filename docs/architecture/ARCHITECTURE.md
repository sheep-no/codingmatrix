# 系统架构

## 技术栈

```
┌─────────────────────────────────────────────────────────┐
│                      Frontend (Vue 3)                     │
│  Vite 5 + Element Plus + Tailwind CSS + Pinia + ECharts   │
└────────────────────────┬────────────────────────────────┘
                         │ HTTP / SSE
┌────────────────────────┴────────────────────────────────┐
│                  Backend (FastAPI / Python 3.11)          │
│                                                          │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐ │
│  │  Auth    │  │ AI Code  │  │ Kolors   │  │  PPTX    │ │
│  │ Module   │  │  Gen     │  │  Image   │  │  Gen     │ │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘ │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐ │
│  │  Agent   │  │ Workflow │  │  Vision  │  │ Aicloud  │ │
│  │  Core    │  │  Engine  │  │  Analyze │  │  Cloud   │ │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘ │
│                                                          │
│  ┌──────────────────────────────────────────────────────┐│
│  │              Middleware Layer                        ││
│  │  CORS │ JWT Auth │ CSRF │ Rate Limit │ Logging       ││
│  └──────────────────────────────────────────────────────┘│
└────────────────────────┬────────────────────────────────┘
                         │
┌────────────────────────┴────────────────────────────────┐
│                    Data Layer                             │
│                                                          │
│  SQLite (Async SQLAlchemy) │ APScheduler │ Redis (Cache) │
└─────────────────────────────────────────────────────────┘
```

## 模块架构图

```
app/
├── api/
│   ├── v1/           # 主要业务 API (15 个模块)
│   │   ├── auth.py           # 认证 (登录/注册/Token)
│   │   ├── Aicode.py         # AI 代码生成
│   │   ├── AiProjectCode.py  # AI 项目生成
│   │   ├── ai_agent.py       # Agent 核心
│   │   ├── GirlAi.py         # 虚拟 AI 对话
│   │   ├── kolors_api.py     # 图像生成
│   │   ├── kolors_history.py # 图像历史
│   │   ├── aiGeneratorPptx.py # PPT 生成
│   │   ├── file_upload.py    # 文件上传
│   │   ├── task_queue.py     # 任务队列
│   │   ├── vision_api.py     # 视觉分析
│   │   ├── workflow.py       # 工作流
│   │   ├── aicloud.py        # AI 云
│   │   ├── aicloud_knowledge.py # 知识库
│   │   └── health.py         # 健康检查
│   └── v2/           # 系统管理 API (5 个模块)
│       ├── Controller.py     # 用户/服务/系统管理
│       ├── nginx_api.py      # Nginx 配置
│       ├── nginx_ai.py       # Nginx AI 分析
│       ├── guardian_router.py # 守护/熔断
│       └── user_manage.py    # 用户管理
├── core/             # 核心配置
├── db/               # 数据库
├── models/           # SQLAlchemy 模型 (11 个)
├── schema/           # Pydantic Schema
└── utils/            # 工具层 (40+ 模块)
```

## 数据流

### AI 代码生成流

```
用户输入 -> CodeGenerator.vue -> POST /api/v1/code (SSE)
    -> Aicode.py -> SiliconFlow API (LLM)
    -> SSE 流式返回 -> 前端实时渲染 Markdown
    -> 代码高亮 + 复制
```

### 项目生成流

```
用户提示词 -> ProjectGenerator.vue -> POST /api/v1/agent/generate
    -> ai_agent.py -> LLM 生成项目结构
    -> 文件树构建 -> SSE 进度推送
    -> 前端展示文件树 + 代码预览
    -> 保存 -> SQLite (saved_projects)
```

### 异步任务流 (PPT/图片)

```
用户请求 -> POST /api/v1/pptx/generate_task
    -> APScheduler 异步任务
    -> LLM 生成内容 -> python-pptx 生成文件
    -> 状态轮询 -> 下载/预览
```

## 中间件链

```
请求 -> CORS -> JWT 验证 -> CSRF 检查 -> 权限检查 -> 限流 -> 路由处理 -> 响应
```

## 部署架构

```
Nginx (反向代理)
├── / -> Vue 前端 (静态文件)
└── /api/ -> FastAPI (uvicorn workers)
    ├── SQLite (持久化)
    └── APScheduler (后台任务)
```
