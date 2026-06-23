# 动态模型路由

> 最后更新：2026-06-22 | 版本：v4.0

动态模型路由是核心子系统之一，负责根据实时健康度、角色需求为 Agent 各组件智能选择最合适的 LLM 模型。

---

## 概述

传统的模型路由是静态的：写死 `TaskType.GENERAL → qwen3-8b` 这样的映射。动态模型路由解决了 3 个核心问题：

1. **健康感知**：模型失败时自动降级到备选
2. **角色专用**：不同 Agent 角色使用不同模型
3. **降级链**：模型不可用时按优先级自动降级

v4.0 移除了基于复杂度的分层路由（SIMPLE/SMALL/MEDIUM/LARGE/XLARGE），改为按角色固定模型分配。复杂度分析仅用于架构决策（`has_frontend`/`has_database` 等），不再影响模型选择。

---

## 架构

```
┌─────────────────────────────────────────────────────────────┐
│ DynamicModelRouter                                           │
│                                                             │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐   │
│  │ HealthTracker│   │ CircuitBreaker│  │ RoleRouter   │   │
│  │ (健康度 0-100)│  │ (熔断器)      │  │ (5 角色固定)  │   │
│  └──────┬───────┘   └──────┬───────┘   └──────┬───────┘   │
│         │                  │                  │            │
│         └──────────────────┼──────────────────┘            │
│                            │                               │
│  ┌─────────────────────────▼─────────────────────────┐    │
│  │ Fallback Chain (降级链)                            │    │
│  │ Nex-N2-Pro → DeepSeek-R1 → GLM-Z1-9B → Qwen3-8B  │    │
│  └─────────────────────────────────────────────────────┘    │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────┴──────────────────────────────────┐
│ Provider Adapters (7 + 动态供应商)                           │
└─────────────────────────────────────────────────────────────┘
```

---

## 核心组件

### 1. HealthTracker（健康度追踪）

为每个模型维护一个 0-100 的健康分：

| 分数范围 | 状态 | 行为 |
|---------|------|------|
| 80-100 | 健康 | 正常路由 |
| 50-79 | 降级 | 优先使用备选 |
| 20-49 | 警告 | 大幅降权，但仍可用 |
| 0-19 | 熔断 | 临时禁用，1 分钟后重试 |

**评分规则**:
- 成功调用: `+1` 分（最高 100）
- 失败调用: `-10` 分
- 超时: `-15` 分
- 连续 3 次失败: 进入熔断状态

### 2. CircuitBreaker（熔断器）

防止持续调用已失败的模型：

```
CLOSED（关闭）→ 正常调用
   ↓ 连续失败 ≥ 3
OPEN（打开）→ 直接拒绝，1 分钟后半开
   ↓
HALF_OPEN（半开）→ 允许 1 次探测调用
   ↓ 成功 → CLOSED
   ↓ 失败 → OPEN
```

### 3. RoleRouter（角色路由）

按角色固定模型分配，不再按复杂度分层：

| 角色 | 模型 | 说明 |
|------|------|------|
| Architect | THUDM/GLM-Z1-9B-0414 | 架构师，使用思考模型 |
| Frontend | deepseek-ai/DeepSeek-R1-0528-Qwen3-8B | 前端工程师 |
| Backend | nex-agi/Nex-N2-Pro | 后端工程师，使用最强模型 |
| Reviewer | THUDM/GLM-Z1-9B-0414 | 审查员，与 backend 不同模型实现交叉审查 |
| Fallback | Qwen/Qwen3-8B | 兜底模型 |

**分配原则**:
1. **Reviewer 与 Backend 不同模型** — 交叉审查，提高质量
2. **Architect 使用思考模型** — 复杂架构需要深度推理
3. **Backend 使用最强模型** — 后端业务复杂
4. **所有项目统一配置** — 不再按复杂度分级

### 4. FallbackChain（降级链）

模型调用失败时按优先级降级：

```
nex-agi/Nex-N2-Pro → deepseek-ai/DeepSeek-R1-0528-Qwen3-8B → THUDM/GLM-Z1-9B-0414 → Qwen/Qwen3-8B
```

降级链可在 `data/agent_model_config.json` 的 `fallback_chain` 字段配置。

### 用户降级偏好 (fallback_preference)

每个用户 API Key 可设置独立的降级策略:

| 值 | 说明 |
|----|------|
| use_admin_default | 使用管理员配置的降级链（默认） |
| custom | 使用用户自定义的 `custom_fallback_chain` |
| disabled | 禁用降级，仅使用用户自己的模型 |

