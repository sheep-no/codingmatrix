# FrameworkDetector 演化深扫文档

> 版本：v0.1 | 扫描日期：2026-08-09 | 状态：已完成
> 归属：Agent 大系统 / 支撑模块（测试框架自动检测）
> 路径：app/agent/framework_detector.py（188 行）
> 索引：[TASKS.md](../TASKS.md)

## 1. 模块作用与功能

项目测试框架自动检测：按优先级「显式配置 → 包清单 → 源文件模式 → 默认 pytest」判断项目语言与测试框架，返回 `TestFrameworkConfig`（语言/框架/测试命令/镜像/输出格式），供测试执行栈选择正确的运行方式与镜像。

- **核心类**：`FrameworkDetector`（:24）。方法：`detect`（:35 优先级编排）、`_check_explicit_config`（:60 tox/setup.cfg/CI/pyproject）、`_check_package_manifests`（:85 package.json/pom.xml/build.gradle/go.mod/Cargo.toml/Makefile/CMakeLists）、`_check_source_patterns`（:156 源文件 rglob）、`_parse_ci_config`（:176 CI 关键词）。
- **依赖**：`test_framework_config.py`（TestFrameworkConfig + 6 preset：python_pytest/javascript_jest/java_maven/go_test/rust_cargo/cpp_make，无 vitest preset）。

## 2. 依赖与被依赖

- **生产使用方**（3 处）：
  - `test_runner.py:169/:202`——`_framework_detector.detect` 决定 language/framework，:577-578 用 `test_command` 构造命令
  - `orchestrator_testing.py:230`——docker 路径 detect 拿框架
  - `docker_runner.py:284/:490`——`auto_detect_framework` 时 detect 决定 test_command + docker_image（镜像切换）
- **测试覆盖**：tests/unit/test_v4_8_features.py `TestFrameworkDetector` 6 个 happy path 用例（pytest/jest/maven/go/rust/cpp 各一）。**全部是「存在清单→判对」正向用例，零误判/边界用例**。其中 `test_detect_python_pytest` 有测试假阳性问题（见 FD9）。

## 3. 已探明 Bug

### FD1 [P2] vitest 分支沿用 jest 输出格式与命令，vitest 项目测试解析必失败

- **Bug 代码**：

```python
# framework_detector.py:99-108 - vitest 手动构造 config，output_format 沿用 jest
if "vitest" in all_deps:
    config = FRAMEWORK_PRESETS["javascript_jest"]
    return TestFrameworkConfig(
        language="javascript", framework="vitest",
        test_command="npm run test", setup_commands=["npm install"],
        docker_image=config.docker_image,
        output_format="jest_json",   # ← 沿用 jest 格式
    )
```

- **根因**：vitest 无 preset，手动构造时 `output_format` 复制 jest 的 `jest_json`；vitest 的 JSON 输出（`--reporter=json`）结构（无 jest 的 `testResults[]`）与 jest 解析器期望不一致。`test_command="npm run test"` 依赖 scripts.test 存在（detect 只查 deps 不查 scripts）。
- **影响**：vitest 项目在 docker_runner/test_runner 里按 jest JSON 解析 vitest 输出 → 解析失败/部分丢失，测试结果失真。实测 detect vitest 项目返回 framework=vitest + output_format=jest_json。
- **验证方式**：实测（见 §5）。

### FD2 [P2] 任意 package.json "test" script 即判 jest：node --test/mocha/ava 假阳性

- **Bug 代码**：

```python
# :109-110 - 存在 test script 即等于 jest，不查具体框架
if "test" in data.get("scripts", {}):
    return FRAMEWORK_PRESETS["javascript_jest"]
```

- **根因**：判断「有 test script」而非「有 jest 依赖」。node --test/mocha/ava/custom 项目（scripts.test 存在但非 jest）全部落入 jest。
- **影响**：实测 `{"scripts":{"test":"node --test"}}` → framework=jest、test_command=npm test。test_command 可能跑通但 output_format=jest_json 解析 node 内置/mocha 输出失败；或 npm test 脚本本身不存在。**「存在 test script」≠「jest 框架」——检测语义误判**（与「存在≠正确」主线同源）。
- **验证方式**：实测（见 §5）。

