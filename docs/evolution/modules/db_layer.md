# app/db 数据层 演化深扫文档

> 版本：v0.1 | 扫描日期：2026-08-28 | 状态：已完成（第一百五十一轮，合扫）
> 归属：基础设施层 / 数据访问层（对应 SERVICES-EVOLUTION.md H 组公共底座）
> 路径：app/db/（12 文件 1322 行：database 36 + models 141 + add_history 63 + search_history 139 + chat_history_service 227 + chat_archiver 318 + scheduler 204 + log_server 132 + permission_service 37 + user_sql_server 20 + init_workflow 15 + clear 19）
> 索引：[TASKS.md](../TASKS.md)

## 0. 模块定位与状态判定（三态）

| 文件 | 状态 | 判定依据 |
|------|------|---------|
| database.py | **活跃** | engine/async_session/get_db 全库会话源（conftest/main.py + 20+ 消费文件 `from app.db.database import`） |
| models.py | **活跃** | 4 表 4 消费族：ProjectSession（orchestrate_endpoints.py:18/helpers.py:17/session_manager.py:139/:371/system_config.py:109）、WorkflowHistory（api/v1/workflow.py:28）、ImageGenerationHistory（kolors_api.py:37/kolors_history.py:21）、ConversationMessage（conversation_store.py:116/:172/:196） |
| add_history.py | **活跃** | save_history_to_db 被 Aicode.py:31→:610/:689（对话主链路）消费 |
| search_history.py | **活跃** | search_history_to_db/get_distinct_conversation_count/get_conversation_history 被 auth.py:300-339（历史列表/详情）消费 |
| user_sql_server.py | **活跃** | auth.py:8 star import，get_user_by_email（:146 登录）/check_email_exists（:249 注册） |
| permission_service.py | **活跃** | auth.py:16 star import，:163/:266/:393 三处注册/登录路径调用 |
| chat_history_service.py | **活跃** | GirlAi.py:22→:443/:578/:839（虚拟姬对话/历史/删除） |
| chat_archiver.py | **活跃** | scheduler.py:11→:20-24 archive_task 每 10 天调度执行 |
| scheduler.py | **活跃** | main.py:86 import + :287 start_scheduler（lifespan 内启动） |
| log_server.py | **活跃（半接）** | api/v2/Controller.py:15→:197-206 WS 日志流（admin 门禁）；stream 循环在轮转后失明（DB9） |
| init_workflow.py | **未接入（一次性脚本）** | 全库零 import，仅 `__main__`；main.py:239 create_all(checkfirst) 已覆盖其功能；docstring 称「创建 workflow_history 表」实际 create_all 建全部表 |
| clear.py | **未接入（一次性脚本）** | 全库零 import；GLOB 为 SQLite 专用语法的一次性脏数据清洗脚本，PG 下不可运行 |

**与 app/models/ 的关系澄清**（MEMORY.md「重复实现」条目复核）：app/db/models.py（4 表）与 app/models/（13 文件）是**表集合互补关系而非双轨**——前者承载 Agent 会话/工作流/绘图/对话四张业务表，后者承载用户/任务/文件等基础表，共用同一 Base（app.models.base）；同名 models.py 是命名混淆源（建议迁移期改名）。

## 1. 模块作用与功能

- 核心职责：异步引擎与会话工厂（database.py）+ Agent 业务四表 ORM（models.py）+ 对话历史读写（add_history/search_history）+ 虚拟姬对话历史（chat_history_service）+ 定时归档与清理调度（chat_archiver/scheduler）+ v2 日志流（log_server）+ 权限/用户查询便捷层（permission_service/user_sql_server）
- 主要符号：`engine`/`async_session`/`get_db`（database.py:7/:20/:29）；`ProjectSession`/`WorkflowHistory`/`ImageGenerationHistory`/`ConversationMessage`（models.py:7/:48/:82/:118）；`save_history_to_db`（add_history.py:10）；`search_history_to_db`/`get_conversation_history`/`get_distinct_conversation_count`（search_history.py:14/:67/:107）；`ChatHistoryService`（chat_history_service.py:8）；`ChatArchiver`（chat_archiver.py:30）；`scheduler`/`archive_task`/`cleanup_files_task`/`cleanup_tasks_task`/`cleanup_logs_task`/`start_scheduler`（scheduler.py:16/:20/:27/:99/:138/:197）；`LogService`/`LogFilter`（log_server.py:11/:121）；`PermissionService`（permission_service.py:8）；`get_user_by_email`/`check_email_exists`（user_sql_server.py:10/:16）
- 内部子功能划分：连接管理 / 历史存储 / 定时任务 / 日志流 / 认证辅助

