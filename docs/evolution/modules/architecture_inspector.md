# ArchitectureInspector 演化深扫文档

> 版本：v0.1 | 扫描日期：2026-08-14 | 状态：已完成
> 归属：A 大系统 Agent 引擎 / A10 支撑层
> 路径：app/agent/architecture_inspector.py（510 行）
> 索引：[TASKS.md](../TASKS.md)

## 1. 模块作用与功能

- **核心职责**：文件生成完成后，以架构师视角审查生成的代码是否符合全局架构设计（分层边界、依赖方向、接口风格、命名规范、全局约束、技术栈一致性），生成架构检查报告。
- **主要类 / 函数清单**（21 方法）：
  - `ArchitectureViolation` / `ArchitectureCheckResult`（:21/:31 dataclass）
  - `ArchitectureInspector.__init__`（:66，architecture_design / generated_files / global_constraints / user_decisions 四字段）
  - `set_context`（:72，注入检查上下文）
  - `inspect`（:85，入口：串行六项检查 + 可选 LLM 审查 → passed / alignment_score / suggestions）
  - `_check_layer_boundaries`（:132）→ `_get_assigned_layer`（:158）→ `_violates_boundary`（:174）
  - `_check_dependency_direction`（:190）→ `_extract_imports`（:213）→ `_check_import_direction`（:231）
  - `_check_interface_style`（:249）→ `_check_api_style`（:273）
  - `_check_naming_conventions`（:289）→ `_check_file_naming`（:310）
  - `_check_global_constraints`（:331）→ `_check_constraint_in_content`（:350）
  - `_check_tech_stack_consistency`（:373）→ `_check_framework_inconsistency`（:422）
  - `_llm_architecture_review`（:443）
  - `_calculate_alignment_score`（:471）/ `_generate_fix_suggestions`（:488）/ `get_violations_by_type`（:500）
- **对外接口**：唯一生产消费方 `spec_first_generate.py:790-797`（实例化 + set_context + inspect + 结果写入 ctx metric `architecture_check`）。
- **内部子功能划分**：规则检查（六类，全部子串/关键词启发式）→ LLM 审查（可选）→ 评分与建议。

## 2. 依赖与被依赖

- **导入依赖**：仅标准库（logging / typing / dataclasses）。无第三方依赖、无 app 内 import。
- **生产使用方**：唯一实例化点 `app/agent/orchestrator_generation/spec_first_generate.py:790`（SpecFirstGenerateMixin 生成链尾部，`ctx.set_metric("architecture_check", ...)` :799-804；不通过时 append warnings :806-807）。传统生成链路（traditional_generate）**不使用**。
- **测试覆盖**：**零**（tests/ 下无任何引用 ArchitectureInspector / architecture_inspector / architecture_check）。

## 3. 已探明 Bug（含 bug 代码）

### AI1 [P0] passed 恒 True——架构检查门禁从未拦截

- **现象**：`inspect()` 的 `passed` 判定仅看 critical 级违规，但全部内建检查产出的 severity 最高为 high，唯一能产出 critical 的 LLM 审查在唯一消费方无参调用永不执行 → 架构检查**永远通过**。
- **Bug 代码**：

```python
# architecture_inspector.py:112-113 - 判定基准
critical_violations = [v for v in violations if v.severity == "critical"]
passed = len(critical_violations) == 0
# 六项内建检查 severity 赋值: high(152/367/406/416) / medium(207/267) / low(304)
# 无任何一处产出 "critical"
```

```python
# spec_first_generate.py:797 - 唯一消费方无参调用，llm_checker 恒 None
architecture_check = architecture_inspector.inspect()
```

- **根因**：`passed` 的语义与检查产出严重度分级脱节。内建规则检查最高只报 high，而门禁只认 critical——设计上假设 LLM 审查会报 critical，但 LLM 审查是可选参数且生产从未传入。
- **影响**：spec_first:806 `if not architecture_check.passed` 分支恒不执行，`architecture_check` metric 中的 `passed` 恒 True。与「存在≠正确」验证语义主线同源：审查环节形同虚设。
- **触发条件**：任何 spec-first 生成流程。
- **验证方式**：构造含多层边界违规的 generated_files 调用 `inspect()`，观察 `passed` 恒 True。

### AI2 [P0] _check_global_constraints 完全空转——安全检查从未执行

