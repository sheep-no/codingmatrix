# spec_first_generate.py 演化深扫文档

> 版本：v0.1 | 扫描日期：2026-08-05 | 状态：已完成
> 归属：Agent 引擎 / Spec-First 完整编排（A2→A9 主链）
> 路径：`app/agent/orchestrator_generation/spec_first_generate.py`（2383 行）
> 索引：[TASKS.md](../TASKS.md)

## 1. 模块作用与功能

核心职责：**SpecFirstGenerateMixin**——Spec-First 模式的**完整编排器**（orchestrator 核心 Mixin，被 orchestrator_generation/mixin.py 继承）。串联：规范生成 → 架构设计 → 依赖图构建验证 → 分层代码生成 → 三重完整性验证 → 沙箱验证 → 缓存 → 指标汇报。

**主流程** `generate_with_spec_first`（:28-852）：
1. 缓存查询（:40-57）+ 需求关联增强（:59-75）
2. 规范生成（SpecFirstGenerator，:110-120）或缓存加载（:107-111）
3. 架构设计 + 分批规划（:135-153）+ 全局约束/关键决策（:161-194）
4. 依赖图构建 + 全图/增量验证（:218-297）+ 未知类型 LLM 推断（:292-297）
5. **分层生成**（:320-631）：同层 `asyncio.gather` 并发 → 每文件 生成→交叉验证→精炼→质量校验→原子写入（:335-567）
6. 三重完整性验证（:634-713）：IntegrityValidator + 依赖图完整性 + CrossValidator 跨文件一致性
7. 项目级沙箱验证 + 自动修复（:715-746）+ final_validation（:750-760）
8. 缓存保存 + 指标汇报（:765-851）

**动态拓扑分支** `_generate_with_dynamic_topology`（:853-1501）：`use_dynamic_topology` 时用 TopologyScheduler（max_concurrent=5）+ set_allowed_file_paths 白名单。

**验证/修复方法**：`_validate_content_syntax`（:1502）、`_fix_sandbox_errors`（:1811）、`_recover_invalid_content`（:2003）、`refactor_file`（:2175）。

## 2. 依赖与被依赖（跨模块引用链）

### 2.1 依赖（import）

| 依赖 | 用途 |
|------|------|
| SpecFirstGenerator / RefinementLoop / CrossValidator / SharedContext / TopologyScheduler | 生成与编排核心 |
| DependencyGraph / DependencyGraphValidator | 依赖图构建与验证 |
| CriticalDecisionExtractor / GlobalConstraintParser / ArchitectureInspector | 决策/约束/架构检查 |
| LanguageAdapterRegistry / get_context_length / IntegrityValidator | 语言适配/上下文/完整性 |
| utils：extract_engineer_content / write_file_atomic / validate_in_sandbox / is_valid_code_content / cleanup_temp_files | 内容处理与沙箱 |
| CodeValidator（:752 实调 run_full_validation） | 单文件完整验证（import/requirements/API） |
| tools.set_allowed_file_paths（:311/:878 运行时） | 工具写路径白名单 |

### 2.2 被消费方

- **orchestrator_generation/mixin.py**（唯一继承方）——orchestrator 主 Mixin 组合

### 2.3 测试覆盖

- **零测试**：tests/ 下无任何 SpecFirstGenerate / generate_with_spec_first 引用——**2383 行核心编排无测试**

### 2.4 交叉回注（2026-08-09 支撑模块深扫）

- **文件生成主链的「质量校验」退化为语法级**：§1 主流程第 5 步「质量校验」实际走 `FilesMixin._validate_and_review_file`（orchestrator_files.py:750-758）——只 `ast.parse` + 直接读写 CodeValidator 私有 `_validation_cache`，**CodeValidator 完整验证（import/requirements/API）在文件生成主链被绕开**（orchestrator_files.md OF1）；且 `run_full_validation` 的文件系统缓存读写恒失败（code_validator.md CV1）。**「三重完整性验证」中的验证体系实际多套并存**：CodeValidator（CV8 四套之一）+ FilesMixin 简化验证（OF1 第 5 处）+ api_contract_checker/integrity_validator._validate_api_contracts/CV4 三处 API 契约校验。
- **精炼步骤验证强度为语法级**：第 5 步「精炼」走 RefinementLoop.refine（:503/:513/:1064/:1074）——success 只依赖轻量验证（语法/括号/import 存在，refinement_loop.md RL3），openapi 路径一致性检查是空操作（RL1）。
- **进度通道 content 全量推送**：第 5 步的 `generated_contents[file_path] = content[:MAX_CONTENT_FOR_CONTEXT]`（:615/:934/:957/:1171）是验证通道截断，但 `_report_file_event` 进度事件推全量 content（orchestrator_progress.md OP2），两通道截断语义不一致。

