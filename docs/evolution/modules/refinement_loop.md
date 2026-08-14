# RefinementLoop 演化深扫文档

> 版本：v0.1 | 扫描日期：2026-08-09 | 状态：已完成
> 归属：Agent 大系统 / 支撑模块（生成-验证-修复循环执行器）
> 路径：app/agent/refinement_loop.py（584 行）
> 索引：[TASKS.md](../TASKS.md)

## 1. 模块作用与功能

小模型代码质量的迭代修复循环：「生成 → 验证 → 注入错误 → 重新生成 → 再验证」，按复杂度分级修复轮次（simple 2 ~ enterprise 5），验证覆盖 Python/JS/JSON/HTML/CSS 五类，修复 prompt 注入错误摘要（含 ±10 行代码上下文）、相关规范、已生成文件摘要。

- **核心类**：`RefinementLoop`（:61）、`ValidationIssue`（:40）、`RefinementResult`（:50）。
- **主流程**（`refine` :94-212）：循环内 `_validate_code`（:216）→ 无 issue 即 success → `_build_error_summary`（:482 错误行 ±10 行上下文）→ `_build_fix_prompt`（:507 注入规范/相关文件）→ `call_llm`（:175 直连顶层体系，temperature=0.5）→ `_clean_code_block` → 内容不变/为空则 break。
- **验证器**：`_validate_python_syntax`（:246 ast.parse）、`_validate_python_imports`（:261 **importlib.import_module 检查**）、`_validate_spec_consistency`（:315 空操作）、`_validate_js_basic`（:348 **node -c**）、`_validate_json_syntax`（:404）、`_validate_html_basic`/`_validate_css_basic`（括号计数）。

## 2. 依赖与被依赖

- **导入依赖**：`app.utils.call_llm`（直连顶层 LLM 体系，不走 LLMClient——TG1/EV1/CEC3 同源）、`shared_context.SharedContext`、`orchestrator.LayeredModelRouter`（模型配置）、惰性 `spec_first_generator.SpecFirstGenerator`。
- **生产使用方**（5 处活跃 refine 调用）：
  - `spec_first_generate.py:196/:880` 实例化；`:503/:513/:1064/:1074` 调 `refine`（spec-first 主链修复核心执行器）
  - `cross_validator.py:263` 调 `refine`（双模型对抗后修复：`validate_and_select` 失败路径）
- **测试覆盖**：`tests/unit/test_refinement_loop.py` 仅 **1 个** test_refine_success（mock 验证通过路径）；`test_small_model_optimization.py` 测的是 SharedContext 非本模块。cross_validator 修复路径、LLM 失败/空返回、空操作验证器全零覆盖。

## 3. 已探明 Bug

### RL1 [P2] `_validate_spec_consistency` 的 openapi 路径检查是空操作

- **Bug 代码**：

```python
# refinement_loop.py:320-331
if file_type in ("api", "view", "controller", "router"):
    openapi = self.context.get_spec("openapi")
    if openapi:
        paths = openapi.get("paths", {})
        for path in paths:
            path_parts = path.strip('/').split('/')
            for part in path_parts:
                if part and not part.startswith('{') and part not in content:
                    # 不一定要报错，只是记录为 warning
                    pass
```

- **根因**：检查条件满足（path 的段不在 content）时只 `pass`，从不 append issue——「检查 API 路由引用」逻辑完整编写但零输出。`file_type` 是 "api" 时该分支从不产生任何 ValidationIssue。
- **实测**：openapi spec 含 `/api/users`、`/api/orders`，content 不含 → **零 issue**（空操作）。
- **影响**：与 code_validator CV4（前端 API 一致性空操作）同类——refinement 的 spec 一致性验证维度实际只有 model 类型（BaseModel 字符串检查）在工作，api 类型验证完全失效。修复循环对「代码未按 openapi 实现」无任何感知。
- **验证方式**：见实测。

### RL2 [P2] `_validate_python_imports` 用 `importlib.import_module` 在当前 agent 环境导入——环境错位 + 执行模块副作用

- **Bug 代码**：

```python
# refinement_loop.py:299-303
try:
    import importlib
    importlib.import_module(imp)
except ImportError:
    missing_imports.append(imp)
```

- **根因**：`importlib.import_module(imp)` 在 **agent 运行环境**（不是用户项目环境）导入。两个语义错位：① 检查的是「agent 环境装没装」，不是「用户项目 requirements 有没有」——agent 装了（如 requests/fastapi）用户项目没声明 → **漏报**；用户项目装了 agent 没有 → **误报**；② **import_module 执行被导入模块的顶层代码**（副作用）——与 code_validator CV2（exec_module 执行任意代码）同源，验证阶段真实执行任意第三方模块。
- **实测**：`import requests`（agent 环境已装）不报，`import totally_nonexistent_pkg_xyz_123` 报 warning——检查的是 agent 环境依赖而非用户项目。
- **影响**：依赖缺失检查结果与用户项目实际依赖脱节；验证执行任意导入代码是安全/副作用风险。修复循环每轮对每个 Python 文件触发。
- **验证方式**：见实测。

