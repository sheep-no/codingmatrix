# performance_monitor.py + performance_metrics.py 性能监控家族

> 第一百二十七轮补扫 | v1.128 | 2026-08-17 | 分析对象：`app/utils/performance_monitor.py`（161 行，API 性能中间件）+ `app/utils/performance_metrics.py`（194 行，模块性能收集器）
>
> 结论：**两模块均为真实消费——performance_metrics 被 5 个 agent 模块 + 性能 API 使用，performance_monitor 被 main.py 挂载——但存在运行时故障：orchestrator_testing.py 调用不存在的 get_last_duration() 导致测试成功却报失败**。

## 一、模块定位

| 组件 | 位置 | 消费状态 |
|------|------|----------|
| PerformanceMonitorMiddleware | performance_monitor.py:24 | main.py:200 真实挂载 |
| setup_performance_monitoring | performance_monitor.py:125 | main.py:200 |
| metrics_collector（MetricsCollector 单例） | performance_metrics.py:194 | project_profiler/failure_clusterer/impact_analyzer/test_selector/orchestrator_testing + performance_endpoints.py:23/:40/:68 |
| save_metrics / export_metrics | performance_metrics.py:135/:154 | performance_endpoints.py 暴露 API |

## 二、缺陷清单

### P2（5 项）

- **PMC8 [P2] orchestrator_testing.py:81 调用不存在的 `metrics_collector.get_last_duration('TestingMixin', 'run_tests')`——测试成功却被报告失败**——performance_metrics.py **无 get_last_duration 方法**（全库 grep 仅此一处调用）——run_tests 成功后 :81 抛 AttributeError → 外层 except（orchestrator_testing.py:98）捕获 → **`return {"success": False, "message": str(e)}`——真实通过的测试被报告为失败**——测试结果事件、进度上报全部丢失，用户看到错误的失败结论。修复方向：MetricsCollector 补 get_last_duration（自 module_metrics 读 total_time 或新增 last 字段），或改调用 end_timer 返回值。
- **PMC1 [P2] MetricsCollector 无锁——avg_time 读改写非原子——并发请求下统计竞态**——performance_metrics.py:178-180 `total_calls += 1; total_time_ms += elapsed; avg_time_ms = total/total_calls`——多协程并发 end_timer → 计数错乱（与 cache 并发命中率同）。修复方向：模块级 asyncio.Lock 或改用原子聚合。
- **PMC2 [P2] `self.metrics` 字典无限增长——每指标点 append 永不清空**——performance_metrics.py:166-170——长运行服务（Agent 任务高频调用）内存持续累积——无上限无裁剪（对比 performance_monitor 有 1000 上限）。修复方向：按模块/时间裁剪或只保留聚合。
- **PM1 [P2] PerformanceMonitorMiddleware 继承 BaseHTTPMiddleware——与 logging.py 的 RequestLoggingMiddleware 决策冲突**——logging.py:126-132 注释明确说明**不用 BaseHTTPMiddleware**（流式响应缓冲/BackgroundTask 时序副作用）——performance_monitor 却使用——流式响应（SSE）会被 BaseHTTPMiddleware 缓冲。修复方向：改用纯 ASGI 实现（参照 RequestLoggingMiddleware）。
- **PM2 [P2] request_id 用 `datetime.utcnow().timestamp()` + client_ip + path 拼接——可碰撞非唯一——与真实日志 request_id 断裂**——performance_monitor.py:41——同秒同 IP 同路径 → 同 ID（并发必然碰撞）——且与 logging.py 的 uuid4 request_id **完全不一致**——X-Request-ID 响应头与日志中 request_id 对不上——追踪断裂。修复方向：复用 structured_logging.generate_request_id 或中间件共享。

### P3（7 项）

- **PM4 [P3] Prometheus 记录 `except Exception: pass` 静默吞错**——performance_monitor.py:61-62——静默失真家族（同 SNT2/EC3/RG1/SL3）。
- **PM5 [P3] stats 键 `f"{method}:{path}"` 对动态路径（/users/123）逐实例建 key——超 1000 触发频繁增删裁剪**——performance_monitor.py:84/:105-107。
- **PM6 [P3] 裁剪 `min(self.stats, key=lambda k: count)` 每次 O(n) 全表扫描**——performance_monitor.py:106——超上限后每请求 O(n)。
- **PMC3 [P3] 缓存命中率告警每次 miss 都 append——alerts 无限增长重复刷屏**——performance_metrics.py:113-116——无去重（同一低命中率状态持续告警）。
- **PMC4 [P3] `save_metrics` 每次生成带时间戳新文件——metrics 目录无限积累无轮转**——performance_metrics.py:157。
- **PMC5 [P3] thresholds 硬编码模块名（ImpactAnalyzer.analyze 等）——与 app/agent 模块名耦合——模块改名阈值失效**——performance_metrics.py:55-58。
- **PMC6 [P3] 默认 `Path('./metrics')` 相对路径——CWD 漂移**——performance_metrics.py:50——GRD3/CRY3/PG10/SC3 家族。

## 三、全库交叉确认

- **运行时 API 断裂**：PMC8 是首例「调用不存在的公共 API」缺陷（此前均为存在但行为异常的 API）——**补扫模式新增一类**：不仅查实现缺陷，还要查调用方引用的符号是否存在。
- **中间件双轨冲突**：PM1（BaseHTTPMiddleware）vs logging.py（纯 ASGI）——同一 app 两个中间件两种实现范式——StreamingResponse 行为不一致。
- **request_id 双轨**：PM2（timestamp+ip+path 拼接）vs logging.py（uuid4）——响应头与日志断链。
- **静默失真家族**：PM4 与 SNT2/EC3/RG1/SL3 同族。
- **相对路径家族**：PMC6 与 CRY3/PG10/SC3 同族。

## 四、测试状态

零单元测试。get_last_duration 缺失、无锁统计竞态、metrics 无限增长、BaseHTTPMiddleware 缓冲流式响应均无测试约束。修复建议：① **优先修复 PMC8（运行时会炸）**——补 get_last_duration 或改调用方；② 并发 end_timer 统计一致性测试；③ metrics 内存上限测试；④ 流式响应中间件测试（SSE 不被缓冲）。
