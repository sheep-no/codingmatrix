# 顶层 ErrorRecoveryLoop 演化深扫文档

> 版本：v1.0 | 扫描日期：2026-08-05 | 状态：已完成
> 归属：Agent 大系统 / 编排层·错误恢复（补扫，不在原 13 模块索引内）
> 路径：`app/agent/error_recovery.py`（797 行）
> 索引：[TASKS.md](../TASKS.md)｜关联：[mixin.md 组装](traditional_generate.md)｜[子包 error_recovery.py（33 行）](error_recovery.md)

## 1. 模块作用与功能

- **核心职责**：智能自我修正循环——单文件验证失败后自动修复（`validate_and_fix` → `_smart_fix_loop`），以及测试失败自动修复（`fix_from_test_logs`）。含错误分类、策略模板、模型降级链
- **主要类/函数**：
  - `ErrorRecoveryLoop`（:38-797）——修复循环主类
  - `validate_and_fix`（:137-177）——单文件验证→修复入口
  - `_smart_fix_loop`（:179-391）——核心：错误分类→策略模板→最多 3 次修复尝试→逐次模型降级
  - `_evaluate_code_quality`（:393-420）——修复后质量评分（喂给 strategy_evaluator）
  - `_build_targeted_error_context`（:492-578）——针对性错误上下文（含 passlib/Middleware/MRO 等硬编码建议）
  - `fix_from_test_logs`（:659-784）——pytest 失败日志→LLM 修复→重跑测试
  - `_load_fallback_chain`（:68-110）——降级链加载（用户偏好→配置→供应商→硬编码四级）
- **对外接口**：`ErrorRecoveryLoop(validator, reviewer, api_key_token, cancel_event)`——生产使用方 `mixin.py:90`、`orchestrator.py`

## 2. 依赖与被依赖

- **导入依赖**：call_llm（直连）、CodeValidator、CodeReviewer、LayeredModelRouter、TestRunner、`error_classifier`（全局单例）、`strategy_evaluator`（全局单例）、`get_global_llm_semaphore`
- **生产使用方**：`orchestrator_generation/mixin.py:90`（`self.error_recovery = ErrorRecoveryLoop(...)`，:368 读 `self.error_recovery.fix_history`）；`orchestrator.py`（同）
- **测试覆盖**：`test_error_recovery.py` 测顶层 ErrorRecoveryLoop（? 用例）——与子包 33 行 `ErrorRecoveryMixin` 的 `test_error_recovery` 测顶层类不同，需确认是否真覆盖本模块
- **与子包 error_recovery.py（33 行）关系**：子包是编排 Mixin 的 `_try_react_auto_fix`（ERR1/ERR2 链），本模块是独立修复循环类——**两套错误恢复并存**（ERR 链用于动态测试后 ReAct 自动修复，本类用于文件级验证修复）

## 3. 已探明 Bug

### ERL1 [P2] 错误上下文构建函数重复 + `_build_error_context` 为死代码

- **Bug 代码**：

```python
# error_recovery.py:492-578 与 :580-650 两份几乎相同实现
def _build_targeted_error_context(self, errors, content, attempt, classification): ...
def _build_error_context(self, errors, content, attempt): ...   # :580 仅定义处出现，未被调用
```

- **根因**：历史演进中 `_build_error_context` 被 `_build_targeted_error_context` 取代，旧函数未删除（grep 全文件仅定义处 1 处）
- **影响**：死代码 ~70 行；两份实现后续若改其一不同步，产生语义分叉

### ERL2 [P2] 默认修复模板占位符替换不完整——`{content}`/`{suggested_fix_strategy}` 裸露注入 system_prompt

- **Bug 代码**：

```python
# error_recovery.py:422-438 默认模板含 3 个占位符
"""...【当前代码】\n```\n{content}\n```...{error_context}...{suggested_fix_strategy}..."""
# :453-454 只替换 error_context
if template and "{error_context}" in template:
    return template.replace("{error_context}", base_context)
```

- **根因**：`_build_targeted_error_context_with_template` 只处理 `{error_context}`；模板注入 system_prompt（:226-234「【修复策略】」段）时 `{content}`/`{suggested_fix_strategy}` 保持字面量
- **影响**：strategy_evaluator 返回的模板若含这些占位符、或默认模板被采用时，LLM 看到裸露 `{content}` 占位符——修复策略指令语义破损
- **验证方式**：`_smart_fix_loop` 走 `fix_template is None` 分支（:208-209）时 system_prompt 含 `{content}` 字面量

### ERL3 [P2] `_evaluate_code_quality` 临时文件泄漏（缺 finally）

- **Bug 代码**：

```python
# error_recovery.py:397-404
temp_file = file_path.parent / f".temp_quality_{file_path.name}"
with open(temp_file, 'w', encoding='utf-8') as f:
    f.write(code)
validation = await self.validator.validate_single_file(temp_file)   # 若抛异常
if temp_file.exists():
    temp_file.unlink()                                              # 不会执行 → 泄漏
```

- **对比**：`_smart_fix_loop` :290-298 正确用了 `finally` 清理；本处漏掉
- **影响**：validate_single_file 抛异常时 `.temp_quality_*` 残留项目目录

### ERL4 [P2] 修复/重试 LLM 调用不记录成本（成本恒 0 又一处）

