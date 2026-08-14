# IntegrityValidator 演化深扫文档

> 版本：v0.1 | 扫描日期：2026-08-09 | 状态：已完成
> 归属：Agent 大系统 / 支撑模块（跨文件完整性验证器）
> 路径：app/agent/integrity_validator.py（508 行）+ 语言适配器 adapters/（python.py / javascript.py / generic.py）
> 索引：[TASKS.md](../TASKS.md)

## 1. 模块作用与功能

生成流程末端的静态完整性验证器：检查生成文件集合的跨文件引用一致性——包入口文件存在性（多语言）、导入路径可解析、前端与后端 API 契约一致性。结果 `IntegrityResult`（passed/issues/missing_files/fixed_files），`generate_fixes` 据 missing_files 生成补缺文件（真实 re-export 内容，非占位符）。

- **核心类**：`IntegrityValidator`（:55）、`IntegrityIssue`（:23）、`IntegrityResult`（:33）。
- **验证流程**（`validate` :104-130）：① `_check_package_init` 查包入口 → ② `_validate_imports` 校验导入 → ③ 混合前后端时 `_validate_api_contracts`（warning 级）。
- **修复流程**（`generate_fixes` :398-440）：仅遍历 `result.missing_files` 生成入口文件内容（`_generate_init_content` :442 扫描同目录 re-export / `_generate_index_content` :472）。
- **语言适配**：依赖 `adapters/language_adapter.py` 抽象（parse_imports/resolve_import_to_file/is_project_module/validate_package_structure）；无 adapter 时 `_check_package_init` 从文件扩展名自动推断（:137-149）。

## 2. 依赖与被依赖

- **导入依赖**：`adapters/language_adapter.py`（PythonLanguageAdapter/JavaScriptLanguageAdapter/GenericAdapter）、`re`。
- **生产使用方**：
  - `spec_first_generate.py:638-658`（IntegrityValidator 补入口 + :660-682 **DependencyGraph 补缺**双路径）
  - `traditional_generate.py:208-229`（`enable_validation` 时校验 + generate_fixes 补入口，**非原子写** open 直接写，:222-228）
- **被依赖（模块内部）**：`utils.write_file_atomic`（spec_first 消费方用它写修复文件）。
- **测试覆盖**：**零**——tests/ 下无 integrity_validator 相关测试（补扫对象中首个无测试覆盖的模块）。

## 3. 已探明 Bug

### IV1 [P2] missing_module 不进 missing_files → generate_fixes 不修缺失模块，补缺闭环断

- **现象**：`from app.missing_module import x` 报 missing_module issue，但 `generate_fixes` 只生成入口文件，缺失模块永不补。
- **Bug 代码**：

```python
# integrity_validator.py:174 / :187 - missing_files 仅在 _check_package_init 追加
result.missing_files.append(init_path)

# :416 - generate_fixes 只遍历 missing_files（入口文件）
for missing in result.missing_files:
```

- **根因**：`_validate_imports` 的 missing_module 问题从不 append 进 `result.missing_files`，`generate_fixes` 的补缺只覆盖入口文件。
- **实测**：`app/main.py` 含 `from app.missing_module import x`，validate 后 `missing_files=['app/index.js']`（见 IV6），missing_module 不修。
- **影响**：完整性补缺闭环**双断**——IntegrityValidator 侧不补模块（IV1），DependencyGraph 侧 `get_missing_files` 恒空（DG3，dependency_graph.py）→ spec_first_generate.py:660-682 的 DependencyGraph 补缺路径永不触发。两条「检测缺失模块→生成补缺文件」路全部断。
- **验证方式**：见实测（/tmp/opencode 脚本，missing_module 报 issue 但 generate_fixes 输出不含该模块）。

### IV2 [P2] `_check_package_init` 中途切换 self.language_adapter：混合项目后端导入校验 + API 提取全失效

- **Bug 代码**：

```python
# integrity_validator.py:137-149 - validate 中途改 self.language_adapter
adapter = self.language_adapter
if not adapter:
    extensions = {Path(f).suffix for f in files}
    if extensions & {'.js', '.jsx', '.ts', '.tsx'}:
        adapter = LanguageAdapterRegistry.get_adapter('javascript')
    elif extensions & {'.go'}:
        adapter = LanguageAdapterRegistry.get_adapter('go')
    elif extensions & {'.java'}:
        adapter = LanguageAdapterRegistry.get_adapter('java')
    if adapter:
        self.language_adapter = adapter
```

