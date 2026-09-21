# app/middleware/ 中间件层详档

> 轮次：第一百五十轮（v1.151）| 日期：2026-08-28 | 扫描对象：rate_limiter.py 429 + input_validator.py 297 + feature_switch.py 93 + security_headers.py 93 = 4 文件 912 行
>
> 缺陷编号前缀：RLM（RateLimit middleware）/ IV（Input Validator）/ FSW（Feature Switch middleware）/ SH（Security Headers）

## 一、模块定位与状态判定

app/middleware/ 是 FastAPI 应用的**HTTP 中间件层**——请求进入路由前的横切拦截带：限流（四层 tier：全局/IP/用户/端点）、输入安全检测（SQL 注入/XSS/请求体大小/Content-Type 白名单）、功能开关拦截（503）、安全响应头注入（CSP/XFO/nosniff 等）。四个中间件全部在 main.py:184-193 挂载，执行顺序（add_middleware 倒序）为 GZip → SecurityHeaders → FeatureSwitch → RateLimit → InputValidator → RequestLogging → CORS——限流在输入验证外层先执行（超量请求省验证成本），顺序合理。三个安全中间件全部采用**纯 ASGI 实现**（显式注释绕开 BaseHTTPMiddleware 的 cancel scope 传播问题——与 RequestLoggingMiddleware、performance_monitor 的 PM1 一致性对照，本目录三个是做对了的）。

| 文件 | 行数 | 状态判定 | 依据 |
|------|------|---------|------|
| rate_limiter.py | 429 | 活跃（约 1/3 死代码） | RateLimitMiddleware main.py:187 挂载；LoginAttemptTracker 三函数 auth.py:139-180 登录锁定活跃消费；guardian_router.py:780 + system_load.py:92 读 get_stats()——但 is_rate_limited/endpoint_limits/get_client_id/get_client_identifiers/check_limit 五符号全库零消费 |
| input_validator.py | 297 | 活跃（AI 主链路白名单裸奔） | InputValidatorMiddleware main.py:184 挂载；SQL/XSS 检测对全部非白名单 POST/PUT/PATCH 生效——但 5 条 AI 主链路整体跳过 |
| feature_switch.py | 93 | 活跃 | FeatureSwitchMiddleware main.py:190 挂载；import services.feature_switch（服务-消费方单轨，双轨嫌疑解除） |
| security_headers.py | 93 | 活跃 | SecurityHeadersMiddleware main.py:193 挂载；全部响应注入安全头 |

**三态分类**：4 文件全活跃（路由挂载 + 生产消费方确认），无死文件、无未接入面——但 rate_limiter.py 内部存在方法级死代码簇（RLM4，五符号零消费 + 第三份硬编码限流规则表）。

## 二、缺陷清单

### P2（2 项）

**RLM1 [P2] 端点限流规则「前缀意图、精确实现」失配——六项前缀规则空转，管理端动态调整对带参路径无效**

- rate_limiter.py:291 `endpoint = path`——把完整 raw path（含路径参数，如 `/api/v1/code/execute/abc-123`）直接传给 check_multi_tier → rate_limit_config.get_endpoint_rule
- services/rate_limit_config.py:28-39 规则表的键是「前缀型意图」条目（`/api/v1/code`、`/api/v1/generate`、`/api/v1/pptx`、`/api/v1/ai_agent`、`/api/v1/aicloud`、`/api/v1/workflow`），实现却是**精确相等匹配**——带路径参数的真实请求（/api/v1/code/execute/xxx）与键（/api/v1/code）永不相等
- 后果：六项 AI 主链路专用限流规则**全部失配落空**，请求全部落默认 (60,60)；仅无参精确路径（/api/v1/login、/api/v1/register、/api/v1/files/upload 等）规则生效；guardian_router 管理端动态调整规则对一切带参路径无效（调整后仍精确匹配失配）
- 交叉确认：RLC2（第 148 轮 services 详档遗留）在本轮终审关闭——传参格式实证为 raw path
- 修复：get_endpoint_rule 改前缀匹配（`path.startswith(rule)`）或路由模板提取（scope["route"].path）

**IV1 [P2] SQL/XSS 黑名单高误报迫使 AI 主链路整体白名单跳过——「安全检查」双向失效**

