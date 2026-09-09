# Core 运行诊断与有界重试实测（2026-09-08）

## 活跃路径与修改

`app.main` 挂载 `ai_agent.router`，评测调用 `/api/v1/agent/orchestrate` 并显式选择 `engine=core`。同步 endpoint 通过 `_select_core_adapter()` 选择 SpecFirstAdapter 或 IncrementalAdapter，`execute_core_generation()` 执行 Core 并投影到 `OrchestratorResponse`。独立 V0-V6 控制面和旧 RepairRouter 具有各自用途，本轮修改直接覆盖这条活跃链路。

前轮检查点保留了 `DateTime(default=...)` 被 repair 改成 `default_factory` 后的新 dataclass 配置异常，但响应只投影概括错误。事务回滚后评测器读取旧磁盘，且失败响应立即停止，导致后续 repair 无法消费新异常。

- Core 在回滚前保存计划与授权保留依赖的 SHA-256，以及 `candidate_validation`；项目级 Profile 命令由 Agent Host 本地执行，Core 保存本地验证等待状态和回传结果。
- runtime 与响应 Schema 增加 `repair_feedback`，保留 task ID、终态、结构化诊断、完整调度候选指纹和 rollback 标记。未完成调度的部分产物不提供完整候选指纹。
- runner 优先使用最新候选诊断，磁盘复验单独保存；新的失败证据可以在 `MAX_REPAIR_ATTEMPTS=3` 内继续。重复历史诊断或完整候选明确无进展终止。
- 诊断指纹忽略耗时、对象地址与调度 attempts 计数。历史诊断循环也能终止。
- 成功同时要求 Core 成功与磁盘复验通过；冻结文件集合、编译、测试、启动、CRUD 和持久化门禁保持原验证逻辑。

源码修改：`app/agent/orchestration/core.py`、`runtime.py`、`app/agent/framework_profiles/validation.py`、`app/api/v1/ai_agent/schemas.py`、`tests/manual/run_core_evaluation_case.py`。测试修改：`tests/unit/test_orchestration_adapters.py`、`tests/unit/test_evaluation_runner.py`。

所有手工编辑使用 apply_patch，保留既有脏工作区；未提交、推送、读取 LLM 环境凭据或手改生成产物。

## 单元回归

```bash
python3 -m pytest tests/unit/test_orchestration_*.py tests/unit/test_declarative_contracts.py tests/unit/test_evaluation_runner.py tests/unit/test_synthesis_validation.py tests/unit/test_toolchain.py tests/unit/test_framework_profiles.py -q
```

- 初次结果：349 passed、2 failed；新测试误读 checkpoint 包装层，以及旧测试接受 Core 失败时的磁盘成功。修正两项断言后通过，原失败日志 `/tmp/terminal_term_1788828664689_792.log`。
- 第二次：351 passed、3 warnings，7.11 秒，日志 `/tmp/terminal_term_1788828737406_793.log`。
- 指纹排除 attempts 计数后的最终回归：351 passed、3 warnings，7.17 秒，日志 `/tmp/terminal_term_1788829244492_796.log`，退出码 0。
- 新增 8 个参数化展开用例覆盖：不同诊断继续、重复诊断停止、重复候选停止、历史循环停止、三轮上限、Core 失败且磁盘成功仍保持失败、真实 repair 请求携带新诊断、真实事务 rollback 后检查点和响应诊断保留。

## 资源与服务

按 README 启动后端，旧终端 `term_1788802826187_790` 已停止；最新后端为 `term_1788828819236_794`，日志 `/tmp/terminal_term_1788828819236_794.log`。启动日志确认 Application startup complete，`GET /api/v1/health` 返回 200。

每次创建前检查终端列表；总内存 8352858112 字节，后端 40%、既有 Redis 10%、测试或实测 30%，同时配额 80%。后端与真实评测均设置 3600000ms 上限，测试上限 240000ms。应用实际使用 memory cache，既有 Redis 保留。

预览地址：https://8000-b9c59b025666bcf4.monkeycode-ai.online

## 真实运行 A

完整执行默认自动 repair，无预算覆盖：

```bash
SECRET_KEY=local-evaluation-secret PYTHONPATH=/workspace python3 tests/manual/run_core_evaluation_case.py python-small-spec_first --timeout 900
```

日志 `/tmp/terminal_term_1788828849163_795.log`，终端退出码 1。项目 `projects/1/evaluation_python-small-spec_first__1788828849`。总耗时 293.902 秒，39 次模型调用，357629 tokens，峰值内存 92.81 MiB。