## 3. 已探明 Bug（含 bug 代码）

### SPFG1 [P1] 断点续传：>10 字节即跳过且**未验证标记通过**

- **Bug 代码**：

```python
# spec_first_generate.py:358-360 - 10 字节即视为完整
if file_size < 10:
    logger.warning(f"文件太小，重新生成: {file_path} ({file_size} bytes)")
else:
    ...
    return {
        "path": file_path, ..., "success": True,  # :374
        "model_name": "cached", "validation_passed": True,  # :380-381
        ...
    }
```

- **根因**：已存在文件只要 `>10 字节` 就跳过（:362），**不做内容有效性/语法校验**，直接标记 `success: True, validation_passed: True`
- **影响**：占位符/垃圾内容文件（>10 字节）在断点续传时被当成功产物，污染生成结果

### SPFG2 [P1] `_validate_content_syntax`：JS/TS 合法语法被误判为 Python 混入

> **实测确认（2026-08-05）**：合法 TS 样本 `import { Router } from "express"` + `class UserController {...}`（python_count=3）被 :1521 硬拒绝 return False——在 `node -c` 之前即误拒。而仅 `import`+`from`（count=2）的 TS 样本正确通过 node -c。

- **Bug 代码**：

```python
# spec_first_generate.py:1519-1522
python_indicators = ['def ', 'import ', 'from ', 'class ', 'self.', 'print(']
python_count = sum(1 for ind in python_indicators if ind in content)
if python_count >= 3:
    return False   # ← 误判：ES module+class 合法组合必命中
```

- **根因**：`import`/`from`/`class` 是 **JS/TS 合法语法**（ES module + class）——一个正常 TS 文件含三者即 ≥3 → **合法 JS/TS 被拒**（且硬拒绝发生在 node -c 语法校验之前，无法被挽救）
- **影响**：前端文件（TS 大量使用 import/class）误报语法失败，触发无效的修复/重试

### SPFG2b [P2] `.jsx`/`.tsx` 不在语法校验分支内——完全不校验

- **Bug 代码**：:1517 `elif ext in ('.js', '.ts', '.vue')`——`.jsx`/`.tsx` 落入 :1558 `return True` 兜底，**任何内容（含垃圾/占位符）都判定语法通过**（与 SPFG1 的假通过叠加）
- **影响**：React/TSX 前端文件语法零校验

### SPFG3 [P1] `_fix_sandbox_errors`：只处理 `.py` 文件错误，非 Python 沙箱错误全丢弃

- **Bug 代码**：

```python
# spec_first_generate.py:1853-1857 - 仅匹配 .py 路径
py_match = re.search(r'(\S+\.py)\b', error)
if not py_match:
    continue   # ← 非 .py 错误直接丢弃
```

- **根因**：文件路径提取只认 `.py` 扩展（:1854）——JS/TS/其他语言的沙箱错误无法关联文件，`continue` 丢弃
- **影响**：前端沙箱错误永不进入自动修复（:1888 `if not file_errors: return`）

### SPFG4 [P1] `_fix_sandbox_errors` 修复 prompt 代码块硬编码 python

- **Bug 代码**：:1931 `` ```python\n{content}\n``` ``——修复非 Python 文件也标 python 代码块（叠加 SPFG3 局限）

### SPFG5 [P1] `refactor_file` 语言硬编码 "python"：非 Python 项目重构依赖图适配器错误

- **Bug 代码**：

```python
# spec_first_generate.py:2195-2197
detected_language = "python"   # ← 硬编码
language_adapter = LanguageAdapterRegistry.get_adapter(detected_language)
dep_graph = DependencyGraph.load(str(dep_graph_path), language_adapter=language_adapter)
```

- **根因**：`refactor_file` 用 python adapter 加载/解析依赖图——**非 Python 项目的依赖图序列化结构不同，加载/后续 get_context_for_file 出错**
- **影响**：重构功能对非 Python 项目不可用/错误

### SPFG6 [P2] `generate_file` 返回类型不稳定（协程/内容漂移）

- **Bug 代码**：:417-419 与 :473-475 两处 `if asyncio.iscoroutine(initial_content): await`——`generate_file` 有时直接返回内容、有时返回协程——**API 契约漂移**（自动 await 是打补丁而非修复根因）

### SPFG7 [P2] 层内并发无显式限流

