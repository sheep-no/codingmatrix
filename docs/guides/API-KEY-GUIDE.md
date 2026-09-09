# 用户 API Key 指南

> 最后更新：2026-09-03

本文档说明 `/api/v1/agent/apikey` 管理的用户内置供应商 Key。部署级环境变量与动态供应商配置见 [多供应商配置指南](MULTI-PROVIDER-SETUP.md)。

## 数据流与存储

1. 已认证前端读取 `GET /api/v1/agent/apikey/public-key`。
2. 前端使用 RSA-OAEP/SHA-256 加密 API Key，提交 `encrypted_key`。
3. 后端在内存中解密，并将真实 Key、元数据和 Token 反向索引写入 Redis。
4. 客户端只保留随机 UUID Token；模型调用通过 Token 查找对应 Key。
5. Redis TTL 到期后 Key 自动失效，相关索引在后续读取时清理。

Redis 中保存的是后端解密后的 API Key。安全边界依赖 Redis 访问控制、网络隔离、持久化策略和主机权限。该模块不把用户 Key 写入 SQL 数据库。

## 支持范围

| provider 值 | 供应商 | 默认模型同步 |
|---------------|--------|--------------|
| `siliconflow` | SiliconFlow | OpenAI 兼容 `/models` |
| `openai` | OpenAI | OpenAI 兼容 `/models` |
| `anthropic` | Anthropic | 提交时不自动同步 |
| `bailian` | 阿里百炼 | OpenAI 兼容 `/models` |
| `glm` | 智谱 GLM | OpenAI 兼容 `/models` |
| `deepseek` | DeepSeek | OpenAI 兼容 `/models` |

每个用户最多保存 20 个 Key。

## TTL

单 Key 提交模型的 `ttl` 是整数秒，默认 `86400`，有效范围为 `1` 到 `315360000`。批量导入的每项使用以下预设字符串：

| 值 | 秒数 |
|----|------|
| `1h` | `3600` |
| `24h` | `86400` |
| `7d` | `604800` |
| `30d` | `2592000` |
| `never` | `315360000`，约 10 年 |

底层管理器也能解析预设字符串和数字字符串；当前单 Key API 的 Pydantic 模型会先将请求限制为整数，批量导入则只接受表中的预设字符串。

## 端点

所有管理端点均要求 `Authorization: Bearer <ACCESS_TOKEN>`，公钥端点除外。

| 方法 | 路径 | 用途 |
|------|------|------|
| `GET` | `/api/v1/agent/apikey/public-key` | 获取 API Key 加密公钥 |
| `POST` | `/api/v1/agent/apikey` | 提交加密 Key |
| `POST` | `/api/v1/agent/apikey/test` | 测试 Token 对应的 Key |
| `GET` | `/api/v1/agent/apikeys` | 列出当前用户 Key 元数据 |
| `DELETE` | `/api/v1/agent/apikey/{token}` | 删除 Key |
| `PUT` | `/api/v1/agent/apikey/{token}/enabled` | 启用或禁用 |
| `PUT` | `/api/v1/agent/apikey/{token}/context-lengths` | 更新模型上下文长度映射 |
| `GET` | `/api/v1/agent/apikey/{token}/fallback-preference` | 读取降级偏好 |
| `PUT` | `/api/v1/agent/apikey/{token}/fallback-preference` | 更新降级偏好 |
| `POST` | `/api/v1/agent/apikey/batch/import` | 批量导入加密 Key |
| `GET` | `/api/v1/agent/apikey/batch/export` | 导出元数据 |

列表路径是 `/api/v1/agent/apikeys`，由路由前缀 `/api/v1/agent/apikey` 与子路径 `s` 组合而成。

## 提交示例

`encrypted_key` 必须由服务端公钥加密。以下示例只展示请求结构：

```bash
curl -X POST http://localhost:8000/api/v1/agent/apikey \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "encrypted_key": "<BASE64_RSA_CIPHERTEXT>",
    "provider": "siliconflow",
    "ttl": 86400,
    "remark": "<KEY_REMARK>"
  }'
```

响应中的 `token` 是模型调用使用的引用标识，不包含真实 API Key。

## Key 状态与操作

元数据状态包括 `unverified`、`verified`、`invalid` 和 `expired`。新 Key 初始为 `unverified`；测试接口更新验证状态并返回模型列表。`enabled=false` 的 Key 仍保留在 Redis 中，模型调用选择时应排除该 Key。

上下文长度配置格式为模型 ID 到正整数的映射：

```json
{
  "context_lengths": {
    "<MODEL_ID>": 32768
  }
}
```

## 降级偏好

| 值 | 行为 |
|----|------|
| `use_admin_default` | 使用管理员模型配置中的默认降级链 |
| `custom` | 使用 `custom_fallback_chain` |
| `disabled` | 调用层设置 `disable_fallback=True` |

```bash
# 关闭当前 Key 的供应商降级
curl -X PUT http://localhost:8000/api/v1/agent/apikey/<KEY_TOKEN>/fallback-preference \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"fallback_preference":"disabled","custom_fallback_chain":[]}'

# 配置自定义模型链
curl -X PUT http://localhost:8000/api/v1/agent/apikey/<KEY_TOKEN>/fallback-preference \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"fallback_preference":"custom","custom_fallback_chain":["<MODEL_A>","<MODEL_B>"]}'
```

## 批量导入与导出

批量导入的每项包含 `provider`、RSA 加密后的 `encrypted_key`、预设字符串 `ttl` 和可选 `remark`。批量导出返回元数据，不导出真实 Key；支持的格式由接口查询参数控制。

## 运维要求

- 为 Redis 配置访问控制、受限网络和符合风险要求的持久化策略。
- 生产环境通过 HTTPS 保护公钥获取、Token 管理和动态供应商请求。
- 日志只记录 Token 截断值和供应商信息，业务代码不得记录真实 Key。
- Key 到期或删除后重新添加并更新调用方 Token。
- 供应商返回 401、403、429 或余额错误时，先检查 Key 状态、权限、限额和账户余额。

## 相关文档

- [多供应商配置指南](MULTI-PROVIDER-SETUP.md)
- [安全概览](../security/SECURITY-OVERVIEW.md)
- [快速开始](GETTING-STARTED.md)
