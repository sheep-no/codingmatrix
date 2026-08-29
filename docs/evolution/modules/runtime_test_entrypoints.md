# Runtime Test Entrypoints 演化深扫文档

> 版本：v0.1 | 扫描日期：2026-08-29 | 状态：已完成
> 归属：后端运行时 / 测试入口与运行态验证
> 路径：tests/conftest.py（268 行）、tests/integration/test_health_api.py（92 行）、tests/unit/test_task_queue.py（312 行）、tests/unit/test_bugfixes.py（266 行）、configs/pytest.ini（25 行）、pyproject.toml（49 行）
> 索引：[TASKS.md](../TASKS.md)，第 159 轮

## 1. 模块定位与状态判定

这是一个由 pytest 配置、公共 fixtures、健康 API 集成测试、任务队列单元测试和 Bug 回归测试组成的运行时测试入口集合。它负责为测试提供事件循环、认证、数据库、Selenium 和 API 地址等基础设施，并验证健康端点、Celery 配置/注册、WebSocket 任务更新以及若干历史导入和实现修复。

- **状态：活跃测试入口**。`configs/pytest.ini` 指定 `tests` 为测试根目录（:1-5），`pyproject.toml` 提供 pytest 与 coverage 配置（:18-20、:22-49）；四个目标测试文件均包含可执行测试类或 fixture。
- **覆盖边界：运行态浅覆盖**。测试能确认模块可导入、端点可访问、响应包含部分字段、任务配置常量和若干纯函数结果；worker 实际执行、真实 broker/backend、服务生命周期和完整健康失败语义缺少验证。
- **配置状态：双入口待收敛**。pytest 配置同时出现在 `configs/pytest.ini` 与 `pyproject.toml`。是否使用 `configs/pytest.ini` 取决于运行命令是否显式指定 `-c`；两处配置的标记、插件行为和 addopts 不能默认视为合并结果。

## 2. 测试入口与覆盖功能

### 2.1 公共 fixture 入口

- `tests/conftest.py:19-25` 提供 session 级 `event_loop`，创建新 loop 并在 session 结束关闭。
- `tests/conftest.py:28-31` 提供默认超时值 30 秒。
- `tests/conftest.py:34-95` 提供测试用户 ID、JWT token 和认证请求头；普通用户与超级管理员均固定使用 `sub="1"`。
- `tests/conftest.py:98-113` 提供 API v1/v2 基础地址，默认指向 `http://127.0.0.1:8000`，并允许 `API_BASE_URL` 环境变量覆盖。
- `tests/conftest.py:116-130` 提供数据库 session 和建表/删表 fixture；数据库 schema 生命周期覆盖 create/drop，数据隔离与事务回滚未覆盖。
- `tests/conftest.py:133-172` 注册 Selenium 与 API 地址命令行参数，并提供对应 fixture。
- `tests/conftest.py:175-220` 提供 Chrome/Firefox options 和 WebDriver 生命周期；`driver` 的浏览器分支在 `:205-215`，释放在 `:217-220`。
- `tests/conftest.py:223-268` 提供项目、聊天、文件和用户样例数据。

### 2.2 健康 API 集成入口

`tests/integration/test_health_api.py:18-70` 覆盖 `/api/v1/health`、`ready`、`live`、`detailed`、`metrics`、`models` 六个路径的可访问性。每个测试在 `:23-25` 等位置直接创建 `ASGITransport(app=app)`，通过 `http://test` 调用应用内路由。

- 存活检查要求 HTTP 200 且 `status == "alive"`（:41-48）。
- 基础健康和就绪检查只要求状态码属于 `[200, 500, 503]`，并分别检查 `status/timestamp`（:21-29）及 `status/checks`（:31-39）。
- 详细、指标、模型端点也接受失败状态码（:51-69）。
- 数据库与 Redis 的就绪字段仅在响应已经包含 `checks` 时检查键存在（:84-92），连接成功、连接失败、超时和恢复过程均未断言。

### 2.3 任务队列与 worker 关联入口

`tests/unit/test_task_queue.py` 的覆盖分为四层：