## 2. 依赖与被依赖

- 导入依赖：sqlalchemy(ext.asyncio)、app.core.config.settings、app.models.base.Base、app.models.{user,history,chat_history,file,task,Permission}、app.utils.call_llm（chat_archiver）、apscheduler、aiofiles、app.utils.task_manager
- 生产使用方：见 §0 状态表判定依据列；celery 侧 project_tasks 经 app.db（graceful_shutdown 依赖 websocket_manager 不涉及本层）
- 测试覆盖：tests/unit/test_database_services.py（23 用例 5 类：user_sql_server/permission_service/chat_history_service/add_history/search_history）、tests/unit/test_linked_cleanup.py（6 用例，ProjectSession 清理）、tests/unit/test_system_monitor.py（12 用例，LogService/LogFilter——流式仅 `hasattr(gen,'__aiter__')` 弱断言）、tests/unit/test_bugfixes.py 22 用例部分涉及；**ChatArchiver/scheduler 定时任务/PRAGMA/轮转行为零测试**（chat_archiver 仅 tests/archive/legacy 引用）

## 3. 已探明 Bug（含 bug 代码）

### DB1 [P2] PRAGMA foreign_keys 终审：主库外键强制关闭，级联矩阵在默认部署下整层失效

- **现象**：默认 SQLite（config.py:21 `sqlite+aiosqlite:///.../app.db`）下删除用户/任务时子表行残留孤儿；149 轮 MD1 判定的「SQLite 下 DB 级联全失效」在本层根因坐实
- **Bug 代码**：

```python
# database.py:7-17 - engine 构造无任何 event listener / PRAGMA
engine = create_async_engine(
    settings.DATABASE_URL,
    ...
    connect_args={"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {},
)
```

- **根因**：SQLite 外键约束默认关闭，需每连接执行 `PRAGMA foreign_keys=ON`；全库唯一设置点在 services/user_preferences.py:24（自有裸 sqlite3 连接，仅作用于偏好存储自身），主引擎无 `event.listens_for(engine, "connect")` 钩子——File/Task 的 DB 层 ondelete、History 的 FK 全部退化为装饰
- **影响**：MD1 级联矩阵在 SQLite 部署下整层失效（对话/审计/文件记录孤儿残留泄露面）；PostgreSQL 部署则切换为「删 User 报 FK 错 → delete_user 失效」的另一分支——两种部署形态各坏一半
- **触发条件**：默认配置启动 + 任何用户/任务删除操作
- **验证方式**：sqlite3 连 app.db 执行 `PRAGMA foreign_keys` 返回 0；删有 History 的用户后 History 行仍在

### DB2 [P2] APScheduler 多 worker 双实例并发——四个定时任务全部双跑

- **现象**：容器内 uvicorn --workers 2 启动后，归档/文件清理/任务清理/日志清理每个周期执行两次
- **Bug 代码**：

```dockerfile
# Dockerfile:91
CMD ["sh", "-c", "nginx & uvicorn app.main:app --host 0.0.0.0 --port 8080 --workers 2"]
```

```python
# main.py:287（lifespan，每个 worker 各执行一次）+ scheduler.py:16 模块级实例
start_scheduler()   # scheduler = AsyncIOScheduler() 无任何分布式锁/leader 选举
```

- **根因**：AsyncIOScheduler 进程内存态，多 worker 各自实例化并 start；无环境变量/锁开关，`max_instances=1` 只约束单进程内并发
- **影响**：chat_archive 双跑 → 同用户并发归档（双份 AI 摘要成本 + ChatSummary 同期重复行——重叠检查先读后写无锁）；cleanup_files_task 双跑 → 同一物理文件 os.remove 竞态（一方 FileNotFoundError → OSError → 整任务 rollback → 该轮零删除）+ ORM delete 0 行匹配异常回滚整批；cleanup_tasks/log_cleanup 同理双份执行；与 DB3 叠加放大 SQLite 写锁冲突
- **触发条件**：生产 Docker 部署（默认 workers 2）+ 任一定时任务到期
- **验证方式**：docker compose up 后观察日志同一任务两条「开始归档任务」，或查询 APScheduler 双实例

### DB3 [P2] SQLite 主库无 busy_timeout/WAL——多进程并发写锁冲突

