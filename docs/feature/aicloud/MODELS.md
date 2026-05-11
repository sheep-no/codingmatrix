# Aicloud 模型配置

## 支持的模型

| 模型 | 提供商 | 用途 | 上下文长度 |
|------|--------|------|-----------|
| Qwen2.5-Coder-7B | SiliconFlow | 代码生成 | 32K |
| Qwen2.5-72B-Instruct | SiliconFlow | 通用对话 | 32K |
| DeepSeek-V3 | SiliconFlow | 通用对话 | 128K |
| glm-4-plus | SiliconFlow | 通用对话 | 128K |

## 模型选择

- **代码生成**: 优先使用 Qwen2.5-Coder 系列
- **通用对话**: Qwen2.5-72B 或 DeepSeek-V3
- **长上下文**: DeepSeek-V3 (128K) 或 glm-4-plus (128K)

## 配置方式

通过环境变量或 `/api/v2/Controller/admin/config` 端点配置:

```
AI_MODEL=qwen2.5-coder-7b-instruct
AI_MAX_TOKENS=4096
AI_TEMPERATURE=0.7
```
