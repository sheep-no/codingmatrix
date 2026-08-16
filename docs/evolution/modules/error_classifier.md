# ErrorClassifier 深扫（error_classifier.py，196 行）

> 第九十八轮推演 | 2026-08-16 | 定位：错误消息 → 错误类型/修复策略的分类器（规则匹配 + LLM 兜底），error_recovery 活跃消费

## 1. 模块定位

错误恢复链的错误分类前端：把错误消息归为 8 种预定义类型（NameError/AttributeError/ImportError/SyntaxError/TypeError/KeyError/IndexError/LogicError）并输出修复策略。

- `ERROR_PATTERNS`（:26-95）：8 类型的正则规则，`_rule_based_classification` 用 `re.search(pattern, message, re.IGNORECASE)` 按 dict 顺序匹配
- `classify_error`（:100-108）：规则优先 → 规则不中走 `_model_based_classification`（LLM）
- `_model_based_classification`（:126-182）：LLM 分类，`re.search(r'\{.*\}', content, re.DOTALL)` 提取 JSON，失败兜底 LogicError confidence=0.5
- `get_fix_strategy_by_type`（:184-188）：按类型取策略（**生产零消费**）
- `add_to_history`（:190-192）：追加到 `classification_history`（**全库零读取**）
- 模块级全局单例 `error_classifier`（:196）

**活跃生产模块**，唯一生产消费方 error_recovery：

- `error_recovery.py:201`：`classification = await error_classifier.classify_error(error_messages, content)`——`error_messages` 为 `"; ".join(self._extract_error_messages(errors))`（:200），拼接最多 7 类错误（syntax/import/dependency/runtime/api/frontend/cross_file）
- `error_recovery.py:203-204`：`strategy_evaluator.get_strategy_template(classification.error_type)`——**分类结果直接决定修复策略模板**
- `error_recovery.py:202`：`error_classifier.add_to_history(classification)`——每修复循环追加历史
- `fix_pattern_cache.py:19`：仅 import `ErrorClassification` 类型

### 依赖链

| 方向 | 模块/位置 | 说明 |
|------|-----------|------|
| 消费方 | `error_recovery.py:201-204` | `classify_error` 结果 → 策略模板选择（活跃） |
| 消费方 | `error_recovery.py:202` | `add_to_history` 追加（活跃但历史无读取方） |
| 消费方 | `error_recovery.py:307/:374` | 拼接错误消息作记录（同样走 `"; ".join`） |
| 依赖 | `app/utils/__init__.py` | `call_llm` |
| 依赖 | `app/agent/models.py:67` | `DEFAULT_CODE_MODEL = "nex-agi/Nex-N2-Pro"`（注释声称 qwen3.5-4b 不符） |
| 测试 | `tests/unit/test_error_classifier.py`（91 行 9 用例） | 全绿，但全走规则路径，模型路径零覆盖 |

## 2. 深扫发现

### P2 项

- **EC1 [P2] 多错误拼接 + dict 顺序匹配使分类与实际错误顺序脱节（实测）**——`error_recovery:200` 用 `"; ".join(_extract_error_messages(errors))` 拼接最多 7 类错误，`_rule_based_classification` 对整段拼接串按 ERROR_PATTERNS **dict 顺序**（NameError→AttributeError→ImportError→SyntaxError→TypeError→KeyError→IndexError→LogicError）做 `re.search` 找第一个匹配——**返回类型由 dict 遍历顺序决定，与实际首个错误无关**。实测 `"TypeError: 'int' object is not subscriptable; NameError: name 'x' is not defined"` → 返回 **NameError**（dict 中 NameError 排 TypeError 前），而实际首个错误是 TypeError。`error_recovery:203-204` 用 `classification.error_type` 查策略模板 → 类型误判直接导致修复策略模板选错。
- **EC2 [P2] 规则覆盖缺口 + LogicError 规则中文不可达（实测）**——模式要求精确格式，常见变体漏检：`KeyError: 5`（数字键）不匹配 `r"KeyError: '(\w+)'"`、`name x is not defined`（无引号）不匹配 `r"name '(\w+)' is not defined"`，实测全部返回 None → **大量真实错误落入 LLM 兜底**（每次修复循环一次 LLM 调用，成本 + 延迟）；且 LogicError 的 pattern 是**中文**（"逻辑错误"/"业务逻辑错误"/"预期结果与实际不符"），英文错误消息永不命中——8 类型规则中 LogicError 规则实际不可达，规则路径有效类型实为 7 种。
- **EC3 [P2] 模型分类失败全兜底 LogicError confidence=0.5（实测三路径）**——`_model_based_classification` 中三类失败全部静默降级：(1) 缺字段 JSON → `ErrorClassification(**result_dict)` 抛 TypeError 被 :172 except 吞；(2) 多 JSON 块 → `re.search(r'\{.*\}', content, re.DOTALL)` 贪婪跨块匹配到解释文本，json.loads 抛 "Extra data"；(3) 非 JSON 文本 → json_match 为 None 跳过。三类失败全部返回 LogicError confidence=0.5，而 LogicError 的 fix_strategy 是「使用 deepseek-r1 深度分析错误信息，重新生成核心逻辑」（:93）——**分类失败被伪装成「业务逻辑错误」且策略指向与 DEFAULT_CODE_MODEL 不符的模型**，误导修复方向（DGV1「验证失败兜底通过」家族在分类器的镜像）。
- **EC4 [P2] `classification_history` 只写不读死数据 + 全局单例无界增长（全库确认）**——`add_to_history`（:190-192）被 error_recovery:202 每修复循环调用，但**全库零读取方**（rg 确认仅 :98/:192 两处，无 get/消费），历史数据收集后从未用于任何决策；且模块级全局单例 `error_classifier`（:196）被 error_recovery 每次引用，`classification_history` 无上限增长——长会话修复循环多时内存持续累积，且全局单例跨请求共享（SM1/MCP1 单例家族）。

