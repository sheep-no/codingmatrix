# OrchestratorUtils 演化深扫文档

> 版本：v0.1 | 扫描日期：2026-08-09 | 状态：已完成
> 归属：Agent 大系统 / 支撑模块（编排工具 Mixin）
> 路径：app/agent/orchestrator_utils.py（410 行）
> 索引：[TASKS.md](../TASKS.md)

## 1. 模块作用与功能

编排器辅助工具集：`UtilsMixin` 提供文件计划校验、项目画像、分层、缓存规格、修复学习、审批等待、API 一致性检查、记忆、patch LLM 调用、成本估算、git 快照等 16 个方法——是 OrchestratorAgent 的横切工具方法簇，无独立状态。

- **核心类**：`UtilsMixin`（:14）。无数据类、无全局状态、无模块级单例。
- **方法族**：`_is_anti_pattern`（:16）、`_cache_review_gate`（:26）、`_select_dynamic_model`（:49）、`_validate_file_plan`（:55）、`_profile_project`（:103）、`_compute_layers`（:123）、`_cache_specs`（:133）、`_record_learning_data`（:163）、`_wait_for_approval`（:194）、`_should_check_api_consistency`（:209）、`_check_and_report_api_issues`（:217）、`_save_to_memory`（:270）、`_call_llm_for_patch`（:296）、`_estimate_generation_cost`（:306）、`_git_save_snapshot`（:339）。

## 2. 依赖与被依赖

- **生产使用方**（1 处）：orchestrator.py:29 `from app.agent.orchestrator_utils import UtilsMixin`（OrchestratorAgent 主类继承）。
- **依赖的外部对象**：feedback_learner（私有 `_fix_patterns`）、reviewer（CodeReviewer）、spec_cache、complexity、approval_callback、api_contract_checker、memory_enabled/conversation_memory/knowledge_memory、backend_engineer/architect、snapshot_mgr、error_recovery、model_assignment——全部经宿主 OrchestratorAgent 注入，**mixin 不可独立实例化**。
- **跨模块引用**：dynamic_model_router.get_dynamic_router（:50 延迟导入）、project_profiler.ProjectProfiler/detect_project_language（:9）、api_contract_checker.check_single_file_consistency、memory.MemoryEntry（:275 延迟导入）。
- **测试覆盖**：tests/unit 无任何 orchestrator_utils 测试（零测试，mixin 依赖宿主属性不可独立单测）。

## 3. 已探明 Bug

### OU1 [P2] 成本估算体系分裂 + estimated_files 不影响估算（CEC7 详化）

- **Bug 代码**：

```python
# :306-337 - 按 complexity.level 查静态表，token/cost 与文件数、架构内容完全脱节
def _estimate_generation_cost(self, architecture, file_plan):
    estimated_files = len(file_plan)          # :307 只算不进计算
    level = self.complexity.level.value if self.complexity else "unknown"
    cost_estimates = {"simple": {...}, "small": {...}, "medium": {"tokens": 45000, "cost_usd": 0.045}, ...}
    estimate = cost_estimates.get(level, cost_estimates["medium"])   # :318 与文件数无关
```

- **根因**：估算完全由 level 决定，`estimated_files`（:307）只塞进返回 dict（:336）不影响计算——30 文件的 medium 与 5 文件的 medium 成本相同，无内容/文件维度。与 CEC7（complexity `$0.001/1K` vs 按 level 查表）同源，本方法是「审批实际使用的后者」。
- **影响**：成本审批与实际生成规模脱节，大项目低估小项目高估；两套成本体系并存（CEC7）。

### OU2 [P2] `_validate_file_plan` 反斜杠死分支 + UTF-8 路径全拒

- **Bug 代码**：

```python
# :62 - 正则不包含反斜杠 → 反斜杠路径在此被拒
if re.search(r'[^a-zA-Z0-9_\-./]', path):
    self.warnings.append(f"跳过非法路径: {path}"); continue
depth = path.count('/') + path.count('\\')   # :66 - 永远执行不到 '\\' 分支
if path.startswith('/') or path.startswith('\\'):   # :71 - 同样死分支
```

