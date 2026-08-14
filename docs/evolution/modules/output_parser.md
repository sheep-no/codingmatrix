# OutputParser 演化深扫文档

> 版本：v0.1 | 扫描日期：2026-08-09 | 状态：已完成
> 归属：Agent 大系统 / 支撑模块（测试输出统一解析）
> 路径：app/agent/output_parser.py（216 行）
> 索引：[TASKS.md](../TASKS.md)

## 1. 模块作用与功能

测试输出统一解析：把 6 种框架的输出（pytest XML、Jest JSON、JUnit XML、Go JSON、Rust text、C++ text）解析为统一的 `ParsedTestResult`（passed/failed/errors/test_cases/duration），未知格式 fallback 到通用文本解析。供测试执行栈展示测试结果。

- **核心**：`OutputParser.parse`（:42 静态工厂，format→parser 映射）、`ParsedTestResult`/`TestCaseResult`（:19/:29 dataclass）。
- **解析器族**：`GenericTextParser`（:67 文本正则 fallback）、`PytestXMLParser`（:87 实际是文本解析）、`JestJSONParser`（:112 真 JSON）、`JUnitXMLParser`（:149 正则假解析 XML）、`GoTestParser`（:172 `--- PASS:`/`--- FAIL:` 行数）、`RustTestParser`（:191）、`CppTestParser`（:215 纯委托 Generic）。

## 2. 依赖与被依赖

- **生产使用方**（3 处）：test_runner.py、orchestrator_testing.py、docker_runner.py——经 `TestFrameworkConfig.output_format`（来自 FrameworkDetector）选解析器。
- **上游格式来源**：test_framework_config.py 6 preset 的 output_format（python_pytest=pytest_xml / javascript_jest=jest_json / java_maven=junit_xml / go_test=go_json / rust_cargo=rust_text / cpp_make=cpp_text）+ FrameworkDetector 的 vitest 手动构造（jest_json，见 FD1）。
- **测试覆盖**：tests/unit/test_v4_8_features.py `TestOutputParser` 5 个正向用例（pytest/go/rust/generic/empty）——**全是文本输入**；JUnitXMLParser/JestJSONParser 零测试；XML/JSON 结构、skipped、panic、vitest 无覆盖。

## 3. 已探明 Bug

### OP1 [P2] PytestXMLParser 名不副实：format=pytest_xml 但只解析文本正则，真 XML 全 0

- **Bug 代码**：

```python
# output_parser.py:87-109 - 名为 XML 解析器，实为文本正则
class PytestXMLParser:
    def parse(self, raw_output):
        passed_match = re.search(r"(\d+)\s+passed", raw_output)  # 文本而非 XML 元素
        ...
```

- **根因**：python_pytest preset 的 `output_format="pytest_xml"`（test_framework_config.py:36），但 PytestXMLParser 只提取 "N passed"/"N failed"/"N error" 文本。test_command=`pytest -xvs --tb=short` 输出文本恰好匹配（碰巧工作）；项目若产生真 JUnit XML（--junitxml / pytest-html / 集成报告）→ XML 内无 "N passed" 文本 → 全 0。
- **影响**：实测真 pytest XML → passed=0 failed=0，测试结果面板全空。名称/format 承诺解析 XML，实现只认文本——**格式标签与解析器语义错配**。
- **验证方式**：实测（见 §5）。

### OP2 [P2] JUnitXMLParser skipped 计入 passed：passed 虚高

- **Bug 代码**：

```python
# :159-164 - JUnit tests 属性含 skipped，未扣除
total = int(tests_match.group(1))
failures = int(failures_match.group(1))
errors_count = int(errors_match.group(1))
result.passed = total - failures - errors_count   # skipped 混入 passed
```

- **根因**：JUnit `testsuite.tests` 包含 passed+failed+skipped+errors，算法只减 failures/errors 不减 skipped。
- **影响**：实测 `<testsuite tests="10" failures="2" errors="1" skipped="3">` → passed=7（正确应 4）。含 skipped 的项目通过数虚高，且 JUnitXMLParser 是正则假解析（非 xml.etree），转义/多行/命名空间/属性顺序脆弱。
- **验证方式**：实测（见 §5）。

### OP3 [P2] vitest 输出经 jest_json 解析全 0（与 FD1 构成完整失效链）

- **Bug 代码**：

```python
# :120-124 - 依赖 jest 专有顶层字段
data = json.loads(raw_output)
num_passed = data.get("numPassedTests", 0)
num_failed = data.get("numFailedTests", 0)
```

- **根因**：JestJSONParser 读 jest 专有的 `numPassedTests`/`numFailedTests`/`testResults[].assertionResults` 结构；vitest 的 JSON（`numTotalTestSuites`/`success`/不同结构）不含这些键 → `.get(..., 0)` 全 0。
- **影响**：实测 vitest 风格 JSON → passed=0 failed=0。与 FD1（FrameworkDetector 给 vitest 打 jest_json 格式标签）闭环：检测端格式错配 → 解析端产出全 0。若测试命令返回码 0（vitest 部分失败仍可能 0），测试被误判「通过」。
- **验证方式**：实测（见 §5）。

