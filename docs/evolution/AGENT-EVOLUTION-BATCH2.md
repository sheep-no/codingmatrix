# Agent 子系统详细推演 · 批2：能力层

> 版本：v1.8 | 日期：2026-08-05 | 范围：A4 上下文压缩 + A5 角色体系 + A6 模型路由 + A7 验证与修复（4 个子系统，模块表 27 个：A5=11 + A6=4 + A7=12，A4 见专项文件）
>
> 本文是 `TASKS.md` A 组演化路径清单的**详细推演版**。A4 已有独立详细文档 [AGENT-CONTEXT-COMPRESSION.md](AGENT-CONTEXT-COMPRESSION.md)，本文件对 A5-A7 展开，A4 列要点并指向详细文档。原则：**先修正确性、再统一机制、后智能增强**。
>
> **v1.8（2026-08-05 系统性补推演 + Backlog 落地）**：**复盘方法论缺陷**——前两轮推演漏检 notes/chart/type 的根因是范围局限模块内部，未做字段级数据流追踪；新增四步标准推演流程（模块断言→数据流字段消费矩阵→语义契约核对→Backlog）。§3.5 升级为**字段级消费追踪表**（SlideOutline 六字段 × 视觉/默认/HTML 三路径消费矩阵）并产出 **10 项待修改清单（Backlog）**：新增关键发现 `type` 字段渲染层整体忽略（7 类契约未兑现）、`slide_type` 语义两套并存（PPTAgent title/... vs 引擎 cover/...，HTML :676 封面跳过失效）、`image_keywords` 默认路径不消费。
>
> **v1.7（2026-08-05 PPT 美观/实用能力核查）**：§3.5 增「实用度缺口」实测——**notes 演讲备注零消费**（`app/utils/pptx/`+`app/utils/visual/` 全目录零读取，PPTX 备注页从未写入，而 PPTAgent 多轮 prompt 强制输出 notes）；**chart 类型零支持**（`SlideType.CHART` 存在但渲染链路无 chart 分支，退化为普通内容）。美观能力画像：9 套配色模板（`PPT_TEMPLATES` 仅主/辅色 2 维）+ layout_decider（755 行，图文/纯内容两模式布局 + 多样 bullet 符号）+ 自定义模板库（templates/presets）+ 动画引擎——但 **PPTAgent 大纲层零美观控制**（无 style/template 字段，模板由请求参数决定默认 modern）。改进杠杆：大纲层注入风格意图透传模板选择 > 模板维度扩展（字体/背景/装饰）> layout_decider 版式变体（时间线/对比/卡片）。
>
> **v1.6（2026-08-05 PPTAgent 演进方案细化）**：A5 阶段三补充 §3.5「PPTAgent 专项演进细化」——基于两轮推演基线，给出 P1 清理（modify_outline 接线或弃用、补 test_ppt_agent.py、quality 落地）+ P2 角色体系接入（实现 AgentRole「生成」钩子、注册进 specialists.py 聚合出口、不继承 Specialist，避免引入无用 ReAct/工具重量）+ P3 架构解耦（大纲生成下沉 service、call_llm 换 LLMClient、惰性钩子处置）。核心判断：PPTAgent 为纯 JSON 生成器，强套 Specialist 成本高，走轻量 AgentRole 接口。
>
> **v1.5（2026-08-05 PPTAgent 再次推演）**：**`modify_outline` 孤儿 public 方法**——全库（app + tests）零调用（仅 ppt_agent.py:329 定义），与活跃入口 `generate_outline`（aiGeneratorPptx:1585/:1629 双端点调用）对比明确，属 dead code；**测试覆盖缺失**——tests/ 全库无任何直接 import ppt_agent/PPTAgent，`test_ppt_unified_generation.py` 走 pptx 引擎路径（sample_outline fixture + 引擎函数），不覆盖 PPTAgent 两入口；**边界安全确认**——`num_slides` 请求层 `Field(ge=1, le=50)`（aiGeneratorPptx:1559，PPT_MAX_SLIDES=50:63）挡住 `_validate_outline`/`_fallback_outline` 退化分支（num_slides<=2 时 range(2, num_slides-1) 为空、pop(-2) 不越界）。
>
> **v1.4（2026-08-05 PPTAgent 专项推演）**：`ppt_agent.py` 420 行实测。接线确认 `aiGeneratorPptx.py` 共 5 处（:1582/:1624 import、:1584/:1628 实例化、:1637 `adapt_for_pptx_engine` 静态适配）；**单点依赖**——PPTAgent 唯一消费方为 aiGeneratorPptx.py（main.py:62 仅挂路由）；PPTAgent 为独立类不继承 specialist_base（实码支撑 A5 演进条目「当前独立于 specialists.py」）；**惰性接线发现**——skill_registry 钩子 `ppt_system_prompt` 全库零注册（`data/custom_skills/_metadata.json` skills=[]，仅 ppt_agent.py:96 读取），:95-98 自定义 system_prompt 逻辑空转回退内置默认；`quality` 参数（:78 注释「保留用于未来扩展」）未落实现，`__init__` 仅存 model；直连 call_llm 三处（:104/:238/:379）；依赖 ArchitectJsonParser（safe_parse_json）与 skill_registry。
>
> **v1.3（2026-08-05 最终确认推演）**：**全量行数断言复核零偏差**——27 模块表（A5=11 + A6=4 + A7=12）全部与实测精确一致；file:line 复核（`orchestrator_generation/error_recovery.py:17` 动态 import、spec_first:14/:165 + orchestrate_endpoints:742 critical_decision 接线、multi_model_agent:42 noqa、dynamic_model_router:880 Kolors）全部精确；A5 表 `error_recovery.py` 与顶层 797 行同名歧义已在 BATCH1 A2 表补全路径消歧。header 模块数「约 30」修正为 **27**（A4 见专项文件）。
>
> **v1.2（2026-08-05 实测复核）**：用例数更新 1376→**1506** 单测、409→**413** E2E（对齐 AGENT-ENGINE v1.9 实测基线）；A5 全部 11 模块行数复核精确（specialist_base 294 / specialists 15 / architect 987 / backend_engineer 356 / frontend_engineer 326 / code_reviewer 168 / ai_reviewer 223 / ppt_agent 420 / react_agent 200 / react_engine 770 / task_planner 180）；`orchestrator_generation/error_recovery.py:17` 动态 import `ReActAgent, ReActResult` 实测成立。**补全 A6/A7 全部行数**：A6 strategy_evaluator 329 / strategy_learner 399 / critical_decision 332；A7 code_validator 767 / api_contract_checker 501 / integrity_validator 508 / dependency_graph_validator 344 / refinement_loop 584 / error_classifier 196 / file_contract 141 / signature_extractor 251 / multi_angle_review 331 / consistency_checker 208。**`critical_decision.py` 由「🔍 待确认」修正为「✅ 已接线」**（spec_first_generate:14/:165 + orchestrate_endpoints:742）；`dynamic_model_router.py:880` Kolors 注释复核精确。
>
> **v1.1（2026-08-04 实测复核）**：react_engine 接线由「待确认」改为「已确认」（react_agent/specialist_base/task_planner/agent_executor 4 处引用）；task_planner 孤儿疑点保持（仅 multi_model_agent.py:42 noqa F401）；**「角色复杂度矩阵」为不存在的断言**（`dynamic_model_router.py:638-660` docstring 明示「不再依赖复杂度」，全库无实现），A6 表已修正为「roles 配置分配（无复杂度矩阵）」；其余行数/接线断言全部实测成立。