- **现象**：`_check_global_constraints` 遍历 `constraint.applies_to`（如 `["backend", "frontend", "all"]`，见 global_constraint.py:77），把层名字符串当**文件路径**去 `generated_files.get()` 查内容，恒 miss；且 `"all"` 被 `continue` 显式跳过 → 所有约束检查的 content 恒空 → **零违规产出**。
- **Bug 代码**：

```python
# architecture_inspector.py:335-342 - applies_to 是层名而非文件路径
for constraint in self.global_constraints:
    for file_path in constraint.applies_to:   # "backend" / "frontend" / "all"
        if file_path == "all":
            continue                          # 全局适用的反而被跳过
        content = self.generated_files.get(file_path, "")   # 层名查不到真实文件 → 恒 ""
        if not content:
            continue                          # 恒 continue
```

- **根因**：把 `applies_to` 的层名/关键词语义误当为文件路径。约束实际应该匹配的是 `generated_files` 的真实文件名，而非 applies_to 字面值。
- **影响**：spec_first:794 传入的 `global_constraints`（含「所有接口必须有权限校验」等）在检查阶段**全部不生效**；`_check_constraint_in_content` 的安全模式缺失检测（:359-369）是死逻辑。
- **触发条件**：spec-first 流程带任意全局约束。
- **验证方式**：传入 `applies_to=["all"]` 的约束 + 含无鉴权 API 文件的 generated_files，调用 `_check_global_constraints` → 返回空列表。

### AI3 [P1] 六类检查中四类依赖架构师不产出的 key——结构性空转

- **现象**：`_check_layer_boundaries` 依赖 `architecture_design["layers"]`、`_check_dependency_direction` 依赖 `["dependency_rules"]`、`_check_naming_conventions` 依赖 `["naming_conventions"]`，但 architect 产出的 architecture 字典只含 `tech_stack`（architect.py:273/:538）+ 其他字段，**全库无任何代码产出这三个 key**。
- **Bug 代码**：

```python
# architecture_inspector.py:136-138 / :194-196 / :293-295 - 三处同构
layer_definitions = self.architecture_design.get("layers", {})
if not layer_definitions:
    return violations        # 恒空转
```

- **根因**：模块设计了规则检查的完整入口，但架构设计侧从未定义对应数据契约（layers/dependency_rules/naming_conventions 是模块私有约定，无生产者）。
- **影响**：六项检查中实际生效的只剩 `_check_interface_style`（依赖 user_decisions，可能有值）、`_check_global_constraints`（AI2 已证死）、`_check_tech_stack_consistency`（AI6）。架构检查覆盖名存实亡。
- **触发条件**：所有 spec-first 生成。
- **验证方式**：断点观察 architect 输出字典，确认无 `layers`/`dependency_rules`/`naming_conventions` 键。

### AI4 [P1] _violates_boundary 正则风格模式按字面子串匹配——恒不触发或假阳性

- **现象**：`rule_patterns` 中 `"import.*sql"` / `"return.*html"` 是正则风格写法，但用 `pattern in content` 字面子串匹配——含 `.*` 的模式字面永远不出现在真实代码中，永不触发；而 `"SELECT"` / `"INSERT"` / `"render"` / `"template"` 等无元字符模式命中注释、字符串、依赖文件 → 双向失真。
- **Bug 代码**：

```python
# architecture_inspector.py:174-186 - 正则写法被当作字面量
def _violates_boundary(self, content: str, rule: str) -> bool:
    rule_patterns = {
        "no_database_access": ["import.*sql", "import.*mongo", "import.*redis", "SELECT", "INSERT"],
        "no_business_logic": ["class.*Service", "def.*calculate", "def.*validate"],
        ...
    }
    patterns = rule_patterns.get(rule, [])
    for pattern in patterns:
        if pattern.lower() in content.lower():   # "import.*sql" 字面匹配，永不命中
            return True
```

- **根因**：作者意图写正则但误用 `in` 子串操作符；`.*` 无转义解析。
- **影响**：分层边界检查的数据库访问/业务逻辑规则静默失效（含 `.*` 的模式全灭），同时 `SELECT` 等裸词在注释/字符串中误报。
- **触发条件**：layer_definitions 存在且有 boundaries 规则（当前因 AI3 无生产者而不可达，修复 AI3 后将直接暴露）。
- **验证方式**：`_violates_boundary("import sqlalchemy\nx", "no_database_access")` → False（应 True）。

