# resource_guard.py + dynamic_concurrent.py + dynamic_chunker.py + system_load.py 资源与并发控制

> 第一百一十八轮补扫 | v1.119 | 2026-08-17 | 分析对象：`app/utils/resource_guard.py`（195 行）+ `app/utils/dynamic_concurrent.py`（167 行）+ `app/utils/dynamic_chunker.py`（106 行）+ `app/utils/system_load.py`（214 行）
>
> 结论：**资源与并发控制四件套——ResourceGuard（资源阈值）+ ConcurrentLimitManager（并发限制）+ DynamicChunker（上传分片）+ SystemLoadMonitor（负载快照）**——核心风险在并发限制的原子性（TOCTOU 超限）与负载采集的同步阻塞/内部 API 紧耦合。

## 一、模块定位

| 模块 | 职责 | 消费方 |
|------|------|--------|
| resource_guard.py | 资源阈值检查 + 安全并发建议（2/3/4） | system_load.is_system_overloaded、orchestrator |
| dynamic_concurrent.py | 按角色并发限制热调整 + 审计 + 负载推荐 | 会话/请求准入 |
| dynamic_chunker.py | 上传分片大小自适应（1MB-50MB） | 大文件上传 |
| system_load.py | 系统负载快照（TTL 1s）+ 过载判断 + 模型负载评分 | dynamic_model_router、orchestrator |

## 二、缺陷清单

### P2（3 项）

- **DCC1 [P2] ConcurrentLimitManager 单例 `__new__` 构造竞态——`if False else None` 死代码标志（同 CRY6/DCC2 家族）**——dynamic_concurrent.py:45 `_lock = threading.Lock() if False else None`——作者显式写锁又禁用它；:47-51 `__new__` 无锁双检——多线程首次并发构造：线程 A `_instance is None` → `super().__new__` 创建 A' 并赋值 `_instance`；线程 B 同判 → 创建 B' 覆盖 `_instance`——A' 的 `__init__` 已跑（设 `_initialized=True`）但 B' 的 `__init__` 见 `_initialized=False` → **重新初始化覆盖 limits/active_sessions**——并发下限额配置丢失。修复方向：模块级 `threading.Lock()` + 正确双检或直接 `lru_cache`。
- **DCC2 [P2] `can_create_session` 与 `register_session` 分离——检查与注册非原子（TOCTOU）→ 并发超限**——dynamic_concurrent.py:107-116 检查 `active < limit` 与 :118-120 单独 `register_session` 非原子——**N 个并发请求同时通过检查 → 全部注册 → 实际并发数超过限额**（free=1 可并发 2+）——限流失效。修复方向：原子 increment 带上限（`if active < limit: active += 1` 单方法完成）。
- **SL2 [P2] `_get_model_queue_depths` 同步阻塞事件循环 + active/reserved 双重计数虚高**——system_load.py:112 `celery_app.control.inspect(timeout=2.0)` 同步阻塞（内部 socket 等待，每个 worker 一轮）——async 协程内直接调用 → **高负载下快照采集卡 2s+ 阻塞事件循环**（每轮 get_load_snapshot）→ 路由决策延迟；且 :114-115 active + reserved 分别遍历**同一任务在两个集合中重复计数**（任务从 reserved 转移到 active）→ 队列深度虚高 → 负载评分失真。修复方向：`inspect` 移到线程池（`asyncio.to_thread`）+ 去重（按 task id）。

### P3（9 项）

