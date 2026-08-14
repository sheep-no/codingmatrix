# OrchestratorTesting 演化深扫文档

> 版本：v0.1 | 扫描日期：2026-08-09 | 状态：已完成
> 归属：Agent 大系统 / 支撑模块（测试执行 Mixin）
> 路径：app/agent/orchestrator_testing.py（306 行）
> 索引：[TASKS.md](../TASKS.md)

## 1. 模块作用与功能

测试执行编排 Mixin：`TestingMixin` 提供动态测试运行（Docker 优先 + 本地 TestRunner fallback）、智能测试选择、失败聚类、测试命令探测、测试事件上报——是 OrchestratorAgent 生成链路的测试验证入口，与 TestRunner/FrameworkDetector/OutputParser 构成验证执行链。

- **核心类**：`TestingMixin`（:17）。方法：`_run_dynamic_tests`（:19）、`_select_tests`（:104）、`_cluster_test_failures`（:129）、`_detect_test_command`（:160）、`_collect_all_tests`（:204）、`_run_tests_in_docker`（:211）。
- **双路径结构**：Docker 分支（:35 `_run_tests_in_docker` 优先，fallback 本地）与本地分支（:40 `runner.run_tests()`）。

## 2. 依赖与被依赖

- **生产使用方**（1 处）：orchestrator.py:28/:39（TestingMixin 注入 OrchestratorAgent）。
- **跨模块引用**：test_runner.IsolatedTestRunner（:6）、impact_analyzer.ImpactAnalyzer（:7）、test_selector.TestSelector（:9）、failure_clusterer.FailureClusterer（:10）、project_profiler（:8）、orchestrator_progress.PROGRESS_LABELS（:12）、utils.performance_metrics（:11）、utils.docker_runner（:213 延迟导入）、service_container_manager（:217）、framework_detector（:227 延迟导入）、output_parser（:269 延迟导入）。
- **测试覆盖**：tests/unit 零测试；仅 tests/archive/integration_old/test_v4_8_e2e.py（归档集成测试）引用。TestingMixin 依赖宿主属性（output_dir/_report_progress/_update_phase/warnings）不可独立单测。

## 3. 已探明 Bug

### OT16 [P2] `_select_tests` 构造缺参恒失败：智能测试选择全链路失效

- **Bug 代码**：

```python
# :114-127 - ImpactAnalyzer()/TestSelector() 无参构造，但两者 __init__ 必填 project_root
analyzer = ImpactAnalyzer()          # :116 → TypeError
changes = analyzer.analyze(modified_files)
selector = TestSelector()            # :120 → TypeError
test_files = selector.select_tests(changes, project_profile)
# :125-127 - except 捕获回退 []
return []
```

- **根因**：`ImpactAnalyzer.__init__(self, project_root: str)`（impact_analyzer.py:33）与 `TestSelector.__init__(self, project_root: str)`（test_selector.py:21）均为必填参数，:116/:120 无参调用必然抛 TypeError → :125-127 捕获回退 `[]`。**每次运行日志都打「测试选择失败」但无人察觉**。
- **影响**：**智能测试选择（变更→影响分析→测试选取）全链路空转**，恒回退全量测试。结合 :33 `_detect_test_command(self.output_dir, test_files)` 的 test_files 恒空——docker 分支命令也不带具体文件，本地分支 `runner.run_tests()` 无参（:40）跑全量。测试选择能力实际从未生效。
- **验证方式**：代码级确凿（构造签名必填 + 调用无参）。

### OT21 [P2] Docker 分支跳过失败聚类与事件报告：两路径输出结构不一致

- **Bug 代码**：

```python
# :35-37 - docker 结果非 None 直接 return，无聚类/事件
docker_result = await self._run_tests_in_docker(test_cmd)
if docker_result is not None:
    return docker_result
# 本地分支 :52-84 - 才有聚类（FailureClusterer）+ _report_test_results 事件
```

- **根因**：Docker 分支成功返回 summary 直接 return（:36-37），本地分支的失败聚类（:52-70）、`_report_test_results` 测试结果事件（:73-84）全部跳过；docker 分支只 `_report_progress`（:284）。两路径输出结构不一致（docker 无 failure_clusters、无测试结果事件推送）。
- **影响**：**同一项目两种验证结果**（TR 主线具体表现）——docker 可用时前端拿不到聚类/事件，docker 不可用时才有；验证行为随环境漂移。

### OT22 [P2] Docker 分支走 FD-OP 失效链：解析全 0 时 success 仍为 True（语义矛盾）

- **Bug 代码**：

```python
# :269-279 - docker 分支用 FrameworkDetector 输出格式解析 docker 日志
from app.agent.output_parser import OutputParser
output_format = "pytest_xml"
if detected_config:
    output_format = detected_config.output_format    # :273 FD1 vitest→jest_json
parsed = OutputParser.parse(raw_output, output_format)  # :276
summary["passed"] = parsed.passed   # :277 - 失效链下恒 0
summary["failed"] = parsed.failed
summary["total"] = parsed.passed + parsed.failed     # :279 - skipped 不计入
```

- **根因**：docker 分支将 docker 日志交给 FrameworkDetector 检测的 output_format 解析（:230/:273/:276）——**FD1（vitest 打 jest 标签）+ OP1（pytest_xml 假解析）+ OP3（vitest 全 0）失效链直接命中**。解析全 0 时 summary total/passed/failed=0，但 `summary["success"] = result.success`（:259）来自 docker_runner 的 exit_code——**可能 True**。
- **影响**：测试结果面板显示全 0 但整体判定成功；skipped 不计入 total（:279 漏 OP2 同款 skipped 口径）。docker 分支与本地分支走不同解析（本地 TestRunner 内部解析 vs docker OutputParser.parse），验证结果口径分裂。
- **验证方式**：代码级结论（依赖 FD-OP 已实测失效链）。

