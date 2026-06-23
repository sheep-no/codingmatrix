# 数据模型与 LLM 适配器

最后更新: 2026-06-06 | 版本：v5.14.0 | 测试基线：1622 passed / 0 failed | Agent 模块：76

---

## v5.13.0+ 关键更新

### LLM 调用路径统一

所有文本 LLM 调用统一走 `call_llm()`，vision（多模态）也走 `call_llm(messages=...)`。

**调用链路**：
```
call_llm() → 4 级优先级路由 → ProviderRouter.route() → Adapter 缓存 → Fallback 链
```

**4 级优先级**：
1. 直接指定动态供应商（`provider_id` 参数）
2. 用户 API Key Token（Redis 取 Key → `ProviderRouter.route()` → 创建 Adapter）
3. 动态供应商中查找该模型（`get_by_model`）
4. 系统默认路由（`ProviderRouter.route()` → fallback 链）

### 供应商感知降级链

`ErrorRecoveryLoop` 根据用户 Key 所属供应商自动选择同供应商的降级链：

| 用户供应商 | 降级链 |
|-----------|--------|
| siliconflow（默认） | Qwen3-8B → DeepSeek-R1-8B → Qwen3.5-4B |
| dashscope | qwen-plus → qwen-turbo |
| zhipu | glm-4 → glm-4 |
| deepseek | deepseek-chat → deepseek-reasoner |
| openai | gpt-4o → gpt-4o-mini |
| anthropic | claude-sonnet-4-20250514 → claude-3-5-haiku-20241022 |

### 多模态 call_llm 兼容

`call_llm` + 所有 Adapter 新增 `messages: Optional[list] = None` 参数：
- 传入时跳过 `prompt`→`messages` 构建，直接使用原始消息列表
- 对现有 text-only 调用方完全透明
- `vision.py._call_vision_model` 重写为 `call_llm(messages=...)`，删除 30 行手动 HTTP/Key 逻辑

---

## v5.12.0+ 关键更新

### 5 复杂度档 × 5 角色模型分配 v4.0

v4.0 更新了模型分配，移除复杂度分层，改为按角色固定模型分配：

**当前分配**（`data/agent_model_config.json`）：

| 角色 | 模型 ID | API 名称 |
|------|---------|----------|
| 架构师 | glm-z1-9b | THUDM/GLM-Z1-9B-0414 |
| 前端工程师 | deepseek-r1 | deepseek-ai/DeepSeek-R1-0528-Qwen3-8B |
| 后端工程师 | nex-n2-pro | nex-agi/Nex-N2-Pro |
| 代码审查 | glm-z1-9b | THUDM/GLM-Z1-9B-0414 |
| 兜底模型 | qwen3-8b | Qwen/Qwen3-8B |

**降级链**: DeepSeek-R1 → GLM-Z1-9B → GLM-4-9B → Qwen3-8B

> 注：所有模型均为免费模型，通过 SiliconFlow 供应商调用。用户可通过 API Key 替换为自定义模型。

详见 [DYNAMIC-MODEL-ROUTER.md](../features/DYNAMIC-MODEL-ROUTER.md)

### 模型健康度评分 (v5.12.0+ 新增)

每个模型维护一个 0-100 的健康分：

| 分数范围 | 状态 | 行为 |
|---------|------|------|
| 80-100 | 健康 | 正常路由 |
| 50-79 | 降级 | 优先使用备选 |
| 20-49 | 警告 | 大幅降权 |
| 0-19 | 熔断 | 临时禁用 |

**熔断器**: 连续 3 次失败 → OPEN（拒绝），1 分钟后 HALF_OPEN（探测），成功 → CLOSED（正常）。

