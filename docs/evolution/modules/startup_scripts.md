# scripts 启动与运维脚本家族演化深扫文档

> 版本：v0.1 | 扫描日期：2026-08-29 | 状态：已完成
> 归属：运行与部署 / 本地脚本入口
> 路径：scripts/{start.sh,dev.sh,start-backend.sh,stop.sh,status.sh,migrate.sh,test.sh,verify-integration.sh}（579 行）
> 索引：[TASKS.md](../TASKS.md)，第 157 轮
>
> 扫描范围：逐文件静态阅读、全库引用/端口检索、README/Compose/路由交叉核对。未启动服务、未执行迁移或测试。

## 一、模块定位与状态

| 脚本 | 定位 | 状态判定 | 关键证据 |
|------|------|---------|---------|
| `scripts/start.sh` | 生产式单机编排：前端构建、Gunicorn API、Celery、Nginx、Redis 检查 | **活跃入口，当前路径契约错误**；README 标记为主启动脚本，但从 `scripts/` 目录运行时多处路径指向错误位置 | `start.sh:17-18,61-77,86-100,125-139`；`docs/ROOT-FILES.md:99-102,140-149` |
| `scripts/dev.sh` | Uvicorn 热重载开发服务 | **活跃开发入口**；依赖调用时的当前工作目录 | `dev.sh:10-22` |
| `scripts/start-backend.sh` | 临时/快速启动 Uvicorn 并调用两个 HTTP 检查 | **活跃但独立旁路**；与主启动脚本使用不同端口和进程模型 | `start-backend.sh:3-19` |
| `scripts/stop.sh` | 停止 Celery、Gunicorn、Uvicorn 并清理 PID 文件 | **活跃运维入口，覆盖面与启动入口不一致**；不停止 Nginx，且工作目录仍为 `scripts/` | `stop.sh:4-5,9-29` |
| `scripts/status.sh` | PID、8080 端口、内存、Redis、错误日志检查 | **活跃诊断入口，检查面偏向 Gunicorn 8080**；无法完整反映 8000 开发服务或 Nginx | `status.sh:4-5,11-55` |
| `scripts/migrate.sh` | 执行 Alembic 到 head 并输出最近历史 | **活跃一次性运维入口，当前目录依赖未封装**；仓库配置位于 `configs/alembic.ini` | `migrate.sh:10-24`；`configs/alembic.ini` |
| `scripts/test.sh` | 使用 pytest 执行 `tests/` 全量测试 | **活跃测试入口，调用目录和测试范围固定** | `test.sh:10-21` |
| `scripts/verify-integration.sh` | 文件存在性、源码内容和单文件语法静态检查 | **活跃验证入口，名称与实际能力不一致**；没有启动服务或发起集成链路验证 | `verify-integration.sh:19-50,53-110,112-125` |

### 1.1 入口关系

当前脚本家族存在三条并行路径：

```text
start.sh start/restart ──► Gunicorn :8080 + Celery + Nginx :80
dev.sh ───────────────────► Uvicorn --reload :8000
start-backend.sh ─────────► Uvicorn :8000（后台子进程）+ curl 检查
stop.sh/status.sh ────────► 主要围绕 scripts/{*.pid} 与 :8080
migrate.sh/test.sh ───────► 依赖调用方当前目录
verify-integration.sh ────► 仅本地文件与源码文本检查
```

应用健康路由由 `app/main.py:331-332` 挂载为 `/api/v1/health`。Compose 生产配置把 API 映射为 `127.0.0.1:8080:8080`、Nginx 映射为 `80:80`（`docker-compose.yml:14-16,70-76`），与 `dev.sh` 和 `start-backend.sh` 的 8000 约定形成端口双轨。

## 二、已探明问题

### P2 发现（4 项）

