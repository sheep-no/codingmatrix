# TestRunner 演化深扫文档

> 版本：v0.1 | 扫描日期：2026-08-09 | 状态：已完成
> 归属：Agent 大系统 / 支撑模块（多语言沙箱测试执行器）
> 路径：app/agent/test_runner.py（811 行）+ orchestrator_testing.py（306 行 TestingMixin 消费入口）
> 索引：[TASKS.md](../TASKS.md)

## 1. 模块作用与功能

多语言本地沙箱测试执行器：Python 用 venv+复制隔离沙箱，JS/Go/Java/Rust 按需 subprocess 执行；集成 FrameworkDetector（6 框架检测）、OutputParser（多语言输出解析）、ServiceContainerManager（依赖服务容器）、安全扫描（记录不中止）、并发控制（信号量 5）。

- **核心类**：`IsolatedTestRunner`（test_runner.py:141）、兼容别名 `TestRunner`（:801）。
- **主要流程**（`run_tests` :175-271）：安全扫描 → FrameworkDetector.detect → 服务容器 → Python 走 venv+复制+白名单装依赖，非 Python 原目录执行 → 构建测试命令 → `_execute_test`（subprocess + timeout + 进程组 kill）→ OutputParser 解析 → cleanup。
- **辅助能力**：`_start_service_containers`(:325 Docker 优先/本地检测降级 Mock)、`_create_venv`(:426)、`_copy_project`(:442 跳过 SKIP_COPY_DIRS/隐藏文件/超大文件)、`_install_dependencies`(:474 白名单过滤)、`_build_test_command`(:569)、`_build_sandbox_env`(:679 环境白名单 + sqlite DATABASE_URL)、`_scan_security`(:710 FORBIDDEN_PATTERNS)、`_parse_with_output_parser`(:741)、`_cleanup`(:779)。
- **常量**：`FORBIDDEN_PATTERNS`(:34)、`ALLOWED_PIP_PACKAGES`(:48 ~100 包)、`ENV_WHITELIST`(:93)、`SKIP_COPY_DIRS`(:103)、`MAX_CONCURRENT_TESTS=5`(:113)。

## 2. 依赖与被依赖

- **导入依赖**：`app.agent.tracing`（traced 装饰器 :30/:174）、`framework_detector`(:31)、`output_parser`(:32)、惰性导入 `docker`(:336)、`service_container_manager`(:345)、`docker_runner`（orchestrator_testing:213）。
- **生产使用方**：
  - `orchestrator_testing.py:19-102` `TestingMixin._run_dynamic_tests`——统一测试入口：`_select_tests`(ImpactAnalyzer/TestSelector :104) → `_detect_test_command`(:160，`cd /app && ...` 为 docker 设计) → **Docker 优先**（:35-37 `_run_tests_in_docker`，DOCKER_AVAILABLE 才用，否则回退）→ 本地 `runner.run_tests()`(:40) → 汇总 + 失败聚类（FailureClusterer :129）
  - `traditional_generate.py:292-294`（`IsolatedTestRunner(self.output_dir)` → `_run_dynamic_tests`）
  - `orchestrator_generation/error_recovery.py:16-29`（ReAct 自动修复循环重跑测试）
- **测试覆盖**：`tests/unit/test_runner_enhanced.py`（约 35 测试）——白名单内容、安全扫描不中止、5 语言 detect、**非 Python 原目录执行（:184 固化预期）**、信号量限流、各类输出解析、服务容器降级。未覆盖：「未找到测试文件→success=True」、docker 分支 summary、`_build_sandbox_env` 的 DATABASE_URL 覆盖语义。

## 3. 已探明 Bug

### TR1 [P2]「未找到测试文件」直接判定测试通过

- **现象**：Python 项目无测试文件时，动态测试返回 `success=True`。
- **Bug 代码**：

```python
# test_runner.py:242-246
targets = test_paths or self._find_test_files()
if not targets and not test_command and language == "python":
    result.success = True
    result.logs = "未找到测试文件"
    return result
```

- **根因**：把「没有测试可跑」当作「测试通过」。生成的项目若未产出测试文件，动态测试静默通过，不触发失败恢复。
- **影响**：与 TG2（test_results 默认 success=True）、IM2（内容启发式）同属「存在≠正确」验证语义主线——**无测试文件 → 通过** 掩盖了「生成器根本没写测试」这一真实缺陷；传统生成链路的 final success（traditional_generate.py:345 `success = len(errors)==0 and test_results.get("success", True)`）据此判定成功。
- **触发条件**：python 项目 `_find_test_files` 返回空（无 tests/ 目录、无 test_*.py、无 *_test.py）。
- **验证方式**：构造无测试文件的项目跑 `run_tests()`，观察 success=True（实码可证，:243-246）。

### TR2 [P2] 非 Python 项目在原目录执行测试，无任何隔离

- **Bug 代码**：

```python
# test_runner.py:235-238 - 非 Python 项目直接用项目原目录作为工作目录
else:
    self._work_dir = self.project_path
    logger.info(f"非 Python 项目，直接在原目录执行: {language}")

# 后续 :614-621 在此目录 create_subprocess_exec 执行 npm test / go test 等
```