- **现象**：2 个 uvicorn worker + celery 并发写 app.db 时偶发 `sqlite3.OperationalError: database is locked`
- **Bug 代码**：

```python
# database.py:16 - 仅 check_same_thread，无 busy_timeout、无 WAL
connect_args={"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {},
```

- **根因**：SQLite 默认 journal 模式 + 默认 busy_timeout=0；WAL 在全库仅三个**各自裸连接**处设置（user_preferences.py:23/feedback_tracker.py:21/dynamic_model_router.py:173），主库从未设置；DB2 的双跑调度任务使写并发常态化
- **影响**：历史保存（add_history:53 commit）、任务状态更新、定时清理全部在锁冲突面内；RLM1 六项 AI 主链路限流空转后写入压力无缓冲
- **触发条件**：默认 SQLite 配置 + 并发写（对话/生成/定时任务任一重叠）
- **验证方式**：两进程同时写同一表循环插入，未设 busy_timeout 一方立即 OperationalError

### DB4 [P3] 归档窗口零容差 + 偏移分页边处理边删——时间带永久逃逸归档

- **现象**：任何调度抖动（重启/延迟/coalesce）或分页偏移后，对应 10 天带内消息 3 天后即超出窗口，**永不归档、永不删除**，存储控制目标对不规则时间线失效
- **Bug 代码**：

```python
# chat_archiver.py:154-165 - 窗口固定 [now-13d, now-3d)，与 10 天调度周期精确铺贴
ChatHistory.created_at >= end_date,      # now-13d
ChatHistory.created_at < start_date,     # now-3d

# chat_archiver.py:56-96 - offset 分页 + 处理中物理删除用户消息，用户集合收缩使后续用户被跳过
user_stmt = (select(distinct(ChatHistory.user_id)).limit(batch_size).offset(offset))
```

- **根因**：窗口只覆盖「3-13 天前」固定带，错过的带无任何补扫机制（无「归档水位线」记录）；overlap 检查（:138-151）对部分重叠**整窗跳过**而非只处理未覆盖部分；offset 分页在数据集变化下经典漂移
- **影响**：跳过带的 ChatHistory 永久驻留（is_archived=False 且无清理路径）；与 docstring「每 10 天执行一次，将 3-13 天前的对话……硬删除」承诺不符
- **触发条件**：调度晚点/早点/跨批用户删除任一发生（nominal 10 天整点路径恰好工作，容差为零）
- **验证方式**：把 IntervalTrigger(days=10) 改 days=9 复跑两轮，第二轮窗口与上一摘要重叠即整窗跳过

### DB5 [P3] 异常清单手抄不全——单用户 content=None 中止整轮归档

- **现象**：reasoning 模型返回 `choices[0].message.content=None`（思考内容在 reasoning_content）时，`None.strip()` 抛 AttributeError 穿透三层 except，剩余全部用户本轮归档中止
- **Bug 代码**：

```python
# chat_archiver.py:238 - 无 None 防护
summary = response["choices"][0]["message"]["content"].strip()

# chat_archiver.py:247/:203/:86 - 三层 except 元组均为手抄同一五元组，缺 AttributeError/KeyError
except (ValueError, TypeError, RuntimeError, OSError, SQLAlchemyError) as e:
```

- **根因**：call_llm 返回 OpenAI dict 无结构防护（LLM3 家族）；异常元组在 :86/:103/:203/:247 四处逐一手抄且不含 AttributeError/KeyError——「except 家族清单逐处复制」模式（EC 家族变体）
- **影响**：一个用户的坏响应使 archive_all_users 中途夭折（per-user 容错设计失效）；KeyError（响应缺 choices）同路径
- **触发条件**：模型侧返回 content=null 的响应一次即可
- **验证方式**：mock call_llm 返回 {"choices":[{"message":{"content":None}}]} 调 _archive_user

### DB6 [P3] conversation_id 生成 SQLite 侧无并发防护 + 无唯一约束

- **现象**：SQLite 部署下同一用户并发首条消息 → 双方读到相同 max → conversation_id 重复；或一方 INSERT 撞锁 500
- **Bug 代码**：

```python
# add_history.py:30-35 - SQLite 显式跳过并发防护
try:
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:uid), hashtext('conversation_id'))"), ...)
except Exception:
    pass  # SQLite 或不支持 advisory lock 的数据库

# app/models/history.py:12 - 仅单列索引，无 (user_id, conversation_id) 唯一约束
conversation_id = Column(Integer, nullable=False, index=True)
```