- **SS1 [P2] `start.sh` 将 `scripts/` 当作项目根目录，主启动链从默认调用位置整体失效**——`start.sh:17-18` 将 `PROJECT_DIR` 固定为 `/workspace/scripts` 并切换到该目录；随后 `start.sh:62-67` 查找 `scripts/src/package.json`，`start.sh:86` 在 `scripts/` 下导入 `app.main`，`start.sh:134-139` 查找 `scripts/configs/nginx.conf`，日志和数据写入 `scripts/logs`、`scripts/data`（`:34-35`）。实际项目根目录是 `/workspace`，前端、`app`、`configs` 均位于根目录。结果是 API 导入、前端构建、Nginx 配置和运行数据路径至少有一项失败或落入错误目录。修复方向：使用脚本目录的父目录作为项目根，或显式设置统一 `PROJECT_ROOT` 并让所有入口复用。
- **SS2 [P2] 健康 URL 已统一**——`start.sh` 的启动检查和状态检查均请求 `http://127.0.0.1:8080/api/v1/health`，与 FastAPI、Dockerfile、Compose 和 Nginx 探针保持一致；脚本实际进程启动仍需运行环境验证。
- **SS3 [P2] 停止与启动进程模型分裂，存在残留服务和误杀无关进程风险**——启动入口同时使用 PID 文件、`pkill -f` 和 Nginx 全名匹配（`start.sh:49-57`）；`stop.sh:16-29` 再次用宽匹配停止所有符合命令文本的 Celery/Gunicorn/Uvicorn。`start-backend.sh:3` 直接 `pkill -9 -f uvicorn`，会结束当前环境内所有匹配的 Uvicorn；其后台子进程没有 `trap` 清理（`:6-9`），而 `stop.sh` 仅按另一条命令文本匹配（`:28-29`）。Nginx 由 `start.sh` 启动却未被 `stop.sh` 停止（`stop.sh:7-31`）。修复方向：统一 PID/进程组生命周期，停止前校验命令与 PID，使用受管服务或明确的进程组清理。
- **SS4 [P2] 8000 与 8080 两套后端端口契约未收敛，README 推荐项与 Compose/主启动项互相偏离**——`dev.sh:22` 和 `start-backend.sh:6` 使用 8000；`start.sh:87`、`status.sh:32-37`、Compose `docker-compose.yml:14-16` 使用 8080；README 同时把 `start.sh` 称为开发环境推荐（`docs/ROOT-FILES.md:140-145`），并把进程检查/端口检查写成 Uvicorn/8000（`:187-198`）。调用方按不同文档启动时会出现健康检查、停止和状态结果不一致。修复方向：按 development/production 明确单一端口契约，集中定义 API 地址并同步所有脚本与文档。

### P3 发现（10 项）

