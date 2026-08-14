# CodePatcher 演化深扫文档

> 版本：v0.1 | 扫描日期：2026-08-09 | 状态：已完成
> 归属：Agent 大系统 / 支撑模块（代码补丁生成与应用）
> 路径：app/agent/code_patcher.py（629 行）
> 索引：[TASKS.md](../TASKS.md)

## 1. 模块作用与功能

代码补丁生成器与应用器：增量修改场景下基于需求生成 unified diff patch（LLM 模式）或从新旧内容直接 diff（difflib 模式），并应用 patch 到原文件（精确 + 模糊匹配）。附跨文件补丁器（CrossFilePatcher）处理依赖链影响。定位是「缓存命中后局部修改」「错误修复只改出错部分」的高效路径。

- **核心类**：`CodePatcher`（:43）、`CrossFilePatcher`（:513）。数据类：`PatchResult`（:32）、`CrossFilePatchResult`（:504）。
- **方法族**：`generate_patch_from_requirement`（:66 LLM 生成）、`generate_diff_from_content`（:140 difflib）、`apply_patch`（:169 解析+应用）、`apply_patch_to_file`（:227 路径穿越校验+备份+写盘）、`estimate_patch_impact`（:285）、`_extract_patch_from_response`（:321）、`_parse_patch`（:346）、`_apply_hunks`（:378 精确）、`_apply_hunks_fuzzy`（:404 模糊）、`apply_incremental_change`（:447 便捷函数）、`generate_cross_file_patches`（:525）。

## 2. 依赖与被依赖

- **生产使用方**（4 处）：orchestrator_files.py（:11 导入 apply_incremental_change、:858 调用；:816 调 cross_file_patcher）、orchestrator_generation/mixin.py（:92 实例化 CodePatcher(llm_call_fn=_call_llm_for_patch)、:93 实例化 CrossFilePatcher）、orchestrator.py、utils/prompt_loader.py。
- **接线状态**：`CrossFilePatcher` 在 mixin.py:93 实例化、orchestrator_files.py:816 调用——但该调用位于 `_apply_patches_incremental`（orchestrator_files:787）内部，后者**全库无入口调用方（OF10 死代码）**→ **整条跨文件补丁链路当前不可达**。
- **测试覆盖**：tests/unit/test_code_patcher.py **仅 2 个**（test_apply_patch_simple / test_apply_patch_failure）——多 hunk 漂移、新文件创建、上下文不匹配、fuzzy 全无覆盖。

## 3. 已探明 Bug

### CP1 [P2] 精确匹配不验证上下文行：上下文不匹配的 patch 静默应用到错误位置

- **Bug 代码**：

```python
# code_patcher.py:378-402 - 精确匹配只查行号边界，不比对上下文内容
def _apply_hunks(self, original_lines, hunks):
    for hunk in hunks:
        old_start = hunk['old_start'] - 1
        old_count = hunk.get('old_count', 0)
        if old_start < 0 or old_start + old_count > len(result):  # 只查边界
            return None
        new_lines = [line[1:] for line in hunk['lines'] if not line.startswith('-')]
        result[old_start:old_start + old_count] = new_lines   # 直接按行号替换
```

- **根因**：精确路径完全不验证 hunk 中 `' '` 上下文行与实际文件内容是否一致，按行号硬替换。**模糊路径（:404-441）反而做了上下文比对**（:421-423 `expected_context == actual_context`）——精确匹配比模糊匹配更不安全（反直觉）。
- **影响**：实测原文件 `AAA/BBB/CCC` + 上下文行 ` ZZZ`（与文件不符）的 patch → 应用后 `ZZZ/CCC`，**success=True 零警告**——LLM 幻觉的上下文行被静默应用到错误位置，破坏代码且无感知。
- **验证方式**：实测（见 §5）。

### CP2 [P2] `@@ -0,0 +1,N @@` 新文件创建场景：精确恒失败，fuzzy 靠「空上下文恒真」碰巧成功

- **Bug 代码**：

