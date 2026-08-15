# SharedContext 深扫（shared_context.py，337 行）

> 第九十四轮推演 | 2026-08-15 | 定位：多阶段生成链路的全局状态容器（规范/文件/依赖/阶段/指标），被新旧两条 spec-first 生成链部分消费

## 1. 模块定位

多阶段生成过程中的全局状态容器：维护需求、复杂度、架构设计、规范产物（SpecArtifact）、文件产物（FileArtifact）、依赖关系、生成阶段、错误警告、指标。**活跃生产模块**，消费方 4 处：

- `app/agent/orchestrator_generation/spec_first_generate.py`（主消费者，v4.8 新生成链）：`ctx = SharedContext(requirement, self.output_dir)`（:71），大量使用 `set_metric` / `save_file_content` / `get_file_content` / `save_spec` / `get_spec` / `add_error` / `get_summary` / `to_export_dict`
- `app/agent/spec_first_generator.py`（v4.7 旧 spec-first 生成器）：`__init__(context)`（:113），使用 `start_phase` / `complete_phase` / `save_spec` / `get_spec` / `add_error` / `add_warning`
- `app/agent/refinement_loop.py`：`__init__(context)`（:83），使用 `increment_fix_attempts`（:126）/ `get_spec` / `get_generated_files_summary`（:528）
- `app/agent/cross_validator.py`：`__init__(context)`（:103）仅存储 `self.context = context`（:104），**整模块不消费 context 任何字段**

### 依赖链

| 方向 | 模块/位置 | 说明 |
|------|-----------|------|
| 被消费 | `spec_first_generate.py:71/:163/:613/:635-843` | 主消费者：文件/规范/指标/序列化 |
| 被消费 | `spec_first_generator.py:113/:135-167/:274-532` | 阶段管理 + 规范读写 |
| 被消费 | `refinement_loop.py:83/:126/:321-528` | 修复计数 + 规范/文件摘要 |
| 仅注入 | `cross_validator.py:103-104` | 只存引用，零字段消费 |
| 未消费 | `register_file`（:168-185）/ `get_dependencies_for`（:237）/ `get_dependents_of`（:241）/ `get_generation_order`（:245-267）/ `get_phase_status`（:138）/ `update_file_review`（:209） | **生产零调用方**（全库确认） |
| 测试 | **零测试覆盖**（tests/ 无任何 shared_context 用例） | |

## 2. 深扫发现

### P2 项

- **SC1 [P2] 依赖管理整条死链（实测）**——`register_file` 全库零调用方 → `self.dependencies` 恒 `{}` → `get_dependencies_for` / `get_dependents_of` / `get_generation_order`（拓扑排序）全部恒空/退化。实测：只调 `save_file_content` 后 `dependencies={}`，`get_generation_order()` 返回纯注册序 `['app/api.py','app/b.py','app/a.py']`——**共享上下文声称的依赖图（docstring 第 9 条「依赖关系图」）从未被填充**。文件生成顺序实际由 topology_scheduler（TS 模块）+ dependency_graph 自己的 `get_generation_order`（dependency_graph.py:622）承担，本模块的依赖排序是重复死实现。
- **SC2 [P2] `save_file_content` 使 file_type 恒 "unknown" + depends_on 恒空（实测）**——未注册文件时 `save_file_content` 建 `FileArtifact(file_type="unknown", depends_on=[])`（:193-200），且 `register_file` 是唯一写 depends_on 的入口（死代码 SC1）→ **主路径 spec_first_generate:613 直接 `ctx.save_file_content(file_path, content, model_name)` 不传 file_type** → 所有经该路径的 `FileArtifact.file_type` 恒 "unknown"、`depends_on` 恒 `[]`（实测确认）。而生成链真正的文件类型判断走 `file_node.file_type`（dependency_graph 节点，spec_first_generate:341/:902）——**同一文件类型信息双轨：dependency_graph 节点有值、shared_context 的 FileArtifact 全 unknown**，共享上下文的 file_type 字段主路径从未被真实填充。
- **SC3 [P2] `session_id` 秒级冲突（实测）**——`datetime.now().strftime("%Y%m%d_%H%M%S")`（:76）秒级精度，同秒创建多个 SharedContext 实例 `session_id` 相同（实测 c2 与 c3 相同）。session_id 用于日志事件前缀（:337）与序列化标识（:283/:301）——**同秒多实例日志/导出无法区分**（SM9 家族）。

### P3 项

