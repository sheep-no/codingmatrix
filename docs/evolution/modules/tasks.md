# app/tasks 任务队列合扫（第 155 轮 / v1.156）

- 轮次：155（内部编号 v1.156）
- 扫描对象：`app/tasks/`（base.py 189 + code_tasks.py 402 + project_tasks.py 110 = 3 文件 701 行；`__init__.py` 仅导出符号）
- 模块定位：Celery 任务执行层，承接 `app/api/v1/task_queue.py` 的任务提交，并调用 Agent、DockerRunner、测试运行器和 WebSocket 进度通知。

## 三态判定

| 文件 | 判定 | 依据 |
|------|------|------|
| base.py | 活跃 | BaseTask 被 5 个 Celery 任务声明为 base；parse_priority/parse_timeout 被任务 API 消费 |
| code_tasks.py | 活跃 | Celery 注册 generate_code、execute_code、modify_with_test，API 任务映射与全库调用确认 |
| project_tasks.py | 活跃 | Celery 注册 generate_project、validate_project，API 任务映射与全库调用确认 |

3 个文件全部活跃。`celery_app.py:20-23/:153-154` 同时 include 与 autodiscover `app.tasks`，任务注册真实生效；`task_queue.py`、`DockerRunner`、`IsolatedTestRunner` 和 `app/main.py` 构成跨模块消费链。

## P2 发现（6 项）

### TSK1 [P2] BaseTask 缺少 `_get_progress_callback`，全部任务执行即崩

- `code_tasks.py:49/:104/:174` 与 `project_tasks.py:42/:91` 均调用 `self._get_progress_callback(task_id, user_id)`。
- `base.py:44-125` 的 `BaseTask` 没有该方法，`app/tasks/` 全库也没有继承补实现。
- Celery 任务进入实际执行后在首个进度回调创建点抛 `AttributeError`；任务 API 能创建 DB 记录和 Celery 消息，但业务任务无法开始。
- Backlog：#1255

### TSK2 [P2] `execute_code` 将代码片段传给项目验证接口，参数契约确定性错误

- `code_tasks.py:108-116` 调用 `DockerRunner.run_validation(code=code, language=language, timeout=timeout)`。
- `docker_runner.py:763` 的项目验证入口以及 `run_validation` 接口接收 `project_path`、`requirements_path`、`test_command`、`install_deps`、`auto_detect_framework`、`required_services` 等项目参数，不接收 `code`/`language`。
- 该任务即使补上进度回调，也会因关键字参数不匹配失败；代码片段执行能力实际位于 `app/agent/tools.py:_tool_execute_code`，任务层调用了错误执行器。
- Backlog：#1256

### TSK3 [P2] `validate_project` 完全跳过验证并固定返回成功

- `project_tasks.py:95-101` 只实例化 `DockerRunner`、发送进度，然后返回 `{"status": "success", "project_path": project_path}`。
- `runner` 没有调用任何验证方法，`project_path` 不读、不校验、不传入容器；依赖安装与测试进度属于虚假状态。
- 失败项目、空目录和不存在路径均可被任务结果标记为成功，形成项目验证链的成功态谎报。
- Backlog：#1257

### TSK4 [P2] 异步任务内嵌 `asyncio.run` 使隔离测试必然回退到宿主执行

- `modify_with_test` 的 `_execute()` 已运行在 `asyncio.run(_execute())` 创建的事件循环中（`code_tasks.py:249-250`）。
- `_run_tests()` 在该异步上下文内再次调用 `asyncio.run(runner.run_tests(...))`（`:367-369`），必抛 `RuntimeError: asyncio.run() cannot be called from a running event loop`。
- 异常被 `:381-398` 捕获后回退到 `subprocess.run(["pytest", ...], cwd=project_root)`，测试从隔离运行器退化为当前服务源码目录的宿主执行；`enable_security_scan=False` 也使该回退路径失去安全扫描。
- Backlog：#1258