### P3 项

- **EC5 [P3] confidence 语义三轨不可比**——规则路径固定 0.95（:121）、模型路径透传 LLM 未校验 confidence（实测 0.9 透传，LLM 返回 5.0 也直接透传）、模型失败兜底固定 0.5——三条路径的 confidence 口径不一致，下游无法据此做阈值决策。
- **EC6 [P3] 注释与实现不符（qwen3.5-4b vs DEFAULT_CODE_MODEL）**——:127 docstring 声称「使用 qwen3.5-4b」，实际 `model=DEFAULT_CODE_MODEL`（models.py:67 Nex-N2-Pro）；LogicError fix_strategy（:93/:180）声称「使用 deepseek-r1 深度分析」与 DEFAULT_CODE_MODEL 也不符——注释描述的是旧方案，模型与策略声明全部漂移。
- **EC7 [P3] 测试弱断言 + 模型路径零覆盖**——`test_classify_name_error` 用 `if hasattr(result, 'error_type')` 条件断言（result 无 error_type 属性时跳过断言，测试仍通过！）；`test_classify_basic` 只断言 not None；9 用例全绿但**全部走规则路径**，`_model_based_classification` 无任何用例（LLM 路径零覆盖），EC1/EC3 实测可复现但无保护（DR8/TR2 弱断言家族）。
- **EC8 [P3] `get_fix_strategy_by_type` 生产零消费死方法**——仅测试引用（test_error_classifier.py:66/:73），error_recovery 用 `strategy_evaluator.get_strategy_template` 而非本方法——方法与模块主消费方脱节（GC6/SCT5「能力未接线方法级」家族），且与 ERROR_PATTERNS 内 fix_strategy 同源重复。

## 3. 演化方向

分类器是错误恢复链的**策略选择输入端**，规则与 LLM 双轨并存但两条路径都有失真：
- **匹配语义（EC1/EC2）**：多错误拼接后按 dict 顺序匹配应改为「按错误出现顺序逐条分类」或「逐条分类后合并」；模式应覆盖常见变体（无引号/数字键），LogicError 中文规则改为英文可达或直接交给 LLM。
- **失败语义（EC3）**：LLM 分类失败兜底 LogicError 与 DGV1 同族——应区分「分类成功但低置信」与「分类失败」，失败时不伪装成业务逻辑错误（可选：返回 confidence 极低的 LogicError 或 None 触发上游降级）。
- **数据消费（EC4）**：classification_history 要么被读取（如供重复错误去重/策略学习），要么删除——当前只写不读是无界内存。
- **策略选择对齐（EC8）**：`get_fix_strategy_by_type` 与 `strategy_evaluator.get_strategy_template` 双实现应收敛（error_recovery 用后者），注释同步到 DEFAULT_CODE_MODEL（EC6）。

**修复优先级**：EC1（分类类型误判 → 策略模板选错）> EC2（规则缺口 → LLM 兜底成本）> EC3（分类失败伪装 LogicError 误导修复）> EC4（死数据无界增长）> EC5（confidence 三轨）> EC7（测试盲区）> EC6（注释漂移）> EC8（死方法收敛）。

## 4. 主线关联

- **「失败兜底掩盖错误」家族**：EC3 与 DGV1（验证失败兜底 passed=True）、FE1（fallback 兜底让「检测」用例恒过）同族——分类失败被伪装成「业务逻辑错误」，且带误导性 fix_strategy；EC1 的 dict 顺序匹配是「顺序语义丢失」家族（DR6 endswith 顺序、dependency_rules 匹配顺序）在分类器的实例。
- **「存在≠正确」**：EC4（classification_history 只写不读，数据存在无消费）与 SC1/OP3 同族；EC8（方法存在零消费）与 SCT5/UPL1 同族。
- **错误恢复链输入失真**：error_recovery 是修复循环执行器（RL1 空操作 + RL3 轻量成功），其策略选择依赖 `classification.error_type`——EC1/EC2/EC3 三项 P2 使**策略选择的输入端已失真**，与 RL 详档「修复循环验证端只有语法级」叠加，错误恢复链从分类到验证两端都不可靠。
- **单例/共享状态**：EC4 全局单例无界增长（SM1/MCP1/CS7 家族）。

## 5. 测试状态

**规则路径弱覆盖、模型路径零覆盖**——91 行 9 用例全绿，但全部走规则路径：`test_classify_basic`/`test_classify_name_error` 只断言 not None + `if hasattr(result, 'error_type')` 条件断言（无属性即通过）；`test_add_to_history` 断言 `hasattr(classifier, 'add_to_history')` 而非行为（方法存在即通过）；**`_model_based_classification` 无任何用例**（LLM 路径零覆盖）。EC1（拼接顺序误判）、EC2（变体漏检）、EC3（三路径兜底 LogicError）全部实测可复现但零用例保护——测试固化「分类器存在」而非「分类正确」（TR2 家族）。