### RL3 [P2] 修复循环 success 只依赖轻量验证，不验证 spec 符合性与功能正确性

- **Bug 代码**：

```python
# refinement_loop.py:134-143 - 无 issues 即 success
if not issues:
    return RefinementResult(success=True, ...)
```

- **根因**：验证覆盖语法（ast/括号计数）/import 存在性/Model 字符串检查，都是「文件自身结构」级——**不含**：与 openapi/types spec 的字段对齐（RL1 空操作使该维度失效）、跨文件引用完整性、运行正确性。`success=True` 只证明「语法合法且 agent 环境能 import」。
- **影响**：与 TG2/TR1/IM2 同属「存在≠正确」验证语义主线——refine 返回 success 后 spec_first 直接采用内容（spec_first_generate.py:503-513/:1064-1074），功能性错误不被捕获，最终落盘的内容未经语义验证。
- **验证方式**：构造语法合法但逻辑错误的代码跑 refine → success=True（实码可证）。

### RL4 [P3] break 后兜底返回 `remaining_issues=[]`，语义不一致

- **Bug 代码**：

```python
# refinement_loop.py:186-188 / 193-195 / 201-202 - LLM 空返回/未改变/异常 → break
# :204-212 兜底（break 后可达）
return RefinementResult(
    success=False,
    ...
    remaining_issues=[]
)
```

- **根因**：最后一次尝试会提前返回（:151-160 带当前 issues），但**中间轮 break**（LLM 返回空/内容未改变/异常）会走到兜底返回，此时仍有未修问题却 `remaining_issues=[]`。调用方若依赖 remaining_issues 判断剩余问题会失真。
- **影响**：spec_first 消费 `result.remaining_issues`（如判断是否记录修复失败）时拿到空列表，掩盖真实未修问题。兜底路径实际可达（LLM 非空返回是常态）。
- **验证方式**：mock call_llm 返回空 → break → 兜底 remaining_issues=[]（实码可证）。

### RL5 [P3] `_validate_js_basic` node -c 临时文件泄漏 + 每轮 5s 阻塞

- **Bug 代码**：

```python
# refinement_loop.py:354-385
with tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False) as f:
    f.write(content); tmp_path = f.name
result = subprocess.run(['node', '-c', tmp_path], ..., timeout=5)
...
Path(tmp_path).unlink(missing_ok=True)
except (subprocess.TimeoutExpired, FileNotFoundError):
```

- **根因**：正常路径清理 tmp 文件，但 except 只捕 `TimeoutExpired`/`FileNotFoundError`——node 存在但 subprocess 抛其他异常（OSError 权限等）时 tmp 文件泄漏；且每个 JS 文件每轮修复 spawn node 进程 + 5s 超时上限（串行阻塞）。
- **影响**：JS 文件多的项目修复循环每轮 spawn node；异常路径临时文件残留。
- **验证方式**：构造 node 存在但 run 抛非捕异常的场景（实码可证）。

### RL6 [P3] `_build_fix_prompt` 每次修复实例化 SpecFirstGenerator + 异常静默吞 spec context

- **Bug 代码**：

```python
# refinement_loop.py:520-525
from app.agent.spec_first_generator import SpecFirstGenerator
gen = SpecFirstGenerator(self.context)
spec_context = gen.get_spec_context_for_file(file_path, file_type)
except Exception as e:
    logger.debug(f"精炼循环操作失败：{e}")
```

- **根因**：每次修复都 new SpecFirstGenerator（生成器实例化成本）；异常仅 debug 日志、spec_context 静默为空——修复 prompt 在生成器异常时退化为「无规范」提示，模型可能改歪。
- **影响**：修复质量依赖生成器可用性但失败无感知；重复实例化浪费。
- **验证方式**：实码可证。

### RL7 [P3] model 类型检查用字符串包含 + 温度硬编码 + import 解析不完整

- **Bug 代码**：

```python
# refinement_loop.py:338 - 字符串包含检查，非 AST
if "BaseModel" not in content and "pydantic" not in content.lower():
# :181 - 修复温度硬编码 0.5（注释称「更低」但无对照基准）
temperature=0.5,
# :277-290 - 逐行解析 import，不处理多行括号 import / as 别名
if line.startswith('import '): parts = line[7:].split()
```

- **根因**：model 检查注释里含 "BaseModel" 也通过（误判）；温度无基准硬编码；`from x import (a, b)` 跨行、`import a.b as c` 别名解析不完整。
- **影响**：验证精度受限；修复温度策略不可配。
- **验证方式**：`# 提到 BaseModel 的注释` → 检查通过（实码可证）。

### RL8 [P3] 测试覆盖仅 1 个（refine 成功路径）

