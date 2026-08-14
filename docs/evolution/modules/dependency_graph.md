# DependencyGraph 演化深扫文档

> 版本：v0.1 | 扫描日期：2026-08-09 | 状态：已完成
> 归属：Agent 大系统 / 支撑模块（依赖图驱动生成排序）
> 路径：app/agent/dependency_graph.py（1340 行）
> 索引：[TASKS.md](../TASKS.md)

## 1. 模块作用与功能

依赖图驱动的文件生成排序器：分析文件间依赖关系确定最优生成顺序，保证生成某文件时其依赖已被生成并纳入上下文。

- **核心类**：`DependencyGraph`（dependency_graph.py:39）——节点（`FileNode` :29）/ 正向邻接 `adjacency` / 反向邻接 `reverse_adjacency` 三结构。
- **主要方法**：
  - 图构建：`add_file`(:60)、`add_dependency`(:94)、`_would_create_cycle`(:110 预防性环检测)、`build_from_architecture`(:175 LLM file_plan → 图)、`build_from_specs`(:519 OpenAPI → api/service/model 节点)、`_auto_add_dependencies`(:543 硬编码规则兜底)、`deduplicate`(:300 同名同类型去重)
  - 生成排序：`get_generation_order`(:622 Kahn 拓扑)、`get_generation_layers`(:729 分层并行)、`_break_cycles`(:676 DFS 打破循环)
  - 上下文注入：`get_context_for_file`(:775 预算分配 + 签名提取)、`get_dependency_summary`(:852)、`to_dict/from_dict/save/load`(:860-916)
  - 已有项目扫描：`build_from_existing_project`(:965 async)、`_build_graph_from_project`(:981)、`_parse_python_imports`(:1050)、`_parse_js_requires`(:1085)、`extract_dependencies_from_content`(:1121 增量反推)、`update_node_dependencies`(:1192)
  - 完整性：`validate_completeness`(:1221)、`get_missing_files`(:1243)、`add_missing_files`(:1254)
- **对外接口**：`get_context_for_file`、`get_affected_files`、`get_generation_order/layers`、`build_from_architecture`、`load/save`、`nodes/adjacency` 属性直接访问。

## 2. 依赖与被依赖

- **导入依赖**：`signature_extractor`（extract_signatures/get_context_budget :22）、`shadow_scanner`（scan_shadow_dependencies/SKIP_DIRS :23）、`dependency_rules`（DEPENDENCY_RULES/PATH_TYPE_RULES/EXTENSION_TYPE_MAP :24）、`adapters`（language_adapter/ImportInfo :482-485 惰性导入）、`app.agent.dynamic_model_router`（error_recovery 场景关联）。
- **生产使用方**：
  - `orchestrator_files.py:342-345`（`get_context_for_file(file_path, generated_contents or {})` 只传 2 参）、`:364/:630`（遍历 `nodes.keys()`）、`:797-799`（`get_affected_files` 跨文件补丁）
  - `orchestrator_generation/traditional_generate.py:161`（`DependencyGraph(language_adapter=...)` 建图）、`incremental_modify.py:20/63`（`DependencyGraph.load()`）、`:258/284/311/432/679/777/913`（增量更新/摘要/补缺）
  - `orchestrator_generation/spec_first_generate.py:10`、`architect.py:822-826`（`DependencyGraph(language_adapter=adapter)`）、`multi_model_agent.py:111/136`（dependency_hints 注入规划 prompt）、`orchestrator.py:14/83/126`（开关 + 持有实例）、`topology_scheduler.py:121`（`build_from_dependency_graph`）
- **测试覆盖**：`tests/unit/test_dependency_graph.py`（202 行 14 测试）。覆盖：add_file/add_dependency/affected_files/generation_layers/build_from_architecture（含显式依赖、缺失依赖「不报错」）/rules 兜底/extract_dependencies（python/js）/update_node_dependencies/generation_order。**未覆盖**：`build_from_existing_project`、`_build_graph_from_project`、`get_missing_files`、`validate_completeness`、`add_missing_files`、`_break_cycles`、`deduplicate`、`save/load`、`get_context_for_file` 预算逻辑。

## 3. 已探明 Bug

### DG1 [P2] `_build_graph_from_project` 调用缺参 → TypeError（接线即崩）

- **现象**：`_auto_add_dependencies()` 被无参调用，必抛 TypeError。
- **Bug 代码**：

```python
# dependency_graph.py:1022 - 缺参调用
self._auto_add_dependencies()

# dependency_graph.py:543 - 定义要求必填参数
def _auto_add_dependencies(self, files_with_imports: set):
```

