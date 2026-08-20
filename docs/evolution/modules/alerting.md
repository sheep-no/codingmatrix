# sentry.py + startup_alert.py 监控告警家族

> 第一百二十六轮补扫 | v1.127 | 2026-08-17 | 分析对象：`app/utils/sentry.py`（257 行，Sentry 错误追踪封装）+ `app/utils/startup_alert.py`（251 行，启动失败告警管理器）
>
> 结论：**两模块均为零业务消费的死代码——全库无 init_sentry/capture_*/record_startup_* 调用方——错误追踪与启动告警机制实际未接入，且 sentry 封装在未初始化时静默丢弃错误**。

## 一、模块定位

| 组件 | 位置 | 消费状态 |
|------|------|----------|
| init_sentry / capture_error / capture_message | sentry.py:20/:96/:126/:154 | **零业务消费**——全库无调用方 |
| set_user / set_tag / add_breadcrumb | sentry.py:184/:207/:225 | 零消费 |
| StartupFailureAlert / get_startup_alert | startup_alert.py:36/:246 | **零消费**——main.py 启动流程未接入 |
| WebhookAlertHandler / ConsoleAlertHandler | startup_alert.py:193/:226 | 零消费 |

## 二、缺陷清单

### P2（3 项）

- **SNT1 [P2] sentry.py 零业务消费——死代码模块——错误追踪实际未接入**——grep 全库：init_sentry/capture_error/capture_message_sync/capture_message_async/set_user 无任何业务调用方——Sentry 封装完备（init+过滤+捕获+scope 配置）但**从未被使用**——应用真实错误仍只落本地日志。修复方向：接入 main.py 启动流程 + 全局异常处理钩子，或删除。
- **SNT2 [P2] capture_* 未初始化时静默 return——调用方误以为错误已上报**——sentry.py:104/:135/:163 `if not _sentry_initialized: return`——无日志无告警——**错误在调用方视角已处理、实际丢失**——静默失真家族（同 EC3/RG1/SL3）。若未来接入调用方（如 error_handler 上报），错误会无声消失。修复方向：未初始化时记录 debug 日志或抛软告警。
- **STA1 [P2] startup_alert.py 零业务消费——死代码模块——启动告警未接入**——grep 全库：StartupFailureAlert/record_startup_begin/record_startup_success/record_startup_failure/WebhookAlertHandler 无任何业务调用方——main.py 启动链路未调用（对比 process_guard 链在 main.py 有真实接入）——启动失败告警机制存在但从未触发。修复方向：接入 main.py 启动/关闭流程 + 配置 Webhook 处理器，或删除。

### P3（6 项）

- **SNT3 [P3] `_before_send` 过滤面窄——仅 aiohttp.client/urllib3.connectionpool 两 logger + SSL/ConnectionRefused 两类异常**——sentry.py:78-91——其余库级噪声（timeout/retry 重试风暴）照常上报。弱过滤。
- **SNT4 [P3] `capture_message_async` 是伪异步——`await asyncio.sleep(0)` 后调用同步 sentry_sdk.capture_message**——sentry.py:168-179——无真实异步收益，调用方按 async 理解却有阻塞 I/O。
- **SNT5 [P3] init_sentry 全局初始化无锁——多协程并发 init 竞态**——sentry.py:30 `if _sentry_initialized: return` 后执行初始化——两协程同过检查 → 二次 init——DCC1 无锁单例家族（同 SNT6/HTTP4/CB1）。
- **STA2 [P3] `_max_alerts = 50` 从未执行裁剪——`_alerts` 列表无限增长**——startup_alert.py:49 定义但 append 处（:104/:136/:157）无裁剪逻辑——长运行服务内存持续增长。修复方向：append 后 `del self._alerts[:-self._max_alerts]`。
- **STA4 [P3] WebhookAlertHandler 每次调用新建 httpx.AsyncClient——无连接复用**——startup_alert.py:217 `async with httpx.AsyncClient(...)`——每次告警新建客户端（与 HTTP1 客户端四轨形成第五处 HTTP 实现——但本处是主动建新即弃）。P3。
- **STA5 [P3] get_startup_alert 单例无锁——多协程首调竞态**——startup_alert.py:248-250——同 DCC1 家族。

## 三、全库交叉确认

- **死代码家族**：sentry.py/startup_alert.py 与 retry.py（上一轮）同族——**监控/告警/重试三件套均为零消费死代码**——本库「完备封装但未接入」是系统性模式（第十处双轨族）。
- **静默失真家族**：SNT2 与 RG1（resource_guard）/SL3（system_load）/EC3（error_handler）同族——**未初始化即静默 return**。
- **无锁单例家族**：SNT5/STA5 与 CB1/HTTP4/DCC1/SC2/CRY6 同族——第 8 处。
- **HTTP 实现第五处**：STA4 每告警新建 AsyncClient vs aicloud/image_generation/AiCodeUtil/mcp_client 四套常驻——**全库 5 处 httpx.AsyncClient 实例化模式不一致**。

## 四、测试状态

零单元测试。死代码状态、静默降级、告警列表增长均无测试约束。修复建议：① 若接入——init_sentry 幂等性测试、capture_error 未初始化行为测试；② 若删除——清理文档引用；③ _alerts 裁剪测试（超 50 条断言）。