- **现象**：test_refinement_loop.py 只有 test_refine_success（mock 验证通过即返回）。LLM 失败/空返回/内容未改变（RL4 兜底路径）、RL1 空操作、RL2 环境错位、node 回退、multi-attempt 全部无测试；cross_validator.py:263 的修复路径零覆盖。
- **影响**：修复循环是 spec-first 主链 5 处调用的核心，但其失败路径与验证语义无回归防线。

## 4. 潜在问题与未知点

- `refine` 的 `_pending_tasks`（:86/:579-582）跟踪异步回调 task，但无显式 await/回收策略（依赖 done_callback discard）——批量 refine 并发时回调任务堆积未验证。
- `_REFINEMENT_ATTEMPTS_BY_COMPLEXITY` 默认 3，但 `MAX_ATTEMPTS` 实例级覆盖——同一实例跨文件复用不重置（实例是 per-file 创建，:196/:880 每轮 new，无复用问题）。
- `_validate_python_imports` 的 standard_libs 集合与 integrity_validator.PYTHON_BUILTINS 重复定义（两处维护同一清单，漂移风险）——与 CV6 依赖清单散落同主线。
- `call_llm` 直连不走 LLMClient（TG1/EV1/CEC3 同源）：无信号量/成本/token 审批，refine 每轮调用不可见于成本体系。

## 5. 修改建议（改什么 → 达成什么目的）

| # | 优先级 | 修改动作 | 达成目的 | 涉及位置 | 对应 Backlog |
|---|--------|---------|---------|---------|-------------|
| 1 | P2 | `_validate_spec_consistency` openapi 分支补全：路径段/参数未在 content 中引用时 append warning；与 openapi 路径参数类型对齐 | 激活 api 类型 spec 一致性验证（RL1），修复循环感知「代码未按 openapi 实现」 | refinement_loop.py:320-331 | 待记 |
| 2 | P2 | `_validate_python_imports` 改用静态分析（AST Import/ImportFrom 提取顶层名 + requirements 文件比对），删除 importlib.import_module | 消除 agent 环境错位 + 执行副作用；依赖检查以用户项目 requirements 为准 | refinement_loop.py:261-313 | 待记 |
| 3 | P2 | refine 的验证通过条件纳入跨文件/spec 符合性（RL1 修复后）；`success` 重命名为「验证通过」语义并让调用方区分「语法通过」与「功能未验证」 | 与 TG2/TR1 验证语义主线统一，spec_first 不将轻量成功当功能成功 | refinement_loop.py:134-143 | 待记 |
| 4 | P3 | 兜底返回携带当前 `issues`（非空 remaining_issues），与最后一次尝试语义一致 | 调用方拿到真实剩余问题（RL4） | refinement_loop.py:204-212 | 待记 |
| 5 | P3 | node -c 用 finally 清理 tmp；或缓存 JS 语法检查（仅内容变更时重跑） | 消除泄漏 + 每轮 spawn 开销 | refinement_loop.py:354-385 | 待记 |
| 6 | P3 | SpecFirstGenerator 实例提升到 RefinementLoop 构造时注入（或复用 spec 提取为独立函数）；异常时输出可见 warning 而非静默 debug | 消除重复实例化，spec context 失败可感知 | refinement_loop.py:520-525 | 待记 |
| 7 | P3 | model 检查改 AST（排除注释）；temperature 从配置读取；import 解析支持多行括号/别名 | 验证精度与可配置性 | refinement_loop.py:181/:277-290/:338 | 待记 |
| 8 | P3 | 补测试：LLM 空返回/未改变/异常兜底、RL1 修复后 spec 一致性、RL2 静态 import 解析、multi-attempt 计数 | 修复循环失败路径有回归防线 | tests/unit/test_refinement_loop.py | 待记 |

## 6. 演化方向关联

- RefinementLoop 是**修复循环执行器**（验证栈的上游驱动）：5 处活跃 refine 调用（spec_first 主链 4 + cross_validator 1）使它是生成质量的最直接修复机制。RL1 空操作 + RL3 轻量成功 → 修复循环「验证-修复」的验证端只有语法级，与 error_recovery 顶层 ErrorRecoveryLoop（797 行）构成两套修复循环（RL 面向单文件生成质量、ERL 面向最终验证）——归位为分层修复策略是「两套错误恢复收敛」主线的延伸。
- RL2 importlib 副作用与 CV2（exec_module 执行任意代码）同源——**验证阶段真实执行代码**是验证闭环的安全/性能主线，二者应一并改静态分析。
- RL1 空操作与 CV4（前端 API 一致性空操作）、IV7（API 提取正则死 issue_type）同类——「声明-实现不符」代码健康主线。
- RL3「存在≠正确」与 TG2/TR1/IM2 直接同主线——修复循环的 success 语义是验证语义统一的一部分。
- RL5 node -c 与 test_runner 的 `_execute_test`（进程执行）同属「subprocess 执行」安全模式——统一进程执行抽象（超时/清理/资源限制）可复用。
- `call_llm` 直连（无信号量/成本）归入 LCL1 收敛范围（与 ERL4/EV1/TG1/CEC3 同源）。