### FD3 [P2] `_parse_ci_config` 关键词顺序碰撞：monorepo CI 多语言步骤误判

- **Bug 代码**：

```python
# :176-188 - 顺序敏感，pytest 先于 mvn/go test/cargo test
if "pytest" in content:
    return FRAMEWORK_PRESETS["python_pytest"]
if "npm test" in content or "jest" in content:
    return FRAMEWORK_PRESETS["javascript_jest"]
if "mvn" in content:
    return FRAMEWORK_PRESETS["java_maven"]
```

- **根因**：字符串包含 + 固定顺序。monorepo/多语言 CI 文件（含 pytest + mvn 多个 job）命中第一个关键词。
- **影响**：实测含 pytest+mvn 的 CI → pytest。整仓判成 Python，docker 镜像/命令/输出格式全错。`pytest`/`jest`/`mvn` 也可能出现在注释/安装日志中造成假阳性。
- **验证方式**：实测（见 §5）。

### FD4 [P3] pyproject.toml 字符串包含 "pytest"：注释/描述即判 pytest；tox/setup.cfg 只认存在

- **Bug 代码**：

```python
# :77-81 - 字符串包含非 TOML 解析
if pyproject.exists():
    content = pyproject.read_text(...)
    if "pytest" in content:
        return FRAMEWORK_PRESETS["python_pytest"]
# :62-66 - tox.ini/setup.cfg 存在即 pytest，不读内容
config_files = {"tox.ini": "python_pytest", "setup.cfg": "python_pytest", ...}
```

- **根因**：pyproject 用 `in` 判断而非解析 TOML 的 `[tool.pytest.ini_options]`；tox.ini/setup.cfg 只要存在即判 pytest，不验证是否真配置 pytest（可能是 nose/unittest 或纯 flake8 项目）。
- **影响**：实测 pyproject 注释 `# pytest will be used` → 判 pytest。误判。
- **验证方式**：实测（见 §5）。

### FD5 [P3] `_check_source_patterns` rglob 全量 + go→java→py→rust 顺序敏感

- **Bug 代码**：

```python
# :156-174 - 顺序固定，go 最先
go_test_files = list(project_path.rglob("*_test.go"))
if go_test_files: return FRAMEWORK_PRESETS["go_test"]
java_test_files = list(project_path.rglob("*Test.java"))
...
py_test_files = list(project_path.rglob("test_*.py"))
```

- **根因**：多语言项目按固定顺序取首个命中；`rglob` 全量递归（vendored/第三方代码计入）。Python 项目混入单个 `*_test.go`（工具链/vendored）即判 Go。
- **影响**：源文件模式的检测噪声大，且与包清单检测不一致（有 package.json 的 JS 项目若有 go 工具文件时，包清单先命中 JS 掩盖问题；无清单纯源文件多语言混编时判首个）。
- **验证方式**：构造含 `vendor/*_test.go` 的 Python 项目 → 判 go（实码可证）。

### FD6 [P3] Makefile 只判 "test" 子串：变量/注释含 test 即判 cpp_make

- **Bug 代码**：

```python
# :137-141 - "test" in content 假阳性
makefile = project_path / "Makefile"
if makefile.exists():
    content = makefile.read_text(...)
    if "test" in content:
        return FRAMEWORK_PRESETS["cpp_make"]
```

- **根因**：子串判断不验证是否有 test target。实测 `VERSION=test` 的纯构建 Makefile → cpp_make + `make test`。
- **影响**：无测试 target 的 Makefile 项目被切 gcc:13 镜像跑 make test（可能失败）；无语言证据强行判 cpp。
- **验证方式**：实测（见 §5）。

