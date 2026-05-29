# 动态供应商功能

> 最后更新：2026-05-27 | 版本：v5.10.0

动态供应商功能允许用户通过自定义 `base_url` + 协议类型添加任意兼容 OpenAI 或 Anthropic 协议的 API 服务，扩展平台的模型支持范围。

## 1. 功能概述

### 1.1 核心特性

- **自定义 API 地址**：指定任意兼容 OpenAI 或 Anthropic 协议的 API 端点
- **多协议支持**：OpenAI 兼容协议 + Anthropic 原生协议
- **自动模型拉取**：添加后自动调用 `/models` 端点获取可用模型列表（OpenAI 兼容）
- **内存存储**：供应商配置存储在内存中，重启后清空
- **模型缓存**：模型列表缓存 5 分钟，减少重复请求
- **故障转移**：与内置供应商统一使用故障转移机制

### 1.2 适用场景

| 场景 | 说明 |
|------|------|
| 企业内部 API | 使用企业部署的开源模型服务 |
| 第三方代理 | 使用 Claude代理、OpenAI代理等中转服务 |
| 私有部署模型 | 使用本地部署的 Llama、Qwen 等模型 |
| 多账户管理 | 通过不同 base_url 管理多个供应商账户 |

## 2. 支持的协议

### 2.1 OpenAI 兼容协议

所有兼容 OpenAI API 格式的服务都可以接入：

| 端点 | 方法 | 用途 |
|------|------|------|
| `{base_url}/chat/completions` | POST | 聊天/代码生成 |
| `{base_url}/models` | GET | 拉取模型列表 |

**认证方式**：`Authorization: Bearer {api_key}`

**已知兼容的服务**：
- OpenAI 官方 API
- SiliconFlow
- DeepSeek
- 智谱 GLM
- 阿里百炼（兼容模式）
- 任意 OpenAI 兼容代理/网关

### 2.2 Anthropic 原生协议

Anthropic Claude 系列模型的原生 API：

| 端点 | 方法 | 用途 |
|------|------|------|
| `{base_url}/messages` | POST | 聊天/代码生成 |

**认证方式**：
- `x-api-key: {api_key}`
- `anthropic-version: 2023-06-01`

**注意**：Anthropic 无公开模型列表 API，使用内置已知模型列表：
- claude-3-5-sonnet-20241022
- claude-3-sonnet-20240229
- claude-3-opus-20240229
- claude-3-haiku-20240307

## 3. 架构设计

### 3.1 核心组件

```
┌─────────────────────────────────────────────────────┐
│              前端 (Vue 3 + Pinia)                    │
│  ┌─────────────────┐  ┌───────────────────────────┐ │
│  │ DynamicProvider │  │ AgentModelConfig (下拉选) │ │
│  │ Manager.vue     │  │ ┌───────────────────────┐ │ │
│  │ - 添加供应商    │  │ │ 系统默认              │ │ │
│  │ - 同步模型      │  │ │ 已配置的 API Key      │ │ │
│  │ - 测试连接      │  │ │ 自定义供应商模型      │ │ │
│  │ - 启用/禁用     │  │ └───────────────────────┘ │ │
│  └─────────────────┘  └───────────────────────────┘ │
└──────────────────────┬──────────────────────────────┘
                       │ HTTP REST API
┌──────────────────────▼──────────────────────────────┐
│              后端 (FastAPI)                          │
│  ┌─────────────────────────────────────────────┐   │
│  │         /api/v1/providers 路由               │   │
│  │  POST /           - 添加供应商                │   │
│  │  GET /            - 列表                     │   │
│  │  GET /{id}        - 详情                     │   │
│  │  DELETE /{id}     - 删除                     │   │
│  │  PUT /{id}/toggle - 启用/禁用                │   │
│  │  POST /{id}/sync  - 同步模型                  │   │
│  │  POST /{id}/test  - 测试连接                  │   │
│  └─────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────┐   │
│  │   DynamicProviderManager (内存单例)          │   │
│  │  - CRUD 操作                                │   │
│  │  - 按模型名查找供应商                        │   │
│  │  - 模型缓存 (5 分钟 TTL)                     │   │
│  └─────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────┐   │
│  │         DynamicAdapter                      │   │
│  │  - 根据协议选择调用格式                      │   │
│  │  - OpenAI: /chat/completions                │   │
│  │  - Anthropic: /messages                     │   │
│  │  - 统一转换为 OpenAI 兼容格式返回            │   │
│  └─────────────────────────────────────────────┘   │
└──────────────────────┬──────────────────────────────┘
                       │ HTTP 请求
            ┌──────────▼──────────┐
            │   外部 API 服务      │
            │   (自定义 base_url)  │
            └─────────────────────┘
```

