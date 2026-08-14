# Agent 子系统详细推演 · 批1：主链路

> 版本：v1.3 | 日期：2026-08-05 | 范围：A1 编排核心 + A2 生成路径 + A3 需求分析（3 个子系统，28 模块）
>
> 本文是 `TASKS.md` A 组演化路径清单的**详细推演版**，格式对齐 [PPT-FEATURE.md](PPT-FEATURE.md)：现状基线 → 演化目标 → 分阶段路径 → 验收标准 → 风险依赖。原则：**先修 Bug、再拆分止血、再收敛统一、后智能增强**。
>
> **v1.3（2026-08-05 第六次推演）**：演化拆分建议归属修正——A1 阶段二「`_select_engineer`/`_recover_invalid_content`/`refine` 重复定义」改为「近似重复」：`_select_engineer` 仅定义于 `orchestrator_files.py:577`（spec_first 经继承调用，非重复）；`_recover_invalid_content_orchestator`（orchestrator_files:584）与 `_recover_invalid_content`（spec_first:2003）为两套不同名同类实现需归一；`refine` 仅定义于 `refinement_loop.py:94`。A2 阶段一 `file_generator` 子模块移除 `_select_engineer`（归属 FilesMixin 不随 spec_first 拆分）；`_initialize_components` 注明实际定义于 mixin.py:39。
>
> **v1.2（2026-08-05 实测复核）**：用例数更新 1376→**1506** 单测、409→**413** E2E（对齐 AGENT-ENGINE v1.9 实测基线）；A2/A3 全部模块行数复核精确（traditional 427 / incremental_generate 85 / evaluate_mixin 351 / feature_extractor 37 / coverage_checker 61 / mixin 146 / A3 十模块 108-202）；`mixin.py` 经 :17-24 汇总导入 8 个 Mixin（coverage_checker/feature_extractor/error_recovery/traditional/spec_first/incremental_generate/incremental_modify/evaluate_mixin）实测成立；行号校正——`_try_react_auto_fix` 定义在 `error_recovery.py:9`（原写 :12），`_run_dynamic_tests`/`_try_react_auto_fix` 的 traditional 调用行为 **:294/:297**（原写 :295/:298）；`generate_with_spec_first`:28 / `_generate_with_dynamic_topology`:853 复核精确。
>
> **v1.1（2026-08-04 实测复核）**：tracing 接线 6→11 处、orchestrator_progress 引用 3→8 处、`_run_dynamic_tests`/`_try_react_auto_fix` 定义归属修正（orchestrator_testing.py:19 / error_recovery.py:9）、coverage_checker 接线由「待确认」改为「已接线」。

## 总览

| 子系统 | 模块数 | 关键现状 | 代表演化点 |
|--------|--------|---------|-----------|
| A1 编排核心 | 8 | OrchestratorAgent 6 层 Mixin，自身仅 138 行 | SharedContext 消除间接导入（P1） |
| A2 生成路径 | 10 | spec_first 2383 行单文件主路径 | spec_first 拆分（P1）、traditional 删除（P1） |
| A3 需求分析 | 10 | layer2 向量检索因 faiss 缺失降级关键词 | faiss 安装（P0） |

---

## A1. 编排核心（8 模块）

### 1. 现状基线

| 模块 | 行数 | 职责 |
|------|------|------|
| `orchestrator.py` | 138 | `OrchestratorAgent` Mixin 聚合入口，`__init__` 14 个参数，无业务方法 |
| `orchestrator_files.py` | 888 | `FilesMixin`：`_generate_files_small_project`/`_generate_files_by_dep_layers`/`_generate_single_file`/`_select_engineer`/`_recover_invalid_content_orchestator`/`_apply_patches_incremental` |
| `orchestrator_utils.py` | 410 | `UtilsMixin` 通用工具 |
| `orchestrator_progress.py` | 568 | `GenerationProgress`/`CostTracker`/`ProgressMixin`，被 orchestrator_testing/orchestrator/incremental_generate 引用 |
| `multi_model_agent.py` | 251 | `MultiModelAgent` Router/Planner/Executor/Reviewer 体系，`process` 唯一入口 |
| `shared_context.py` | 337 | `FileArtifact`/`SpecArtifact`/`GenerationPhase`/`SharedContext`（指标/阶段/spec/文件注册载体） |
| `session_manager.py` | 582 | `SessionManager`：create/resume/update_file_status/pause/complete/cancel/cleanup |
| `tracing.py` | 246 | OTel 追踪，已接线 code_reviewer/specialist_base/mixin/evaluate_mixin/traditional_generate |

