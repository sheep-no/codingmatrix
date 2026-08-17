# orchestrator_requirements 子包深扫（10 模块 1036 行）

> 第一百零三轮推演 | 2026-08-17 | 定位：需求联想流水线（领域模板 Layer 1 → 历史语义 Layer 2 → 双模型深度联想 Layer 3 → 魔鬼代言人反向审视）的编排 + 反馈追踪数据源

## 1. 模块定位

子包实现「需求联想」：给定用户需求与复杂度，产出可能遗漏的功能/架构/风险/决策联想项与增强需求文本。四层流水线由 `RequirementAssociationMixin._generate_requirement_associations`（mixin.py:30）编排，经 `asyncio.wait_for` 受 `TIME_BUDGET_SECONDS` 预算保护，`SKIP_COMPLEXITY_LEVELS`（simple/small）直接跳过。

- `__init__.py`（43）：统一导出（constants/data_models/feedback_tracker/mixin）
- `constants.py`（51）：`DOMAIN_TEMPLATES_DIR`/`SKIP_COMPLEXITY_LEVELS`/`TIME_BUDGET_SECONDS`/`CONFIDENCE_*`/`MIN_HISTORY_*`/`DUAL_MODEL_*`（模块加载期从 `data/agent_model_config.json` 经 `resolve_model_key` 读取）+ `DEVILS_ADVOCATE_MODEL` 硬编码
- `data_models.py`（31）：`AssociationItem`/`AssociationResult`
- `domain_detection.py`（40）：关键词打分判领域（`score>=2` 全收、`score>=1` 收前 2，取前 3）
- `layer1_template.py`（108）：读 `configs/domain_templates/{domain}.json` 的 core_modules/NFR/pitfalls/decisions 生成联想项，`compute_template_confidence` 关键词命中比例映射 0.5-1.0
- `layer2_semantic.py`（122）：FAISS 语义检索（`vi.total_count() >= MIN_VECTOR_RESULTS=5` 才启用）→ 失败降级关键词匹配（`pm.total_count() >= MIN_HISTORY_PROJECTS=50` 才启用，`similarity > 0.15`）
- `layer3_dual_model.py`（128）：A/B 双模型串行 `call_llm` + `parse_llm_response`，单模型成功降级 single、双空再走 `DUAL_MODEL_FALLBACK`、双成功 `merge_dual_model_results`（`content[:50]` 判同项）
- `devil_advocate.py`（83）：魔鬼代言人审视高置信项（`[:15]`），返回 challenges 独立列表
- `llm_prompts.py`（122）：系统 prompt / 组装 prompt / `parse_llm_response` 贪婪 JSON 提取 / `summarize_items`
- `feedback_tracker.py`（106）：`AssociationFeedbackTracker` sqlite 反馈存储（WAL + 写锁 + 90 天保留 + 2MB 上限清理）

**活跃模块**，调用链：

- `orchestrator.py:30/:41`：`OrchestratorAgent` 继承 `RequirementAssociationMixin`（宿主契约齐备：`_report_progress` orchestrator_progress.py:138 签名兼容 + `architect` 实例属性）
- `orchestrator_generation/{traditional_generate,spec_first_generate}.py:52/:57`、`evaluate_mixin.py:57`：主生成链调用 `_generate_requirement_associations`
- `api/v1/ai_agent/association_endpoints.py:40-47`：独立 API `POST /requirement-association` **单独 `RequirementAssociationMixin()` 实例化**
- `api/v1/ai_agent/association_endpoints.py:85/:104/:120`：confirm/helpfulness/stats 反馈端点

### 依赖链

| 方向 | 模块/位置 | 说明 |
|------|-----------|------|
| 上游 | `project_metadata.py` `ProjectMetadataManager` | Layer 2 历史项目数据源（PM 详档，语义/关键词检索 + 补查 feature_list） |
| 上游 | `configs/domain_templates/{domain}.json` | Layer 1 模板数据源（TE 详档写端） |
| 上游 | `app/agent/vector_index.py` | Layer 2 语义检索（VI 详档，embedding 四断） |
| 上游 | `app/utils` `call_llm` | Layer 3 + 魔鬼代言人直连 LLM（LCL1 家族） |
| 上游 | `app/agent/complexity.py` | endpoint 无复杂度时 `ComplexityAnalyzer` 计算（CMP 详档） |
| 下游 | `association_endpoints.py` | 联想/反馈/统计三组 API（唯一对外出口） |
| 依赖 | `constants.py:22-45` | `_load_dual_models_from_config` 模块加载期读 `data/agent_model_config.json` roles |
| 测试 | `tests/unit/test_requirement_association.py` | FakeMixin **手工补 `_report_progress` + `architect`**（掩盖宿主契约缺失） |

