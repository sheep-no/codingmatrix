# 动态供应商

> 最后更新：2026-09-03

动态供应商允许已认证用户通过自定义 `base_url`、协议和 API Key 接入 OpenAI 兼容或 Anthropic 原生聊天服务。对外 API 位于 `/api/v1/providers`。

## 支持协议

### OpenAI 兼容

- 模型同步：`GET {base_url}/models`
- 聊天调用：`POST {base_url}/chat/completions`
- 认证：`Authorization: Bearer {api_key}`
- 模型同步会尝试读取 `context_length`、`max_context_length`、`max_model_len` 及 metadata/meta 中的上下文字段，缺省上下文为 32768。

调用方应提交已经包含所需版本路径的 `base_url`。动态供应商管理器仅移除末尾斜杠。

### Anthropic 原生

- 聊天调用：`POST {base_url}/messages`
- 认证：`x-api-key` 与 `anthropic-version: 2023-06-01`
- 模型同步直接返回代码内维护的 Claude 模型清单。
- 非流式响应由 `DynamicAdapter` 转换为 OpenAI 风格的 `choices[0].message.content`。

动态适配器当前仅实现聊天，embedding 调用会抛出 `NotImplementedError`。

## API

| 方法 | 路径 | 说明 | 限流 |
|------|------|------|------|
| POST | `/api/v1/providers` | 添加供应商 | 10/分钟 |
| GET | `/api/v1/providers` | 列表 | 30/分钟 |
| GET | `/api/v1/providers/{id}` | 详情 | 30/分钟 |
| DELETE | `/api/v1/providers/{id}` | 删除 | 10/分钟 |
| PUT | `/api/v1/providers/{id}/toggle` | 启用或禁用 | 20/分钟 |
| POST | `/api/v1/providers/{id}/sync` | 同步模型 | 10/分钟 |
| POST | `/api/v1/providers/{id}/test` | 测试连接 | 20/分钟 |

所有端点使用 JWT `verify_token`。添加接口验证协议值和 API Key 最小长度；添加后需要显式调用同步接口获取模型。`force=true` 可跳过 5 分钟模型列表缓存。

列表和详情响应会隐藏 API Key，只返回 ID、名称、URL、协议、启用状态、模型 ID、同步时间和错误。

## 调用优先级

`app/utils/aicloud/llm_caller.py` 的适配器选择顺序为：

1. 请求显式提供 `provider_id` 时使用对应动态供应商。
2. 请求提供用户 API Key Token 时使用该 Token 对应的内置供应商配置。
3. 按模型 ID 在启用的动态供应商中查找。
4. 使用系统 ProviderRegistry 和静态模型到供应商映射。

OpenAI 与 Anthropic 动态调用支持流式和非流式聊天。非流式动态请求使用共享 HTTP 客户端和最多 3 次底层重试；统一调用层还处理 429 重试和并发信号量。

内置供应商降级链主要作用于系统供应商适配器创建失败和流式调用开始前失败。动态供应商失败沿用当前调用异常路径，故障转移候选仅来自内置供应商注册表。

## 存储与作用域

- `DynamicProviderManager` 是 Python 进程内全局单例。
- 供应商、API Key、模型列表和同步错误均保存在内存中，服务重启或多进程切换会丢失或产生不同视图。
- 当前 API 数据按全局单例组织，所有通过认证的调用者共享该进程中的动态供应商集合。
- 前端 Pinia Store 将服务端返回的脱敏供应商数据缓存到 `localStorage`，用于离线显示。

这套动态供应商与以下机制相互独立：

- `/api/v2/model-config/providers`：superadmin 管理并写入统一 YAML 的供应商配置。
- 用户 API Key 管理：密钥保存在 Redis，并可在启动时恢复 `CustomProviderManager` 的模型列表。
- `app/services/custom_provider_manager.py`：另一套进程内管理器，模型列表缓存为 1 小时，主要服务用户 API Key 流程。

## 前端

设置页的 `DynamicProviderManager.vue` 支持：

- 添加供应商。
- 列出模型和同步错误。
- 强制同步模型。
- 测试连接。
- 启用、禁用和删除。

`src/stores/providers.js` 负责 API 调用，并可将所有启用供应商的模型整理为带 `provider_id` 的选项。

## 当前边界

- API Key 仅存于当前后端进程，接口采用认证用户全局共享作用域，适合受信任的单租户或受控管理场景。
- OpenAI 测试固定使用 `gpt-3.5-turbo`，Anthropic 测试固定使用 `claude-3-haiku-20240307`；供应商未提供这些模型时，测试结果可能无法代表其他模型可用性。
- Anthropic 模型清单由代码静态维护，可能与实际账户权限不同。

## 相关文件

- `app/api/v1/providers.py`
- `app/utils/aicloud/dynamic_provider.py`
- `app/utils/aicloud/adapters/dynamic.py`
- `app/utils/aicloud/llm_caller.py`
- `app/utils/aicloud/provider_router.py`
- `app/services/custom_provider_manager.py`
- `src/components/settings/DynamicProviderManager.vue`
- `src/stores/providers.js`
