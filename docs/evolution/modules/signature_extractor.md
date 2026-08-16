# SignatureExtractor 深扫（signature_extractor.py，251 行）

> 第九十六轮推演 | 2026-08-16 | 定位：从源代码文件提取函数/类签名与类字段，供依赖上下文注入，dependency_graph 链活跃消费

## 1. 模块定位

从生成文件的源码中提取类定义、类字段、类方法签名、顶层函数签名（不包含函数体），失败时返回 None（调用方退化为截断原文）。支持 8 种语言 + 冷门语言通用兜底，另导出 `get_context_budget` 按模型上下文窗口计算注入预算。**活跃生产模块**，唯一消费方 dependency_graph.py：

- `dependency_graph.py:22`：import `extract_signatures`, `get_context_budget`
- `dependency_graph.py:787`：`get_context_budget(ctx_len)` 计算注入预算（`get_context_for_file` 内，model_context_length=0 时兜底 32768）
- `dependency_graph.py:840`：`extract_signatures(dep_path, content)` 提取依赖文件签名；签名成功时 `preview=signatures`（**不按预算截断**），失败时退化 `content[:budget]`
- 下游：`orchestrator_files.py:343`、`incremental_modify.py:734/:945`、`spec_first_generate.py:407/:967/:2317` 共 5 处调用 `get_context_for_file`

### 依赖链

| 方向 | 模块/位置 | 说明 |
|------|-----------|------|
| 被消费 | `dependency_graph.py:787/:840` | `get_context_for_file` 内预算计算 + 签名提取 |
| 被消费 | `orchestrator_files.py:343` 等 5 处 | `get_context_for_file` 下游消费（依赖上下文注入） |
| 依赖 | `dependency_graph.py`（预算/截断逻辑） | 签名输出与预算约束的交互（SE2 缺陷所在） |
| 未消费 | 无 | 本模块两个导出函数均被消费 |
| 测试 | `tests/unit/test_small_model_optimization.py:188` 弱断言 | 仅断言 `"config.py" in context` 与 `"DATABASE_URL" in context`，不校验签名内容 |

## 2. 深扫发现

### P2 项

- **SE1 [P2] 类方法体内带注解的局部变量被误判为类字段且缩进丢失（实测）**——`_is_class_field` 只在类体收集模式下对 `indent > class_indent` 的行调用，但**方法体内缩进更深的行同样满足 `indent > class_indent`**，没有「当前是否在函数体内」的状态跟踪。实测 `class Order` 中 `def calc(self, n):` 内的 `x: int = n + 1` 与 `total: float = x * 2` 全部被当类字段追加，且 `result_parts.append(f"  {stripped[:200]}")` 固定 2 空格前缀使局部变量的真实缩进（8 空格）丢失——注入上下文中出现本不属于类的「字段」，污染 LLM 对类结构的认知。控制流语句（if/for/return）已被排除（:214），但带注解的局部变量赋值不在排除列表。
- **SE2 [P2] 签名文本超预算导致后续依赖全部被 break 丢弃（实测）**——`get_context_for_file` 中 `preview = signatures if signatures else content[:budget]`（dependency_graph.py:841），签名存在时**完全不按 budget 截断**，随后 `remaining_budget -= len(preview) + 50`（:846）。实测核心依赖（priority<=2 分 60% 预算）签名文本 5298 字节、预算仅 1800 字节 → `remaining_budget` 直接变负 → `if remaining_budget <= 0: break`（:847）→ 排序在后的非核心依赖 b.py 完全丢失，注入上下文只剩 1 个依赖。**签名提取的「更紧凑」承诺在依赖文件函数/类多时反而失效**——签名文本长度与预算（按窗口比例）完全脱节，预算机制被签名输出绕过。

### P3 项