- **SS5 [P3] `dev.sh`、`migrate.sh`、`test.sh` 均依赖调用方当前目录**——`dev.sh:11-14,18,22` 使用相对 `.env`、`logs` 和 `app.main`；`migrate.sh:18,24` 直接调用 Alembic；`test.sh:18` 直接调用 `tests/`。从仓库根目录和从 `scripts/` 目录调用会得到不同结果，迁移配置尤其需要 `configs/alembic.ini`（docs/ROOT-FILES.md:164-172）。修复方向：统一解析仓库根目录并通过 `--config`/绝对路径传递关键资源。
- **SS6 [P3] `start.sh` 的 Redis 默认地址与 Compose 网络地址语义不同**——裸机默认 `redis://localhost:6379/0`（`start.sh:26-32`），Compose API/Celery 使用 `redis://redis:6379/0`（`docker-compose.yml:16-19,43-45`）。同一套环境变量说明在宿主机和容器中需要人工切换，增加误连本机 Redis 的概率。修复方向：按运行模式生成配置或在启动入口显式校验 Redis 主机名。
- **SS7 [P3] `start.sh` 端口占用检查是交互式阻塞点，无法稳定用于自动化部署**——`start.sh:149-161` 发现 80 端口占用后执行 `read -p`，无人值守调用会挂起；用户输入确认后使用 `pkill -f nginx`，目标识别仍然宽泛。修复方向：增加非交互模式和明确的失败返回，按 PID/配置归属处理端口冲突。
- **SS8 [P3] 启动成功判定缺少 PID、进程和退出状态联动**——Gunicorn 只依赖一次 curl（`start.sh:102-108`）；Celery 启动后无健康检查，仅读取 PID 或输出 `N/A`（`:114-122`）；Nginx 只用 `pgrep -x nginx`（`:141-146`）。服务短暂启动后退出、PID 文件陈旧或其他实例存在时，报告可能与实际服务状态不符。修复方向：保存并校验进程身份，设置有界重试和各服务就绪检查。
- **SS9 [P3] PID 文件没有陈旧清理、原子写入和进程身份校验**——`start.sh:99-100,119-120` 依赖 Gunicorn/Celery 写 PID；`start.sh:52-53`、`stop.sh:10-14,20-23` 直接读取并 kill；`status.sh:12-28` 只检查 PID 是否存在。PID 重用或并发启动会把停止操作指向错误进程。修复方向：使用服务管理器或在操作前校验 `/proc` 命令行与启动实例标识。
- **SS10 [P3] `status.sh` 的状态覆盖不完整且依赖可选外部工具**——仅检查 8080（`status.sh:31-37`），未检查 8000、80、Nginx 或 API URL；`lsof`、`ps`、`tail` 的缺失处理不一致（`:32-55`）。开发服务运行时可能显示 API 停止，Nginx 失效也不会出现在结果中。修复方向：按启动模式检查端口、HTTP 健康和进程，并对工具缺失给出明确状态。
- **SS11 [P3] `stop.sh` 删除 PID 文件的动作可能掩盖停止失败**——`stop.sh:12-14,21-23` 在 kill 失败时仍继续清理 PID 文件，后续 status 无法区分进程仍存活与文件已丢失；`start.sh:52-57` 的停止流程也不等待进程退出，只固定 `sleep 1`。修复方向：先确认进程退出，再清理 PID 文件；超时后报告残留 PID。
- **SS12 [P3] `start-backend.sh` 的验证管线不会可靠传播失败**——脚本没有 `set -e`（`start-backend.sh:1-19`）；`curl` 失败、JSON 解析失败或公钥字段缺失后仍会输出 `Backend is ready!`（`:11-19`）。`head -10` 还会截断健康响应，诊断证据不完整。修复方向：对 HTTP 状态码和 JSON 结构显式断言，并根据检查结果退出。
- **SS13 [P3] `test.sh` 将全量测试、外部服务和超时责任全部交给 pytest**——`test.sh:16-18` 固定运行 `tests/`，没有测试分类、服务可用性检查、超时或资源边界；集成测试会把本地环境状态混入“全量测试”结果。修复方向：拆分 unit/integration 入口，使用项目既有标记与服务可用性跳过策略，并提供有界执行参数。
- **SS14 [P3] `verify-integration.sh` 是静态集成前置检查，名称与输出会让人误判为真实集成验证**——所有检查集中在文件存在、文本 `grep`、单文件 `py_compile`（`verify-integration.sh:19-110`）；没有启动前后端、HTTP 请求、数据库或跨组件行为断言。脚本只在最终计数后退出（`:112-125`），无法报告检查项的运行时覆盖范围。修复方向：改名为静态集成前置检查，或增加隔离服务启动、健康检查和真实接口断言。

## 三、路径、端口与生命周期矩阵

| 维度 | `start.sh` | `dev.sh` / `start-backend.sh` | `stop.sh` / `status.sh` | 结论 |
|------|------------|------------------------------|-------------------------|------|
| 工作目录 | 脚本目录 `/workspace/scripts` | 调用方当前目录；`start-backend.sh` 固定 `/workspace` | 脚本目录 `/workspace/scripts` | 根目录契约分裂，`app`/`src`/`configs`/`tests` 解析不稳定 |
| API 端口 | Gunicorn `0.0.0.0:8080`（`start.sh:86-88`） | Uvicorn `0.0.0.0:8000`（`dev.sh:22`、`start-backend.sh:6`） | 只检查 8080（`status.sh:31-37`） | 8000/8080 双轨 |
| 前端入口 | 构建 `src/dist`，Nginx 80（实现受路径错误影响） | 无前端启动 | 不检查 80/Nginx | 开发与生产入口职责断开 |
| PID/停止 | Gunicorn/Celery PID + 宽匹配 kill | `$!` 仅打印，脚本退出无清理 | PID 文件 + 宽匹配 kill | 进程归属和清理策略不统一 |
| Redis | `localhost:6379` 默认值 | 未显式设置 | `REDIS_URL` 默认 localhost | 宿主机与 Compose 服务名双语义 |

## 四、潜在问题与未知点

