# task_manager.py + task_dispatcher.py + resume_manager.py 任务调度家族

> 第一百二十八轮补扫 | v1.129 | 2026-08-17 | 分析对象：`app/utils/task_manager.py`（330 行，Redis 异步任务队列）+ `app/utils/task_dispatcher.py`（60 行，任务处理器注册表）+ `app/utils/resume_manager.py`（161 行，分片上传断点续传）
>
> 结论：**任务分发设计断裂——task_manager 真实消费（aiGeneratorPptx 六个生成任务）、task_dispatcher 与 resume_manager 均为零消费死代码——task_type 注册表从未接入 task_manager 的执行链路（调用方直接传 func），Redis 故障时任务状态内存/Redis 分裂双轨**。

> 后续变更（2026-09-16）：`app/utils/task_dispatcher.py` 已确认零生产引用并删除（`task_manager.py`、`resume_manager.py` 保留），正文保留扫描时的判定与行号。

## 一、模块定位

| 组件 | 位置 | 消费状态 |
|------|------|----------|
| TaskManager / task_manager | task_manager.py:31/:330 | aiGeneratorPptx.py:934/:1212/:1690/:1858 真实消费（create_task/get_task_info_async/cancel_task/update_progress） |
| TaskDispatcher / task_dispatcher | task_dispatcher.py:14/:60 | **零业务消费**——注册表/分发从未接入 |
| ResumeManager | resume_manager.py:30 | **零消费**——全库无外部引用 |

## 二、缺陷清单

### P2（7 项）

- **TM1 [P2] TaskManager `__new__` 单例初始化无锁——并发首调竞态**——task_manager.py:46-53——`if cls._instance is None` 后 new——多协程首次并发 → 多个实例，`_tasks`/`_running_tasks` 各自为政——DCC1 无锁单例家族（同 TD1）。
- **TM2 [P2] `_get_redis` 懒加载无锁——多协程并发创建多个 Redis 连接**——task_manager.py:55-59——`if self._redis is None: self._redis = redis.from_url(...)`——无锁竞态 → 连接泄漏/半初始化。
- **TM3 [P2] Redis 故障时静默降级内存——任务状态内存/Redis 分裂双轨**——task_manager.py:124-126/:195-198/:206-208——**同一任务 Redis 有旧状态、内存有新状态**——同步 `get_task_info`（读内存 `_tasks`）与异步 `get_task_info_async`（读 Redis）**返回不一致**——查询 API 可能拿到过期 PENDING 或丢失 SUCCESS——写 Redis 失败时任务状态永远 PENDING。修复方向：单写源 + 降级时标记，或 Redis 优先并在降级时告警。
- **TM5 [P2] `cleanup_old_tasks` 用 `r.keys(f"{TASK_PREFIX}*")` 全库扫描——生产 Redis 阻塞主线程**——task_manager.py:305——**KEYS 命令 O(n) 单线程阻塞**——每小时一次全库遍历（大规模 key 时阻塞数秒）。修复方向：SCAN 游标迭代。
- **TD1 [P2] task_dispatcher 零业务消费且与 task_manager 脱节——任务分发双轨设计断裂**——设计上 task_type 应通过注册表分发（`@task_dispatcher.register("ppt_generate")`）——但 aiGeneratorPptx.py:934 等直接 `task_manager.create_task(task_type, ..., func, ...)` 传函数——**注册表从未被 lookup**——task_type 参数形同虚设（执行端只认 func）——两组件意图配合却互不相连。修复方向：create_task 内按 task_type 查 get_handler 分发，或删除 dispatcher。
- **RM1 [P2] `save_chunk_state` 读-改-写非原子无锁——并发分片上传竞态丢状态**——resume_manager.py:66-78——多分片并发上传同时 `read_text` → 各自 append → 后写覆盖先写——**已完成分片记录丢失**→ 断点续传完整性破坏（validate_completed_chunks 依据的 hashes 不完整）。修复方向：文件锁（asyncio.Lock 按 upload_id）或原子写（tmp+rename）。
- **RM2 [P2] `upload_id` 直接拼接路径——路径穿越**——resume_manager.py:44 `self.resume_dir / f"{upload_id}.json"`——若 upload_id 含 `../`/绝对路径 → **任意路径写入/读取 .json**——断点续传场景 upload_id 若来自客户端则高危（当前零消费未暴露，接入时必查）。修复方向：upload_id 白名单校验（uuid 格式）。

### P3（10 项）

- **TM4 [P3] 同步 `get_task_info` 正常路径恒返回 None——形同虚设**——task_manager.py:210-216——`_tasks` 只在 Redis 写失败时填充（:126/:208）——正常路径内存空 → 同步 API 永远 None。
- **TM6 [P3] `task_type` 参数从未用于执行——类型校验/分发缺失**——task_manager.py:77-136。
- **TM8 [P3] 裸 `except:` 吞错**——task_manager.py:227/:323（datetime 解析失败静默）。
- **TM9 [P3] `REDIS_URL = "redis://localhost:6379/0"` 硬编码——多 worker 环境不可配置**——task_manager.py:18（config 未接入）。
- **TD2 [P3] `register` 同名 task_type 重复注册静默覆盖——无警告**——task_dispatcher.py:41。
- **RM3 [P3] `save_chunk_state` 无分片去重——同分片重复 append**——resume_manager.py:75。
- **RM4 [P3] MD5 非加密哈希——完整性校验非对抗场景**——resume_manager.py:48（分片可能被恶意覆盖时不可靠）。
- **RM5 [P3] 同步文件 I/O（read_text/write_text/read_bytes）包在 async 函数中——阻塞事件循环**——resume_manager.py:66-78/:102-115/:137-155。
- **RM6 [P3] 中断/失败上传残留 `.json` 状态文件——无清理机制**——resume_manager.py（clear_state 仅在合并完成后调用）。
- **RM7 [P3] 默认 `Path("uploads/.resume")` 相对路径——CWD 漂移**——resume_manager.py:39——GRD3/CRY3/PG10/SC3/PMC6 家族。

