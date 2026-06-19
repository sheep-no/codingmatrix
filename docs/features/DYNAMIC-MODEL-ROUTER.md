# 动态模型路由

> 最后更新：2026-06-10 | 版本：v3.0

动态模型路由是核心子系统之一，负责根据实时健康度、角色需求为 Agent 各组件智能选择最合适的 LLM 模型。

---

## 概述

传统的模型路由是静态的：写死 `TaskType.GENERAL → qwen3-8b` 这样的映射。动态模型路由解决了 3 个核心问题：

1. **健康感知**：模型失败时自动降级到备选
2. **角色专用**：不同 Agent 角色使用不同模型
3. **降级链**：模型不可用时按优先级自动降级

v3.0 移除了基于复杂度的分层路由（SIMPLE/SMALL/MEDIUM/LARGE/XLARGE），改为按角色固定模型分配。复杂度分析仅用于架构决策（`has_frontend`/`has_database` 等），不再影响模型选择。

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
│  │ deepseek-r1 → glm-z1-9b → glm-4-9b → qwen3-8b    │    │
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
| Architect | glm-z1-9b | 架构师，使用思考模型 |
| Frontend | glm-4-9b | 前端工程师 |
| Backend | deepseek-r1 | 后端工程师，使用最强模型 |
| Reviewer | glm-z1-9b | 审查员，与 backend 不同模型实现交叉审查 |
| Fallback | qwen3-8b | 兜底模型 |

**分配原则**:
1. **Reviewer 与 Backend 不同模型** — 交叉审查，提高质量
2. **Architect 使用思考模型** — 复杂架构需要深度推理
3. **Backend 使用最强模型** — 后端业务复杂
4. **所有项目统一配置** — 不再按复杂度分级

### 4. FallbackChain（降级链）

模型调用失败时按优先级降级：

```
deepseek-r1 → glm-z1-9b → glm-4-9b → qwen3-8b
```

降级链可在 `data/agent_model_config.json` 的 `fallback_chain` 字段配置。

---

## 配置

### 配置文件

`data/agent_model_config.json` (v3.0):
```json
{
  "version": "3.0",
  "description": "Agent 模型配置 v3.0",
  "roles": {
    "architect": "glm-z1-9b",
    "frontend": "glm-4-9b",
    "backend": "deepseek-r1",
    "reviewer": "glm-z1-9b",
    "fallback": "qwen3-8b"
  },
  "fallback_chain": [
    "deepseek-r1",
    "glm-z1-9b",
    "glm-4-9b",
    "qwen3-8b"
  ],
  "error_type_models": {
    "validation_error": "qwen3-8b",
    "timeout_error": "glm-4-9b",
    "api_error": "glm-z1-9b",
    "code_error": "deepseek-r1",
    "logic_error": "glm-z1-9b"
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
deepseek-r1 → glm-z1-9b → glm-4-9b → qwen3-8b
```

从最强模型开始，逐步降级到兜底模型。可在配置文件的 `fallback_chain` 字段自定义。

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