```python
# :383 - 新文件 hunk 的 old_start = 0-1 = -1
old_start = hunk['old_start'] - 1     # @@ -0,0 @@ → -1
if old_start < 0 or ...: return None  # :386 → 精确恒返回 None
# :411-423 - fuzzy 中 expected_context=[]（全 + 行）→ 空==空 恒真
```

- **根因**：标准新文件创建 diff（`@@ -0,0 +1,3 @@`）old_start=-1 恒被精确路径拒绝；fuzzy 因无上下文 hunk（expected_context=[]）的 `[] == []` 恒真匹配 offset 0 而碰巧成功，**且成功后 errors 仍残留「Patch 应用失败：行号不匹配」与 success=True 并存**（语义矛盾）。
- **影响**：新文件场景的成功依赖 fuzzy 的空上下文退化匹配（CP3），errors 污染；多 hunk 新文件时错误不可控。
- **验证方式**：实测（见 §5）。

### CP12 [P2] 多 hunk 顺序应用行号漂移：增行后后续 hunk 错位

- **Bug 代码**：

```python
# :382-400 - 循环内逐个 hunk 修改同一 result，后续 hunk 基于已变更的行号
for hunk in hunks:
    result[old_start:old_start + old_count] = new_lines  # 第一个 hunk 增行后行数变化
```

- **根因**：hunk 的 old_start/old_count 基于原始文件计算，但应用时依次修改同一 result 列表——第一个 hunk 净增/净减行后，后续 hunk 的行号失准。正确做法应从后向前应用或维护偏移。
- **影响**：实测双 hunk（第一 hunk 插 1 行）→ 结果 `line7` 重复出现（第 7、8 行），第二个 hunk 错位应用；多 hunk 的大 patch（LLM 生成常见）必然产生错误内容且 success=True。
- **验证方式**：实测（见 §5）。

### CP10 [P2] CrossFilePatcher 的 primary_result 循环覆盖 + 整链路不可达

- **Bug 代码**：

```python
# :551-580 - 多 changed_file 时每个成功都覆盖 primary_result，只留最后一个
for changed_file in changed_files:
    ...
    if patch_result.success:
        result.primary_result = patch_result   # ← 前一个被覆盖
```

- **根因**：`primary_file=changed_files[0]`（:547）但循环中每个成功都写 `primary_result` → 多文件变更时 primary_result 对应最后一个文件而非 primary_file 声明的第一个（语义错乱）。且整个 CrossFilePatcher 因 `_apply_patches_incremental`（orchestrator_files:787）无入口调用方而**当前不可达**（OF10 死代码）。
- **影响**：即使接线，多文件变更的跨文件补丁结果只保留最后一个文件的 PatchResult，调用方拿到的结果不完整。
- **验证方式**：rg 确认 `_apply_patches_incremental` 无调用方；代码追踪 primary_result 覆盖。

### CP3 [P3] fuzzy 无上下文 hunk 退化为纯行号应用（与 CP1 同风险）

- **Bug 代码**：

```python
# :411-423 - expected_context 为空时 `[] == []` 恒真
expected_context = [line[1:] for line in hunk['lines'] if line.startswith(' ')]
if expected_context == actual_context:   # 空列表恒等
    best_match = test_start
```

- **根因**：hunk 全为 +/- 行（无上下文）时 expected_context=[]，任意偏移都「匹配」→ best_match=offset 0 → 纯行号应用，无上下文校验。CP2 的新文件场景即依赖此行为。
- **影响**：无上下文 hunk 的 fuzzy 与 CP1 精确路径同样脆弱。

### CP4 [P3] `.bak` 备份文件残留：多轮 patch 后项目目录堆积 + 只留最后版本

- **Bug 代码**：

```python
# :277-278 - 每次成功生成 <file>.bak，从不清理
backup_path = file_path.with_suffix(file_path.suffix + '.bak')
backup_path.write_text(original_content, encoding='utf-8')
```

- **根因**：每轮 patch 覆盖同一 `.bak`（第二轮备份覆盖第一轮），且不清理、无 .gitignore 保护。
- **影响**：多轮增量修改后项目目录堆积 .bak 残留（可能被打包/测试扫描）；回滚只能回到上一轮而非原始状态。