## 2. 深扫发现

### P2 项

- **OA1 [P2] requirement-association API 恒静默降级 skipped（实测）**——`association_endpoints.py:40-47` 单独 `RequirementAssociationMixin()` 实例化后调用 `_generate_requirement_associations`，而 `_association_pipeline` 第一步 `mixin.py:72 self._report_progress(...)` 需要宿主提供该方法——**mixin 自身不定义 `_report_progress`，endpoint 实例无宿主** → AttributeError → mixin.py:56-61 捕获 → 返回 `skipped=True`。实测：endpoint 同款调用（callback/_start_time/_current_phase 手工赋值后）→ `skipped=True, skip_reason='联想异常: ...no attribute _report_progress'`。即使补 `_report_progress`，mixin.py:101 `architect=self.architect` 也无此属性 → 再次降级。**全库唯一无宿主契约的调用路径**（OrchestratorAgent 主链路契约齐备正常，测试用 FakeMixin:39-40 手工补齐遮蔽了该缺口）——用户经 API 永远看不到联想项，返回 200 + skipped 静默失败。

- **OA2 [P2] 反馈记录链路三端全断（实测）**——① `association_endpoints.py:88` 调 `tracker.record_feedback(association_id, "accepted")`：**`record_feedback` 方法不存在**（feedback_tracker.py 仅 record_choice/record_helpfulness）→ AttributeError → confirm 端点 500；② `:105` `tracker.record_helpfulness(association_id, helpful)`：签名 `(session_id, requirement, helpfulness)` 需 3 参，传 2 参 → TypeError → helpfulness 端点 500（即使补参，int association_id 被当 session_id、bool helpful 被当 requirement，UPDATE 按错误键匹配）；③ `record_choice`（唯一正确写入方法）**全库零调用**——联想项选择反馈从未落库。实测 `hasattr(tracker, 'record_feedback')==False` + `record_helpfulness(123, True)` 抛 TypeError。

- **OA3 [P2] `parse_llm_response` 双 JSON 贪婪跨块 + 降级污染（实测）**——llm_prompts.py:55 `re.search(r'\{[\s\S]*\}', response)`（MAR5/EC3/PM1/TE3 同款）：LLM 输出含两段 JSON（如代码块 + 补充）时贪婪匹配跨块 → json.loads 抛 Extra data → :62-71 文本降级**把整块 JSON 原文当 functional item**。实测：两段合法 JSON 拼接 → 降级产物为 2 个 content 等于完整 JSON 串的伪功能项。且文本降级无过滤，实测非 JSON 响应时把 prompt 说明文字「你是架构顾问。」「请分析需求。」也当功能项（PM2 家族）。

- **OA8 [P2] `_cleanup` 超限删除量语义错位——超 2MB 即清空全表（全库确认）**——feedback_tracker.py:98-103 `db_size > MAX_DB_SIZE_BYTES` 时 `DELETE ... ORDER BY created_at ASC LIMIT db_size // 4`：**db_size 是字节数（page_count*page_size），db_size//4 ≈ 524288 当 LIMIT 行数**——反馈表 90 天内行数远小于 50 万，LIMIT 恒大于行数 → 一旦超过 2MB 首次 cleanup **删光全表**（保留期数据与超限清理语义颠倒）。且 `_cleanup` 在 `__init__`:37 每次实例化执行——endpoint 每请求 new tracker 都跑 DELETE + pragma 查询。

### P3 项

