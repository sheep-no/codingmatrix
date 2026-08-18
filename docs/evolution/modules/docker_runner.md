# docker_runner.py 演化深扫文档

> 版本：v0.1 | 扫描日期：2026-08-17 | 状态：已完成
> 归属：Agent 引擎 / 测试执行链（Docker 容器化验证侧）
> 路径：`app/utils/docker_runner.py`（802 行）
> 索引：[TASKS.md](../TASKS.md)

## 1. 模块定位

Docker 容器化运行管理器，提供「安全隔离的项目验证环境」。声明安全特性：文件系统隔离（只读根文件系统）、网络隔离（默认 none）、资源限制（CPU/内存/进程数）、提权防护（no-new-privileges）、能力限制（cap_drop ALL）、自动清理（remove=True）。

三个生产使用方：
- `orchestrator_testing.py:211-306` `_run_tests_in_docker`——生成流程测试执行主路径的 docker 分支（docker 优先、fallback 本地 TestRunner）
- `code_tasks.py:87-129` `execute_code`（Celery 任务）——执行用户代码段
- `project_tasks.py:74-95` `validate_project`（Celery 任务）——项目验证

## 2. 依赖链与消费方

```
orchestrator_testing._run_tests_in_docker
  └─ DockerRunner(config, timeout=120).run_validation(project_path, requirements_path, test_command, install_deps, auto_detect_framework, required_services)
       ├─ FrameworkDetector().detect → test_command/docker_image（框架检测）
       ├─ ServiceContainerManager.start_service_containers（依赖服务容器）
       ├─ _scan_code_security（FORBIDDEN_PATTERNS 逐行扫描）
       ├─ container.exec_run(test_command)（_exec_command）
       └─ finally: _cleanup_container + service cleanup
code_tasks.execute_code → DockerRunner().run_validation(code=, language=) ✗ 签名不符
project_tasks.validate_project → DockerRunner() 构造后从不使用，固定返回 success
```

- 消费外部：`FrameworkDetector`（框架检测）、`OutputParser`（调用方侧解析）、`test_framework_config.FRAMEWORK_PRESETS`、`service_container_manager`（依赖服务）
- 依赖 docker SDK（`DOCKER_AVAILABLE` 标志，未装则 `__init__` raise RuntimeError）

## 3. 发现

### DR1 [P2] `read_only=True` 与 `pip install` 冲突——依赖安装路径恒失败（静态可证）

- **Bug 代码**：DockerSecurityConfig.read_only=True（:63）挂只读根文件系统；tmpfs 仅 `/tmp` 与 `/app`（:64-67）；:531-536 `pip install -r requirements.txt` 写入 `/usr/local/lib/python3.11/site-packages`（python:3.11-slim 的 site-packages 在根 FS 下）。
- **根因**：read_only 锁根 FS，site-packages 不在 tmpfs 内 → pip 写包被内核拒绝 → `EnvironmentError`。
- **影响**：docker 验证容器内依赖安装必失败——python:3.11-slim 未预装 pytest/fastapi 等，测试命令（pytest/npm/go test）必然找不到依赖。**除非镜像已预装全部依赖，否则依赖安装路径恒失败**；OR 依赖安装失败时 :540-545 直接 return「依赖安装失败」——docker 分支要么因缺依赖失败、要么永不安装（无 requirements.txt 走 DR4）。

### DR2 [P2] 安全扫描只告警不阻断（全库确认）

- **Bug 代码**：:477 `security_warnings = self._scan_code_security(project_path)`，:478 仅 `result.logs.extend(security_warnings)`，**从不检查非空即终止**——检测到 `os.system`/`subprocess.run`/`eval`/`__import__`/`open('/etc/` 危险模式后仍继续创建容器运行测试。
- **根因**：FORBIDDEN_PATTERNS 声明「禁止的危险命令模式」（:106-117）但扫描结果零决策权——安全门禁「只记录不阻断」（DGV1 放行家族；容器安全实际只靠 cap_drop=ALL + read_only 兜底，业务代码级危险模式从未拦截）。

### DR3 [P2] `run_validation` 无实际超时机制（全库确认）

- **Bug 代码**：`self.timeout`（默认 300）仅在 `except asyncio.TimeoutError`（:563）被引用，但整个 run_validation 全程**无 `asyncio.wait_for`/`asyncio.timeout` 包裹**任何操作——`container.start`/`exec_run` 均走 `asyncio.to_thread` 且不传超时。
- **根因**：except asyncio.TimeoutError 是**不可达死分支**（除非调用方外部包裹）；测试死循环/挂起进程（如 sleep 无限）永不超时，容器长期占用（pids_limit/nofile 之外无时间约束）。

### DR4 [P2] 依赖安装只认 requirements.txt（TFC1 docker 侧确认）

