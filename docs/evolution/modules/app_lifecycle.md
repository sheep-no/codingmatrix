# app_lifecycle.py 应用生命周期与运行时接线演化深扫文档

> 版本：v0.1 | 扫描日期：2026-08-29 | 状态：已完成
> 归属：应用基础设施层 / 生命周期、健康探针与异步任务接线
> 路径：`app/main.py`（367 行）+ `app/celery_app.py`（154 行）+ `app/api/v1/health.py`（196 行）
> 索引：[TASKS.md](../TASKS.md)，第 156 轮

## 1. 模块定位与状态判定

本档案覆盖 API 进程的启动/关闭编排、健康检查 HTTP 入口、Celery 应用与信号接线，以及 APScheduler 和数据库初始化的连接关系。三份目标文件均属于活跃运行面：`main.py` 创建 FastAPI 应用并挂载健康路由，`health.py` 提供探针和运营观测入口，`celery_app.py` 被任务 API、Celery 任务和健康/关闭逻辑导入。

| 组件 | 状态 | 生产消费方与证据 |
|------|------|------------------|
| `main.py` 的 `lifespan` 与启动链 | 活跃但生命周期接线断裂 | `app = FastAPI(lifespan=lifespan)`（`main.py:103-166`）；迁移、调度、供应商恢复仍挂在 `on_startup`（`main.py:274-296`） |
| `health.py` 健康路由 | 活跃 | `main.py:56` 导入，`main.py:331-332` 以 `/api/v1` 前缀挂载；集成测试覆盖 `tests/integration/test_health_api.py:22-92` |
| `celery_app.py` | 活跃 | `task_queue.py:21` 调用 `send_task/AsyncResult/control.revoke`；`project_tasks.py`、`code_tasks.py` 注册任务；`health_checker.py:127-161` 和 `graceful_shutdown.py:199-202` 观测/关闭 |
| `app/db/scheduler.py` | 活跃接线目标，当前启动受生命周期断接影响 | `main.py:86` 导入、`main.py:285-290` 计划启动；模块级注册四个周期任务（`scheduler.py:155-194`） |
| `migrations/runner.py` | 活跃接线目标，当前启动受生命周期断接影响 | `main.py:47` 导入，`main.py:279-284` 计划执行 `run_async_migrations()` |

### 对外接口

- 健康接口：`GET /api/v1/health`（`health.py:30-57`）、`/ready`（`:60-85`）、`/live`（`:88-98`）、`/detailed`（`:131-139`）、`/metrics`（`:141-171`）、`/models`（`:174-196`）。
- 应用生命周期：FastAPI `lifespan`（`main.py:103-144`）。
- Celery 应用：模块级 `celery_app`（`celery_app.py:16-24`），由任务 API发送任务并查询/撤销任务。

## 2. 依赖与被依赖

- `main.py` 依赖 FastAPI/Starlette、SQLAlchemy、Alembic runner、数据库会话、缓存、限流、Guardian、关闭管理器、路由模块和 APScheduler 的启动包装。
- `lifespan` 当前执行：信号处理器、上传目录创建、限流初始化、缓存初始化、数据库连接池预热、Guardian 启动；退出时执行 Guardian、关闭管理器、HTTP 客户端和缓存关闭（`main.py:105-143`）。
- `health.py` 的基础/就绪检查直接执行数据库 `SELECT 1`（`health.py:101-111`），Redis 配置存在时执行写读验证（`:114-128`）；详细检查转发到 `HealthChecker.check_all()`（`:131-139`）。
- `celery_app.py` 使用 `REDIS_URL` 同时作为 broker/backend，默认值为 `redis://localhost:6379/0`（`:14-24`），固定发现 `app.tasks`，并在导入时注册信号与执行 autodiscover（`:119-154`）。
- 任务 API 的核心发送链为：写入 `Task` 数据库记录（`task_queue.py:66-80`）→ `celery_app.send_task()`（`:82-91`）→ 回写 Celery ID（`:93-95`）。状态查询读取 Celery `AsyncResult`（`:137-150`），取消调用同步 `control.revoke`（`:253-258`）。
- 测试：健康接口集成测试仅断言端点可访问和宽泛状态码（`tests/integration/test_health_api.py:22-92`）；Celery 配置/任务注册测试位于 `tests/unit/test_task_queue.py:269-312`。未发现覆盖完整生命周期、迁移启动、调度启动或信号状态回写的测试。

## 3. 已探明问题

### P2

#### AL1 [P2] `lifespan` 与 `on_event("startup")` 并存，迁移/调度/恢复启动链被绕过

- **现象**：应用实例显式传入 `lifespan=lifespan`（`main.py:103-166`），数据库迁移、APScheduler 启动和用户供应商恢复却只定义在 `@app.on_event("startup")`（`:273-296`）。按 FastAPI 的 lifespan 语义，提供 lifespan 时 startup/shutdown 事件处理器不参与该应用生命周期，因此三项启动动作无法从当前入口得到执行。
- **证据代码**：