### FD7 [P3] CI 只查硬编码 `.github/workflows/test.yml` 单文件

- **Bug 代码**：

```python
# :65 - 单个文件名硬编码，其他 workflow 名不查
".github/workflows/test.yml": None,
```

- **根因**：只检查 test.yml，ci.yml/main.yml/build.yml 等其他 CI 文件不检测；无 rglob。
- **影响**：实际 CI 配置多为 ci.yml/main.yml，检测覆盖不足（但不致误判，只漏检）。

### FD8 [P3] `detect` 返回类型 Optional：preset 缺失时消费方 AttributeError 风险

- **Bug 代码**：

```python
# :72 - FRAMEWORK_PRESETS.get(preset_key) 类型 Optional
return FRAMEWORK_PRESETS.get(preset_key)
# test_runner.py:203-204 - 消费方直接解引用
language = self._detected_config.language
```

- **根因**：`detect` 若返回 None（FRAMEWORK_PRESETS 被删 key 等），test_runner:203-204 直接 `.language` 抛 AttributeError（:577-578 有 None 检查但 :203 没有）。当前 preset_key 均存在，风险低。
- **影响**：防御性不足，preset 变更/删减时消费方崩溃。

### FD9 [P2] `test_detect_python_pytest` 测的是默认 fallback 而非检测逻辑（测试假阳性）

- **Bug 代码**：

```python
# tests/unit/test_v4_8_features.py:70-81
def test_detect_python_pytest(self, temp_project):
    """测试检测 Python pytest 项目"""
    (temp_project / "requirements.txt").write_text("pytest\nflask\n")
    config = fd.detect(temp_project)
    assert config.language == "python"
    assert config.framework == "pytest"
```

- **根因**：`requirements.txt` **不在任何检查项中**（:62-174 无 requirements 检查）。项目无 tox/setup.cfg/pyproject/package.json/pom 等 → detect 走完三检查全 None → fallback 默认 pytest。断言恰好满足。
- **影响**：测试断言的是「无配置时默认 pytest」，但测试名/注释声称验证「检测到 pytest 项目」。**Python 检测逻辑（本不存在）实际零保护**；若未来实现 requirements/pytest 检测但实现有误（如判 jest），该测试不暴露。测试通过 ≠ 检测正确。
- **验证方式**：代码追踪（requirements.txt 无检查点）+ 测试恒过。

## 4. 修复建议

- **FD1**：新增 `javascript_vitest` preset（output_format=vitest_junit 或 vitest_json）；test_command 从 scripts.test 取值（存在时）。
- **FD2**：按 devDependencies 精确识别框架（jest/vitest/mocha/ava/node），test script 仅作为命令来源不作框架判据。
- **FD3**：`_parse_ci_config` 改为「识别多个关键词后按项目文件证据裁决」，或按 job 级解析；关键词用 word 边界匹配避免子串。
- **FD4**：pyproject 解析 TOML 的 `[tool.pytest.ini_options]`/`[tool.poetry]`；tox.ini/setup.cfg 读 section 验证 pytest 配置。
- **FD5**：源文件扫描排除 vendored/node_modules/venv，或用「多数派投票」替代首命中。
- **FD6**：Makefile 正则匹配 `^test:` target 而非子串。
- **FD7**：`rglob(".github/workflows/*.yml")` 检查所有 workflow。
- **FD8**：`detect` 返回非 Optional（None 时统一 fallback pytest），或在消费方统一 None 兜底。
- **FD9**：改写该测试——显式构造 pytest 配置（pyproject.toml 的 `[tool.pytest.ini_options]`）验证检测；同时补 fallback 专项用例（空项目 → pytest）。

## 5. 待实测项

- FD1/FD2/FD4 已实测（vitest→jest_json；node --test→jest；pyproject 注释含 pytest→pytest）。
- FD3 已实测（pytest+mvn CI→pytest）。
- FD6 已实测（VERSION=test Makefile→make）。
- FD5/FD7/FD8/FD9 为代码级结论。