- **根因**：:62 正则字符类不含 `\\` → 含反斜杠路径先被拒，:66 的 `count('\\')` 与 :71 的 `startswith('\\')` 归一化分支永远不执行（死代码）。且字符类不允许任何非 ASCII → **UTF-8 中文文件名路径全部被跳**（warnings「跳过非法路径」）。
- **影响**：中文项目/Windows 风格路径的文件计划被整体过滤；死分支误导后续维护。

### OU3 [P2] `_check_and_report_api_issues` 每文件事件全量 rglob 读对端（AC6 位置确认）

- **Bug 代码**：

```python
# :225-231 - 前端分支每次检查都 rglob 全项目 .py 并 read_text
if is_frontend:
    backend_files = {}
    for py_file in self.output_dir.rglob('*.py'):
        if '__pycache__' not in str(py_file):
            backend_files[str(py_file.relative_to(self.output_dir))] = py_file.read_text()
# :240-245 - 后端分支同样 rglob 全部前端文件
```

- **根因**：对端文件集每次调用重新构建，无缓存。生成 N 个前端文件 → N 次全量后端扫描，O(N×M) 文件读取。
- **影响**：**与 api_contract_checker.md AC6 同一实码（orchestrator_utils.py:227）**，此处为位置确认。项目文件多时每次写文件事件触发全量扫描。
- **验证方式**：代码级结论。

### OU4 [P2] `_record_learning_data` 学习数据空样本：学不到「怎么修的」

- **Bug 代码**：

```python
# :183-192 - original/fixed 内容全空，只有 error_message
self.feedback_learner.record_fix(
    file_path=fix_attempt.file_path,
    file_type="python",          # :185 硬编码，无论真实语言
    original_content="",         # :186
    fixed_content="",            # :187
    errors={"validation_error": [fix_attempt.error_message]},
    ...
)
```

- **根因**：记录修复学习时不含样本内容（original/fixed 恒空），只记错误消息与 success。strategy_learner 侧无法从样本学到修复模式（无「输入→正确输出」对）。
- **影响**：反馈学习数据空洞，learning 闭环的「修复模式提取」无内容可学；硬编码 file_type="python" 使非 Python 项目数据错标。

### OU5 [P2] `_is_anti_pattern` 跨模块访问私有 `_fix_patterns`

- **Bug 代码**：

```python
# :16-24 - 直接迭代宿主注入对象的私有 dict
if not self.feedback_learner:
    return False
for pattern in self.feedback_learner._fix_patterns.values():
    if pattern.is_anti_pattern() and pattern.error_pattern:
```

- **根因**：UtilsMixin 通过宿主注入的 feedback_learner 直接访问其私有 `_fix_patterns` 属性并依赖 pattern 对象的方法/属性（is_anti_pattern/error_pattern/error_type/failure_reason），绕过反馈学习器封装。
- **影响**：feedback_learner 内部结构变更即破坏此处；契约隐式（依赖对象方法而非公开接口）。

### OU6 [P3] `_cache_review_gate` 的 risk_level 依赖 LLM 自由输出 + 审查对象是架构 JSON

- **Bug 代码**：

```python
# :35-43 - review_code 返回 LLM 自由输出 dict，risk_level 缺失时兜底 low 恒放行
review = await self.reviewer.review_code(architecture_summary, "cached_architecture", context=...)
risk_level = review.get("risk_level", "low")
if risk_level == "high": return False
```

- **根因**：CodeReviewer.review_code（code_reviewer.py:57）返回 LLM 生成的 JSON dict，`risk_level` 键缺失时 `.get` 兜底 low → 放行。审查对象是 `json.dumps(cached.architecture)[:800]` 截断的架构摘要，非代码。
- **影响**：缓存审查闸门有效性依赖 LLM 恰好输出 risk_level；架构摘要审查语义弱。已确认 reviewer 类型为 CodeReviewer（orchestrator.py:120），无 Pydantic 契约问题（Pydantic 假设不成立，此处仅为质量风险）。

### OU7 [P3] `_wait_for_approval` 300s 超时对交互审批过长，超时语义=拒绝

- **Bug 代码**：

```python
# :199-207 - 超时返回 False（拒绝）但只记 warning
approved = await asyncio.wait_for(self.approval_callback(key), timeout=timeout)
```

- **根因**：默认 300s 交互审批等待；超时自动跳过（返回 False 视为拒绝）。语义上「超时拒绝」安全但用户侧无感。
- **影响**：长时间审批阻塞生成流程；拒绝原因不区分用户主动拒绝与超时。

