# 模型配置指南

## 全局配置

通过 `app/core/config.py` 管理所有模型配置:

```python
class Settings:
    # API 配置
    SILICONFLOW_API_KEY: str
    SILICONFLOW_BASE_URL: str = "https://api.siliconflow.cn/v1"

    # 默认模型
    DEFAULT_MODEL: str = "Qwen/Qwen2.5-Coder-7B-Instruct"

    # 功能特定模型
    VISION_MODEL: str = "Qwen/Qwen2.5-VL"
    NGINX_AI_MODEL: str = "Qwen/Qwen2.5-Coder-7B-Instruct"

    # 生成参数
    MAX_TOKENS: int = 4096
    TEMPERATURE: float = 0.7
    TOP_P: float = 0.9
```

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| SILICONFLOW_API_KEY | - | API Key (必填) |
| SILICONFLOW_BASE_URL | https://api.siliconflow.cn/v1 | API 地址 |
| DEFAULT_MODEL | Qwen2.5-Coder-7B | 默认模型 |
| VISION_MODEL | Qwen2.5-VL | 视觉模型 |
| MAX_TOKENS | 4096 | 最大输出 token |
| TEMPERATURE | 0.7 | 创造性参数 |

## 运行时修改

通过管理 API 动态修改:

```
PUT /api/v2/Controller/admin/config/{key}
{"value": "new-model-name"}
```

## 模型切换

不同功能可配置不同模型:

| 功能 | 环境变量 |
|------|----------|
| 代码生成 | DEFAULT_MODEL |
| 图像分析 | VISION_MODEL |
| Nginx AI | NGINX_AI_MODEL |
| PPT 生成 | DEFAULT_MODEL |
| 虚拟 AI | DEFAULT_MODEL |