## 总览

| 子系统 | 关键现状 | 代表演化点 |
|--------|---------|-----------|
| A4 上下文压缩 | 三层压缩并存，LLM 压缩未接线 | 详见 AGENT-CONTEXT-COMPRESSION.md |
| A5 角色体系 | 4 角色 + 独立 PPTAgent，无统一角色抽象 | AgentRole 接口化（P3） |
| A6 模型路由 | 三套模型数据源互不相通，默认切换失效 | 三源合一（P1） |
| A7 验证修复 | cross_validator 1512 行，Java/Go 验证为零 | 静态验证补齐（P0） |

---

## A4. 上下文压缩（要点，详见详细文档）

**完整推演见 [AGENT-CONTEXT-COMPRESSION.md](AGENT-CONTEXT-COMPRESSION.md)**。关键演化链：
1. **阶段一正确性修复**：token 口径统一（tiktoken 单一口径）、压缩持久化（免重复压缩）、阈值感知模型窗口、压缩后必达标
2. **阶段二机制归一**：`compress_history` LLM 语义压缩接线、主压缩提取增强、`ContextCompressor` 统一入口
3. **阶段三智能压缩**：预防式压缩、增量摘要、压缩质量回检
4. **阶段四跨会话记忆**：摘要落库、新会话 RAG 检索续作