### 3.2 数据模型

```python
class DynamicProvider:
    id: str              # UUID
    name: str            # 供应商名称
    base_url: str        # API 地址
    protocol: Protocol   # OPENAI / ANTHROPIC
    api_key: str         # 访问密钥
    enabled: bool        # 是否启用
    models: List[ModelInfo]  # 模型列表
    last_sync: float     # 最后同步时间戳
    sync_error: str      # 同步错误信息
```

### 3.3 调用流程

```
用户选择动态供应商模型
    │
    ▼
call_llm(model, ...)
    │
    ▼
ProviderRouter.route(model)
    │  ├─ 1. 检查动态供应商模型映射
    │  └─ 2. 匹配内置供应商
    │
    ▼
DynamicAdapter(provider)
    │  ├─ protocol=openai → /chat/completions
    │  └─ protocol=anthropic → /messages
    │
    ▼
httpx.AsyncClient 发送请求
    │
    ▼
返回 OpenAI 兼容格式响应
```

## 4. 使用指南

### 4.1 添加供应商

1. 进入设置页面 → 「自定义供应商」标签
2. 填写表单：
   - **供应商名称**：自定义名称（如 "Claude 代理"）
   - **Base URL**：API 服务地址（如 `https://api.example.com/v1`）
   - **协议类型**：
     - OpenAI 兼容：适用于大多数服务
     - Anthropic 原生：适用于 Claude 原生 API
   - **API Key**：服务访问密钥
3. 点击「添加供应商」

### 4.2 同步模型

- **OpenAI 兼容**：自动调用 `{base_url}/models` 拉取
- **Anthropic 原生**：使用内置已知模型列表
- **缓存时间**：5 分钟
- **强制刷新**：点击「同步模型」按钮

### 4.3 测试连接

点击「测试连接」发送测试请求：

| 协议 | 测试模型 | 测试端点 |
|------|---------|---------|
| OpenAI | gpt-3.5-turbo | `/chat/completions` |
| Anthropic | claude-3-haiku-20240307 | `/messages` |

### 4.4 在 Agent 中使用

1. 进入设置页面 → 「Agent 模型配置」
2. 在下拉列表中找到「自定义供应商模型」分组
3. 选择需要的模型
4. 配置自动保存

## 5. API 参考

### 添加供应商

```http
POST /api/v1/providers
Content-Type: application/json

{
  "name": "Claude 代理",
  "base_url": "https://api.anthropic.com",
  "protocol": "anthropic",
  "api_key": "sk-ant-xxx..."
}
```

### 获取列表

```http
GET /api/v1/providers
```

### 同步模型

```http
POST /api/v1/providers/{id}/sync?force=true
```

### 测试连接

```http
POST /api/v1/providers/{id}/test
```

### 启用/禁用

```http
PUT /api/v1/providers/{id}/toggle
```

### 删除

```http
DELETE /api/v1/providers/{id}
```

## 6. 注意事项

- **内存存储**：供应商配置在内存中，服务重启后丢失
- **模型缓存**：模型列表缓存 5 分钟，如需最新列表请强制同步
- **故障转移**：动态供应商不参与内置供应商的故障转移链
- **安全提醒**：API Key 仅在内存中存储，不写入日志或数据库

## 相关文档

- [API Key 使用指南](../guides/API-KEY-GUIDE.md)
- [多供应商配置指南](../guides/MULTI-PROVIDER-SETUP.md)
- [项目功能介绍](PROJECT-INTRODUCTION.md)
- [架构设计](../architecture/ARCHITECTURE.md)