- input_validator.py:35 `\b(SELECT|INSERT|UPDATE|DELETE|DROP|UNION|ALTER|CREATE|EXEC|EXECUTE)\b` 命中**日常英文词**——「create a new project」「delete this file」「select a template」「update the profile」全数 400 拒绝（本平台是 AI 代码生成平台，需求文本天然含这些词）；:36 `--` 命中「well--known」/负数区间、:41 `1=1`、:48 `on(error|load|...)` 命中「on error resume next」等英文文本
- 迫使 :74-80 把 5 条 AI 主链路（orchestrate/stream、generate、ai_agent/process 等）**整体列入 SKIP_SECURITY_CHECK_PATHS 白名单**——最需要输入检查的入口（LLM 提示词注入、XSS payload 经 AI 链路直达下游生成物）完全裸奔
- 双向失效：白名单外端点对正常业务文本持续误报（可用性损害 + 用户绕过动机），白名单内零防护（安全承诺空转）——「安全设施未接线」家族的中间件层变体：线接了，但被自己的误报逼得拔了
- 修复：正则改参数化检测（引号拼接/注释符+关键词组合等高危组合特征）而非单词黑名单；白名单收窄到真正产生代码文本的字段级；LLM 输入走提示词注入检测层（与 WS3 间接注入同源）

### P3（8 项）

**RLM2 [P3] _history 旧窗口 key 永不清理——缓慢内存泄漏 + 私有成员被两处外部直摸**

- rate_limiter.py:43 `_history: defaultdict(list)`，key 含窗口号 `int(time/window)`；_cleanup_old_records 只清理**当前传入 key** 的过期记录——窗口滚动后旧 key（ip:1.2.3.4:100）再无人引用、永久残留，随时间×IP 数缓慢膨胀；LoginAttemptTracker.failed_attempts 同型（IP/用户名维度 defaultdict 无界，仅成功登录清当前 identifier）
- 封装破坏：system_load.py:102-104（SL1 已在第 118 轮记录）与 rate_limiter.py:333-334（send_wrapper 内直摸 `rate_limiter._lock/_history` 取 count）两处外部直摸私有成员——重构即静默断裂

**RLM3 [P3 待交叉] IP 桶失真——反代部署共享网关桶 + 多 worker 内存态不共享**

- rate_limiter.py:287-288 `scope.get("client")[0]` 为直连对端——V2N nginx 反代部署下若无 proxy_headers 转发，全站用户共享同一 IP 桶（100/分全局配额被全站瓜分、攻击者与正常用户不可区分）；uvicorn 启动配置在 main.py/run.py 无命中（docker/外部启动），是否开 proxy_headers 待交叉
- :39 docstring 自认「生产环境建议使用 Redis 实现分布式限流」——内存态多 worker 不共享，限流总量按 worker 数放大（CSK3 同族、RL1 slowapi 同型——限流三轨全内存级主线的 middleware 层实证）

**RLM4 [P3] 死代码家族第 37 处——五符号零消费 + 第三份硬编码限流规则表**

- rate_limiter.py:161-186 `is_rate_limited`、:47-59 `endpoint_limits`（与 services/rate_limit_config.py 规则表重复维护的**第三份限流规则表**——双轨家族第 18 处）、`get_client_id`、`get_client_identifiers`、`check_limit` 全部全库零消费（grep 实证：唯一消费方是 auth.py 的 login_tracker 三函数与 guardian_router/system_load 的 get_stats）——死方法含各自独立的 JWT 解析三胞胎实现（:194-230 区段）

**RLM5 [P3] 429 响应 retry_after 双值不一致 + 每请求同步 JWT 解码**

- :307 body `retry_after = window // 2` 与 :317 header `retry-after = window` 不一致（客户端按 body 重试仍撞墙）；:348-363 每请求同步 jwt.decode 无缓存（高 QPS 下 HMAC 验签 CPU 开销可感知，且 except Exception 吞全部异常静默降级 IP 桶——降级合理但不可观测）

**IV2 [P3] 哨兵字节串碰撞 + 非 JSON body 零检测 + 前缀碰撞**

- :127-128 超限返回哨兵 `b"__TOO_LARGE__"`——14 字节真实 body 恰等于该串被误判 413（应返回 (None, oversized) 二元组而非魔法值）；:201 非 JSON content-type（form/multipart/octet-stream）body 完全不检测（设计取舍：文件内容扫描误报更高，但安全承诺应如实收窄）；:154 `path.startswith(p)` 前缀碰撞（/api/v1/agent/generate-evil 也跳过——GH4/V2N2 家族）

**FSW1 [P3] FeatureSwitchMiddleware SKIP_PATHS 冗余 + 前缀映射硬编码**