## 三、全库交叉确认

- **死代码家族**：task_dispatcher/resume_manager 与 retry/sentry/startup_alert 同族——**「完备封装但未接入」累计第五、六处**。
- **无锁单例家族**：TM1/TD1 与 CB1/HTTP4/SNT5/STA5/DCC1/SC2/CRY6 同族——第 10 处。
- **双轨设计断裂**：TD1（注册表 vs 直传 func）与加密/缓存/日志/HTTP 双轨同族——**任务分发是第十一处双轨**。
- **相对路径家族**：RM7 与 CRY3/PG10/SC3/PMC6 同族。
- **Redis 使用面**：task_manager 与 cache（Redis）、rate_limiter、security（session）共用 Redis——**但 REDIS_URL 三处各自硬编码/配置不一致**（本文件 localhost 硬编码）——Redis 配置未统一收敛。

## 四、测试状态

零单元测试。Redis 故障降级、内存/Redis 状态一致性、并发分片上传、KEYS 阻塞均无测试约束。修复建议：① 单例/Redis 懒加载加锁；② Redis 优先单写源 + 降级告警测试（Redis down 场景断言查询一致性）；③ cleanup 改 SCAN；④ save_chunk_state 原子写 + 并发测试；⑤ upload_id 白名单校验。

## 五、状态更新（2026-09-18 核实）

逐条对照当前代码后，本模块结论修正如下：

- **TM1 已修复**：`TaskManager.__new__` 改用 `_instance_lock = threading.Lock()` 双检锁。`__new__` 是同步方法，无法 `await` 既有的 `asyncio.Lock`，改用线程锁是正确的实现方式。
- **TM2 已修复**：`_get_redis` 懒加载纳入同一把 `_instance_lock` 双检，避免并发创建多个连接。
- **TM5 已修复**：`cleanup_old_tasks` 的 `await r.keys(...)` 改为 `async for key in r.scan_iter(match=...)`，消除 KEYS 全库阻塞。
- **TM8 部分修复**：`cleanup_old_tasks` 内裸 `except:` 收窄为 `except (ValueError, TypeError):`（仅吞 datetime 解析错误）。同步 `get_task_info` 路径的裸 except 未动。
- **RM1 已修复**：`ResumeManager.save_chunk_state` 增加按 `upload_id` 的 `asyncio.Lock`，并用「写 `.tmp` + `os.replace`」原子替换；`clear_state` 同锁保护。
- **RM2 已修复**：新增 `_UPLOAD_ID_RE` 白名单（`^[A-Za-z0-9_-]{1,64}$`），`_state_file` 对非法 `upload_id` 抛 `ValueError`，阻断 `../` 与绝对路径穿越。
- **RM3 已修复**：`save_chunk_state` 用 `if chunk_index not in completed` 去重，同一分片重复上报不再重复追加。
- **TD1 已消解**：`task_dispatcher.py` 已删除，注册表/分发双轨不复存在。
- **TM9 已修**：`REDIS_URL` 改为 `os.getenv("REDIS_URL", "redis://localhost:6379/0")`，与 `app/celery_app.py` 既有模式对齐，多 worker 环境可通过环境变量配置。
- **RM5 已修**：`resume_manager.py` 中 `save_chunk_state`/`get_resume_state`/`validate_completed_chunks`/`clear_state` 内的同步文件 I/O（`read_text`/`write_text`/`read_bytes`/`unlink`）统一改用 `asyncio.to_thread` 执行，新增 `_load_state` 辅助方法，不再阻塞事件循环。
- **TM3 基本消解 / TM4 为死方法**：生产调用方只用 `get_task_info_async`（`aiGeneratorPptx.py:2813/:3934`），其内部走 `_get_task_from_redis`，Redis 失败时回退同一内存快照，读写路径一致；且已叠加 SQL 双写（`_persist_sql_create`/`_persist_sql_update`）与 `reconcile_task` 对账。同步 `get_task_info` 全库零调用（仅 `_tasks` 在 Redis 失败时填充，正常路径恒 None），属死方法，未删。
- **TM6 非缺陷**：`create_task` 由调用方直接传入 `func` 执行，`task_type` 仅作元数据/落库字段，不存在需要按类型分发的注册表。
- **RM4/RM6/RM7 复核后不再单独处理（2026-09-22）**：`app/utils/resume_manager.py` 全模块零生产消费——除 `tests/unit/test_task_scheduling_utils.py`、`tests/unit/test_v4_8_features.py` 外，`rg "ResumeManager|resume_manager|ResumeState|compute_chunk_hash"` 在 `app/` 内除定义处无任何命中，`app/api/v1/file_upload.py` 的断点续传端点从未接入该管理器。RM3–RM7 全部落在这个死模块上，在原位修 MD5/路径/清理策略不产生任何生产收益。整体属「删除或接入」决策（与 TD1、SNT1/STA1 同族），删除需确认后执行。

新增回归测试 `tests/unit/test_task_scheduling_utils.py`（8 项）：回退源码后 `test_invalid_upload_id_rejected`、`test_duplicate_chunk_index_not_appended_twice`、`test_cleanup_uses_scan_and_removes_old_tasks` 三项失败。
