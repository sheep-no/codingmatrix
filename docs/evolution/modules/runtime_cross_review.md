# 启动链交叉终审（第 156-159 轮范围）

## 1. 审查范围与证据口径

本次审查只读核对当前仓库中的 `app/main.py`、`scripts/`、`Dockerfile`、两个 Compose 文件，以及 `docs/evolution/modules/tasks.md`、`db_layer.md`、`middleware.md`、`services.md`。终审结果已登记为第 160 轮；`tasks.md` 标题写作“第 155 轮 / v1.156”（`tasks.md:1-4`），轮次编号与版本号保持原有历史口径。因此本文以当前代码和配置的行号为最终证据，使用既有文档结论作为待复核输入。

审查主链如下：

```text
启动入口
  -> Dockerfile / docker-compose / scripts
  -> Nginx 80
  -> API 8080
  -> app.main 导入与 FastAPI 构造
  -> lifespan / startup
  -> 迁移、调度器、Redis、健康检查
  -> Celery 任务与状态链
```

## 2. 交叉链路结论

| 链路节点 | 当前事实 | 证据 | 终审结论 |
|---|---|---|---|
| 真实 Python 入口 | 应用对象为 `app`，定义于 `app/main.py`；FastAPI 文档挂载为 `/api/docs`、`/api/redoc`、`/api/openapi.json` | `app/main.py:166` | 入口定位明确 |
| 生产容器 API | Dockerfile 使用 `uvicorn app.main:app --host 0.0.0.0 --port 8080 --workers 2` | `Dockerfile:90-91` | 与 DB2 的多 worker 结论一致 |
| 宿主脚本 API | `start.sh` 使用 Gunicorn 2 worker 监听 `0.0.0.0:8080`；`dev.sh` 和 `start-backend.sh` 使用 Uvicorn 8000 | `scripts/start.sh:80-100`、`scripts/dev.sh:20-22`、`scripts/start-backend.sh:5-8` | 启动方式存在三套端口/进程语义，文档必须按场景区分 |
| Nginx 容器到 API | Compose 中 Nginx 与 API 分属不同容器；Nginx 配置 upstream 固定为 `127.0.0.1:8080` | `docker-compose.yml:70-83`、`docker-compose.prod.yml:79-92`、`configs/nginx.conf:80-84` | **确认 P1：容器间代理目标错误，Nginx 回连自身** |
| API 健康检查 | FastAPI 明确注册 `/api/v1/health`；`/health` 未注册为 API 路由，根捕获路由会把非 API 路径返回前端 `index.html` | `app/main.py:304-332`、`app/main.py:345-365`、`app/api/v1/health.py:25-31` | **确认 P2：Dockerfile、生产 Compose、Nginx 和生产文档把 `/health` 当 API 健康端点，实际可能以 SPA 200 掩盖 API 不健康** |
| Nginx 健康检查 | Nginx `/health` 代理到自身配置的 API upstream | `configs/nginx.conf:121-125` | 与 upstream 错误叠加，Nginx 健康状态不能证明 API 可达 |
| 容器文件路径 | Dockerfile 工作目录为 `/app`，运行时目录与依赖复制均在 `/app`；普通 Compose API volume 却挂载到 `/workspace/app`、`/workspace/logs`、`/workspace/data` | `Dockerfile:25`、`Dockerfile:41`、`Dockerfile:54-61`、`docker-compose.yml:23-26` | **确认 P2：普通 Compose 的源码/日志/数据挂载与运行目录分裂** |
| 前端构建产物 | Dockerfile 将 dist 放到 `/app/src/dist`，随后创建 `/workspace/src/dist` 并建立软链接；普通 Compose Nginx 只挂载宿主 `./src/dist` | `Dockerfile:60-73`、`docker-compose.yml:77-80` | 镜像内路径可用性取决于软链接和挂载组合，Compose API 与 Nginx 使用两套文件视图 |
| Nginx 运行权限 | 镜像切换 `USER appuser` 后执行 `nginx & ...`；Nginx 配置要求 `user root`、监听 80、写 `/var/run/nginx.pid` | `Dockerfile:43-48`、`Dockerfile:75-88`、`Dockerfile:90-91`、`configs/nginx.conf:6-16`、`configs/nginx.conf:86-89` | **确认 P1：非 root 容器启动 Nginx 的绑定 80、PID 和日志权限链未闭合** |
| 数据库启动 | `on_startup` 执行自定义 `run_async_migrations()`；lifespan 中 `_warm_up_database_pool()`，另有未调用的 `create_tables()` | `app/main.py:123-124`、`app/main.py:236-240`、`app/main.py:273-290`、`migrations/runner.py:27-62` | 自定义表创建与预热均接线；`create_all` 当前为死函数，DB12 中“同一次启动两条建表路径并行生效”的表述需要收窄 |
| 调度器启动 | `start_scheduler()` 位于 startup 钩子，每个 worker 各执行一次；调度器是模块级 `AsyncIOScheduler` | `app/main.py:273-290`、`app/db/scheduler.py:16`、`app/db/scheduler.py:155-200` | **确认 P2：DB2 多 worker 双跑成立**；`max_instances=1` 只限制单进程内实例 |
| Redis 启动 | Compose API 依赖 Redis，但普通 Compose 仅声明启动顺序；生产 Compose 使用 Redis `service_healthy` 条件 | `docker-compose.yml:16-30`、`docker-compose.prod.yml:17-30`、`docker-compose.prod.yml:61-66` | 生产依赖闭环较完整，普通 Compose 的就绪保障较弱 |
| Celery 启动 | `start.sh` 启动 Celery；普通 Compose 有独立 celery 服务；生产 Compose 没有 Celery 服务 | `scripts/start.sh:111-123`、`docker-compose.yml:35-55`、`docker-compose.prod.yml:5-126` | **确认 P2：生产 Compose 与生产文档声明的 Celery 运行模型不一致**；API 健康检查仍可能探测 Celery |
| 任务执行前提 | `tasks.md` 已确认 BaseTask 缺进度回调、项目验证固定成功、任务签名映射错位、异步嵌套 `asyncio.run` | `tasks.md:19-59` | 这些问题位于 API/worker 启动完成后的执行链，属于启动成功后的功能性阻断，结论与启动配置相互加强 |