---

## A5. 角色体系（11 模块）

### 1. 现状基线

| 模块 | 行数 | 职责 | 接线状态 |
|------|------|------|---------|
| `specialist_base.py` | 294 | `Specialist` 基类 + 日志/并发常量 | ✅ 各角色继承 |
| `specialists.py` | 15 | 聚合导出 Specialist/Architect/Frontend/Backend/CodeReviewer | ✅ 统一出口 |
| `architect.py` | 987 | Architect 角色（架构设计） | ✅ |
| `backend_engineer.py` | 356 | Backend 角色（2 类） | ✅ |
| `frontend_engineer.py` | 326 | Frontend 角色 | ✅ |
| `code_reviewer.py` | 168 | CodeReviewer 角色，已接 tracing | ✅ |
| `ai_reviewer.py` | 223 | AI 审查角色 | ✅ |
| `ppt_agent.py` | 420 | PPTAgent 大纲生成，接线 aiGeneratorPptx:1582/:1584/:1624/:1628/:1637 唯一消费方；`modify_outline` 孤儿方法零调用；skill 钩子 ppt_system_prompt 零注册空转 | ✅ |
| `react_agent.py` | 200 | ReActAgent（4 类），经 __init__ 导出 | ✅ 由 error_recovery 动态 import |
| `react_engine.py` | 770 | ReAct 引擎（4 类） | ✅ 已接线（react_agent/specialist_base/task_planner/agent_executor 4 处引用） |
| `task_planner.py` | 180 | TaskPlanner | ⚠️ 仅 multi_model_agent:42 引用（noqa F401 注释，疑死代码） |

**实测确认（2026-08-04）**
- `specialists.py` 是 4 个生产角色的聚合出口（15 行纯 re-export）
- `react_agent` 经 `app/agent/__init__.py` 导出 + `orchestrator_generation/error_recovery.py:17` 动态 import；`react_engine`（ReActEngine）被 react_agent/specialist_base/task_planner/agent_executor 4 处引用——**已接线，非孤儿**
- `task_planner.py`：唯一引用是 `multi_model_agent.py:42` 带 `# noqa: F401`（仅导入防误删，实际未调用）——**疑为孤儿**

### 2. 演化目标

```
【近期】孤儿确认：task_planner/react_engine 接线核实
  ↓
【中期】角色抽象：AgentRole 接口（规划/生成/验证/修复钩子）
  ↓
【长期】工具白名单：不同角色不同工具权限、角色配置注册
```

### 3. 分阶段路径

**阶段一（近 1 迭代）：孤儿确认与决策**
- `react_engine` **已确认接线**（4 处引用），无需处置；与 `react_agent` 职责边界文档化即可
- `task_planner` 唯一引用是 multi_model_agent.py:42（noqa F401 仅导入防误删）：全库二次扫描确认零实际调用后，决策接线（供 Architect 规划）或标记废弃
- 验收：grep 确认每个角色模块都有真实生产调用方或显式废弃标记

