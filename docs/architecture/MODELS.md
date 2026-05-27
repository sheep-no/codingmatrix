# 数据模型与 LLM 适配器

最后更新: 2026-05-27

---

## 一、SQLAlchemy 数据模型

### 模型列表

| 模型 | 文件 | 表名 | 描述 |
|------|------|------|------|
| User | `user.py` | users | 用户信息 |
| History | `history.py` | histories | 聊天/代码历史 |
| File | `file.py` | files | 上传文件元数据 |
| Task | `task.py` | tasks | 异步任务 |
| SavedProject | `saved_project.py` | saved_projects | 已保存项目 |
| AgentMemory | `agent_memory.py` | agent_memories | Agent 记忆 |
| AicloudSession | `aicloud.py` | aicloud_sessions | AI 云会话 |
| AicloudKnowledge | `aicloud_knowledge.py` | aicloud_knowledge | 知识库文档 |
| ServerConfig | `server_config.py` | server_config | 系统配置 |
| ChatHistory | `chat_history.py` | chat_histories | 对话历史 |
| Permission | `Permission.py` | (常量) | 权限定义 |

### User

| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer (PK) | 用户 ID |
| username | String | 用户名 (唯一) |
| email | String | 邮箱 (唯一) |
| hashed_password | String | bcrypt 密码 |
| permission_level | Integer | 权限级别 (0/1/2) |
| created_at | DateTime | 创建时间 |
| updated_at | DateTime | 更新时间 |

### History

| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer (PK) | 历史 ID |
| user_id | Integer (FK) | 用户 ID |
| type | String | 类型 (code/chat) |
| content | Text | 内容 |
| created_at | DateTime | 创建时间 |

### Task

| 字段 | 类型 | 说明 |
|------|------|------|
| id | String (PK) | 任务 UUID |
| user_id | Integer (FK) | 用户 ID |
| type | String | 任务类型 |
| status | String | 状态 |
| result | JSON | 结果数据 |
| created_at | DateTime | 创建时间 |
| completed_at | DateTime | 完成时间 |

### SavedProject

| 字段 | 类型 | 说明 |
|------|------|------|
| id | String (PK) | 项目 UUID |
| user_id | Integer (FK) | 用户 ID |
| name | String | 项目名称 |
| files | JSON | 文件树 |
| session_id | String | 会话 ID (预留多会话) |
| created_at | DateTime | 创建时间 |

### ServerConfig

| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer (PK) | 配置 ID |
| key | String | 配置键 (唯一) |
| value | Text | 配置值 |
| description | String | 描述 |
| updated_by | Integer | 修改人 |
| created_at | DateTime | 创建时间 |
| updated_at | DateTime | 更新时间 |

---

## 二、LLM 模型适配器

### 概述

CodingMatrix 通过统一适配器接口调用多种 LLM 模型，实现三层路由策略按任务复杂度自动分派。

### 支持的模型 (ALLOWED_MODELS)

**最后更新**: 2026-05-22 | **版本**: v5.3.1

| 模型 ID | 提供商 | 用途 | 说明 |
|---------|--------|------|------|
| deepseek-ai/DeepSeek-R1-0528-Qwen3-8B | DeepSeek | 攻坚层推理 | 深度推理与复杂分析 |
| deepseek-ai/DeepSeek-OCR | DeepSeek | OCR | 图像文字识别 |
| Qwen/Qwen3.5-4B | Alibaba | 简单层对话 | 轻量快速响应 |
| Qwen/Qwen3-8B | Alibaba | 标准层对话 | 通用代码与对话 |
| Qwen/Qwen2.5-7B-Instruct | Alibaba | 标准层代码 | 代码生成与补全 |
| THUDM/GLM-4.1V-9B-Thinking | THUDM | 视觉推理 | 图像分析 + 推理链 |
| THUDM/GLM-4-9B-0414 | THUDM | 标准层对话 | 通用对话与协作 |
| THUDM/GLM-Z1-9B-0414 | THUDM | 攻坚层推理 | 深度推理与验证 |
| Kwai-Kolors/Kolors | Kuaishou | 图像生成 | 文生图 |
| netease-youdao/bce-embedding-base_v1 | NetEase | 嵌入/相似度 | 文本向量化 |

**共 10 个内置模型**（不包括用户在前端调用 API Key 的自付费模型）

### 三层路由策略

| 层级 | 模型 | 适用场景 |
|------|------|----------|
| 简单层 | Qwen/Qwen3.5-4B | 快速问答、格式化、简单改写 |
| 标准层 | Qwen/Qwen2.5-7B-Instruct, THUDM/GLM-4-9B-0414 | 代码生成、通用对话、常规开发任务 |
| 攻坚层 | deepseek-ai/DeepSeek-R1-0528-Qwen3-8B, THUDM/GLM-Z1-9B-0414 | 深度推理、复杂 bug 分析、架构设计 |

### 配置

全局配置通过 `app/core/config.py` 管理：

```python
class Settings:
 SILICONFLOW_API_KEY: str
 SILICONFLOW_BASE_URL: str = "https://api.siliconflow.cn/v1"

 DEFAULT_MODEL: str = "Qwen/Qwen2.5-7B-Instruct"
 VISION_MODEL: str = "THUDM/GLM-4.1V-9B-Thinking"
 OCR_MODEL: str = "deepseek-ai/DeepSeek-OCR"
 IMAGE_GEN_MODEL: str = "Kwai-Kolors/Kolors"

 MAX_TOKENS: int = 4096
 TEMPERATURE: float = 0.7
 TOP_P: float = 0.9
```