- **RG1 [P3] ResourceGuard 非 psutil 分支静默失真——内存检查失败即跳过、cpu 恒 0**——resource_guard.py:54-55 `/proc/meminfo` 读取 OSError → 静默跳过内存检查（只查磁盘）；:143 `get_resource_status` cpu 恒 0——依赖资源判断的调用方（system_load.is_system_overloaded 用 `max(resources)`）得到**偏低失真**的负载信号。修复方向：失败时标记指标缺失而非静默 0。
- **RG2 [P3] `psutil.cpu_percent(interval=0.5)` 同步阻塞 0.5s**——resource_guard.py:26/:68/:105——在 async 上下文（system_load 是 async 协程链）直接调用——每次检查阻塞事件循环 0.5s（与 SL2 同族）。修复方向：interval=0 用两次采样差值或移线程池。
- **DC1 [P3] DynamicChunker `upload_speed_history` 只增不删——内存无限增长**——dynamic_chunker.py:54 每次上传 append——无上限裁剪（仅 reset 全清）——长期运行内存累积。修复方向：定长 deque。
- **DC2 [P3] DynamicChunker 可变实例状态无锁——并发上传共享实例竞态**——current_chunk_size/consecutive_failures 无同步——并发上传互相改写分片大小与失败计数（一次失败计数污染全局降片）。修复方向：per-session 实例或锁。
- **DCC3 [P3] 会话泄漏无自动补偿——异常路径 register 后未 unregister → 用户被永久拒绝**——dynamic_concurrent.py 注释 :40-42 自认「否则 active_count 会泄漏，导致用户被错误拒绝新会话」——register/unregister 靠调用方约定成对，异常/超时路径漏调即永久泄漏——无兜底（会话 TTL/心跳清理）。修复方向：会话超时回收。
- **DCC4 [P3] `_change_log` 无限增长**——dynamic_concurrent.py:99 append 永不清——仅 get_change_history 尾部读取。修复方向：定长环形。
- **DCC5 [P3] `update_limit` new_limit 无边界校验——负数/超大值直通**——dynamic_concurrent.py:88-89——`-1` → `active < -1` 恒 False → 全员拒绝；`100000` → 限流失效。修复方向：0 < new_limit <= 上限。
- **SL1 [P3] `_get_active_requests` 直接访问 rate_limiter 私有内部 `_config`/`_lock`/`_history`——紧耦合中间件私有 API**——system_load.py:100-104——rate_limiter 重构（v1.114 已详档）即静默 except 返回 0 → active_requests 失真；且 global_key 单窗口计数——窗口切换瞬间计数断崖归零。修复方向：rate_limiter 暴露公共 `get_active_requests()`。
- **SL3 [P3] psutil 缺失环境负载信号全 0——过载判断失真**——system_load.py:155-157 ImportError → `{'cpu': 0.0, ...}`——`is_system_overloaded` 的 `max(resources)` 恒 0 偏低 → 过载不触发（与 RG1 同族）。修复方向：缺失标记 + 保守默认。

## 三、全库交叉确认

- **并发限额家族**：ConcurrentLimitManager 是项目会话准入的限额来源——DCC2 原子性缺失使 free=1 并发可 2+——与 rate_limiter（v1.114）、dynamic_model_router 的并发控制构成三层并发防线——**中间层（本模块）最薄弱**。
- **异步阻塞家族**：RG2（interval=0.5）与 SL2（inspect 2s）同族——async 链路内同步阻塞——与 process_guard PG2 卡死模式不同（短阻塞 vs 永久挂起）但同族。
- **静默失真家族**：RG1/SL3（指标缺失静默 0）——与 file_operator FO7（编码静默丢）、encryption CRY5（吞错）同族。
- **内存增长家族**：DC1/DCC4——与 process_guard 熔断状态、crypto 密钥缓存同族。
- **单例竞态家族**：DCC1——与 crypto.py CRY6、resource_guard 单例（:191-194 无锁）同族。

## 四、测试状态

零单元测试。DCC2 并发超限、DCC1 构造竞态、SL2 队列双重计数、RG1 失真均无测试约束。修复建议：① 并发限额原子性压力测试（N 并发 register 断言不超过 limit）；② 队列深度去重测试（active+reserved 同 task id）；③ 资源缺失指标测试（非 psutil 环境断言标记缺失）；④ 会话泄漏兜底测试。