## 3. 已确认问题

### RC1 [P1] Nginx 容器代理回环地址导致 API 入口断链

Compose 启动 `nginx` 与 `api` 为独立服务，二者通过同一 bridge network 通信（`docker-compose.yml:70-83`、`docker-compose.prod.yml:79-92`）。Nginx upstream 却固定为 `server 127.0.0.1:8080`（`configs/nginx.conf:80-84`），该地址指向 Nginx 容器自身。API 容器的服务名是 `api`，生产服务名仍为 `api`（`docker-compose.prod.yml:9-13`），所以 `/api/`、`/ws/`、`/health` 代理请求无法到达 API 容器。

这项确认了文档中“80 暴露、8080 API 直连”的拓扑描述（`README.ROOT.md:138-149`、`docs/guides/PRODUCTION.md:167-186`）只描述端口表面，未验证容器间真实路由。建议将容器模式的 upstream 收敛到 Compose 服务名，并为独立宿主脚本保留单独配置入口。

### RC2 [P1] 非 root 用户与 Nginx 监听/运行目录权限冲突

Dockerfile 创建并切换到 `appuser`（`Dockerfile:43-48`、`Dockerfile:87-88`），最终命令却在同一 shell 中启动 Nginx 和 Uvicorn（`Dockerfile:90-91`）。Nginx 配置要求监听特权端口 80（`configs/nginx.conf:86-89`），使用 `/var/run/nginx.pid`（`configs/nginx.conf:15`），并设置 `user root`（`configs/nginx.conf:6-7`）。现有权限设置只覆盖 `/var/log/nginx`、`/var/lib/nginx`、`/var/run` 的所有权（`Dockerfile:75-78`），端口能力、PID 文件创建和 Nginx master/worker 用户语义仍未形成可验证闭环。

该问题属于镜像启动硬阻断，影响 Dockerfile 单容器模式和 Compose 复用该镜像的 `api` 服务。Compose 独立 Nginx 使用 nginx 官方镜像，权限问题的适用面集中在 Dockerfile 内置 Nginx 路径。

### RC3 [P2] `/health` 检查路径形成成功态假象

