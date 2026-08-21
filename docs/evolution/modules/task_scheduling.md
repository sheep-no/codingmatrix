# task_manager.py + task_dispatcher.py + resume_manager.py 任务调度家族

> 第一百二十八轮补扫 | v1.129 | 2026-08-17 | 分析对象：`app/utils/task_manager.py`（330 行，Redis 异步任务队列）+ `app/utils/task_dispatcher.py`（60 行，任务处理器注册表）+ `app/utils/resume_manager.py`（161 行，分片上传断点续传）
>
> 结论：**任务分发设计断裂——task_manager 真实消费（aiGeneratorPptx 六个生成任务）、task_dispatcher 与 resume_manager 均为零消费死代码——task_type 注册表从未接入 task_manager 的执行链路（调用方直接传 func），Redis 故障时任务状态内存/Redis 分裂双轨**。

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
