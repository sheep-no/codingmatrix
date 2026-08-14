# CodeValidator 演化深扫文档

> 版本：v0.1 | 扫描日期：2026-08-09 | 状态：已完成
> 归属：Agent 大系统 / 支撑模块（代码验证器，语法/导入/运行时/API/跨文件 + 缓存）
> 路径：app/agent/code_validator.py（767 行）
> 索引：[TASKS.md](../TASKS.md)

## 1. 模块作用与功能

多语言代码验证器：对生成/修复的代码做语法、导入、运行时、API 兼容性、跨文件一致性验证，带 LRU 缓存。

- **核心类**：`CodeValidator`（code_validator.py:20）——实例需 `project_path`（:49）。
- **验证方法**：
  - 单文件：`validate_syntax`(:128 ast.parse)、`validate_imports`(:143 importlib.find_spec)、`validate_runtime_imports`(:222 exec_module 实际执行)、`validate_api_compatibility`(:304 库版本规则)、`validate_js_syntax`(:336 node -c)、`validate_html_structure`(:357)、`validate_css_syntax`(:385 括号计数)、`validate_single_file`(:503 汇总，修复循环用)
  - 全项目：`validate_cross_file_consistency`(:409 AST 符号 + main.py 导入 + 前端路由)、`validate_requirements`(:550 requirements/pyproject/Pipfile)、`run_full_validation`(:642 并发 + 缓存)
- **缓存**：类级 `_lru_cache` OrderedDict（:23）、`_compute_content_hash`(:52)、`_clear_old_cache`(:58)、`get_cached_validation`(:73)、`cache_validation`(:97)、`get_cache_stats`(:115)。
- **对外接口**：`run_full_validation`（最终验证）、`validate_single_file`（修复循环）、`_compute_content_hash`（orchestrator_files 复用）。

## 2. 依赖与被依赖

- **导入依赖**：标准库（re/sys/ast/time/asyncio/importlib.util）；`tomllib`（pyproject，:580）；`toml`（Pipfile，:597，第三方未声明）。
- **生产使用方**：
  - `orchestrator_generation/mixin.py:89` `self.validator = CodeValidator(self.output_dir)`（生成/增量基类持有）
  - `orchestrator.py:121` `self.validator: Optional[CodeValidator]`
  - `error_recovery.py:155/295/402`（`validate_single_file` 修复循环逐轮验证）
  - `traditional_generate.py:284`、`spec_first_generate.py:752`（`run_full_validation` 最终验证报告）
  - `orchestrator_files.py:702/754`（直接访问 `self.validator._validation_cache[cache_key]`，绕过公共方法）
- **姊妹验证器（另两套并存）**：
  - `utils.is_valid_code_content`（utils.py:243，语言无关内容有效性，防 JSON/MD 伪代码）+ `validate_syntax_for_extension`（:303）——被 spec_first_generate/traditional_generate/incremental_modify 大量消费（~15 处）
  - `SandboxValidator` + `HARDCODED_RULES`（utils.py:341-365，AI 生成验证脚本的沙箱体系，未接线）
  - `agent_core.py:807/885/906/1268/1950` 自带的 `run_full_validation`/`_validate_single_file`（第四处验证实现）
- **测试覆盖**：`tests/unit/test_code_validator.py`（72 行 5 测试）——仅测 `_compute_content_hash`/`cache_validation`/`get_cache_stats`/LRU 上限，且缓存测试用**真实文件路径**（NamedTemporaryFile）；**验证逻辑（syntax/imports/runtime/api/cross_file/requirements/single_file/run_full_validation）零覆盖**。

## 3. 已探明 Bug

### CV1 [P2] `run_full_validation` 缓存读写恒失败（合成 key 被当文件路径 open）

- **现象**：最终验证永远 cache miss，缓存条目恒为 0。
- **Bug 代码**：