| 阶段 | 是否进入 / HTTP | 新诊断与处理 | 调用 / tokens |
| --- | --- | --- | --- |
| 初始生成 | 是 / 200 | tests/test_crud.py 引用的 app/main.py 未导出 app；调度失败 | 12 / 108017 |
| repair 1 | 是 / 200 | 新候选改为 app/schemas.py 未导出 TodoSchema；回滚，诊断变化允许继续 | 15 / 133881 |
| repair 2 | 是 / 200 | 再次出现 app/main.py 未导出 app；回滚，命中历史重复诊断 | 12 / 115731 |
| repair 3 | 否 | `no_progress_repeated_diagnostic`，明确停止 | 0 / 0 |

repair 1 耗时 83.248 秒，repair 2 耗时 122.898 秒。repair 2 的 `input_failure` 为 `core_candidate`，明确含上一候选的 TodoSchema 错误；磁盘复验仍报告 tests/test_crud.py 缺失。这证明 rollback 后新的候选证据通过 API 投影进入下一轮。

最终仅三个业务文件，`compile_passed=true`，`plan_consistent/files_complete/tests_passed/startup_passed/persistence_passed=false`，`first_passed/candidate_passed/repaired_passed/success=false`。CRUD 因缺少必需测试文件未执行。本次失败为模型跨文件符号不一致；磁盘 main.py 只有 create_app() 工厂，未导出模块级 app，诊断与源码一致。

检查点：

- 初始：`data/orchestration_core_checkpoints/4f1e4d73-c4f5-40ec-9c79-74cb77110538-1788828850055791073-spec_first.json`
- repair 1：`data/orchestration_core_checkpoints/a7a78d52-cc9f-4750-b550-3d24a0775098-1788828937275668749-incremental.json`
- repair 2：`data/orchestration_core_checkpoints/1c5d39e0-daed-4f5a-9d15-89548447a557-1788829020632060808-incremental.json`

本次在调度阶段失败，Profile runtime 诊断回滚链路由单元测试验证；真实运行未到达该阶段。随后排除 attempts 计数对诊断指纹的影响，并使用同一完整命令重测。

## 真实运行 B

第二次使用相同命令验证最终 runner：

日志 `/tmp/terminal_term_1788829288545_797.log`，终端退出码 1；项目 `projects/1/evaluation_python-small-spec_first__1788829289`。总耗时 359.178 秒，36 次模型调用，276556 tokens；初始阶段 7 次调用、45265 tokens。

| 阶段 | 是否进入 / HTTP | 新诊断与处理 | 调用 / tokens |
| --- | --- | --- | --- |
| 初始生成 | 是 / 200 | `tests/test_crud.py` 文件生成超时；调度状态 timed_out | 7 / 45265 |
| repair 1 | 是 / 200 | 新诊断为测试模块使用未定义全局 `get_db`；回滚后继续 | 15 / 117812 |
| repair 2 | 是 / 200 | 新诊断为 project profile validation failed；回滚后继续 | 10 / 76098 |
| repair 3 | 是 / 200 | 仍为 project profile validation failed，候选完整指纹已记录；达到三轮预算停止 | 4 / 37381 |

总调用数与分阶段调用数一致为 36，token 总数为 276556。repair 1 耗时 74.290 秒，repair 2 耗时 55.540 秒，repair 3 耗时 31.317 秒。repair 3 的完整调度状态为 completed，但 profile 测试仍失败；`candidate_fingerprint` 为 `6dc0d3ad58fe7861bb2fdd28ea419b91a44354acca1d959a8819ed881dd360f2`，随后 rollback=true。

最终 `repair_stop_reason=budget_exhausted`。`compile_passed=true`，`files_complete=false`（缺失 `tests/test_crud.py`），`tests_passed=false`、`startup_passed=false`、`persistence_passed=false`、`candidate_passed=false`、`success=false`。结果同时显示完整候选生成过，但 profile 的测试失败和回滚后的必需文件复验仍阻止成功。

repair 2 的实际 pytest 输出包含 `TypeError: 'async_sessionmaker' object does not support the asynchronous context manager protocol` 和字符串 `/` 操作类型错误；repair 3 则变为 `TypeError: 'NoneType' object is not callable`，以及模块缺少 `get_test_db_path` 的 AttributeError。这些具体运行异常随 `repair_feedback` 保留，repair 3 的 `input_failure` 与 repair 2 的 `result_failure` 一致。新运行诊断与回滚磁盘上“缺少测试文件”的复验结果明确分开。