- `start.sh:86` 的 Gunicorn 命令是否在实际部署环境中由外部 `cd /workspace` 包装执行无法从脚本本身确认；脚本内部的 `cd /workspace/scripts` 已足以形成路径风险。
- `start.sh:103` 的 `/health` 可能由外部 Nginx 或其他中间层提供，但当前 API 路由交叉检索只确认 `/api/v1/health`；裸连 8080 的检查契约需要运行时确认。
- `stop.sh` 使用 `celery control shutdown --pidfile=...` 的 CLI 参数是否被当前 Celery 版本支持未执行验证；失败会被 `|| true` 静默吞掉。
- `verify-integration.sh` 中的 `((PASSED++))`/`((FAILED++))` 在计数初值为 0 时返回 shell 状态 1；当前脚本没有 `set -e`，因此暂未形成中止缺陷，后续若统一加入 `set -e` 需同步改写。
- README 的“保留脚本”表明这些入口仍被项目维护者视为活跃面；脚本本身没有引用统一的服务编排配置，实际生产使用路径仍需运维环境证据确认。

## 五、修改建议（改什么 → 达成什么目的）

| # | 优先级 | 修改动作 | 达成目的 | 涉及位置 | 对应 Backlog |
|---|--------|---------|---------|---------|-------------|
| 1 | P2 | 统一计算仓库根目录，修正 `app`、`src`、`configs`、`logs`、`data` 与 PID 路径 | 让主启动、停止、状态和构建从任意调用目录得到相同结果 | `start.sh:17-18,34-35,62-77,134-139`；`stop.sh:4-5`；`status.sh:4-5` | 待记 |
| 2 | P2 | 统一 API 端口与健康 URL，并同步 README、Compose、Nginx 和全部脚本 | 消除 8000/8080 双轨与假失败 | `start.sh:87,103,173`；`dev.sh:22`；`start-backend.sh:6,13`；`status.sh:32-37`；`app/main.py:331-332` | 待记 |
| 3 | P2 | 用 PID/进程组或外部服务管理器收敛启动、停止、重启；移除宽泛 `pkill -f` | 防止误杀、残留进程和 PID 重用 | `start.sh:49-57,156`；`stop.sh:9-29`；`start-backend.sh:3,6-9` | 待记 |
| 4 | P3 | 为 `migrate.sh`、`test.sh`、`dev.sh` 引入根目录解析、显式配置路径和模式化参数 | 消除 CWD 漂移，让迁移、开发和测试入口可重复 | `dev.sh:10-22`；`migrate.sh:16-24`；`test.sh:16-18` | 待记 |
| 5 | P3 | 将服务就绪检查改为 HTTP 状态/响应断言，增加超时和失败退出 | 让启动与快速验证结果反映真实服务状态 | `start.sh:102-108,121-123,141-146`；`start-backend.sh:11-19` | 待记 |
| 6 | P3 | 让 `status.sh` 按模式覆盖 API、Nginx、Celery、Redis、PID 身份和开发端口 | 形成统一可观测的服务状态报告 | `status.sh:11-55` | 待记 |
| 7 | P3 | 将静态文件检查与真实集成测试分名分层，补充受控服务生命周期 | 避免静态命中被解释为跨组件验证通过 | `verify-integration.sh:19-125` | 待记 |
| 8 | P3 | 为全量 pytest 增加测试分类、服务依赖检查、超时和资源边界 | 降低环境状态对测试结果的干扰 | `test.sh:16-18` | 待记 |

## 六、演化方向关联

- 该脚本家族属于部署与验证闭环的外层入口，当前主要演化矛盾是“脚本各自维护路径、端口、PID 和健康判定”，与仓库内相对路径 CWD 漂移、进程守护和验证语义分裂属于同一类系统问题。
- `start.sh` 应收敛为唯一生产式编排入口，`dev.sh` 保留为明确的开发入口，`start-backend.sh` 需要转为受控诊断工具或并入开发入口；三者共享项目根目录、API 地址和健康检查配置。
- `stop.sh` 与 `status.sh` 应围绕同一服务清单生成操作和报告，覆盖 Gunicorn/Uvicorn、Celery、Nginx、Redis 与前端入口，形成“启动声明什么、状态观察什么、停止回收什么”的对称生命周期。
- `migrate.sh` 与 `test.sh` 应进入可重复的工程命令层，明确执行目录、配置来源、测试分类和失败语义；`verify-integration.sh` 应定位为静态门禁或补齐真实集成执行链。