**阶段二（近 2 迭代）：角色抽象**
- 定义 `AgentRole` 接口（规划/生成/验证/修复钩子），`Specialist` 体系作为内置实现（承接 AGENT-ENGINE.md 6.1）
- 角色通过配置/技能包注册，支持第三方自定义角色
- 验收：新角色注册无需修改引擎源码（仅配置/插件目录）

**阶段三（中期）：工具权限差异化**
- 不同 `AgentRole` 拥有不同工具白名单（承接 AGENT-ENGINE.md 6.3 动态工具选择）
- PPTAgent 纳入统一角色注册（当前独立于 specialists.py）
- 验收：角色工具裁剪生效，PPTAgent 以角色形式注册

### 3.5 PPTAgent 专项演进细化（2026-08-05 专项推演后补充）

**推演基线**：`ppt_agent.py` 420 行，独立类不继承 Specialist；唯一消费方 `aiGeneratorPptx.py`（5 处：:1582/:1584/:1624/:1628/:1637）；`modify_outline` 孤儿 public 方法零调用；tests/ 零直接覆盖；`ppt_system_prompt` skill 钩子零注册空转；`quality` 参数未实现。

**演进顺序（不直接套 Specialist——PPTAgent 为纯 JSON 生成器，无 ReAct/工具需求，强继承会引入无用重量机制）**：

- **P1 清理（近 1 迭代）**
  - `modify_outline` 接线：aiGeneratorPptx 增 `POST /modify-from-text`（复用 OutlineGenerationRequest 骨架），孤儿方法转活；若产品无改稿需求则加 `@deprecated` 标注
  - 补 `tests/unit/test_ppt_agent.py`（mock call_llm）：`generate_outline` 正常解析/LLM 兜底/退避 fallback 三路径、`modify_outline`、`_validate_outline` 边界（空 slides/非法 type/num_slides 收缩 pop(-2)/首尾补页）、`adapt_for_pptx_engine`
  - `quality` 落地 3 档（balanced/fast/high_quality → temperature/prompt 分支）或删除；num_slides<2 防御（当前仅靠请求层 `ge=1`）

- **字段级消费追踪（2026-08-05 系统性补推演，属 P1 修复项）**——SlideOutline 各字段在三条渲染路径（视觉 visual_analyzer→layout_decider / 默认 _render_slide_default / HTML generate_html_ppt）的消费实测：

| 字段 | 视觉路径 | 默认路径 | HTML 路径 | 结论 |
|------|---------|---------|-----------|------|
| `title` | ✅ :576 | ✅ :273/:291 | ✅ | 正常 |
| `bullets`→`content`（适配器补） | ✅ :261/:577 | ✅ :308 | ✅ :682 | 正常 |
| `image_keywords` | ✅ :595 搜图 | ⚠️ 仅认 `local_images` | ❌ | 视觉失败时无图 |
| `notes` | ❌ | ❌ | ❌ | **完全死字段，备注页从不写入** |
| `type`/`slide_type` | ❌ 忽略 | ❌ 忽略 | ⚠️ 读但语义不符 | **7 类契约全失效** |

  - **`type` 字段渲染层整体忽略**：PPTAgent 生成 7 种 SlideType（title/chapter/content/bullet/image/chart/end），但两条 PPTX 路径都不读 type——视觉路径布局由 visual_analyzer 按内容分析决定，默认路径统一内容渲染。SlideType 枚举是大纲层的「契约承诺」，渲染层未实现对应契约
  - **`slide_type` 语义两套并存**：PPTAgent 输出 `title/chapter/...`（ppt_agent.py:26-34），引擎期望 `cover/content/summary/toc`（aiGeneratorPptx:417/:471/:478/:485/:492）。HTML 路径 `:676 if slide_type=='cover'` 对 PPTAgent 输出永远为 False，封面跳过逻辑失效
  - **chart 零支持**：`SlideType.CHART`（ppt_agent.py:33）存在，layout_decider LayoutType 仅 5 种（title_slide/content_with_image/content_only/two_column/center_focus，layout_decider.py:32-38），无 chart 布局
  - 修复：统一 slide_type 语义或适配层做映射（title→cover/chapter→toc 等）；type 契约落地（LayoutType 增 chart/summary）或大纲层降级为 content 单类型；notes 写备注页