- **根因**：检测逻辑「有任何 .js 即整体切 JavaScript」（**无 python 分支**）。调用方未传或传错 adapter 时，混合项目（Python/Go 后端 + JS 前端，全栈项目最常见形态）被整体当 JS：`_validate_imports` 用 JS 语法解析 Python 文件（parse_imports 零匹配 → 后端导入**全部漏检**）；`_extract_backend_apis` 的 backend_extensions 变成 JS extensions（不含 .py）→ 后端 API 提取为空 → 前端调用**全部误报不存在**。
- **实测**：`app/main.py`（`from app.missing import x`）+ `web/index.js` 无 adapter 传入 → missing_module **零 issue**（JS adapter 漏检）。
- **影响**：全栈生成项目的后端导入校验与 API 契约校验在该路径下静默失效。
- **验证方式**：见实测（IV16，混合项目缺失导入零 issue）。

### IV3 [P2] `_api_endpoint_exists` 前缀误判，漏报真实缺失端点

- **Bug 代码**：

```python
# integrity_validator.py:390-395
api_pattern = re.sub(r'\{[^}]+\}', r'[^/]+', api_path)
if re.match(f'^{api_pattern}$', endpoint):
    return True
if endpoint.startswith(api_path) or api_path.startswith(endpoint):
    return True
```

- **根因**：`startswith` 前缀匹配把 `/api/users` 判为 `/api/user` 的子路径、`/api/username/123` 判为 `/api/user` 的子路径——**资源名被当路径前缀**。且 `{id}` 参数转换未 `re.escape` 路径特殊字符。
- **实测**：后端仅 `@app.get("/api/user")`，前端调 `/api/users`、`/api/user/123` → **零 warning**（误判存在）。API 契约校验对真实缺失端点漏报。
- **影响**：契约校验形同虚设——漏报率主导，生成的报错几乎只来自 IV2 的全误报。
- **验证方式**：带 PythonLanguageAdapter 跑混合项目（见实测）。

### IV4 [P2] API 契约校验完全忽略 HTTP method

- **Bug 代码**：

```python
# integrity_validator.py:354-380 - 前端调用不记录 method
calls.append({'endpoint': endpoint, 'file': file_path})

# :384-396 - 匹配只比对路径
def _api_endpoint_exists(self, endpoint, apis):
    for api in apis:
        api_path = api['path']
```

- **根因**：`_extract_backend_apis` 提取了 method（:344 `method = match.group(1).upper()`），但 `_api_endpoint_exists` 只比 path；`_extract_frontend_api_calls` 的 fetch 分支本就无 method、axios 分支有方法名但未保存。
- **实测**：后端仅 `@app.post("/api/todo")`，前端 GET 调 `/api/todo` → **零 warning**（method 不匹配不报）。
- **影响**：前端用错 HTTP 方法的调用不报；契约语义（method×path 二元组）未落地。
- **验证方式**：见实测。

### IV5 [P2] 导入校验前缀白名单漏检：非 app/src 项目根包名被跳过

- **Bug 代码**：

```python
# adapters/python.py:358-382 is_project_module
project_prefixes = ['app', 'src', 'lib', 'pkg', 'internal', 'core']
if top_level in project_prefixes:
    return True
return False

# integrity_validator.py:198 - 非项目模块直接跳过
if imp.is_relative or not self.language_adapter.is_project_module(imp.module):
    continue
```

- **根因**：`is_project_module` 用前缀白名单（app/src/lib/pkg/internal/core）判定项目边界。项目根包名不在白名单（如 `myproject`、`backend`、`server`、`company_api`）→ 模块被判「非项目内」→ **导入校验整体跳过**。
- **影响**：与 CV3（code_validator project_root 只认 src/tests）、DG9（JS 别名）同类——「项目边界误判」主线。大量真实项目的顶层包名非白名单。
- **验证方式**：`from myproject.mod import x` 且 myproject 无对应文件 → 不报 issue（实码可证）。

### IV6 [P3] 无 adapter 时 fallback 硬编码 index.js 作为入口文件

- **Bug 代码**：

