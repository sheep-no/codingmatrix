# OrchestratorFiles 演化深扫文档

> 版本：v0.1 | 扫描日期：2026-08-09 | 状态：已完成
> 归属：Agent 大系统 / 支撑模块（文件生成编排核心 FilesMixin）
> 路径：app/agent/orchestrator_files.py（888 行）
> 索引：[TASKS.md](../TASKS.md)

## 1. 模块作用与功能

文件生成编排核心（FilesMixin）：按文件计划生成项目文件——分小项目/依赖分层两种模式，单文件生成主流程含工程师选择、反馈预防提示注入、依赖上下文、内容提取（`extract_engineer_content` + 绝对导入修复）、无效内容恢复、HITL 审批、验证与审查、API 契约检查、反馈学习。附带 git stash 回滚、路径规范化、模型/工程师选择。

- **核心类**：`FilesMixin`（:154）。模块级工具：`_git_stash_push/pop/drop`（:36-82）、`_fix_absolute_imports`（:85 绝对导入转相对导入）、`_is_edit_marker`（:25）。
- **两种生成模式**：`_generate_files_small_project`（:156 单层并发）、`_generate_files_by_dep_layers`（:215 依赖分层并发）。
- **单文件主流程**（`_generate_single_file` :302-489）：选工程师 → prevention prompt → 依赖上下文 → engineer.generate_file → extract_engineer_content（含语言检测 LLM）→ 无效恢复（`_recover_invalid_content_orchestator` :584）→ 直连兜底（`_direct_llm_generate_file` :648）→ HITL 审批 → 验证审查（`_validate_and_review_file` :691）→ API 契约检查 → 反馈学习。
- **增量补丁**：`_apply_patches_incremental`（:787 跨文件补丁 + 逐文件补丁）。
- **选择器**：`_select_model_for_file`（:568）、`_select_engineer`（:577）、`_select_alternative_model`（:772）、`_select_engineer_for_model`（:781）。

## 2. 依赖与被依赖

- **导入依赖**：`app.utils.call_llm`（直连顶层体系）、`code_validator.CodeValidator`、`specialists`、`code_patcher.apply_incremental_change`、`complexity`、`orchestrator_progress`、`utils`（extract_engineer_content/write_file_atomic/is_valid_code_content/clean_code_block）。
- **生产使用方**：
  - `traditional_generate.py:196-198`（小项目/分层两模式入口）
  - `incremental_generate.py:21`（增量走 small_project）
  - `spec_first_generate.py:466-467/:1024-1025/:1777-1780`（`_select_alternative_model`/`_select_engineer_for_model` 3 处活跃，模型降级）
  - `mixin.py:92`（`_call_llm_for_patch` 注入 CodePatcher，定义于 orchestrator_utils.py:296）
- **被依赖**：`_validate_and_review_file` 被 spec_first 与 traditional 共用；`_fix_absolute_imports` 是 extract_engineer_content 的回调。
- **测试覆盖**：无 direct 测试文件（rg tests/ 无 orchestrator_files/FilesMixin 引用）——**零测试覆盖**。

## 3. 已探明 Bug

### OF1 [P2] `_validate_and_review_file` 直接操作 validator 私有缓存 + 只做 ast.parse 简化验证

- **Bug 代码**：

```python
# orchestrator_files.py:700-702 - 读 CodeValidator 私有内存缓存
content_hash = CodeValidator._compute_content_hash(content)
cache_key = f"{file_path}:{content_hash}"
cached_result = self.validator._validation_cache.get(cache_key) if self.validator else None

# :750-758 - 只 ast.parse，写私有缓存，绕过 validator 正式接口
if self.validator and file_path.endswith('.py'):
    ast.parse(content)
    self.validator._validation_cache[cache_key] = {"is_valid": True, ...}
```

- **根因**：FilesMixin 用**自建缓存 key（`{file_path}:{hash}`）直接读写 `CodeValidator._validation_cache` 私有 dict**，与 CodeValidator 正式接口（get_cached_validation/run_full_validation，CV1 的文件系统缓存体系）**双缓存并存且互不通**。验证逻辑只有 ast.parse 语法——**不做 import/requirements/API 映射检查**（CodeValidator 的主要能力被绕开）。
- **影响**：单文件验证退化为语法检查，CodeValidator 的依赖校验在文件生成主链不生效；缓存体系分裂（CV1 内存/文件 + 此私有 dict）。这是「验证器多套并存」的又一处（CV8 四套之外的第 5 处简化验证）。
- **验证方式**：生成含缺失 import 的 .py → 该路径 ast.parse 通过 → 缓存写入且无依赖告警（实码可证）。

