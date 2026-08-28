# 模块详档：app/services/（服务层）

> 轮次：第一百四十八轮 | 日期：2026-08-28 | 文件数：16 | 总行数：4300
> 扫描范围：apikey_manager / skill_registry / websocket_manager / model_config_manager / agent_memory_service / health_checker / custom_skill_manager / custom_provider_manager / resource_config / prometheus_metrics / websocket_manager / provider_health / log_config / rate_limit_config / feature_switch / audit_logger / user_preferences / __init__.py

## 1. 模块定位与状态判定

服务层，承载 API Key 管理、Skill 注册、模型配置、自定义供应商、资源/限流/功能开关配置、健康检查、WebSocket 推送、Agent 记忆、指标暴露等横切能力。

| 文件 | 行数 | 状态 | 消费方（引用数） |
|------|------|------|------------------|
| apikey_manager.py | 630 | 活跃 | 7（apikey.py、dynamic_model_router 等） |
| skill_registry.py | 296 | 活跃 | 8（orchestrator/agent 多处） |
| model_config_manager.py | 435 | 活跃 | model_config_api.py（v2 路由） |
| agent_memory_service.py | 367 | 活跃 | knowledge_endpoints.py:7/:25/:58/:88 |
| health_checker.py | 347 | 活跃 | health.py（v1 路由） |
| custom_skill_manager.py | 292 | 活跃 | skills.py:11 |
| custom_provider_manager.py | 273 | 活跃 | apikey.py:53、dynamic_model_router.py:941、main.py:245 |
| resource_config.py | 250 | 活跃 | feature_switch.py、guardian_router.py |
| audit_logger.py（services 版） | 218 | **死文件** | 全库零 import；活跃版为 utils/aicloud/audit_logger.py（被 aicloud.py 消费）——ADT2 双轨家族第 17 处的被取代侧确认 |
| prometheus_metrics.py | 211 | 活跃 | performance_monitor.py:60 |
| websocket_manager.py | 193 | 活跃 | 5（ws 路由、task 推送） |
| user_preferences.py | 179 | **死文件** | 全库零 import（grep 命中均为其他文件局部变量）；agent/user_preference_learner.py 是另一独立模块 |
| provider_health.py | 173 | 活跃 | apikey.py:24/:242 |
| log_config.py | 158 | 活跃 | guardian_router.py |
| rate_limit_config.py | 140 | 活跃 | middleware/rate_limiter.py:125/:331、guardian_router.py:776 |
| feature_switch.py | 128 | 活跃 | guardian_router.py（2） |
| __init__.py | 10 | 活跃 | 仅 re-export WebSocketManager/ws_manager |

## 2. 活跃面缺陷清单

### P2（5 项）

**AKM1 [P2] API Key 索引 TTL 被绝对重置，混合 TTL 下长效 Key 从管理面消失**
- apikey_manager.py:37 `store_key` 内 `EXPIRE index_key ttl+86400`——每次存新 key 都把该用户索引集合的 TTL 绝对重置为「本次 key 的 TTL + 1 天」。
- 场景：用户先存 10 年 key（index TTL=10y+1d），再存 1 小时 key（index TTL 被重置为 ≈25h）→ 25h 后索引集合过期 → 10 年 key 的 token 脱离索引 → `list_keys` 永久丢失该 key；key/meta 本体仍在 Redis（占内存成幽灵），用户不可见、不可管理、不可删。
- 缓解面：`get_key_by_token` 反向索引快路径仍可命中（LLM 调用链不受影响），丢失的是管理面（列出/状态更新/删除入口）。
- 修复：EXPIRE 改为相对延长（TTL 当前值与新值取 max）或索引 TTL 固定长值 + 空集合清理。

**CPM4 [P2] 自定义供应商 SSRF：base_url 用户可控，无内网地址/协议校验**
- custom_provider_manager.py:114-135 sync_models / :212-235 _test_openai / :237-261 _test_anthropic——服务端向用户提交的任意 base_url 发起 httpx 请求（GET /models、POST /chat/completions、POST /v1/messages）。
- 无 169.254.169.254/127.0.0.1/内网网段/非 http(s) 协议黑名单 → 可探测内网、打云元数据端点；api_key 随请求发出（用户自己的 key，泄露面有限，但 SSRF 本体成立）。
- 与 GH4/V2N2 同属服务端请求面家族。修复：URL 白名单校验（仅公网 http/https）+ 解析后二次校验 IP（防 DNS rebinding 需连接时校验）。