第二次实测确认：timed_out 初始失败可进入 repair；每轮新诊断会传递给下一轮；达到 `MAX_REPAIR_ATTEMPTS=3` 后停止；Core 失败与磁盘验证的组合不会被错误判定为成功。生成结果仍存在跨文件一致性和测试实现错误，完整交付验收保持未通过。

## HTTP body 合同修复

用户另行报告生成的 `tests/test_crud.py` 将 Pydantic `TodoCreate` 实例直接传给 httpx `json=`，触发不可序列化异常。本轮依据该报告修复合同链路；上述 A/B 日志的历史结论保持原样。

根因是 HTTP 调用需要 JSON 可序列化值，而模型实例尚未转换；原评测结构化合同只传 method/path/status_code，缺少 body schema 和编码语义。活跃端点、Core 索引和后端文件提示词已有透传能力，本轮增加 `HttpContract` 的可选 request/response body schema 与 serialization guidance，在评测 case 中声明并通过首次、repair 共用构造函数传入。Core 仅提示遵循合同中的字段，领域路由与框架编码示例保留在评测数据中。

兼容验证覆盖省略新增字段的旧路由、额外 status_code、routes/endpoints 两种输入、JSON 往返、body 字段改变摘要、三类 adapter 上下文、文件 retry、实际模型提示词和自定义库存合同首次/repair 请求。指导说明 Pydantic v1 `dict()` 对日期等非 JSON 原生类型仍需编码。

```bash
python3 -m pytest tests/unit/test_code_synthesis_contracts.py tests/unit/test_evaluation_runner.py tests/unit/test_evaluation_matrix.py tests/unit/test_orchestration_adapters.py tests/unit/test_orchestration_endpoint_core_adapter.py tests/unit/test_orchestrator_files.py tests/unit/test_orchestration_generation_scheduler.py tests/unit/test_orchestration_core.py tests/unit/test_stack_adapters.py -q
```

最终结果：361 passed、3 warnings，5.13 秒；`git diff --check` 通过。保留脏工作区，未安装依赖、读取 LLM key、提交或推送，生成项目未作手工修改。

真实验收未完成：本轮没有再次调用真实模型生成或执行生成项目的 CRUD/SQLite 持久化验收。单元测试证明合同传递及可见性；模型是否正确采用指导、生成项目是否完整通过测试和自动 repair，仍需真实复验。

## HTTP body 合同更新后的真实验收 C

2026-09-08 07:22 UTC 起执行当前工作区最新代码，使用上文相同验收命令 `python-small-spec_first --timeout 900`，保留默认三轮自动 repair。以下为本次新增实测，前述 A/B 和单元测试结果保留其历史含义。

### 服务与资源

- 启动前检查后台终端：Redis `term_1788349922836_415` 运行中，旧 backend `term_1788842402485_798` 已超时退出，8000 端口空闲。
- 按 README 与用户指定命令重载 backend：`term_1788852109750_800`，日志 `/tmp/terminal_term_1788852109750_800.log`。07:22:06 显示 `Application startup complete`，健康检查 `GET /api/v1/health` 返回 HTTP 200。
- 总内存约 7965 MiB，backend 40%、Redis 10%、验收 30%，总配额 80%。backend 峰值 314.32 MiB，验收峰值 122.04 MiB，Redis 峰值 14.66 MiB。验收终端正常退出码 1，未被资源限制或超时终止。
- 本次 backend 日志仍显示应用使用 memory cache；保留既有 Redis。backend 在验收后继续运行。
- 验收终端 `term_1788852157327_801`，完整输出 `/tmp/terminal_term_1788852157327_801.log`。
- 项目绝对路径：`/workspace/projects/1/evaluation_python-small-spec_first__1788852158`。

### Core 与逐轮结果

四份实际检查点均为 `engine_version=core-v1`，初始模式 `spec_first`，三轮 repair 为 `incremental`；合同摘要均为 `4ed8759875d29624ae04ca2a5f39b099a68c2b469ae49e3fe6a43d5a6e72af5b`。初始请求检查点明确保存 POST/PUT 的 `request_body_schema` 与 `serialization_guidance`。

