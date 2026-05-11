# 开发者指南

## 环境准备

### 系统要求
- Python 3.11+
- Node.js 18+
- SQLite 3 (内置)
- 2 CPU, 4GB RAM (最低)

### 后端安装

```bash
# 安装依赖
pip install -r requirements.txt

# 设置环境变量
export SECRET_KEY=your-secret-key
export SILICONFLOW_API_KEY=your-api-key
export DATABASE_URL='sqlite+aiosqlite:///./app.db'

# 启动开发服务器
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 前端安装

```bash
cd src

# 安装依赖
npm install

# 启动开发服务器
npm run dev
```

## 项目结构

```
├── app/                  # 后端 (FastAPI)
│   ├── api/v1/          # v1 API 端点 (15 个模块)
│   ├── api/v2/          # v2 API 端点 (5 个模块)
│   ├── core/            # 配置
│   ├── db/              # 数据库
│   ├── models/          # SQLAlchemy 模型
│   ├── schema/          # Pydantic Schema
│   └── utils/           # 工具层
├── src/                 # 前端 (Vue 3)
│   ├── components/      # Vue 组件 (50 个)
│   ├── stores/          # Pinia 状态
│   ├── router/          # 路由
│   └── utils/           # 工具函数
├── tests/               # 测试
│   ├── unit/            # 单元测试
│   └── integration/     # 集成测试
└── docs/                # 文档
```

## 开发规范

### 后端规范
- 使用 async/await 处理异步操作
- SQLAlchemy 使用异步引擎
- Pydantic Schema 定义请求/响应模型
- 全局异常处理器统一错误格式
- 结构化 JSON 日志

### 前端规范
- Vue 3 Composition API (`<script setup>`)
- 组件命名: PascalCase
- 变量声明必须在 watch/computed 之前
- 使用 Pinia 管理状态
- API 调用统一使用 Axios 封装

### Git 分支规范

```
YYMMDD-(feat|fix|chore|refactor)-description
```

示例: `260508-feat-add-login-page`

## 运行测试

```bash
# 单元测试
python3 -m pytest tests/unit/ -v

# 集成测试
python3 -m pytest tests/integration/ -v

# 全部测试
python3 -m pytest tests/ --ignore=tests/archive -v
```

## 常用 API 端点

| 功能 | 端点 | 方法 |
|------|------|------|
| 登录 | `/api/v1/login` | POST |
| 代码生成 | `/api/v1/code` | POST |
| 项目生成 | `/api/v1/agent/generate` | POST |
| AI 对话 | `/api/v1/GirlAi` | POST |
| 图像生成 | `/api/v1/kolors/text-to-image` | POST |
| PPT 生成 | `/api/v1/pptx/generate` | POST |
| 健康检查 | `/api/v1/health` | GET |
| API 文档 | `/docs` | GET |

## 调试技巧

### 后端调试
- 访问 `/docs` 查看 Swagger UI
- 查看结构化日志输出
- 使用 `--reload` 热重载

### 前端调试
- Vue DevTools 浏览器插件
- `npm run dev` 支持 HMR
- 网络面板查看 API 请求

## 权限级别

| 级别 | 名称 | 说明 |
|------|------|------|
| 0 | normal | 普通用户，基础 AI 功能 |
| 1 | admin | 管理员，用户管理、监控 |
| 2 | super | 超级管理员，系统配置、部署 |