- **P2 角色体系接入（中期，承接阶段二 AgentRole 接口）**
  - PPTAgent 实现 AgentRole「生成」钩子，经配置注册进 specialists.py 聚合出口（`__all__` 增 PPTAgent），**不继承 Specialist**
  - 保留 `adapt_for_pptx_engine` 独立能力接口（对应风险表「保留 PPTAgent 独立能力接口」）

- **P3 架构解耦（长期）**
  - PPT 大纲生成下沉 `app/services/ppt_outline_service.py`，aiGeneratorPptx.py（2133 行）路由层变薄
  - 直连 call_llm 换 LLMClient（复用 dynamic_model_router 模型路由/降级/成本追踪）；`ppt_system_prompt` 钩子注册示例或移除

**待修改清单（Backlog，按优先级排序，全部实测确认）**

| # | 优先级 | 问题 | 位置 | 修复方向 |
|---|--------|------|------|---------|
| 1 | P1 | `slide_type` 语义两套（title/... vs cover/...），HTML 封面跳过失效 | ppt_agent.py:26-34 / aiGeneratorPptx.py:676 | 适配层映射或统一语义 |
| 2 | P1 | `type` 字段渲染层整体忽略，7 类契约未兑现 | ppt_agent.py:26-34 / layout_decider.py:32-38 | LayoutType 补 chart/summary 或降级单类型 |
| 3 | P1 | `notes` 演讲备注零消费，PPTX 备注页从不写入 | ppt_agent.py:44 / 渲染链路 | 渲染层写 speaker notes |
| 4 | P1 | `modify_outline` 孤儿 public 方法，零调用 | ppt_agent.py:329 | 接线 `POST /modify-from-text` 或 @deprecated |
| 5 | P1 | 无直接单元测试（tests/ 零引用） | tests/ | 补 test_ppt_agent.py |
| 6 | P1 | `image_keywords` 默认路径不消费（仅认 local_images），视觉失败无图 | aiGeneratorPptx.py:326 | 默认路径接搜图结果 |
| 7 | P2 | `quality` 参数未实现（死参） | ppt_agent.py:78 | 落地 3 档或删除 |
| 8 | P2 | `ppt_system_prompt` skill 钩子零注册空转 | ppt_agent.py:95-98 | 注册示例或移除 |
| 9 | P2 | 单点依赖 aiGeneratorPptx（2133 行巨型路由） | aiGeneratorPptx.py | 大纲生成下沉 service |
| 10 | P3 | 直连 call_llm（不计入模型路由/成本） | ppt_agent.py:104/:238/:379 | 换 LLMClient |

**方法论改进（2026-08-05 复盘）**：前两轮推演漏检 notes/chart/type 的根因是**推演范围局限模块内部**（验证行数/接线/孤儿），未做字段级数据流追踪。**新增标准推演流程**——① 模块边界断言（行数/行号/接线）② 数据流追踪（输出 Schema 每个字段在下游全部消费方的消费矩阵）③ 语义契约核对（同名字段在不同层语义一致性）④ 产出 Backlog。后续模块推演均按此四步执行。

### 4. 风险与依赖

| 风险 | 应对 |
|------|------|
| 角色抽象破坏现有 Specialist 调用 | 接口层适配，Specialist 作为默认实现不破坏对外签名 |
| react_agent 动态 import 脆弱 | 改为显式依赖注入，去除局部 import |
| PPTAgent 独立演化 | 统一角色注册时保留 PPTAgent 独立能力接口 |

---

## A6. 模型路由（4 模块）

### 1. 现状基线