| 阶段 | HTTP | 模型调用 | tokens | 候选完成文件 | 复验磁盘文件 | 磁盘 compile | 候选 tests | 磁盘 tests | startup | CRUD | persistence |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 初始 | 200 | 12 | 112205 | 3/4 | 3/4 | 通过 | 未执行，调度失败 | 未执行，缺文件 | 未执行 | 未执行 | 未执行 |
| repair 1 | 200 | 10 | 86692 | 2/4 | 3/4，已回滚 | 通过 | 未执行，调度失败 | 未执行，缺文件 | 未执行 | 未执行 | 未执行 |
| repair 2 | 200 | 12 | 108618 | 3/4 | 3/4，已回滚 | 通过 | 未执行，调度失败 | 未执行，缺文件 | 未执行 | 未执行 | 未执行 |
| repair 3 | 200 | 12 | 107260 | 4/4 | 3/4，已回滚 | 通过 | pytest 7 errors | 未执行，缺文件 | 未执行 | 未执行 | 未执行 |

总计 **46 次调用、414775 tokens、365.722 秒**。repair 1/2/3 的 API `elapsed_time` 分别为 68.220、90.339、108.993 秒。初始 backend HTTP 请求耗时 96.466 秒。调用与 token 数取自 API `generation_metrics`，包含文件生成过程中的调用。

磁盘 compile 实际执行 `/usr/bin/python3 -m compileall -q .`，各轮 stdout/stderr 均为空。该结果仅证明现存文件语法编译通过。各轮磁盘均缺失 `tests/test_crud.py`，runner 的文件完整性门禁阻止后续 tests/runtime 执行，故 startup、CRUD、跨进程 SQLite persistence 均无成功观测；报告布尔字段为 false。

### 具体失败与回滚证据

1. 初始：`tests/test_crud.py` 尝试 3 次仍失败，诊断为 `Python module uses undefined global names: engine; local dependency app/main.py does not export: app`。其他三个文件各尝试 1 次并完成。
2. repair 1：`app/main.py` 尝试 3 次，最终 `local dependency app/schemas.py does not export: TodoUpdate`；测试节点为 blocked、尝试 0 次，原因 `upstream artifact app/main.py is unavailable`。`repair_feedback.rolled_back=true`。
3. repair 2：测试文件尝试 3 次仍报 `Python module uses undefined global names: get_db; local dependency app/main.py does not export: app`。`repair_feedback.rolled_back=true`。
4. repair 3：四个候选文件均 completed，main/test 各尝试 2 次，models/schemas 各 1 次；实际执行 `python3 -m pytest`，结果 `1 warning, 7 errors in 0.77s`。诊断包含 `fixture 'client' not found`，七个测试为 create、list、get、update、delete、invalid_title、nonexistent_todo，失败发生在 setup。完整候选指纹 `ac1be2dd388c5e934b565a62b7a5d778c732693af630f96e38196f0aaee9145b`，随后回滚。

repair 2 的 `input_failure` 与 repair 1 的 `result_failure` 完全一致；repair 3 的输入也与上一轮输出一致，source 均为 `core_candidate`。候选诊断在回滚后真实传递到了下一轮。最终完整候选的 pytest 诊断保留在 API 和检查点中，最终磁盘复验仍报告缺失测试文件。

最终 `repair_stop_reason=budget_exhausted`；`success/first_passed/candidate_passed/repaired_passed/files_complete/tests_passed/startup_passed/persistence_passed/plan_consistent/interfaces_consistent=false`，`compile_passed=true`。`evaluation_status=completed` 表示验收执行结束。

磁盘最终文件为 `app/main.py`、`app/models.py`、`app/schemas.py`。响应顶层 `files` 为最后候选的四个文件列表，磁盘实存列表以 `project_files` 和文件完整性复验为准。只读核对最终 main.py，模块包含 APIRouter，未导出模块级 app，与初始/第二轮诊断一致。

本次失败为模型生成的跨文件符号及 pytest fixture 语义错误，按用户要求停止；本次证据未建立需要修复的通用编排缺陷，因此未修改源代码或另开一轮重测。未手改生成项目、安装包、读取 LLM key、提交或推送。本次手工编辑仅追加此报告。

### 检查点路径

- 初始：`data/orchestration_core_checkpoints/ed890b6a-e0aa-4bc9-a904-9ad225d83489-1788852159348709930-spec_first.json`
- repair 1：`data/orchestration_core_checkpoints/9b431b0d-992c-46f5-8960-91b31e529a81-1788852256472998851-incremental.json`
- repair 2：`data/orchestration_core_checkpoints/492bf01d-cbb4-464d-a587-265c781d40ab-1788852324851450007-incremental.json`
- repair 3：`data/orchestration_core_checkpoints/c0969296-f990-4d01-9e15-2bfc1cd6f0cf-1788852415362593594-incremental.json`
