# API Key 使用指南

> 最后更新：2026-06-01 | 版本：v5.12.0

本文档详细介绍 CodingMatrix 平台的 API Key 管理机制和使用方法。

## 1. API Key 管理概述

### 1.1 为什么需要 API Key？

平台的所有 AI 功能（代码生成、项目生成、对话、PPT 生成、图像生成等）都需要调用大语言模型。用户可以配置自己的 API Key，系统将使用用户的 Key 进行调用，避免消耗平台资源。

### 1.2 安全机制

- **RSA-2048 加密传输**：API Key 在前端使用 RSA 公钥加密后传输
- **Redis 内存存储**：加密后的 Token 存储在 Redis 中，不写入数据库
- **TTL 自动过期**：Key 有有效期，到期自动清除（1 小时 / 24 小时 / 7 天 / 30 天 / 永久）
- **前端不保存 Key**：前端仅保存无意义的 Token UUID
- **按需获取**：调用时从 Redis 临时读取，使用后释放

### 1.3 新增功能 (v5.12.0)

- **自动模型同步**：提交 OpenAI/Anthropic/DeepSeek/GLM/阿里百炼 Key 时自动从 `/v1/models` 拉取模型列表
- **自定义 context_length**：用户可为每个 Key 设置模型的上下文长度，仅对自己的请求生效
- **模型配置管理**：在 Key 卡片中展开「模型配置」区域，添加/编辑/删除模型的 context_length

## 2. 配置 API Key

### 2.1 硅基流动 Key（必填）

硅基流动 (SiliconFlow) 是平台的默认供应商，必须配置才能使用 AI 功能。

#### 配置步骤

