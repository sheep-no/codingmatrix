# conversation_store.py 深扫详档

> 版本：v1.69 | 日期：2026-08-09 | 文件：`app/agent/conversation_store.py`（317 行，ConversationStore 单类 + 模块级单例）
> 结论：**P2 4 项（CS1 实测、CS2/CS3/CS4 静态）、P3 4 项**｜单元测试：零

## 定位

Redis + 数据库混合会话历史存储。设计原则（docstring :4-14）：数据库是 source of truth、写入先 DB 后 Redis、读取先 Redis miss 从 DB 回填、实时双写无后台任务。消费方：orchestrate_endpoints.py（:297-312/:378 多轮会话历史加载 + 用户/助手消息追加）。

## 跨模块引用链

| 方向 | 模块 | 位置 | 用途 |
|------|------|------|------|
| 被消费 | orchestrate_endpoints.py | :298 `get_history_async`；:301 `truncate_history`；:312/:378 `append_message` | 多轮会话历史 |
| 依赖 | app.db.database.async_session + ConversationMessage | :115-127/:171-185 | DB 读写 |
| 依赖 | redis（同步客户端） | :44 `redis.from_url(decode_responses=True)` | Redis 读写 |
| 死代码 | compress_history | :247-303 **全库零生产调用方** | 历史 LLM 压缩（未接线） |
| 测试 | — | — | **零测试** |

## 关键代码路径

`append_message`（:143）：先 DB `_save_message_to_db` → 同步 `get_history` 读 Redis 列表 → append → `setex` 全量写回。`get_history_async`（:77）：Redis get → miss 走 `_load_from_db_async`（async_session 全量）→ 回填 Redis。`truncate_history`（:215）：纯规则截断。`compress_history`（:247）：LLM 摘要 + clear/re-append（死代码）。

## Bug 清单

### P2

**CS1 [P2] `append_message` 「读-改-写」非原子 → 并发丢消息 + async 上下文 Redis miss 短路覆盖（实测）**

- 位置：:159 `get_history`（读）→ :160 `append` → :161 `setex`（全量写回）——三步无原子性
- 实测（await 让出模拟并发 IO）：
  ```
  并发 append 3 条后 Redis 存：['消息C']  -> last-write-wins 丢 2 条
  ```
- 次生问题：`append_message` 是 async 但内部调**同步** `get_history`（:159）——Redis miss 时 `_load_from_db_sync`（:99-110）在 async 上下文 `loop.is_running()` True 返回 `[]`（:104-106）→ messages=[] → Redis 被覆盖为只有最新一条（历史缓存丢失，DB 仍在）
- 影响：多轮会话并发（同 session 并行请求）丢消息；Redis 缓存内容不完整
- 修复方向：Redis 用 RPUSH/pipeline 原子追加（存消息列表而非 JSON 全量），或 Lua 脚本原子读改写；async 方法内改 redis.asyncio

**CS2 [P2] DB 写失败仍写 Redis → 幽灵消息破坏「DB 是 source of truth」声明（静态确认）**

- 位置：:155 `db_success = await self._save_message_to_db(...)` → :157-161 **无 `if db_success:` 短路**，DB 失败仍写 Redis
- 影响：DB 写失败（连接断/约束错）时 Redis 存了 DB 没有的消息；`get_history` Redis 命中优先返回（:62-63）→ 幽灵消息进历史上下文——**权威声明（:5）在故障路径被违背**，且注释 :164「下次读取会从数据库回填」不成立（回填只在 miss 时，Redis 命中不查 DB）
- 修复方向：db_success=False 时跳过 Redis 写 + 返回可辨识失败状态

**CS3 [P2] `compress_history` clear + re-append 非事务 → 中途失败丢历史；且全库零调用（静态确认）**

- 位置：:294 `await self.clear_history(...)` 清空 DB 旧数据 → :295-296 逐条 re-append——**无事务包裹**：DB 中途失败（连接断）→ 历史部分丢失；压缩期间并发 append 的消息被 clear 误删；压缩期间读取窗口读到空历史
- **死代码确认**：rg 全库 `compress_history` 仅定义处——历史压缩能力从未接线（设计存在、功能未激活，同 memory MEM2 压缩 / spec_cache SC1 async 家族）
- 修复方向：DB 层用事务 + delete/insert 原子替换；并发控制（压缩时锁 session）

**CS4 [P2] `_estimate_tokens` 注释与实现不符 + 英文 token 高估 2 倍 → 历史过早丢弃（静态确认）**

- 位置：docstring :33 声称「中文约 1.5 字/token，英文约 4 字符/token」，实现 :37 `return len(text) // 2`——总字符/2
- 影响：英文消息实际 ≈4 字符/token，实现按 2 字符/token 高估 2 倍 → `truncate_history`/`compress_history` 的 max_tokens=4000 预算下英文对话被过早截断（丢弃本可保留的历史）；注释与实现漂移（AR3/OP8/SFG1 家族）
- 修复方向：按 docstring 实现双语估算，或统一为单一口径并在常量处注明