### OF2 [P2] git stash 回滚的全局栈语义：非 git 项目回滚不完整 + 多层 stash 顺序错乱风险

- **Bug 代码**：

```python
# orchestrator_files.py:174/:254 - 每层/每批 push 一个 stash
stashed = _git_stash_push(str(self.output_dir), existing_files, "agent-backup-batch")

# :55-69 - pop 弹栈顶，不校验 message 对应哪批
result = subprocess.run(['git', 'stash', 'pop'], cwd=work_dir, ...)
```

- **根因**：`git stash` 是**栈式全局操作**。① output_dir 非 git 仓库时（大量生成场景）`git stash push` 失败 → stashed=False → 回滚时**已有文件不恢复**，只删新文件；② 分层模式每层 push 一个 stash（agent-backup-layer-0/1/...），`git stash pop` 恒弹栈顶——若某层跳过 push（该层无 existing_files → :38 `if not files: return True` 不 push）或层间异常，**pop/drop 与 push 的栈顺序错位**，恢复错误层或误弹用户自己的 stash。`stash drop` 同理无条件丢栈顶。
- **影响**：生成失败回滚在非 git 项目不完整；多层并发/串行时 stash 栈状态易错乱，可能覆盖/丢失用户工作区改动。
- **验证方式**：非 git 目录（或 git 但无 stash 权限）构造失败层 → 回滚后已有文件未恢复（实码可证）。

### OF3 [P2] `_recover_invalid_content_orchestator` 恢复路径缺少语言检测与依赖上下文

- **Bug 代码**：

```python
# orchestrator_files.py:631-635 - 只传 5 参，主路径 :379-385 传 8 参
content = await extract_engineer_content(
    content, engineer, self.output_dir, file_path,
    fix_imports_fn=_fix_absolute_imports,
    all_files=all_files
)
```

- **根因**：主路径的 `extract_engineer_content` 传 `expected_language` + `llm_caller`（语言检测 + 内容提取双重保障），恢复路径缺这两参——恢复内容跳过语言检测，`expected_language` 为空时 utils 的内容提取退化。且 `_recover_invalid_content_orchestator` 只循环 2 次（:619），失败后返回 None → 上层走 `_direct_llm_generate_file` 兜底（又一轮无语言检测的裸生成）。
- **影响**：无效内容恢复路径的提取质量低于主路径，恢复成功率受限。
- **验证方式**：构造 JSON 元数据内容触发恢复 → 恢复路径语言检测缺失（实码可证）。

### OF4 [P2] `_direct_llm_generate_file` 硬编码 DEFAULT_CODE_MODEL + 不走动态路由/成本

- **Bug 代码**：

```python
# orchestrator_files.py:676-683
response = await call_llm(
    model=DEFAULT_CODE_MODEL,
    ...
    max_tokens=4096, temperature=0.4,
    api_key_token=self.api_key_token
)
```

- **根因**：兜底直连 LLM 硬编码 `DEFAULT_CODE_MODEL`，不经过 model_assignment/dynamic_model_router（模型配置体系被绕开）；call_llm 直连不计成本/信号量（LCL1 主线）。`:373 llm_caller` 语言检测同款硬编码 DEFAULT_CODE_MODEL。
- **影响**：兜底路径与主路径模型策略脱节；降级后模型选择不可控。
- **验证方式**：实码可证。

### OF5 [P3] `_select_alternative_model`/`_select_engineer_for_model` 硬编码 Qwen 模型名

- **Bug 代码**：

```python
# orchestrator_files.py:772-785
alt_map = {
    DEFAULT_REASONING_MODEL: DEFAULT_CODE_MODEL,
    DEFAULT_CODE_MODEL: DEFAULT_REASONING_MODEL,
    "Qwen/Qwen3-8B": DEFAULT_CODE_MODEL,   # 硬编码
    DEFAULT_ARCHITECT_MODEL: DEFAULT_REASONING_MODEL,
}
frontend_models = {"Qwen/Qwen3-8B", DEFAULT_CODE_MODEL}
```

