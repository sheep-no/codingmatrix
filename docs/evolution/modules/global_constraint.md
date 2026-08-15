# GlobalConstraintParser 深扫（global_constraint.py，359 行）

> 第九十二轮推演 | 2026-08-15 | 定位：全局约束解析器（spec_first 链活跃接线，但提取/注入链路多缺陷）

## 1. 模块定位

从用户需求文本中提取全局约束（技术栈/兼容性/安全/性能/架构/风格/命名/测试 8 类），生成 prompt 片段注入生成链路。**活跃生产模块**：spec_first_generate.py:161-162 `parse_requirement` + :208 `generate_prompt_fragment("all","all")` + :794 传 constraints 给 ArchitectureInspector。与 ArchitectureInspector AI2（约束检查空转）同属一条链路的两端。

### 依赖链

| 方向 | 模块/位置 | 说明 |
|------|-----------|------|
| 被消费 | `spec_first_generate.py:161-162` | `parse_requirement(requirement)` 提取 → ctx metric |
| 被消费 | `spec_first_generate.py:208-210` | `generate_prompt_fragment("all","all")` → project_context["global_constraints"] 注入架构师/工程师 prompt |
| 被消费 | `spec_first_generate.py:794` | constraints 传给 `ArchitectureInspector.inspect(..., constraints=...)` |
| 被消费 | `architecture_inspector.py:331-348` | `_check_global_constraints`（AI2 已证空转：applies_to 层名被当文件路径） |
| 未消费 | `get_constraints_for_file` / `merge_with_decisions` / `_file_matches_category` | 生产零消费方（全库确认） |
| 测试 | **零测试覆盖**（tests/ 无任何 constraint 用例） | |

## 2. 深扫发现

### P2 项

- **GC1 [P2] 单句多约束只取第一个（实测）**——`_classify_constraint` 按 `CONSTRAINT_PATTERNS` dict 顺序匹配，命中第一个 pattern 即 `return`（:190-202），一个句子最多产出一个约束。而 `_extract_global_statements` 用 `re.split(r'[。\n;]')` 分句（:174），**逗号不分句**——需求「必须使用 FastAPI，兼容 IE11，所有接口必须有权限校验，响应时间不超过 200ms，统一代码风格」整段成一句 → 只提取 tech_stack FastAPI，IE11/权限/性能/风格 4 个约束全部丢失。实测需求 1/需求 10 均只输出第一条。**分类先到先得**：同一句同时命中多类别时按 dict 顺序 tech_stack 优先（GC9 与 GC1 同源，合并）。
- **GC2 [P2] compatibility/security 约束在全量注入时被过滤（实测，安全约束从未进入 prompt）**——spec_first **只用** `generate_prompt_fragment("all","all")`（:208）。`get_constraints_for_file("all","all")` 判定链：`"all" in applies_to` → compatibility 的 applies_to=["frontend"]、security 的 applies_to=["backend","api"] 均不含 "all" → False；`file_type in applies_to`（"all" in ["frontend"]）→ False；`_file_matches_category("all", COMPATIBILITY)` → `"frontend" in "all"` → False → **compatibility/security 约束永远不注入**。实测需求 4：IE11 与权限校验约束已成功提取，但 `generate_prompt_fragment("all","all")` 输出仅含 FastAPI。**安全/兼容约束提取了却不进 prompt**——提取层正常、注入层丢弃，属「提取≠生效」家族。文件级路径 `generate_prompt_fragment('app/api/users.py','api')` 能注入 security（实测需求 5），但 spec_first 从不走文件级。
- **GC3 [P2] 普通需求误提取为 general 约束（实测）**——GLOBAL_KEYWORDS 含「必须/所有/统一/支持/兼容」等高频词（:60-66），任何含这些词的日常句子都通过 `_extract_global_statements` 筛选，若无 pattern 匹配则兜底为 general ARCHITECTURE medium 约束（:204-211）。实测需求「开发一个用户管理系统，必须有登录功能，用户数据统一存在 MySQL」→ 输出 `[architecture] 开发一个用户管理系统，必须有登录功能... | medium`——**登录功能/数据存储这类正常需求被当成全局约束**注入 prompt，噪声污染生成。keyword 层与 pattern 层完全脱节（keyword 只做粗筛，pattern 不匹配照样兜底产出）。

### P3 项