**实测确认的接线状态（2026-08-04）**
- `OrchestratorAgent` 继承顺序：`ProgressMixin, GenerationMixin, FilesMixin, TestingMixin, UtilsMixin, RequirementAssociationMixin`，6 层叠加
- `tracing.py` 已真实接线（**11 处** `from app.agent.tracing import traced`：requirements_mixin/frontend_engineer/session_manager/backend_engineer/test_runner/architect/traditional_generate/generation_mixin/evaluate_mixin/specialist_base/code_reviewer），非死代码
- `orchestrator_progress.py` 被 **8 处**生产引用（`PROGRESS_LABELS`/`MAX_CONTENT_FOR_CONTEXT`：orchestrator_files/incremental_modify/traditional_generate/mixin/spec_first/incremental_generate/orchestrator/orchestrator_testing）
- **关键缺陷**：`incremental_modify.py:97` 通过 `from app.agent.orchestrator_generation.spec_first_generate import SharedContext` 间接 re-export 导入，而 `spec_first_generate.py:12` 从 `app.agent.shared_context` 导入——脆弱依赖链（spec_first 改名/重构即断）

### 2. 演化目标

```
【近期】消除脆弱依赖：SharedContext 改为直接导入
  ↓
【中期】收敛编排：Mixin 职责边界文档化、multi_model_agent 归一
  ↓
【长期】协议化：进度/成本/tracing 打通端到端可观测
```

### 3. 分阶段路径

**阶段一（近 1 迭代）：依赖修正**
- `incremental_modify.py:97` 改从 `app.agent.shared_context` 直接导入 `SharedContext`，消除对 spec_first 的间接依赖
- 全局 grep 确认无其他模块经 spec_first 间接 re-export 共享符号
- 验收：grep 无 `spec_first_generate import SharedContext` 间接引用；单测通过

**阶段二（近 2 迭代）：Mixin 职责收敛**
- 梳理 6 个 Mixin 的方法归属，消除跨 Mixin 近似重复的实现：`_select_engineer` 仅定义于 orchestrator_files.py:577（spec_first 经继承调用，非重复定义）；`_recover_invalid_content_orchestator`（orchestrator_files.py:584）与 `_recover_invalid_content`（spec_first_generate.py:2003）两套不同名同类实现需归一；`refine` 收敛到 refinement_loop.py:94 单一入口
- Mixin 边界写入模块 docstring（Progress=进度/成本、Files=文件编辑、Testing=验证、Requirement=需求关联）
- 验收：每个 Mixin 职责单一，无同名方法多处定义（除有意 override）

**阶段三（中期）：编排体系归一**
- `multi_model_agent.py`（Router/Planner/Executor/Reviewer）与 `OrchestratorAgent` 两套编排收敛为统一模型（承接 AGENT-ENGINE.md 6.1 角色插件化）
- 进度/成本追踪与 `tracing.py` 打通：CostTracker 数据进入可观测性报表
- 验收：单一编排入口，成本数据可追溯

**阶段四（长期）：端到端可观测**
- `session_manager.py` 状态与前端恢复完整一致，断点续作不丢进度
- tracing trace_id 关联到前端界面（承接 AGENT-FRONTEND 阶段五）
- 验收：一次生成全程可追踪（trace_id 贯穿后端→前端）

### 4. 风险与依赖

| 风险 | 应对 |
|------|------|
| 消除间接导入破坏增量路径 | 改导入后跑 incremental 单测回归 |
| Mixin 收敛改变 MRO 行为 | 小步提交，依赖 git 快照可回滚 |
| 两套编排体系归一周期长 | 阶段三前保持独立稳定，以接口适配渐进接入 |

---

## A2. 生成路径（10 模块）

### 1. 现状基线

