# 多供应商模型配置指南

> 最后更新：2026-09-03

项目提供三类供应商配置入口：部署级环境变量、用户内置供应商 Key、运行时动态供应商。三者的存储方式和路由优先级不同。

## 部署级供应商

`app/core/config.py` 定义以下配置：

| 供应商 | API Key | Base URL | 默认地址 |
|--------|---------|----------|----------|
| SiliconFlow | `SILICONFLOW_API_KEY` | `SILICONFLOW_BASE_URL` | `https://api.siliconflow.cn/v1` |
| 阿里百炼 | `DASHSCOPE_API_KEY` | `DASHSCOPE_BASE_URL` | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| 智谱 GLM | `ZHIPU_API_KEY` | `ZHIPU_BASE_URL` | `https://open.bigmodel.cn/api/paas/v4` |
| DeepSeek | `DEEPSEEK_API_KEY` | `DEEPSEEK_BASE_URL` | `https://api.deepseek.com/v1` |
| OpenAI | `OPENAI_API_KEY` | `OPENAI_BASE_URL` | `https://api.openai.com/v1` |
| Anthropic | `ANTHROPIC_API_KEY` | `ANTHROPIC_BASE_URL` | `https://api.anthropic.com/v1` |
| Ollama | 无 | `OLLAMA_BASE_URL` | `http://localhost:11434` |

除 Ollama 外，注册表只启用同时具有非空 API Key 和 Base URL 的供应商。Ollama 只要求 Base URL。

```bash
SILICONFLOW_API_KEY=<SILICONFLOW_API_KEY>
DASHSCOPE_API_KEY=<DASHSCOPE_API_KEY>
ZHIPU_API_KEY=<ZHIPU_API_KEY>
DEEPSEEK_API_KEY=<DEEPSEEK_API_KEY>
OPENAI_API_KEY=<OPENAI_API_KEY>
ANTHROPIC_API_KEY=<ANTHROPIC_API_KEY>
OLLAMA_BASE_URL=http://localhost:11434
```

## 模型路由

`app/utils/aicloud/provider_router.py` 从 `data/agent_model_config.yaml` 的 `models.*.provider` 构建模型映射，并补充以下兼容映射：

| 模型 | 供应商 |
|------|--------|
| `qwen-plus`、`qwen-turbo`、`qwen-max`、`qwen-long` | 阿里百炼 |
| `glm-4`、`glm-4v`、`glm-4-alltools` | 智谱 GLM |
| `deepseek-chat`、`deepseek-reasoner` | DeepSeek |
| `THUDM/glm-4-9b-chat`、`Qwen/Qwen-2.5-7B-Instruct`、`THUDM/GLM-4.1V-9B-Thinking`、`BAAI/bge-m3`、`deepseek-ai/DeepSeek-R1` | SiliconFlow |

精确模型名优先，其次按模型名前缀匹配；未知模型回退到 SiliconFlow 路由。动态供应商已同步的模型优先于静态映射。

## 调用优先级

`call_llm()` 按以下顺序选择适配器：

1. 请求显式传入且已启用的 `provider_id`
2. 请求传入的用户 `api_key_token`
3. 动态供应商中已登记该模型的条目
4. 部署级供应商注册表与模型路由

用户 Token 从 Redis 解析真实 Key。Token 已过期或不存在时调用直接报错。适配器建立后，模型调用执行速率限制重试；流式迭代期间保持全局和模型级并发信号量。

## 故障转移

静态供应商初始化失败时使用以下候选链，并过滤当前注册表中不可用的供应商：

| 主供应商 | 候选供应商 |
|----------|------------|
| SiliconFlow | 阿里百炼、智谱 GLM |
| 阿里百炼 | SiliconFlow |
| 智谱 GLM | SiliconFlow |
| DeepSeek | SiliconFlow |
| OpenAI | SiliconFlow |
| Anthropic | SiliconFlow |
| Ollama | 无 |

`disable_fallback=True` 会关闭该降级路径。当前实现的 provider fallback 发生在适配器获取阶段；已建立适配器后的 HTTP 调用失败由该适配器和速率限制重试处理。

## 用户内置供应商 Key

API Key 管理接口支持以下 provider 标识：

- `siliconflow`
- `openai`
- `anthropic`
- `bailian`
- `glm`
- `deepseek`

提交地址为 `POST /api/v1/agent/apikey`。前端从 `GET /api/v1/agent/apikey/public-key` 获取公钥并加密 Key；后端解密后按用户 ID 和随机 Token 保存到 Redis。OpenAI 兼容供应商提交成功后会尝试同步模型；Anthropic 保存 Key，但不进入该自动同步集合。

具体端点、TTL 和降级偏好见 [API Key 指南](API-KEY-GUIDE.md)。

## 动态供应商

动态供应商 API 前缀为 `/api/v1/providers`，所有端点要求 Bearer access token。

| 方法 | 路径 | 用途 |
|------|------|------|
| `POST` | `/api/v1/providers` | 添加供应商 |
| `GET` | `/api/v1/providers` | 列表 |
| `GET` | `/api/v1/providers/{pid}` | 详情 |
| `PUT` | `/api/v1/providers/{pid}/toggle` | 启用或禁用 |
| `POST` | `/api/v1/providers/{pid}/sync` | 同步模型，默认缓存 5 分钟 |
| `POST` | `/api/v1/providers/{pid}/test` | 测试连接 |
| `DELETE` | `/api/v1/providers/{pid}` | 删除 |

支持协议值 `openai` 和 `anthropic`。OpenAI 兼容调用使用 `{base_url}/chat/completions` 与 Bearer Token；Anthropic 调用使用 `{base_url}/messages`、`x-api-key` 和 `anthropic-version`。

动态供应商请求体中的 `api_key` 直接提交给后端，依赖 HTTPS 保护传输。当前 `DynamicProviderManager` 为进程内运行时管理器，接口实现未按用户 ID 隔离记录；多用户部署应在启用该功能前补充用户作用域与持久化策略。

## Python 调用

```python
from app.utils.aicloud import call_llm

result = await call_llm(
    model="Qwen/Qwen3-8B",
    prompt="你好",
)
```

调用方可按需传入 `api_key_token`、`provider_id`、`stream`、`messages` 或 `disable_fallback`。

## 配置核验

- 检查模型名是否存在于 `data/agent_model_config.yaml` 或兼容映射。
- 检查目标供应商的 API Key 与 Base URL 是否同时可用。
- 用户 Key 依赖 Redis，确认 `REDIS_URL` 指向可访问实例。
- 动态供应商先同步模型，再确认目标模型出现在供应商模型列表中。
- 生产配置使用占位符模板和密钥管理系统保存凭据。