FastAPI 健康 router 的实际路径是 `/api/v1/health`（`app/main.py:331-332`、`app/api/v1/health.py:25-31`）。Dockerfile、生产 Compose 健康检查、Nginx `/health` location 和生产文档均使用 `/health`（`Dockerfile:83-85`、`docker-compose.yml` 未为 api 定义独立 healthcheck、`docker-compose.prod.yml:32-37`、`configs/nginx.conf:121-125`、`docs/guides/PRODUCTION.md:183-186`）。

`app/main.py:345-365` 的 SPA fallback 会处理非 `api/` 路径，因此 `/health` 可能返回 `index.html` 并带 200；该响应无法证明数据库、Redis 或 API 健康逻辑通过。Nginx 端 `/health` 还受 RC1 影响，形成双重误判来源。

### RC4 [P2] 普通 Compose 的挂载路径与容器工作目录分裂

镜像工作目录与后端代码位于 `/app`（`Dockerfile:41`、`Dockerfile:54-58`），前端产物位于 `/app/src/dist`（`Dockerfile:60-61`）。普通 Compose API 却挂载 `./app` 到 `/workspace/app`、日志到 `/workspace/logs`、数据到 `/workspace/data`（`docker-compose.yml:23-26`），运行命令仍从镜像的 `/app` 工作目录执行。Dockerfile 为 `/workspace` 创建软链接（`Dockerfile:70-73`），但普通 Compose 的 `./app` 挂载会覆盖软链接目标关系，无法自动证明 Python 导入、日志落盘和数据访问使用同一份文件树。

生产 Compose 使用 `/app/logs` 和 `/app/data` named volume（`docker-compose.prod.yml:24-26`），与镜像工作目录一致，路径问题主要集中在普通 Compose。

### RC5 [P2] 调度器双跑结论成立，且启动钩子位置应统一

既有 `db_layer.md` 的 DB2 通过 `Dockerfile:91` 的 `--workers 2` 与 `main.py:287` 的 `start_scheduler()` 推导每 worker 启动调度器（`db_layer.md:60-78`）。当前代码核对确认：`start_scheduler()` 位于 `@app.on_event("startup")`（`app/main.py:273-290`），模块级调度器注册四个周期任务且只设置 `max_instances=1`（`app/db/scheduler.py:155-200`）。该缺陷不受 lifespan 中 `yield` 的存在影响。

同时，应用已经使用 lifespan 承载缓存、数据库池、Guardian 和关闭流程（`app/main.py:103-143`），又使用 startup 事件承载迁移、调度器和供应商恢复（`app/main.py:273-296`）。这是两套生命周期机制并存的维护风险，建议统一到一个生命周期入口，再单独抽出唯一调度进程或分布式 leader 锁。

### RC6 [P2] 生产 Compose 缺少 Celery 服务，健康能力与部署拓扑不一致

`start.sh` 明确启动 Celery worker（`scripts/start.sh:111-123`），普通 Compose 也定义 celery 服务（`docker-compose.yml:35-55`）。生产 Compose 只有 api、redis、nginx 三个服务（`docker-compose.prod.yml:5-126`），生产文档却将 Celery 列为非 Docker 部署的第 4 步（`docs/guides/PRODUCTION.md:198-206`），并把详细健康检查描述为包含 Celery（`docs/guides/PRODUCTION.md:241-249`）。因此生产 Compose 的任务队列执行依赖没有部署声明，健康文档与服务清单无法互相证明。

## 4. 已排除误报

| 原疑点 | 核对证据 | 结论 |
|---|---|---|
| `middleware.md` 的 `/api/docs` 是否与实际 docs 挂载点冲突 | `app/main.py:166` 明确设置 `docs_url="/api/docs"`；`app/main.py:166` 同时设置 redoc/openapi 路径 | **排除误报**。`middleware.md:71-73` 所列 SH2 当前已可关闭 |
| DB12 是否能直接认定 `create_all()` 与 Alembic 在同一次启动并行执行 | `create_tables()` 定义在 `app/main.py:236-240`，调用点仅为注释 `app/main.py:276-277`；实际 startup 执行 `run_async_migrations()` 于 `app/main.py:279-281`，其实现是按表存在性执行 `CreateTable`（`migrations/runner.py:27-62`） | **收窄结论**。当前运行路径是自定义表创建 runner，`create_all` 不是同次启动的第二个执行调用；文档将该 runner 概括为 Alembic 的表述需要修正，schema 漂移风险仍保留 |
| `tasks.md` 的任务问题是否等同于 API 启动失败 | `tasks.md:19-23` 的 TSK1、`tasks.md:26-30` 的 TSK2 等均发生在 Celery 消费任务执行阶段 | **排除层级误报**。它们是 worker 已启动后的执行链阻断，不能单独证明进程启动失败 |
| 普通 Compose 与生产 Compose 是否完全同一运行拓扑 | 普通 Compose 使用 `/workspace/*` 挂载和独立 celery（`docker-compose.yml:23-55`）；生产 Compose 使用 `/app/*` named volume 且无 celery（`docker-compose.prod.yml:24-26`、`docker-compose.prod.yml:5-126`） | **排除“同构部署”假设**。两者必须分别验收，不能用一个环境的健康结果代表另一个环境 |