- :33-39 SKIP_PATHS 含 health/docs 等不在 PATH_FEATURE_MAP 拦截范围（/api/v1/aicloud|docker|agent|workflow）的路径——白名单装饰性存在，与 input_validator 的 SKIP_PATHS 清单还不一致；:26-31 四条前缀硬编码 → 新增受控功能需改代码（services 侧 DB 开关已动态，映射端静态——半动态半静态）；**双轨嫌疑解除**：本文件 import services.feature_switch_service，是服务的 HTTP 拦截消费方（单轨）

**SH1 [P3] CSP 核心防护被放开——unsafe-inline/unsafe-eval 使 CSP 对 XSS 防护大幅削弱**

- security_headers.py:26-27 script-src `'unsafe-inline' 'unsafe-eval'`——CSP 存在但内联脚本/eval 全放行，对注入型 XSS 的核心防护失效（「安全设施未接线」轻量变体：线接了、保险拔了——AJP3 存储型 XSS 在此得不到 CSP 兜底）；connect-src `https: wss:` 允许任意外联（多 AI 提供商直调的现实取舍，记录在案）；x-xss-protection 已被现代浏览器废弃（无害冗余）

**SH2 [P3 待交叉] CSP 文档分支前缀 /api/docs 与实际 docs 挂载点一致性未确认**

- :12/:62 CSP 特化分支与 COEP 排除分支判定 `/api/docs` 前缀——input_validator SKIP_PATHS 用的却是 `/docs`；若 FastAPI docs 实际挂 /docs（默认），docs 专用 CSP 分支永不命中、COEP require-corp 会加到 /docs 响应（可能破坏 Swagger UI 跨域资源加载）——需确认 main.py docs_url 配置后归一

## 三、交叉确认记录

| 遗留项 | 来源 | 结论 |
|--------|------|------|
| RLC2 get_endpoint_rule 传参格式 | services.md（148 轮） | **关闭升级 RLM1**——:291 `endpoint = path` raw path 直传，六项前缀规则空转实锤 |
| endpoint_limits 与 rate_limit_config 双轨嫌疑 | services.md（148 轮） | **确认双轨家族第 18 处**且硬编码侧零消费（RLM4 一并记录） |
| middleware/feature_switch.py 与 services 版双轨嫌疑 | 上轮盘点 | **解除**——服务-消费方单轨（import feature_switch_service） |
| is_rate_limited/get_client_id/get_client_identifiers/check_limit 消费方 | 本轮 grep | 全部零消费 → 死代码家族第 37 处 |
| LoginAttemptTracker 消费方 | 本轮 grep | auth.py:139-180 活跃（登录失败 5 次/300s 锁定）——auth.py 本体在 v1 余量，细节留待该轮 |
| guardian_router.py:780 | 本轮 grep | rate_limiter.get_stats() 管理端观测活跃 |
| system_load.py:91-104 | 本轮 grep | get_stats + 私有成员直摸（SL1 已记录，RLM2 补充 middleware 侧对称证据） |
| 限流三轨全内存（RL1 主线） | rate_limiter.md（113 轮） | RLM3 补充 middleware 层实证：内存 tier + docstring 自认需 Redis + 多 worker 放大 |
| proxy_headers / uvicorn 启动配置 | 本轮 grep | main.py/run.py 无命中——RLM3 待交叉项，docker/外部启动方式确认后关闭 |

## 四、正面点名

- **三个安全中间件全部纯 ASGI 实现**（:133-137/:17-24/:5 显式注释 cancel scope 原因）——与 RequestLoggingMiddleware 决策一致，对照 PM1（performance_monitor 用 BaseHTTPMiddleware 缓冲 SSE）本目录是正确示范
- **input_validator receive_replay body 回放**（:259-270）——中间件读 body 后正确回塞 receive 使下游可再读，http.disconnect 分支处理完备
- **security_headers 响应头去重**（:88-89 按 bytes key 静默覆盖下游重复头）——避免 X-Frame-Options 等头重复注入
- **四层 tier 限流设计**（全局/IP/用户/端点）+ 分层 429 响应（tier/retry_after/x-ratelimit-* 头）结构完整
- **FeatureSwitchMiddleware 503 结构化响应**（code/feature 字段）+ 命中即短路，开销最小

## 五、修复建议（优先级序）