**PM2 [P2] Prometheus 指标 raw path 高基数，字典无限增长（内存泄漏）**
- prometheus_metrics.py:111-119 record_request 以 `labels={"method","path","status"}` 生成指标 key；消费方 performance_monitor.py:38/60 传入 `request.url.path`（原始路径，含 UUID/数字 ID）→ 每个不同 URL 生成新 key。
- `_counters`/`_histograms` 字典随请求 URL 多样性无限增长 → 进程内存缓慢泄漏 + /metrics 基数爆炸拖垮抓取。
- 修复：中间件改传 route template（`request.scope["route"].path`），或 label 值做模板化归一。

**CSK1 [P2] Skill 系统无真实身份归属：author 硬编码，配额全局共享，任意用户可改/删他人 Skill**
- skills.py:71 `author="api_user"  # TODO: 从认证信息获取`（上传与恢复端点 :204 同样硬编码）→ 所有用户共享同一 author 身份。
- 后果链：custom_skill_manager.py:136-138 `MAX_SKILLS_PER_USER=50` 配额按 author 统计 → 全站共享 50 个名额（先到先得占满）；update_skill(:163)/delete_skill(:201) 仅按 name 查找、无 author 归属校验 → 任意登录用户可改/删全站任意 Skill（IDOR，V2U 家族同型）。
- list_skills 全站共享 + Skill 内容注入 Agent prompt → 还有提示词投毒面（改他人 skill 内容影响其他用户的 Agent 行为）。
- 修复：author 接入真实 user_id + update/delete 增加 owner 校验 + 配额按真实用户。

**HC1 [P2] Celery 健康检查同步阻塞事件循环（探针高频放大）**
- health_checker.py:135-137 `celery_app.control.inspect().stats()/.active()`——Celery control inspect 是同步网络 RPC（每次 1s+ 超时预算），在 async check_celery 内直接调用 → 阻塞事件循环。
- check_all/check_ready 被 /health /ready 探针高频调用（K8s 默认周期秒级）→ 每次 Redis/Celery 抖动时整站请求被串行卡顿。
- VK1（aicloud_knowledge 上传阻塞）家族第 2 处。修复：`asyncio.to_thread()` 包装或 celery inspect 异步化 + check_all 改 `asyncio.gather`。

### P3（25 项）

**apikey_manager.py**
- **AKM2 [P3]** store_key 三步 setex（key/meta/reverse+index）非原子（:210-240），中途失败产生幽灵 token（index 有、key/meta 缺）；update_status/enabled/context_lengths/fallback_preference 四函数均为 GET→改→SETEX 读改写（:412-523），并发更新互相覆盖字段（CS1 家族）；get_metadata :274 `json.loads` 无 try，一个损坏 meta 使 list_keys/get_metadata 整体异常；update_status :432-434 `ttl==-1`（永不过期）时静默跳过更新。
- **AKM3 [P3]** API Key 与用户 token 在 Redis 明文存储（:210 setex 明文），docstring 声称「安全存储」；仓库已有 crypto/encryption 加密设施而未接线——「安全设施未接线」家族。
- **AKM4 [P3]** get_context_lengths_by_token（:309-336）/get_key_by_token SCAN 回退（:338-382）全表扫 `apikey_index:*`（注释自称低效；同模块 get_key_by_token 已有反向索引优化，context_lengths 版没有——一优一劣双实现）；:597 默认 Redis localhost:6379 硬编码（TM9 家族）；单例 :591-599 无锁（DCC1 家族）；get_fallback_preference_by_token :531 魔术数字 `len(token)<30`。

