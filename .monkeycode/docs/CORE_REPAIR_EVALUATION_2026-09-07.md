# Core 增量修复实测（2026-09-07）

## 已确认根因与修复

1. 上轮生成项目在 `app/main.py:29-33` 将 `lifespan` 传给 `FastAPI.include_router()`，运行时返回 `TypeError`，pytest 收集和运行探针均失败。这是模型产物语义错误，本轮保留原文件与真实失败证据。
2. 活跃入口 `orchestrate_endpoints` 选择 `IncrementalAdapter`；候选校验此前只用变更文件构建 `planned_contents`，遗漏保留的 `app.models` 和 `app.schemas`。现以快照、磁盘存在性、项目路径和显式授权筛选保留文件，读取实际依赖内容并继续校验导出；生成上下文分别声明可导入集合和可写集合。
3. 评测 runner 此前将编排生成的根目录 `.dep_graph.json` 算作额外业务文件。现精确排除此路径；额外隐藏文件和嵌套同名文件仍计入严格集合。
4. 本轮第一次重测发现增量收尾把验证刷新产生的五个 `.pyc` 文件判为计划外修改。`ProjectSnapshot` 和磁盘成功门禁现共用字节码缓存规则，仅豁免直接位于 `__pycache__` 下的 `.pyc`，同目录源码仍受检查。

未添加 FastAPI/Todo 固定门禁或模板回退；未手改生成产物、安装包、读取 LLM 环境凭据、提交或推送代码。

## 修改文件

- `app/agent/orchestration/adapters.py`
- `app/agent/project_snapshot.py`
- `app/agent/orchestration/artifact_committer.py`
- `tests/manual/run_core_evaluation_case.py`
- `tests/unit/test_orchestration_adapters.py`
- `tests/unit/test_orchestration_artifact_committer.py`
- `tests/unit/test_evaluation_runner.py`
- `.monkeycode/docs/ARCHITECTURE.md`、`INTERFACES.md`、`DEVELOPER_GUIDE.md`、本报告
- `.monkeycode/specs/2026-08-31-multilanguage-generation-orchestration/tasklist.md`

## 单元回归

- 首批相关回归：230 passed，3 warnings，4.61 秒；日志 `/tmp/terminal_term_1788802493880_785.log`。
- 缓存修复后扩大回归：300 passed，3 warnings，4.56 秒；日志 `/tmp/terminal_term_1788802795979_789.log`。
- 一次测试命令误引用不存在的 `test_change_plan.py`，退出码 4、未收集测试；已纠正并执行上述 300 项。原日志 `/tmp/terminal_term_1788802772882_788.log`。

```bash
python3 -m pytest tests/unit/test_orchestration_*.py tests/unit/test_declarative_contracts.py tests/unit/test_evaluation_runner.py tests/unit/test_synthesis_validation.py tests/unit/test_toolchain.py -q
```

## 真实运行数据

每次均使用完整命令，保留默认最多三次自动 repair 和原有提前终止条件：

```bash
SECRET_KEY=local-evaluation-secret PYTHONPATH=/workspace python3 tests/manual/run_core_evaluation_case.py python-small-spec_first --timeout 900
```

| 运行 | 总耗时 | 初始调用 / token | repair 调用 / token | 严格集合 | 最终状态 |
| --- | --- | --- | --- | --- | --- |
| 用户提供的上轮 | 100.298s | 8 / 64344 | 6 / 64363 | false | 失败 |
| 本次第一轮 | 141.993s | 10 / 88283 | 8 / 91736 | true | 失败，缓存误报回滚 |
| 本次第二轮 | 151.066s | 12 / 99124 | 6 / 75237 | true | 失败，模型语义错误 |

上轮日志 `/tmp/terminal_term_1788800892752_784.log`，报告 `/tmp/opencode/python-small-spec_first-1788800893-report.md`，项目 `projects/1/evaluation_python-small-spec_first__1788800893`。

本次第一轮初始节点尝试：models、schemas、main 各 1 次，test_crud 2 次。初始产物四文件齐全、编译通过；`DateTime(timezone=True, default=...)` 触发模型代码运行时错误，pytest 收集 0 项、1 个错误。repair 实际执行 1 次，HTTP 200，四个文件各尝试 1 次，调度 completed，但 `incremental.untouched_file_changed` 导致事务回滚。最终复验仍为原模型错误，测试、启动、CRUD 和持久化均失败，进程退出码 1。合计 18 次模型调用、180019 tokens。

- 第一轮日志：`/tmp/terminal_term_1788802552547_787.log`
- 第一轮后端日志：`/tmp/terminal_term_1788802529117_786.log`
- 第一轮项目：`projects/1/evaluation_python-small-spec_first__1788802553`
- 缓存误报检查点：`data/orchestration_core_checkpoints/8a642196-c19b-4c7f-aa5d-e81637911386-1788802646605441323-incremental.json`

## 资源与后端

后端按 README 启动，当前终端 `term_1788802826187_790`，日志 `/tmp/terminal_term_1788802826187_790.log`。每次重载先停止旧后端，创建前检查后台列表；后端 40%、既有 Redis 10%、实测 30%，配额合计 80%，实测和本轮后端均设置 3600000ms 上限。后端启动成功；应用日志显示缓存使用 memory，既有 Redis 进程保留。

第二轮完整实测已结束，终端 `term_1788802872205_791`，日志 `/tmp/terminal_term_1788802872205_791.log`，正常退出码 1，峰值内存 152.09 MiB。

## 第二轮最终证据

- 项目：`projects/1/evaluation_python-small-spec_first__1788802872`。
- 初始 HTTP 200，节点尝试 main/models/test_crud 各 1 次、schemas 3 次；四文件齐全、编译通过，pytest 收集 0 项、1 个错误。初始失败为 `DateTime.__init__() got an unexpected keyword argument 'default'`。
- 自动 repair 实际执行 1 次，HTTP 200，78.898 秒，修改 models/main/test_crud 三文件，各尝试 1 次；schemas 作为真实保留依赖通过候选校验。调度 `completed`，随后项目 Profile 验证失败。
- 修复候选的实际失败由检查点保留：`sqlalchemy.exc.ArgumentError: Attribute 'created_at' ... includes dataclasses argument(s): 'default_factory' but class does not specify SQLAlchemy native dataclass configuration.`；pytest 收集 0 项、1 个错误。
- repair 检查点：`data/orchestration_core_checkpoints/d49820b5-ba2d-4255-a7d1-0f98e455a891-1788802943092375872-incremental.json`，`status=failed`，唯一诊断 `project.validation_failed`；未出现冻结依赖误判或缓存计划外变化诊断。
- Profile 失败按事务规则回滚，最终磁盘复验恢复为初始 `DateTime(default=...)` 错误。`plan_consistent=true`、`files_complete=true`、`compile_passed=true`；tests/startup/persistence 均 false，CRUD 未执行成功。`first_passed/candidate_passed/repaired_passed/success` 全为 false。
- 合计 18 次模型调用、174361 tokens，耗时 151.066 秒。自动 repair 沿用失败响应且复验未通过时提前终止的现有规则，未修改预算或成功标准。
- 本轮通用编排错误已修复并回归通过；剩余证据属于模型生成语义失败，代表性运行时验收和完整矩阵门禁继续保持未通过。
- `git diff --check` 通过；保留全部既有工作区修改。本轮两个真实生成目录均由原流程生成与自动 repair 管理。