### OP4 [P3] GoTestParser 只数 `--- PASS:`/`--- FAIL:` 行：包级 FAIL（编译错误/panic）不计

- **Bug 代码**：

```python
# :178-182 - 只数用例级 PASS/FAIL 标记
pass_count = len(re.findall(r"--- PASS:", raw_output))
fail_count = len(re.findall(r"--- FAIL:", raw_output))
```

- **根因**：go test 的包级 `FAIL`/`FAIL\tpkg`（编译失败、panic）不带 `--- FAIL:` 前缀，不计入 failed。
- **影响**：实测 panic 场景（有 `--- PASS:` 无 `--- FAIL:`，尾部 `FAIL` + `FAIL\tgithub.com/x/y`）→ passed=1 failed=0，被当「全过」。
- **验证方式**：实测（见 §5）。

### OP5 [P3] RustTestParser errors 收集摘要行噪声

- **Bug 代码**：

```python
# :205-207 - 所有含 FAILED 且非 --- 的行进 errors
for line in raw_output.split("\n"):
    if "FAILED" in line and "---" not in line:
        result.errors.append(line.strip())
```

- **根因**：cargo test 的 `test result: FAILED.` 摘要行含 FAILED → 整行进 errors，与具体失败用例重复。
- **影响**：errors 列表噪声（摘要行 + 失败列表重复），前端错误面板信息冗余。

### OP6 [P3] GenericTextParser 正则形态/顺序粗糙：特定输出形态漏匹配

- **Bug 代码**：

```python
# :73-79 - "N passed"/"N failed" 需数字紧跟空格；"1 test passed" 不匹配
passed_match = re.search(r"(\d+)\s+passed", raw_output)
```

- **根因**：`(\d+)\s+passed` 要求数字直接空格接 passed。"1 test passed"/"tests passed: 3"/"3 tests, 2 passed" 等常见形态漏匹配或取错；errors 正则 `ERROR[:\s]+(.+)` 只匹配大写 ERROR。
- **影响**：cpp/make/未知格式的文本输出解析结果不稳定，取决于框架措辞。

### OP7 [P3] CppTestParser 纯委托 GenericTextParser：格式层级虚设

- **Bug 代码**：

```python
# :212-216
class CppTestParser:
    def parse(self, raw_output: str) -> ParsedTestResult:
        return GenericTextParser().parse(raw_output)
```

- **根因**：cpp_text 格式无专属解析逻辑，与 generic 无差异。
- **影响**：格式层级存在但无实际价值；make/catch2/gtest 输出措辞各异，统一走 generic 正则。

### OP8 [P3] `parse` 参数名 `format` 遮蔽内置函数

- **Bug 代码**：

```python
# :42 - format 是内置函数名
def parse(raw_output: str, format: str) -> ParsedTestResult:
```

- **根因**：参数名遮蔽内置 `format()`，命名规范问题。
- **影响**：可维护性（无功能性 bug）。

### OP9 [P3] JUnitXMLParser/JestJSONParser 零测试 + 全部用例为文本输入

- **Bug 代码**：

```python
# tests/unit/test_v4_8_features.py:144-182 - 5 个用例全文本输入
output = "test_api.py::test_login PASSED\n...\n2 passed, 1 failed"
```

- **根因**：测试只覆盖「文本含 N passed/failed」形态，印证了 OP1 的「实际解析文本」现状；真 XML/JSON 结构、skipped、panic、vitest 全无覆盖。
- **影响**：OP1/OP2/OP3/OP4 的全部误判在测试网下通行，解析器回归零保护。

## 4. 修复建议

- **OP1**：`python_pytest` preset 的 output_format 改为 `pytest_text`（匹配 `pytest -xvs` 文本输出）或新增真 XML 解析分支（检测 `<?xml` 头走 xml.etree）。
- **OP2**：解析 `<testsuite>` 的 skipped 属性并从 passed 扣除；用 xml.etree.ElementTree 真解析替代正则。
- **OP3**：与 FD1 一起修——vitest 有专属 output_format/preset；或 JestJSONParser 兼容 vitest 结构。
- **OP4**：GoTestParser 增加包级 `^\s*FAIL\s*$` 行/`FAIL\t` 行检测计入 failed。
- **OP5**：errors 过滤掉 `test result:` 摘要行。
- **OP6**：放宽正则到 `(?:(\d+)\s+)?tests?\s+passed` 等常见形态；errors 大小写不敏感。
- **OP7**：删除 CppTestParser 或按 make/gtest/catch2 措辞实现专属解析。
- **OP8**：参数改名 `output_format`。
- **OP9**：补 XML/JSON/skipped/panic/vitest 结构用例。

## 5. 待实测项

- OP1 已实测（pytest 真 XML → 0/0）。
- OP2 已实测（skipped 混入 passed，tests=10/fail=2/err=1/skip=3 → 7）。
- OP3 已实测（vitest JSON → 0/0）。
- OP4 已实测（Go panic → failed=0）。
- OP5-OP9 为代码级结论。