**model_config_manager.py**
- **MCM1 [P3]** save_config :219-221 直接 `open('w')` 非原子写；写一半崩溃 → JSON 损坏 → _load_config :116-118 catch 后 `_init_default_config()` **静默回退默认配置** → 下次任意保存全量覆盖 → 用户自定义配置永久丢失（配置静默重置家族，与 CSK2 同型）。
- **MCM2 [P3]** _sync_to_agent_config :275-276 同步失败仅 log → unified_model_config.json（管理面）与 agent_model_config.json（运行面）漂移：admin 界面显示新配置、运行时仍用旧配置，且无告警。双文件双轨结构本身即为漂移温床。
- **MCM3 [P3]** update_model/update_provider :302-304/:344-346 `hasattr→setattr` 任意字段注入：可改 `id` 字段造成 dict key 与对象 id 不一致（旧 id 键下挂新 id 对象）。
- **MCM4 [P3]** delete_provider :350-355 不级联检查引用 → 孤儿模型（model.provider 指向已删供应商，调用时 get_provider 返回 None）。
- **MCM5 [P3]** export_config :404-410 **全库零调用——死代码家族第 35 处**；且 vars() 导出含明文 api_key，若未来被接线到响应即泄露；:185 `__import__('datetime')` 内联 import；save_config 全量写两个文件（高频操作 IO 放大）。

**skill_registry.py**
- **SKR1 [P3]** :20 硬编码 `/workspace/data/custom_skills` 绝对路径（VK4 同族），与 custom_skill_manager.py:14 重复定义同一常量（双常量源）。
- **SKR2 [P3]** 单例 :264-270 无锁（DCC1 家族）；docstring 声称「热重载」实为手动 invalidate/reload_skill（半实现）；:91 datetime.utcnow() 弃用（SLG3 家族）。

**websocket_manager.py**
- **WSM1 [P3]** broadcast :168-172 发送失败的连接不清理（与 send_personal_message :124-130 清理逻辑不一致 → 死连接只能靠 personal 消息路径回收）；connect :54-65 锁内 `await websocket.accept()`（网络操作持锁，锁持有时间放大）；docstring 声称 "Automatic reconnection handling / Connection health monitoring"（:33-34）代码中无任何实现——文档谎言；:72 日志引用锁内变量 current_count（数值偏差）。

**agent_memory_service.py**
- **AME1 [P3]** get_session :47-52 / delete_session :338-345 仅按 session_id 全局查询/删除，无 user_id 归属参数——越权面依赖调用方过滤（knowledge_endpoints.py 三个调用点 :25/:58/:88，需确认是否先校验归属；与 WFA1 同型设计缺陷）；update_model_stats :283-322 SELECT→内存改→commit 读改写竞态丢计数（应 `UPDATE ... SET x=x+1`，CS1 家族）；delete_session 依赖 ORM cascade（app/models/agent_memory.py 未扫，下轮确认）；:80/:228/:307/:318 utcnow 弃用。

**health_checker.py**
- **HC2 [P3]** check_all :230-289 / check_ready :291-326 串行 await 六项检查（延迟叠加，Celery 项可达 2s+；应 gather）；check_api :42-63 恒真检查（try 包裹不可能失败的 uptime 计算——形式主义健康检查，永远 healthy）；:171 访问 `ws_manager._max_connections` 私有属性；单例 :339-344 无锁（DCC1 家族）。

**custom_skill_manager.py**
- **CSK2 [P3]** _save_metadata :71-76 非原子写；_load_metadata :67-68 JSONDecodeError 静默返回空 → 元数据损坏时全部自定义 Skill 变孤儿文件（文件在、注册表清空）。与 MCM1 同型（配置静默重置家族）。
- **CSK3 [P3]** 进程内存态不同步：self._metadata 每进程独立，_notify_registry :35-46 只 reload 本进程 registry；多 worker 部署时 A 进程上传 B 进程不可见/不可删（CS1 家族多进程变体）。
- 注：路径安全做得正确——name 正则白名单 :81 + category 白名单 :122 挡死目录穿越（正面点名）。