- **根因**：max+1 读改写仅 PG 侧有 xact lock 兜底（持锁到 commit，语义正确）；SQLite 侧依赖「单写者」假设但读-读-写交错仍可双写同 id；表层无唯一约束兜底
- **影响**：对话归属错乱（消息混入他人会话视图）/ 500；与 DB3 锁冲突面叠加
- **触发条件**：SQLite + 同用户毫秒级并发两条消息
- **验证方式**：asyncio.gather 两条 save_history_to_db(conversation_id=None)

### DB7 [P3] 历史搜索只匹配每会话最新一条 + 列表/计数双语义失配

- **现象**：关键词命中会话早期消息但最新一条不含关键词 → 会话从列表漏召回；分页总数与列表口径不一致
- **Bug 代码**：

```python
# search_history.py:49-58 - 关键词过滤套在「每会话最新一条」结果集上
stmt = select(History).where(and_(History.id.in_(max_ids_subquery), History.user_id == user_id))
if prompt_keyword:
    stmt = stmt.where(History.prompt.like(f"%{escaped_keyword}%", escape="\\"))

# search_history.py:121-135 - 计数函数却把关键词放子查询内（任意一条命中即计入）
if prompt_keyword:
    subquery = subquery.where(History.prompt.like(...))
subquery = subquery.group_by(History.conversation_id).subquery()
```

- **根因**：列表与计数两函数对同一关键词使用两种语义（列表=最新一条命中、计数=任一条命中）；auth.py:300-308 同时消费两者做分页
- **影响**：搜索漏召回 + 翻页总数虚高/空页
- **触发条件**：用户在历史列表输入关键词搜索
- **验证方式**：同会话两条消息，旧消息含关键词新消息不含 → 列表 0 条、count 1

### DB8 [P3] get_recent_context 死方法 + 接线即无界查询

- **现象**：方法全库零生产消费（GirlAi 实际走 get_lightweight_context，仅测试引用）——**死代码家族第 38 处**
- **Bug 代码**：

```python
# chat_history_service.py:27-39 - 3 天窗口查询无 limit，一旦接线即全量加载
recent_stmt = (select(ChatHistory).where(and_(
    ChatHistory.user_id == user_id,
    ChatHistory.created_at >= three_days_ago,
    ChatHistory.is_archived == False)).order_by(ChatHistory.created_at.desc()))
```

- **根因**：GirlAi 侧另写轻量版（MAX_HISTORY_MESSAGES=10），重版遗留；无界查询是 PM/AGM 家族「无上限加载」同款
- **影响**：死代码 + 未来接线者的 OOM/上下文爆炸地雷
- **触发条件**：接线或误用
- **验证方式**：rg "get_recent_context" 全库仅定义与测试

### DB9 [P3] WS 日志流轮转即失明 + 错误无退避重推 + 相对路径

- **现象**：日志归档（log_archiver.py:297 shutil.move）后，流端点静默直到新文件长回旧 position；异常时错误 JSON 每 0.3s 重复推送；log_dir 默认相对路径
- **Bug 代码**：

```python
# log_server.py:82,88-93 - position 只增不减，文件被 move 后永不重置
position = log_file.stat().st_size
while True:
    ...
    await f.seek(position)
    new_content = await f.read()
    if new_content:
        position = await f.tell()
    ...
    await asyncio.sleep(0.3)
except (ValueError, TypeError, RuntimeError, OSError, SQLAlchemyError) as e:
    yield json.dumps({...error...})   # 无退避，0.3s 后原样再推
```

- **根因**：tail 实现无「文件 size < position → 重置 0」的轮转感知；异常分支无连续错误计数/退避；`Path("logs")` CWD 漂移（GRD3/AIC1 家族）
- **影响**：v2 admin 日志流端点（Controller.py:206）在轮转后失去观测能力——排障工具在最需要时失效
- **触发条件**：日志归档任务执行一次（每 7 天）或手动轮转
- **验证方式**：连接 WS 日志流后手动 mv app.log app.log.bak && touch app.log，写入新日志无输出

### DB10 [P3] PermissionService 先查后插竞态 + 文件头注释路径不符

- **现象**：并发注册同一邮箱的两次请求均通过 create_permission_if_not_exists 查空 → 双插 Permission 行（表无 user_id 唯一约束，149 轮 MD2 服务层双确认）
- **Bug 代码**：

```python
# permission_service.py:1 - 文件在 app/db/，头注释声称 services/
# app/services/permission_service.py

# permission_service.py:23-28 - 查空即插，无锁无唯一约束兜底
stmt = select(Permission).where(Permission.user_id == user_id)
...
if not permission:
    permission = await self.create_permission(user_id, level)
```

