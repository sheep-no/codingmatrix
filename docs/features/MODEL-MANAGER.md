# 模型管理接口

> 最后更新：2026-06-25 | 版本：v5.13.0+

## 概述

模型管理接口提供 AI 模型的配置、查看和管理能力。

## v5.13.0+ 统一模型配置

### 新接口 (推荐)

新的统一模型配置接口更简单直观，支持任意供应商模型。

**配置文件**: `data/unified_model_config.json`

**API 前缀**: `/api/v2/model-config`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v2/model-config/models` | 获取所有模型 |
| POST | `/api/v2/model-config/models` | 添加模型 |
| PUT | `/api/v2/model-config/models/{id}` | 更新模型 |
| DELETE | `/api/v2/model-config/models/{id}` | 删除模型 |
| PUT | `/api/v2/model-config/models/{id}/toggle` | 切换启用状态 |
| GET | `/api/v2/model-config/providers` | 获取供应商列表 |
| POST | `/api/v2/model-config/providers` | 添加供应商 |
| DELETE | `/api/v2/model-config/providers/{id}` | 删除供应商 |
| GET | `/api/v2/model-config/agent` | 获取 Agent 配置 |
| PUT | `/api/v2/model-config/agent/role` | 更新角色模型 |
| PUT | `/api/v2/model-config/agent/fallback` | 更新降级链 |
| POST | `/api/v2/model-config/reload` | 重新加载配置 |

### 添加新模型

只需在配置文件中添加一行：

```json
{
  "models": {
    "gpt-4o": {
      "name": "gpt-4o",
      "display_name": "GPT-4o",
      "provider": "openai",
      "type": "chat",
      "context_length": 128000,
      "max_output": 16384
    }
  }
}
```

或使用 API：

```bash
curl -X POST http://localhost:8000/api/v2/model-config/models \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "id": "gpt-4o",
    "name": "gpt-4o",
    "display_name": "GPT-4o",
    "provider": "openai",
    "model_type": "chat",
    "context_length": 128000
  }'
```

### 模型类型

| 类型 | 说明 | 示例 |
|------|------|------|
| `chat` | 对话模型 | Qwen3, DeepSeek R1 |
| `embedding` | 嵌入模型 | BGE M3, BCE Embedding |
| `vision` | 视觉理解 | GLM 4.1V, DeepSeek OCR |
| `image` | 图像生成 | Kolors |
| `audio` | 音频处理 | SenseVoice |

### Agent 角色配置

```bash
# 更新角色模型
curl -X PUT http://localhost:8000/api/v2/model-config/agent/role \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"role": "architect", "model_id": "qwen3-8b"}'

# 更新降级链
curl -X PUT http://localhost:8000/api/v2/model-config/agent/fallback \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"chain": ["qwen3-8b", "glm-z1-9b"]}'
```

## 旧接口 (已废弃)

> ⚠️ 以下接口保留用于向后兼容，将在未来版本中移除。请使用新的 `/api/v2/model-config/*` 接口。

### 用户端接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/models/` | 获取模型列表 |
| GET | `/api/v1/models/default` | 获取默认模型 |
| GET | `/api/v1/models/{id}` | 获取模型详情 |
| GET | `/api/v1/models/capabilities/list` | 获取能力列表 |
| GET | `/api/v1/models/agent-config` | 获取 Agent 配置 |

### 管理端接口

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v2/models/default` | 切换默认模型 |
| PUT | `/api/v2/models/agent-config` | 更新角色配置 |
| PUT | `/api/v2/models/agent-config/fallback-chain` | 更新降级链 |
| PUT | `/api/v2/models/agent-config/error-type-model` | 更新错误类型映射 |
| POST | `/api/v2/models/agent-config/reload` | 重新加载配置 |
| GET | `/api/v2/models/context-lengths` | 获取上下文长度 |
| PUT | `/api/v2/models/context-length` | 更新上下文长度 |
| DELETE | `/api/v2/models/context-length/{key}` | 删除上下文长度 |

## 内置模型列表

共 17 个内置模型。

| 模型 ID | 显示名称 | 类型 | 上下文 |
|---------|----------|------|--------|
| qwen3-8b | Qwen3 8B | chat | 128k |
| deepseek-r1 | DeepSeek R1 | chat | 128k |
| nex-n2-pro | Nex N2 Pro | chat | 256k |
| glm-z1-9b | GLM Z1 9B | chat | 128k |
| glm-4-9b | GLM 4 9B | chat | 32k |
| qwen2.5-7b | Qwen2.5 7B | chat | 32k |
| qwen3.5-4b | Qwen3.5 4B | chat | 256k |
| deepseek-ocr | DeepSeek OCR | vision | 8k |
| glm-4.1v-9b | GLM 4.1V 9B | vision | 32k |
| kolors | Kolors | image | 4k |
| bge-m3 | BGE M3 | embedding | 8k |
| bce-embedding | BCE Embedding | embedding | 512 |
| bge-reranker | BGE Reranker | embedding | 8k |
| hunyuan-mt | Hunyuan MT | chat | 32k |
| sense-voice | SenseVoice | audio | 4k |

## 配置文件

### unified_model_config.json (新)

```json
{
  "version": "5.0",
  "providers": {
    "siliconflow": {
      "name": "SiliconFlow",
      "base_url": "https://api.siliconflow.cn/v1"
    }
  },
  "models": {
    "qwen3-8b": {
      "name": "Qwen/Qwen3-8B",
      "display_name": "Qwen3 8B",
      "provider": "siliconflow",
      "type": "chat",
      "context_length": 131072,
      "max_output": 8192,
      "temperature": 0.7,
      "timeout": 300,
      "enabled": true
    }
  },
  "agent": {
    "roles": {
      "architect": "qwen3-8b",
      "frontend": "deepseek-r1",
      "backend": "nex-n2-pro",
      "reviewer": "glm-z1-9b",
      "fallback": "qwen3-8b"
    },
    "fallback_chain": ["qwen3-8b", "glm-z1-9b"]
  }
}
```

### agent_model_config.json (旧)

保留用于向后兼容，新项目请使用 `unified_model_config.json`。

## 相关文件

- `app/services/model_config_manager.py` - **新**: 统一配置管理器
- `app/api/v2/model_config_api.py` - **新**: 统一配置 API
- `data/unified_model_config.json` - **新**: 统一配置文件
- `app/api/v1/model_manager.py` - 旧: 用户端接口
- `app/api/v2/model_admin.py` - 旧: 管理端接口 (已废弃)
- `app/utils/aicloud/model_registry.py` - 模型注册表
- `app/agent/dynamic_model_router.py` - 动态路由