**custom_provider_manager.py**
- **CPM1 [P3]** providers 纯内存 dict 无持久化 → 重启丢失全部自定义供应商配置；apikey.py:_sync_provider_models 塞入的 `user_{provider}` 条目（含用户 key）同样丢失 → dynamic_model_router 降级链中 custom provider 失效直至用户重新验证 key。
- **CPM2 [P3]** :60 provider_id 用 `hash(name+base_url)`——PYTHONHASHSEED 随机化 → 重启后同配置生成不同 id；32bit 截断有碰撞理论面（时间戳前缀使实际碰撞概率极低）。
- **CPM5 [P3]** _fetch_anthropic_models :182-194 静态硬编码 7 个模型列表（claude-3/4 代，2025-05 后新模型不在）→ Anthropic 的 sync_models 永远返回过期列表；与 _test_anthropic 真实调用形成半双轨。
- 注：list_providers :83-98 正确隐藏 api_key（正面点名）；get_provider 返回完整对象含 key，但未发现序列化回显路径（CPM3 不成立，撤销）。

**prometheus_metrics.py**
- **PM1 [P3]** 收集-暴露断链：get_all :77-85 只返回 counters/gauges，**histograms 被丢弃** → generate_metrics_text :173-176 直方图段永远空；celery_tasks_total（counters 段只放行 http_requests_total 前缀 :168）、database_connections_active（无对应过滤段 :179-198）同样收集了永不暴露。monitoring 断链家族（与 VPX1「收集了不用」同型）。
- 注：:107-108 `_request_counts/_request_durations/_lock` 死字段；histogram :64-75 桶语义正确（正面点名）。

**resource_config.py**
- **RC1 [P3]** get_server_stats :209 `psutil.cpu_percent(interval=0.1)` 同步 sleep 0.1s 阻塞事件循环（VK1 家族第 3 处）；:237-239 docker SDK 同步调用在 async 内。
- **RC2 [P3]** batch_update_configs :165-187 循环内逐个 SELECT（N 次查询，应一次 IN）；:185 commit 前改缓存 → commit 失败时缓存与 DB 漂移；多进程部署时 set_config 后其他进程缓存不失效（CSK3 同族）。
- 注：__new__ 单例 + _initialized 挡重复初始化正确；_ensure_cache_loaded 双重检查锁正确（正面点名）。

**provider_health.py / apikey.py 组合**
- **PH1 [P3]** check 返回「请求超时/连接失败」与「API Key 无效」同为 (False, msg) → apikey.py:250-254 统一 `update_status(..., "invalid")` → **瞬时网络抖动/超时把有效 key 误标 invalid**（用户可重测恢复，但 invalid key 在恢复前被调用链跳过）。修复：区分超时与 401，超时不改状态或标记为待重试。
- 注：:69-71 getattr 分发的 provider 来自白名单 dict keys，安全；:20 TEST_EXPECTED 死常量；5 个 _check_X 全部转发 _check_openai_compatible 的冗余样板。

**log_config.py**
- **LC1 [P3]** set_file_logging :129-141 只改内存布尔、无任何 handler 操作 → **假开关**：接口返回成功、文件日志行为不变；get_config :143-155 返回的 log_to_file 状态与真实行为脱节。

**rate_limit_config.py**
- **RLC1 [P3]** 纯内存配置无持久化 → 管理端（guardian_router.py:776）调整的限流规则重启即丢（与 resource_config 的 DB 持久化双轨并存——同是配置，一持久一易失）。
- **RLC2 [P3-待交叉]** get_endpoint_rule :59-64 精确匹配端点名；middleware/rate_limiter.py:125/:331 传入的 endpoint 格式待下轮（app/middleware）确认——若传 raw path 则 :28-39 的规则表全部失配空转。

**feature_switch.py**
- 无独立缺陷（薄封装正确：FEATURE_KEYS 白名单 + 复用 resource_config 缓存）。RBAC 门禁在路由层（V2G 系列已覆盖）。

## 3. 死文件标注（不定活跃 P 级）