### OT18 [P3] `_detect_test_command` 顺序碰撞：npm test script 遮蔽 playwright

- **Bug 代码**：

```python
# :161-185 - 先判 package.json test script，playwright.config 判断在其后
if "test" in scripts:
    return f"cd /app && npm run test -- {files_str}"   # :170 先返回
playwright_config = ...   # :175-185 永远执行不到（有 package.json 时）
```

- **根因**：package.json 有 test script 即判 npm（:166），playwright.config.js/ts 判断在 :175-185 之后——两者共存时 playwright 分支被遮蔽（FD2「存在 test script ≠ 框架」同类启发式）。命令产物硬编码 `cd /app`（:170-202 全部），假设 docker 挂载点（TR2 test_runner_enhanced.py:184 同款 /app）。
- **影响**：JS 项目测试命令选择失真；/app 硬编码使命令脱离 docker 环境不可用。

### OT24 [P3] `_cluster_test_failures` 正则 test_name 未 escape + 每调用实例化

- **Bug 代码**：

```python
# :142-150 - test_name 直接插入正则，pytest 参数化名含 [ ] ( ) 元字符
pattern = rf"FAILED {test_name}.*?(?=FAILED|PASSED|ERROR|$)"
match = re.search(pattern, logs, re.DOTALL)   # 参数化名 → 正则异常
error_message = traceback.split('\n')[-2] if traceback else ""   # :150
```

- **根因**：pytest 参数化测试名（如 `test_x[param1]`）含 `[` `]` 等正则元字符未 `re.escape` → `re.search` 抛异常 → :156-158 except 捕获回退 `[]`（聚类失效）或错匹配；`traceback.split('\n')[-2]` 对无回溯日志取错行。且 FailureClusterer 每次调用实例化（:137）。
- **影响**：参数化失败的聚类静默失效，失败根因归并不可靠。

### OT25 [P3] `_report_test_results` 的 skipped 字段填 errors 数（语义错位）

- **Bug 代码**：

```python
# :73-84 - skipped 字段传的是 errors 计数
self._report_test_results({
    "summary": { "passed": result.passed, "failed": result.failed,
                 "skipped": result.errors, ... })   # :77 skipped=errors
```

- **根因**：skipped 事件字段错误地填入 errors（TestResult.errors），skipped 与 errors 是两个独立计数，语义错位。
- **影响**：测试结果事件里 skipped 数据失真。

### OT2 [P3] docker summary 的 errors 字段双语义漂移

- **Bug 代码**：

```python
# :263 初始 = ValidationResult.errors；:280-281 解析后被 parsed.errors 覆盖
summary = {"errors": len(result.errors), ...}
if parsed.errors:
    summary["errors"] = len(parsed.errors)   # 同字段两种语义
```

- **根因**：同字段先填 docker 运行错误数（ValidationResult.errors），解析后又被输出解析错误数（parsed.errors）覆盖——两种错误类型混用。
- **影响**：errors 字段含义随代码路径变化，消费方无法区分运行错误与解析错误。

### OT20 [P3] 零单元测试覆盖（mixin 依赖宿主属性）

- **根因**：TestingMixin 全部方法经 `self.output_dir`/`self._report_progress`/`self.warnings` 等宿主属性，不可独立实例化；tests/unit 零覆盖，仅归档集成测试引用。
- **影响**：OT16（构造缺参恒失败）在测试网下完全通行，智能测试选择失效从未被测试暴露。

### OT26 [P3] `_collect_all_tests` 返回绝对路径与 `_detect_test_command` 相对路径基准不一致

- **Bug 代码**：

```python
# :207-209 - str(f) 为绝对路径（含 output_dir 前缀）
test_files.extend(str(f) for f in self.output_dir.glob(pattern))
```

- **根因**：`:208` glob 结果 str(f) 是绝对路径；`_select_tests` 返回 TestSelector.select_tests 相对路径。两处路径基准不一致，`test_files` 直接 join 进 shell 命令时混用。当前仅日志计数（:123）使用，尚未造成命令错误。
- **影响**：潜在命令拼接错误风险；路径契约不统一。

## 4. 修复建议

- **OT16**：构造传 `self.output_dir`（`ImpactAnalyzer(str(self.output_dir))` / `TestSelector(str(self.output_dir))`），或 TestingMixin 持有懒初始化实例。
- **OT21**：docker 分支复用本地分支的聚类 + `_report_test_results` 事件路径（提取公共方法，双路径输出结构统一）。
- **OT22**：docker 分支解析失败（total=0 且 success=True）时降级为「结果不可信」，与本地路径统一用 TestRunner 解析；skipped 计入 total。
- **OT18**：命令探测顺序改为 playwright → package.json test → pytest，消除遮蔽；`cd /app` 改为 docker 挂载点常量。
- **OT24**：`re.escape(test_name)`；FailureClusterer 实例化移出循环/惰性。
- **OT25/OT2**：事件字段与 summary 字段语义对齐（skipped/errors 独立计数，明确字段语义）。
- **OT26**：统一相对/绝对路径基准。
- **OT20**：为纯方法（_detect_test_command/_collect_all_tests）提供宿主属性默认值的可测入口。

## 5. 待实测项

- OT16 为代码级确凿（构造签名必填 + 无参调用），无待实测阻塞。
- OT21/OT22/OT18 为代码级结论（依赖已实测的 FD-OP 失效链与 TR 双路径结论）。
- OT24-OT26 为代码级结论。
