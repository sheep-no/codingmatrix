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
| 生产容器 API | Dockerfile 支持单容器模式；生产 Compose 显式覆盖为仅运行 2 worker Uvicorn，由独立 Nginx 提供入口 | `Dockerfile`、`docker-compose.prod.yml`、`configs/nginx.conf` | RC3 运行模型代码修复完成，容器验证待完成 |
| 宿主脚本 API | `start.sh` 使用 Gunicorn 2 worker 监听 `0.0.0.0:8080`；`dev.sh` 和 `start-backend.sh` 使用 Uvicorn 8000 | `scripts/start.sh:80-100`、`scripts/dev.sh:20-22`、`scripts/start-backend.sh:5-8` | 启动方式存在三套端口/进程语义，文档必须按场景区分 |
| Nginx 容器到 API | Compose 中 Nginx 与 API 分属不同容器；Compose upstream 使用 `api:8080` | `docker-compose.yml`、`docker-compose.prod.yml`、`configs/nginx-upstream-compose.conf` | RC1 代码修复完成，网络代理待验证 |
| API 健康检查 | FastAPI、Dockerfile、Compose、Nginx 和启动脚本统一使用 `/api/v1/health`；Nginx 保留 `/health` 到真实 API 的显式别名 | `app/main.py`、`app/api/v1/health.py`、`Dockerfile`、`docker-compose*.yml`、`configs/nginx.conf`、`scripts/start.sh` | **RC3 代码修复完成，容器运行验证待完成** |
| Nginx 健康检查 | Nginx `/api/v1/health` 代理到 API upstream，`/health` 显式映射到相同 API | `configs/nginx.conf` | RC3 与 RC1 已完成代码修复 |
| 容器文件路径 | Dockerfile 与普通 Compose 的代码、日志、数据路径统一使用 `/app` | `Dockerfile`、`docker-compose.yml` | **RC4 代码修复完成，容器运行验证待完成** |
| 前端构建产物 | Dockerfile 将 dist 放到 `/app/src/dist`，随后创建 `/workspace/src/dist` 并建立软链接；普通 Compose Nginx 只挂载宿主 `./src/dist` | `Dockerfile:60-73`、`docker-compose.yml:77-80` | 镜像内路径可用性取决于软链接和挂载组合，Compose API 与 Nginx 使用两套文件视图 |
| Nginx 运行权限 | 修复前镜像切换 `USER appuser` 后执行 `nginx & ...`；当前由 root master 启动、`nginx` worker 运行并将 Uvicorn 降权为 `appuser` | `Dockerfile:43-48`、`Dockerfile:75-91`、`configs/nginx.conf:6-16`、`configs/nginx.conf:86-89` | **RC2 代码修复完成，容器端口、PID 和日志权限待运行验证** |
| 数据库启动 | `on_startup` 执行自定义 `run_async_migrations()`；lifespan 中 `_warm_up_database_pool()`，另有未调用的 `create_tables()` | `app/main.py:123-124`、`app/main.py:236-240`、`app/main.py:273-290`、`migrations/runner.py:27-62` | 自定义表创建与预热均接线；`create_all` 当前为死函数，DB12 中“同一次启动两条建表路径并行生效”的表述需要收窄 |
| 调度器启动 | API 由 `ENABLE_SCHEDULER` 控制；普通 Compose 使用单 worker，生产 Compose 使用独立 scheduler 服务 | `app/main.py`、`app/db/scheduler_runner.py`、`docker-compose*.yml` | **RC5 代码修复完成，单实例运行待验证** |
| Redis 启动 | Compose API 依赖 Redis，但普通 Compose 仅声明启动顺序；生产 Compose 使用 Redis `service_healthy` 条件 | `docker-compose.yml:16-30`、`docker-compose.prod.yml:17-30`、`docker-compose.prod.yml:61-66` | 生产依赖闭环较完整，普通 Compose 的就绪保障较弱 |
| Celery 启动 | `start.sh`、普通 Compose 和生产 Compose 均声明独立 Celery worker | `scripts/start.sh:111-123`、`docker-compose.yml:35-55`、`docker-compose.prod.yml` | **RC6 代码修复完成，worker 消费和健康状态待验证** |
| 任务执行前提 | `tasks.md` 已确认 BaseTask 缺进度回调、项目验证固定成功、任务签名映射错位、异步嵌套 `asyncio.run` | `tasks.md:19-59` | 这些问题位于 API/worker 启动完成后的执行链，属于启动成功后的功能性阻断，结论与启动配置相互加强 |