- **Bug 代码**：`_smart_fix_loop` :257 与 `fix_from_test_logs` :716 的 `call_llm` 均无 `cost_tracker` 参数；构造 `ErrorRecoveryLoop` 时（mixin.py:90）也未传 cost_tracker
- **影响**：修复循环的 LLM 消耗不计入成本汇总——LC1（成本恒 0）的又一个贡献点（specialist 层有 cost_tracker，error_recovery 直连 call_llm 没有）

### ERL5 [P2] `error_classifier`/`strategy_evaluator` 全局单例——跨请求状态污染

- **Bug 代码**：:19-20 模块级导入单例；:202 `error_classifier.add_to_history(classification)` 写全局 history；`strategy_evaluator.record_evaluation_result`（:278/:315/:344/:361/:381）写全局策略统计
- **影响**：多用户/多请求共享错误分类历史与策略评估统计——与 MCP1 单例竞争同类；单请求内的修复会污染其他请求的策略统计

### ERL6 [P2] `fix_from_test_logs` 修复写盘不走 write_file_atomic + 无 is_valid 校验

- **Bug 代码**：:757 `target.write_text(content, encoding='utf-8')` 直接写——路径穿越校验有（:750-755）但无内容有效性校验（is_valid_code_content），坏内容直接覆盖源文件
- **影响**：LLM 返回的修复内容语法错误时直接覆盖，测试重跑才暴露——且覆盖不可回滚（对比 traditional_generate 用 write_file_atomic）

### ERL7 [P3] `_infer_source_files`（:786-797）死代码

- 仅定义处出现，`fix_from_test_logs` 实际用 LLM 推断 file_path 而非此方法——未使用

### ERL8 [P3] `_smart_fix_loop` 无总超时 / 无单文件修复成本上限

- 最多 3 次 × 每模型 max_tokens，无总时长/总 token 上限；`cancel_event` 是唯一中断手段

## 4. 潜在问题与未知点

- `_build_default_fix_template`（:422）与 `_build_targeted_error_context`（:492）的硬编码修复建议（passlib/Middleware/tokenUrl 等）——针对特定库版本，随库演进过时
- 修复后只 `validate_single_file`（:295）——单文件验证，跨文件 import 错误无法被本循环捕获（靠 cross_validator 兜底，但 error_recovery 在 cross_validator 之前执行）
- `validate_and_fix` 写临时文件 `.temp_{name}`（:149）——与项目文件同目录，git 备份/沙箱扫描可能误收录
- 与子包 ErrorRecoveryMixin（33 行，ReAct 自动修复）**职责重叠**：两套错误恢复，触发场景不同（文件级验证失败 vs 动态测试失败）

## 5. 修改建议（改什么 → 达成什么目的）

| # | 优先级 | 修改动作 | 达成目的 | 涉及位置 | 对应 Backlog |
|---|--------|---------|---------|---------|-------------|
| 1 | P2 | ERL1：删除死代码 `_build_error_context`，合并两份上下文构建为单一实现 | 消除死代码与语义分叉 | error_recovery.py:580-650 | 新增 |
| 2 | P2 | ERL2：模板替换改为统一占位符渲染（replace 全部 `{content}`/`{error_context}`/`{suggested_fix_strategy}`） | 修复策略指令完整注入 | error_recovery.py:453-454 | 新增 |
| 3 | P2 | ERL3：`_evaluate_code_quality` 临时文件清理移入 finally | 消除临时文件泄漏 | error_recovery.py:397-404 | 新增 |
| 4 | P2 | ERL4：ErrorRecoveryLoop 构造与调用点传入 cost_tracker | 修复循环成本计入汇总 | mixin.py:90、error_recovery.py:257/:716 | 新增 |
| 5 | P2 | ERL5：error_classifier/strategy_evaluator 实例化下沉到调用方或按请求隔离 | 消除跨请求状态污染 | error_recovery.py:19-20/:202 | 新增 |
| 6 | P2 | ERL6：修复写盘走 write_file_atomic + is_valid_code_content 校验 | 坏内容不覆盖源文件 | error_recovery.py:757 | 新增 |
| 7 | P3 | ERL7：删除 `_infer_source_files` | 清理死代码 | error_recovery.py:786 | 新增 |
| 8 | P3 | ERL8：`_smart_fix_loop` 加总时长/token 预算 | 修复循环有界 | error_recovery.py:211 | 新增 |

## 6. 演化方向关联

- **职责归位**：本模块与子包 ErrorRecoveryMixin（33 行 ReAct 自动修复）同属「错误恢复」域但两套实现并存——演化应收敛为统一错误恢复服务，按触发源（文件级验证 / 测试失败 / ReAct 循环）分策略
- **RE1/ERR 链关联**：子包 `_try_react_auto_fix` 调用链（ERR1/ERR2）修复后，传统链路 `traditional_generate.py:297` 的 ReAct 自动修复恢复——本模块的 `fix_from_test_logs` 与 ReAct 修复是「测试失败后两条修复路径」，需明确分工
- **基础设施**：ERL5 全局单例污染 → 对应演化蓝图「全局状态显式注入」（§1 工具层 ToolRuntime 注入方向）；ERL4 成本 → 对应 LC1 客户端收敛后统一观测层