```python
# integrity_validator.py:175-187
init_file = "index.js"  # 通用默认值
init_path = f"{pkg}/{init_file}"
```

- **根因**：无 language_adapter 时通用 fallback 假设入口是 index.js，对 Python 项目完全错误。
- **实测**：`app/main.py` + `app/__init__.py`（入口已存在）无 adapter → 仍报「包缺少入口文件: app」建议 `app/index.js`，`missing_files=['app/index.js']`。假阳性 + 生成错误语言文件。
- **影响**：仅无 adapter 场景触发（生产调用方都传 adapter），假阳性误导补缺。
- **验证方式**：见实测。

### IV7 [P3] `_extract_backend_apis` 正则仅匹配 `@app.`/`@router.` 且不转义路径

- **Bug 代码**：

```python
# integrity_validator.py:342
pattern = r'@(?:app|router)\.(get|post|put|delete|patch)\s*\(\s*["\']([^"\']+)["\']'
```

- **根因**：硬编码 app/router 变量名——APIRouter(prefix=...) 的 prefix 拼接、`@api_router.post`、Flask 蓝图、`@bp.get` 等全部漏检；路径参数 `[^/]+` 转换未 re.escape（`/api/v1.0/x` 的 `.` 当任意字符）。
- **影响**：后端 API 提取覆盖率低，契约校验基线不准。
- **验证方式**：`@bp.get("/api/x")`（蓝图）→ 不被提取（实码可证）。

### IV8 [P3] `_extract_top_level_symbols` 用正则提取符号，非 AST

- **Bug 代码**：

```python
# integrity_validator.py:504
re.finditer(r'^(?:async\s+)?def\s+(\w+)\s*\(|^class\s+(\w+)', content, re.MULTILINE)
```

- **根因**：注释/字符串里的 `def fake(` 被误提取进 `__init__.py` 的 re-export；多行签名、装饰器缩进变体漏提。影响 `_generate_init_content` 生成的 re-export 质量（import 不存在的符号 → 引入新错误）。
- **影响**：修复本身可能制造 import 错误，降低补缺修复可信度。
- **验证方式**：`# def fake():` 注释 → 被提取（实码可证）。

### IV9 [P3] `generate_fixes` 父目录跳过逻辑语义错误（不触发但意图错）

- **Bug 代码**：

```python
# integrity_validator.py:419-421
parent = str(Path(missing).parent)
if parent in [str(Path(m).parent) for m in result.missing_files if m != missing]:
    continue  # 跳过，父目录也是缺失的
```

- **根因**：意图是「父目录本身缺失则跳过」（`pkg/sub/__init__.py` 的父 `pkg/sub` 若不在文件里应整体跳过），实现却是「另一个 missing 文件的父目录与当前相同则跳过」——两个入口文件不可能同父目录，条件恒 False，死逻辑；父目录缺失的深层判断（`parent` 不在 `files`）从未检查。
- **影响**：死逻辑，当前无行为影响；若修好应实现真正意图。
- **验证方式**：实码可证（恒 False）。

### IV10 [P3] 完整性验证器零测试覆盖

- **现象**：tests/ 下无 integrity_validator 相关测试。3 个 P2 级 API 契约 bug（IV3/IV4）+ IV1/IV2 全部无测试防线；`_api_endpoint_exists` 的前缀误判与 method 忽略属于「实现与语义不一致」类，完全未被捕获。
- **影响**：契约校验是 warning 级，误判/漏报不影响流程通过，但降低验证可信度；测试为零使修复回归无保障。

## 4. 潜在问题与未知点

- `_validate_imports` 的相对导入：PythonAdapter `resolve_import_to_file`（python.py:243-249）相对导入只生成一层候选（`{base}/{module}.py` + `__init__.py`），`from .sub.x import y` 多层相对导入解析未验证。
- `_module_exists`（:277-307）的 adapter 分支是死代码（`_validate_imports` 的 else fallback 里 `self.language_adapter` 恒 None），但 fallback 分支是活路径；语义冗余。
- `validate` 的 `has_frontend` 含 `.css`/`.html`，但 `_extract_frontend_api_calls` 只认 `.js/.ts/.vue/.jsx/.tsx`——纯 `.html` 前端（如 CDN 方式）会触发 `_validate_api_contracts` 但提取恒空，空转。
- `_generate_init_content` 的 import 行 `from .module import a, b` 若同目录文件间循环依赖，生成的 re-export 可能引入循环 import，未验证。
- 调用方 traditional_generate.py:222-228 用 `open().write()` 非原子写补缺文件（TG1 同源，非 write_file_atomic），spec_first 消费方正确使用 `write_file_atomic`。

