# Agent 引擎 · 大系统演化文件

> 版本：v1.7 | 日期：2026-08-05 | 大系统：`app/agent/`（98 模块，15 子系统）
>
> 本文件是 Agent 大系统的**演化总文件**，列出其 15 个子系统的演化文件映射与具体演化路径。更详细的逐阶段推演见各子系统演化文件。
>
> **2026-08-05 实测复核（v1.7）**：AGENT-ENGINE 更新至 v1.10、BATCH1 至 v1.3——**演化拆分建议归属修正**：`_initialize_components` 定义于 `mixin.py:39`（非 spec_first）；`_select_engineer` 仅定义于 `orchestrator_files.py:577`（spec_first 经继承调用，非重复定义）；`_recover_invalid_content_orchestator` 与 `_recover_invalid_content` 为两套不同名同类实现；`refine` 仅 `refinement_loop.py:94`。**拆分可行性验证通过**：cross_validator 可拆四部分、tools.py 文件(10)/git(4)/搜索(3)/执行(2)四域、dynamic_model_router 指标/熔断/学习/配置四部分全部成立。**模块数口径修正**：header「112 模块」修正为 **98**（15 个子系统标注模块和 8+10+10+4+11+4+12+5+9+7+5+5+4+1+3=98，与 `app/agent` 实际去重模块数 98 精确一致；AGENT-ENGINE 对应修正为 77 顶层模块 + 3 子包）。
>
> **2026-08-05 实测复核（v1.6）**：BATCH1-3 更新至 v1.2——**补全全部 19 处「-」行数**（A6 strategy_evaluator 329/strategy_learner 399/critical_decision 332；A7 code_validator 767/api_contract_checker 501/integrity_validator 508/dependency_graph_validator 344/refinement_loop 584/error_classifier 196/file_contract 141/signature_extractor 251/multi_angle_review 331/consistency_checker 208；A10 user_preference_learner 487/fix_pattern_cache 266/cloud_learning_hub 336/conversation_store 317）；**`critical_decision.py` 由「🔍 待确认」修正为「✅ 已接线」**（spec_first:14/:165 + orchestrate_endpoints:742，332 行）；BATCH1 行号校正（`_try_react_auto_fix` 定义 :12→:9、traditional 调用 :295→:294、:298→:297）；A1 八模块行数、spec_first:28/:853、orchestrator_testing:19、docker_runner 三使用方、dynamic_model_router:880 Kolors 注释全部复核精确。
>
> **2026-08-05 实测复核（v1.5）**：AGENT-ENGINE.md 已更新至 v1.9——收集错误实测 **8 个**（`_LayeredModelRouterCompat` 缺失被 test_multi_model_agent + test_orchestrator 两个文件引用；`test_specialist_base` 引用不存在的 `_REACT_MODE_BY_COMPLEXITY`；aiofiles 未声明且未装致 4 个测试收集失败；test_security_services 引用 PyJWT 而项目统一 jose）；用例数实测更新（单测 **1506**、E2E **413**）；模型配置断言行号全部精确（dynamic_model_router:735、services/model_config_manager:232、model_admin:67/:83、react_agent:72、MODEL_REGISTRY 17 模型）。
>
> **2026-08-04 实测复核（v1.4）**：AGENT-ENGINE.md 已更新至 v1.8（含「5×5 角色复杂度矩阵」不存在的断言修正——`dynamic_model_router.py` 已移除复杂度依赖、tools.py 工具数 21→20、orchestrator_testing:36、端点实测 257）；三个 BATCH 文件更新至 v1.1——**docker_runner 非孤儿（3 生产使用方）**、tracing 接线 11 处、orchestrator_progress 引用 8 处、react_engine 已确认接线、coverage_checker 已确认接线、mcp_client:41、方法数校正（A13 4 处 + code_patcher）。

## 演化文件索引