环境变量：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| SILICONFLOW_API_KEY | - | API Key (必填) |
| SILICONFLOW_BASE_URL | https://api.siliconflow.cn/v1 | API 地址 |
| DEFAULT_MODEL | Qwen/Qwen2.5-7B-Instruct | 默认模型 |
| VISION_MODEL | THUDM/GLM-4.1V-9B-Thinking | 视觉模型 |
| OCR_MODEL | deepseek-ai/DeepSeek-OCR | OCR 模型 |
| IMAGE_GEN_MODEL | Kwai-Kolors/Kolors | 图像生成模型 |
| MAX_TOKENS | 4096 | 最大输出 token |
| TEMPERATURE | 0.7 | 创造性参数 |

运行时可通过管理 API 动态修改：

```
PUT /api/v2/Controller/admin/config/{key}
{"value": "new-model-name"}
```

### 快速开始

1. 在 [SiliconFlow](https://siliconflow.cn) 注册并获取 API Key
2. 设置环境变量：

```bash
export SILICONFLOW_API_KEY=your-api-key
```

3. 使用模型：

```python
from app.utils.AiCodeUtil import call_siliconflow

result = await call_siliconflow(
 prompt="写一个快速排序",
 model="Qwen/Qwen2.5-7B-Instruct"
)

async for chunk in await call_siliconflow(
 prompt="写一个快速排序",
 model="Qwen/Qwen2.5-7B-Instruct",
 stream=True
):
 print(chunk)
```

4. 验证：

```bash
python -m uvicorn app.main:app --reload
curl http://localhost:8000/api/v1/health/models
```

### 功能-模型映射

| 功能 | 环境变量 | 默认模型 |
|------|----------|----------|
| 代码生成 | DEFAULT_MODEL | Qwen/Qwen2.5-7B-Instruct |
| 图像分析 | VISION_MODEL | THUDM/GLM-4.1V-9B-Thinking |
| OCR | OCR_MODEL | deepseek-ai/DeepSeek-OCR |
| 图像生成 | IMAGE_GEN_MODEL | Kwai-Kolors/Kolors |
| PPT 生成 | DEFAULT_MODEL | Qwen/Qwen2.5-7B-Instruct |

---

## 三、多供应商架构 (v5.4.0+)

### 概述

从 v5.4.0 开始，CodingMatrix 支持多个 LLM API 供应商，通过统一的调用接口自动路由到对应供应商，并支持故障转移。

### 支持的供应商

| 供应商 | 枚举值 | Base URL | 说明 |
|--------|--------|----------|------|
| SiliconFlow | `siliconflow` | https://api.siliconflow.cn/v1 | 默认供应商，支持所有 10 个内置模型 |
| 阿里百炼 | `dashscope` | https://dashscope.aliyuncs.com/compatible-mode/v1 | 支持 Qwen 系列 |
| 智谱 GLM | `zhipu` | https://open.bigmodel.cn/api/paas/v4 | 支持 GLM 系列 |
| DeepSeek 官方 | `deepseek` | https://api.deepseek.com/v1 | DeepSeek 官方 API |
| OpenAI | `openai` | https://api.openai.com/v1 | OpenAI API |
| Anthropic | `anthropic` | https://api.anthropic.com/v1 | Claude 系列 |
| Ollama | `ollama` | http://localhost:11434 | 本地部署模型 |

### 核心组件

```
app/utils/aicloud/
├── providers.py        # ModelProvider 枚举、ProviderConfig、ProviderRegistry
├── provider_router.py  # ProviderRouter 模型路由和故障转移
├── llm_caller.py      # call_llm() 统一调用入口
├── adapters/
│   ├── base.py         # BaseProviderAdapter 抽象基类
│   ├── siliconflow.py  # SiliconFlow 适配器
│   ├── dashscope.py    # 阿里百炼适配器
│   ├── zhipu.py        # 智谱 GLM 适配器
│   └── openai.py       # OpenAI 适配器
└── test_providers.py   # 单元测试
```

### 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| SILICONFLOW_API_KEY | - | SiliconFlow API Key |
| DASHSCOPE_API_KEY | - | 阿里百炼 API Key |
| ZHIPU_API_KEY | - | 智谱 API Key |
| DEEPSEEK_API_KEY | - | DeepSeek 官方 API Key |
| OPENAI_API_KEY | - | OpenAI API Key |
| ANTHROPIC_API_KEY | - | Anthropic API Key |
| OLLAMA_BASE_URL | http://localhost:11434 | Ollama 本地服务地址 |

### 统一调用接口

```python
# 新方式：统一调用（推荐）
from app.utils.aicloud import call_llm

result = await call_llm(
    model="Qwen/Qwen3.5-4B",
    prompt="你好",
    system_prompt="你是助手",
    temperature=0.7,
    max_tokens=4096,
)

# 向后兼容：SiliconFlow 专用
from app.utils.AiCodeUtil import call_siliconflow

result = await call_siliconflow(
    prompt="你好",
    model="Qwen/Qwen3.5-4B",
)
```

### 故障转移策略

| 主供应商 | 故障转移顺序 |
|---------|-------------|
| SiliconFlow | 阿里百炼 → 智谱 |
| 阿里百炼 | SiliconFlow |
| 智谱 | SiliconFlow |
| DeepSeek | SiliconFlow |
| OpenAI | SiliconFlow |
| Ollama | 无（本地部署） |

### 模型路由规则

```python
# 完整模型名称（如 deepseek-ai/DeepSeek-R1-0528-Qwen3-8B）→ SiliconFlow
# 简短名称（如 qwen-plus、glm-4、deepseek-chat）→ 对应供应商
# 未知模型 → SiliconFlow (默认)
```