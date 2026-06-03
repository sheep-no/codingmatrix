# 动态模型路由

> 最后更新：2026-06-02 | 版本：v5.12.0+

动态模型路由是 v5.12.0+ 的核心子系统之一，负责根据实时健康度、复杂度等级、角色需求为 Agent 各组件智能选择最合适的 LLM 模型。

---

## 概述

传统的模型路由是静态的：写死 `TaskType.GENERAL → qwen3-8b` 这样的映射。v5.12.0+ 引入的动态模型路由解决了 3 个核心问题：

1. **健康感知**：模型失败时自动降级到备选
2. **复杂度分层**：简单任务用小模型，复杂任务用大模型
3. **角色专用**：不同 Agent 角色使用不同模型

---

## 架构

```
┌─────────────────────────────────────────────────────────────┐
│ DynamicModelRouter                                           │
│                                                             │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐   │
│  │ HealthTracker│   │ CircuitBreaker│  │ LayeredRouter│   │
│  │ (健康度 0-100)│  │ (熔断器)      │  │ (5 档 × 5 角色)│  │
│  └──────┬───────┘   └──────┬───────┘   └──────┬───────┘   │
│         │                  │                  │            │
│         └──────────────────┼──────────────────┘            │
│                            │                               │
│  ┌─────────────────────────▼─────────────────────────┐    │
│  │ ModelAssignmentCache (LRU 缓存)                    │    │
│  │ 缓存: complexity_level × role → model_id            │    │
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

### 3. LayeredRouter（分层路由）

5 复杂度档 × 5 角色模型的二维矩阵：

| 复杂度 | Architect | Frontend | Backend | Reviewer | Complexity |
|--------|-----------|----------|---------|----------|------------|
| SIMPLE | qwen3.5-4b | qwen3-8b | qwen3-8b | qwen3-8b | 关键词匹配 |
| SMALL | glm-z1-9b | qwen3-8b | deepseek-r1 | deepseek-r1 | 关键词匹配 |
| MEDIUM | glm-z1-9b | qwen3-8b | deepseek-r1 | deepseek-r1 | LLM 校准 |
| LARGE | glm-z1-9b | qwen3-8b | deepseek-r1 | deepseek-r1 | LLM 校准 |
| XLARGE | glm-z1-9b | qwen3-8b | deepseek-r1 | deepseek-r1 | LLM 校准 |

> **注意**：因 SiliconFlow Qwen3.5-4B 暂时不可用，SIMPLE 架构师临时改为 qwen3-8b（见 `data/agent_model_config.json`）。

**分配原则**:
1. **Reviewer ≥ Generator** — 审查员模型能力不低于生成员
2. **Backend > Frontend** — 后端业务复杂，用更强模型
3. **Architect 使用思考模型** — 复杂架构需要深度推理
4. **跨验证用不同模型** — A/B 生成 + 互评，提高质量
5. **SIMPLE 档用轻量模型** — 节省成本

### 4. ModelAssignmentCache

LRU 缓存 `complexity_level × role → model_id` 映射，避免重复计算。

---

## 配置

### 配置文件

`data/agent_model_config.json`:
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
    "SMALL": {
      "architect": "glm-z1-9b",
      "frontend": "qwen3-8b",
      "backend": "deepseek-r1",
      "reviewer": "deepseek-r1"
    },
    "MEDIUM": {
      "architect": "glm-z1-9b",
      "frontend": "qwen3-8b",
      "backend": "deepseek-r1",
      "reviewer": "deepseek-r1"
    },
    "LARGE": {
      "architect": "glm-z1-9b",
      "frontend": "qwen3-8b",
      "backend": "deepseek-r1",
      "reviewer": "deepseek-r1"
    },
    "XLARGE": {
      "architect": "glm-z1-9b",
      "frontend": "qwen3-8b",
      "backend": "deepseek-r1",
      "reviewer": "deepseek-r1"
    }
  },
  "fallback_chains": {
    "default": ["qwen3-8b", "glm-4-9b", "qwen2.5-7b", "glm-z1-9b", "deepseek-r1"],
    "thinking": ["glm-z1-9b", "deepseek-r1"],
    "fast": ["qwen3-8b", "qwen3.5-4b"]
  }
}
```

### API 端点

- `GET /api/v2/models/assignments` - 查看当前分配
- `PUT /api/v2/models/assignments` - 修改分配（superadmin）
- `GET /api/v2/models/health` - 查看模型健康度
- `POST /api/v2/models/reset-health` - 重置健康分

---

## Fallback 链

模型调用失败时的降级顺序：

### default 链

```
qwen3-8b → glm-4-9b → qwen2.5-7b → glm-z1-9b → deepseek-r1
```

### thinking 链

```
glm-z1-9b → deepseek-r1
```

### fast 链

```
qwen3-8b → qwen3.5-4b
```

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
| `get_assignment(complexity_level, role)` | 获取模型分配 |
| `record_call_result(model, success, latency)` | 记录调用结果 |
| `is_healthy(model)` | 检查模型是否健康 |
| `get_fallback(primary_model, role)` | 获取备选模型 |
| `reset_health(model)` | 重置健康分 |
| `_load_config_assignments()` | 从配置文件加载分配 |

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
2. 检查 SIMPLE 档是否被改成 qwen3-8b（临时）
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