- **根因**：TOCTOU + MD2 缺唯一约束两层叠加；头注释路径与实际不符（AIC 家族判定要点，迁移即破坏 import 路径认知）
- **影响**：重复权限行（get_permission scalar_one_or_none 多行时抛 MultipleResultsFound → 登录 500）
- **触发条件**：注册接口并发双击/重试
- **验证方式**：asyncio.gather 两次 create_permission_if_not_exists 同 user_id

### DB11 [P3] 时间语义三态在 db 层延续

- **现象**：同一 models.py 内两种时间默认混用；ConversationMessage.to_dict 的 timestamp 字段随时区漂移
- **Bug 代码**：

```python
# db/models.py:62-63 - 本地 naive 时间（对比 :21-22 aware UTC lambda）
created_at = Column(DateTime, default=datetime.now, nullable=False)

# db/models.py:140 - naive 值按本地时区解释，CST 服务器时间戳前移 8h
"timestamp": int(self.created_at.timestamp()) if self.created_at else 0,
```

- **根因**：MD4/MD3「时间语义三态混用」在 app/db/models.py 的延续；SQLite 丢 tzinfo 读回 naive 后 `.timestamp()` 本地化解释
- **影响**：conversation_store 消费 to_dict 下发的 timestamp 与真实 UTC 偏差 TZ 秒数；WorkflowHistory 时间字段与其他表不可比
- **触发条件**：服务器时区非 UTC（部署即默认）
- **验证方式**：TZ=Asia/Shanghai 下插入后读 to_dict 比对 time.time()

### DB12 [P3] schema 管理双轨（create_all + alembic）+ 两个一次性脚本零接线

- **现象**：main.py:280 run_async_migrations（alembic，versions/ 14 个迁移）与 main.py:239 create_all(checkfirst) 并行生效；init_workflow.py/clear.py 零 import
- **Bug 代码**：

```python
# main.py:239 与 :280 - 同一次启动两条建表路径
await conn.run_sync(Base.metadata.create_all, checkfirst=True)
...
await run_async_migrations()
```

- **根因**：checkfirst 兜底掩盖迁移漏项（db/models 4 表是否全在迁移版本中不可证，靠 create_all 补）；两套 schema 演化互不知晓（SCT6 双份配置家族在 schema 管理层的变体）；init_workflow docstring「创建 workflow_history 表」实际 create_all 全部表
- **影响**：迁移与实际 schema 漂移不可检测；新表可能只进 create_all 不进 alembic，PG 迁移部署即缺表
- **触发条件**：新增表只写 models 不写迁移（或反之）
- **验证方式**：对照 alembic versions/ 与 create_all 建出的表清单 diff

### DB13 [P3] cleanup_files_task N+1 + TOCTOU + file_path 未校验直接 rmtree

- **现象**：全量加载软删除文件逐行查任务关联；exists→remove 竞态；DB 记录的 file_path 无任何路径校验即 os.remove/shutil.rmtree
- **Bug 代码**：

```python
# scheduler.py:49-53,77-81
if os.path.exists(file.file_path):
    if os.path.isfile(file.file_path): os.remove(file.file_path)
    elif os.path.isdir(file.file_path): shutil.rmtree(file.file_path)
...
tasks = (await db.execute(select(Task).where(Task.input_file_id == file.id))).scalars().all()  # 每文件一查
```

- **根因**：O(N) 全量加载 + N+1 查询（重用户数千文件）；路径信任 DB 记录无白名单/前缀校验（GO2「启发式删除」家族在定时任务的实例）；TOCTOU 与 DB2 双跑竞态叠加放大
- **影响**：慢查询阻塞事件循环（async 内同步 os I/O，VK1 家族）；误配置/脏数据时 rmtree 误删目录树
- **触发条件**：文件量增长后每次 7 天周期
- **验证方式**：千行 File 表单轮耗时统计 + 逐文件 SQL 计数

## 4. 潜在问题与未知点

- alembic versions/ 14 个迁移对 db/models 4 表（project_sessions/workflow_history/image_generation_history/conversation_messages）的覆盖清单未逐一核对（DB12 验证项）
- add_history 的 PG advisory lock 在 aiosqlite 之外的真实 PG 部署尚未实测（hashtext 双参形式依赖 PG 版本）
- Controller.py 日志流 log_type 参数集固定三键（app/error/debug）与 logging.py 实际落盘文件清单的一致性未交叉
- GirlAi clear_user_history 清空 ChatHistory 但保留 ChatSummary——摘要与原文失配的体验影响未评估