| 模块 | 行数 | 职责 | 接线状态 |
|------|------|------|---------|
| `dynamic_model_router.py` | 1035 | 健康评分/熔断/降级链/ε-greedy 学习路由/roles 配置分配（无复杂度矩阵） | ✅ 主路由 |
| `strategy_evaluator.py` | 329 | 策略评估 | ✅ 已接线 error_recovery（get_strategy_template/record_evaluation_result） |
| `strategy_learner.py` | 399 | Q-Learning 策略优化 | ⚠️ 孤儿（仅测试） |
| `critical_decision.py` | 332 | 关键决策（CriticalDecisionExtractor） | ✅ 已接线 spec_first_generate:14/:165 + orchestrate_endpoints:742 |

**实测确认（2026-08-02，AGENT-ENGINE.md 9.6）**
- **三套模型数据源互不相通**：
  - `MODEL_REGISTRY`（`utils/aicloud/model_registry.py`）：硬编码 17 模型，用户端浏览
  - `agent_model_config.json` roles + `DEFAULT_*_MODEL`：Agent 实际生成
  - 内存 `_runtime_default_model`：进程级，仅影响 is_default 标记
- **默认模型切换失效**：`POST /model-admin/default` 只写内存不落盘，重启即失效，对 Agent 生成零影响
- **is_free 空壳**：17 模型无 is_free=True，`free_only` 过滤参数未使用

### 2. 演化目标

```
【近期】配置归一：三源合一，默认/免费语义修正
  ↓
【中期】能力扩展：图片模型纳入路由、窗口感知
  ↓
【长期】学习闭环：ε-greedy 与策略学习合并
```

### 3. 分阶段路径

**阶段一（近 1-2 迭代）：配置三源合一**
- 删除 `_runtime_default_model` 内存切换机制，default/roles 统一走 `unified_model_config.json`（经 `_sync_to_agent_config` 同步）
- `MODEL_REGISTRY` 每模型补 `is_free` 标注，`list_models.free_only` 真参与过滤
- 收敛 `model_registry.py`（硬编码）与 `model_config_manager.py`（JSON）为一套数据源
- 验收：管理员切默认/免费模型后，Agent 生成与用户端浏览一致生效且重启保留

**阶段二（近 2 迭代）：能力扩展**
- `dynamic_model_router.py:880` 注释的 Kolors 落地：图片生成计入统一路由/成本/并发（承接 IMAGE-GENERATION.md 5.1）
- 新增模型上下文窗口映射，路由感知窗口指导压缩/预算（承接 A4）
- `dynamic_model_router.py`（1035 行）拆指标收集/熔断/学习路由/配置加载
- 验收：图片模型可路由切换，窗口感知生效，模块 <800 行

**阶段三（中期）：学习闭环**
- ε-greedy 学习数据与 `strategy_learner`（Q-Learning）合并评估（承接 AGENT-ENGINE.md 5.1）
- `strategy_learner` 从孤儿接线为策略评估回调，离线回放验证
- 验收：路由学习数据单一来源，策略回放验证通过

### 4. 风险与依赖

| 风险 | 应对 |
|------|------|
| 三源合一破坏现有端点 | 先删内存切换端点（9.6 建议），统一配置灰度替换硬编码注册表 |
| 图片模型入路由影响生成并发 | 沿用现有 Semaphore 并发控制，独立配额 |
| strategy_learner 接线不稳定 | 先「记录-观察」模式，Q-Learning 离线回放 |

---

## A7. 验证与修复（12 模块）

### 1. 现状基线