**audit_logger.py（services 版，218 行）——死文件 + 4 个死代码点**
- 全库零 import；活跃版为 utils/aicloud/audit_logger.py（ADT2 双轨家族第 17 处的被取代侧，本轮确认其死文件属性）。
- 若未来误接线即踩坑：① :74 token（API Key）全文存入审计日志 Redis 30 天（:97 debug 日志倒是只打前 8 位——存储与日志脱节）；② :45-52 默认 Redis localhost 硬编码（TM9）；③ 同步 redis 客户端（接线即阻塞事件循环）；④ clear_logs :194-203 只清主 key 不清 date 索引（注释自认「需要定期清理任务」且未实现）。

**user_preferences.py（179 行）——死文件（孤儿模块）+ 3 个死代码点**
- 全库零 import；agent/user_preference_learner.py 是另一独立模块（同名易混淆——建议一并清理或改名）。
- 死代码点：① :13 DB 落 `/tmp/user_preferences.db`（tmpfs 重启丢失 + 多用户共享权限面）；② sqlite3 同步阻塞（接线即阻塞事件循环）；③ _init_db :45-59 构造副作用：每次实例化执行 90 天归档 INSERT+DELETE（构造函数做数据清理）。

## 4. 交叉确认记录

| 疑点 | 结论 |
|------|------|
| agent_memory_service 消费方式 | knowledge_endpoints.py:25/:58/:88 直接实例化 `AgentMemoryService(db)`；get_session/delete_session 的归属校验待下轮 ai_agent 目录复核（AME1 保留待交叉标记） |
| skills.py author | :71 `author="api_user" # TODO` 硬编码实锤 → CSK1 定级 P2 |
| record_request path 来源 | performance_monitor.py:38 `request.url.path` raw path 实锤 → PM2 定级 P2 |
| rate_limit endpoint 来源 | middleware/rate_limiter.py:125/:331 调 get_endpoint_rule，传参格式待下轮 middleware 扫描（RLC2 保留） |
| custom_provider key 回显 | apikey.py/dynamic_model_router 均内部使用，无序列化回显路径 → CPM3 撤销 |
| provider_health 结果处理 | apikey.py:250-254 False 一律标 invalid 实锤 → PH1 |
| export_config 消费方 | 全库零调用 → 死代码家族第 35 处（MCM5） |
| get_cache 连接复用 | app/utils/cache.py 已在 utils 轮扫过（health_checker 每次 get_cache(redis_url) 是否复用池待查，影响 HC2 量级） |

## 5. 双轨与死代码盘点

- **双轨家族**：本轮无新增双轨；确认 audit_logger（services 版）为 ADT2 第 17 处双轨的被取代侧死文件；确认 MCM2 unified/agent 双配置文件为漂移温床（结构性双轨，不计入符号级双轨家族）。
- **死代码家族**：第 35 处——model_config_manager.export_config 零调用（MCM5）。
- **「接线即崩」家族**：无新增（死文件若接线会踩 4+3 个坑，已在死文件标注中列明）。
- **「安全设施未接线」家族**：+1——AKM3（Redis 明文存储 API Key，crypto/encryption 设施在而不用）；MCM5 附属（JSON 明文 api_key）。
- **同步阻塞事件循环家族**（VK1 系）：HC1（Celery inspect，第 2 处）、RC1（cpu_percent sleep，第 3 处）。
- **配置静默重置家族**：MCM1（save 非原子 + 损坏回退默认）、CSK2（元数据损坏静默清空）。

## 6. 修复建议优先级

1. **立即**：AKM1（EXPIRE 改 max 逻辑，一处改动止损管理面 key 丢失）；CPM4（base_url 校验）；PM2（中间件传 route template）。
2. **短期**：CSK1（author 接入 user_id + 归属校验）；HC1/RC1（to_thread/gather）；PH1（超时不标 invalid）；MCM1/CSK2（原子写 + 损坏告警不静默重置）。
3. **中期**：删除两个死文件（audit_logger services 版、user_preferences）与 export_config 死方法；CPM1 持久化或明示易失；LC1 假开关移除或实现；AKM3 明文存储接入加密设施。

## 7. 下轮候选

app/models（12 文件，含 agent_memory cascade 确认）/ app/db（12）/ app/schema（13）/ app/middleware（rate_limiter 传参确认 RLC2）/ app/tasks（3）/ app/core/config settings 全量复核。