## 5. 修改建议（改什么 → 达成什么目的）

| # | 优先级 | 修改动作 | 达成目的 | 涉及位置 | 对应 Backlog |
|---|--------|---------|---------|---------|-------------|
| 1 | P2 | `_validate_imports` 的 missing_module 追加进 `result.missing_files`，`generate_fixes` 按语言生成 stub（Python: `"""Module: ..."""`，JS: 空导出）；与 DependencyGraph 补缺（DG3 修复后）收敛为统一补缺入口 | 打通完整性补缺闭环（现与 DG3 双断） | integrity_validator.py:205-212/416 | 待记 |
| 2 | P2 | `_check_package_init` 的 adapter 推断改为**每文件按扩展名分派**（后端文件用后端 adapter、前端文件用 JS adapter），或移除自动切换强制调用方传入 | 混合项目后端导入校验/API 提取不再静默失效 | integrity_validator.py:137-149 | 待记 |
| 3 | P2 | `_api_endpoint_exists` 删除 `startswith` 前缀匹配，仅用路径正则（`re.escape` 特殊字符 + `{param}` → `[^/]+`） | 消除前缀误判漏报 | integrity_validator.py:390-395 | 待记 |
| 4 | P2 | 契约比对改为 (method, path) 二元组：前端调用记录 method（fetch 缺省 GET），后端 method 不匹配即报 | method 维度纳入契约校验 | integrity_validator.py:354-396 | 待记 |
| 5 | P2 | `is_project_module` 改为「解析后按生成的 files 集合判定」（module 前缀 ∈ files 中路径的顶层）或让调用方显式传 project root 包名 | 非白名单项目根包导入校验生效（与 CV3 同主线收敛） | adapters/python.py:358-382 | 待记 |
| 6 | P3 | fallback 入口文件按文件扩展名主流推断（有 .py → `__init__.py`）而非硬编码 index.js | 消除无 adapter 场景假阳性 | integrity_validator.py:175-187 | 待记 |
| 7 | P3 | 后端 API 提取用 AST/更宽正则（支持 prefix 拼接、蓝图）；路径参数转换 re.escape | API 提取覆盖提升，契约基线准确 | integrity_validator.py:342 | 待记 |
| 8 | P3 | `_extract_top_level_symbols` 改 ast 解析（忽略注释/字符串、支持多行签名） | 补缺 re-export 不引入假符号 | integrity_validator.py:499-508 | 待记 |
| 9 | P3 | `generate_fixes:419-421` 改为检查「父目录本身不在 files 中则跳过该入口补缺」 | 实现真实意图，避免为缺失父目录生成孤立入口 | integrity_validator.py:419-421 | 待记 |
| 10 | P3 | 补 integrity_validator 单测（API 契约 method/前缀、missing_module 进 fixes、混合项目 adapter 分派） | 修复回归有保障，固化契约语义 | tests/ | 待记 |

## 6. 演化方向关联

- IntegrityValidator 是验证栈的**跨文件静态验证器**，与 CodeValidator（单文件语法/依赖）、DependencyGraph（架构补缺）、CrossValidator（双模型对抗）构成生成后验证链。**IV1 + DG3 双断**使「检测缺失 → 补缺」闭环在当前代码里完整失效，是 EVOLUTION §5.1 验证闭环语义统一的直接阻塞项。
- API 契约校验（IV3/IV4）是「前端与后端契约一致性」方向（CV4 前端 API 一致性检查空操作同主线）——当前契约校验方法维度缺失 + 前缀误判，实际是**误报（IV2）与漏报（IV3/IV4）并存**。
- IV5 前缀白名单误判与 CV3（code_validator project_root 只认 src/tests）、DG9（JS 别名）归入「项目边界判定」收敛主线——统一改为「以生成文件集合动态判定项目根」。
- `_check_package_init` 的 adapter 中途切换（IV2）是「语言适配器职责边界」问题——adapter 应随文件分派而非全局单一，与 test_runner 的 FrameworkDetector（单语言检测）同一设计约束。