```python
# code_validator.py:673-675 - 合成字符串 key
cache_key = f"full_validation:{content_hash}"
cached = self.get_cached_validation(cache_key)   # cache_key 是字符串不是 Path

# code_validator.py:73-79 - get_cached_validation 却把参数当文件打开
def get_cached_validation(self, file_path: Path) -> Optional[Dict]:
    cache_key = None
    try:
        with open(file_path, 'r', encoding='utf-8') as f:   # open("full_validation:xxx") 抛 FileNotFoundError
```

- **根因**：`get_cached_validation`/`cache_validation` 设计为「真实文件路径 → 读内容算 hash 作 key」，但 `run_full_validation`（:675/:755）直接传合成字符串 `full_validation:{hash}`，`open` 必然失败 → 走 except 返回 None / 写不进去。测试（test_code_validator.py:28-43）只用真实路径，掩盖了该不匹配。
- **影响**：全项目最终验证缓存完全失效（每次全量重验）；`_cache_hits` 恒 0。
- **触发条件**：每次 `run_full_validation`。
- **验证方式**：实测连续两次 `run_full_validation`，`cache_hit` 恒 False、`_lru_cache` entries 恒 0（已实测确认）。

### CV2 [P2] `validate_runtime_imports` 执行任意模块级代码，无超时且阻塞事件循环

- **现象**：验证时真实执行被验证模块的模块级代码；`asyncio.wait_for` 无法打断同步阻塞。
- **Bug 代码**：

```python
# code_validator.py:281-284 - 实际 exec 模块
module = importlib.util.module_from_spec(spec)
sys.modules[module_name] = module
try:
    spec.loader.exec_module(module)   # 同步执行模块级代码
```

- **根因**：`exec_module` 同步执行任意顶层代码。副作用：连接数据库、发请求、写文件、`print`；阻塞：模块级 `time.sleep`/阻塞 I/O 卡死事件循环（`run_full_validation` :695 的 `asyncio.gather` 全部被同一事件循环上的阻塞拖死），且 `wait_for` 的 timeout 对同步阻塞无效（事件循环被占，无法切换）。
- **影响**：验证阶段真实运行生成/修复的代码——安全与稳定风险；error_recovery 修复循环（validate_single_file :519 → :284）每轮都会 exec 被修复模块；一个含阻塞模块级代码的文件即可拖死整个最终验证。
- **触发条件**：生成项目的任一 .py 含模块级副作用或阻塞 I/O。
- **验证方式**：实测 `main.py` 含 `print(os.name)` 在验证时打印（副作用实证）；`slow.py` 含 `time.sleep(3)`，`asyncio.wait_for(timeout=1)` 后仍执行完毕（阻塞实证，已实测确认）。
- **关联**：修复方向应改为 `compile` + AST 静态检查（不 exec），或 subprocess + 超时 + 资源限制的隔离沙箱（utils.py:341 SandboxValidator 方向）。

### CV3 [P2] 相对导入误报「缺少依赖」（project_root 只认 src/ 和 tests/）

- **现象**：不含 src/ 或 tests/ 目录的普通项目（如 `app/` 为主包），所有 `from app.xxx import` 被误判为缺失依赖。
- **Bug 代码**：

```python
# code_validator.py:179-186 - 只认 src/ 或 tests/ 目录
for _ in range(10):
    if (current / 'src').is_dir() or (current / 'tests').is_dir():
        project_root = current
        break
```

- **根因**：项目根判定只认 `src`/`tests` 目录。`app/` 为主包的项目找不到 root → 项目根/`src` 不加入 sys.path → `find_spec('app')` 返回 None → 误报。
- **影响**：`run_full_validation`（最终验证）与 `validate_single_file`（修复循环）对 `app/` 布局项目大量误报导入缺失 → `is_valid=False` → 触发不必要的修复循环或误报最终验证失败。
- **触发条件**：项目根含 `app/` 包但无 `src/` 或 `tests/`。
- **验证方式**：实测构造 `app/` 主包项目，`validate_imports(main.py)` 返回 `['缺少依赖: mod', '缺少依赖: app.mod']`（已实测确认）。

### CV4 [P3] 前端 API 一致性检查为空操作

- **Bug 代码**：