API: `PUT /api/v1/apikey/{token}/fallback-preference`

---

## 配置

### 配置文件

`data/agent_model_config.json` (v4.0):
```json
{
  "version": "4.0",
  "description": "Agent 模型配置 v4.0",
  "models": {
    "THUDM/GLM-Z1-9B-0414": {
      "name": "glm-z1-9b-0414",
      "display_name": "GLM-Z1-9B-0414",
      "provider": "siliconflow",
      "is_reasoning": true,
      "context_length": 131072,
      "max_tokens": 8192,
      "thinking_budget": 4096,
      "thinking_ratio": 0.5,
      "temperature": 0.7,
      "timeout": 120,
      "speed": "medium"
    },
    "deepseek-ai/DeepSeek-R1-0528-Qwen3-8B": {
      "name": "deepseek-r1-0528-qwen3-8b",
      "display_name": "DeepSeek-R1-0528-Qwen3-8B",
      "provider": "siliconflow",
      "is_reasoning": true,
      "context_length": 131072,
      "max_tokens": 8192,
      "thinking_budget": 4096,
      "thinking_ratio": 0.5,
      "temperature": 0.7,
      "timeout": 120,
      "speed": "medium"
    },
    "nex-agi/Nex-N2-Pro": {
      "name": "nex-n2-pro",
      "display_name": "Nex-N2-Pro",
      "provider": "siliconflow",
      "is_reasoning": true,
      "context_length": 131072,
      "max_tokens": 16384,
      "thinking_budget": 8192,
      "thinking_ratio": 0.5,
      "temperature": 0.7,
      "timeout": 180,
      "speed": "slow"
    },
    "Qwen/Qwen3-8B": {
      "name": "qwen3-8b",
      "display_name": "Qwen3-8B",
      "provider": "siliconflow",
      "is_reasoning": false,
      "context_length": 131072,
      "max_tokens": 8192,
      "temperature": 0.7,
      "timeout": 60,
      "speed": "fast"
    }
  },
  "roles": {
    "architect": "THUDM/GLM-Z1-9B-0414",
    "frontend": "deepseek-ai/DeepSeek-R1-0528-Qwen3-8B",
    "backend": "nex-agi/Nex-N2-Pro",
    "reviewer": "THUDM/GLM-Z1-9B-0414",
    "fallback": "Qwen/Qwen3-8B"
  },
  "fallback_chain": [
    "nex-agi/Nex-N2-Pro",
    "deepseek-ai/DeepSeek-R1-0528-Qwen3-8B",
    "THUDM/GLM-Z1-9B-0414",
    "Qwen/Qwen3-8B"
  ],
  "error_type_models": {
    "validation_error": "Qwen/Qwen3-8B",
    "timeout_error": "THUDM/GLM-Z1-9B-0414",
    "api_error": "deepseek-ai/DeepSeek-R1-0528-Qwen3-8B",
    "code_error": "nex-agi/Nex-N2-Pro",
    "logic_error": "THUDM/GLM-Z1-9B-0414"
  },
  "settings": {
    "max_concurrent_requests": 10,
    "circuit_breaker_threshold": 3,
    "circuit_breaker_cooldown_seconds": 60
  },
  "cross_validation": {
    "enabled": true,
    "auto_priority_1": true,
    "critical_patterns": [
      "security",
      "database_migration",
      "payment"
    ]
  }
}
```

### API 端点

- `GET /api/v1/models/agent-config` - 查看当前角色模型分配
- `PUT /api/v2/models/agent-config` - 修改角色模型分配（superadmin）
- `PUT /api/v2/models/agent-config/fallback-chain` - 修改降级链（superadmin）
- `PUT /api/v2/models/agent-config/error-type-model` - 修改错误类型模型映射（superadmin）
- `POST /api/v2/models/agent-config/reload` - 重新加载配置（superadmin）
- `GET /api/v2/models/health` - 查看模型健康度
- `POST /api/v2/models/reset-health` - 重置健康分

---

## Fallback 链

模型调用失败时的降级顺序：

### 默认降级链

```
nex-agi/Nex-N2-Pro → deepseek-ai/DeepSeek-R1-0528-Qwen3-8B → THUDM/GLM-Z1-9B-0414 → Qwen/Qwen3-8B
```

从最强模型开始，逐步降级到兜底模型。可在配置文件的 `fallback_chain` 字段自定义。

---

## 交叉验证 (cross_validation)