### CP5 [P3] `apply_patch_to_file` 非原子写

- **Bug 代码**：

```python
# :281 - 直接写文件，失败中断留半写状态
file_path.write_text(result.patched_content, encoding='utf-8')
```

- **根因**：无临时文件 + rename 原子替换（TG1 非原子同类）。备份（.bak）在写入前生成但写入非原子。
- **影响**：进程中断时文件半写，备份与实际内容不一致。

### CP6 [P3] `_parse_patch` hunk 行收集遇裸空行截断

- **Bug 代码**：

```python
# :362 - 只收集 +/-,空格开头行；裸空行('') 停止收集
while i < len(lines) and lines[i].startswith(('+', '-', ' ')):
    hunk_lines.append(lines[i]); i += 1
```

- **根因**：unified diff 中新增空行应为 `+` 或上下文 `' '`；LLM 生成的 patch 若含裸空行（''），hunk 提前截断，后续行被当新 hunk 头跳过。
- **影响**：含空行的 LLM patch 解析不完整，应用结果与预期不符。

### CP7 [P3] `_extract_patch_from_response` 第三 fallback 把响应剩余全当 patch

- **Bug 代码**：

```python
# :341-342 - 找到 --- 后把响应从该行到结尾全当 patch
return '\n'.join(lines[start_idx:])
```

- **根因**：LLM 在 diff 后附解释文字会混入返回；`_parse_patch` 对非 hunk 行跳过（:373-374）实际无害，但 `--- ` 前缀若匹配 markdown 水平线相关内容有误提取风险（`--- ` 需后跟空格，低概率）。
- **影响**：容错性一般，多数场景无害。

### CP13 [P3] 测试仅 2 个：多 hunk/新文件/上下文不匹配/fuzzy 全无覆盖

- **Bug 代码**：

```python
# tests/unit/test_code_patcher.py - 仅 2 个用例
def test_apply_patch_simple(self, patcher): ...
def test_apply_patch_failure(self, patcher): ...
```

- **根因**：只覆盖单个 hunk 简单 patch 成功 + 无法解析失败。CP1（上下文不匹配静默破坏）、CP12（多 hunk 漂移）、CP2（新文件）等破坏性 bug 在测试网下全部通行。
- **影响**：补丁应用器的核心正确性（静默破坏）零回归保护。

## 4. 修复建议

- **CP1**：精确路径补上下文行比对（与 fuzzy 一致），不匹配即返回 None 走 fuzzy 或报错。
- **CP2**：`old_start < 0` 时按「新文件插入」处理（`result[0:0] = new_lines`），不依赖 fuzzy 空上下文退化。
- **CP12**：hunk 从后向前应用（`for hunk in reversed(hunks)`），或维护插入偏移。
- **CP10**：primary_result 改为主文件专用（与 primary_file 对应），多文件结果进独立列表；接线 `_apply_patches_incremental`（OF10）或删除死链路。
- **CP3**：fuzzy 对 expected_context=[] 的 hunk 拒绝模糊（直接按精确边界处理并加校验）。
- **CP4**：patch 成功且验证通过后删除 .bak；或 .bak 放临时目录。
- **CP5**：写临时文件 + `os.replace` 原子替换。
- **CP6**：hunk 行收集容忍裸空行（补 `lines[i] == ''` 处理）。
- **CP7**：第三 fallback 改为提取 `--- a/` 到首个非 diff 行。
- **CP13**：补多 hunk 漂移/新文件/上下文不匹配/fuzzy 用例。

## 5. 待实测项

- CP1 已实测（上下文 `ZZZ` 不匹配 → ZZZ/CCC，success=True 零警告）。
- CP2 已实测（`@@ -0,0 +1,3 @@` → 精确失败走 fuzzy 碰巧成功，errors 与 success 并存）。
- CP12 已实测（双 hunk 增行 → line7 重复，行号漂移）。
- CP3/CP4/CP5/CP6/CP7/CP10/CP13 为代码级结论。
