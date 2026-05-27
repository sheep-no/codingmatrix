# 免费模型管理接口

> 最后更新：2026-05-27 | 版本：v5.10.0

## 概述

免费模型管理接口 (`app/api/v1/model_manager.py`) 提供内置免费模型的查看、切换和管理能力，支持超级管理员动态配置默认模型。

## API 端点

### 获取模型列表

**GET /api/v1/models** - 获取所有可用的免费模型

**权限**: 普通用户

**响应示例**:
```json
{
  "models": [
    {
      "id": "qwen2.5-7b",
      "name": "Qwen2.5-7B-Instruct",
      "model_key": "Qwen/Qwen2.5-7B-Instruct",
      "description": "代码生成与补全",
      "capabilities": ["CODE", "FAST"],
      "tags": ["标准层"],
      "is_default": true
    }
  ],
  "total": 10,
  "default_model": "qwen2.5-7b"
}
```

### 获取当前默认模型

**GET /api/v1/models/default** - 获取当前默认模型信息

**权限**: 普通用户

### 切换默认模型

**POST /api/v1/models/switch** - 切换默认模型

**权限**: 超级管理员

**请求体**:
```json
{
  "model_id": "deepseek-r1-qwen3-8b"
}
```

### 按能力筛选模型

**GET /api/v1/models/capability/{capability}** - 按能力筛选模型

**权限**: 普通用户

**能力类型**:
- `CODE` - 代码生成
- `FAST` - 快速响应
- `REASONING` - 深度推理
- `VISION` - 视觉理解
- `OCR` - 文字识别
- `EMBEDDING` - 文本向量化
- `CREATIVE` - 创意生成

## 内置模型列表

| 模型 ID | 全名 | 能力 | 层级 |
|---------|------|------|------|
| deepseek-r1-qwen3-8b | DeepSeek-R1-0528-Qwen3-8B | REASONING, CODE | 攻坚层 |
| deepseek-ocr | DeepSeek-OCR | OCR, VISION | 专用 |
| paddleocr-vl-1.5 | PaddlePaddle/PaddleOCR-VL-1.5 | VISION | 专用 |
| qwen3.5-4b | Qwen/Qwen3.5-4B | FAST | 简单层 |
| qwen3-8b | Qwen/Qwen3-8B | REASONING, FAST | 标准层 |
| qwen2.5-7b | Qwen/Qwen2.5-7B-Instruct | CODE, FAST | 标准层 |
| glm-4-9b | THUDM/GLM-4-9B-0414 | FAST, CODE | 标准层 |
| glm-z1-9b | THUDM/GLM-Z1-9B-0414 | REASONING | 攻坚层 |
| kolors | Kwai-Kolors/Kolors | CREATIVE | 专用 |
| bce-embedding | netease-youdao/bce-embedding-base_v1 | EMBEDDING | 专用 |

## 相关文件

- `app/api/v1/model_manager.py` - API 端点实现
- `app/utils/aicloud/model_registry.py` - 模型注册表
- `tests/unit/test_model_manager_api.py` - 单元测试
