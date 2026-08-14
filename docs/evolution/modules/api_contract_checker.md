# APIContractChecker 演化深扫文档

> 版本：v0.1 | 扫描日期：2026-08-09 | 状态：已完成
> 归属：Agent 大系统 / 支撑模块（前后端 API 契约一致性检查器）
> 路径：app/agent/api_contract_checker.py（501 行）
> 索引：[TASKS.md](../TASKS.md)

## 1. 模块作用与功能

多 Agent 架构中的 API 契约一致性检查器：从后端代码提取路由定义（FastAPI/Flask/Django），从前端提取 API 调用（fetch/axios/XMLHttpRequest），对比路径+方法一致性，生成缺失/方法不匹配报告与修复建议。附带 API 契约生成（注入前端生成 prompt）与便捷函数。

- **核心类**：`APIContractChecker`（:57）、`APIEndpoint`（:33）、`ConsistencyIssue`（:46）。
- **提取**：`extract_backend_endpoints`（:108，按框架选模式，自动检测）、`extract_frontend_endpoints`（:169）。
- **对比**：`check_consistency`（:232，双端全量，missing_backend error / missing_frontend warning / method_mismatch）、`check_single_file_consistency`（:310，单文件对端检查）。
- **契约生成**：`generate_api_contract`（:366，按路径首段分组）、`generate_frontend_prompt_contract`（:474，注入前端生成 prompt）。
- **归一化**：`_normalize_path`（:427，去查询参数/去尾斜杠/`{id}`→`:id`/补 `/`）。
- **便捷**：`check_api_consistency`（:457 返回 (通过, issues)）。

## 2. 依赖与被依赖

- **生产使用方**（三处，均活跃）：
  - `traditional_generate.py:155` `generate_frontend_prompt_contract(backend_files)`——生成前端文件的 prompt 注入 API 契约表
  - `orchestrator_files.py:468` + `orchestrator_utils.py:224` `_check_and_report_api_issues`——FilesMixin 每次写前端/API 文件时触发单文件一致性检查（`_should_check_api_consistency` :209：.vue/.js/.jsx/.ts/.tsx 全触发，.py 仅路径含 api/route）
  - `mixin.py:91` 初始化 `self.api_contract_checker = APIContractChecker()`（GenerationMixin，主链继承）；`orchestrator.py:123` 声明 `Optional[...]=None` 被 mixin 覆盖
- **测试覆盖**：`tests/unit/test_api_contract_checker.py` 仅 **1 个** test_check_consistency——单文件检查、跨行 fetch、prefix、模板字符串、契约生成、prompt 生成、归一化全零覆盖。

## 3. 已探明 Bug

### AC1 [P2] 前端模板字符串 `${id}` 归一化为 `$:id`，与后端 `:id` 不匹配 → missing_backend 误报

- **Bug 代码**：

```python
# api_contract_checker.py:435-436 - {id} -> :id，但前端 ${id} 被替换成 $:id
path = re.sub(r'\{(\w+)\}', r':\1', path)
```

- **根因**：`_normalize_path` 把后端 `{id}` 和前端 `${id}` 都无差别替换，前端模板字符串变 `/api/users/$:userId`，与后端 `/api/users/:user_id` 不匹配。
- **实测**：前端 `` fetch(`/api/users/${userId}`) `` → 提取 `/api/users/$:userId` → 后端 `@router.get('/api/users/{user_id}')` → **missing_backend 误报**。
- **影响**：前端按路径参数传 ID 的高频写法全量误报；且 `' + userId` 拼接形式被正则截断为 `/api/users`（静态路径），与列表端点匹配——**误报与漏报并存**。
- **验证方式**：见实测。

### AC2 [P2] FastAPI `APIRouter(prefix=...)` 不解析，`API_PREFIXES` 死常量 → 标准 prefix 写法全盘误判

- **Bug 代码**：

