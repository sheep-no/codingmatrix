# TraditionalGenerate 生成链深扫（traditional_generate.py 427 行 + feature_extractor.py 37 行 + coverage_checker.py 61 行）

> 第一百零四轮推演 | 2026-08-17 | 定位：传统生成链（非 spec-first）主编排——从需求联想增强、架构设计、分批规划、成本审批到文件生成/验证/测试/记忆/快照的完整收尾链，及其功能清单提取与需求覆盖率检查两个收尾步骤

## 1. 模块定位

`TraditionalGenerateMixin._generate_traditional`（traditional_generate.py:19-379）是传统生成模式的唯一入口（mixin.py:123 `generate()` 中 `spec_first=False` 分支），由 `GenerationMixin`（mixin.py:29）组合进 `OrchestratorAgent`。链路：缓存查找（spec_cache + embedding）→ 需求联想增强（OA1 消费方）→ 架构设计/分批规划 → 成本估算/审批 → 会话恢复/创建 → API 契约注入 → 依赖图分层 → 三路文件生成（增量/小项目/依赖分层）→ 完整性验证 → 静态验证 → 动态测试 → 记忆保存 → 缓存回写 → 功能清单提取 → 覆盖率检查 → 快照提交。

- `_validate_project_completeness_traditional`（:381-427）：按 file_plan 检查缺失/空/无效文件
- `feature_extractor.py`（37）：`extract_and_save_feature_list` 收尾写历史功能数据源（PM 详档 `extract_and_save` 消费方），≥15 项目触发模板萃取（TE 详档触发方）
- `coverage_checker.py`（61）：`check_requirement_coverage` 用联想项 functional 高置信项（≥0.7）对 file_plan+architecture 关键词匹配算覆盖率
- 宿主契约依赖：`self.architect/reviewer/spec_cache/session_manager/validator/cost_tracker/error_recovery` 等 20+ 属性（mixin.py:85-93 初始化）

**活跃模块**，调用链：

- `orchestrator_generation/mixin.py:123`：`generate()` 传统分支 → `_generate_traditional`
- `orchestrator_files.py`：`_generate_files_small_project`/`_generate_files_by_dep_layers` 文件生成（OF 详档）
- `orchestrator_utils.py:26/:306/:339`：`_cache_review_gate`/`_estimate_generation_cost`/`_git_save_snapshot`（OU 详档）
- `project_metadata.py:57`：`extract_and_save` 功能清单入库（PM 详档）
- 下游消费：Layer 2 联想（orchestrator_requirements）读 project_metadata + 模板萃取（TE 详档）

### 依赖链

| 方向 | 模块/位置 | 说明 |
|------|-----------|------|
| 上游 | `orchestrator_generation/mixin.py:39-99` | `_initialize_components` 初始化 complexity/architect/reviewer/validator 等 |
| 上游 | `orchestrator_requirements/mixin.py:30` | `_generate_requirement_associations` 需求联想（OA 详档） |
| 上游 | `orchestrator_utils.py` | 缓存闸门/成本估算/快照 |
| 上游 | `orchestrator_files.py` | 三路文件生成器 |
| 下游 | `project_metadata.py:57` | 功能清单写入（feature_extractor → extract_and_save） |
| 下游 | `template_extractor.py` | ≥15 项目触发模板萃取（feature_extractor:28） |
| 下游 | `layer2_semantic.py` | 历史功能数据消费（恒空降级） |
| 测试 | `tests/unit/test_v5_1_requirement_deep.py:85-120` | 仅 ProjectMetadata CRUD，extract_and_save 零用例 |

## 2. 深扫发现

### P2 项

