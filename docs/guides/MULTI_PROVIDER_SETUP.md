# 多供应商模型配置指南

## 概述

从 v5.4.0 开始，CodingMatrix 支持多个 LLM API 供应商，通过统一的调用接口自动路由到对应供应商，并支持故障转移。

## 支持的供应商

| 供应商 | 环境变量前缀 | 支持模型 | 说明 |
|--------|------------|---------|------|
| SiliconFlow | `SILICONFLOW_` | 所有 10 个内置模型 | 默认供应商 |
| 阿里百炼 | `DASHSCOPE_` | qwen-plus、qwen-turbo 等 Qwen 系列 | 阿里云 |
| 智谱 GLM | `ZHIPU_` | glm-4、glm-4v 等 GLM 系列 | 智谱 AI |
| DeepSeek 官方 | `DEEPSEEK_` | deepseek-chat、deepseek-reasoner | DeepSeek 官方 |
| OpenAI | `OPENAI_` | gpt-4o、gpt-4o-mini 等 | OpenAI |
| Anthropic | `ANTHROPIC_` | claude-3-5-sonnet、claude-3-opus 等 | Anthropic |
| Ollama | `OLLAMA_` | 本地部署的任何模型 | 本地服务 |

## 快速开始

### 1. 最小配置

只需要配置 SiliconFlow API Key 即可使用所有 10 个内置模型：

```bash
SILICONFLOW_API_KEY=your-api-key
```

### 2. 添加额外供应商

在 `.env` 文件中添加其他供应商的 API Key：

```bash
# 阿里百炼
DASHSCOPE_API_KEY=your-dashscope-api-key

# 智谱 GLM
ZHIPU_API_KEY=your-zhipu-api-key

# OpenAI
OPENAI_API_KEY=your-openai-api-key
```

### 3. 使用统一调用接口

```python
# 新方式：自动路由到对应供应商
from app.utils.aicloud import call_llm

# 会自动路由到 SiliconFlow
result = await call_llm(
    model="Qwen/Qwen3.5-4B",
    prompt="你好",
)

# 如果配置了 DashScope API Key，会自动路由到阿里百炼
result = await call_llm(
    model="qwen-plus",
    prompt="你好",
)
```

## 模型路由

系统根据模型名称自动选择供应商：

| 模型模式 | 供应商 |
|---------|--------|
| `deepseek-ai/*` | SiliconFlow |
| `Qwen/*` | SiliconFlow |
| `THUDM/*` | SiliconFlow |
| `Kwai-Kolors/*` | SiliconFlow |
| `qwen-plus` / `qwen-turbo` | 阿里百炼 |
| `glm-4` / `glm-4v` | 智谱 GLM |
| `deepseek-chat` / `deepseek-reasoner` | DeepSeek 官方 |

未知模型默认路由到 SiliconFlow。

## 故障转移

当主供应商失败时，系统自动尝试备份供应商：

- SiliconFlow 失败 → 阿里百炼 → 智谱 GLM
- 智谱 GLM 失败 → SiliconFlow
- 阿里百炼失败 → SiliconFlow

流式输出模式不支持故障转移。

## 向后兼容

现有的 `call_siliconflow()` 函数继续有效：

```python
from app.utils.AiCodeUtil import call_siliconflow

result = await call_siliconflow(
    prompt="你好",
    model="Qwen/Qwen3.5-4B",
)
```

## 自定义 Base URL

可以通过环境变量覆盖默认 Base URL：

```bash
SILICONFLOW_BASE_URL=https://custom-siliconflow-proxy.com/v1
DASHSCOPE_BASE_URL=https://custom-dashscope-proxy.com/v1
```