- **根因**：:1022 漏传 `files_with_imports`；而 :280（build_from_architecture）传参正确。
- **影响**：`build_from_existing_project`（:965）→ `_build_graph_from_project`（:974）→ :1022 必崩。当前该入口**全库零调用**（rg 仅 :965/:982 定义处），为潜在故障（接线即崩，DMR8 同类非即时）。一旦增量上传项目场景接线即触发。
- **触发条件**：任何调用 `build_from_existing_project` 的路径。
- **验证方式**：`python3 -c` 实测 `_build_graph_from_project(tempdir)` 输出 `TypeError: missing 1 required positional argument`（已实测确认）。

### DG2 [P2] 泛化依赖反推返回 stem 而非完整路径，边永不建立

- **现象**：非 Python/JS 文件（Go/Rust/C# 等）的反推依赖永远无效。
- **Bug 代码**：

```python
# dependency_graph.py:1153-1164 - 泛化匹配收集 stem/name，append 的是 name 而非完整路径
possible_names = set()
for node_path in self.nodes.keys():
    possible_names.add(Path(node_path).stem)   # 'util'
    possible_names.add(Path(node_path).name)   # 'util.py'
for name in possible_names:
    if re.search(r'\b' + re.escape(name) + r'\b', content):
        deps.append(name)                       # 'util' 而非 'src/util.py'

# 消费处 :1032-1034 - add_dependency 要求 dep 是完整路径才加边
for file_path, dep_paths in generic_imports.items():
    for dep in dep_paths:
        self.add_dependency(file_path, dep)
```

- **根因**：匹配收集的是 `stem`/`name`，后续 `add_dependency`（:100）要求 `depends_on in self.nodes`（nodes key 为完整路径）→ stem 不在 nodes → 边静默丢弃。
- **影响**：增量场景下非 Python/JS 项目的依赖图完全失效（IM4「依赖图只解析 Python import」的直接成因之一）。
- **触发条件**：`extract_dependencies_from_content` 泛化分支（:1153 `if not patterns`）。
- **验证方式**：实测 `extract_dependencies_from_content('src/main.go', '调用 util')` 返回 `['util']`（非 `src/util.py`），add_dependency 后 `adjacency` 仍空（已实测确认）。

### DG3 [P2] `add_dependency` 静默丢弃缺失依赖，完整性三方法全为死逻辑

- **现象**：`get_missing_files` 恒返回 `[]`，`validate_completeness`/`add_missing_files` 永不生效。
- **Bug 代码**：

```python
# dependency_graph.py:96-100 - 依赖目标不在 nodes 则丢弃（注释声明为「避免外部库」）
def add_dependency(self, file_path, depends_on):
    if file_path not in self.nodes:
        self.add_file(file_path)
    if depends_on in self.nodes and depends_on != file_path:   # 缺失目标静默跳过
        ...  # 边仅在目标存在时建立

# :1243-1252 - 检查的是 adjacency 中的 dep 是否在 nodes，而该条件永真
def get_missing_files(self):
    for path in self.nodes:
        for dep in self.adjacency.get(path, set()):
            if dep not in self.nodes:   # 恒 False（add_dependency 已过滤）
                missing.add(dep)
```

- **根因**：缺失依赖在入口（:100）被静默丢弃，导致下游 `get_missing_files`（:1243）、`validate_completeness`（:1221）、`add_missing_files`（:1254）检查的对象恒完整——三方法全为死逻辑。`add_missing_files` 对 file_plan 的自动补缺（architect.py:803 依赖它）永不触发。
- **影响**：IM9「依赖图缺失静默回退全量」的根本成因；架构补缺能力（`add_missing_files`）形同虚设。
- **触发条件**：任何缺失依赖的 file_plan/增量场景。
- **验证方式**：实测 `add_dependency('app/main.py', 'app/nonexistent.py')` → `adjacency` 空、`get_missing_files()` == `[]`（已实测确认）。`test_build_from_architecture_handles_missing_dependencies`（test_dependency_graph.py:96）将「不报错」固化为预期行为，从不测 get_missing_files。

### DG4 [P2] `_break_cycles` DFS 递归无深度保护，长链 RecursionError

- **现象**：约 1500 层依赖链触发 `RecursionError: maximum recursion depth exceeded`。
- **Bug 代码**：

```python
# dependency_graph.py:682-698 - 纯递归 DFS，无深度限制
def dfs(node: str, path: List[str]):
    visited.add(node)
    rec_stack.add(node)
    ...
    for neighbor in self.adjacency.get(node, set()):
        if neighbor not in visited:
            dfs(neighbor, path)   # Python 默认递归上限 1000
```

- **根因**：`get_generation_order`（:630）/`get_generation_layers`（:739）每次调用先 `_break_cycles`，深依赖链（monorepo、自动依赖叠加）超过 1000 层即崩。
- **影响**：大项目长链生成排序崩溃；当前测试未覆盖（最浅图）。
- **触发条件**：依赖链深度 > ~1000 的文件集。
- **验证方式**：实测构造 1500 层链 `get_generation_order()` 抛 RecursionError（已实测确认）。