- 优先级与超时解析：`parse_priority` 在 `:12-42` 覆盖大小写、未知值和空值；`parse_timeout` 在 `:44-69` 覆盖默认值、上下限。
- 领域枚举与 Schema：`TaskStatus`、`TaskType`、`TaskPriority` 在 `:71-97` 验证枚举值；`TaskCreateRequest` 与 `TaskResponse` 在 `:99-132` 验证默认字段和响应字段。
- WebSocket 与进度：`WebSocketManager` 在 `:134-221` 覆盖连接、断开、个人消息、任务更新格式和不存在用户；`ProgressCallback` 仅在 `:223-235` 验证初始字段。
- 结果处理与 Celery 声明：`handle_task_result` 在 `:237-264` 覆盖内联/文件存储；Celery app 配置和任务注册在 `:266-286`；三个任务的名称、重试次数和延迟在 `:288-312` 验证。

### 2.4 Bug 回归入口

`tests/unit/test_bugfixes.py` 验证若干历史修复的导入、文件元数据和源码特征：

- `PathSecurityError` 导入与继承关系：:19-37。
- `get_db()` 异步生成器及一次 yield：:39-61。
- `ChunkMetadata` 加载、完整性、去重追加和保存：:63-137。
- 图片生成 `response_format/url` 源码特征：:139-150。
- 流式 keepalive 通过函数存在和源码字符串存在性验证：:152-172。
- 多个 API v1/v2 模块只执行导入检查：:175-264。

## 3. 生命周期覆盖矩阵

| 生命周期 | 当前覆盖 | 证据 | 状态与缺口 |
|---|---|---|---|
| pytest 配置加载 | 测试路径、文件/类/函数命名、asyncio auto、部分 marker、300 秒 timeout | `configs/pytest.ini:1-25` | 有配置，但配置文件来源分裂；实际默认入口需运行确认 |
| 事件循环创建与关闭 | session loop 创建、yield、关闭 | `tests/conftest.py:19-25` | 有基础生命周期；与 `pyproject.toml:18-20` 的 function loop scope 语义未统一验证 |
| async fixture | 数据库 session 使用 async with；数据库表 create/drop | `tests/conftest.py:116-130` | 有资源释放路径；装饰器使用 `pytest.fixture`，严格 asyncio 模式兼容性未验证 |
| HTTP 应用调用 | ASGI transport 创建、AsyncClient 上下文关闭 | `test_health_api.py:21-69` | 覆盖应用内调用；真实监听端口、启动/停止、反向代理链路未覆盖 |
| 健康检查 | live 强断言；其余端点字段和部分状态码 | `test_health_api.py:21-92` | 存活有最低保障；ready 的依赖可用性、失败分类和恢复未闭环 |
| Celery worker | app 导入、配置常量、任务注册 | `test_task_queue.py:266-312` | worker 生命周期为缺口；没有 broker、worker 启停、投递、执行、重试、结果回收 |
| WebSocket | manager 内存连接与消息调用 | `test_task_queue.py:134-221` | 覆盖 manager 单元行为；真实握手、断线重连、多连接和 worker 推送未覆盖 |
| 文件结果清理 | 测试中创建大结果并主动删除临时文件 | `test_task_queue.py:250-264` | 只覆盖写入返回值；异常中断、权限、并发和结果过期清理未覆盖 |
| Bug 回归 | 导入、源码字符串、元数据读写 | `test_bugfixes.py:19-264` | 多数属于静态/冒烟检查；真实请求、异常路径和行为回归不足 |
| 覆盖率门槛 | branch、source、omit、fail_under=70 | `pyproject.toml:2-16、22-42` | 策略已声明；目标入口未提供覆盖率产物或阈值执行证据 |

## 4. 已探明问题与运行缺口

### RT1 [P2] 健康测试允许不健康状态通过

- **现象**：基础健康、就绪、详细、指标和模型测试将 `500/503` 作为合法结果；测试仍可在服务不健康时通过。
- **证据**：`tests/integration/test_health_api.py:26`、`:36`、`:55`、`:62`、`:69` 分别接受失败状态码；字段断言只验证结构（:27-29、:37-39）。
- **根因**：测试目标被定义为“端点存在且返回 JSON”，健康语义与可用性语义尚未分层表达。
- **影响**：CI 可能把数据库、Redis 或模型依赖故障报告为通过；就绪端点无法承担部署门禁。
- **建议**：按依赖可用/不可用拆分测试；健康路径要求 200 与 healthy，ready 故障路径断言明确 503、失败依赖和错误结构，并为 live 保留独立的 200 契约。

