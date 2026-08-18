# rate_limiter.py 演化深扫文档

> 版本：v0.1 | 扫描日期：2026-08-17 | 状态：已完成
> 归属：Agent 引擎 / 请求限流（slowapi 中间件层）
> 路径：`app/utils/rate_limiter.py`（38 行）
> 索引：[TASKS.md](../TASKS.md)

## 1. 模块定位

「请求限流中间件」——基于 slowapi 的 API 滥用与 DDoS 防护层。模块级创建全局 `limiter`（默认 100/minute，key 为客户端 IP），通过 `init_rate_limit(app)` 注册异常处理器。接口级通过 `@limiter.limit("N/minute")` 装饰器设置更细粒度限制（注释示例：代码生成 5/minute、系统状态 30/minute）。

## 2. 依赖链与消费方

**活跃接线**：
- `main.py:53/112`——`init_rate_limit(App)` 应用启动时注册（活跃）
- `apikey.py:20/154/167/224/260/280/307/332/369/413/439/514`——10 处 `@limiter.limit`（5-60/minute）
- `providers.py:25/71/96/117/133/142/152/190`——7 处 `@limiter.limit`

**零消费**：
- `get_client_ip`（:27-32，X-Forwarded-For 解析）——全库零调用（设计了正确逻辑未用）

**并列限流（同一请求链三层）**：
- 本层 slowapi Limiter（全局 + 接口装饰器）
- `app/middleware/rate_limiter.py` RateLimitMiddleware（多级 tier，guardian_router.py:780/auth.py:23/system_load.py:91 消费）
- `app/utils/guardrails.py:385` InMemoryRateLimiter（GRD2，orchestrate_endpoints:254/:519 消费）

## 3. 发现

### RL1 [P2] slowapi 限流默认内存存储 + 单进程计数——多 worker 部署失效（GRD2/MCP1 家族）

- **Bug 代码**：:14-17 `Limiter(key_func=get_remote_address, default_limits=["100/minute"])`——未配置 storage_uri（slowapi 默认 in-memory 存储）——限流计数在单进程内存。
- **影响**：多 worker/多进程部署（uvicorn workers/Celery）每进程独立计数——同一客户端请求被负载均衡分摊后每进程配额独立、总量 n 倍突破（与 GRD2 InMemoryRateLimiter 完全同构）——**限流三套全内存级**，无一套跨进程有效。

### RL2 [P2] key_func=get_remote_address 忽略代理——反向代理后全站共享同一配额（全库确认）

- **Bug 代码**：:15 `key_func=get_remote_address`——slowapi 直接用 request.client.host；:27-32 `get_client_ip` 实现了 X-Forwarded-For 解析（:31 `forwarded.split(",")[0]`）却**零消费**——设计了正确逻辑没用上。
- **根因**：项目配置 nginx 反向代理（configs/nginx.conf 存在）+ main.py:112 接线——所有请求经代理后 client.host 均为代理内网地址 → **全站用户共享 100/minute 全局配额**（apikey/providers 的接口级限制同样按代理 IP 归并）——正常多用户并发立即触发全局 429 误伤；单用户也可独占全站配额。
- **影响**：限流在代理部署下退化为「全站总量限制」，语义彻底失真（区别于 GRD2 的业务级 user 键，本层 IP 键在代理后恒为同一值）。

### RL3 [P3] 三层限流并存——同一请求链三套配额语义叠加（SCT6 三轨家族）

- **Bug 代码**：slowapi Limiter（本模块，100/min 全局 + 接口级）+ middleware/rate_limiter.py RateLimitMiddleware（多级 tier）+ guardrails.py:385 InMemoryRateLimiter（10/60s 业务级）——三套计数互不可见、各自独立窗口。
- **影响**：同一请求链经过三套限流叠加误伤（全局量 + tier 量 + 业务量三者取最小生效）；三套状态各自漂移无法统一治理/统计（guardian_router /admin/rate-limit 只暴露 middleware 层 stats，slowapi 与 guardrails 层不可观测）——配置双轨/三轨家族极端例（DR3/SCT6 同族）。

### RL4 [P3] _rate_limit_exceeded_handler 用 slowapi 默认 handler——错误文案与项目体系不一致

- **Bug 代码**：:24 `app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)`——slowapi 默认 handler 返回英文「Rate limit exceeded: ...」JSON；未定制项目统一中文错误格式（api_response/error_handler 体系）也无 Retry-After 重试语义。
- **影响**：429 响应与其他业务错误格式不一致（客户端解析差异）；无重试窗口提示。

### RL5 [P3] get_client_ip 零消费 + X-Forwarded-For 无信任校验（能力未接线 + 安全）

- **Bug 代码**：:27-32 get_client_ip 全库零调用；:31 `forwarded.split(",")[0]` 取第一个代理值——若未来接线限流 key 换用 X-Forwarded-For，客户端可直接伪造该头（无 trusted-proxy 白名单校验）→ 任意 IP 冒充绕过/陷害。
- **影响**：当前零消费无风险；接线需配套 trusted proxy 校验（参考 DR10/FCT3 安全接线需前置设计的家族规律）。

## 4. 演化方向

- **统一限流层**（RL3）：三层限流收敛为一套——推荐保留 middleware RateLimitMiddleware（已有多级 tier + admin 观测），slowapi 装饰器与 guardrails 业务级限流并入；或明确分层职责（中间件=全局/tier、业务级=用户维度的 guardrails）并统一存储（Redis——main.py:114-116 已检测 REDIS_URL，可复用）
- **key_func 修复**（RL2）：改用正确代理感知——需配置 trusted proxies（X-Forwarded-For 白名单校验后再取值，参考 RL5），否则代理后全站共享配额
- **存储升级**（RL1）：slowapi 配 storage_uri=redis://… 跨进程一致计数（与 GRD2 同方案——内存级三套全部失效需统一 Redis 化）
- **错误语义**（RL4）：定制 429 handler 返回项目统一错误格式 + Retry-After

## 5. 主线关联

- **内存级限流三套全失**：RL1 加入 GRD2（guardrails InMemoryRateLimiter）——slowapi + RateLimitMiddleware + guardrails 三套限流全部单进程内存级，多进程部署下整套限流体系失效——限流主线从「双轨」扩展为「三轨全内存」
- **配置多轨家族**：RL3 加入 DR3/SCT6（sentry 双配置/limiter 三副本同源问题）
- **安全接线前置**：RL5 加入 DR10/FCT3（安全能力接线需前置信任校验设计的家族规律）
- **零消费函数**：RL5 get_client_ip 加入 GRD7/GC4（设计了未接线）
- **防护层「检测不拦截」对照**：限流三层是防护层唯一「主动拦截」机制（429 阻断，区别于 GC2/GRD3 的检测放行）——但三层全内存级（RL1）使拦截在部署形态下失效

## 6. 测试状态

- **零单元测试**：tests/ 下无任何 slowapi/rate_limiter/Limiter 引用
- RL1 跨进程失效、RL2 代理后 key 归并均无测试约束（修复建议：以 mock 代理请求验证 key_func 行为 + 多 worker 场景集成测试）