- **TG1 [P2] `_extract_feature_list` prompt f-string 未转义花括号——功能清单提取恒 ValueError（实测）**——`project_metadata.py:99` 的 prompt f-string 内嵌 `{"features": [...]}` 模板（:107-108 裸 `{` 未转义 `{{`）→ 每次调用 `_extract_feature_list` 必然 `ValueError: Invalid format specifier`；实测空 dict 与非空 dict 均复现，且 prompt 构造在 try 块外（:99 vs try :122）不被捕获 → `extract_and_save` 中断不落库 → **传统链每轮收尾的功能清单提取从未成功执行过**。传统链收尾 `_extract_and_save_feature_list`（traditional_generate.py:326）每轮必触发，异常被 :329-330 捕获仅 logger.warning（非阻塞静默吞）。
- **TG2 [P2] `feature_extractor` 输入恒空——generated_files 无 content/code 键（全库确认）**——`feature_extractor.py:17-21` `gf.get("content", gf.get("code", ""))` 读取文件内容，但 `self.generated_files` 全部六处 append 结构均为 `{"path","description","success","size"}` 无 content 键（orchestrator_files.py:483-485/:825/:866、traditional_generate.py:228/:258）→ `files_dict` 恒空 → 即使修 TG1，LLM 也只凭空 file_summary（`_summarize_files` 空 dict → 空串）提取，文件内容信息从未传入——**输入侧与 prompt 侧双断**。
- **TG3 [P2] 历史功能数据源恒空 + 模板萃取永不触发（实测，级联影响）**——`data/vector_index/project_metadata.json` 实测不存在（`METADATA_PATH` 指向路径无文件），结合 TG1 恒定失败 → 项目从不入库 → `get_projects_by_domain` 恒空 → **模板萃取（≥15 项目）与 Layer 2 联想（≥50 项目）永不触发，TE 详档 TE1「手工模板被自动萃取覆盖」的触发前提实际不可达**（TE1/TE2/TE4 描述的缺陷被 TG1 前置阻断而休眠），Layer 2 关键词/语义联想恒静默降级（OA9）。
- **TG4 [P2] 完整性检查 `is_complete` 忽略空文件（全库确认）**——`_validate_project_completeness_traditional`（:381-427）`empty_files`（内容 <10 字符，:407-410）单独列出但 `is_complete = missing==0 and invalid==0`（:426）**不含 empty_files 判定**，且 :414 对 empty 文件跳过 invalid 检查 → 文件生成但内容为空仍判项目完成（TR1「存在≠正确」家族）。同时 missing 基于 `generated_files_dict`（:211-219 read 成功集合），read 异常（编码/IO）的文件静默 pass 也算缺失。
- **TG5 [P2] 缓存审查闸门异常/缺评审即放行（全库确认）**——`_cache_review_gate`（orchestrator_utils.py:26-47）`except Exception: 放行`（:44-45）+ `reviewer` 缺失 return True（:30-31）——缓存架构审查任何异常或未配置审查员都直接命中缓存复用；且只判 `risk_level == "high"`（:41）单一维度，`review_code` 返回 Dict（code_reviewer.py:57）`.get` 不抛错，medium/low 风险与审查失败无差别放行（DGV1 放行家族）。

### P3 项

- **TG6 [P3] 缓存命中时联想增强需求与缓存架构错配（全库确认）**——:55-56 用 `_association_result.enhanced_requirement` 覆盖 requirement，但 :60-63 缓存命中分支直接用 `cached.architecture`（旧版架构/文件计划）——增强需求进入 project_context（:182）与 `_cache_specs`（:306）回写，需求与架构错配（仅缓存路径）。
- **TG7 [P3] 静态验证失败仍报告 success=True（全库确认）**——:345 `success = errors==0 and test_results.get("success", True)`，test_results 默认 `{"success": True}`（:201）；:287-290 静态验证失败（`final_validation.is_valid=False`）时不跑测试 → test_results 恒 True → **整体 success 仅取决于 errors 列表**，静态验证失败不反映在最终结果（TR1「存在≠正确」家族）。
- **TG8 [P3] 完整性补充文件写盘后验证 dict 未更新（全库确认）**——:221-234 补充的 `__init__.py` 等写盘但 `generated_files_dict` 未加入 → 后续项目级沙箱验证（:270-275 `files=generated_files_dict`）与 `_validate_project_completeness_traditional` 用旧 dict，补充文件不在验证范围。
- **TG9 [P3] 覆盖率关键词子串匹配无词边界（全库确认）**——coverage_checker.py:45-46 `kw in combined_text` 子串匹配，功能项「订单」匹配「子订单管理」等子串误判已覆盖（BE1/FE1/PP8 子串家族）；且 `confirmed_items` 空时返回 `coverage_rate: 1.0`（:23）「零联想项 = 100% 覆盖」成功态谎报（MAR8 家族）。
- **TG10 [P3] 补缺失文件走 `_direct_llm_generate_file` 硬编码模型（全库确认）**——traditional_generate.py:250 补文件走 orchestrator_files.py:648 的 `_direct_llm_generate_file`（OF4 硬编码 DEFAULT_CODE_MODEL 不走 DMR/成本），传统链补全路径又一次消费该缺陷。

