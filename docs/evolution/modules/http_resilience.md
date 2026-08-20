# http_client.py + retry.py + circuit_breaker.py 网络容错家族

> 第一百二十五轮补扫 | v1.126 | 2026-08-17 | 分析对象：`app/utils/http_client.py`（93 行，HTTPClientPool）+ `app/utils/retry.py`（178 行，四策略重试）+ `app/utils/circuit_breaker.py`（220 行，熔断器）
>
> 结论：**HTTP 客户端四轨——HTTPClientPool（本模块）几无业务消费方（仅 main.py shutdown 引用清理），实际请求走 aicloud/http_client.py / image_generation.py / AiCodeUtil.py 三套内嵌单例 + mcp_client.py 独立实例；retry.py 四策略全部零消费（死代码模块，真实重试在 aicloud call_with_retry）；circuit_breaker.py 真实消费方仅 async_enhanced_guard**。

## 一、模块定位

| 组件 | 位置 | 消费状态 |
|------|------|----------|
| HTTPClientPool | http_client.py:12 | **零业务消费**——仅 main.py:160 shutdown 清理 |
| get_http_client / get_http_client_pool | http_client.py:72/:84 | 同上，全库无调用方 |
| retry_on_failure + retry_api_call/db/file | retry.py:24/:123/:143/:162 | **零消费**——死代码模块 |
| retry_with_circuit_breaker | retry.py:82 | 零消费 |
| CircuitBreaker / get_circuit_breaker | circuit_breaker.py:54/:195 | async_enhanced_guard.py:27 真实消费 |
| circuit_breaker 装饰器 | circuit_breaker.py:202 | 零消费 |
| 另三套 HTTP 客户端 | aicloud/http_client.py、image_generation.py:49、AiCodeUtil.py:18 | 真实请求走这几套（均有 is_closed 重建检查） |
| call_with_retry（真实重试） | aicloud/http_client.py | 7 个 adapter 消费 |

## 二、缺陷清单

### P2（4 项）

- **HTTP1 [P2] HTTP 客户端四轨并存——本模块 HTTPClientPool 无 is_closed 检查无重建机制且几无消费方**——http_client.py:25-51——image_generation.py:56/:59、AiCodeUtil.py:26、aicloud/http_client.py:29-31 三套均带 `is_closed` 检查+锁内重建——**唯独 HTTPClientPool 只判 `self._client is None`**——若客户端因异常关闭（网络栈回收）→ 复用已关闭连接持续报错且无重建路径——四轨中能力最弱但被 main.py 当作统一清理入口（清理的是无人使用的池）。第九处双轨（HTTP 客户端四轨）。修复方向：统一到带 is_closed 重建的单例，清理无消费方。
- **RET1 [P2] retry.py 四策略零业务消费——死代码模块**——grep 全库：retry_on_failure/retry_api_call/retry_db_operation/retry_file_operation/retry_with_circuit_breaker **无任何业务调用**——真实重试走 aicloud/http_client.py call_with_retry（自研信号量+重试）。且 retry_db_operation 默认 `(Exception,)` 全异常重试——若未来被套在含副作用事务外层 → 重复执行写入。修复方向：删除或接入统一重试体系。
- **CB1 [P2] get_circuit_breaker 无锁创建——并发竞态导致熔断器实例丢失**——circuit_breaker.py:197 `if name not in _circuit_breakers: _circuit_breakers[name] = CircuitBreaker(...)`——**多协程首次并发调用同一 name → 各自 new 实例，后写入覆盖先写入**——丢失的实例其计数/状态作废——DCC1 无锁单例家族最典型一例（async_enhanced_guard 在 import 期创建规避了风险，但运行时动态创建即触发）。修复方向：模块级 asyncio.Lock 包裹创建。
- **CB2 [P2] cb.call 不包裹请求超时——HALF_OPEN 慢请求占满配额**——circuit_breaker.py:113-125——半开状态 `_half_open_calls += 1` 但**无超时收回**——慢请求（挂起的第三方调用）持续占用半开额度 → 半开探测失效、熔断恢复延迟。修复方向：call 内包 asyncio.wait_for。