| 文件 | 内容 |
|------|------|
| [AGENT-ENGINE.md](AGENT-ENGINE.md) | 大系统总演化（编排/角色/路由/验证/RAG/孤儿/实测 Bug） |
| [AGENT-CONTEXT-COMPRESSION.md](AGENT-CONTEXT-COMPRESSION.md) | A4 上下文压缩子系统专项演化 |
| [AGENT-EVOLUTION-BATCH1.md](AGENT-EVOLUTION-BATCH1.md) | A1-A3 详细推演（现状→目标→阶段→风险） |
| [AGENT-EVOLUTION-BATCH2.md](AGENT-EVOLUTION-BATCH2.md) | A4-A7 详细推演 |
| [AGENT-EVOLUTION-BATCH3.md](AGENT-EVOLUTION-BATCH3.md) | A8-A15 详细推演 |

## 子系统演化路径总览

### A1 编排核心（orchestrator 家族，8 模块）
- **演化文件**：[AGENT-EVOLUTION-BATCH1.md §A1](AGENT-EVOLUTION-BATCH1.md#a1-编排核心8-模块)
- **演化路径**：消除 SharedContext 间接依赖（P1）→ Mixin 职责收敛（P2）→ multi_model_agent 归一（P3）→ tracing/进度/成本端到端可观测（P3）

### A2 生成路径（orchestrator_generation/，10 模块）
- **演化文件**：[AGENT-EVOLUTION-BATCH1.md §A2](AGENT-EVOLUTION-BATCH1.md#a2-生成路径10-模块)
- **演化路径**：spec_first 2383 行拆分（P1）→ incremental_modify 拆分 + 消除间接依赖（P1）→ 删除 traditional 路径（P1）→ feature_extractor RAG 写入打通（P1）→ evaluate_mixin 收敛（P2）；coverage_checker **已确认接线**（v1.1）

### A3 需求分析（orchestrator_requirements/，10 模块）
- **演化文件**：[AGENT-EVOLUTION-BATCH1.md §A3](AGENT-EVOLUTION-BATCH1.md#a3-需求分析10-模块)
- **演化路径**：faiss 安装使 layer2 向量检索生效（P0）→ 三层质量闭环 + 检索过滤去重（P2）→ feedback_tracker 入学习闭环（P2）→ 对抗审查按需触发 + 域识别 LLM 化（P2/P3）

### A4 上下文压缩（conversation_store/agent_core/端点，4 模块）
- **演化文件**：[AGENT-CONTEXT-COMPRESSION.md](AGENT-CONTEXT-COMPRESSION.md) + [AGENT-EVOLUTION-BATCH2.md §A4](AGENT-EVOLUTION-BATCH2.md#a4-上下文压缩要点详见详细文档)
- **演化路径**：token 口径统一（P1）→ 压缩持久化 + 阈值感知窗口（P1）→ compress_history LLM 摘要接线 + ContextCompressor 归一（P1/P2）→ 预防式压缩 + 摘要入库跨会话记忆（P2/P3）

### A5 角色体系（specialist 家族 + react + ppt_agent，11 模块）
- **演化文件**：[AGENT-EVOLUTION-BATCH2.md §A5](AGENT-EVOLUTION-BATCH2.md#a5-角色体系11-模块)
- **演化路径**：react_engine 已确认接线 + task_planner 孤儿决策（P2）→ AgentRole 接口化（P3）→ 角色工具白名单差异化（P3）

### A6 模型路由（dynamic_model_router 等，4 模块）
- **演化文件**：[AGENT-EVOLUTION-BATCH2.md §A6](AGENT-EVOLUTION-BATCH2.md#a6-模型路由4-模块)
- **演化路径**：三源合一（MODEL_REGISTRY/JSON/内存，P1）→ 默认模型切换失效修复 + is_free 空壳修复（P1）→ 图片模型入路由 + 窗口感知（P1/P2）→ strategy_learner 接线 + ε-greedy 学习闭环（P2）

### A7 验证与修复（validator 家族，12 模块）
- **演化文件**：[AGENT-EVOLUTION-BATCH2.md §A7](AGENT-EVOLUTION-BATCH2.md#a7-验证与修复12-模块)
- **演化路径**：Java/Go 静态验证补齐（P0）→ cross_validator 1512 行拆分（P1）→ CodeValidator vs CrossValidator 职责收敛（P2）→ record_fix 全覆盖学习闭环（P2）

### A8 测试运行（test_runner 家族，5 模块）
- **演化文件**：[AGENT-EVOLUTION-BATCH3.md §A8](AGENT-EVOLUTION-BATCH3.md#a8-测试运行5-模块)
- **演化路径**：test_runner 收敛为轻量验证 + docker_runner 迁移 3 处引用后废弃（P0，v1.1 修正非孤儿）→ VSCode 插件本地验证入口（P3）→ 验证报告 JSON 协议化（P3）

### A9 工具执行（executor/tools 家族，9 模块）
- **演化文件**：[AGENT-EVOLUTION-BATCH3.md §A9](AGENT-EVOLUTION-BATCH3.md#a9-工具执行9-模块)
- **演化路径**：ToolRegistry 单例闭包 Bug 修复（P0）→ 工具错误处理中间件（P1）→ tools.py 1292 行域分组拆分（P1）→ 与 Workflow 节点对齐（P2）

### A10 学习与记忆（learner/memory 家族，7 模块）
- **演化文件**：[AGENT-EVOLUTION-BATCH3.md §A10](AGENT-EVOLUTION-BATCH3.md#a10-学习与记忆7-模块)
- **演化路径**：孤儿模块接线/删除决策（P2）→ 三处余弦相似度收敛 utils/similarity.py（P2）→ record_fix 学习闭环全覆盖（P2）→ 跨会话记忆（P3）

### A11 RAG 与检索（vector_index 家族，5 模块）
- **演化文件**：[AGENT-EVOLUTION-BATCH3.md §A11](AGENT-EVOLUTION-BATCH3.md#a11-rag-与检索5-模块)
- **演化路径**：faiss 安装 + spec-first 写索引（P0/P1）→ 检索过滤去重 + embedding 可配置 + 索引健康检查（P2）→ 跨会话长记忆（P3）

### A12 依赖分析（dependency_graph 家族，5 模块）
- **演化文件**：[AGENT-EVOLUTION-BATCH3.md §A12](AGENT-EVOLUTION-BATCH3.md#a12-依赖分析5-模块)
- **演化路径**：dependency_graph 1340 行拆分（P1）→ multi_language_parser 孤儿处置（P3）→ import 验证增强（插件回传，P2）

### A13 语言适配（adapters/，4 模块）
- **演化文件**：[AGENT-EVOLUTION-BATCH3.md §A13](AGENT-EVOLUTION-BATCH3.md#a13-语言适配4-模块)
- **演化路径**：新语言配置化注册（P2）→ Java/Go 适配器与 code_validator 对齐（P1）

### A14 MCP 集成（mcp_client，1 模块）
- **演化文件**：[AGENT-EVOLUTION-BATCH3.md §A14](AGENT-EVOLUTION-BATCH3.md#a14-mcp-集成1-模块)
- **演化路径**：MCP 工具注册进 SPECIALIST_TOOLS + 动态工具选择（P2）→ 健康度入路由（P3）

### A15 基础工具（utils/complexity/shadow_scanner，3 模块）
- **演化文件**：[AGENT-EVOLUTION-BATCH3.md §A15](AGENT-EVOLUTION-BATCH3.md#a15-基础工具3-模块)
- **演化路径**：utils.py 1383 行按域拆子包（P1）→ complexity 与关键文件判定共用（P2）

## 演化批次与优先级

- **批1 主链路**（A1-A3）：拆分止血 + RAG 打通
- **批2 能力层**（A4-A7）：配置归一 + 验证补齐 + 角色抽象
- **批3 支撑层**（A8-A15）：P0 修复 + 支撑能力收敛

**P0 清单**（最先修复）：faiss 安装、ToolRegistry 闭包 Bug、test_runner 收敛、Java/Go 静态验证