### AI5 [P1] _check_import_direction 语义反转——允许目标任一不在 import 即报违规

- **现象**：对 `allowed_targets` 循环 `if allowed not in import_path: return rule_name`——只要允许目标中**有一个**不在 import 路径中即判违规。语义应是「import 目标须属于 allowed 集合」，实为「allowed 全部须出现在 import 里」，多目标规则必然误报。
- **Bug 代码**：

```python
# architecture_inspector.py:238-246
for rule_name, rule_config in dependency_rules.items():
    source_pattern = rule_config.get("source")
    allowed_targets = rule_config.get("allowed_targets", [])
    if source_pattern and source_pattern in file_path:
        for allowed in allowed_targets:           # 循环任一不满足即违规
            if allowed not in import_path:
                return rule_name                   # 应判断 import 目标归属，而非要求全包含
```

- **根因**：方向判断逻辑写反——把「白名单」当「必须全含」处理。
- **影响**：allowed_targets 有 2+ 项时，任何 import 只要不含其中一项即误报违规；同时反向依赖（import 指向禁止层）反而可能漏检。
- **触发条件**：dependency_rules 存在（当前因 AI3 不可达）。
- **验证方式**：构造 `allowed_targets=["src.models", "src.services"]`，import 仅含 `src.services` → 误报。

### AI6 [P2] _check_tech_stack_consistency 路径子串归属 + 框架标记子串误判

- **现象**：用 `"backend" in file_path.lower()` / `"frontend" in file_path.lower()` 判定文件归属——`backend_utils.py`、含 `frontend` 的目录路径、`data/backend/` 等一律按子串归类，无真实框架边界；`_check_framework_inconsistency` 的 markers（`"from fastapi"`、`"FastAPI"`、`"ref("`）子串命中注释/文档/依赖锁定文件 → 假阳性或漏检。
- **Bug 代码**：

```python
# architecture_inspector.py:399-410 - 子串归属判定
if backend_framework and "backend" in file_path.lower():
    if self._check_framework_inconsistency(content, backend_framework):
        # 判违规
```

- **根因**：路径启发式替代真实模块归属分析；markers 未做语法级（AST/import 解析）判断。
- **影响**：技术栈一致性检查产生噪声违规（注释含 "FastAPI" 即通过、路径含 frontend 的后端文件被查前端框架）。
- **触发条件**：tech_stack 非空（唯一有生产者的 key，architect.py:273/:538）。
- **验证方式**：`_check_framework_inconsistency("# not FastAPI code", "FastAPI")` → False（应为无实际使用，但注释误判为一致）。

### AI7 [P2] _check_api_style 单向关键词——无法判定风格一致性

- **现象**：REST 分支只查是否出现 GraphQL 关键字（`query {`/`mutation {`），GraphQL 分支只查 REST 路由关键字——不检查「该用 REST 时是否真的用了 REST 语义」，只做对向反证；且 `HTTPMethod` 等模式与真实代码形态（FastAPI `@app.get`）不匹配。
- **Bug 代码**：

```python
# architecture_inspector.py:275-287
if api_style == "REST":
    graphql_patterns = ["query {", "mutation {", "type Query", "type Mutation"]
    for pattern in graphql_patterns:
        if pattern in content:
            return "包含 GraphQL 语法"
```

- **影响**：REST 风格项目只要不含 GraphQL 字面即通过，接口风格检查基本是空检。
- **触发条件**：user_decisions 含 `api_style`（spec_first:795 传入 `decision_extractor.get_all_choices()`，CD 决策链可能提供）。

### AI8 [P2] 附属问题集合

- **AI8a `_check_file_naming` 只覆盖 snake_case/kebab-case 两规则**（:319-329），naming_rules 无 camelCase/PascalCase 分支，且依赖 AI3 不产出的 key。
- **AI8b `_calculate_alignment_score` 权重求和**（:479-485）：无违规=1.0，任一违规扣分后叠加，`"critical": 0.3` 无来源（AI1），违规一多 score 迅速归零，与 passed 判定（只看 critical）口径不一致。
- **AI8c `_llm_architecture_review` 异常静默**（:466-467）：LLM 返回结构不符合 `{"violations": [...]}` 时静默 return []，成功态与失败态同返回（「成功态家族」）；且要求 dict 契约与项目两套 LLM 返回契约（顶层 call_llm dict vs LLMClient str）主线冲突，接线即崩。
- **AI8d `get_violations_by_type` 全库零消费方**（:500-510，死方法，「能力未接线」家族成员）。
- **AI8e 模块无 __main__/测试入口**，零测试覆盖（见 §2）。