### DG5 [P3] Kahn 拓扑反复全量 sort，复杂度 O(V² log V)

- **Bug 代码**：

```python
# dependency_graph.py:654-655 - while 内每轮全量 sort
while queue:
    queue.sort(key=lambda x: self.nodes[x].priority if x in self.nodes else 99)
    node = queue.pop(0)
```

- **根因**：应使用优先队列（heapq），当前每轮 O(V log V) × V 轮。
- **影响**：2000+ 文件项目 `get_generation_order`/`get_generation_layers` 明显变慢；`to_dict`（:865 含 generation_order）每次 save 全量排序。
- **验证方式**：构造 N=3000 节点对比 heapq 实现计时。

### DG6 [P3] `deduplicate` 纯启发式评分，可能误删业务关键文件

- **Bug 代码**：

```python
# dependency_graph.py:342 - 评分无内容对比
score = in_degree * 10 + out_degree * 2 + depth * 5 + (20 if has_type else 0)
```

- **根因**：同名同 file_type 文件仅按入度/出度/深度/类型分差，无内容比对；file_type='utils' 不计 has_type（:340），utils 文件易被低分误删。
- **影响**：`build_from_architecture`（:283）自动去重可能删除仍被引用的实现文件；被删文件的出边被转移（:360-364），入边重定向（:352-358）——重定向后可能引入错误依赖。
- **验证方式**：构造两个同名 model 文件仅一个被引用，观察去重后最佳保留是否符合预期。

### DG7 [P3] `get_context_for_file` 生产调用恒走 32768 兜底，与模型窗口脱节

- **Bug 代码**：

```python
# dependency_graph.py:785-787 - 未传 context length 时固定 32768
if max_context_bytes <= 0:
    ctx_len = model_context_length if model_context_length > 0 else 32768
    max_context_bytes = get_context_budget(ctx_len)

# orchestrator_files.py:343-345 - 生产调用只传 2 参
dep_context = self.dependency_graph_obj.get_context_for_file(file_path, generated_contents or {})
```

- **根因**：生产调用方（orchestrator_files）从不传 `model_context_length`，预算恒按 32768 计算（`get_context_budget` 通常取其 ~40%），与模型实际窗口（如 128K）脱节 → 注入上下文偏保守、浪费可用窗口。
- **影响**：依赖文件注入量受限于固定小预算，模型可用上下文未充分利用；且 `extract_signatures` 签名预览长度不可控（:840-841 签名长度可能远大于预算，:846 扣减逻辑失真）。
- **验证方式**：对比 32768 与 131072 下 get_context_budget 输出差异。

### DG8 [P3] LLM 显式 `dependencies` 用文件名（非完整路径）时被 DG3 丢弃

- **Bug 代码**：

```python
# dependency_graph.py:262-266 - 直接把 LLM 声明的 dep 传给 add_dependency，不规范化
explicit_deps = file_info.get("dependencies", [])
for dep in explicit_deps:
    if dep and dep != path:
        self.add_dependency(path, dep)
```

- **根因**：LLM 若输出 `dependencies: ["models.py"]`（文件名）而非 `"models/user.py"`（路径），`:100` 过滤导致边丢失（DG3 同源）；实测完整路径可用、文件名被丢。
- **影响**：依赖图对 LLM 输出格式敏感，同名文件场景极易丢失依赖。
- **验证方式**：实测 `dependencies: ['models.py']` 与 `['models/user.py']` 的建边差异。

### DG9 [P3] `_parse_js_requires` 不解析路径别名，前端图不完整

- **Bug 代码**：

```python
# dependency_graph.py:1094-1098 - 只匹配相对路径（./ ../）
patterns = [
    r'import\s+.*?\s+from\s+["\'](\./[^"\']+)["\']',
    r'import\s+.*?\s+from\s+["\'](\.\./[^"\']+)["\']',
    ...
]
```

- **根因**：不解析 `@/components/X`、`src/...` 等别名 import，前端 TS/Vue 项目依赖图大量缺失（IM4 同源）。
- **影响**：增量修改场景前端文件受影响集 `get_affected_files` 漏报。
- **验证方式**：构造含 `@/` 别名的 .ts 文件实测解析结果。

### DG10 [P3] `_path_to_api_file` 多段路径合并单文件，粒度粗

- **Bug 代码**：

```python
# dependency_graph.py:950 - /api/users/{id}/posts 与 /api/users/{id} 混入不同路径
return f"app/api/{'_'.join(parts)}.py"
```