### RT2 [P2] worker 生命周期只验证声明，未验证运行链路

- **现象**：任务队列测试验证 Celery app 的序列化、超时、重试配置以及任务对象存在，未投递或执行任何 Celery 任务。
- **证据**：`tests/unit/test_task_queue.py:266-312` 全部为配置、属性和导入断言；文件没有 broker/backend fixture、worker 启停、`.delay/apply_async`、任务结果或 retry 断言。
- **根因**：测试范围停留在进程内单元层，worker、broker、result backend 被视为外部运行条件。
- **影响**：任务注册表与 worker 实际加载不一致、消息序列化、ack、重试和结果状态问题不会被目标测试入口发现；WebSocket 的任务进度链路也无法验证。
- **建议**：增加受控的 worker 集成层，覆盖 broker 可用性、任务投递到成功/失败/重试、结果回收和 worker 停止清理；将外部服务检查标注为可跳过并输出原因。

### RT3 [P2] pytest 配置来源分裂，严格标记未形成稳定契约

- **现象**：`configs/pytest.ini` 声明 `--strict-markers` 并只注册 `api/selenium/slow/security/smoke` 五类标记；`pyproject.toml` 的 pytest 区块只声明 asyncio 设置，未注册 marker，也未复制 addopts。
- **证据**：`configs/pytest.ini:7-22`；`pyproject.toml:18-20`。仓库其他测试使用 `unit`、`database` 等 marker 的事实可由测试目录检索确认，但本次目标文档不修改这些文件。
- **根因**：pytest 配置分散在不同候选配置文件，运行命令是否显式使用 `-c configs/pytest.ini` 会改变 marker 校验、输出和 timeout 行为。
- **影响**：本地、CI、IDE 可能收集到相同测试却拥有不同的严格程度和超时策略；新增 marker 可能在某一入口下告警或失败。
- **建议**：选定单一 pytest 配置源并迁移完整契约，显式注册全项目 marker；在 CI 中固定配置入口，并用 `pytest --showconfig` 记录实际生效配置。

### RT4 [P3] async fixture 装饰器与项目 asyncio 策略耦合

- **现象**：`db_session` 和 `test_db_setup` 是异步生成器，却使用 `@pytest.fixture`；项目同时声明 `asyncio_mode=auto` 和 function 级 fixture loop scope。
- **证据**：`tests/conftest.py:116-130`；`pyproject.toml:18-20`；`configs/pytest.ini:7`。
- **影响**：当前 auto 模式可能掩盖装饰器契约问题；切换为 strict、升级 pytest-asyncio 或从另一配置入口运行时，异步 fixture 可能无法按预期执行。
- **建议**：统一使用 `pytest_asyncio.fixture` 表达异步 fixture 契约，并针对 session/function loop 关系增加一个最小生命周期测试。

### RT5 [P3] 自定义 session event loop 与 pytest-asyncio loop 管理重复

- **现象**：conftest 手工维护 session 级 `event_loop`；pyproject 同时配置 `asyncio_default_fixture_loop_scope="function"`。
- **证据**：`tests/conftest.py:19-25`；`pyproject.toml:18-20`。
- **影响**：fixture、测试函数和资源释放可能落在不同 loop 语义下；数据库引擎、异步客户端等 loop 绑定资源的跨作用域行为没有证据保障。
- **建议**：保留一套 loop 生命周期策略，优先使用 pytest-asyncio 配置管理；需要 session loop 时为明确需要它的 fixture 指定 scope，并测试跨 fixture 的关闭顺序。

### RT6 [P3] Bug 回归测试大量依赖源码字符串和导入成功

