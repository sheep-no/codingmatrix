# error_recovery.py（子包）演化深扫文档

> 版本：v0.1 | 扫描日期：2026-08-05 | 状态：已完成
> 归属：Agent 引擎 / 测试失败自动修复闭环（orchestrator 子包）
> 路径：`app/agent/orchestrator_generation/error_recovery.py`（33 行）
> 索引：[TASKS.md](../TASKS.md)

## 1. 模块作用与功能

核心职责：**ErrorRecoveryMixin**——测试失败后的 ReAct 自动修复入口：

1. `_try_react_auto_fix`（:9-33）：动态测试失败时，构造 ReActAgent（max_iterations=5）→ `process` 修复 → 成功后重新跑动态测试 → 返回 `{"fixed": bool, "test_results": ...}`

## 2. 依赖与被依赖（跨模块引用链）

### 2.1 依赖

| 依赖 | 用途 |
|------|------|
| ReActAgent / ReActResult（react_agent.py:17/:44） | 自动修复执行 |
| IsolatedTestRunner（test_runner.py:16） | 复测 |
| `self.error_recovery`（ErrorRecoveryLoop，顶层 error_recovery.py:797，mixin.py:90 构造） | 门控判断（对象真值） |
| `self.reviewer` / `self.model_assignment` / `self.api_key_token` | 门控与模型选择 |

### 2.2 被消费方

- **orchestrator_generation/mixin.py:19/:30** 继承 ErrorRecoveryMixin（orchestrator 主 Mixin 组合）
- **traditional_generate.py:297** `_try_react_auto_fix` 唯一调用方：动态测试失败 → 尝试 ReAct 修复 → 成功则替换 test_results（:298-300）

### 2.3 测试覆盖

- **零覆盖**：test_error_recovery.py 测的是**顶层 ErrorRecoveryLoop**（`from app.agent.error_recovery import ErrorRecoveryLoop`），子包 ErrorRecoveryMixin 无任何测试

## 3. 已探明 Bug（含 bug 代码）

### ERR1 [P1] process context 传参被 ReActAgent 忽略——project_path 恒空

- **Bug 代码**：

```python
# error_recovery.py:26 - 传入 context 但 ReActAgent.process 不消费
result: ReActResult = await react_agent.process(task_description, {"project_path": str(self.output_dir)})
```

- **根因**：react_agent.md RA2 已证——`process` 的 context 参数未使用（react_agent.py:149 `project_path=""` 固定）；此处传入的 `{"project_path": str(self.output_dir)}` **实际不生效**
- **影响**：ReActEngine 收到 project_path="" → RE1 空串短路（react_engine.py:344）→ 修复闭环退化为单次 LLM 调用，工具不可用

### ERR2 [P1] `if result.success:` 恒 False（RE1 连锁）→ 自动修复完全失效

- **Bug 代码**：

```python
# error_recovery.py:27-30 - 短路路径下 success 恒 False
result: ReActResult = await react_agent.process(...)
if result.success:                     # ← 恒 False（RE1 短路）
    test_runner = IsolatedTestRunner(self.output_dir)
    new_test_results = await self._run_dynamic_tests(test_runner)
    return {"fixed": new_test_results.get("success", False), ...}
# :33 直接 return None
```

- **根因**：react_engine.md RE1 已证——project_path 空串短路时 ReActResult.success 恒 False（单次 LLM 输出不设 success）
- **影响**：即使 LLM 输出修复代码，`_run_dynamic_tests` 复测永不执行，`_try_react_auto_fix` 恒返回 None → traditional_generate.py:298 `if react_result and react_result.get("fixed")` 恒不成立 → **测试失败自动修复功能完全失效**
- **交叉回注（2026-08-09 支撑模块深扫）**：即使 ERR1/ERR2 修复打通，`_run_dynamic_tests` 复测结果仍依赖 framework_detector + output_parser 解析栈——该栈存在 FD1-FD3（JS 系误判 jest、vitest→jest_json 全 0）、OP1-OP4（pytest 真 XML 全 0、JUnit skipped 虚高、Go panic 漏报）失真，「fixed」判定可能建立在失真解析上（叠加影响，优先级低于 ERR1/ERR2）。

### ERR3 [P2] 所有失败路径吞错返回 None

- **Bug 代码**：:31-32 `except Exception as e: logger.warning(...)` + :33 `return None`——调用方（traditional_generate:298）无法区分「未尝试修复」与「修复失败」，连 warning 都只能靠日志

### ERR4 [P2] `self.error_recovery` 门控语义混乱

- **Bug 代码**：:10 `if not self.error_recovery or not self.reviewer:`——`self.error_recovery` 是 ErrorRecoveryLoop 对象（mixin.py:90），**对象恒真值**，判断实际只依赖 `not self.reviewer`——「错误恢复开关」与「对象存在性」混淆，配置关掉 error_recovery 也不会停用此路径

### ERR5 [P2] 修复路径无总超时

- **Bug 代码**：:21 max_iterations=5——有效路径下 5 轮 × 每轮 4 次 LLM 调用（specialist_base SB1），无总超时控制——传统生成路径测试修复可能长时间阻塞

### ERR6 [P3] fallback_model 硬编码兜底

- **Bug 代码**：:20 `fallback_model or "Qwen/Qwen3-8B"`——绕过 dynamic_model_router 配置链（与 _DEFAULT_ROLES fallback 一致但硬编码）

## 4. 潜在问题与未知点

- 顶层 `app/agent/error_recovery.py`（797 行 ErrorRecoveryLoop）**不在 13 模块索引内**但被 mixin.py:90 构造——为 §13 修复闭环的另一半，后续补扫时纳入
- `failed_tests[:5]` + `test_logs[:500]` 截断（:25）——长日志时修复上下文不足

## 5. 修改建议（改什么 → 达成什么目的）

| # | 优先级 | 修改动作 | 达成目的 | 涉及位置 | 对应 Backlog |
|---|--------|---------|---------|---------|-------------|
| 1 | P1 | ERR1+ERR2：修复 ReActAgent.process 消费 context（RA2），打通 RE1 短路——本模块是 RA2/RE1 链在生产端唯一显式传入 project_path 的位置，修复从源头生效 | 自动修复闭环真实可用 | error_recovery.py:26（根因在 react_agent.py:149） | 关联 #16(RE1)/#13(RA2) |
| 2 | P2 | ERR4：error_recovery 改为显式布尔开关（配置项） | 门控语义正确 | error_recovery.py:10 | 新增 |
| 3 | P2 | ERR5：process 增加总超时（asyncio.wait_for） | 防阻塞 | error_recovery.py:26 | 新增 |
| 4 | P2 | ERR3：失败返回结构化信息（未尝试/失败原因） | 调用方可感知 | error_recovery.py:33 | 新增 |

## 6. 演化方向关联

- **§13 修复闭环终结确认**：`_try_react_auto_fix` 是 RA2/RE1 链的**生产端收尾**——react_agent 传空 context → react_engine 空串短路 → success 恒 False → 此处修复失效。链路四段（error_recovery:26 → react_agent:149 → react_engine:344 → error_recovery:27）全部打通确认，单一根因在 react_agent:149
- **模块索引第 13 个完成**：13/13 深扫收尾，顶层 error_recovery.py（797 行）留待后续补扫
- **Backlog 关联**：#13-#18（RA/RE 系列），新增 ERR2-ERR5