- **根因**：模型名硬编码（spec_first_generate.py:466/:1024/:1777 三处活跃调用的降级映射），模型配置变化时（替换/新增模型）映射失配，与 IM1（SiliconFlow 硬编码）同属 DMR 绕开主线。
- **影响**：spec-first 主链的模型降级依赖硬编码模型名，配置驱动模型体系下不可维护。
- **验证方式**：实码可证。

### OF6 [P3] 小项目/分层两种生成方法高度重复

- **现象**：`_generate_files_small_project`（:156-213）与 `_generate_files_by_dep_layers` 的分层内逻辑（:226-300）在「分离已有/新文件 → stash → gather → 结果检查 → 回滚/成功处理」几乎逐行重复（约 60 行重复）。
- **影响**：回滚/成功处理逻辑两份实现，后续修复需同步两处（DRY 违例，演化修改成本翻倍）。
- **验证方式**：对比 :163-213 与 :243-300（实码可证）。

### OF7 [P3] `_normalize_file_path` 只修「目录/纯扩展名」一种格式，`\` 分隔不处理

- **Bug 代码**：

```python
# orchestrator_files.py:538-549
parts = file_path.split('/')   # 只处理 / 分隔
if last_part and last_part.lower() in KNOWN_EXTENSIONS:
```

- **根因**：只修 `events/rpy → events.rpy` 一类错误；Windows 风格 `\`（LLM 偶尔生成）不规范化；`file_path` 含 `.` 但最后一段非纯扩展名的其他格式错误不修。
- **影响**：路径规范化的覆盖有限，LLM 生成的其他路径变体仍会落盘错误位置。
- **验证方式**：`src\\utils\\api.py` → 不处理（实码可证）。

### OF8 [P3] `_validate_and_review_file` 中 review high 后内容已采用但 success=False 语义

- **Bug 代码**：

```python
# orchestrator_files.py:747-748
if review_result.get("risk_level") == "high":
    validation_success = False
```

- **根因**：error_recovery 修复成功（:724 success）后内容已写盘（:725-726），随后 review 报 high → validation_success=False → 调用方 :449-450 记录 warning，但 **内容已采用**（文件已写、后续照常返回 success:True 于 :487）。「验证未通过但内容已落盘」语义矛盾。
- **影响**：high 风险审查后文件仍被采用，validation_success 只影响 warning 记录，不影响采用决策。
- **验证方式**：实码可证。

### OF9 [P3] `llm_caller` 语言检测每文件定义一次 + 成本不计

- **Bug 代码**：

```python
# orchestrator_files.py:371-377 - 每次 _generate_single_file 都定义并可能调用
async def llm_caller(prompt: str) -> str:
    return await call_llm(model=DEFAULT_CODE_MODEL, ..., api_key_token=...)