v4.0 引入自动交叉验证机制：当任务涉及关键模式（如安全、数据库迁移、支付）时，系统自动使用不同模型进行独立审查，降低单模型盲区风险。

### 配置

```json
{
  "cross_validation": {
    "enabled": true,
    "auto_priority_1": true,
    "critical_patterns": [
      "security",
      "database_migration",
      "payment"
    ]
  }
}
```

| 字段 | 说明 |
|------|------|
| `enabled` | 是否启用交叉验证 |
| `auto_priority_1` | 自动将匹配 `critical_patterns` 的任务提升为 Priority 1 |
| `critical_patterns` | 触发交叉验证的关键模式列表 |

当 `enabled=true` 且任务匹配 `critical_patterns` 时，Reviewer 会使用与 Backend 不同的模型独立执行代码审查，两份审查结果合并后输出。

---

## 性能指标

v5.12.0+ 路由改造后的实测效果：

| 指标 | 优化前 | 优化后 | 提升 |
|------|--------|--------|------|
| 模型调用失败率 | 8% | 2% | 75% |
| 平均响应延迟 | 12s | 9s | 25% |
| TPM 利用率 | 60% | 85% | 42% |
| 任务失败自动恢复率 | 30% | 75% | 150% |

---

## 监控

### Health Score API

```bash
curl http://localhost:8000/api/v2/models/health
```

返回：
```json
{
  "models": {
    "qwen3-8b": {
      "score": 95,
      "status": "healthy",
      "success_rate": 0.98,
      "avg_latency_ms": 8500,
      "circuit_state": "closed"
    },
    "deepseek-r1": {
      "score": 100,
      "status": "healthy",
      "success_rate": 0.99,
      "avg_latency_ms": 18000,
      "circuit_state": "closed"
    }
  }
}
```

### Prometheus 指标

- `model_call_total{model, role, status}` - 调用总数
- `model_call_duration_seconds{model, role}` - 响应时长
- `model_circuit_state{model}` - 熔断器状态（0=closed, 1=half_open, 2=open）
- `model_health_score{model}` - 健康分

---

## 与其他子系统的协作

### 与 Session Lifecycle 协作

- 健康度过低的模型会让会话超时
- 熔断状态会反映在会话错误信息中
- 429 响应时会记录到模型统计

### 与 ReAct Tool Calling 协作

- ReAct 不同阶段可以使用不同模型
- 思考阶段可用 qwen3-8b（快速）
- 最终生成阶段用对应角色模型

### 与 Code Sandbox 协作

- 沙箱执行超时会降低模型的健康分
- 多次沙箱失败会触发模型熔断

---

## 实现细节

**文件**: `app/agent/dynamic_model_router.py`

### 关键方法

| 方法 | 描述 |
|------|------|
| `get_assignment(role)` | 获取角色模型分配（无复杂度参数） |
| `get_assignment_with_learning(role)` | 获取分配 + epsilon-greedy 学习（无复杂度参数） |
| `record_call_result(model, success, latency)` | 记录调用结果 |
| `is_healthy(model)` | 检查模型是否健康 |
| `get_fallback(primary_model)` | 获取降级模型 |
| `reset_health(model)` | 重置健康分 |
| `_load_roles_assignment()` | 从配置文件加载角色分配 |
| `reload_roles_config()` | 重新加载角色配置 |

### 缓存策略

- 配置变更时 `_config_loaded = False` 触发重新加载
- LRU 缓存大小: 100
- 缓存命中率: ~95%

---

## 故障排查

### 模型失败率突然升高

1. 检查 `/api/v2/models/health` 看哪个模型分数低
2. 查看熔断器状态
3. 检查 SiliconFlow 供应商状态页
4. 必要时手动 `reset_health`

### 路由分配不符合预期

1. 查看 `data/agent_model_config.json` 当前配置
2. 确认 `roles` 字段中各角色的模型是否正确
3. 通过 admin UI 修改分配

### 跨模型名称不一致

代码中有 `MODEL_ID_TO_KEY` 映射，处理：
- `qwen3.5-4b` → `Qwen/Qwen3.5-4B`
- `qwen3-8b` → `Qwen/Qwen3-8B`
- 等

如发现新模型未映射，需要同步到 `MODEL_ID_TO_KEY` 字典。

---

## 相关文档

- [Agent 系统](AGENT.md)
- [模型系统](../architecture/MODELS.md)
- [ReAct 工具调用](REACT-TOOL-CALLING.md)
- [分布式追踪](../observability/TRACING.md)