- **现象**：图片生成仅检查源码含 `response_format` 或 `url`；keepalive 仅检查源码含字符串；大量 API 模块只验证导入成功。
- **证据**：`tests/unit/test_bugfixes.py:142-150`、`:155-172`、`:175-264`。
- **影响**：代码可能包含目标字符串却未在实际请求路径生效；模块能导入却可能在依赖调用、认证、异常响应时失败，回归测试信号偏弱。
- **建议**：对 response_format 和 keepalive 使用 mock 客户端/流式迭代器验证实际调用与事件序列；对关键导入冒烟测试补充最小行为断言。

## 5. 配置与环境观察

- `configs/pytest.ini:10-15` 设置 verbose、short traceback、strict markers 和禁用 warnings；`pyproject.toml` 未重复这些设置。实际命令若使用 `-c configs/pytest.ini`，覆盖率区块仍需通过 pytest-cov 参数或其他配置启用。
- `configs/pytest.ini:24-25` 的 timeout=300 依赖 pytest-timeout 插件；目标文件没有验证插件是否安装或超时异常是否可观测。
- `tests/conftest.py:98-113` 的 API fixture 默认 8000，但健康测试绕过该 fixture，固定使用 `base_url="http://test"`（:24、:34、:44 等）。健康测试因此不检查 `API_BASE_URL` 或真实 API 监听地址。
- `tests/conftest.py:133-172` 注册了 `--api-base-url`，但 `api_base_url_option` 未被本次目标测试消费；命令行配置与健康测试入口存在断开。
- 数据库 fixture 使用真实项目 `engine/async_session`（:12-14、:116-130），并在测试后执行 `drop_all`；没有证据表明该 engine 已切换到独立测试数据库，运行隔离属于待确认项。

## 6. 修改建议

| # | 优先级 | 修改动作 | 达成目的 | 涉及位置 | 对应 Backlog |
|---|---|---|---|---|---|
| 1 | P2 | 将健康成功、依赖失败、恢复分别建成明确断言，并覆盖数据库/Redis 的 ready 结果 | 让健康测试成为可靠的运行门禁 | `test_health_api.py:21-92` | 待记 |
| 2 | P2 | 增加 Celery worker 集成 fixture 和任务生命周期用例 | 验证投递、执行、重试、结果和清理链路 | `test_task_queue.py:266-312` | 待记 |
| 3 | P2 | 收敛 pytest 配置到一个入口，注册全项目 marker，固定 CI 配置命令 | 消除本地、CI、IDE 的测试语义漂移 | `configs/pytest.ini:1-25`、`pyproject.toml:18-20` | 待记 |
| 4 | P3 | 使用 pytest-asyncio 专用异步 fixture 装饰器并统一 loop scope | 固化异步资源生命周期和插件兼容性 | `conftest.py:19-25、116-130` | 待记 |
| 5 | P3 | 让健康测试消费 `api_base_url`/`api_base_url_option`，或明确其为纯 ASGI 测试 | 区分进程内路由测试与真实服务测试 | `conftest.py:98-113、163-172`、`test_health_api.py:21-69` | 待记 |
| 6 | P3 | 将源码字符串断言改为 mock 行为断言，并为模块导入测试补关键路径 | 提升 Bug 回归测试的故障发现能力 | `test_bugfixes.py:139-264` | 待记 |
| 7 | P3 | 对数据库 fixture 增加测试数据库来源、事务隔离和 cleanup 验证 | 避免测试污染运行时数据库 | `conftest.py:116-130` | 待记 |

## 7. 演化方向关联

- 该入口集合属于验证闭环的运行态边界：健康 API 负责服务可用性信号，Celery 测试负责异步任务声明，公共 fixture 负责资源生命周期，Bug 回归测试负责历史缺陷的最低回归信号。
- 当前主线是“声明存在”向“运行可证”演化：RT1、RT2 和 RT6 分别对应健康结果、worker 执行和修复行为的证据不足。
- 配置演化方向是统一收敛：`configs/pytest.ini` 与 `pyproject.toml` 应形成单一可审计入口，marker、asyncio、timeout、覆盖率策略需要在同一运行契约中呈现。
- 生命周期演化方向是边界明确：ASGI 内存测试、真实 HTTP 服务、Celery worker 和依赖服务应按测试层级拆分，并为每层定义启动、执行、失败和清理证据。