- **Bug 代码**：:531 `if install_deps and requirements_path and requirements_path.exists():` → 只 `pip install -r requirements.txt`。
- **根因/影响**：npm/go/maven 项目无 requirements.txt → 依赖安装被跳过；framework_detector 已检测到 test_command=`npm test` 等（:490-492）但依赖从未安装——容器内测试必失败。**TFC1 详档「setup_commands 全库零消费」在 docker 执行端的精确落点**：test_framework_config 的 npm install/mvn 等 setup_commands 本应在此消费但从未接线。

### DR5 [P2] `__init__` 同步阻塞 + 资源配置异步加载竞态（全库确认）

- **Bug 代码**：:288-290 `__init__` 同步执行 `_init_docker_client`（docker.from_env + ping）+ `_pull_image`（images.get / images.pull 网络拉镜像）+ `_load_resource_config`。
- **根因**：
  1. **同步网络 I/O 阻塞事件循环**——每次实例化 DockerRunner 都在 async 服务器线程同步 pull 大镜像（python:3.11-slim/node 镜像数百 MB），`asyncio.to_thread` 未用于这两步；
  2. **配置加载与容器创建竞态**——`_load_resource_config`（:312-322）在 async 上下文 `create_task(self._load_resource_config_async())` 后立即返回，run_validation 紧接着读 `self.config.mem_limit/image` 创建容器——DB 配置（docker_max_memory/docker_image）可能未生效容器已创建；纯同步上下文调用则 :316 `get_running_loop()` 抛 RuntimeError 被 :321-322 吞 → 配置加载完全跳过（mem_reservation 动态属性 :302 永不设置）。
- **影响**：资源配置时灵时不灵 + 事件循环被镜像拉取阻塞（TR5 同步阻塞家族）。

### DR6 [P2] `execute_code` 任务接线即崩（跨模块确认，DG1 同类）

- **Bug 代码**：`code_tasks.py:112-114` `await runner.run_validation(code=code, language=language, timeout=timeout)`——**DockerRunner.run_validation 签名是 `(project_path, requirements_path, test_command, install_deps, auto_detect_framework, required_services)`，无 code/language 参数**。
- **根因**：code_tasks 期望的是旧版/另一实现 API，从未随 docker_runner 签名演化；且 `DockerRunner()` 构造在 Docker 库未装时 raise RuntimeError（:275-276）而 `_execute` 无 try 包裹。
- **影响**：execute_code（Celery 任务，@celery_app.task 注册）被调用即 TypeError——「接线即崩」家族（DG1/SCT1 同类：签名契约未对齐即上生产路径）。

### DR7 [P2] `validate_project` 任务谎报成功（跨模块确认，TR1/MAR8 家族）

- **Bug 代码**：`project_tasks.py:88-95` `_execute` 构造 `runner = DockerRunner()` 后**从不调用任何验证方法**，仅 progress_cb.update 后 `return {"status": "success", "project_path": project_path}`。
- **根因/影响**：validate_project 任务是 task_queue.py:54 注册的 `project_generate` 配套验证任务，宣称「验证环境/安装依赖/运行测试」（progress_cb 文案 :93/:95）但实际零验证——**无论项目是否可运行都报告成功**（TR1「无测试=通过」的跨模块镜像 + MAR8 成功态谎报家族；runner 变量为死对象）。

### DR8 [P3] 容器内 `/app` 是 bind mount 到宿主 project_path（rw）——测试写文件回写宿主

- **Bug 代码**：:619-624 `volumes: {str(project_path.resolve()): {"bind": "/app", "mode": "rw"}}`——read_only 只锁根 FS，**/app 是读写 bind mount**。
- **影响**：测试期间项目代码写文件（sqlite 库、上传文件、日志）直接回写宿主项目目录（TR2「非 Python 项目原目录执行」的容器化镜像——docker 分支同样无隔离）；测试污染宿主输出目录。

### DR9 [P3] ALLOWED_PACKAGES 死数据 + 三份独立副本（全库确认）

- **Bug 代码**：:119-259 定义 ~200 项 ALLOWED_PACKAGES，**本模块全文件零消费**（rg 确认仅定义处）——pip install 从不经白名单过滤（:531-536 直接 `-r requirements.txt`）；且 `'shutil'/'subprocess'/'multiprocessing'/'tempfile'/'unittest'` 等**标准库被列进 pip 包名单**（pip install shutil 会失败）。
- **双份配置家族**：ALLOWED_PACKAGES 三份独立副本——docker_runner.py:121 / AiProjectCode.py:235 / project_config.py:3→helpers.py:24，升级即漂移。

### DR10 [P3] FORBIDDEN_PATTERNS 三份独立副本（全库确认）

- **Bug 代码**：:107（本模块）与 test_runner.py:34、guardrails.py:187 各一份 FORBIDDEN_PATTERNS——同一概念三处手工复制，模式集可能已漂移（test_runner.py:10-11 注释自称「与 DockerRunner 一致」「合并 DockerRunner 白名单」但无机制保证）。
- **影响**：安全规则无单一来源（SCT6 双份配置家族；升级即漂移）。

### DR11 [P3] orchestrator_testing 调 `docker_runner.cleanup()` 方法不存在（全库确认）