```python
# app/main.py:103-131
@asynccontextmanager
async def lifespan(App: FastAPI):
    ...
    await _warm_up_database_pool()
    ...
    yield

# app/main.py:166
app = FastAPI(lifespan=lifespan, ...)

# app/main.py:274-296
@app.on_event("startup")
async def on_startup():
    await run_async_migrations()
    start_scheduler()
    await _restore_user_providers()
```

- **影响**：新环境不会经过 `run_async_migrations()`；四个定时任务不会启动；Redis 中已有用户供应商模型不会恢复。应用进程仍可完成部分 API 初始化，造成“服务已启动、后台能力未接线”的运行时分裂。
- **修复建议**：把迁移、调度和供应商恢复纳入同一个 `lifespan` 启动阶段，并为失败策略、启动顺序和退出清理建立明确契约；移除重复事件注册后补生命周期测试。

#### AL2 [P2] 就绪探针未纳入 Celery，任务服务故障时仍可能返回 ready

- **现象**：`/api/v1/health/ready` 只调用 `_check_db_quick()` 与 `_check_redis_quick()`（`health.py:68-85`）。Celery 检查只存在于详细检查链 `health_checker.check_all()`（`health.py:131-139`；`health_checker.py:123-162`），因此 broker 可用但 worker 全部离线时，ready 仍可返回 `{"status": "ready"}`。
- **影响**：负载均衡或编排系统继续把具备任务提交能力的流量送入一个无法消费任务的 API；异步任务会停留在 pending，探针状态无法表达关键消费端故障。
- **修复建议**：定义探针分层契约：基础存活保持进程级，ready 至少验证必需的任务消费能力；为 Celery 检查设置有限超时并区分 broker 可达、worker 存活和队列积压。

### P3

#### AL3 [P3] 健康检查链路把同步 Celery RPC 放进异步请求

- `HealthChecker.check_celery()` 在 async 函数内直接调用同步 `inspect.stats()` 和 `inspect.active()`（`health_checker.py:123-138`），而 `check_all()` 串行执行六类检查（`:230-275`）。`/detailed` 直接暴露该链路（`health.py:131-139`），Redis/Celery 抖动时会阻塞事件循环并叠加探针延迟。
- 修复方向：为同步 inspect 设置明确超时并使用 `asyncio.to_thread()`，或采用异步客户端；独立检查可用 `asyncio.gather()` 并保留单项结果。

#### AL4 [P3] Celery broker/backend 配置与 API 缓存配置缺少统一来源

- `celery_app.py:14` 对 `REDIS_URL` 使用 localhost 默认值；`main.py:114-120` 在未设置该变量时改用缓存管理器默认后端；`health.py:117-120` 在未设置时直接把 Redis 检查视为通过。三个运行面因此可能分别落到 Celery localhost、内存缓存和“跳过 Redis”语义。
- 修复方向：由统一 settings 提供 broker、backend、cache 和探针启用状态；启动时输出非敏感的后端类型；让未配置 Redis 的部署明确标记 Celery 是否可用。

#### AL5 [P3] 任务提交的数据库记录与 Celery 发送缺少失败补偿

- `task_queue.py:78-80` 先提交 pending 记录，`:82-91` 再同步发送 Celery 任务；发送异常会遗留没有 `celery_task_id` 的 pending 记录。重试路径 `:302-315` 也只有在已有 `celery_task_id` 时才发送，无法修复此类记录。
- 修复方向：采用 outbox/可靠发送状态，或在发送失败时原子记录失败状态与可重试原因；补充 broker 不可用和数据库提交失败的组合测试。

#### AL6 [P3] 异步 API 内直接执行同步 Celery 控制调用

- `task_queue.py:82` 的 `send_task()`、`:140` 的 `AsyncResult` 状态读取、`:254` 的 `control.revoke()` 都位于 async 路由中；Celery broker/backend/control 调用可能发生网络等待，造成事件循环阻塞。
- 修复方向：集中封装任务网关并将同步调用移到线程池，统一超时、错误和状态映射；保持数据库状态与 Celery 状态的单向更新约定。

#### AL7 [P3] 调度器只定义启动，没有对应关闭与多 worker 领导者接线

- `scheduler.py:16` 创建进程内 `AsyncIOScheduler`，`:155-194` 在导入时注册四个 job，`main.py:287` 仅调用 `start_scheduler()`。没有看到 `scheduler.shutdown()`、启动幂等保护或跨 worker 锁；多 worker 时每个进程都可能拥有一份调度器并重复执行任务。
- 修复方向：将 scheduler 生命周期与 `lifespan` 成对管理，增加幂等启动和关闭；生产多 worker 采用独立 scheduler 进程或数据库/Redis leader lock。该项与 `docs/evolution/modules/db_layer.md` 的 DB2 交叉确认一致。