```python
# api_contract_checker.py:100-101 - 定义却从不使用
API_PREFIXES = ['/api', '/api/v1', '/api/v2']

# :70-73 - 只提取装饰器路径，不读 router 的 prefix 参数
r'@router\.(get|post|put|delete|patch)\(\s*["\']([^"\']+)["\']',
```

- **根因**：`API_PREFIXES` 定义后从未在 `_normalize_path`/提取逻辑中被引用（死常量，本意可能是前缀裁剪）；`APIRouter(prefix='/api/v1')` + `@router.get('/users')` 提取为 `/users`，不拼接 prefix。
- **实测**：后端 `router = APIRouter(prefix='/api/v1')` + `@router.get('/users')`，前端 `fetch('/api/v1/users')` → **missing_backend + missing_frontend 双误报**。
- **影响**：FastAPI 标准 prefix 分组写法（最常见组织方式）契约校验全盘失效。
- **验证方式**：见实测。

### AC3 [P2] 前端具体参数值/拼接路径不归一化为 `:param`，详情类请求漏/误匹配

- **Bug 代码**：

```python
# api_contract_checker.py:87-91 - 提取后路径保持原样，仅 {id}->:id 单向
r'fetch\(\s*["\']([^"\']+)["\']',
```

- **根因**：`_normalize_path` 只把后端式 `{id}` 归一化，前端拼接 `'/api/users/' + userId`、具体值 `/api/users/123` 保持原样 → 与后端 `/api/users/:id` 不匹配（漏报：该调用后端明明存在）。且 `' + userId` 的引号截断使提取路径止于 `/api/users/`。
- **影响**：详情/单资源操作的前端调用无法与参数化后端端点对齐，是契约校验误报的第二大来源。
- **验证方式**：`fetch('/api/users/' + userId)` 提取为 `/api/users`（截断），与后端 `/api/users/{id}` 对不上。

### AC4 [P2] 逐行扫描 + method 推断只认同行：跨行 fetch options 的 method 漏判为 GET

- **Bug 代码**：

```python
# api_contract_checker.py:183-204 - 按行扫描，method 推断依赖同行的 'method:' 文本
for line_num, line in enumerate(lines, 1):
    match = re.search(pattern, line)
    if match:
        ...
        if 'method:' in line:
            method_match = re.search(r'method:\s*["\'](\w+)["\']', line)
```

- **根因**：`extract_frontend_endpoints` 逐行处理，fetch 的 `method` 在第二参对象里通常换行（格式化代码常态），跨行时当前行无 `method:` → 推断 GET。
- **实测**：`` fetch('/api/orders', {\n method: 'POST',\n...}) `` → 提取 `(GET, '/api/orders')` → 与后端 POST 不匹配 → **误报**。
- **影响**：写/删类请求（POST/PUT/DELETE）大量被误判为 GET，契约校验失真。
- **验证方式**：见实测。

### AC5 [P3] AXIOS_PATTERNS 第三模式与分派逻辑为死代码：非 axios 的 `.get/.post` 调用全漏检

- **Bug 代码**：

```python
# api_contract_checker.py:97 - 独立 get(...) 调用模式（1 个捕获组）
r'(?:get|post|put|delete|patch)\(\s*["\']([^"\']+)["\']',

# :210-221 - len(groups)==2 才处理，单组恒走 else continue
if len(groups) == 2:
    ...
elif len(groups) == 2 and groups[0] in (...):  # 恒 False（len 已判 2）
    ...
else:
    continue
```

- **根因**：:97 模式只有 1 个捕获组（path），:210 要求 len==2 → 恒走 `else: continue`；:217 的 `elif len(groups)==2 and ...` 是死分支。`$.get(...)`、`http.get(...)`、任意对象 `.get()` 调用全部漏检。
- **实测**：`obj.get('/api/nonexistent')` 不被提取（死模式未误报，但独立调用全漏检）。
- **影响**：非 axios 封装的 HTTP 客户端（$.ajax 简写、自定义 request 层）的调用从契约校验中消失。
- **验证方式**：见实测。