```

- **根因**：语言检测 LLM 调用硬编码模型、每文件内联定义、call_llm 直连不计成本/信号量（LCL1 主线）。语言不确定时 extract_engineer_content 可能触发该调用。
- **影响**：每文件潜在一次额外 LLM 调用且不可见成本；模型不可配。
- **验证方式**：实码可证。

### OF10 [P3] `_apply_patches_incremental` 全库无调用方（死代码）

- **现象**：rg 全库（app/）仅定义于 orchestrator_files.py:787，无任何生产调用方。跨文件补丁逻辑（cross_file_patcher + apply_incremental_change）整套未接线。
- **影响**：跨文件补丁方向（CrossFilePatcher）在 FilesMixin 侧无入口，仅 code_patcher 的直接调用存在；若该能力是设计意图，需接线（incremental_modify 或 incremental_generate 调用）；否则删。
- **验证方式**：rg `_apply_patches_incremental` 全库仅定义处（已实测）。

## 4. 潜在问题与未知点

- `_validate_and_review_file` 的缓存 key `{file_path}:{hash}` 与 CodeValidator 的 `full_validation:{hash}`（CV1）完全独立——文件路径维度引入的重复校验（同内容不同路径不命中），未深挖与 CV1 修复的冲突面。
- `_friendly_error` 的 `"500" in error_lower`（:505）子串匹配会误判含 500 的任意文本；`_is_critical_file` 只认 10 个 basename 白名单，`config/__init__.py` 等变体不触发审批。
- `_generate_single_file` 300+ 行大方法：prevention/dep_context/审批/验证/反馈学习五阶段耦合，拆分（生成/审批/验证/学习四子方法）是演化建议。
- 路径规范化（`_normalize_file_path`）在 :348（生成前）与 :453（生成后）两处调用，`is_existing` 判定基于规范化前路径——不一致潜在（未实测）。

## 5. 修改建议（改什么 → 达成什么目的）

| # | 优先级 | 修改动作 | 达成目的 | 涉及位置 | 对应 Backlog |
|---|--------|---------|---------|---------|-------------|
| 1 | P2 | `_validate_and_review_file` 改调 `validator.run_full_validation`（走正式接口 + 正式缓存），删除私有 `_validation_cache` 读写 | 文件生成主链接入 CodeValidator 完整验证（import/API/requirements），消除双缓存分裂（CV8/CV1 主线） | orchestrator_files.py:700-765 | 待记 |
| 2 | P2 | 回滚改为「文件级快照」（临时目录备份已有文件，失败时复制恢复），替代 git stash；或生成前要求 output_dir 是 git 仓库并在 push 前检查 `git stash list` | 非 git 项目回滚完整；多层 stash 顺序错乱风险消除 | orchestrator_files.py:36-82/174/:254 | 待记 |
| 3 | P2 | `_recover_invalid_content_orchestator` 的 extract_engineer_content 补 expected_language/llm_caller（与主路径对齐） | 恢复路径提取质量与主路径一致 | orchestrator_files.py:631-635 | 待记 |
| 4 | P2 | `_direct_llm_generate_file`/`llm_caller` 改走 model_assignment + dynamic_model_router；成本/信号量接入（LCL1） | 兜底与语言检测路径模型策略一致、成本可见 | orchestrator_files.py:371-377/:676-683 | 待记 |
| 5 | P3 | `_select_alternative_model` 从 model_config/注册表推导降级，删除硬编码 Qwen；`_select_engineer_for_model` 按 ext 而非模型名 | 模型降级配置驱动（DMR 主线） | orchestrator_files.py:772-785 | 待记 |
| 6 | P3 | 抽公共 `_generate_layer(files, layer_info)` 供 small_project/分层共用 | 消除 ~60 行重复，回滚逻辑单一实现 | orchestrator_files.py:156-300 | 待记 |
| 7 | P3 | `_normalize_file_path` 补 `\`→`/` 与更多格式修复 | 路径规范化覆盖提升 | orchestrator_files.py:519-551 | 待记 |
| 8 | P3 | review high 时不采用内容（回滚该文件）或把 validation_success 语义改为「仅记录」，避免「未通过但已采用」 | 验证-采用语义一致 | orchestrator_files.py:747-748 | 待记 |
| 9 | P3 | `_apply_patches_incremental` 接线到 incremental 入口或删除并记录意图 | 消除死代码/激活跨文件补丁方向 | orchestrator_files.py:787 | 待记 |
| 10 | P3 | 补 FilesMixin 测试（回滚、路径规范化、无效恢复、验证缓存） | 文件编排核心回归防线（当前零测试） | tests/ | 待记 |

## 6. 演化方向关联

- FilesMixin 是**文件生成编排核心**——spec_first 与传统链路的共同文件出口（:443-489 的验证/审查/契约检查/反馈学习在此串联）。OF1 使 CodeValidator 完整验证绕开，是验证闭环归位（CV8/CV1 主线）的接线缺口。
- OF2 回滚机制与「原子写」（TG1/ERL6/IM3）同属**写安全主线**——stash 回滚是文件级原子性的尝试，但全局栈语义使其在非 git 项目失效。
- OF4/OF5/OF9 硬编码模型名与直连 call_llm 归入 DMR 绕开 + LCL1 收敛范围（IM1/CEC4/EV1 同源）。
- OF10 `_apply_patches_incremental` 死代码揭示跨文件补丁方向（CrossFilePatcher）缺接线——与 incremental_modify（IM 系列）的「增量修改」演化主线相关，是两套增量实现收敛时需要决策的接线点。
- OF6 重复（DRY）与 `_generate_single_file` 大方法拆分是文件生成编排的代码健康主线。