#### AL8 [P3] “迁移 runner”实际是缺表创建，不执行 Alembic 版本迁移

- `main.py:46-47` 将 `run_async_migrations` 描述为 Alembic 迁移入口，`migrations/runner.py:27-60` 实际读取 `Base.metadata.tables` 并对缺失表执行 `CreateTable`；代码没有 Alembic command、版本表或 revision upgrade 调用。
- 修复方向：选择并统一一种 schema 变更机制。生产演化应由 Alembic revision 执行；若保留 runner，应改名为 bootstrap/create-missing-tables 并明确其只能覆盖缺失表，避免把列变更、索引变更误认为已迁移。

#### AL9 [P3] 健康路由存在重复检查实现，版本与状态语义可能漂移

- `health.py:30-85` 自己实现基础/就绪检查；`HealthChecker` 同时实现 `check_all/check_ready/check_live`（`health_checker.py:230-333`），但路由仅把详细检查接到服务层，基础/就绪未复用服务层结果。基础检查将未配置 Redis 视为成功（`health.py:117-120`），服务层将其标记为 `skipped`（`health_checker.py:93-99`）。
- 修复方向：收敛为一个健康检查服务和明确的 probe policy，路由只负责 HTTP 映射；统一版本来源、时间格式和 skipped/degraded/ready 判定。

## 4. 交叉确认与测试缺口

| 主题 | 结论 | 证据 |
|------|------|------|
| lifespan 与 startup 语义 | 同一 FastAPI 应用同时存在两套生命周期入口，关键启动动作在 `on_startup` | `main.py:103-166`, `:273-296` |
| 健康路由挂载 | 实际前缀为 `/api/v1/health` | `main.py:331-332`, `health.py:25` |
| Celery 生产消费 | 任务创建、查询、取消均从 `task_queue.py` 进入；任务实现来自 `project_tasks/code_tasks` | `task_queue.py:21`, `:53-95`, `:137-150`, `:253-258` |
| 调度任务 | 四个 job 在模块导入时注册，启动函数只调用 `scheduler.start()` | `scheduler.py:155-200` |
| 迁移实现 | runner 逐表 `CreateTable`，未见 Alembic upgrade | `runner.py:27-60` |

现有测试验证了健康端点可访问和 Celery 配置/任务符号存在。测试没有验证 ASGI lifespan 是否执行迁移、调度、供应商恢复，也没有验证 Celery worker 缺失时 ready 状态、同步 RPC 超时、任务发送失败补偿、scheduler 关闭和多 worker 去重。

## 5. 演化建议

| # | 优先级 | 修改动作 | 达成目的 | 涉及位置 |
|---|--------|---------|---------|---------|
| 1 | P2 | 统一 `lifespan` 启动/关闭编排，迁移、调度、供应商恢复纳入同一生命周期 | 让数据库与后台能力真实随 API 启停，消除双轨生命周期 | `main.py:103-144`, `:274-296` |
| 2 | P2 | 明确 `/live`、`/ready`、`/detailed` 的依赖层级并纳入 Celery worker 状态 | 让编排探针准确反映任务消费能力 | `health.py:60-85`, `health_checker.py:123-162` |
| 3 | P3 | 建立统一运行时配置和异步任务网关，隔离同步 Celery RPC | 收敛 Redis 配置，避免网络调用阻塞事件循环 | `celery_app.py:14-54`, `task_queue.py:82-95`, `:137-150`, `:253-258` |
| 4 | P3 | 为 scheduler 增加成对关闭、幂等和 leader 选举/独立进程策略 | 消除重复调度与关闭泄漏 | `app/db/scheduler.py:16-200` |
| 5 | P3 | 将缺表创建 runner 与真正的 Alembic migration contract 分开 | 防止 schema 变更被静默遗漏 | `migrations/runner.py:27-60`, `main.py:279-284` |
| 6 | P3 | 收敛 health.py 与 HealthChecker 的重复实现并补生命周期集成测试 | 统一探针语义，覆盖启动、关闭和依赖故障 | `health.py:30-139`, `health_checker.py:230-333` |

## 6. 演化方向关联

- **拆分解耦**：把 API 进程生命周期、健康策略、Celery 网关、scheduler runner、schema migration 分成边界清晰的运行时组件。
- **统一收敛**：统一 Redis/数据库配置来源、健康状态枚举、任务状态映射和 startup/shutdown 入口，消除 `health.py` 与 `HealthChecker` 的重复语义。
- **平台化**：为健康探针提供依赖分级，为 scheduler 提供 leader 机制，为 Celery 提供可靠投递和可观测状态闭环。
- **接线优先级**：先修复 AL1 的 lifespan 断接，再处理 AL2 的 ready 契约；随后完成 AL3-AL9 的运行时一致性和测试补强。当前建议以“生命周期单入口 + 依赖分级探针 + 可补偿任务投递”作为下一轮演化主线。