### AC6 [P3] 契约检查每次写文件全量扫描 output_dir 全部 .py（消费方设计）

- **Bug 代码**：

```python
# orchestrator_utils.py:227-232 - 每次写前端/API 文件都 rglob 全 .py
for py_file in self.output_dir.rglob('*.py'):
    if '__pycache__' not in str(py_file):
        backend_files[str(py_file.relative_to(self.output_dir))] = py_file.read_text()
```

- **根因**：`_should_check_api_consistency` 对任何 .vue/.js/.ts 文件返回 True → 每次写前端文件都全量扫描 output_dir（含用户自带/无关 .py）并构建单文件检查。非 checker 本体，属消费方接线——性能成本 + 无关 .py 混入后端端点集合的误判来源。
- **影响**：大项目写文件密集时的重复 IO；无关 .py 的路由被算进 backend 契约。
- **验证方式**：实码可证。

### AC7 [P3] `path_mismatch` issue_type 声明但从不产生；method_mismatch 只单向

- **Bug 代码**：

```python
# api_contract_checker.py:50 - 声明了 path_mismatch 却无任何代码产生该类型
issue_type: str  # 'missing_backend', 'missing_frontend', 'method_mismatch', 'param_mismatch', 'path_mismatch'

# :295-299 - 只报前端多余方法（extra_fe），后端方法多于前端不报
if fe_methods != be_methods:
    extra_fe = fe_methods - be_methods
```

- **根因**：注释声明 5 种 issue_type，实际只产生 3 种（path_mismatch/param_mismatch 从未产出）；method_mismatch 单方向（后端 GET+POST 前端只 GET 不报）。`params`/`request_body`/`response_type` 字段（APIEndpoint :40-42）从未被填充使用。
- **影响**：契约校验的类型覆盖与文档声明不符，字段死代码。
- **验证方式**：实码可证（rg 无 path_mismatch 赋值）。

### AC8 [P3] Django `path(...)` 正则假阳性 + include() 子路由拼接缺失

- **Bug 代码**：

```python
# api_contract_checker.py:83
r'(?:path|url)\(\s*["\']([^"\']+)["\']',
```

- **根因**：Django 模式下匹配任何字面 `path("...")`——view 函数内部 `path("report.pdf")` 等也被当路由；`include()` 子路由（`path('api/', include('app.urls'))`）的 prefix 不拼接，子路由端点从契约消失。
- **影响**：Django 项目契约提取假阳性 + 子路由漏检。
- **验证方式**：含 `path("static.txt")` 的 view 被提取（实码可证）。

### AC9 [P3] 测试覆盖仅 1 个测试

- **现象**：`test_api_contract_checker.py` 只有 1 个 `test_check_consistency`（fixture 传入 checker）。AC1-AC4 四类高频误报/漏报场景全部无测试防线。
- **影响**：契约校验以误报/漏报主导而流程静默通过（warning/error 不进生成结果阻断），修复无回归保障。

## 4. 潜在问题与未知点

- `_extract_backend_endpoints` 框架检测对混合框架项目（FastAPI + Flask 并存）逐文件检测，但 Django 的 `path()` 与 JS 侧 `path()` 无区分；framework 传参在 `check_consistency` 调用时不传（每文件自动检测）。
- `generate_api_contract` 按路径首段分组（`/api/v1/users` → 模块 `api`），粒度粗糙；`generate_frontend_prompt_contract` 输出未被完整性验证（无法确认 prompt 注入是否真的改变了前端生成行为）。
- 与 integrity_validator 的 `_validate_api_contracts`（integrity_validator.py:309，简版重复实现）关系：**三处 API 契约校验并存**——integrity_validator._validate_api_contracts / api_contract_checker / code_validator CV4 前端 API 一致性检查（空操作）。api_contract_checker 是功能最全者（有 method 维度与路径归一化），但被 AC1-AC4 误报主导。
- `XMLHttpRequest`（docstring :63 声明支持）无对应 pattern。

