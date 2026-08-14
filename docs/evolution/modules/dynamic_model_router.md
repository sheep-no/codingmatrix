# DynamicModelRouter 深扫（dynamic_model_router.py，1035 行）

> 第七十二轮推演 | 2026-08-09 | 定位：模型选择/路由/上下文窗口计算的统一决策层

## 1. 模块定位

DynamicModelRouter 是「选哪个模型」的统一决策层，四个能力域：① 模型 ID/Key/Provider 映射（配置驱动，:35-127）；② 动态路由——基于 ModelMetrics（成功率 50% + 延迟 30% + 队列 20%，:445-468）选健康分最高模型，连续失败 ≥3 熔断（:491-610）；③ 学习路由——LearningRouter + ModelPerformanceTracker（sqlite 持久化）按历史表现选模型，数据 >10 条才启用（:323-397/:657-685）；④ 上下文窗口/模型参数计算（MODEL_CONTEXT_LENGTHS + get_model_config，:848-1035）。健康感知路由（系统负载结合，:780-845）是扩展能力。

### 依赖链

| 方向 | 模块/位置 | 说明 |
|------|-----------|------|
| 依赖 | `utils/system_load.py` system_load_monitor（:15） | 健康感知路由的系统负载源 |
| 依赖 | `utils/aicloud/provider_router.py` ModelProvider（:38） | provider 枚举 |
| 依赖 | `services/apikey_manager` / `dynamic_provider` / `custom_provider_manager`（:909/:930/:941） | context_length 优先级链 |
| 被消费 | `llm_client.py:156-375`（6 处） | **DynamicModelRouter.record_call（内存 metrics）** |
| 被消费 | `models.py:312`、`multi_model_agent.py:201` | **get_assignment_with_learning（学习路由）** |
| 被消费 | `api/v2/model_admin.py:27-309` | 配置管理（save + reload 已接线） |
| 被消费 | `orchestrator_utils`/`specialist_base`/`spec_first_generate` 等（9 文件） | get_model_config/get_context_length/get_best_model |

## 2. 深扫发现

### P2 项

- **DMR1 配置读取失败静默降级**——`_build_provider_map`（:58-59）/`_build_model_id_to_key`（:76-77）`except Exception: return _provider_map_cache or {}`——配置文件损坏/缺失时返回旧 cache（首启为 `{}` 或 `_FALLBACK_MODEL_ID_TO_KEY`），**无日志**；模块加载期（:107/:113）即执行构建，若配置暂不可用则整个会话沿用空映射/兜底，后续配置就绪也不自动重试（需手动 invalidate_model_mapping_cache）。**错误被静默吞 + 缓存不自动恢复**（UT5「不可用=未执行」家族）。
- **DMR6 `DEFAULT_FALLBACK_ORDER` 首尾重复（实测确认）**——:504-508 `["Qwen/Qwen3-8B", "THUDM/GLM-4-9B-0414", "Qwen/Qwen3-8B"]`，第三项与第一项相同。降级链前两个模型都熔断时，第三个实际是第一个模型的重复（Qwen 出现 2 次、GLM-4-9B 仅 1 次）——「3 级降级」实为 2 个不同模型，降级深度虚标。
- **DMR15 学习路由数据链路断裂（实测确认，select_model 死代码）**——`LearningRouter.record_call`（:371-381，写 sqlite ModelPerformanceTracker）**生产代码零调用方**；生产链路（llm_client:156-375）只调 `DynamicModelRouter.record_call`（写**内存** metrics，不落 sqlite）。实测：新开 sqlite 0 条 → `has_sufficient_data()` 恒 False → `get_assignment_with_learning`（:664-665）**恒走静态分配 + 熔断分支**，`learning_router.select_model` 永不执行（死代码）。学习路由有数据模型（sqlite 表）、有选择算法、有门槛逻辑，但**数据通道无写入端**——与 SE1（strategy_evaluator 评估无输入）/CLH1（知识共享无消费）同构，§5.1 学习闭环第三个数据断裂点。
- **DMR14 健康感知路由生产零消费方 + 默认关闭 + docstring 与字段名不一致（实测确认）**——`get_best_model_with_health_awareness` 生产代码零调用方（rg 无）;`RoutingConfig.enable_health_aware_routing` 默认 False（:718）→ :796-798 未启用时直接走传统 `get_best_model`，系统负载感知整体未启用（TT2「启用路径零验证」家族）；docstring :788 写 `enable_health_awareness=True` 而字段名是 `enable_health_aware_routing`（实测确认）——调用者按 docstring 传参将静默不生效（参数被忽略家族）。