- **Bug 代码**：:586-590 `asyncio.gather(*tasks)` 同层全部文件同时生成——每文件内部多级 LLM（生成+交叉验证+精炼），依赖底层 call_llm 信号量（§10.1 直连）兜底，但层大时并发风暴（动态拓扑分支用 TopologyScheduler max_concurrent=5，普通分支无此约束）

### SPFG8 [P2] 缓存无失效策略

- **Bug 代码**：:766-784 按 `requirement` 原样缓存（specs/architecture/file_plan）——**同一 requirement 不同复杂度/技术栈共用缓存**，无版本/参数失效键

### SPFG9 [P2] `_validate_content_syntax` 其余启发式

> **实测确认（2026-08-05）**：合法 CSS 字符串值含 `"{"`（`content: "{"`）→ 误判 FAIL；合法 HTML 的 JS 字符串含 `<script>` 文本 → `script_opens` 误增 → 误判 FAIL。正常样本均 PASS。

- html/css 括号计数（:1554-1555 `{`==`}`）——字符串/注释内不配对括号误判
- html script 标签开闭计数（:1544-1546）——JS 字符串内 `<script>` 文本误增 opens
- 未知扩展直接 `return True`（:1557-1558）——.json/.md 等不校验

### SPFG10 [P2] `refactor_file` 其余

- `old_file_action` 默认 "delete"（:2277）——LLM 未指定即默认删除原文件（:2362-2368 有「全成功才删」保护）
- 重构验证失败仅 warning（:2294-2297）仍继续生成
- `original_content[:8000]` / `[:4000]` 截断 prompt（:2219/:2321）

## 4. 潜在问题与未知点

- `project_context["output_dir"]` 用 `_relative_output_dir or str(output_dir)`（:205）——两套路径表示，相对路径缺失时回退绝对路径
- 断点续传跳过文件时 `content` 直接读磁盘（:378）——与 write_file_atomic 的编码/换行处理可能不一致
- `_report_progress` 各阶段步数（1-6 步）与动态拓扑分支进度语义（total_files+5）混用
- IntegrityValidator 自动生成的默认内容（:670-681 只有 `"""Module: ..."""` 头）——**stub 文件可能含占位符语义**（虽 skip_placeholder_check 写入）

## 5. 修改建议（改什么 → 达成什么目的）

| # | 优先级 | 修改动作 | 达成目的 | 涉及位置 | 对应 Backlog |
|---|--------|---------|---------|---------|-------------|
| 1 | P1 | SPFG1：断点续传跳过前做语法/有效性校验（复用 _validate_content_syntax + is_valid_code_content） | 杜绝坏文件被当成功产物 | spec_first_generate.py:349-383 | 新增 |
| 2 | P1 | SPFG2：JS/TS 检测改为纯语法工具（node -c 直接跑），去掉 import/class/from 指示符；**SPFG2b：分支补齐 .jsx/.tsx**（node -c 不支持 TS，需 tsc/esbuild 或至少括号+占位符校验） | 合法前端文件不再误拒、JSX/TSX 有校验 | spec_first_generate.py:1517-1522 | 新增 |
| 3 | P1 | SPFG3/4：错误解析与修复 prompt 按扩展名分支 | 非 Python 沙箱错误可修复 | spec_first_generate.py:1854/:1931 | 新增 |
| 4 | P1 | SPFG5：refactor_file 从架构/依赖图推断语言（读已保存架构） | 非 Python 项目重构可用 | spec_first_generate.py:2195 | 新增 |
| 5 | P2 | SPFG6：generate_file 统一返回契约（全 async） | 消除运行时类型探测 | spec_first_generate.py:417/:473 | 新增 |
| 6 | P2 | SPFG8：缓存键含复杂度/语言维度或加失效时间 | 缓存命中语义正确 | spec_first_generate.py:766 | 新增 |
| 7 | P2 | SPFG10：old_file_action 默认 keep | 重构默认保守 | spec_first_generate.py:2277 | 新增 |

## 6. 演化方向关联

- **§15（双 spec_first 文件）**：本 Mixin 是编排层，spec_first_generator.py 是生成器——编排/生成职责分离确认；SPFG1 断点续传是本模块特有逻辑（生成器无此）
- **动态拓扑（§ 拓扑）**：普通分支 vs 动态拓扑分支双路径并存（:303 vs :320）——`use_dynamic_topology` 开关决定，收敛时应统一（SPFG7 并发差异）
- **Backlog 关联**：#6、#7、#12，新增 SPFG1-SPFG10