### P3

**CS5 [P3] async 方法内同步 Redis 阻塞事件循环**

- `redis.from_url`（:44）同步客户端；`get_history_async` :83 `self.redis.get`、`append_message` :159/:161 全同步网络 IO 在 async 上下文直接执行——高并发下阻塞事件循环（应 redis.asyncio）

**CS6 [P3] `get_history` / `get_history_async` 双实现重复**

- :50-75 与 :77-97 逻辑几乎相同（Redis 读 + DB 回填 + 写回），DRY；sync 版 `_load_from_db_sync` 的 async 短路（:104）是 CS1 次生问题的源头——sync/async 语义纠缠

**CS7 [P3] 模块级单例 `get_conversation_store` 无锁**

- :310-317 全局 `_store` 懒加载无锁（ERL5/MCP1/SM1 家族）；且消费方每次调用重复 `getattr(settings, 'REDIS_URL', ...)`

**CS8 [P3] `truncate_history` 轮次语义按 ×2 假设**

- :232 `max_messages = max_rounds * 2` 假设每轮恰好 user+assistant 2 条——tool/system/summary 消息混入后「10 轮」实际保留条数不定（10-30 条），与 docstring「每轮 = user + assistant」（:225）不符

## 与既有主线闭环

- **写安全主线**：CS3 的 clear+re-append 非事务（CP5/OF2/SM10 DB 同步面家族）——「先清后写」破坏故障原子性；CS2 在故障路径违背「DB 权威」声明
- **并发主线**：CS1 读改写竞态（MCP1 连接竞争、SM1 Queue、TR4 信号量家族）——Redis 客户端是共享全局单例，并发 append 是本模块最大风险面
- **成本/上下文主线**：CS4 token 高估 → 历史窗口利用率低（memory MEM4 同款「字符当 token」）；compress_history 死代码使「LLM 摘要压缩」能力缺失（memory MEM2 压缩阈值颠倒同侧）
- **「存在≠正确」主线**：CS1 Redis 覆盖为单条 + CS2 幽灵消息——存储层数据完整性与权威性在故障/并发路径失真

## 状态校准（2026-09-23 复核）

以当前代码（317 行，与建档时一致）逐条复核，并补齐回归（原文档称「零测试」，实际 `tests/unit/test_conversation_store.py` 已有 19 项，本批增至 22 项）。

| 编号 | 状态 | 说明 |
|------|------|------|
| CS1 | 已修 | `append_message` 的「读-改-写」改为 Lua 原子追加（`_APPEND_SCRIPT`：GET → decode → append → SETEX），Redis 单线程内不再 last-write-wins；并用实例级 `asyncio.Lock` 串行化「seed 读取 + DB 写入 + 原子追加」。次生问题（async 上下文调同步 `get_history` → `_load_from_db_sync` 短路返回 `[]` → 缓存被覆盖为仅最新一条、旧历史在 24h TTL 内不可见）修复为：Redis miss 时**先**取数据库历史作 seed（在写 DB 之前取，避免含本次消息），Lua 仅在 key 不存在时使用 seed，故并发 append 不重复历史、不覆盖完整缓存。跨进程 seed 竞态（多 worker）仍存在，属 CA2 同族，未在本批处理。 |
| CS2 | 已修 | `db_success` 为 False 时跳过 Redis 追加并记录 warning，不再产生「DB 没有、Redis 有」的幽灵消息；DB 失败返回 False 的语义保持。 |
| CS4 | 已修 | `_estimate_tokens` 由「总字符 / 2」改为按 docstring 口径分别估算（CJK ≈1.5 字/token、非 CJK ≈4 字符/token），消除英文高估约 2 倍导致的历史过早截断；同步更新 `TestEstimateTokens` 与 `test_truncate_by_tokens`/`test_compression_when_exceeded` 的预算口径，并新增中英混排用例。 |
| CS3 | **保留** | `compress_history` 仍全库零调用（未接线的历史压缩能力）且 clear + 逐条 re-append 非事务。事务化或删除该能力属独立决策，未在本批处理。 |
| CS5 | **保留** | async 方法内仍用同步 `redis` 客户端（阻塞事件循环）。迁移 `redis.asyncio` 与 CS6 的双实现收敛是同一模块级重构，应合并专项处理。 |
| CS6 | **保留** | `get_history` / `get_history_async` 双实现重复；收敛需先统一 sync/async 边界。 |
| CS7 | **保留** | 模块级单例 `get_conversation_store` 仍无锁。 |
| CS8 | **保留** | `truncate_history` 仍按 `max_rounds * 2` 假设每轮 user+assistant；tool/system 混入时轮次语义不准，属 P3。 |

**复核中一并修正**：`TestEdgeCases` 中三项用例（并发追加、特殊字符、超长内容）未声明 `test_db_setup`，此前依赖「DB 写失败仍写 Redis」的幽灵路径而通过。CS2 修复后这些用例暴露为失败，已补 `test_db_setup` 使其在隔离运行下也真实落库。
