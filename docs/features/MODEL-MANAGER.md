# 免费模型管理接口

> 最后更新：2026-06-02 | 版本：v5.12.0+

## 概述

免费模型管理接口 (`app/api/v1/model_manager.py`) 提供内置免费模型的查看、切换和管理能力，支持超级管理员动态配置默认模型。

## v5.12.0+ 重要更新

### 5×5 模型分配矩阵

v5.12.0+ 引入了**复杂度档 × 角色**的二维模型分配矩阵，取代原有的简单默认模型。详细配置见 `data/agent_model_config.json`，详见 [DYNAMIC-MODEL-ROUTER.md](DYNAMIC-MODEL-ROUTER.md)。

### 模型健康度监控

每个内置模型都有健康度评分（0-100），用于动态路由决策。详见 [DYNAMIC-MODEL-ROUTER.md#1-healthtracker健康度追踪](DYNAMIC-MODEL-ROUTER.md#1-healthtracker健康度追踪)。

### context_length 多级管理

`/api/v2/models/context-length` 端点（superadmin）可管理模型 context_length。详细优先级见 [MODELS.md#context_length-管理](../architecture/MODELS.md#context_length-管理)。

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
      "name": "qwen2.5-7b",
      "model_key": "qwen2.5-7b",
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
  "model_id": "deepseek-r1"
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

共 17 个内置模型。

| 模型 ID | 能力 | 层级 |
|---------|------|------|
| deepseek-r1 | REASONING, CODE | 攻坚层 |
| deepseek-ocr | OCR, VISION | 专用 |
| glm-4.1v-9b | VISION | 专用 |
| qwen3.5-4b | FAST | 简单层 |
| qwen3-8b | REASONING, FAST | 标准层 |
| qwen2.5-7b | CODE, FAST | 标准层 |
| glm-4-9b | FAST, CODE | 标准层 |
| glm-z1-9b | REASONING | 攻坚层 |
| kolors | CREATIVE | 专用 |
| bce-embedding | EMBEDDING | 专用 |
| bge-m3 | EMBEDDING | 专用 |
| bge-large-zh | EMBEDDING | 专用 |
| bge-reranker-v2-m3 | RERANKING | 专用 |
| bce-reranker | RERANKING | 专用 |
| sense-voice | ASR | 专用 |
| telespeech-asr | ASR | 专用 |
| hunyuan-mt | TRANSLATION | 专用 |

## 相关文件

- `app/api/v1/model_manager.py` - API 端点实现
- `app/api/v2/model_admin.py` - **v5.12.0+ 新增**: 模型管理 (context_length, assignments, health)
- `app/utils/aicloud/model_registry.py` - 模型注册表
- `app/agent/dynamic_model_router.py` - **v5.12.0+ 增强**: 动态路由
- `data/agent_model_config.json` - 5×5 模型分配配置
- `tests/unit/test_model_manager_api.py` - 单元测试

## v5.12.0+ 新增端点

### `GET /api/v2/models/context-length`

列出所有模型 context_length 配置。

**权限**: superadmin

**响应**:
```json
{
  "models": {
    "qwen3-8b": {
      "context_length": 131072,
      "source": "user_custom"
    },
    "glm-z1-9b": {
      "context_length": 131072,
      "source": "config_file"
    }
  }
}
```

### `PUT /api/v2/models/context-length`

设置或更新模型 context_length。

**权限**: superadmin

**请求体**:
```json
{
  "model_id": "qwen3-8b",
  "context_length": 131072
}
```

### `GET /api/v2/models/assignments`

查看 5×5 模型分配矩阵。

**权限**: superadmin

**响应**:
```json
{
  "version": "2.0",
  "assignments": {
    "SIMPLE": {
      "architect": "qwen3-8b",
      "frontend": "qwen3-8b",
      "backend": "qwen3-8b",
      "reviewer": "qwen3-8b"
    },
    "MEDIUM": {
      "architect": "glm-z1-9b",
      "frontend": "qwen3-8b",
      "backend": "deepseek-r1",
      "reviewer": "deepseek-r1"
    }
  }
}
```

### `PUT /api/v2/models/assignments`

修改模型分配。

**权限**: superadmin

**请求体**:
```json
{
  "complexity": "MEDIUM",
  "role": "backend",
  "model": "deepseek-r1"
}
```

### `GET /api/v2/models/health`

查看所有模型健康度。

**权限**: superadmin

**响应**:
```json
{
  "models": {
    "qwen3-8b": {
      "score": 95,
      "status": "healthy",
      "circuit_state": "closed",
      "avg_latency_ms": 8500,
      "success_rate": 0.98
    }
  }
}
```

### `POST /api/v2/models/reset-health`

重置指定模型的健康分。

**权限**: superadmin

**请求体**:
```json
{
  "model_id": "qwen3-8b"
}
```