## 4. 潜在问题与未知点

- `_check_interface_style` 的 api_style 来源：spec_first:795 传 `decision_extractor.get_all_choices()`，需实测 CD 决策是否产出 `api_style` 键（CD 详档显示 decision 状态可能恒空，见 critical_decision.md CD2）。
- architecture 字典除 `tech_stack` 外是否还有其他潜在 key 可复用（如 `layers` 别名/嵌套结构）——architect.py:273/:538 上下文未见，需全量核对架构输出 schema。
- `_check_tech_stack_consistency` 的 `tech_stack` list 分支（:382-394）字符串分类启发式（"backend" in item.lower()）在真实 tech_stack 结构（list of dict 或 dict）下的实际形态未实测。

## 5. 修改建议（改什么 → 达成什么目的）

| # | 优先级 | 修改动作 | 达成目的 | 涉及位置 | 对应 Backlog |
|---|--------|---------|---------|---------|-------------|
| 1 | P0 | `inspect` 的 passed 判定改为「high 及以上违规数为 0」，或在六项内建检查中按严重度产出 critical；同步调整 `_calculate_alignment_score` 权重口径 | 架构检查门禁真实生效，spec_first:806 警告分支可触发 | architecture_inspector.py:112-115 / :479 | #456 |
| 2 | P0 | 重写 `_check_global_constraints`：按 `applies_to` 语义（层名/关键词/`all`）匹配 `generated_files` 真实文件路径，`all` 应匹配全部而非跳过 | 安全/权限全局约束检查真正执行 | architecture_inspector.py:331-371 | #457 |
| 3 | P1 | 为架构设计字典定义 `layers`/`dependency_rules`/`naming_conventions` 数据契约并在 architect 侧产出，或将检查降级为基于 tech_stack + 实际文件结构的自推导 | 四项规则检查从空转转为可执行 | architect.py + architecture_inspector.py:136/:194/:293 | #458 |
| 4 | P1 | `_violates_boundary` 改用正则 `re.search`（转义修正）或 AST/import 解析，去除 `SELECT` 等裸词子串误报 | 分层边界检查双向可靠 | architecture_inspector.py:174-188 | #459 |
| 5 | P1 | `_check_import_direction` 改为「import 目标是否落在 allowed_targets 白名单之外」，消除多目标误报 | 依赖方向语义正确 | architecture_inspector.py:231-247 | #460 |
| 6 | P2 | 文件归属改用真实目录/包结构判断替代 `"backend"/"frontend" in path` 子串；框架 markers 用 AST import 解析替代裸词子串 | 技术栈一致性检查降低噪声 | architecture_inspector.py:373-441 | #461 |
| 7 | P2 | 统一 LLM 审查契约（对齐两套 LLM 返回规范），修复异常静默；spec_first:797 接线 llm_checker | LLM 架构审查从死路径转活跃 | architecture_inspector.py:443-469 | #462 |
| 8 | P2 | 删除死方法 `get_violations_by_type` 或接线消费方；补充模块单元测试（passed 语义/全局约束/import 方向/边界违规） | 消除死代码 + 建回归基线 | architecture_inspector.py:500 | #463 |

## 6. 演化方向关联

- 该模块在演化四阶段中属于**阶段一修复止血（P0）与阶段二统一收敛（P1）**之间：AI1/AI2 是检查门禁真实性缺口（修复止血），AI3-AI5 是数据契约与检查语义错配（统一收敛）。
- 归属「存在≠正确」验证语义主线（与 cross_validator CV / refinement_loop RL3 / test_runner TR1 同族）——架构审查是生成链路最后一道验证关口，当前形同虚设。
- 架构检查与 `critical_decision`（CD 决策）耦合：AI7 的 api_style 依赖决策链路产出；CD 修复（见 critical_decision.md CD1/CD2）后检查输入源才可靠。
- 与两套 LLM 契约主线（LLMClient str vs call_llm dict）冲突点：AI8c；接线 LLM 审查须走统一 llm_client（LCL1 收敛范围）。