```python
# code_validator.py:491-497 - 检查到不匹配时只 pass，不报错也不警告
api_calls = re.findall(r'(?:fetch|axios\.(?:get|post|put|delete))\(["\'](/api/[^"\']+)["\']', js_content)
for call in api_calls:
    if api_routes_defined and not any(call.startswith(r) or r.startswith(call.split('?')[0]) for r in api_routes_defined):
        pass   # 只警告，不报错 —— 实际连警告都没有
```

- **根因**：前端 API 与后端路由一致性检查逻辑只 `pass`，`errors` 从不追加前端 API 项。
- **影响**：`validate_cross_file_consistency` 对前端 API 调用的校验完全无效。
- **验证方式**：构造 fetch 调用不存在的 /api 路径，观察 cross_file_errors 为空。

### CV5 [P3] OAuth2PasswordBearer 兼容规则过时、方向相反

- **Bug 代码**：

```python
# code_validator.py:315 - 要求 token_url 而非 tokenUrl
if 'OAuth2PasswordBearer' in source and 'token_url=' not in source and 'tokenUrl=' in source:
    errors.append("FastAPI 兼容性: OAuth2PasswordBearer 参数应为 'token_url=' 而非 'tokenUrl='")
```

- **根因**：现代 FastAPI 的 `OAuth2PasswordBearer` 标准参数是 `tokenUrl`（`token_url` 是早期版本）。此规则对正确代码误报，且 `API_COMPATIBILITY_RULES`（:34-41）声明了 `{"token_url": "tokenUrl"}` 映射却未被此处使用。
- **影响**：含 `OAuth2PasswordBearer(tokenUrl=...)` 的正确代码被误报 → 不必要的修复循环。
- **验证方式**：构造 `OAuth2PasswordBearer(tokenUrl="token")` 调用 `validate_api_compatibility` 观察误报。

### CV6 [P3] Pipfile 分支依赖未声明的 `toml` 包，缺失时误报依赖齐全

- **Bug 代码**：

```python
# code_validator.py:596-603 - toml 非标准库（仅 tomllib 是）
import toml
with open(pipfile, 'r') as f:
    pipdata = toml.load(f)
```

- **根因**：`toml` 是第三方包（标准库只有 3.11+ 的 `tomllib`），requirements 未声明（搜索确认无 toml 依赖）；环境未装时 except 吞掉 → `required=[]` → 返回 `(True, [])` 误报依赖齐全。
- **验证方式**：`python -c "import toml"` 报 ModuleNotFoundError 即确认。

### CV7 [P3] 类级缓存/统计跨实例全局共享 + MAX_CACHE_SIZE 未使用

- **Bug 代码**：

```python
# code_validator.py:23-31 - 全部类级，跨实例共享
_lru_cache: OrderedDict = OrderedDict()
_max_cache_bytes = 50 * 1024 * 1024
_cache_size_bytes = 0
_cache_hits = 0
MAX_CACHE_SIZE = 100   # 定义未使用（实际用 _max_cache_bytes）
```

- **根因**：ERL5/MCP1 同类全局状态——不同 project_path 实例共享缓存与统计；`MAX_CACHE_SIZE` 声明但 LRU 修剪只按字节（:69-71）。
- **影响**：多项目并发时缓存相互污染、统计串扰。
- **验证方式**：两个实例 `get_cache_stats` 相互累计。

### CV8 [P3] 验证器四套实现并存，语义分裂（结构性）

- **现象**：同一验证职责四套实现：①`CodeValidator`（本模块）；②`utils.is_valid_code_content`（utils.py:243 内容有效性，非 py 扩展名语法恒通过 :337-338）；③`SandboxValidator`（utils.py:365，AI 生成验证脚本，未接线）；④`agent_core.py:807` 自带 `run_full_validation`。
- **根因**：演化历史遗留，各套对「有效」定义不同：is_valid_code_content 只查「非 JSON/MD」，CodeValidator 做真实语法/导入/运行时。
- **影响**：spec_first/traditional 的生成后校验（is_valid_code_content）与最终验证（CodeValidator.run_full_validation）语义不一致，中间产物可能绕过语法检查（非 py 扩展名直接放行）。
- **验证方式**：对比同一文件两套验证结果。

