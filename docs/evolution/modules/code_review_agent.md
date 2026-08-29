# code_review_agent.py 演化深扫文档

> 版本：v0.1 | 扫描日期：2026-08-29 | 状态：已完成
> 归属：Agent 引擎 / 审查能力
> 路径：`app/utils/review/code_review_agent.py`（582 行）
> 索引：[TASKS.md](../TASKS.md)，第 161 轮

## 1. 模块定位与三态判定

### 1.1 模块作用

`CodeReviewAgent` 是一个同步、规则驱动的本地代码扫描器：按 Python AST、正则、JavaScript 正则和通用文本规则生成 `ReviewIssue` 列表，并由 `review_project()` 汇总为统计报告。模块同时内置 6 类 `SkillPrompt` 配置，用于切换生产、安全、性能、测试、无障碍和文档检查。

主要符号：

- `SeverityLevel`：严重程度枚举，`code_review_agent.py:21-27`。
- `ReviewCategory`：审查类别枚举，`code_review_agent.py:29-37`。
- `ReviewIssue` / `SkillPrompt`：问题结果和 Skill 配置数据类，`code_review_agent.py:39-62`。
- `SKILL_PROMPTS`：6 类规则配置，`code_review_agent.py:64-181`。
- `CodeReviewAgent.__init__`：默认启用 `production`、`security`，`code_review_agent.py:184-200`。
- `review_file()` / `review_python_code()` / `review_javascript_code()` / `review_generic_code()`：单文件分派和语言扫描，`code_review_agent.py:202-300`。
- `get_review_report()` / `review_project()`：项目级递归扫描和报告组装，`code_review_agent.py:509-582`。

### 1.2 三态判定：未接入

本文件属于“未接入”状态：能力实现完整度较高，但全库 `rg` 未发现 `app/` 或 `tests/` 对 `app.utils.review.code_review_agent`、`CodeReviewAgent`、`review_project()` 或其数据类型的导入和调用。它没有路由入口，也没有被编排器、服务层或校验链挂载。

- **活跃面**：零。`app/agent/code_reviewer.py` 是当前生成链实际使用的审查器，不属于本模块。
- **未接入面**：整个 `CodeReviewAgent` 及 `review_project()` API；唯一外部命中是 `.claude/skills/code-review/SKILL.md:132-138` 的使用示例，属于文档引用。
- **废弃面**：当前尚无明确的删除提交或废弃声明，但该模块的代码审查职责已被 `app/agent/code_reviewer.py` 的 LLM 门禁体系覆盖，具备迁移后退役条件。

未接入状态改变缺陷定级：以下 P2/P3 描述的是模块一旦接线或被文档示例调用时的行为风险，当前生产链路不会直接触发这些问题。

## 2. 消费方证据与双轨关系

### 2.1 全库消费方证据

| 方向 | 模块/位置 | 证据与用途 |
|------|-----------|------------|
| 文档引用 | `.claude/skills/code-review/SKILL.md:129-138` | 示例导入 `CodeReviewAgent`，却调用不存在的异步 `review_code(file_path)` API；当前实现提供同步 `review_file(Path, language)` 和 `review_project(Path, skills)` |
| 生产消费 | `app/` | `rg` 未发现 `app.utils.review.code_review_agent`、`CodeReviewAgent` 或 `review_project()` 的 import/call |
| 测试消费 | `tests/` | `rg` 未发现目标模块、`CodeReviewAgent`、`ReviewIssue`、`ReviewCategory` 或 `SeverityLevel` 的直接测试引用 |
| 活跃审查门禁 | `app/agent/orchestrator_generation/mixin.py:88-90` | 实例化 `app.agent.code_reviewer.CodeReviewer`，并注入 `ErrorRecoveryLoop` |
| 活跃审查调用 | `app/agent/orchestrator_files.py:732-748` | 调用 `self.reviewer.review_code()`，消费 `needs_fix`、`risk_level` 和 `issues` 决定警告及验证失败 |
| 活跃审查重试 | `app/agent/orchestrator_utils.py:30-35`、`app/agent/error_recovery.py:59-61` | 同一 `CodeReviewer` 贯穿缓存审查和错误恢复链 |

### 2.2 与 `app/agent/code_reviewer.py` 的双轨关系

两者都表达“代码审查”语义，运行模型和结果契约不同：

