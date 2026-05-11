# 模型适配器

## 概述

CodingMatrix 支持多种 LLM 模型，通过统一的适配器接口进行调用。

## 支持的模型

| 模型 | 提供商 | 用途 | 上下文长度 |
|------|--------|------|-----------|
| Qwen2.5-Coder-7B-Instruct | SiliconFlow | 代码生成 | 32K |
| Qwen2.5-72B-Instruct | SiliconFlow | 通用对话 | 32K |
| DeepSeek-V3 | SiliconFlow | 通用对话 | 128K |
| glm-4-plus | SiliconFlow | 通用对话 | 128K |
| Qwen2.5-VL | SiliconFlow | 视觉分析 | 8K |

## 模型选择策略

| 场景 | 推荐模型 |
|------|----------|
| 代码生成 | Qwen2.5-Coder-7B |
| 通用对话 | Qwen2.5-72B |
| 长上下文 | DeepSeek-V3 |
| 图像分析 | Qwen2.5-VL |
| PPT 内容生成 | Qwen2.5-72B |

## 配置

```env
# 默认模型
DEFAULT_MODEL=qwen2.5-coder-7b-instruct

# 视觉模型
VISION_MODEL=qwen2.5-vl

# Nginx AI 模型
NGINX_AI_MODEL=qwen2.5-coder-7b-instruct
```

## 相关文档

- [QUICKSTART.md](QUICKSTART.md) - 快速开始
- [MODEL-CONFIG-GUIDE.md](MODEL-CONFIG-GUIDE.md) - 配置指南