## 3. 演化方向

传统生成链收尾端（功能清单提取）是**历史数据积累的唯一写入口**，当前从输入到 prompt 双断：
- **修复 f-string（TG1，最高优先）**：`project_metadata.py:99-108` 的 `{"features": [...]}` 模板花括号转义为 `{{`——一处改动即激活整条历史数据写入链；同时把 prompt 构造移入 try 或单独校验。
- **修复输入侧（TG2）**：feature_extractor 改为从 `self.output_dir` 按 path 读文件内容（与完整性检查 :211-219 同模式），或 `_generate_single_file` 返回结构补 content 键。
- **数据源激活（TG3）**：TG1/TG2 修复后 `project_metadata.json` 开始积累，Layer 2 联想（≥50）与模板萃取（≥15）随之激活——需同步复核 TE1（自动覆盖手工模板）在数据源激活后的真实触发风险。
- **完整性语义（TG4）**：`is_complete` 纳入 empty_files；read 失败文件显式计入 missing。
- **闸门语义（TG5）**：缓存审查失败应「重新生成」而非放行；风险维度扩展。
- **结果语义（TG7/TG9）**：success 纳入静态验证结果；覆盖率空项时 `checked=False` 而非 1.0。

**修复优先级**：TG1（恒 ValueError）> TG2（输入恒空）> TG4（空文件=完成）> TG5（审查放行）> TG7 > TG9 > TG3（随 TG1/TG2 自动激活）> TG6 > TG8 > TG10。

## 4. 主线关联

- **「数据源写入端恒失效」主线**：TG1/TG2/TG3 组成完整链路——传统生成链每轮调用功能清单提取，但 prompt f-string 恒抛 ValueError（TG1）+ 输入恒空（TG2）→ 历史功能数据源（Layer 2 + 模板萃取）写入端从代码层面从未工作，`project_metadata.json` 恒空。这**反向修正 TE 详档**：TE1 的「手工模板被自动覆写」风险依赖数据源 ≥15 项目，而 TG1 使该前提不可达——缺陷被更上游的缺陷掩盖（「上游阻断式休眠」模式）。
- **「存在≠正确」家族**：TG4（空文件=完成）、TG7（静态验证失败 success=True）、TG9（零联想项=100% 覆盖）三处收尾判定都把「存在/无输出」当「正确」，与 TR1/DGV1/CV2 同族。
- **「放行兜底」家族**：TG5（缓存审查异常放行）与 DGV1（验证失败 passed=True）、EC3（分类失败兜底）同族——LLM 依赖路径的异常都倾向放行而非重试。
- **「子串假阳性」家族**：TG9 关键词匹配延续 BE1/FE1/PP8/DR6/CMP1 第 N 例。

## 5. 测试状态

**CRUD 单测、写入链零覆盖**——test_v5_1_requirement_deep.py:85-120 仅 3 用例测 `ProjectMetadataManager` CRUD（手工注入 `_projects` 后断言），`extract_and_save`/`_extract_feature_list` 全库零测试；`rg` 确认传统链（`_generate_traditional`/feature_extractor/coverage_checker）无任何测试文件引用。TG1 恒定 ValueError 可一次 `extract_and_save` 调用复现却无任何用例保护，历史数据写入链唯一行为的正确性完全依赖未被验证的实现。