### OU8 [P3] `_call_llm_for_patch` 复用 backend_engineer/architect 的 call_llm

- **Bug 代码**：

```python
# :296-304 - 经工程师/架构师实例调用，不走统一 llm_client
engineer = self.backend_engineer or self.architect
return await engineer.call_llm(prompt, system_prompt)
```

- **根因**：patch 生成复用 agent 实例的 call_llm（specialist_base 链），不经 LLMClient/DMR/成本记录（归入 LCL1 收敛范围，与 OF4/ERL4/CEC3 同类）。
- **影响**：patch 调用不计成本、不参与统一路由。

### OU9 [P3] `_git_save_snapshot` 裸 git init/commit 双快照体系 + 每轮 --allow-empty commit

- **Bug 代码**：

```python
# :339-410 - snapshot_mgr 优先，失败回退裸 git init + git commit --allow-empty
```

- **根因**：快照优先走 SnapshotManager，失败回退在 output_dir 裸 `git init` + `git config` + `git add -A` + `git commit --allow-empty`（:366-401）。两套快照体系并存；`--allow-empty` 使无变更轮也产生空 commit。
- **影响**：双快照路径语义不统一（tag 体系 vs 裸 commit）；git 历史每轮一个 commit 含空提交；`git config` 固定写 CodingMatrix Agent 身份（:372-379）。

### OU10 [P3] `_should_check_api_consistency` .py 启发式（路径含 api/route）

- **Bug 代码**：

```python
# :209-215 - 后端判定靠路径关键词
if ext == '.py' and ('api' in file_path.lower() or 'route' in file_path.lower()):
    return True
```

- **根因**：后端文件识别靠路径含 `api`/`route` 子串，与 IV3/AC 判定同类启发式。命名不含 api/route 的后端文件漏检。
- **影响**：API 一致性检查覆盖面依赖命名约定。

### OU11 [P3] `_compute_layers` priority 缺失默认 3

- **Bug 代码**：

```python
# :123-131 - 按 priority 分组，缺失默认 3
p = fi.get("priority", 3)
```

- **根因**：file_plan 未显式 priority 的文件全部落入第 3 层（最后一批）；_validate_file_plan 过滤保留原 file_info 的 priority，但默认计划显式 1/2/3。
- **影响**：无 priority 的生成计划分层扁平化（全在一批），并行分层退化为顺序。

### OU12 [P3] 零测试覆盖（mixin 依赖宿主属性不可独立单测）

- **根因**：UtilsMixin 16 方法全部经 `self.xxx` 访问宿主注入属性（warnings/feedback_learner/reviewer/output_dir 等），无默认值 → 无法独立实例化测试。tests/unit 零覆盖。
- **影响**：成本估算、文件计划校验、API 扫描等全部无回归保护（OU1/OU2/OU3 全在测试网下通行）。

## 4. 修复建议

- **OU1**：成本估算引入 file_plan 内容维度（按文件数 × 单文件 token 估算），与 CEC7 的 complexity `$0.001/1K` 体系合并为单一入口。
- **OU2**：修正正则允许 `\\` 与 UTF-8；删除死分支或先归一化再校验。
- **OU3**：对端文件集缓存（key=output_dir mtime），文件事件内复用。
- **OU4**：从 error_recovery fix_history 取 original/fixed 真实内容；file_type 从文件后缀推断。
- **OU5**：feedback_learner 暴露公开查询接口（如 get_anti_patterns()），mixin 不访问私有属性。
- **OU6**：审查闸门用结构化 schema 校验 LLM 输出必含 risk_level；或改用确定性的静态判定。
- **OU7**：超时缩短并区分「用户拒绝 / 超时跳过」两种结果。
- **OU8**：patch 调用统一走 llm_client（LCL1 收敛）。
- **OU9**：固定单一快照路径（SnapshotManager 优先，删除裸 git fallback 或反向）。
- **OU12**：为纯函数方法（_estimate_generation_cost/_validate_file_plan/_compute_layers）提供宿主注入默认值的可测入口。

## 5. 待实测项

- OU1-OU12 均为代码级结论。OU4（reviewer 类型）已实码确认 CodeReviewer；OU3 为 AC6 位置确认。无待实测阻塞项。