1. **注册硅基流动账号**
   - 访问 [cloud.siliconflow.cn](https://cloud.siliconflow.cn/)
   - 完成注册和实名认证

2. **获取 API Key**
   - 登录后进入「API Keys」页面
   - 点击「创建 API Key」
   - 复制生成的 Key

3. **在平台配置 Key**
   - 打开平台设置页面 → 「API Key 管理」标签
   - 在「硅基流动」卡片中输入 API Key
   - 选择有效期（默认 24 小时）
   - 点击「保存」

#### 支持的模型

硅基流动提供以下模型：
- **Qwen 系列**：Qwen/Qwen3-8B 及其他 Qwen 变体
- **GLM 系列**：THUDM/GLM-Z1-9B-0414 及其他 GLM 变体
- **其他**：平台 `agent_model_config.json` 中配置的模型

### 2.2 其他供应商 Key（可选）

平台支持多个供应商同时配置：

| 供应商 | 说明 |
|--------|------|
| OpenAI | GPT-3.5-turbo, GPT-4, GPT-4o 等 |
| Anthropic | Claude 3 Haiku, Sonnet, Opus |
| 阿里百炼 | 通义千问系列 (dashscope) |
| 智谱 GLM | GLM-4, GLM-4V |
| DeepSeek | deepseek-chat, deepseek-reasoner |

#### 配置步骤

1. 在「其他供应商」区域选择供应商类型
2. 输入对应的 API Key
3. 填写备注（可选，用于识别）
4. 选择有效期
5. 点击「添加」

### 2.3 Key 管理操作

| 操作 | 说明 |
|------|------|
| 测试连接 | 验证 Key 是否有效 |
| 启用/禁用 | 临时禁用某个 Key 而不删除 |
| 清除 | 永久删除 Key，不可恢复 |

## 3. 降级偏好设置 (fallback_preference)

每个 API Key 可以独立配置降级策略，控制当主模型失败时的行为。

### 3.1 三种模式

| 模式 | 说明 |
|------|------|
| use_admin_default | 使用管理员配置的全局降级链（默认） |
| custom | 使用用户自定义的降级链 |
| disabled | 禁用降级，仅使用用户自己的模型 |

### 3.2 API 端点

```bash
# 设置降级偏好
curl -X PUT http://localhost:8000/api/v1/agent/apikey/{token}/fallback-preference \
  -H "Authorization: Bearer <JWT>" \
  -H "Content-Type: application/json" \
  -d '{"fallback_preference": "disabled"}'

# 自定义降级链
curl -X PUT http://localhost:8000/api/v1/agent/apikey/{token}/fallback-preference \
  -H "Authorization: Bearer <JWT>" \
  -H "Content-Type: application/json" \
  -d '{"fallback_preference": "custom", "custom_fallback_chain": ["Qwen/Qwen3-8B", "THUDM/GLM-Z1-9B-0414"]}'

# 查看当前配置
curl http://localhost:8000/api/v1/agent/apikey/{token}/fallback-preference \
  -H "Authorization: Bearer <JWT>"
```

### 3.3 工作原理

- `disabled` 模式：`LLMClient` 检测到偏好后设置 `disable_fallback=True`，`call_llm()` 跳过所有 provider 级别降级
- `custom` 模式：`ErrorRecoveryLoop` 使用用户提供的模型列表进行降级
- `use_admin_default` 模式：使用 `agent_model_config.json` 中的 `fallback_chain`

## 4. Token 使用统计

设置页面提供详细的 Token 使用统计：

### 4.1 统计维度

- **今日使用量**：当天消耗的 Token 总数
- **本月使用量**：当月累计 Token
- **总计使用量**：所有时间的 Token 总和
- **消息总数**：发送的消息条数
- **按模型统计**：每个模型消耗的 Token 分布

### 4.2 用途

- 监控 API 调用成本
- 优化模型选择（选择性价比更高的模型）
- 审计异常消耗

## 5. Agent 角色模型配置

平台支持为 Agent 的不同角色配置不同的模型，基于 `agent_model_config.json` 中定义的 5 角色系统：

### 5.1 角色说明

| 角色 | 用途 | 推荐模型 |
|------|------|---------|
| architect | 架构设计、任务分析与规划 | Qwen/Qwen3-8B, THUDM/GLM-Z1-9B-0414 |
| frontend | 前端代码生成 | Qwen/Qwen3-8B, THUDM/GLM-Z1-9B-0414 |
| backend | 后端代码生成 | Qwen/Qwen3-8B, THUDM/GLM-Z1-9B-0414 |
| reviewer | 代码审查和质量检查 | Qwen/Qwen3-8B, THUDM/GLM-Z1-9B-0414 |
| fallback | 降级备用模型 | Qwen/Qwen3-8B, THUDM/GLM-Z1-9B-0414 |

### 5.2 配置方法

1. 进入设置页面 → 「Agent 模型配置」标签
2. 每个角色可选择：
   - **系统默认**：使用 `agent_model_config.json` 中配置的默认模型
   - **已配置的 API Key**：选择特定的 Key 和模型
   - **自定义供应商模型**：选择已添加的动态供应商模型
3. 配置自动保存

### 5.3 降级链配置

管理员可在 `agent_model_config.json` 中配置全局降级链（`fallback_chain`），当主模型不可用时按顺序尝试降级。用户也可通过降级偏好设置（见第3节）自定义个人降级链或禁用降级。

## 6. 自定义供应商（动态供应商）

### 6.1 什么是动态供应商？

支持通过自定义 `base_url` + 协议类型添加任意兼容 OpenAI 或 Anthropic 协议的 API 服务。

### 6.2 支持的协议

| 协议 | 调用端点 | 认证方式 |
|------|---------|---------|
| OpenAI 兼容 | `{base_url}/chat/completions` | Bearer Token |
| OpenAI 兼容 | `{base_url}/models` | Bearer Token（拉取模型列表） |
| Anthropic 原生 | `{base_url}/messages` | x-api-key Header |

### 6.3 添加供应商

1. 进入设置页面 → 「自定义供应商」标签
2. 填写表单：
   - **供应商名称**：自定义名称（如 "Claude 代理"）
   - **Base URL**：API 服务地址（如 `https://api.example.com/v1`）
   - **协议类型**：OpenAI 兼容 / Anthropic 原生
   - **API Key**：服务访问密钥
3. 点击「添加供应商」
4. 添加后点击「同步模型」拉取模型列表
5. 点击「测试连接」验证可用性

### 6.4 供应商管理

| 操作 | 说明 |
|------|------|
| 同步模型 | 从供应商拉取最新模型列表（缓存 5 分钟） |
| 测试连接 | 发送测试请求验证 Key 和连通性 |
| 启用/禁用 | 控制供应商是否参与调用 |
| 删除 | 移除供应商配置 |

### 6.5 使用动态供应商

添加并启用后，动态供应商的模型会出现在：
- Agent 角色模型配置的下拉列表中
- 对话模型选择器中（如果平台支持）
- 项目生成的模型配置中

## 7. 常见问题

### 7.1 Key 过期了怎么办？

1. 清除过期的 Key
2. 重新添加新的 Key
3. 或联系供应商续费/刷新 Token

### 7.2 为什么测试连接失败？

- 检查 Key 是否正确
- 检查网络是否可达供应商 API
- 检查供应商账户余额是否充足
- 查看供应商是否有区域限制

### 7.3 可以同时使用多个 Key 吗？

可以。平台支持多个供应商 Key 同时配置，不同环节可使用不同的 Key。

### 7.4 Key 会被平台保存吗？

不会。Key 仅在 Redis 中加密存储，TTL 到期后自动清除，不写入持久化数据库。

### 7.5 如何选择性价比最高的模型？

- 简单任务：使用 Qwen/Qwen3-8B, THUDM/GLM-Z1-9B-0414
- 日常开发：使用 Qwen/Qwen3-8B, THUDM/GLM-Z1-9B-0414
- 复杂任务：使用 Qwen/Qwen3-8B, THUDM/GLM-Z1-9B-0414
- 代码生成：使用 Qwen/Qwen3-8B, THUDM/GLM-Z1-9B-0414

## 相关文档

- [多供应商配置指南](MULTI-PROVIDER-SETUP.md)

- [安全说明](../security/SECURITY-OVERVIEW.md)
- [快速开始](GETTING-STARTED.md)