## 3. 已确认问题与修复状态

### RC1-RC2 修复记录（2026-08-29）

- RC1 已修复：`configs/nginx.conf` 通过 `/etc/nginx/conf.d/upstream.conf` 注入上游；Compose 使用 `configs/nginx-upstream-compose.conf` 指向 `api:8080`，Dockerfile 单容器使用 `configs/nginx-upstream-local.conf` 指向 `127.0.0.1:8080`。
- RC2 已修复：Dockerfile 安装 Nginx 后复制运行配置，Nginx 由 root master 启动并以 `nginx` worker 用户运行，Uvicorn 通过 `su` 降权到 `appuser`；`/var/log/nginx`、`/var/lib/nginx` 和 `/var/run` 由 `nginx` 用户管理。
- 当前状态：代码和配置静态检查已完成；Docker build、Nginx `-t`、Compose 网络代理、80 端口绑定和 API 实际可达性等待容器环境验证。

### RC1 [P1] Nginx 容器代理回环地址导致 API 入口断链

修复前，Compose 启动的独立 Nginx 使用 `server 127.0.0.1:8080`，该地址指向 Nginx 容器自身。当前 Compose 专用 upstream 已改为 `server api:8080`；单容器 Dockerfile 继续使用本机 upstream。容器网络中的 `/api/`、`/ws/` 和健康路径仍需运行验证。

修复将容器模式 upstream 收敛到 Compose 服务名，并为单容器模式保留独立配置入口；原有端口和健康路径文档仍需配合 RC3 一并核对。

### RC2 [P1] 非 root 用户与 Nginx 监听/运行目录权限冲突

修复前，Dockerfile 切换到 `appuser` 后在同一 shell 启动 Nginx 和 Uvicorn，Nginx 监听 80 并使用 `/var/run/nginx.pid`，权限链无法闭合。当前 Dockerfile 由 root master 启动 Nginx，Nginx worker 使用 `nginx` 用户，Uvicorn 使用 `appuser`，并完成相关运行目录授权。

当前代码路径已完成权限模型调整；Dockerfile 镜像启动、Nginx PID 创建、80 端口绑定和 Uvicorn 降权仍需容器运行验证。Compose 独立 Nginx 继续使用官方镜像，采用其 `nginx` 用户模型。

### RC3 [P2] 健康检查路径已统一

FastAPI、Dockerfile、Compose、Nginx 和启动脚本统一使用 `/api/v1/health`。Nginx 保留 `/health` 显式别名并转发到同一真实 API，避免 SPA fallback 的 200 响应掩盖 API 状态。容器内 API 与 Nginx 的实际探针仍需运行验证。

### RC4 [P2] Compose 挂载路径已统一

镜像工作目录、后端代码、日志和数据目录均位于 `/app`。普通 Compose 的 API/Celery bind mount 已统一挂载到 `/app/app`、`/app/logs` 和 `/app/data`，与生产 Compose 的 named volume 路径一致。容器内 Python 导入、日志落盘和数据访问仍需运行验证。

生产 Compose 使用 `/app/logs` 和 `/app/data` named volume（`docker-compose.prod.yml:24-26`），与镜像工作目录一致，路径问题主要集中在普通 Compose。

### RC5 [P2] 调度器已拆分为独立单实例

应用初始化已统一进入 `lifespan`。API 仅在 `ENABLE_SCHEDULER=true` 时启动 scheduler；普通 Compose 使用单 worker API，生产 Compose 将 API 设置为 `false` 并运行独立 `scheduler` 服务，通过 `app.db.scheduler_runner` 保持唯一调度进程。容器启动和任务单实例仍需运行验证。

### RC6 [P2] 生产 Compose 已补齐 Celery 服务

生产 Compose 现已声明独立 `celery` worker，并依赖健康的 Redis；API、Celery、scheduler、Redis 和 Nginx 的服务职责均有对应条目。Celery worker 的任务消费和健康语义仍需容器运行验证。

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