- **SC4 [P3] `GenerationPhase.files_generated` 恒 0 死字段（实测）**——`start_phase` 收 `files_total`（:117）但 `complete_phase`（:127-136）从不更新 `files_generated` → 阶段完成后 `files_generated=0, files_total=5`（实测确认）。`get_summary` 用自己的 `files_count`/`files_generated` 计数（:291-292），`phase.files_generated` 字段无人消费。
- **SC5 [P3] 两个 summary 截断无标记**——`get_all_specs_summary` 的 `json.dumps(...)[:500]`（:162）、`get_generated_files_summary` 的 `content[:300]`（:231）静默截断。二者都是注入生成 prompt 的内容（refinement_loop:528 消费后者），截断后内容不完整零提示（JP2/TR2 家族）。
- **SC6 [P3] `to_export_dict` 不含文件内容，与 docstring 承诺不符（实测）**——docstring「导出完整的上下文字典（用于保存或调试）」（:298），但 files 序列化只含元数据（file_type/model/order/depends_on/validation/...）**不含 content**（:309-320）——实测导出字典的 files 条目无 content 键。该导出被 spec_first_generate:837 用作 `context_full`，**用于「保存」时无法还原文件内容**。
- **SC7 [P3] 五个方法生产零消费方**——`update_file_review`（:209）、`get_phase_status`（:138）、`get_dependencies_for`（:237）、`get_dependents_of`（:241）、`get_generation_order`（:245）全库无调用方。共享上下文的部分方法族未接线（与 GC6/SCT5 同族，方法级）。
- **SC8 [P3] 新旧两条生成链部分重叠消费同一上下文**——`spec_first_generator`（v4.7）用阶段/规范 API（start_phase/save_spec/get_spec），`spec_first_generate`（v4.8）用文件/metrics API（save_file_content/set_metric/to_export_dict），`cross_validator` 只注入不消费——同一上下文被三处不同方式使用，`save_spec` 等规范 API 在两链间共享但文件 API 各自写入（SC2 的 unknown 只影响新链）。多实现并存（AGM3 家族）。

## 3. 演化方向

共享上下文是 spec-first 链的全局状态容器，**文件/依赖子系统的核心数据结构实际未被主路径正确填充**：
- **依赖图（SC1）**：shared_context 的依赖管理（register_file + dependencies + 拓扑排序）整条死链，而实际排序由 topology_scheduler 和 dependency_graph 承担——**本模块的依赖部分是重复死实现**，方向是删除或与 dependency_graph 统一（dependency_graph 有完整节点模型，shared_context 的 `Dict[str,List[str]]` 简化版无生存价值）。
- **文件元数据（SC2）**：`file_type` 恒 unknown 暴露「FileArtifact 是设计完整但主路径不填充」——真正类型在 dependency_graph 节点。若共享上下文仅作内容缓存（spec_first_generate 用 `ctx.files.keys()` / `get_file_content`），FileArtifact 的 file_type/depends_on/validation/review 字段大量闲置。
- **标识与序列化（SC3/SC6）**：秒级 session_id 冲突 + 导出不含 content——序列化/日志的标识与完整性均有缺口。
- **消费面分裂（SC8）**：新旧两条链 + cross_validator 三处使用方式不同，是「同一能力多实现/多入口」收敛对象。

**修复优先级**：SC3（session_id 冲突，低改造成本高收益）> SC6（导出完整性）> SC1/SC2（依赖与文件元数据死链，需先决定 shared_context 与 dependency_graph 的边界）> SC5/SC4/SC7/SC8（设计瑕疵）。

## 4. 主线关联

- **「能力未接线」家族**：SC1（依赖管理死链）、SC7（五方法零消费）与 GC6/SCT5/UPL1 同族——本模块是**活跃容器内的死方法族**（容器被消费但部分能力未接线）。
- **「同一能力双实现」主线**：SC1 与 dependency_graph.get_generation_order（dependency_graph.py:622，活跃）——两处拓扑排序实现；SC2 与 dependency_graph.file_node.file_type——同一文件类型双轨。shared_context 是 spec-first 链的「轻量旧容器」，与 dependency_graph 的「重型新模型」并存。
- **「报告≠实际」家族**：SC6（导出承诺完整实际无 content）+ SC4（files_generated 恒 0）+ SC5（截断无标记）——序列化/计数/摘要层的语义失真（OP1/TR1 同族）。
- **标识冲突家族**：SC3 与 MEM6/SM9（秒级 session_id 冲突）同族。

## 5. 测试状态

**零测试覆盖**——tests/ 无任何 shared_context 用例。SC1-SC6 全部实测可复现但无用例保护。作为 spec-first 链两代生成器的公共状态容器，其依赖图、文件元数据、序列化完整性均无回归保护。