- **SE3 [P3] `.pyi` stub 文件走冷门兜底路径，类字段全部丢失（实测）**——`SIGNATURE_PATTERNS` 只有 `.py` 无 `.pyi`，fallback 映射仅 `.jsx→.js`/`.tsx→.ts`（:86），`.pyi` 无法命中精确正则 → 走 `_GENERIC_DEF` 兜底（:178-198），而 `_is_class_field` 却显式支持 `.pyi`（:217）——**提取器自身对 `.pyi` 字段提取有实现但入口正则表缺失 `.pyi` 键，字段逻辑永远不可达**。实测 `class User: id: int / name: str` 仅输出 `class User`（被兜底截断在 `:`），字段全丢；`def get_name(self) -> str` 也仅截断到 `def get_name(self)`。
- **SE4 [P3] JS/TS 类方法签名完全不提取（实测）**——JS/TS 的 function pattern 只匹配 `function name(` 与 `const name = (`（:37/:41），**class 体内标准方法语法 `run(): void {}` / `constructor() {}` 不匹配任何 pattern**。实测 `export class Service` 后仅输出类名行，`run`/`constructor` 方法签名全丢——TS 类的核心 API 面在注入上下文中完全缺失。Go 方法（`:49` 支持 `func (receiver) Method(`）与 Python 方法正常，JS/TS 是 8 语言中唯一类方法语法不覆盖者。
- **SE5 [P3] 多行函数签名被截断（实测）**——`_extract_sig` 逻辑在单行内做括号深度匹配（:122-130），`def long_func(\n a: int,\n b: str,\n) -> bool:` 提取为 `def long_func(`——多行参数签名只保留到首个括号，参数列表全丢。对 Python 类型注解签名（常见多行格式化）信息损失明显。
- **SE6 [P3] 嵌套类状态错乱（实测）**——类体收集用单一 `current_class`/`class_indent` 变量无栈（:94-96），`class Outer` 内嵌套 `class Inner` 时 class_indent 被覆盖为 Inner 的缩进，之后 `def outer_method`（缩进 4 = Inner 的 class_indent）判定 `indent <= class_indent` 退出收集被当顶层函数（:152-153）——外层类方法被错误归属为顶层、嵌套类退出后状态不恢复。实测输出中外层 `outer_method` 无缩进前缀（顶层格式），类归属混乱。
- **SE7 [P3] 顶层签名/字段 `[:200]` 截断无标记（静态确认）**——:112/:134/:140/:145/:173 多处 `stripped[:200]` 与 `sig[:200]` 截断均无截断标记，下游无法感知签名信息被截断（JP2/TR2 家族）。

## 3. 演化方向

签名提取是 `get_context_for_file` 依赖上下文注入的信息压缩层，目标是用「签名而非全文」注入更精准的依赖信息，但两个 P2 缺陷使压缩失效方向相反：
- **噪声污染（SE1）**：方法体局部变量混入字段列表，注入上下文含「伪字段」——修复方向：类体收集需跟踪当前是否在函数体内（遇到方法签名行后进入函数体状态，用缩进或 `pass` 边界退出），仅收集函数外的字段行。这是「提取≠正确」在信息压缩层的实例。
- **压缩失效（SE2）**：签名输出不受预算约束，核心依赖签名溢出预算后剩余依赖全丢——修复方向：`extract_signatures` 提供 `max_chars` 参数（截断签名输出），或消费方对 signatures 也按 budget 截断（`signatures[:budget]`）。否则预算机制对「签名命中」路径形同虚设，反而不如退化路径（`content[:budget]` 至少受控）。
- **覆盖缺口（SE3/SE4）**：`.pyi` 加键映射到 `.py` 即修复字段提取；JS/TS class 方法 pattern 需补充 `methodName(` 语法（类体内特判）。这两个是纯 pattern 缺口，修复成本低收益直接。

**修复优先级**：SE2（预算失效，核心依赖挤出其他依赖）> SE1（上下文污染）> SE4（JS/TS 类方法全丢）> SE3（.pyi 字段全丢）> SE5（多行截断）> SE6（嵌套类错乱）> SE7（截断无标记）。

## 4. 主线关联

- **「存在≠正确」信息压缩层**：SE2 是预算机制的失效——签名提取「本应更紧凑」但实际可绕过预算分配，与 SC4（files_generated 恒 0 死字段）、OP1（成本恒零）同属「机制存在但语义未生效」；SE1 是「提取结果错误」而非「未提取」，与 GC1（单句多约束取第一）、MLP1（字符串误解析）同族。
- **「提取≠正确」家族**：SE1（方法体局部变量误判字段）、SE3（.pyi 字段入口不可达）与 GC2（约束提取了不进 prompt）、CD1（决策注入）同族——提取层实现与预期语义脱节。
- **JS/TS 覆盖缺口**：SE4 与 MLP5（JS 扩展名非确定）、LD（JS 检测）同族——8 语言支持声明下 JS/TS 类方法这一主流语法零覆盖，「支持 8 种语言」文档承诺（:5）与实际提取能力不符。
- **信息压缩与预算**：SE2 直接指向 DG7（上下文预算恒 32768 兜底）——签名提取是预算分配后的第二道约束，两处都失效使依赖上下文注入的实际内容不可控。

## 5. 测试状态

**近乎零测试覆盖**——`tests/unit/test_small_model_optimization.py:188` 的 `test_get_context_for_file` 仅断言依赖文件名与字符串片段存在，不校验签名提取结果、不覆盖 `extract_signatures` 直接调用。SE1/SE2/SE3/SE4/SE5/SE6 全部实测可复现但无任何用例保护；`get_context_budget` 各窗口边界（32K/64K 分档与上下限）零测试。签名提取是 dependency_graph 依赖上下文注入的唯一信息源，其正确性直接决定注入 LLM 的依赖上下文质量，当前无回归保护。
