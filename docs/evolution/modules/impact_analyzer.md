# ImpactAnalyzer 演化详档

- 文件：`app/agent/impact_analyzer.py`（205 行）
- 扫描日期：2026-08-09
- 状态：✅ 已完成
- 模块定位：测试选择的「精准影响分析」——通过 AST 符号提取 + 新旧版本 diff，识别修改文件、新增/删除/修改符号，供 TestSelector 决定跑哪些测试

## 职责

docstring 声称「通过轻量级符号提取和文件级变更对比，**准确识别受代码修改影响的文件范围**」（:4）。实际实现只有两件事：

1. `analyze`（:36-117）：遍历修改文件 → 对每个文件 AST 提取符号（函数/类）→ 若有 old_versions 则与旧版 diff → 汇总 ChangeSummary
2. `_extract_symbols`（:119-154）：ast.walk 提取 FunctionDef/ClassDef
3. `_has_dynamic_imports`（:156-176）：子串匹配动态导入模式
4. `_generate_summary`（:178-205）：人类可读摘要

## 消费方

- `orchestrator_testing.py:116`：唯一消费方 `ImpactAnalyzer(project_root)` → 已归 **OT16 [P2]**（无参构造 TypeError 恒被 except 捕获）——**本模块的 analyze 从未被执行过**（构造即失败）

## 实测确认的 bug

### IA1 [P2] 新旧同名（modified）符号同时出现在 new_symbols 与 modified_symbols

- 位置：:82-89 diff 逻辑
- 实测：`old={"util.py": "def helper():..."}` + 新文件同文件新增 `Foo` 类 → `new=['helper','Foo']`、`modified=['helper']`——**helper 同时出现在 new 与 modified**，`summary` 输出「新增 2 个符号：helper, Foo；修改 1 个符号：helper」自相矛盾
- 根因：:86 过滤 `all_new_symbols = [s for s in all_new_symbols if s['name'] not in added or s['file'] != file_path]`——只排除了 added 语义，modified（新旧同名）符号因 `s['name'] not in added` 为 True 保留在 all_new_symbols；:89 又把 modified 符号 extend 进 all_modified_symbols → 双重归属
- 影响：新符号与修改符号集合重叠，下游（若有）按互斥集合消费会重复处理

### IA2 [P2] 只解析 Python，非 Python 文件符号全盲

- 位置：:133 `ast.parse(content)`
- 实测：`app.js`（含 function/export）→ `AST 解析失败 app.js: invalid syntax` → 返回空符号，new_symbols 只含 util.py 的 helper/Foo
- 影响：多语言项目（前端 JS/TS、Go 等）修改文件的影响分析全为空白——「精准影响分析」对大部分真实项目只对 .py 生效。与多语言主线（DG2/IM4/AR16）同源
- 修复方向：按扩展名分发解析器（Python→ast、JS/TS→tree-sitter 或正则、Go→go AST），解析失败时降级为文件名级推断而非空

### IA3 [P2] 「影响分析」名不副实——只做符号 diff，不做影响传播

- 位置：analyze 整体
- 事实：docstring 声称「识别受代码修改影响的**文件范围**」，但实现从不查引用者/依赖图，不计算修改波及到哪些文件——返回的只是「哪些符号变了」，没有「哪些文件受影响」
- 影响：TestSelector 即便拿到 ChangeSummary 也无法据此决定跑哪些测试（没有受影响文件列表）。影响传播是测试选择的输入，当前整个测试选择链（OT16+IA3）从未具备核心能力
- 修复方向：基于符号级依赖（import 图 / AST 引用扫描）计算传播闭包，产出 `affected_files`；与 DG 体系复用同一依赖图源

## 其余发现

### IA4 [P3] `_has_dynamic_imports` 子串假阳性

- 位置：:166-170
- 实测：`x = getattr(obj, 'y')`（普通反射）→ True；`# __import__ is dangerous`（纯注释）→ True
- 影响：动态导入标记污染；`getattr(` 子串匹配任何反射调用

### IA5 [P3] 符号粒度只有函数/类

- 位置：:138-152 ast.walk 只收 FunctionDef/ClassDef
- 影响：变量、Import 语句、嵌套函数（ast.walk 会收到嵌套 def，但标注为顶层文件符号无层级信息）、async def（ast.AsyncFunctionDef **未处理**——`isinstance(node, ast.FunctionDef)` 不含 AsyncFunctionDef）丢失

### IA7 [P3] 无 old_versions 时「新符号」全量累积

- 位置：:71 `all_new_symbols.extend(new_symbols)` + :100
- 实测：无 old_versions 时未变文件的既有符号也进 new_symbols → `new=['Foo','helper']` 把本来存在的类当「新增」
- 影响：无旧版本快照时 new_symbols 语义失真（无从对比时不应声称「新增」）；与 SM2/SM3（content_hash 恒空）叠加使 diff 路径在真实调用中从未走通

## 修复优先级

| 项 | 级别 | 关键点 |
|---|---|---|
| IA3 | P2 | 无影响传播 = 核心能力缺失，OT16 修复后直接暴露 |
| IA1 | P2 | 集合重叠，diff 语义错误 |
| IA2 | P2 | 多语言全盲 |
| IA7 | P3 | 无快照时语义失真 |
| IA4 | P3 | 假阳性 |
| IA5 | P3 | 符号粒度 + AsyncFunctionDef 漏收 |

## 关联

- OT16 [P2]：消费方构造失败，本模块 analyze 从未执行——**先修 OT16 才谈得上本模块的修复**
- SM2/SM3 [P2]：old_versions 来源（content_hash/快照）恒空，diff 路径缺数据
- DG 体系（OA12/DG1/DG3/AR8）：影响传播应复用依赖图
- 测试状态：impact_analyzer **零单元测试**（tests/unit 无 impact 相关文件）
