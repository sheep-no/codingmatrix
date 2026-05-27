# 服务启动说明

> 最后更新：2026-05-27 | v5.10.0

## 重要说明

**统一端口**: 后端的 `dist/` 目录包含前端构建产物，统一在 **8000 端口** 提供服务

无需分别启动前后端，一个命令即可：

```bash
# 启动服务
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000

# 访问
open http://localhost:8000
```

---

## 快速启动

### 方法 1: 使用服务管理脚本（推荐）

```bash
# 启动服务
./manage-services.sh start

# 查看状态
./manage-services.sh status

# 健康检查
./manage-services.sh health

# 查看日志
./manage-services.sh logs

# 停止服务
./manage-services.sh stop

# 重启服务
./manage-services.sh restart
```

### 方法 2: 手动启动

```bash
cd /workspace
# 统一在 8000 端口提供前后端服务
nohup python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload > logs/backend.log 2>&1 &
echo $! > logs/backend.pid
```

### 开发模式（前后端分离）

如需分别开发前后端：

```bash
# 终端 1: 启动后端 API（8000 端口）
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000

# 终端 2: 启动前端开发服务器（3000 端口，带 HMR）
cd src
npm run dev
```

**注意**: 开发模式需要配置 Vite proxy，详见 `src/vite.config.js`

---

## 服务地址

| 服务 | 地址 | 说明 |
|------|------|------|
| 统一服务 | http://localhost:8000 | 生产模式 |
| 前端应用 | http://localhost:8000 | 统一入口 |
| 后端 API | http://localhost:8000/api/v1 | API 端点 |
| API 文档 | http://localhost:8000/docs | Swagger UI |
| 健康检查 | http://localhost:8000/api/v1/health | 健康状态 |
| 模型列表 | http://localhost:8000/api/v1/health/models | 支持的模型 |

---

## API 端点概览

### v1 API

| 模块 | 端点 | 功能 |
|------|------|------|
| 认证 | `/api/v1/login, /register, /refresh` | 用户认证、JWT Token |
| Agent | `/api/v1/agent/*` | 项目生成、代码审查、快照管理 |
| AI 代码 | `/api/v1/code` | 代码生成、流式输出 |
| PPT | `/api/v1/pptx/*` | PPT 生成 |
| 图像 | `/api/v1/kolors/*` | 文生图、图生图 |
| AI Cloud | `/api/v1/aicloud/*` | 沙箱执行、审查队列 |
| 文件 | `/api/v1/files/*` | 文件上传、解析 |
| 工作流 | `/api/v1/workflow/*` | 可视化编排 |
| 健康 | `/api/v1/health` | 健康检查、指标 |
| API Key | `/api/v1/agent/apikey/*` | API Key 管理 |

### v2 API

| 模块 | 端点 | 功能 |
|------|------|------|
| 管理 | `/api/v2/admin/*` | 管理员配置 |
| Nginx | `/api/v2/nginx/*` | Nginx 配置管理 |
| 监控 | `/api/v2/Controller/*` | 系统监控 |
| 用户 | `/api/v2/Controller/users/*` | 用户管理 |
| 守护 | `/api/v2/Controller/guardian/*` | 进程守护 |

---

## 日志位置

| 类型 | 路径 |
|------|------|
| 后端日志 | `/workspace/logs/backend.log` |
| 进程 PID | `/workspace/logs/backend.pid` |
| E2E测试报告 | `/workspace/test-results/` |
| Playwright 报告 | `/workspace/playwright-report/` |

---

## 停止服务

### 使用脚本
```bash
./manage-services.sh stop
```

### 手动停止
```bash
# 读取 PID
cat logs/backend.pid

# 停止服务
kill $(cat logs/backend.pid)

# 或强制停止
pkill -f "uvicorn app.main"
```

---

## 健康检查

```bash
# 基础健康检查
curl http://localhost:8000/api/v1/health

# 查看支持的模型
curl http://localhost:8000/api/v1/health/models

# 查看详细状态
curl http://localhost:8000/api/v1/system/health
```

响应示例：
```json
{
  "status": "healthy",
  "timestamp": "2026-05-26T...",
  "version": "v5.10.0"
}
```

---

## 端口说明

### 为什么使用 8000 端口？

1. **统一部署**: 后端 dist 目录包含前端构建产物
2. **避免 CORS**: 前后端同端口，无需跨域配置
3. **简化运维**: 一个进程管理所有服务

### 端口历史

| 版本 | 端口 | 说明 |
|------|------|------|
| v4.x | 8080 | 早期版本 |
| v5.0-v5.3 | 8002 | 临时端口 |
| **v5.4.0+** | **8000** | **统一端口** |

---

## 常见问题

### Q: 前端构建产物在哪里？

A: `app/dist/` 目录包含前端构建产物：
```
app/dist/
├── static/          # 静态资源
│   ├── vendor-*.js  # 第三方库
│   ├── index-*.js   # 主应用
│   └── *.css        # 样式文件
└── index.html       # 入口文件
```

### Q: 如何更新前端？

```bash
# 构建前端
cd src
npm run build

# 产物自动输出到 app/dist/
# 重启后端即可
```

### Q: 可以分别开发吗？

可以，见上方"开发模式"章节。

---

## 环境变量

关键环境变量：

```bash
# 后端配置
SILICONFLOW_API_KEY=your-key
SECRET_KEY=your-secret

# 多供应商配置（可选）
DASHSCOPE_API_KEY=your-dashscope-key
ZHIPU_API_KEY=your-zhipu-key
DEEPSEEK_API_KEY=your-deepseek-key
```

详见 [guides/MULTI_PROVIDER_SETUP.md](guides/MULTI_PROVIDER_SETUP.md)

---

## 相关文档

- [快速开始](guides/GETTING-STARTED.md)
- [生产部署](guides/PRODUCTION.md)
- [多供应商配置](guides/MULTI_PROVIDER_SETUP.md)
- [API 文档](api/)

---

最后更新：2026-05-27