1. **RLM1**：get_endpoint_rule 改前缀匹配或 route template 提取（一处改动激活六项 AI 主链路限流 + 管理端动态调整全量生效）
2. **IV1**：SQL/XSS 正则改「组合特征」检测（引号外拼接、注释符+关键词等），白名单收窄到字段级，LLM 链路补提示词注入检测
3. **RLM2**：_history 定期全表清扫（惰性过期 key 回收）+ login_tracker deque 裁剪；rate_limiter 暴露公共 count API 收编两处私有直摸
4. **RLM4**：删五死符号与第三份硬编码表（-70 行）
5. **SH1/SH2**：unsafe-eval 移除 + unsafe-inline 收敛为 nonce；确认 docs 挂载点后归一 CSP 分支
6. **RLM5/IV2/FSW1**：retry_after 单一来源、哨兵改二元组、SKIP_PATHS 清理

## 六、测试状态

四文件**零单元测试**（app/test 下无 middleware 对应测试）——RLM1 前缀匹配、IV1 误报/白名单行为均无回归保护。

## 七、下轮候选

- **app/db 12 文件 1,351 行**（PRAGMA foreign_keys 终审 + scheduler.py）——MD1 级联矩阵的 DB 层验证
- app/schema 13 文件 828 行
- app/core 5 文件 1,044 行 + 顶层散件 7 文件 1,104 行

## 八、状态更新（2026-09-18 核实）

以当前代码为准逐条核实并修复：

- **RLM1 已修复**：`RateLimitConfig.get_endpoint_rule` 改最长前缀匹配（新增 `resolve_endpoint_key`，按路径段边界判断），中间件端点桶 key 由完整 raw path 归一为匹配到的规则前缀。六项 AI 主链路前缀规则恢复生效，带路径参数请求不再各自成桶。
- **IV1 已部分修复**：SQL 正则从单词黑名单改为组合特征（引号布尔注入、`UNION SELECT`、堆叠 DDL、`--` 注释、`1=1`），消除 `create`/`delete`/`select`/`update` 日常文本误报；XSS 移除 `eval(`、`document.*` 等代码语义模式，保留标签/协议/事件属性 payload；`SKIP_SECURITY_CHECK_PATHS` 的空转范围收窄为「仅跳过内容扫描」，Content-Type 与请求体大小校验对 AI 主链路重新生效，并顺带用路径段边界匹配修掉 `startswith` 前缀碰撞。
- **仍存权衡**：AI 主链路仍不做 SQL/XSS 内容扫描（代码生成场景下把代码文本当攻击 payload 拦截本身不成立，正确防护是输入侧提示词注入检测）；XSS 对 `<script>` 等标签仍会在非白名单端点拦截含字面标签的文本。
- **IV2 已失效（核实为不成立）**：`MAX_BODY_SIZE = 10MB`，14 字节的 `b"__TOO_LARGE__"` 永远达不到该阈值，`_read_body_safe` 不可能把它当作超限哨兵返回，因此「真实 body 恰等于哨兵被误判 413」不可复现（`input_validator.py:19/:143-144/:225`）。`path.startswith(p)` 前缀碰撞已在 IV1 用 `path == p or path.startswith(p + "/")` 的段边界匹配修掉（`:172-175`）。「非 JSON body 不扫描」是对文档已记录的设计取舍，本项无代码缺陷。
- **SH2 已失效（核实为不成立）**：`app/main.py:186` 显式配置 `docs_url="/api/docs"`、`redoc_url="/api/redoc"`、`openapi_url="/api/openapi.json"`，与 `security_headers.py` 的 `/api/docs` CSP 特化分支一致，不存在「docs 专用分支永不命中」。`input_validator` 的 `/docs` SKIP_PATH 属另一清单，不影响该分支命中。
- **仍未处理**：FSW1、SH1（P3）。FSW1 为清单冗余与静态前缀映射的整洁性问题（`SKIP_PATHS` 装饰性、新增受控功能需改代码），非正确性缺陷；SH1（CSP `'unsafe-inline'`/`'unsafe-eval'`）需先确认前端是否依赖内联脚本与 eval，收敛为 nonce 会改变全部页面脚本加载方式，属需实测的专项。
- **测试**：新增 `tests/unit/test_middleware_hardening.py`(15)；回退源码后 8 项失败。

## 九、状态更新（2026-09-20 核实）

以当前代码为准逐条核实并修复：