- **根因**：Python 走 venv+复制隔离（:213-234），非 Python 直接原目录执行——`npm test`/`go test` 的构建产物（dist/node_modules/.next）、副作用脚本直接作用于用户真实项目文件，且与生成流程共享目录。
- **影响**：JS/Go/Java/Rust 项目测试污染原目录、无环境隔离（依赖用宿主机全局安装状态）；`test_runner_enhanced.py:184 test_non_python_project_works_in_original_dir` 将该行为固化为预期。
- **触发条件**：任一非 Python 语言项目跑动态测试。
- **验证方式**：JS 项目 run_tests，观察工作目录 == project_path。

### TR3 [P3] `_execute_test` 成功判定只看 returncode，与解析出的失败数解耦

- **Bug 代码**：

```python
# test_runner.py:654-665 - success 仅由 returncode 决定
return TestResult(
    success=proc.returncode == 0,
    total_tests=0, passed=0, failed=0, ...
)

# :741-775 - 统计靠后续 OutputParser 解析，与 success 决策分离
result = self._parse_with_output_parser(result)
```

- **根因**：success 与 passed/failed 统计两套来源（returncode vs 日志解析）。`_parse_with_output_parser` 的 fallback（:756-773）仅在三个数字全为 0 时触发——若 OutputParser **部分解析**（如识别到 passed 但漏 failed），统计不完整而 success 仍以 returncode 为准；极端下 returncode=0 但日志含失败（框架以非标准退出码报告）时 success 误判。
- **影响**：失败测试数可能与 success 不一致，ReAct 修复依据 failed_tests 可能漏触发。
- **验证方式**：构造 returncode=0 但日志含 "1 failed" 的输出（mock subprocess）观察 success=True。

### TR4 [P3] 全局信号量 `_SemaphoreHolder` 跨事件循环共享

- **Bug 代码**：

```python
# test_runner.py:116-123
class _SemaphoreHolder:
    semaphore: Optional[asyncio.Semaphore] = None

def _get_semaphore() -> asyncio.Semaphore:
    if _SemaphoreHolder.semaphore is None:
        _SemaphoreHolder.semaphore = asyncio.Semaphore(MAX_CONCURRENT_TESTS)
    return _SemaphoreHolder.semaphore
```

- **根因**：`asyncio.Semaphore` 创建时绑定当前事件循环，全局单例在多事件循环环境（多 worker / 多请求各自 loop）下复用错误 loop 的信号量——Python 3.10+ 部分场景不主动报错但 wait 行为跨 loop 错乱。ERL5/MCP1 同类全局状态。
- **影响**：限流失效或跨请求串扰；`test_semaphore_default_limit`/`test_concurrent_execution_respects_limit` 单 loop 下通过。
- **验证方式**：两个不同 loop 交替调用 `_get_semaphore()` 观察语义漂移。

### TR5 [P3] 安全扫描仅前 100 个 py 文件 + 字符串正则匹配

- **Bug 代码**：

```python
# test_runner.py:712-715
py_files = list(self.project_path.rglob("*.py"))
scan_limit = min(len(py_files), 100)
for py_file in py_files[:scan_limit]:
```

- **根因**：大项目仅扫前 100 文件（按目录序，非按风险），且用逐行正则匹配 FORBIDDEN_PATTERNS（:722），不解析 AST——字符串常量里的 `os.system(` 误报、多行拼接的真实调用漏报。
- **影响**：安全扫描是「记录警告不中止」，语义为提示性，覆盖不全降低其价值。
- **验证方式**：构造 101+ 文件项目观察第 101 个含危险模式文件未被扫描。

### TR6 [P3] 白名单过滤静默丢弃不在名单的依赖

- **Bug 代码**：

```python
# test_runner.py:509-512 - 不在白名单的包行被过滤
pkg_base = re.split(r'\[', pkg_name)[0].strip()
if pkg_base in ALLOWED_PIP_PACKAGES or pkg_name in ALLOWED_PIP_PACKAGES:
    allowed_lines.append(line)
```

- **根因**：requirements 中不在 `ALLOWED_PIP_PACKAGES`（约 100 包）的依赖被静默丢弃（如 `boto3`、`elasticsearch`、自定义包），安装后测试因缺依赖失败，且失败原因被归为「测试失败」而非「依赖被过滤」。
- **影响**：白名单外依赖的项目测试失败率偏高，且过滤动作无日志提示用户。
- **验证方式**：requirements 含 `boto3`（不在白名单）观察过滤后 pip 安装无 boto3。

### TR7 [P3] `_build_sandbox_env` 无条件注入 sqlite DATABASE_URL，覆盖项目真实配置

- **Bug 代码**：

```python
# test_runner.py:695
env['DATABASE_URL'] = f'sqlite+aiosqlite:///{self._work_dir / "test_sandbox.db"}'
```