| 维度 | `app/utils/review/code_review_agent.py` | `app/agent/code_reviewer.py` |
|------|----------------------------------------|-----------------------------|
| 定位 | 未接入的本地静态规则扫描器 | 活跃的 Specialist 子类和生成门禁 |
| 调用方式 | 同步 `review_file()` / `review_project()` | 异步 `review_code(code, file_path, context)` |
| 分析方式 | AST + 正则，默认 `production`/`security` | LLM 审查 + 版本兼容性检查 |
| 结果类型 | `List[ReviewIssue]` 或裸 `Dict[str, Any]` 报告 | 裸 `Dict`，消费方依赖 `needs_fix`、`risk_level`、`issues` |
| 消费链 | 无生产消费 | `mixin.py:88` → `orchestrator_files.py:733`，并进入错误恢复链 |

这是一组审查能力双轨：静态规则引擎保留了低成本、可重复的本地检查，LLM Specialist 承担当前生产门禁。两者没有共享的结果 Schema、统一入口或组合顺序，文档示例把静态实现描述成异步 `review_code`，进一步放大了 API 认知漂移。

## 3. 已探明 Bug

### B1 [P2] accessibility Skill 命中缺少 alt 的图片时引用不存在的枚举成员

- **现象**：启用 `accessibility` Skill，且 JavaScript/HTML 中存在不含 `alt=` 的 `<img>` 标签时，`_check_js_skills()` 构造 `ReviewIssue` 会访问 `ReviewCategory.ACCESSIBILITY`；该枚举只定义到 `DOCUMENTATION`，因此抛出 `AttributeError`，整个文件审查中断。
- **Bug 代码**：

```python
# app/utils/review/code_review_agent.py:29-37 - ReviewCategory 未定义 ACCESSIBILITY
class ReviewCategory(str, Enum):
    SECURITY = "security"
    PERFORMANCE = "performance"
    STYLE = "style"
    MAINTAINABILITY = "maintainability"
    TESTING = "testing"
    DOCUMENTATION = "documentation"

# app/utils/review/code_review_agent.py:497-502 - 实际访问缺失成员
category=ReviewCategory.ACCESSIBILITY,
```

- **根因**：Skill 配置在 `SKILL_PROMPTS` 中包含 `accessibility`，检查分支也已实现，但结果枚举没有同步增加对应类别。
- **影响**：目标模块接线后，无障碍检查的特定命中会从“返回审查问题”升级为异常；其他 Skill 和当前活跃 `app/agent/code_reviewer.py` 不受此处代码直接影响。
- **触发条件**：调用 `review_javascript_code()` 或以 `language="javascript"` 调用 `review_file()`，同时启用 `accessibility`，并命中缺少 `alt` 的图片标签。
- **验证方式**：构造 `CodeReviewAgent(skills=["accessibility"])`，审查 `"<img src='a.png'>"`，断言当前抛出 `AttributeError`；修复后应返回 `ReviewCategory.ACCESSIBILITY` 类型的问题。

### B2 [P2] 规则扫描器无法作为文档声明的审查 API 使用

- **现象**：`.claude/skills/code-review/SKILL.md:132-138` 声明 `await agent.review_code(file_path)`，目标类没有 `review_code()`，并且现有 `review_file()` 是同步方法且要求 `Path`；按文档示例接线会立即触发 `AttributeError`，改为 `review_file()` 后又需要调整同步/异步边界和参数类型。
- **根因**：Skill 文档沿用了另一版 API 设计，代码只实现了 `review_file()` 和项目级 `review_project()`，缺少兼容的公共入口与契约校验。
- **影响**：任何依文档接入静态审查能力的调用方都会在真正扫描前失败；这也是目标模块长期保持零生产消费的直接接线风险。
- **触发条件**：按 Skill 文档的示例导入并调用 `CodeReviewAgent.review_code()`。
- **验证方式**：执行示例调用并确认方法不存在；全库 `rg` 已确认没有其他真实调用方可替代验证。

## 4. P3 发现与未知点

### B3 [P3] AsyncFunctionDef 未纳入 Python AST 的函数长度和 docstring 检查

- **位置**：`app/utils/review/code_review_agent.py:306-332`。
- `ast.walk()` 只判断 `ast.FunctionDef`，异步函数节点 `ast.AsyncFunctionDef` 不会产生“函数过长”或“缺少文档字符串”问题；目标是代码质量审查时会漏掉常见的 async API 和 Agent 方法。
- 修复方向：统一处理 `ast.FunctionDef` 与 `ast.AsyncFunctionDef`，并补边界测试。

### B4 [P3] 多项正则检查返回行号 0，报告无法定位问题

