# CriticalDecisionExtractor 深扫（critical_decision.py，332 行）

> 第七十七轮推演 | 2026-08-13 | 定位：spec_first 链的「用户决策」交互层（生成链路中唯一等待用户实时输入的点）

## 1. 模块定位

CriticalDecisionExtractor 在需求分析完成后，从架构设计中提取 1-3 个关键架构假设（认证/数据库/API 风格/前端框架等），以选择题形式等待用户 30 秒决策，声称「将用户选择注入后续生成 prompt」（docstring :4-11）。7 类硬编码决策模板 + 不确定性启发式提取。

### 依赖链

| 方向 | 模块/位置 | 说明 |
|------|-----------|------|
| 消费方 | `spec_first_generate.py:165-187` | extract_from_architecture → format_as_questions → apply_user_choice（**生产活跃**，非死代码） |
| 消费方 | `spec_first_generate.py:795` | get_all_choices → ArchitectureInspector（检查基准） |
| 消费方 | `spec_first_generate.py:842` | ctx metric critical_decisions（结果面板） |
| 回调注入 | `orchestrate_endpoints.py:740-761` | decision_callback SSE 推送 + asyncio.wait 等待用户 HTTP 提交（:1430-1432 put） |

## 2. 深扫发现

### P2 项

- **CD1 用户决策从未注入生成 prompt（核心闭环断裂，docstring 与实现不符）**——`get_decision_context_for_prompt`（:303-320，docstring 声称的核心能力「将用户选择注入后续生成 prompt」的唯一实现）**全库零消费方**。实测链路：用户 120 秒等待窗口内的决策经 apply_user_choice 记录后，只流向 ① `get_all_choices()` → ArchitectureInspector（:253/:396/:397 仅作为**事后检查基准**，不改变生成内容）② ctx metric（结果面板展示）。**生成文件阶段的 prompt 从未收到用户决策**——用户耗时选择 JWT/PostgreSQL 等对生成结果零影响。这是生成链路中「用户输入收集了但未生效」的又一实例（UPL1 用户偏好从未注入同族）。
- **CD2 超时/异常/空决策路径全部静默丢弃，不填默认值（实测）**——spec_first_generate:189-194 三个分支（空决策/120s 超时/异常）只 logger.warning 后 continue，**从不调用 `skip_remaining_decisions`**（:326-332，唯一「使用默认值」路径，本身也零消费方）→ 实测超时后 `get_all_choices()` 恒返回 {} → ArchitectureInspector 拿空 dict 全走内置默认。docstring 声称「超时使用默认值继续」（spec_first:192/:194 日志文案），实际是**静默丢弃**而非使用默认值——决策功能的降级路径语义不符。

### P3 项

- **CD3 `_analyze_uncertainty` 子串/条件启发式误判**——tech_stack list 分支 `" ".join(...).lower()` 后子串匹配（:191-203）：`"auth" not in tech_stack_str` 遇 "fastauth"/"authlib" 等子串误判已选、`"rest"` 遇 "restful" 误判 API 风格已定；dict 分支要求 `tech_stack.get("auth_explicit")` 等特定键（:205-217），架构师输出通常无这些键 → 恒判定需要 auth/database 决策，提取结果依赖架构师输出的键命名。
- **CD4 DecisionCategory 枚举 8 类 vs 模板 7 类不一致 + 死模板**——枚举含 `deployment_mode`（:29）但 DECISION_TEMPLATES（:61-135）无对应模板 → `DecisionCategory(deployment_mode)` 只在 extract 命中模板时调用，永不触发；且 `_analyze_uncertainty`（:178-219）只产出 auth/database/frontend/architecture/api 五类，`state_management`/`caching_strategy` 两个模板**永不被产出**（死模板）。
- **CD5 `apply_user_choice` 不校验选项合法性**——:265-294 任意 choice 字符串都接受并写入 user_choices（即使不在 decision.options 中），前端/API 提交任意值即可注入；`_identify_impact_files` 用子串匹配路径（:244 `keyword in path`）→ "auth" 误匹配 "authorization.py" 等。
- **CD6 决策状态仅内存、每请求新建实例不持久化**——spec_first_generate:165 每轮请求新建 extractor，self.decisions/self.user_choices 纯内存 → 断点续传/多轮生成决策丢失，与 SM2/SM3（会话状态不持久化）同族。

## 3. 演化方向

### 3.1 决策闭环的接线语义

CD1 是核心问题：决策提取→提问→记录全流程生产活跃，但**记录结果从未回注生成 prompt**。接线路径：apply_user_choice 后 → 决策上下文拼入后续文件生成 prompt（每个文件 prompt 或全局约束，参照 GlobalConstraintParser 的 constraint_prompt 注入模式 spec_first:208-209）。这与 UPL2（默认值当偏好）构成用户个性化输入域的两端缺口：UPL 应注入生成默认偏好、CD 应注入本轮明确选择。

### 3.2 与约束体系的收敛

GlobalConstraintParser（同链路 :161-162）已建立「解析需求 → 生成 prompt fragment → 注入」的成熟模式，CD 应复用该模式（决策也本质是用户约束）。CD5 校验与 CD4 模板对齐是接线前置项。

## 4. 主线关联

- **用户输入「收集了未生效」家族**：CD1（决策未注入）+ UPL1（偏好未注入）——两条用户输入通道都断了，生成侧从未收到用户个性化/明确选择
- **降级路径语义不符**：CD2「宣称用默认值实际静默丢弃」与 DMR1（配置失败静默降级）、MEM1（embedding 失败静默回退）同族
- **启发式误判**：CD3（子串）+ UPL6（框架词）+ LD1/LD2（语言检测）同族

## 5. 测试状态

无 critical_decision 专项测试；tests/test_agent_stream_monitor.py 只覆盖 SSE 事件 passthrough（orchestrate_endpoints 层），extractor 本身的提取/应用逻辑零覆盖——CD1/CD2 从未被测试暴露。