- **RLM2 已修复**：`RateLimiter` 新增 `_prune_stale_keys`，按 `rate_limit_config.max_window`（新增属性，取各层级与端点规则窗口最大值）每秒一次全量清扫，删除记录已全部过期的 key——窗口滚动后的旧时间桶不再永久残留。`LoginAttemptTracker.is_blocked` 在过滤后为空时 `del` 键，`clear_failed_attempts` 改 `pop` 而非置空列表，避免为每个出现过的用户名/IP 永久保留空列表。
- **RLM4 已修复**：删除五个零消费符号 `is_rate_limited` / `endpoint_limits` / `get_client_id` / `get_client_identifiers` / `check_limit`（含 `endpoint_limits` 第三份硬编码限流规则表与各自的 JWT 解析重复实现）。限流规则单一来源收敛为 `services/rate_limit_config.py`。
- **RLM5 已修复**：429 响应体 `retry_after` 由 `window // 2` 改为 `window`，与响应头 `retry-after` 一致，客户端按任一值等待都不会提前重试撞墙。
- **RLM3 仍未处理**：反代部署 IP 桶失真与多 worker 内存态不共享依赖部署配置，留待运维口径。
- **测试**：新增 `tests/unit/test_middleware_rlm_and_request_id.py`(7)；同步调整 `tests/unit/test_performance_monitor_metrics.py` 两处 `_metric_path` 调用签名。回退源码后 8 项失败。

## 十、状态更新（2026-09-21 核实）

- **SH1 已部分修复（unsafe-eval 移除）**：应用页面 CSP 的 `script-src` 由 `'self' 'unsafe-inline' 'unsafe-eval'` 收敛为 `'self' 'unsafe-inline'`，并补 `object-src 'none'`。依据：`src/dist/index.html` 构建产物无内联脚本，Vue 模板在构建期编译，运行期不依赖 eval；两个 bundle 中仅有的 `eval(`/`new Function(`（core-js `setImmediate` 传字符串分支、zrender 取不到 `JSON.parse` 时的 `parseJSON` 回退）正常路径不可达。实测（真实中间件 + 真实 dist，Chromium 加载 `http://127.0.0.1:8100/`）：`eval` 抛 `EvalError`，外部脚本正常执行，页面 0 console error / 0 page error。
- **SH1 保留 `'unsafe-inline'` 的原因（已实测）**：`documentPictureInPicture` 创建的画中画文档会继承本文档的 CSP（隔离实验：父文档 `script-src 'self'` 时，画中画窗口内联脚本被拦、`document.write` 的脚本不执行），而 `src/components/VirtualGirl.vue` 的画中画聊天界面正是靠窗口内内联脚本 + `postMessage` 工作。撤销该依赖需要 nonce 方案（后端按请求注入 + 画中画复用 nonce）或把画中画 UI 改为由主窗口直接操作其 DOM，属独立专项。
- **文档分支判定补段边界**：`/api/docs`、`/api/redoc`、`/api/openapi` 三个前缀改为 `_is_docs_path()` 的段边界/精确匹配。原 `path.startswith("/api/docs")` 会让 `/api/docsomething` 这类同前缀业务路径命中放宽策略（`unsafe-eval` + jsdelivr + 免 COEP），与 IV2 的 `startswith` 前缀碰撞同族；当前路由表暂无此类路径，属潜在放行面。`/api/openapi` 由前缀改为精确 `/api/openapi.json`，与 `app/main.py:186` 的 `openapi_url` 一致。
- **FSW1 已修复（段边界 + 单一来源 + 清冗余）**：`FeatureSwitchMiddleware` 抽出 `_match_feature()` 按路径段边界匹配（`path == prefix or path.startswith(prefix + "/")`），`/api/v1/agentfoo`、`/api/v1/agent-evil`、`/api/v1/aicloudx`、`/api/v1/workflows`、`/api/v1/dockerfile` 这类同前缀路径不再被误判归属（原 `startswith` 会让它们因该功能关闭而收到 503）；功能中文名改用 `feature_switch_service.FEATURE_NAMES`（原为中间件内联复制的第二份中文名表，双轨隐患）；删除 `SKIP_PATHS`（五项 `/health`、`/ready`、`/docs`、`/openapi.json`、`/favicon.ico` 均不在 `PATH_FEATURE_MAP` 拦截范围内，属装饰性白名单），无归属路径直接放行、不再进入判断链；移除两个未使用的 fastapi 导入。`/api/v1/docker` 在路由表 0 条命中，映射项当前不生效但保留意图明确（docker 路由回归即接管），未删。
- **测试**：新增 `tests/unit/test_security_headers_csp.py`(12)、`tests/unit/test_feature_switch_middleware.py`(17)；回退对应源文件后分别 6 项、6 项失败。