| 模块 | 行数 | 职责 | 接线状态 |
|------|------|------|---------|
| `cross_validator.py` | 1512 | 双模型对抗生成/裁判合并/符号/契约/一致性/关键模式 | ✅ 主验证 |
| `code_validator.py` | 767 | 单文件语法/API 映射/requirements 验证（仅 py/js/html/css） | ✅ |
| `api_contract_checker.py` | 501 | API 契约检查 | ✅ |
| `integrity_validator.py` | 508 | 项目完整性 | ✅ |
| `dependency_graph_validator.py` | 344 | 依赖图校验 | ✅ |
| `error_recovery.py` | 797 | 唯一带模型降级的修复器（分类→策略→3 轮→降级链） | ✅ |
| `refinement_loop.py` | 584 | RefinementLoop 精炼循环（2-5 轮） | ✅ |
| `error_classifier.py` | 196 | ErrorClassifier 错误分类 + 修复策略 | ✅ |
| `file_contract.py` | 141 | 文件契约 | ✅ |
| `signature_extractor.py` | 251 | 函数签名提取 | ✅ |
| `multi_angle_review.py` | 331 | MultiAngleReviewSkill 多角度审查 | ✅ 已接线 agent_skills |
| `consistency_checker.py` | 208 | 简化一致性检查 | ⚠️ 孤儿（被 cross_validator 取代） |

**实测确认（2026-08-02）**
- **主路径修复链全静态验证驱动**（AGENT-ENGINE.md 9.8）：
  - ① 双模型对抗（复杂文件）→ ② RefinementLoop（2-5 轮）→ ③ 内容质量校验 → ④ 写入前语法验证 → 原子写入
  - ④ 失败 → `error_recovery.validate_and_fix`（分类→策略模板→3 次修复→模型降级链）→ 仍败 → `_retry_generate_file`
- **code_validator 只处理 .py/.js/.html/.css**：Java/Go 项目语法错误全漏（Spring Boot 刚需）
- `error_recovery.py` 是唯一带 `_select_fix_model_by_error_type` 模型降级的修复器

### 2. 演化目标

```
【近期】静态验证补齐：Java/Go 语法检查（P0）
  ↓
【中期】职责收敛：CodeValidator vs CrossValidator 边界、修复链分工
  ↓
【长期】校验化：修复记录全覆盖、核心注释校验
```

### 3. 分阶段路径

**阶段一（近 1 迭代）：静态验证补齐**
- `code_validator.validate_single_file` 扩展非 Python 分支：`javac -proc:none` / `gofmt -e` / `go vet` 无依赖静态检查
- 与 test_runner 收敛同步落地，保证 Spring Boot 项目语法级校验不断档
- 验收：Java/Go 文件语法错误被静态验证捕获

**阶段二（近 2 迭代）：职责收敛**
- `CodeValidator`（单文件静态）vs `CrossValidator`（双模型对抗）职责边界文档化，重复实现合并
- `error_recovery` 与 `refinement_loop` 分工明确：refinement 用于精炼、error_recovery 用于错误分类修复
- fallback 链解析统一：`error_recovery` 与 `dynamic_model_router` 共用一套配置加载
- `consistency_checker`（孤儿）删除候选，全库引用扫描确认零引用后归档
- 验收：无重复验证实现，孤儿标记明确

**阶段三（中期）：修复记录全覆盖**
- `record_fix` 在所有修复路径（refinement/error_recovery/cross_validator）触发（承接 AGENT-ENGINE.md 5.1 学习闭环）
- 修复记录进入 `feedback_learner`，错误聚类驱动预防 prompt
- 验收：学习数据覆盖率 90%+ 修复路径

### 4. 风险与依赖

| 风险 | 应对 |
|------|------|
| javac/gofmt 依赖 JDK/Go 环境 | 无依赖编译（-proc:none），缺失时降级跳过并告警 |
| 双验证合并破坏主路径 | 合并前跑 1506 单测 + 413 E2E，保留接口签名 |
| record_fix 覆盖改动面大 | 分批接入三条路径，每批回归验证 |

---

## 验收标准汇总（批2）

| 子系统 | 阶段一验收 | 阶段二验收 |
|--------|-----------|-----------|
| A5 角色体系 | grep 确认角色模块均有真实调用方或废弃标记 | AgentRole 接口可注册新角色，无需改引擎源码 |
| A6 模型路由 | 切默认/免费模型重启保留且对 Agent 生效 | 图片模型可路由，窗口感知生效，router <800 行 |
| A7 验证修复 | Java/Go 语法错误被捕获 | 无重复验证实现，修复记录入学习闭环 |