- **GC4 [P3] 性能约束 pattern 不可达（实测）**——performance pattern `响应\s*时间\s*(?:不超过|少于)\s*(\d+)` 存在（:100-102），但 `_extract_global_statements` 先用 GLOBAL_KEYWORDS 过滤，关键词表无「响应时间/加载时间/延迟/性能」→ 纯性能句「响应时间不超过 200ms」被过滤 → 0 约束（实测需求 8）；只有句子同时含「所有/必须」等词（如「所有接口响应时间必须不超过 200ms」）才能进入。**关键词筛选层与 pattern 层两套词表脱节**，性能约束实际几乎不可达。
- **GC5 [P3] `_file_matches_category` 大量恒 True（实测）**——tech_stack/performance/architecture/style/naming 5 类恒 True（:271/:274-277），实际只有 compatibility/security/testing 有路径判断。路径匹配形同虚设，TECH_STACK/PERFORMANCE 约束对任何文件路径都适用（注：`"all" in applies_to` 已先短路这些类，恒 True 分支主要影响 `get_constraints_for_file` 未走全量路径时）。
- **GC6 [P3] 文件级筛选/决策合并能力零消费（全库确认）**——`get_constraints_for_file`、`merge_with_decisions`（:335-359，docstring 声称合并用户决策到约束 prompt，与 CD1 决策注入主线直接相关）、`_file_matches_category` 生产零调用方。主路径只走 `generate_prompt_fragment("all","all")`——**文件级差异注入与决策合并能力从未接线**，「能力未接线」家族（扩展方法层面，非模块级）。
- **GC7 [P3] constraint_id 语义混乱（实测）**——`constraint_id = f"{category}_{len(self.constraints)}"`（:194）用当前全局长度而非 category 内序号。实测需求 7 三条 tech_stack → id=tech_stack_0/1/2 递增碰巧正确；但若 general 兜底在前（如「必须有登录功能」→ general_0），后续 tech_stack 从 len 计数得 tech_stack_1——**category 前缀 + 全局序号混用**，id 不稳定且不可预测（依赖解析顺序），下游无法按 id 稳定引用。
- **GC8 [P3] 分句正则不含英文句点**——`re.split(r'[。\n;]')`（:174）不含 `\.`，英文需求（全英文句点分隔）整段被当一句 → 放大 GC1（英文多约束需求只取第一个）。中文需求用「。」「\n」可正确分句。

## 3. 演化方向

本模块是 spec_first 链「用户约束 → 生成 prompt」的唯一通道，提取层与注入层**都有缺陷但缺陷不对称**：
- **提取端（GC1/GC3/GC4/GC8）**：单句多约束丢失 + 高频词误报 + 性能类不可达——提取质量直接决定注入质量，是全链路第一步。
- **注入端（GC2）**：**最严重**——compatibility/security 提取成功却在全量注入被丢弃，安全约束从未影响生成。修复方向：`get_constraints_for_file` 对 `"all"` 文件路径应视为「全部适用」而非「匹配 applies_to 含 all」，或 spec_first 改为遍历所有 constraints 全量注入。
- **扩展端（GC6）**：文件级差异注入 + 决策合并未接线——与 CD1（决策从未注入生成 prompt）同主线，`merge_with_decisions` 是现成的决策注入通道，接线即补上 CD1 缺口。
- **架构检查端（AI2 已记录）**：spec_first:794 传约束给 ArchitectureInspector 期望约束检查，但 applies_to 层名被当文件路径查——契约错位（本模块产 `["backend","frontend","all"]` 层名，inspector 按文件名查）。两模块需统一 applies_to 语义。

**修复优先级**：GC2（安全约束失效）> GC1（多约束丢失）> GC3（误报噪声）> GC4/GC6（性能不可达 + 能力未接线）> GC5/GC7/GC8（设计瑕疵）。

## 4. 主线关联

- **「提取≠生效」家族**：GC2 与 CD1（用户决策提取了未注入）、SCT5（能力提取了未接线）同族——本模块是**提取层正常、注入层丢弃**的典型（与「纯死代码」不同）。
- **「存在≠正确」需求解析主线**：GC1/GC3/GC4 与 JP1（解析语义失真）、FD1（检测端失真）、LD1（语言检测失真）同族——需求解析器的语义缺陷影响整条生成链。
- **「能力未接线」家族**：GC6 扩展方法零消费，与 UPL1/SL1/FPC1/SCT5 同族（扩展层面）。
- **架构检查闭环**：AI2 + GC（applies_to 契约错位）——全局约束从提取到检查整条链路两端都失效。

## 5. 测试状态

**零测试覆盖**——tests/ 无任何 global_constraint 用例。GC1-GC8 全部实测可复现但无用例保护。spec_first 集成链测试也未覆盖约束注入（约束相关功能全凭手工验证）。