- **Bug 代码**：orchestrator_testing.py:254 `await docker_runner.cleanup()`——docker_runner.py 全文**无 cleanup 方法**（方法清单：__init__/_load_resource_config*/get_max_containers/can_run_container/_get_running_container_count/_init_docker_client/_pull_image/_scan_code_security/run_validation/_prepare_container_config/_exec_command/_cleanup_container/get_container_stats），:253-256 `except Exception: logger.debug` 吞掉 AttributeError。
- **影响**：容器实际已由 run_validation 的 finally（:581-589 _cleanup_container）清理，此调用为死调用——但静默吞掩盖了「调用方契约的 cleanup 从未实现」这一事实（若未来容器泄漏需要 cleanup，此路径已瘫痪且无感知）。

### DR12 [P3] `_scan_code_security` 正则扫描缺陷（TR5 同族）

- **Bug 代码**：:408-419 逐行 re.search——:410 只跳过**整行以 # 开头**，行内尾注释（`code  # subprocess...`）仍命中；字符串字面量内 `"eval("`/`"subprocess.run("` 误报（非 AST 解析）；`open\s*\(["\']\/etc\/` 只匹配字面量字符串，`open('/etc/x')` 用变量拼接即漏检。

### DR13 [P3] 并发与输出小缺陷（MCP1/TR5 家族）

- `can_run_container`/`_get_running_container_count`（:333-352）：查询容器数无锁，并发启动两请求同时通过 → 超限（MCP1 家族）
- `_exec_command`（:699-711）：stdout/stderr **全量收集进内存**再返回（大测试输出数 MB），:701-705 的「只记录前 10 行」只影响 logger 不影响 result 大小（TR5 无界收集家族）
- `_prepare_container_config` :608 `mem_reservation` 用 getattr fallback "256m"——DockerSecurityConfig dataclass 无此字段，仅 `_load_resource_config_async` 动态添加（dataclass 字段漂移）

## 4. 演化方向

docker_runner 的声明能力（安全隔离验证）与真实行为存在系统性偏差：
- **安全三条线全空转**：read_only 与 pip install 冲突（DR1）→ 依赖安装必失败；FORBIDDEN_PATTERNS 只告警不阻断（DR2）→ 危险模式照跑；超时机制缺失（DR3）→ 死循环永挂。**「存在≠正确」在容器化验证执行端的集中体现**（UT5 沙箱恒通过的镜像场景——bwrap 缺失恒通过 / docker 路径依赖安装恒失败，两条验证执行端都不可信）。
- **修复优先级**：
  1. DR1 最优先——read_only 时 pip install 需挂 volume/tmpfs 到 site-packages，或改用 `pip install --target /app/deps`（/app 是 tmpfs）+ PYTHONPATH 注入；DR3 加 `asyncio.wait_for` 包裹 exec_run（timeout 参数真正生效）
  2. DR2 补「警告即阻断」决策（或明确扫描仅审计性质）；DR4 接 test_framework_config.setup_commands 按框架执行（TFC1 修复的 docker 侧落点）
  3. DR6/DR7 修 code_tasks/project_tasks 的签名错配与谎报——execute_code 接对 run_validation 签名、validate_project 真正调用验证
  4. DR9/DR10 收敛三份白名单/黑名单为单一来源（与 TFC/SCT6 双份配置主线统一修复）

## 5. 主线关联

- **「存在≠正确」执行端**：UT5（bwrap 缺失恒 True）↔ DR1/DR3/DR4（docker 依赖安装恒失败/无超时/只认 requirements）——两条验证执行端都不产生可信验证结果
- **成功态谎报**：DR7（validate_project 固定 success）加入 TR1/UT5/MAR8/EC3 家族——「验证任务」在 docker 侧从不验证
- **双份配置**：DR9/DR10（ALLOWED_PACKAGES/FORBIDDEN_PATTERNS 各三副本）加入 SCT6/DR3 家族
- **接线即崩**：DR6（code_tasks 签名不符）加入 DG1/SCT1 家族
- **同步阻塞**：DR5（pull 镜像阻塞事件循环）加入 TR5 家族
- **测试执行链闭环**：TFC1（setup_commands 零消费）→ DR4（docker 侧只认 requirements.txt）是同一缺陷在「配置定义端」与「执行端」的两处表现；DR2 与 test_runner.py:722 的 FORBIDDEN_PATTERNS 扫描（同样只记录）行为一致——安全扫描在两条执行路径都「只告警不阻断」

## 6. 测试状态

- **零单元测试**：tests/ 下无任何 DockerRunner/run_validation/_scan_code_security 引用（docker 依赖使单测需 mock，但 DR1/DR2/DR3 均可静态断言）
- DR1-DR7 七个 P2 项全部全库/静态确认，零用例保护
- code_tasks/project_tasks 两个 Celery 任务（DR6/DR7）同样零测试——「接线即崩」与「谎报成功」均未被测试拦截