| 模块 | 行数 | 职责 | 生产状态 |
|------|------|------|---------|
| `spec_first_generate.py` | 2383 | 主路径：`generate_with_spec_first`(28) → `_generate_with_dynamic_topology`(853) → 语法验证/类型推断/重试/沙箱修复/完整性验证/重构 | ✅ 主路径 |
| `traditional_generate.py` | 427 | 旧路径，动态测试 `_run_dynamic_tests` 调用 + `_try_react_auto_fix` 调用 | ⚠️ 并存 |
| `incremental_modify.py` | 1028 | 增量修改，:97 经 spec_first 间接导入 SharedContext | ✅ |
| `incremental_generate.py` | 85 | 增量生成，薄包装引用 PROGRESS_LABELS | ✅ |
| `evaluate_mixin.py` | 351 | 需求/架构/风险/总评评估，已接 tracing | ✅ |
| `feature_extractor.py` | 37 | RAG 特征提取，仅 traditional 调用 | ⚠️ spec-first 未调用 |
| `coverage_checker.py` | 61 | 覆盖率检查 | ✅ 已接线（mixin.py import check_requirement_coverage） |
| `orchestrator_generation/error_recovery.py` | 33 | 薄包装（ErrorRecoveryMixin，区别于顶层 797 行 error_recovery.py） | ✅ |
| `mixin.py` | 146 | Mixin 汇总导入，已接 tracing | ✅ |

**实测确认（2026-08-04）**
- 主路径生成链：`generate_with_spec_first` → `_generate_with_dynamic_topology`（动态拓扑分层生成）→ 每文件 ① 双模型对抗(可选) → ② RefinementLoop → ③ 内容质量校验 → ④ 写入前语法验证 → 原子写入 → 项目级完整性 → 全量验证
- 修复链全为静态验证驱动，**0 次动态测试**（spec_first 无任何 test_runner/`_run_dynamic_tests` 调用，AGENT-ENGINE.md 9.8 已确认）
- `_run_dynamic_tests` 定义于 `orchestrator_testing.py:19`（TestingMixin），仅 traditional（:294）与 error_recovery（:29）调用；`_try_react_auto_fix` 定义于 `error_recovery.py:9`（ErrorRecoveryMixin），traditional:297 调用——**动态测试只在 traditional 修复链出现**

### 2. 演化目标

```
【近期】拆分止血：spec_first 2383 行拆 7 子模块、incremental_modify 拆分
  ↓
【中期】路径收敛：删除 traditional、消除间接导入、RAG 写入打通
  ↓
【长期】增量路径完整：增量生成与全量生成共用能力
```

### 3. 分阶段路径

**阶段一（近 1-2 迭代）：拆分**
- `spec_first_generate.py` 按职责拆 7 子模块（参照 AGENT-ENGINE.md 3.1）：
  - `spec_initializer.py`：`_initialize_components` 组件初始化
  - `spec_pipeline.py`：OpenAPI→types→db_schema→config 规范管线
  - `file_generator.py`：`generate_single_file`/工程师选择（`_select_engineer` 归属 orchestrator_files FilesMixin:577，spec_first 经继承调用，不随 spec_first 拆分）
  - `content_recovery.py`：`_recover_invalid_content`/重试
  - `file_refactor.py`：`refactor_file`
  - `sandbox_validation.py`：`_fix_sandbox_errors`
  - `file_type_inference.py`：`_infer_unknown_file_types`
  - 骨架保留 `generate_with_spec_first` + `_generate_with_dynamic_topology` 编排（<400 行）
- `incremental_modify.py`（1028）拆变更分析/增量生成/依赖图增量更新
- 验收：各模块 <800 行，对外 Mixin 接口不变，1506 单测 + 413 E2E 通过

**阶段二（近 2 迭代）：路径收敛**
- 删除 `traditional_generate.py`：移除 `_run_dynamic_tests`，ReAct 修复输入改接静态验证结果
- `incremental_modify.py:97` 改为直接导入 SharedContext
- `spec_first_generate.py` 收尾调用 `feature_extractor.extract_and_save_feature_list`（RAG 数据源覆盖主路径）
- 验收：grep 无 traditional 残留；spec-first 生成完成写 FAISS 索引

**阶段三（中期）：能力复用**
- `coverage_checker` 已确认接线（mixin.py 经 `check_requirement_coverage` 调用），与项目级完整性校验共用，无需废弃处置
- 增量生成/修改路径与全量路径共用评估/验证能力（evaluate_mixin 收敛到统一评估入口）
- 验收：增量与全量共用能力层，无重复实现

### 4. 风险与依赖