- **根因**：build_from_specs（:519）把每个 API 路径映射为一个平铺文件名，嵌套路径被 `_` 拼接，不同资源可能落同一文件。
- **影响**：OpenAPI 驱动的模型/API 文件规划粒度粗，依赖关系近似。
- **验证方式**：多段 API 路径实测映射文件。

## 4. 潜在问题与未知点

- `get_generation_layers`（:729）与 `get_generation_order`（:622）双实现，分层语义（并行层）未被生产使用（orchestrator_files 用 nodes.keys() 遍历 + get_context_for_file，未消费 layers）。
- `build_from_existing_project`（:965）完整功能（Python/JS/泛化解析 + 阴影依赖）当前零接线——增量修改实际走 `DependencyGraph.load` 磁盘图（incremental_modify.py:63），两套图来源（架构构建 vs 项目扫描）并存但扫描侧无消费者。
- `dependency_graph_validator`（spec_first_generate.py:21 引用）为独立模块，本次未扫，与本图形成「构建 vs 校验」双模块关系。
- `_would_create_cycle`（:110）每次 add_dependency BFS 全图，批量建图 O(E·V) 潜在慢，未验证。
- `_infer_file_type`（:920）PATH_TYPE_RULES 顺序敏感（首命中返回），未验证规则冲突时行为。

## 5. 修改建议（改什么 → 达成什么目的）

| # | 优先级 | 修改动作 | 达成目的 | 涉及位置 | 对应 Backlog |
|---|--------|---------|---------|---------|-------------|
| 1 | P2 | `_auto_add_dependencies(files_with_imports)` 补默认参数 `set()`（或 :1022 传入空集）；`build_from_existing_project` 接线前跑通 | 消除接线即崩的 TypeError，项目扫描路径可用 | dependency_graph.py:543/1022 | 待记 |
| 2 | P2 | 泛化反推改为返回完整路径：匹配到 name 后用 `_import_to_file_path` 或 nodes 精确查找映射回完整 path 再入图 | 多语言依赖反推真正生效，IM4 收敛 | dependency_graph.py:1153-1164 | 待记 |
| 3 | P2 | `add_dependency` 对缺失目标改为「记录 dangling 依赖」而非静默丢弃，`get_missing_files`/`add_missing_files`/`validate_completeness` 消费 dangling 表 | 激活架构补缺能力，修复 IM9 根因 | dependency_graph.py:100/1221-1295 | 待记 |
| 4 | P2 | `_break_cycles` 改为显式栈迭代（或 DFS 加深度守卫），消除 RecursionError | 长链图不崩 | dependency_graph.py:682-698 | 待记 |
| 5 | P3 | Kahn 换 heapq 优先队列，删除 while 内 sort | 大图 O(V log V) | dependency_graph.py:644-664 | 待记 |
| 6 | P3 | `deduplicate` 增加内容/依赖签名比对后再删除，或默认关闭由用户确认 | 防误删关键文件 | dependency_graph.py:300-373 | 待记 |
| 7 | P3 | `get_context_for_file` 由调用方传 model_context_length（或读 DMR model_config），删除 32768 固定兜底 | 上下文预算与模型窗口匹配 | dependency_graph.py:785-787、orchestrator_files.py:343 | 待记 |
| 8 | P3 | LLM `dependencies` 字段做路径规范化（补 `models/` 前缀或 `_import_to_file_path` 解析）后再 add_dependency | 对 LLM 输出格式鲁棒 | dependency_graph.py:262-266 | 待记 |
| 9 | P3 | `_parse_js_requires` 补别名解析（@/、src/） | 前端图完整，get_affected_files 不漏报 | dependency_graph.py:1094-1118 | 待记 |
| 10 | P3 | `_path_to_api_file` 按资源层级建目录（app/api/<section>/<resource>.py） | OpenAPI 规划粒度合理 | dependency_graph.py:941-958 | 待记 |

## 6. 演化方向关联

- 依赖图是「编排层图形化」（EVOLUTION.md §5.1，编排层 → Orchestrator-worker）的**执行前端**：生成顺序 = 任务的 DAG 调度。当前 Kahn 排序（DG5）与递归（DG4）是大图化的阻塞项；分层生成（get_generation_layers）已是 worker 并行化的雏形但未接线。
- 两套图来源（build_from_architecture 架构驱动 vs build_from_existing_project 项目扫描）与两套增量实现（IncrementalModify 依赖图驱动 vs IncrementalGenerate 会话驱动，incremental_modify.md）呼应——项目扫描侧当前零接线（DG1 印证），需归位。
- 依赖完整性（DG3）与 IM9「依赖图缺失静默回退全量」、architect.py:803 补缺能力闭环——修复 DG3 即激活补缺主线。
- 图构建侧（本模块）与校验侧（dependency_graph_validator，spec_first_generate.py:21）构成「构建-校验」对，符合四阶段中「验证闭环图形化」的拆分方向。
