# 开发者指南

> 最后更新：2026-05-27 | 版本：v5.10.0

快速开始、环境配置、开发流程、常见问题。

## 环境要求

- **Python**: 3.11+
- **Node.js**: 18+
- **SQLite**: 3.35+
- **Redis**: 6.0+（用于 API Key 存储和会话缓存）
- **Docker**: 可选（用于 Jaeger 和 DockerRunner）
- **Git**: 2.0+

## 快速开始

### 1. 克隆项目

```bash
git clone https://github.com/sheep-no/codingmatrix.git
cd codingmatrix
```

### 2. 安装依赖

```bash
# 后端
pip install -r configs/requirements.txt

# 前端
cd src && yarn install
```

### 3. 配置环境

```bash
# 复制环境变量
cp .env.example .env

# 编辑配置
# - 设置数据库路径
# - 配置 LLM API Key（可选，用户可自行提供）
# - 设置 JWT 密钥
# - 配置 Redis 连接
```

### 4. 启动服务

```bash
# 后端（开发模式）
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload

# 前端
cd src && yarn dev
```

### 5. 访问应用

- 前端：http://localhost:5173
- 后端 API: http://localhost:8080/api/v1
- Swagger: http://localhost:8080/docs

## API Key 配置 (v5.9.0)

### 用户 API Key 管理

用户可在设置页面配置自己的 API Key：

1. 访问设置页面 → 「API Key 管理」标签
2. 输入 API Key
3. 系统使用 RSA-2048 加密传输
4. 加密 Token 存储在 Redis 中，TTL 自动过期
5. 所有功能（项目生成、代码对话、PPT、图像生成等）均使用用户 API Key

### 支持的供应商

| 供应商 | 说明 |
|--------|------|
| 硅基流动 (SiliconFlow) | 默认供应商，必填 |
| OpenAI | GPT 系列模型 |
| Anthropic | Claude 系列模型 |
| 阿里百炼 (DashScope) | 通义千问系列 |
| 智谱 GLM | GLM-4 系列 |
| DeepSeek | deepseek-chat, deepseek-reasoner |

### 动态供应商（自定义供应商）

平台支持通过自定义 `base_url` + 协议类型添加任意兼容 OpenAI 或 Anthropic 协议的 API 服务：

1. 访问设置页面 → 「自定义供应商」标签
2. 填写供应商名称、Base URL、协议类型、API Key
3. 点击「添加供应商」
4. 添加后可同步模型列表、测试连接、启用/禁用

### Token 使用统计

设置页面展示 Token 使用统计：
- 今日使用量
- 本月使用量
- 总计使用量
- 按模型分类统计

## 开发流程

详见 [服务管理](SERVICES.md)

## 常见问题

### 端口被占用

```bash
lsof -i :8080
kill -9 <PID>
```

### 依赖安装失败

```bash
pip cache purge
yarn cache clean
pip install -r configs/requirements.txt
yarn install
```

### 数据库锁定

```bash
rm app/data.db
```

## 相关文档

- [文档首页](../README.md) - 文档导航
- [生产部署](PRODUCTION.md) - 生产部署
- [API Key 使用指南](API-KEY-GUIDE.md) - API Key 详细说明
- [动态供应商](../features/DYNAMIC-PROVIDERS.md) - 自定义供应商功能说明
