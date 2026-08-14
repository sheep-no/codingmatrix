# json_parser.py 深扫详档

> 版本：v1.67 | 日期：2026-08-09 | 文件：`app/agent/json_parser.py`（345 行，`_JsonParser` 内部类 + 4 个模块函数 + 模块级单例）
> 结论：**P2 2 项（JP1/JP2 实测）、P3 3 项**｜单元测试：test_json_parser.py 40 用例 + test_json_parsing.py（较全，但存在测试固化错误预期）

## 定位

全库统一 JSON 解析层：5 层解析链（thinking 清理 → 直接解析 → 花括号提取+格式修复 → 状态机截断修复 → json_repair 兜底），设计意图是「替代所有文件自行实现的 JSON 解析」。`safe_parse_json`/`parse_tool_call`/`extract_json_field` 被 11 个生产文件消费（spec_first_generator/task_planner/ppt_agent/architect/react_engine/ai_reviewer/specialist_base/cross_validator/Aicode 等）。

## 跨模块引用链

| 方向 | 模块 | 位置 | 用途 |
|------|------|------|------|
| 被消费 | react_engine.py | :194/:282 `safe_parse_json`（经 self.json_parser） | ReAct 决策/工具调用 JSON 解析 |
| 被消费 | task_planner.py | :109 `safe_parse_json` | 规划 JSON |
| 被消费 | spec_first_generator.py | :457-459 | OpenAPI 步骤结果解析 |
| 被消费 | architect.py | AR3 降级链上游（LLM 输出解析） | 架构 JSON |
| 被消费 | cross_validator.py / ai_reviewer.py | judge/审查结果解析 | 验证结果 |
| 被消费 | specialist_base.py / ppt_agent.py / Aicode.py | — | 各角色 JSON 输出 |
| 依赖 | json_repair（可选导入，HAS_JSON_REPAIR） | :19-23 | 层 5 兜底 |
| 测试 | tests/unit/test_json_parser.py（40 用例）+ test_json_parsing.py | — | **用例全在「顶层是 dict/list」假设下；截断用例把补全当期望行为** |

## 关键代码路径

`safe_parse_json`（:86）：strip → 层 1 `_clean_thinking`（只认 `<think>`）+ `_extract_code_block` → 层 2 `json.loads` → 层 3 `{`..`}` 提取 + `_apply_common_fixes` → 层 3b `[`..`]` → 层 4 `_fix_truncation`（状态机补括号）→ 层 5 json_repair。`parse_tool_call`（:136）3 策略。模块级单例 `_get_parser`（:30）。

## Bug 清单

### P2

**JP1 [P2] 顶层标量 JSON 不 raise、直接返回非 Dict/list，违反「Raises ValueError」契约（实测）**

- 位置：层 2 `:97 return json.loads(text)`——`json.loads("null")` 合法返回 None、`"123"`→123、`"true"`→True、`'"abc"'`→'abc'，直接穿透 5 层链返回；docstring（:46-48）声明「Raises ValueError: 无法解析」但**「能解析成标量」≠「解析成 Dict/list」**
- 实测：
  ```
  safe_parse_json('null')  -> None  type=NoneType  （不 raise）
  safe_parse_json('123')   -> 123   type=int       （不 raise）
  safe_parse_json('true')  -> True  type=bool      （不 raise）
  safe_parse_json('"abc"') -> 'abc' type=str       （不 raise）
  extract_json_field('null','a',default='D') -> 'D'  # .get AttributeError 被宽 except 吞
  ```
- 影响：调用方若 `data = safe_parse_json(...)` 后直接 `data.get(...)`（无 isinstance 检查）→ AttributeError；extract_json_field 用 `except (ValueError, Exception)`（:78）宽吞返回 default——**顶层 null/标量被静默当「字段缺失」**，错误信息丢失。11 个消费方按 Dict/list 假设使用，标量穿透时语义漂移
- 修复方向：层 2/3/4/5 返回前统一校验 `isinstance(result, (dict, list))`，否则抛 ValueError（契约收口）

**JP2 [P2] 截断修复静默补全、返回不完整数据当完整（实测）+ 测试固化错误预期**

- 位置：`_fix_truncation`（:291-333）——状态机数括号/引号，`stack` 非空时 `text += ''.join(reversed(stack))`（:327-328）补全后 `json.loads` 成功即返回；**无任何「截断已发生」标记**
- 实测（LLM 输出在任意处截断都静默成功）：
  ```
  '{"tool": "read_file", "params": {"path": "x"'  -> {'tool':'read_file','params':{'path':'x'}}
  '{"files": ["a.py", "b.py"'                     -> {'files':['a.py','b.py']}
  ```
  字段值中途截断时补全后**值不完整但解析成功**（如 `'{"name": "hello wo'` → `{"name": "hello wo"}`）
- 影响：LLM 输出被 max_tokens 截断 → 半份 JSON 当完整架构/工具调用/审查结果用——**「存在≠正确」主线的解析端实例**；消费方（react_engine 工具调用、architect 架构、cross_validator judge）拿截断数据继续执行，字段级丢失零提示
- **测试固化**：test_truncated_json_object（:74-78）断言 `{"key": "value", "nested": {"a": 1` → dict 且只验部分字段——把「截断补全」当期望行为而非风险（TR2 同款「测试固化错误预期」家族）
- 修复方向：截断修复返回时携带「已截断」标记或对比原始文本结构；消费方对修复结果做完整性断言（必需字段存在性），截断场景触发重试而非静默接受

### P3

**JP3 [P3] `<thinking>`/`<thought>`/`<reasoning>` 变体标签不清理（实测）**

- `_clean_thinking`（:193-195）只认 `<think>.*?</think>`。实测 `'<thinking>let me check</thinking>{"a": 1}'` 层 1 不清理、层 2 失败、**层 3 的 `{`..`}` 提取救回**——依赖「提取最外层花括号」间接兜底，但数组 JSON/无花括号场景（thinking 变体 + `[...]`）仍受影响；DeepSeek 系模型常用 `<thinking>`

**JP4 [P3] 模块级单例 `_parser_instance` 无锁**

- `_get_parser`（:30-34）懒加载无锁；asyncio 单线程下安全，多线程/多事件循环（ERL5/MCP1/SM1 家族）下重复实例化无一致性保证

**JP5 [P3] `extract_json_field` 宽异常吞错**

- `except (ValueError, Exception)`（:78）`Exception` 已含 ValueError，冗余；且吞掉标量返回时的 AttributeError（JP1 关联），调用方无感知

## 与既有主线闭环

- **「存在≠正确」主线**：JP2 截断静默补全是解析端失真——与 TR1（无测试=通过）、CV2/RL3（轻量验证）、UT5（验证空转）同属「结果看起来成功但内容不完整」家族，构成解析端的又一实例
- **验证栈**：cross_validator/ai_reviewer/architect 的 LLM 结构化输出解析全部经 safe_parse_json——JP1/JP2 的返回契约问题直接决定验证结果可信度；§5.6 支柱 2（验证器协议）的解析基础
- **契约主线**：docstring「Raises ValueError」与实际行为（标量穿透）不符是「文档-实现契约漂移」又一例（AR3/OP8/SFG1 家族）；**json_parser 设计意图是「统一解析层」，消费方仍有 ppt_agent:675/GirlAi:511 等下标解析（Aicode 家族）未收敛至此——统一层存在但未全量接线**
