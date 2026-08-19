# cache.py + cache_decorator.py 缓存双轨

> 第一百一十九轮补扫 | v1.120 | 2026-08-17 | 分析对象：`app/utils/cache.py`（349 行，RedisCacheManager + MemoryCache + cached 装饰器）+ `app/utils/cache_decorator.py`（201 行，cache_response/invalidate_cache 装饰器）
>
> 结论：**缓存双轨——Redis 优先内存降级 + 两套装饰器（cached/cache_response）并存——最大风险是 cache_response 缓存键排除用户身份导致跨用户数据泄露（P1）**。

## 一、模块定位

| 层 | 组件 | 说明 |
|----|------|------|
| 后端 | RedisCache | Redis 异步，序列化/TTL/模式失效 |
| 降级 | MemoryCache | LRU 1000 条，Redis 不可用时 |
| 管理器 | RedisCacheManager | 统一接口，Redis→memory 自动降级 |
| 装饰器 A | cache.py `cached` | 通用 async 函数缓存（向后兼容） |
| 装饰器 B | cache_decorator.py `cache_response` | FastAPI 路由缓存（3 处使用） |

cache_response 使用方（app/api/v1/auth.py）：`/history`（:289，ttl 60）、`/user/profile`（:445，ttl 300）、`/conversations`（:479，ttl 120）——**三处全部按 user_id 返回个性化数据**。

## 二、缺陷清单

### P1（1 项）

- **CA12 [P1] cache_response 缓存键排除用户身份——三处个性化路由跨用户数据泄露**——cache_decorator.py:51 `if k not in ("request", "db", "token", "current_user", "user_id", "background_tasks")` 显式排除 token/user_id——`/user/profile`（auth.py:445）参数仅 (db, token)——db 非标量忽略、token 排除——**缓存键 = md5("profile:get_user_profile") 全站共键**——用户 A 首次请求后，**5 分钟内所有用户命中 A 的 profile（含 email/permission_level）**——P1 级隐私泄露。`/history`（:289）与 `/conversations`（:479）键含 query/body 参数但不含 user——**相同参数的不同用户互串历史/会话数据**。修复方向：缓存键强制并入用户身份（从 token 提取 user_id），或删除该三处装饰器改按用户 key 缓存。

### P2（4 项）

- **CA1 [P2] Redis 降级→恢复切换时缓存读一致性断裂——memory 值不可见**——cache.py:246-253 `RedisCacheManager.get`——set 时 Redis 失败落 memory（:259-260）且 `_is_connected=False`（:164）；随后 Redis 恢复 → `_ensure_connection` 重建 `_is_connected=True` → **get 走 Redis 返回 None（:251-252 短路 return None）而非 memory 值**——降级期间写入的缓存瞬间全部不可见。且 `set` 永远返回 True（:261）——**调用方无法知道数据落在哪层**。修复方向：get 优先 memory 检查或双读合并。
- **CA2 [P2] 跨进程内存缓存无法失效——分布式一致性假象**——`invalidate_pattern`（:270-275）清 Redis + 本进程 memory——**其他 worker 的 MemoryCache 残留过期数据**——多 worker 部署下失效不同步（RedisCacheManager 全局单例 per process）。修复方向：invalidate 走 Redis pub/sub 或全 Redis（memory 仅容灾不参与读命中写一致性）。
- **CA11 [P2] cache_response 缓存 Response 对象——Redis 后端命中返回字符串而非 Response**——cache_decorator.py:123-125 命中返回 `cached_value["_cached_response"]`——若原始 result 是 FastAPI `JSONResponse`/`Response` 对象：Redis 序列化 `json.dumps(value, default=str)`（cache.py:156）→ Response 变字符串 → **命中后返回字符串给 FastAPI → 响应结构破坏**——MemoryCache 存原对象正常——**双后端行为不一致**。修复方向：缓存前将 Response 转 dict（.body() 解码）。
- **CA18 [P2] `_generate_cache_key` 非标量/非 pydantic 参数静默忽略 → 不同参数缓存同键**——cache_decorator.py:34-48——dict/list 等参数不进键——路由参数含 dict 时不同请求命中同一缓存——数据串。修复方向：不可序列化参数 fallback 进键（repr 摘要）。

### P3（5 项）

- **CA3 [P3] cache.py `cached` 装饰器缓存 None 值永远穿透**——cache.py:341 `if cached_value is not None`——func 返回 None 被 set 缓存但 get 判 None 未命中——每次穿透重算（击穿）。修复方向：区分「缓存未命中」与「缓存 None」。
- **CA13 [P3] `invalidate_on` 触发清整个 key_prefix 前缀——误清同前缀其他路由缓存**——cache_decorator.py:116-117 `invalidate_pattern(f"{key_prefix}:*")`——粗粒度（同前缀不同路由/不同参数全清）。修复方向：按具体键失效。
- **CA16 [P3] `invalidate_cache` 在 func 抛异常时不执行失效——缓存残留过期数据**——cache_decorator.py:174 `result = await func()` 抛错 → 失效逻辑不跑。修复方向：finally 块执行。
- **CA5 [P3] Redis 宕机时每次操作重建连接（ping 超时 2s）——降级路径自身慢**——cache.py:109-130 `_ensure_connection` 失败置 `_redis=None` → 下次操作再建连重 ping——Redis 全宕时每次 get 卡 socket_connect_timeout（2s）——**雪崩时降级反而更慢**。修复方向：失败后冷却期跳过重建。
- **CA19 [P3] RedisCache.clear 用 `flushdb`——多应用共享 Redis 时清空他人数据**——cache.py:198——DB 级全清。修复方向：按 key_prefix 扫删。

## 三、全库交叉确认

- **CA12 是全库迄今首个经装饰器路径确认的 P1 跨用户数据泄露**——与 IM1（会话内容泄露）/SCT1/SCT5（已记 P1）同级别——但**缓存层泄露是 100% 命中复现**（非概率），且影响面是全部注册用户。
- **SCT6 家族（secret 处理）关联**：profile 含 email——泄露面含个人身份信息。
- **双轨模式**：cached（通用）+ cache_response（路由）两套装饰器并存——功能重叠（都做函数缓存）——与加密双轨（crypto/encryption）、CodeValidator 双轨同模式。
- **内存缓存降级家族**：CA1/CA2 与 file_operator 读缓存、resource_guard 内存缓存同族——降级路径一致性普遍缺失。

## 四、测试状态

零单元测试。CA12 跨用户泄露（最高危）无任何测试约束——三处使用方无 auth 集成测试覆盖缓存命中场景。修复建议：① 用户隔离缓存键参数化测试（不同 token 同参数断言不命中）；② Redis 降级恢复切换一致性测试；③ Response 对象序列化测试；④ 多 worker 失效同步测试。
