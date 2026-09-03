# 动态模型路由

> 最后更新：2026-09-03

动态模型路由为 Agent 提供角色模型分配、实时健康评分、连续失败降级和基于历史表现的学习选择。核心实现位于 `app/agent/dynamic_model_router.py`。

## 配置来源

运行时读取 `data/agent_model_config.yaml`：

- `models`：模型 ID、API 模型名、供应商、上下文和调用参数。
- `roles`：architect、frontend、backend、reviewer、fallback 五类角色模型。
- `fallback_chain`：候选模型不可用时的模型顺序。
- `error_type_models`、`settings`、`cross_validation`、`model_context_lengths`：保留给对应运行时功能使用的扩展配置。

`data/agent_model_config.yaml` 通常由 `ModelConfigManager` 从 `data/unified_model_config.yaml` 派生。统一配置保存后会刷新模型映射、角色缓存和降级链。

当前角色配置为：

| 角色 | 模型 ID |
|------|---------|
| architect | `qwen3-8b` |
| frontend | `deepseek-r1` |
| backend | `deepseek-r1` |
| reviewer | `glm-z1-9b` |
| fallback | `qwen3-8b` |

当前降级链为 `qwen3-8b -> glm-z1-9b`。运行时会把模型 ID 解析成供应商 API 使用的模型名。

## 实时健康路由

`ModelMetrics` 为每个模型维护：

- 总请求、成功、失败和连续失败数。
- 最近 100 次延迟、平均延迟和 P95 延迟。
- 当前活动请求数。
- 最近成功与失败时间。

健康分范围为 0 到 100，权重为成功率 50%、平均延迟 30%、活动请求数 20%。平均延迟以 10 秒作为评分衰减上限，活动请求数以 20 作为队列评分上限。

`get_best_model()` 的选择规则：

1. 从候选列表过滤连续失败达到 3 次的模型。
2. 从剩余模型中选择健康分最高者。
3. 候选全部熔断时，按 `fallback_chain` 查找连续失败少于 3 次的模型。
4. 降级链也全部熔断时，强制返回降级链首项供调用方重试。

角色分配还有一层快速保护：`get_assignment()` 和 `get_assignment_with_learning()` 会将连续失败达到 2 次的角色模型替换为 fallback 模型。成功调用会清零该进程内模型的连续失败计数。

熔断行为由计数阈值直接决定，成功调用负责恢复模型计数。

## 学习路由

`LearningRouter` 使用 `ModelPerformanceTracker` 记录按模型和任务类型聚合的成功率、平均延迟、调用数和连续失败数：

- SQLite 路径为 `/tmp/model_performance.db`，启用 WAL 和 5 秒 busy timeout。
- 默认保留 30 天；数据库超过 1 MiB 时进一步清理 7 天前记录并执行 VACUUM。
- 累积记录超过 10 条后，角色分配可启用学习选择。
- 选择使用 20% 探索率，在历史排序和候选列表之间执行 epsilon-greedy 路由。
- 同一任务类型连续失败达到 5 次的模型会在学习选择中降级，成功后恢复。

实时健康指标保存在当前进程内，SQLite 历史统计用于学习路由，两者生命周期不同。

## 系统负载感知

`get_best_model_with_health_awareness()` 可组合模型健康与系统负载：

- 默认 `enable_health_aware_routing = False`，调用普通健康路由。
- 启用后，系统过载时选择负载分最低的候选模型。
- 常态下以模型健康 60%、系统负载 40% 计算综合分。

当前代码库没有其他调用点启用该函数，因此它属于可选能力。

## 上下文与调用参数

`get_context_length()` 按以下顺序解析上下文长度：

1. 用户 API Key Token 对应的自定义配置。
2. `agent_model_config.yaml` 的 `model_context_lengths`。
3. 代码内置模型映射。
4. `/api/v1/providers` 动态供应商同步到内存的模型元数据。
5. 用户 API Key 恢复出的自定义供应商模型元数据。
6. 默认值 32768。

`get_model_config()` 根据上下文窗口和模型配置计算 `temperature`、`max_tokens`、`thinking_budget`、`context_length` 和 `timeout`。

## API 与调用点

- `GET /api/v1/health/models`：读取当前进程的模型健康报告。
- `GET /api/v1/models/agent-config`：只读查看运行时 Agent 配置，需要 JWT。
- `/api/v2/model-config/*`：superadmin 管理统一模型、角色和降级链。
- `/api/v2/models/*`：保留的旧版管理接口。

用户 API Key 可配置 fallback preference：`use_admin_default` 使用管理员默认降级链，`custom` 使用用户提供的降级链，`disabled` 关闭调用层 fallback。接口为 `GET`/`PUT /api/v1/agent/apikey/{token}/fallback-preference`；`disabled` 会由 `LLMClient` 关闭调用层降级处理。

`app/agent/llm_client.py` 在模型调用开始、成功、失败或超时时更新实时指标。多模型 Agent 和模型选择代码会调用学习角色分配。

## 当前边界

- 健康报告仅包含本进程已观察到的模型，服务重启后实时指标清空。
- `/tmp/model_performance.db` 位于临时目录，其跨重启保留行为取决于部署环境。
- `cross_validation` 和错误类型映射属于配置数据；具体业务是否消费这些字段应以调用方实现为准。
- 当前实时阈值由代码中的 2、3 和 5 次规则决定；`settings.circuit_breaker_threshold` 与 cooldown 字段尚未接入这些判断。
- `ModelConfigManager._refresh_runtime_config()` 当前以同步方式调用异步 `get_dynamic_router()`，模型映射和角色缓存可以刷新，已创建路由单例的 fallback 链刷新会进入异常处理分支。

## 相关文件

- `app/agent/dynamic_model_router.py`
- `app/agent/llm_client.py`
- `app/agent/models.py`
- `app/services/model_config_manager.py`
- `data/unified_model_config.yaml`
- `data/agent_model_config.yaml`
- `app/api/v1/health.py`