### TSK5 [P2] 任务创建参数与任务签名、任务类型映射不一致

- `task_queue.py:53-57` 只映射 `project_generate`、`code_generate`、`modify_with_test`，但请求契约和 docstring 同时声明 `ppt_generate`、`file_process`，两类请求必定 400。
- `task_queue.py:82-91` 对所有任务统一发送 `requirement`、`prompt`、`language`，没有发送 `code`；`execute_code` 的必填 `code` 参数因此缺失，消息进入 worker 即失败。
- `modify_with_test` 的必填 `requirement` 会收到空字符串默认值，且 `target_files`、`max_retry_loops`、`input_file_id` 等业务参数没有从 `body.params` 透传，任务行为与 API 契约脱节。
- Backlog：#1259

### TSK6 [P2] 重试复用旧任务标识且不保存新 Celery ID，结果链路形成幽灵任务

- `task_queue.py:292-313` 将原记录重置为 pending 后，以同一 `task_record.task_id` 再次发送任务；Celery 结果后端与历史执行共享业务标识，旧结果可能覆盖或混淆新结果。
- `send_task()` 的返回值没有赋回 `task_record.celery_task_id`，API 继续查询旧的 Celery ID；旧任务已失败时，新任务状态、进度和结果无法被正确读取。
- retry 的 `task_map` 还遗漏 `modify_with_test`，该类型会被重置为 pending 却不发送任何新任务。
- Backlog：#1260

## P3 发现（20 项）

### base.py（6 项）

- **TSK7 [P3]** `ProgressCallback.update()` 不校验 progress 范围，任意调用方可发送小于 0 或大于 100 的进度；消息仅发 WebSocket，不写 Task DB，刷新查询与实时通知两套进度来源分裂。
- **TSK8 [P3]** `on_failure` 经 WebSocket 原样发送 `str(exc)`（`:64/:105-107`），内部异常信息可能进入用户通道；同时 Celery signal 侧再次写入错误，错误通知双轨。
- **TSK9 [P3]** `on_retry` 把 Celery 状态写成 `RETRYING`（`:71-77`），DB signal `_sync_notify_retry` 写成小写 `retrying`（`celery_app.py:109-114`），状态大小写语义依赖消费入口。
- **TSK10 [P3]** `handle_task_result()` 仅在结果大于 1MB 时落盘，却固定写 `/tmp/task_results/{task_id}.json`；相同 task_id 会覆盖文件，无过期清理、权限策略和读取 API，临时盘可持续增长。
- **TSK11 [P3]** `handle_task_result()` 对大结果直接执行 `result.get('task_id')` 与 `json.dump(result)`，非 dict 结果会在大结果分支抛 `AttributeError` 或序列化失败；函数全库无生产消费，声明的结果治理能力未接线。
- **TSK12 [P3]** `parse_priority()` 对 None、非字符串和未知值统一落 medium 或直接抛异常；API 当前由 Enum 限制，但 Celery 直接调用与重放消息没有同等输入契约。

### code_tasks.py（8 项）