| 风险 | 应对 |
|------|------|
| spec_first 拆分破坏主路径 | 每步拆分跑端点冒烟 + E2E 回归，Mixin re-export 保持可用 |
| 删除 traditional 影响 ReAct 修复 | ReAct 输入改接静态验证（AGENT-ENGINE 2.1 收敛顺序第 3 步） |
| feature_extractor 写入引入失败面 | 写入失败不阻断主生成，记录告警 |
| 依赖 faiss（A11 阶段一） | RAG 写入前 faiss 依赖先装（A11 P0 前置） |

---

## A3. 需求分析（10 模块）

### 1. 现状基线

| 模块 | 行数 | 职责 |
|------|------|------|
| `layer1_template.py` | 108 | `layer1_cross_domain_template` 跨域模板匹配 + `compute_template_confidence` |
| `layer2_semantic.py` | 122 | `layer2_semantic_match` 向量检索（faiss 缺失 → `layer2_keyword_fallback` 关键词降级） |
| `layer3_dual_model.py` | 128 | `layer3_dual_model_deep` 双模型深析 + `merge_dual_model_results` |
| `domain_detection.py` | 40 | `_detect_domains`/`_detect_domain` 关键词域检测 |
| `devil_advocate.py` | 83 | `devil_advocate_review` 对抗式需求审查 |
| `data_models.py` | 31 | `AssociationItem`/`AssociationResult` |
| `feedback_tracker.py` | 106 | `AssociationFeedbackTracker` 反馈追踪 |
| `constants.py` | 51 | `_load_dual_models_from_config` 双模型配置 |
| `llm_prompts.py` | 122 | `llm_system_prompt`/`build_llm_prompt`/`parse_llm_response`/`summarize_items` |
| `orchestrator_requirements/mixin.py` | 202 | `RequirementAssociationMixin` 汇总入口 |

**实测确认（2026-08-02）**
- 三层结构：layer1（模板匹配）→ layer2（语义检索）→ layer3（双模型深析），经 `RequirementAssociationMixin` 暴露给 OrchestratorAgent
- **layer2 向量检索从未生效**：`layer2_semantic_match` 因 faiss 未安装走 `layer2_keyword_fallback`（AGENT-ENGINE.md 1.3 实测确认）

### 2. 演化目标

```
【近期】检索生效：faiss 安装，layer2 向量分支启用
  ↓
【中期】质量闭环：三层结果质量回检、反馈入学习
  ↓
【长期】智能增强：域识别 LLM 化、对抗审查按需触发
```

### 3. 分阶段路径

**阶段一（近 1 迭代）：检索修复**
- faiss-cpu 加入 `configs/requirements.txt`，`vector_index.py` 的 `except ImportError` 改为显式告警 + 依赖登记（承接 A11 P0）
- 补 `layer2_semantic` 测试断言走向量分支
- 验收：layer2_semantic_match 真实调用 FAISS，关键词仅作 fallback

**阶段二（近 2 迭代）：质量闭环**
- layer2 检索结果做相关性阈值过滤 + 去重（避免低分项目污染需求分析）
- layer3 双模型 merge 增加一致性判定与置信度阈值
- `feedback_tracker` 反馈数据接入 `feedback_learner`，优化关联注入质量
- 验收：低分项目不进入需求注入，双模型分歧有明确仲裁

**阶段三（中期）：智能增强**
- `domain_detection` 从关键词规则升级为 LLM/模板辅助域识别
- `devil_advocate` 对抗审查按复杂度触发（复杂需求才执行，避免全量延迟）
- 需求数据模型（`data_models.py`）与 spec/PPT 需求结构统一
- 验收：域识别准确率提升，对抗审查有触发策略

### 4. 风险与依赖

| 风险 | 应对 |
|------|------|
| faiss 安装失败 | faiss-cpu wheel 无编译依赖，锁版本入 requirements-test |
| 检索结果污染需求 | 相关性过滤 + 灰度对比关键词/向量两条路径命中质量 |
| 双模型 merge 不稳定 | 一致性判定 + 阈值，失败回退单模型 |
| 依赖 embedding API 可用性 | AiCodeUtil 已有内存+磁盘缓存，可复用 |

---

## 验收标准汇总（批1）

| 子系统 | 阶段一验收 | 阶段二验收 |
|--------|-----------|-----------|
| A1 编排核心 | grep 无间接 re-export 依赖 | Mixin 职责单一，无重复同名方法 |
| A2 生成路径 | 模块 <800 行，E2E 通过 | 无 traditional 残留，spec-first 写 FAISS |
| A3 需求分析 | layer2 走真实向量检索 | 检索过滤去重生效，反馈入学习闭环 |