- **位置**：`_check_python_skills()` 的 SQL 拼接和相对导入检查，`app/utils/review/code_review_agent.py:417-438`。
- 这些检查对整段代码执行正则，却把 `ReviewIssue.line` 固定为 `0`；项目报告虽然输出 `line`，消费方无法跳转到触发代码，且无法区分多处命中。
- 修复方向：逐行检查或从正则匹配对象计算起始行号，统一保证 `line >= 1`。

### B5 [P3] 正则规则存在注释、字符串和复杂语法误报/漏报面

- **位置**：`app/utils/review/code_review_agent.py:369-406`、`417-438`、`448-483`。
- `print`、密码赋值、SQL 拼接、`console.log` 和 `eval` 检查主要依赖文本匹配，注释、示例字符串和多行表达式可能产生误报，换行或等价 AST 写法可能漏报；`_check_python_skills()` 还把整段代码压成一个零行问题。
- 修复方向：Python 规则优先使用 AST，JavaScript 规则引入有语法位置信息的解析器或明确把结果标为启发式提示。

### B6 [P3] `review_file()` 对文件读取和编码错误没有结果化处理

- **位置**：`app/utils/review/code_review_agent.py:213-226`。
- `filepath.read_text(encoding="utf-8")` 的权限错误、目录路径、非法 UTF-8 或瞬时 I/O 异常会直接冒泡；项目级 `get_review_report()` 没有按文件隔离异常，单个输入可能中断整个扫描报告。
- 修复方向：定义读取失败的 `ReviewIssue`/报告错误契约，并让项目扫描继续处理其余文件。

### B7 [P3] `self.issues` 状态字段从未参与审查和报告

- **位置**：`app/utils/review/code_review_agent.py:200`。
- 构造函数初始化 `self.issues`，所有审查方法都使用局部 `issues`，`get_review_report()` 也从局部结果汇总；该字段会误导调用方以为实例持有累计结果，且多次调用的状态语义未定义。
- 修复方向：移除无效状态，或明确采用实例级累计并规定重复扫描和并发访问语义。

## 5. 退役与迁移建议

| # | 优先级 | 修改动作 | 达成目的 | 涉及位置 | 对应 Backlog |
|---|--------|---------|---------|---------|-------------|
| 1 | P2 | 若保留接线，先补 `ReviewCategory.ACCESSIBILITY`、文档示例 API 和直接测试 | 让静态扫描器能够稳定执行并兑现公开示例 | `code_review_agent.py:29-37,497-502`；`.claude/skills/code-review/SKILL.md:132-138` | 待登记 |
| 2 | P2 | 评估静态规则是否需要成为活跃审查链；若需要，将其结果映射到统一审查 Schema 并接入 `CodeReviewer` 前后明确顺序 | 统一静态检查与 LLM 门禁的边界、失败策略和结果消费 | `code_review_agent.py:202-567`；`app/agent/code_reviewer.py:56-102` | 待登记 |
| 3 | P3 | 迁移有价值的 AST/正则规则到活跃审查器的统一验证器，补行号、读取失败和 async 函数覆盖 | 保留可重复的确定性检查，消除独立双轨维护 | `code_review_agent.py:302-507`；`app/agent/orchestrator_files.py:732-748` | 待登记 |
| 4 | P3 | 完成迁移后移除 `app/utils/review/code_review_agent.py` 和过时 Skill 示例，或将其明确标为离线工具并补唯一入口 | 清理零消费模块，避免新调用方接入错误审查契约 | `code_review_agent.py` 全文件；`.claude/skills/code-review/SKILL.md:127-150` | 待登记 |

推荐路径是“规则提取 → 统一 Schema → 活跃链路接线 → 直接测试 → 退役旧模块”。目标模块当前零生产消费，不应围绕其每个启发式缺陷单独建立生产修复循环；迁移前优先修复 B1/B2 以避免接线即失败，迁移后由 `app/agent/code_reviewer.py` 作为唯一代码审查门禁。

## 6. 演化方向关联

- **统一收敛**：本模块与 `app/agent/code_reviewer.py` 构成代码审查双轨，属于审查链多实现和多结果契约问题；应收敛为一个入口和一个结果 Schema。
- **拆分解耦**：可复用的 AST 确定性检查可以作为独立 validator，被活跃 Specialist 审查前置调用；规则、报告组装和门禁决策应分离。
- **平台化**：统一结果需至少包含文件、行号、类别、严重程度、问题和建议，并定义解析失败、读取失败和规则误报的可观测状态。
- **退役方向**：当规则已迁入活跃审查链且 Skill 文档改为真实 API 后，目标文件整体退役；当前阶段保留档案以记录双轨关系和迁移风险。