- **TSK13 [P3]** `modify_with_test` 中 `max_retries=0` 时 `50 + int(40 * retry_count / max_retries)` 除零；配置允许通过 `max_retry_loops` 传入 0。
- **TSK14 [P3]** `_find_affected_files()` 使用 `if target in file_path`（`:269-273`）做反向索引匹配，路径方向反转且无边界；短文件名会误命中，标准完整路径依赖边可能漏报。
- **TSK15 [P3]** `_get_related_tests()` 使用 `pattern.replace('*', '') in target or target in pattern`，通配符仅删除星号，目录边界、扩展名和 glob 语义均不成立；任意匹配还会叠加全局测试。
- **TSK16 [P3]** `_agent_modify()` 与 `_agent_fix_from_test_logs()` 只调用 LLM 并返回文本，不写入目标文件、不生成 patch、不校验修改结果；随后运行的测试验证旧磁盘内容，成功结果无法证明需求已落地。
- **TSK17 [P3]** `modify_with_test` 的守护合约读取 `Path(file_path)`（`:233-238`）不经过用户项目根目录校验，worker 当前目录变化会读错文件；用户可控相对路径具备越界读取可能。
- **TSK18 [P3]** `modify_with_test` 即使修改结果为空、测试列表为空，也因 `test_logs` 为空返回 `success=True`（`:240-247`）；无测试被当作验证通过，复现 TestRunner 的 TR1 家族。
- **TSK19 [P3]** 任务流程只检查 `test_logs` 中所有结果均成功（`:241`），最终修复轮通过但早期失败仍报告失败；返回语义没有区分最终状态与历史尝试状态。
- **TSK20 [P3]** `_run_tests()` 回退命令固定使用宿主 `pytest`，不限制 test file 路径、不限制输出大小；`test_files` 来自 YAML 配置并直接拼接命令参数，测试映射文件成为执行面配置源。

### project_tasks.py（6 项）

- **TSK21 [P3]** `generate_project()` 导入 `async_session`（`:40`）但从未使用，任务函数的数据库会话契约属于残留实现；任务状态与生成结果完全依赖 Celery signal 的旁路同步。
- **TSK22 [P3]** `generate_project()` 只捕获 `SoftTimeLimitExceeded`，普通异常不记录 task_id 上下文后再抛出；与 `code_tasks.py` 的错误处理粒度不一致。
- **TSK23 [P3]** `validate_project()` 导入 `async_session`（`:89`）同样零消费，并以相对/绝对路径原样返回结果；路径归属校验缺失与 DockerRunner 的项目根校验职责重复且未形成闭环。
- **TSK24 [P3]** 两个项目任务把 `kwargs` 透传能力留给调用方，却没有显式声明或校验 `timeout`、`requirements_path`、`test_command` 等关键执行参数；Celery JSON 消息可携带无效配置并静默忽略。
- **TSK25 [P3]** 任务内部 `asyncio.run()` 与 `BaseTask` 回调中的 `asyncio.run()` 形成两套同步桥接；任务执行上下文一旦由异步 worker 或测试直接调用，回调通知会再次触发 running-loop 错误并仅记录日志。
- **TSK26 [P3]** 任务固定 `acks_late=True`，但业务函数没有统一幂等键、状态条件更新或重复执行保护；worker 崩溃重投后，生成、修改、通知和数据库旁路更新可能重复发生。

## 交叉确认

- `celery_app.py:33-39` 全局软/硬时间限制为 270/300 秒；5 个任务自身只声明重试次数与延迟，没有显式 `time_limit`，实际超时策略完全依赖全局配置。
- `task_queue.py` 的状态查询优先读取 `AsyncResult.state`（`:137-150`），而 `celery_app.py` 的 signal 另写 `app.models.task.Task.status`；Celery 后端、DB signal、任务回调三套状态来源并存。
- `app/tasks/__init__.py` 仅导出 BaseTask 和解析辅助函数，没有导出具体 Celery 任务；实际注册依赖 `celery_app.py` 的 include/autodiscover。
- 既有 `docker_runner.md` 已记录 TSK2/TSK3 的初步发现，本轮完成任务层独立定位并补全其与 API 参数、状态和测试链的影响面；家族归并不重复计数。

## 建议顺序

1. 先实现或统一进度回调工厂，修复 TSK1 后再验证其他任务真实运行。
2. 拆分「代码片段执行」与「项目验证」接口，分别修复 TSK2、TSK3、TSK5。
3. 将 `_run_tests` 改为异步调用或在线程中运行，并移除不受控宿主回退，处理 TSK4。
4. 重试生成新 Celery ID，保存映射并为任务执行增加幂等约束，处理 TSK6。