### P3 项

- **DMR16 `select_model` 无数据时探索仍触发（实测确认）**——sqlite 无记录时 `get_best_model` 返回空 → ranked=候选原序 → len>1 时 20% 概率 `random.choice(ranked[1:])` 选非第一候选（实测选中 GLM-Z1-9B）。生产被 has_sufficient_data（DMR15）拦截掩盖，但 LearningRouter 被独立调用时会引入无数据探索噪声。
- **DMR17 `get_context_length`/`get_model_config` 每次调用全量读配置 I/O**——:920 `load_agent_model_config()`（读文件）每次调用执行，`get_model_config`（:997）二次读文件——高频生成链调用（spec_first/specialist 每次 LLM 调用前）重复磁盘 I/O，无配置级缓存。
- **DMR18 `ModelMetrics.record_failure` 不记 latency**——:479-485 失败时不 append recent_latencies、不加 total_latency_ms——health_score 的延迟部分对失败模型永远用旧值，熔断后延迟权重失真。
- **DMR19 同步/异步双路径无锁 + `_cleanup` VACUUM 锁表**——`get_assignment`/`_apply_circuit_breaker`（sync，:638/:643）调用 `get_or_create_metrics`（:649）修改 `self._metrics` dict，与 async `get_best_model`（lock 内 :576-610）并发时 dict 竞态；`_cleanup`（:216）大库 VACUUM 锁表阻塞写。

## 3. 演化方向

### 3.1 三层路由的激活顺序

本模块三层能力（内存路由/学习路由/健康感知）现状：**内存路由+熔断是唯一活的**（llm_client 写入、_apply_circuit_breaker 读取）；学习路由和健康感知均未激活。演化顺序：① 修 DMR15 数据通道——把 llm_client 的 record_call 同时写 LearningRouter（或让 DynamicModelRouter 聚合 sqlite 持久化），学习路由即刻有数据；② has_sufficient_data 达标后 select_model 自动启用（此时 DMR16 探索噪声需先修）；③ 健康感知路由（DMR14）依赖系统负载监控数据可信度，是第 3 步。**这三层是 §5.3 Evaluator-optimizer 在模型选择维度的落地形态**——评估数据（record_call）是唯一输入，当前只有内存态半闭环。

### 3.2 上下文窗口管理

MODEL_CONTEXT_LENGTHS（:853-883）注释自述「手动维护静态映射，API 支持后自动同步」——新模型必须改代码。演化方向：配置驱动 + 运行期探测，消除硬编码映射漂移（DMR17 读配置优化与静态映射收敛到同一配置源）。

## 4. 主线关联

- **学习闭环主线（第三处断裂）**：DMR15（学习路由无数据写入）+ SE1（评估无输入）+ CLH1（知识共享无消费）——§5.1 学习闭环在评估/学习/共享三处数据通道全部断裂
- **评估数据主线**：llm_client 的 record_call 是唯一活的数据写入点（内存 metrics），与 AGM5/ModelUsageStats（DB 层模型统计）双轨并存——同一「模型表现」被两套独立记录
- **参数忽略家族**：DMR14 docstring 字段名不一致（CLH2/MEM2 家族）
- **静默降级**：DMR1 配置失败静默（UT5/SE6 家族）

## 5. 测试状态

ModelPerformanceTracker/ModelMetrics 有独立可测性（sqlite 可注入 db_path），但生产链路 llm_client→DynamicModelRouter 无集成测试；学习路由与健康感知两个死代码路径无测试（未被测试覆盖也未暴露其死亡状态）。