## 4. 潜在问题与未知点

- `validate_imports`（:203-211）对第三方库做 `find_spec`，但项目内 `src` 布局已处理；`src` 与 `app` 双布局并存时 root 判定歧义未验证。
- `validate_runtime_imports` 对 `sys.modules` 的 `module_name = file_path.stem`（:243）在并发同名 stem 文件下存在覆盖窗口（实测瞬时模块无残留，竞态难复现，标记 P3）。
- `validate_requirements`（:640）无缺失包时返回 `[f"未安装的包..." if missing else ""]` 含空字符串，仅 run_full_validation 在 `not dep_ok` 分支消费，未验证其他潜在调用方。
- `validate_html_structure`（:368-379）只查 `html/head/body` 三标签闭合，覆盖有限。

## 5. 修改建议（改什么 → 达成什么目的）

| # | 优先级 | 修改动作 | 达成目的 | 涉及位置 | 对应 Backlog |
|---|--------|---------|---------|---------|-------------|
| 1 | P2 | `run_full_validation` 缓存改用「真实文件列表 + 内容 hash」为 key 直接存取 `_lru_cache`（参考 orchestrator_files:702/754 的直接访问方式），或给 `get_cached_validation` 加字符串 key 入口 | 最终验证缓存生效 | code_validator.py:673-679/753-765 | 待记 |
| 2 | P2 | `validate_runtime_imports` 改为 `compile()` 编译 + AST 静态检查（不 exec），或 subprocess 隔离沙箱 + 超时 + 资源限制 | 验证不执行任意代码、不阻塞事件循环 | code_validator.py:281-297 | 待记 |
| 3 | P2 | project_root 判定扩展为「存在 `app/`、`src/`、`tests/`、`pyproject.toml`、`setup.py` 任一即视为根」 | 消除 app/ 布局项目相对导入误报 | code_validator.py:179-186/252-262 | 待记 |
| 4 | P3 | `validate_cross_file_consistency` 前端 API 检查补真实报错（或删除空操作段） | 跨文件校验覆盖前端 | code_validator.py:485-499 | 待记 |
| 5 | P3 | 修正 OAuth2PasswordBearer 规则方向（现代为 `tokenUrl`），并实际消费 `API_COMPATIBILITY_RULES` 映射 | 消除正确代码误报 | code_validator.py:315/34-41 | 待记 |
| 6 | P3 | Pipfile 分支改用 `tomllib`（3.11+）或声明 `toml` 依赖 | 依赖校验不静默失效 | code_validator.py:596-603 | 待记 |
| 7 | P3 | 缓存改实例级（按 project_path 隔离），删除未用的 `MAX_CACHE_SIZE` | 消除跨项目污染 | code_validator.py:23-31 | 待记 |
| 8 | P3 | 收敛验证器实现：is_valid_code_content/CodeValidator/SandboxValidator/agent_core 四套归位为「内容有效性 → 语法 → 运行时」分层 | 统一「有效」语义，消除绕过语法检查路径 | utils.py:243/341、agent_core.py:807 | 待记 |

## 6. 演化方向关联

- 验证器是「验证闭环图形化」（EVOLUTION.md §5.1，LangGraph Evaluator 方向）的核心评估端——当前四套实现并存（CV8）是归位最大障碍，收敛方向与 SpecFirst 单入口（spec_first_generator.md）一致：CodeValidator 收编为唯一语法/运行时验证器，is_valid_code_content 降为生成侧快速预检。
- CV2（exec 任意代码）在修复循环（error_recovery_loop.md ERL 系列）与最终验证（traditional_generate.md）中每轮触发——是「修复→验证」闭环的性能/安全阻塞项，应先于 LCL1 收敛处理。
- CV1 缓存失效与 orchestrator_files.py:702/754 绕过公共方法的直接访问并存，属「同一资源两套访问路径」——归入统一收敛主线。
- SandboxValidator（utils.py:341）是「运行时验证」的既成方向（隔离沙箱），CV2 修复可复用其设计而非重造。