- **OA4 [P3] architect 缺失即静默空，无 fallback 提示**——layer3_dual_model.py:27-28 与 devil_advocate.py:14 在 `not architect` 时返回 `[]`，mixin 无任何标记。设计上「无架构师不调 LLM」的降级本合理，但 OA1 场景（endpoint 实例无 architect）正好命中，用户看到联想项仅剩 Layer 1/2 无解释。
- **OA5 [P3] merge key `content[:50]` 判同项 + 置信度地板/天花板硬编码**——layer3_dual_model.py:98/106 两模型同前缀不同细节被合并丢弃；both_agree `min(+0.1, 0.95)` / single `max(*0.95, 0.5)`（0.5 下限使单模型项置信度永不低于 0.5）。
- **OA6 [P3] `AssociationItem.devil_review` 死字段**——data_models.py:16 定义但全库无写入：`devil_advocate_review` 返回独立 challenges 列表（mixin.py:112-114 存 `result.devil_review_items`），审视不修正被质疑项置信度、不 merge 回 item——「反向审视」只展示不生效（SCT5 家族）。
- **OA7 [P3] 模型配置双轨**——`DEVILS_ADVOCATE_MODEL` 硬编码 `THUDM/GLM-Z1-9B-0414`（constants.py:47）vs `DUAL_MODEL_*` 从 `agent_model_config.json` roles 经 `resolve_model_key` 加载（:22-45，SCT6/DR3/TFC4/CMP2 家族）——同子包内两套模型来源，升级即漂移；且 `_load_dual_models_from_config` 模块加载期执行，配置缺失时静默用默认值。
- **OA9 [P3] Layer 2 数据门槛与萃取触发阈值不一致 + 静默降级**——layer2_semantic.py:65 `MIN_HISTORY_PROJECTS=50` 才启用关键词匹配，而模板萃取在 15 项目即触发（TE 详档）——联想的历史支撑比数据源萃取晚 35 个项目；低于门槛时 `logger.info` 后返回 `[]` 无 result 标记（PM2 静默家族）。

## 3. 演化方向

需求联想是「历史数据 → 新需求补全」的闭环输入端，当前最大缺陷在**对外契约断裂**：
- **宿主契约显式化（OA1，最高优先）**：mixin 将 `_report_progress`/`architect` 声明为依赖或提供默认实现（空 progress + 空 architect 时层 3/魔鬼代言人可跳过并标记 `llm_called=False`），endpoint 复用 `OrchestratorAgent` 实例或注入存根——结束「单独实例化恒降级」。
- **反馈链路接线（OA2）**：补 `record_feedback` 或改 confirm 走 `record_choice`；统一反馈键为 association_id/session_id 单一语义；`record_helpfulness` 签名对齐调用方。
- **解析加固（OA3）**：贪婪 `\{[\s\S]*\}` 换非贪婪/JSON 边界定位（EC3/PM1/TE3 同款修复）；文本降级过滤非功能行（JSON 串/说明文字）。
- **清理语义（OA8）**：LIMIT 改按行数百分比或先查 count；`_cleanup` 移出 `__init__` 或加频率闸（避免每请求 DELETE）。
- **契约收敛（OA6/OA7/OA9）**：魔鬼代言人结果 merge 回 item 并影响置信度；模型配置统一到 `agent_model_config.json`；Layer 2 门槛与萃取阈值对齐。

**修复优先级**：OA1（API 恒降级）> OA2（反馈全断）> OA3（解析污染）> OA8（清空全表）> OA6 > OA7 > OA9 > OA4 > OA5。

## 4. 主线关联

- **「已接线但契约缺失」反向实例**：OA1 与孤儿家族（SCT5/EC8）相反——mixin 已被 orchestrator 与 API 双路径接线，但独立 API 路径缺宿主契约恒降级，测试 FakeMixin 手工补齐掩盖缺口（TR2 家族：测试固化错误预期）。警示「接线 ≠ 契约完整」。
- **「失败兜底产生伪结果/丢弃」家族**：OA3（解析跨块降级把 JSON 原文当功能）与 PM2/EC3/DGV1/TE2 同族；OA4/OA9（静默空）与 DGV1 静默 passed、layer2 静默降级同族。
- **「双份/双轨」家族第 N 处**：OA7（模型配置双轨）+ OA2（反馈方法签名与调用三处不一致）延续 SCT6/DR3/TFC4/CMP2。
- **「写安全」家族**：OA8（超限清空全表）与 CS1/PM3/TE6 同属写入侧破坏数据，但方向是**清理逻辑自身把保留数据删空**。

## 5. 测试状态

**表层单测、契约盲区**——test_requirement_association.py 28 用例覆盖领域检测/Layer1/Layer2 门槛/解析/分类/增强文本，但全部 P2 项零用例：OA1 被 FakeMixin:39-40 手工补 `_report_progress`+`architect` 遮蔽（endpoint 场景无测试）；OA2 `record_feedback`/`record_helpfulness` 签名无断言；OA3 双 JSON 跨块未测（test_parse_json_in_text 只测单 JSON 前有文字）；OA8 清理超限删除无测试。最严重的 OA1 是「全库唯一路径」却由测试夹具掩盖——契约缺口在测试层被「恰好补上」而未暴露。
