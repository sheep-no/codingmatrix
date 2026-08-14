# ArchitectJsonParser 深扫（architect_json_parser.py，15 行）

> 第七十轮推演 | 2026-08-09 | 定位：json_parser 的向后兼容包装层

## 1. 模块定位

纯转发包装类：`ArchitectJsonParser.safe_parse_json` 直接调用 `json_parser._get_parser().safe_parse_json`（:14-15）。实现已迁移到 json_parser，本模块仅为兼容旧导入路径保留。自身无任何独立逻辑，**全部语义缺陷继承自 json_parser（JP1-JP5）**。

### 依赖链

| 方向 | 模块/位置 | 说明 |
|------|-----------|------|
| 依赖 | `json_parser._get_parser()`（:8） | 单例转发，继承 JP1-JP5 |
| 被消费 | `architect.py:11/:21/:265/:363/:419` | 架构生成链，`_safe_parse_json` 直接转发无类型检查 |
| 被消费 | `react_engine.py:17/:118/:194/:282` | 有 `isinstance(result, dict) and "tool" in result` 保护（安全） |
| 被消费 | `ppt_agent.py:18/:182/:256` | 无保护，`_validate_outline` 假设 Dict |
| 测试 | `test_review_result_parsing.py:24/:95`、`test_orchestrator.py:12/:130-170` | 7 处用例 |

## 2. 深扫发现

### P2 项

- **AJP1 包装层无类型保护 → JP1 顶层标量穿透生成链（实测确认）**——architect.py `_safe_parse_json`（:419-422）直接转发 `safe_parse_json` 且返回类型标注 `-> Dict`，但调用方 architect.py:265 后 `isinstance(architecture, list)` 之外直接 `architecture["project_type"]`（:277）——实测 `safe_parse_json('null')` 返回 None 后 `architecture["project_type"]` 抛 **TypeError: 'NoneType' object is not subscriptable**；ppt_agent.py:183 `data = parser.safe_parse_json(raw)` 后 `_validate_outline` 内 `data.get("slides", [])`（:258）抛 **AttributeError: 'NoneType' object has no attribute 'get'**，且外层 `except ValueError`（:186）捕获不了 AttributeError → 未处理崩溃（LLM 输出 `null`/`123`/`"文本"` 时架构生成/PPT 生成直接崩）；react_engine.py:194-201 因有 isinstance 检查而幸免。**JP1 的 12 个消费方中，本模块经 architect/ppt_agent 两条路径把「顶层标量不 raise」放大为生成链崩溃**——JP1 修复优先级应包含此层契约（safe_parse_json 返回非 Dict 时下游 TypeError/AttributeError）。修复方向：包装层不解决根本问题，JP1 修 raise + 下游调用方按 Dict 断言，二者都做。

### P3 项

- **AJP2 迁移未完成的双入口并存**——architect/react_engine/ppt_agent 仍经 ArchitectJsonParser 包装，而 refinement_loop/cross_validator 等直接消费 json_parser——同一解析能力两个导入路径。未来 JP1 修复为 raise 后，消费方行为取决于走哪条路径，行为分裂。迁移完成标志：删除本包装、消费方全部改 `from app.agent.json_parser import safe_parse_json`。
- **AJP3 经包装二次引用 `_get_parser()` 无锁单例**（json_parser JP4 同族）——包装层转发本身不引入新问题，但让单例被引用面扩大。

## 3. 演化方向

本模块是「存在即技术债」的迁移中间态。演化终点：删除文件、统一消费方导入 json_parser 公共 API。在此之前的唯一有效动作是 AJP1——让 architect/ppt_agent 消费方对解析结果做 Dict 类型断言，使「不 raise」的解析器不把 null/标量漏进生成链。**在 JP1 修复前，本层是唯一能低成本兜底的位置**（一处包装内加类型校验即可覆盖 architect/react_engine/ppt_agent 全部消费方）。

## 4. 主线关联

- **「存在≠正确」解析端主线**：AJP1 证明 JP1 已从「解析器语义问题」放大为「生成链崩溃」——三消费方两处崩溃一处安全，语义失真的传播路径完整（JP1 解析 → AJP1 传播 → architect/ppt 崩溃）
- **双轨/并存主线**：AJP2 与 CR1（三套审查三轨契约）、三套 API 契约校验同族——同一能力多路径并存

## 5. 测试状态

`test_orchestrator.py:130-170` 7 处用例全部测「合法 dict JSON 解析成功」路径，无一覆盖 null/标量顶层 JSON 的下游行为——JP1 语义从未被测试暴露；`test_review_result_parsing.py:95` 测 Pydantic 集成，同无异常路径覆盖。