- **根因**：Python 沙箱恒注入 sqlite 的 DATABASE_URL（除非 :704 service env 含 DATABASE_URL 才被 update 覆盖）；`ENV_WHITELIST`（:93-101）不含 DATABASE_URL，宿主机配置也不会带入。依赖 PostgreSQL/MySQL 的项目测试在 sqlite 下运行，方言差异导致行为异常。
- **影响**：数据库相关项目本地测试与真实环境语义不一致。
- **验证方式**：构造用 postgresql DATABASE_URL 的项目观察沙箱 env 被强制 sqlite。

### TR8 [P3] `_cleanup` 在用户项目目录递归删除 `__pycache__`

- **Bug 代码**：

```python
# test_runner.py:793-798
if self.project_path.exists():
    for pycache in self.project_path.rglob("__pycache__"):
        shutil.rmtree(str(pycache), ignore_errors=True)
```

- **根因**：Python 隔离场景在临时复制目录测试，但 cleanup 对**原始 project_path** 递归删 `__pycache__`——修改用户项目文件系统（虽无实质危害但属越界）。
- **影响**：非 Python 场景（原目录执行）更明显——运行测试产生的 `__pycache__` 被删属可接受，但删除操作与验证职责无关。
- **验证方式**：项目含 `__pycache__` 时 run_tests 后观察目录被删。

## 4. 潜在问题与未知点

- `_detect_test_command`（orchestrator_testing.py:160-202）恒返回 `cd /app && ...`（为 docker 容器挂载点设计），本地 fallback 不消费该值（runner.run_tests() 内部重新构建命令）——函数名与 docker/本地双用途语义易误读，未验证 docker 挂载点确实为 /app。
- `_run_tests_in_docker`（:211-306）summary 初始 `total=0`，`errors=len(result.errors)`，失败聚类在 docker 分支不执行（只在本地分支 :53）。
- `_select_tests`（:104-127）的 ImpactAnalyzer/TestSelector 未深扫，变更影响选测的准确度未验证。
- `run_tests` finally（:263-269）的 `language` 变量在 detect 异常时保持初始 "python"，cleanup 路径安全但语义靠初始值兜底。

## 5. 修改建议（改什么 → 达成什么目的）

| # | 优先级 | 修改动作 | 达成目的 | 涉及位置 | 对应 Backlog |
|---|--------|---------|---------|---------|-------------|
| 1 | P2 | 「未找到测试文件」改返回 `success=False` + 明确 reason（或新增 `no_tests_found` 标志，让编排层决定是否补写测试而非静默通过） | 消除「无测试文件=通过」验证缺口，与 TG2/IM2 验证语义主线一致 | test_runner.py:243-246 | 待记 |
| 2 | P2 | 非 Python 项目也做隔离（复制到临时目录或容器/沙箱执行），删除原目录直跑路径 | 前端/后端多语言测试不污染项目，与 Python 隔离语义一致 | test_runner.py:235-238、test_runner_enhanced.py:184 同步改 | 待记 |
| 3 | P3 | `_execute_test` success 改为「returncode==0 且 parsed.failed==0」双重判定；修复 fallback 仅全零触发的部分解析丢失 | success 与失败统计一致，ReAct 修复可靠触发 | test_runner.py:654-665/741-775 | 待记 |
| 4 | P3 | `_get_semaphore` 改实例级（按 runner 或 request scope），删除全局单例 | 多 loop 环境限流正确，消除全局状态 | test_runner.py:116-123 | 待记 |
| 5 | P3 | 安全扫描移除 100 文件上限或按风险排序；正则改为 AST 解析 | 安全扫描覆盖完整、减少误报 | test_runner.py:710-737 | 待记 |
| 6 | P3 | 白名单过滤记录被丢弃的包名到日志/警告；或提供配置项放行 | 依赖过滤可审计，测试失败可归因 | test_runner.py:501-522 | 待记 |
| 7 | P3 | sqlite DATABASE_URL 仅在没有项目自带数据库配置时注入，或从 ENV_WHITELIST/项目 .env 探测 | 数据库项目测试语义与真实环境一致 | test_runner.py:679-706 | 待记 |
| 8 | P3 | `_cleanup` 只清理测试产生的临时目录，不触碰用户 project_path | 职责边界清晰，不越界修改项目 | test_runner.py:793-798 | 待记 |

## 6. 演化方向关联

- TestRunner 是「验证闭环」（EVOLUTION.md §5.1，Evaluator 端）的**运行验证执行器**，与 CodeValidator（静态验证）、OutputParser（结果解析）、FailureClusterer（失败聚类）构成验证栈。TR1 的「无测试文件=通过」与 TG2/IM2 同属「存在≠正确」验证语义主线，是验证闭环语义统一的阻塞项之一。
- 双路径（Docker 优先 / 本地 fallback，orchestrator_testing.py:35-40）与 `_detect_test_command` 的 `/app` 硬编码——DockerRunner（docker_runner.py 802 行，未深扫）与本地 TestRunner 的验证语义需收敛，避免「同一项目两种验证结果」。
- TR2 非 Python 隔离缺失归入「多语言支持」演化方向；TR4 全局信号量归入「单例→按需实例」收敛主线（ERL5/MCP1/CEC6/DG7 同类）。
- 依赖白名单（TR6）与 requirements 校验（code_validator CV6）同属依赖管理收敛主线。