### P3（8 项）

- **HTTP2 [P3] `__aenter__` 返回客户端但 `__aexit__` 空操作——上下文管理器语义误导**——http_client.py:62-66——`async with pool as client:` 用完既不归还池也不关闭——调用方按上下文语义理解会误以为连接已回收。修复方向：`__aexit__` 中 aclose 或删去协议方法。
- **HTTP3 [P3] `follow_redirects=True` 默认跟随重定向——用户可控 URL 请求时 SSRF 面扩大**——http_client.py:43——重定向可指向内网/元数据地址（同 web_search WS2 家族）。修复方向：按需开启或限制重定向次数。
- **HTTP4 [P3] 全局单例 `get_http_client_pool` 无锁——多线程首调竞态**——http_client.py:75-77（非 async 无锁）——虽 get_client 内 async lock 兜底，但 `_http_client_pool` 变量替换本身竞态。同 DCC1 家族。
- **HTTP5 [P3] 30s 全局超时不可按调用配置——慢服务定制超时无入口**——http_client.py:23。
- **RET2 [P3] `enable_jitter` 参数无效——两个分支 wait_strategy 完全相同**——retry.py:52-63——`if enable_jitter: wait_exponential(...) else: wait_exponential(...)`——**两分支一字不差，抖动从未生效**（tenacity 需显式传 jitter 参数）——重试风暴风险（外部服务故障时 3 路齐涌）。修复方向：`wait_exponential(..., jitter=enable_jitter)`。
- **RET3 [P3] `retry_with_circuit_breaker` 的 except 分支完全冗余**——retry.py:113-116——`if isinstance(e, exceptions): raise` / `raise`——两分支均 re-raise，判断无分流作用——死逻辑。
- **CB3 [P3] `_half_open_calls` 增减在锁外——并发半开请求计数错乱**——circuit_breaker.py:113-117 自增无锁（`_on_success`/`_on_failure` 有锁）——半开额度可能超限。
- **CB4 [P3] `callback` 参数存储但从未调用——熔断回调机制未实现**——circuit_breaker.py:73 保存后全文件无 `self.callback(...)`——状态变更通知/告警钩子缺失。

## 三、全库交叉确认

- **HTTP 客户端四轨（第九处双轨以上）**：HTTPClientPool（无重建）vs aicloud/http_client.py vs image_generation.py vs AiCodeUtil.py（三套均有 is_closed 重建）——**重复实现四处，重建机制不一致**——清理入口 main.py 指向最弱实现。
- **重试体系双轨**：retry.py（tenacity，零消费）vs aicloud/http_client.py call_with_retry（asyncio.Semaphore + 自研重试，真实消费）——同库两套重试框架。
- **熔断消费面**：真实消费仅 async_enhanced_guard（API 调用防护）；dynamic_model_router.py:641 的 `_apply_circuit_breaker` 是**自有实现**（模型路由层），与 circuit_breaker.py 无关联——熔断两处异构。
- **单例无锁家族**：CB1/HTTP4 与 DCC1（dynamic_concurrent）、SC2（system_config）、CRY6（crypto）同族——**本库并发单例竞态累计第 6+ 处**。
- **SSRF 家族**：HTTP3 与 WS2（web_search）同族——HTTP 客户端无默认 SSRF 防护。

## 四、测试状态

零单元测试。HTTP 客户端四轨、retry.py 死代码、enable_jitter 死分支、callback 未调用均无测试约束。修复建议：① 统一 HTTP 客户端单例（is_closed 重建）测试；② jitter 分支行为测试（enable_jitter 切换断言等待时间分布）；③ 熔断并发创建竞态测试；④ cb.call 超时包裹测试。