## 5. 剩余风险

1. `migrations/runner.py:35-62` 每次创建独立异步 engine，并按表是否存在执行 `CreateTable`；其迁移版本、并发启动行为和异常恢复语义仍需单独核对。当前终审只确认它已被 startup 调用。
2. `app/main.py:114-121` 的 Redis 配置按环境变量选择缓存后端，`docker-compose.yml:18` 与生产 Compose `docker-compose.prod.yml:19` 提供 Redis URL；Redis 可用性、缓存初始化失败后的降级行为未在本次只读交叉审查中运行验证。
3. `scripts/start.sh:17-23` 使用 `export $(grep ... | xargs)` 解析 `.env`，特殊字符、空格和多行值可能被改写；脚本还以 `pkill` 和交互式端口清理控制进程（`scripts/start.sh:49-57`、`scripts/start.sh:149-161`），存在误操作与无人值守阻塞风险。
4. `scripts/start-backend.sh:3-6` 直接结束已有 Uvicorn 进程、后台启动 8000 端口；脚本探测的 `/api/v1/health` 与 Docker/Compose 探测的 `/health` 口径不同，诊断结果无法直接横向比较。
5. Dockerfile 使用 `nginx & uvicorn` 的 shell 组合（`Dockerfile:90-91`），进程信号转发、Nginx 子进程退出传播和优雅关闭语义尚未确认；这与 `main.py:133-135` 的应用清理流程形成独立的容器级收尾风险。
6. `app/main.py:100` 在模块导入阶段执行 `setup_logging()`，大量路由和服务也在导入期间构造全局对象；第 156-159 轮对应文档中尚未形成“导入失败、迁移失败、调度失败、健康失败”的分层启动状态协议。

## 6. 最终收敛建议

按以下顺序收敛启动真相：

1. 先修复部署硬断链：为容器模式设置 `api:8080` upstream；统一容器内 `/app` 路径；让 Nginx 运行方式与非 root 策略一致；将 Docker/Compose/Nginx 健康检查统一到真实 API 健康端点。
2. 将启动拓扑拆成明确的 `api`、`celery`、`nginx` 责任边界。生产 Compose 增补 Celery 或同步删除健康与文档中的 Celery 依赖声明，确保任务队列有唯一部署真相。
3. 合并 lifespan 与 startup 的初始化编排，迁移、缓存预热、Guardian、供应商恢复、调度器启动分别返回可观测状态；启动失败策略按“阻断启动 / 降级启动 / 告警继续”显式定义。
4. 调度器采用独立进程、Celery Beat 或分布式 leader 锁三者之一，并把 `ENABLE_SCHEDULER` 类开关纳入部署配置；`max_instances=1` 保留为进程内保护层。
5. 启动链稳定后再处理 `tasks.md` 的 TSK1-TSK6：先补进度回调和任务参数契约，再修项目验证实际调用与异步测试执行，最后统一重试 ID 和状态来源。
6. 文档收敛以“场景 + 唯一命令 + 端口 + 健康 URL + 服务清单”为最小单元，明确第 155 轮与 `v1.156` 编号关系，并为第 156-159 轮补充可追溯的索引条目。

最终验收门槛是：从每种支持的启动入口都能得到同一套服务拓扑、同一套健康 URL、同一套工作目录语义，并能证明 API、Nginx、Celery、Redis 和调度器各自只启动一次且状态可观测。