## 5. 修改建议（改什么 → 达成什么目的）

| # | 优先级 | 修改动作 | 达成目的 | 涉及位置 | 对应 Backlog |
|---|--------|---------|---------|---------|-------------|
| 1 | P2 | engine 加 connect 事件钩子执行 `PRAGMA foreign_keys=ON`（SQLite 分支）+ 部署文档二选一（SQLite 开 PRAGMA 或切 PG 补 ondelete） | MD1 级联矩阵在默认部署生效 | database.py:7-17 | #1175 |
| 2 | P2 | 调度任务加环境变量开关（ENABLE_SCHEDULER 仅 worker 0 开）或分布式锁；uvicorn --workers 1 + 独立调度进程为替代方案 | 消除定时任务双跑 | Dockerfile:91 + main.py:287 + scheduler.py | #1176 |
| 3 | P2 | connect_args 增 `timeout`(busy_timeout) + startup 执行 `PRAGMA journal_mode=WAL`（主库统一一处） | 并发写锁冲突消除 | database.py:16 | #1177 |
| 4 | P3 | 归档改水位线模型（记录 last_archived_at，窗口 [水位线, now-3d)），分页改 keyset（id > last_id） | 时间带不再逃逸 | chat_archiver.py:56-165 | #1178 |
| 5 | P3 | 异常元组收敛为模块级常量并补 AttributeError/KeyError/JSONDecodeError + content None 防护走 fallback | 单坏响应不中止整轮 | chat_archiver.py:86/:103/:203/:238/:247 | #1179 |
| 6 | P3 | History 加 UniqueConstraint(user_id, conversation_id) + SQLite 分支 INSERT 捕获 IntegrityError 重取 max | 并发会话 id 唯一 | app/models/history.py:12 + add_history.py:37-42 | #1180 |
| 7 | P3 | 列表与计数统一「任一条命中」语义（关键词移入子查询） | 搜索召回与分页一致 | search_history.py:49-58/:121-135 | #1181 |
| 8 | P3 | 删除 get_recent_context 或补 limit 后接线 | 消除第 38 处死代码 | chat_history_service.py:12-63 | #1182 |
| 9 | P3 | stream 循环检测 size < position 即重置 0 + 连续异常计数退避 + log_dir 走 settings | 轮转后流不失效 | log_server.py:69-118 | #1183 |
| 10 | P3 | Permission 表加唯一约束（MD2 落地）+ create 改 upsert；修正文件头注释 | 竞态消除 + 路径一致 | permission_service.py + app/models/Permission.py | #1184 |
| 11 | P3 | db/models 时间默认统一 aware UTC lambda；to_dict timestamp 改 `created_at.replace(tzinfo=timezone.utc).timestamp()` | 三态收敛一层 | db/models.py:62-63/:98/:127/:140 | #1185 |
| 12 | P3 | schema 管理收敛 alembic 单轨（create_all 降级为 dev 开关）；init_workflow/clear 移 scripts/ 或删除 | 漂移可检测 | main.py:239/:280 + 两脚本 | #1186 |
| 13 | P3 | cleanup 改批量 IN 查询 + 路径前缀白名单校验 + 批次上限 | N+1 消除 + 误删面收窄 | scheduler.py:27-96 | #1187 |

## 6. 演化方向关联

- **统一收敛（§5.6 支柱 1）**：DB1（PRAGMA/部署形态二选一）与 DB12（schema 单轨）是「一套部署真相」的基础设施前提；db/models.py 与 app/models/ 的命名混淆建议迁移期改名 db_models 或并入统一 models 包
- **平台化**：DB2/DB3 决定 SQLite 形态能否支撑多 worker——长期方向是 PG 化（ondelete 级联 + advisory lock 已就绪）+ 调度独立进程（或改用 celery beat，与现有 celery 栈收敛）
- **「定时任务三态」主线**：ChatArchiver（活跃但零容差 DB4/DB5）、scheduler（活跃但双跑 DB2）、log_server（活跃半接 DB9）——与 DR7「验证任务从不验证」同属「调度存在 ≠ 任务正确」家族
- **死代码家族**：DB8 为第 38 处（get_recent_context 零生产消费）；clear.py/init_workflow.py 两个一次性脚本建议随 DB12 收敛一并归位 scripts/