## 5. 修改建议（改什么 → 达成什么目的）

| # | 优先级 | 修改动作 | 达成目的 | 涉及位置 | 对应 Backlog |
|---|--------|---------|---------|---------|-------------|
| 1 | P2 | `_normalize_path` 先转前端模板串：`${...}` → `{...}` → `:param` 单一路径（或统一为 `:param` 并在对比层归一化具体值 `/api/users/123` → `/api/users/:id`） | 模板字符串/拼接/具体值三类前端写法与后端参数化端点对齐，消除 AC1/AC3 误报 | api_contract_checker.py:427-442 | 待记 |
| 2 | P2 | 解析 `APIRouter(prefix=...)` 与 Flask blueprint prefix、Django include 前缀，提取时拼接；接线 `API_PREFIXES`（用于前后端前缀差异归一） | FastAPI/Flask/Django 标准分组写法契约校验生效（AC2/AC8） | api_contract_checker.py:108-167 | 待记 |
| 3 | P2 | fetch/axios 解析改为跨行（AST 或按语句块），method 从第二个实参对象提取 | 跨行 fetch 的 POST/PUT/DELETE 不被误判为 GET（AC4） | api_contract_checker.py:169-230 | 待记 |
| 4 | P2 | 移除 :97 死模式 + :217 死分支，独立 `.get/.post` 调用显式纳入（或删除并记录漏检范围） | 非 axios 客户端调用纳入契约校验，消除死代码 | api_contract_checker.py:94-98/207-221 | 待记 |
| 5 | P3 | `_should_check_api_consistency` 改为缓存后端端点集合（仅生成开始时扫描一次），而非每次写文件 rglob | 消除写文件密集时的重复全量 IO 与无关 .py 混入 | orchestrator_utils.py:209-232 | 待记 |
| 6 | P3 | issue_type 实现与声明对齐（实现 path_mismatch/param_mismatch 或删声明）；填充/使用 APIEndpoint.params/request_body/response_type | 契约校验类型覆盖与文档一致，参数维度纳入 | api_contract_checker.py:33-50 | 待记 |
| 7 | P3 | 补测试：模板字符串/prefix/跨行 fetch/拼接路径/独立 get/方法不匹配 6 类场景 | AC1-AC5 有回归防线 | tests/unit/test_api_contract_checker.py | 待记 |
| 8 | P3 | 三处 API 契约校验收敛为一处（api_contract_checker 为唯一实现；integrity_validator._validate_api_contracts 与 CV4 空操作删除或委派） | 消除「三套契约校验并存」，与 CV8 验证器归位主线一致 | integrity_validator.py:309 / code_validator | 待记 |

## 6. 演化方向关联

- APIContractChecker 是「前端与后端契约一致性」方向（EVOLUTION §5.1 验证闭环的契约维度）的**专门实现**，与 integrity_validator 的 `_validate_api_contracts`（简版）、code_validator CV4（空操作）构成**三套并存**——归位为唯一实现是契约校验主线第一步（AC8 建议）。
- 与 IV3/IV4（integrity_validator 前缀误判/method 忽略）对照：api_contract_checker 有 method 维度与 `{id}`→`:id` 归一化，但 AC1/AC3/AC4 的误报说明「归一化不完整 + 提取行级」比缺失维度更隐蔽——**契约校验三件套（路径归一化 / method 提取 / prefix 拼接）缺一不可**。
- `generate_frontend_prompt_contract`（traditional_generate.py:155 活跃注入）是「契约先验注入」方向的基础设施——修复 AC2 后注入的契约表才准确，属生成质量前置。
- AC2 死常量 `API_PREFIXES` 与 IV7 死 issue_type（integrity_validator）、CV4 空操作同属「声明-实现不符」代码健康主线。