详见 [DYNAMIC-MODEL-ROUTER.md#健康度追踪](../features/DYNAMIC-MODEL-ROUTER.md#1-healthtracker健康度追踪)

### ReAct 阶段化模型 (v5.12.0+ 新增)

ReAct 工具调用循环的不同阶段可用不同模型：

| 阶段 | 推荐模型 | 理由 |
|------|---------|------|
| 思考 | qwen3-8b | 快速理解 |
| 行动 | qwen3-8b | 简单工具调用 |
| 观察 | qwen3-8b | 简单分析 |
| 最终生成 | deepseek-r1 或对应角色模型 | 高质量输出 |

详见 [REACT-TOOL-CALLING.md#阶段化模型路由](../features/REACT-TOOL-CALLING.md#阶段化模型路由)

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

### 支持的模型

**最后更新**: 2026-06-01

| 模型 ID | 提供商 | 用途 | 上下文长度 |
|---------|--------|------|-----------|
| deepseek-ai/DeepSeek-R1-0528-Qwen3-8B | DeepSeek | 攻坚层推理 | 128k |
| THUDM/GLM-Z1-9B-0414 | THUDM | 攻坚层推理 | 128k |
| Qwen/Qwen3.5-4B | Alibaba | 简单层对话 | 256k |
| Qwen/Qwen3-8B | Alibaba | 标准层对话 | 128k |
| Qwen/Qwen2.5-7B-Instruct | Alibaba | 标准层代码 | 32k |
| THUDM/GLM-4-9B-0414 | THUDM | 标准层对话 | 32k |
| deepseek-ai/DeepSeek-OCR | DeepSeek | OCR | 8k |
| BAAI/bge-m3 | BAAI | 嵌入 | 8k |
| BAAI/bge-reranker-v2-m3 | BAAI | 重排序 | 8k |
| netease-youdao/bce-embedding-base_v1 | NetEase | 嵌入 | 0.5k |
| netease-youdao/bce-reranker-base_v1 | NetEase | 重排序 | 0.5k |
| nex-agi/Nex-N2-Pro | Nex AGI | 推理 | 262k |

### context_length 管理

系统通过多级优先级获取模型的上下文长度：

1. **用户自定义配置**：用户在 API Key 管理页面为自己的 Key 设置的 context_length
2. **配置文件**：`data/agent_model_config.json` 中的 `model_context_lengths`
3. **代码映射**：`dynamic_model_router.py` 中的 `MODEL_CONTEXT_LENGTHS`
4. **动态供应商**：从 `/v1/models` API 响应中提取
5. **自定义供应商**：用户提交 Key 时自动同步
6. **默认值**：32768 tokens

### 三层路由策略

| 层级 | 路由器 | 职责 |
|------|--------|------|
| Layer 1 | FileModelRouter | 读取 `agent_model_config.json`，按文件类型路由 |
| Layer 2 | DynamicModelRouter | 熔断器、健康度追踪、降级链 |
| Layer 3 | LearningRouter | 基于历史性能自适应选择 |

### 配置

全局配置通过 `app/core/config.py` 管理：

```python
class Settings:
 SILICONFLOW_API_KEY: str
 SILICONFLOW_BASE_URL: str = "https://api.siliconflow.cn/v1"

 DEFAULT_MODEL: str = "qwen2.5-7b"
 VISION_MODEL: str = "deepseek-ocr"
  OCR_MODEL: str = "deepseek-ocr"
 IMAGE_GEN_MODEL: str = "kolors"

 MAX_TOKENS: int = 4096
 TEMPERATURE: float = 0.7
 TOP_P: float = 0.9
```

环境变量：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| SILICONFLOW_API_KEY | - | API Key (必填) |
| SILICONFLOW_BASE_URL | https://api.siliconflow.cn/v1 | API 地址 |
| DEFAULT_MODEL | qwen2.5-7b | 默认模型 |
| VISION_MODEL | deepseek-ocr | 视觉模型 |
| OCR_MODEL | deepseek-ocr | OCR 模型 |
| IMAGE_GEN_MODEL | kolors | 图像生成模型 |
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
from app.utils.aicloud.llm_caller import call_llm

result = await call_llm(
    model="Qwen/Qwen3-8B",
    messages=[{"role": "user", "content": "Hello"}],
    temperature=0.7
)
```

4. 验证：

```bash
python -m uvicorn app.main:app --reload
curl http://localhost:8000/api/v1/health/models
```

### 功能-模型映射

| 功能 | 环境变量 | 默认模型 |
|------|----------|----------|
| 代码生成 | DEFAULT_MODEL | qwen2.5-7b |
| 图像分析 | VISION_MODEL | deepseek-ocr |
| 视觉理解 | - | glm-4.1v-9b |
| OCR | OCR_MODEL | deepseek-ocr |
| 图像生成 | IMAGE_GEN_MODEL | kolors |
| PPT 生成 | DEFAULT_MODEL | qwen2.5-7b |

---

## 三、多供应商架构 (v5.4.0+)

### 概述

从 v5.4.0 开始，CodingMatrix 支持多个 LLM API 供应商，通过统一的调用接口自动路由到对应供应商，并支持故障转移。

### 支持的供应商

| 供应商 | 枚举值 | Base URL | 说明 |
|--------|--------|----------|------|
| SiliconFlow | `siliconflow` | https://api.siliconflow.cn/v1 | 默认供应商，支持所有 17 个内置模型 |
| 阿里百炼 | `dashscope` | https://dashscope.aliyuncs.com/compatible-mode/v1 | 支持 Qwen 系列 |
| 智谱 GLM | `zhipu` | https://open.bigmodel.cn/api/paas/v4 | 支持 GLM 系列 |
| DeepSeek 官方 | `deepseek` | https://api.deepseek.com/v1 | DeepSeek 官方 API |
| OpenAI | `openai` | https://api.openai.com/v1 | OpenAI API |
| Anthropic | `anthropic` | https://api.anthropic.com/v1 | Claude 系列 |
| Ollama | `ollama` | http://localhost:11434 | 本地部署模型 |

### 动态供应商支持 (v5.10.0+)

除内置供应商外，支持用户通过 base_url 自定义供应商：

| 参数 | 说明 | 示例 |
|------|------|------|
| `name` | 供应商名称 | MyCustomAPI |
| `base_url` | API 端点地址 | https://api.example.com/v1 |
| `protocol` | 协议类型 | `openai` / `anthropic` |
| `api_key` | 认证密钥 | sk-... |

**支持的协议类型**：
- `openai`: OpenAI 兼容格式 (`/v1/chat/completions`)
- `anthropic`: Anthropic 原生格式 (`/v1/messages`)

**动态供应商调用**：

```python
from app.utils.aicloud.dynamic_provider import get_dynamic_provider_manager
from app.utils.aicloud.llm_caller import call_dynamic_llm

# 添加自定义供应商
manager = get_dynamic_provider_manager()
provider = manager.add(
    name="My API",
    base_url="https://api.example.com/v1",
    protocol="openai",  # 或 "anthropic"
    api_key="sk-xxx"
)

# 调用
result = await call_dynamic_llm(
    provider_id=provider.id,
    model="gpt-4",
    prompt="你好"
)
```

### 核心组件

```
app/utils/aicloud/
├── providers.py            # ModelProvider 枚举、ProviderConfig
├── provider_router.py      # ProviderRouter 模型路由
├── llm_caller.py          # call_llm() 统一调用入口
├── dynamic_provider.py     # 动态供应商管理
├── adapters/
│   ├── base.py            # BaseProviderAdapter 基类
│   ├── siliconflow.py     # SiliconFlow 适配器
│   ├── dashscope.py       # 阿里百炼适配器
│   ├── zhipu.py           # 智谱 GLM 适配器
│   ├── openai.py          # OpenAI 适配器
│   ├── anthropic.py       # Anthropic 适配器
│   ├── deepseek.py        # DeepSeek 适配器
│   └── dynamic.py         # 动态供应商适配器
└── test_providers.py      # 单元测试
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
    model="qwen3.5-4b",
    prompt="你好",
    system_prompt="你是助手",
    temperature=0.7,
    max_tokens=4096,
)

# 向后兼容：SiliconFlow 专用
from app.utils.AiCodeUtil import call_siliconflow

result = await call_siliconflow(
    prompt="你好",
    model="qwen3.5-4b",
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
# 完整模型名称（如 deepseek-r1）→ SiliconFlow
# 简短名称（如 qwen-plus、glm-4、deepseek-chat）→ 对应供应商
# 未知模型 → SiliconFlow (默认)
```