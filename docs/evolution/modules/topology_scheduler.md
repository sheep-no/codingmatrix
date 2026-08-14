# TopologyScheduler 深扫（topology_scheduler.py，521 行）

> 第七十八轮推演 | 2026-08-13 | 定位：spec_first 链的动态拓扑调度执行器（生产活跃，非死代码）

## 1. 模块定位

TopologyScheduler 在 spec_first 链的文件生成阶段按依赖图实时调度：依赖计数 0 的文件入就绪队列 → 并行生成 → 完成后触发下游递减 → 依赖计数归零即就绪。声称「保证任意文件生成时，其所有上游代码已确定，彻底杜绝接口猜测」。含心跳监控（HeartbeatTracker，同时被 react_engine 独立使用）。`use_dynamic_topology` 默认 True（orchestrator.py:53），spec_first:303-308 生产活跃路径。

### 依赖链

| 方向 | 模块/位置 | 说明 |
|------|-----------|------|
| 消费方 | `spec_first_generate.py:867-873/:1193` | scheduler.run(file_generator) 生产活跃 |
| 消费方 | `spec_first_generate.py:1275/:1499` | scheduler.get_stats() 结果面板 |
| 消费方 | `react_engine.py:18/:541` | HeartbeatTracker（心跳超时保护） |
| 上游 | `dependency_graph.py:56-57` | adjacency/reverse_adjacency 语义核对一致 |

## 2. 深扫发现

### P2 项

- **TS1 全局超时强制取消后 success=True（实测确认）**——run 主循环检测全局超时（:197-200）后 `_stop_event.set()` + 取消所有任务（:259-263）；`_generate_file_with_retry` 的 CancelledError 分支（:330-334）只设 `node.error` 后 `raise`，**节点 status 保持 GENERATING 不落 FAILED**（且 raise 跳过 :341-344 的 FAILED 标记块）。run 返回的 `success = len(failed_files)==0`（:281），而 failed_files 只统计 FAILED 状态节点（:275-278）→ **全局超时取消后所有节点仍是 GENERATING/READY，failed_files 为空 → success=True**。实测 `global_timeout=1.0` + 生成器 sleep 3s → `success: True, generated_files: {}, stats.completed_files=0`——**调度完全失败却报告成功**，下游（spec_first:313-319 取 files_generated/errors）拿到空产物继续，错误被吞。修复方向：超时/取消路径统一把未终态节点标 FAILED（含节点 error），success 判定加入「存在非终态节点」检查。

### P3 项

- **TS2 取消路径节点状态残留**——TS1 的伴生：CancelledError 分支 raise 后 `async with self._lock`（:341）不执行，节点永久 GENERATING；若超时发生在个别任务（心跳超时 :378-387 会走 FAILED，但外部 cancel 不会），节点状态与实际不一致。
- **TS3 死参数/死字段/死统计**——`timeout_per_file`（:97/:104）接收但从未使用（心跳用 heartbeat_timeout）；`HeartbeatTracker._lock`（:36）定义未用（touch/is_alive 无锁，float 赋值原子性侥幸）；`ScheduleStats.interface_errors`（:80/:494）全模块零递增点恒 0。
- **TS4 max_concurrent 注释与实现不符**——spec_first:866-868 注释「免费模型速率限制：并行度降为 2」，实际 `max_concurrent=5`（免费模型 5 并发极易 429）。
- **TS5 progress total 硬编码偏移**——spec_first:892 `total + 5` 进度分母偏移 5、:1188 事件 `4,6` 阶段拼接，与实际 total_files 不一致，进度条显示错位（schedule 事件 real total_files+5 但 stats.total_files 未加 5）。
- **TS6 调度器复用非幂等**——`initialize_ready_queue`（:142）每次 run 重复执行，已 COMPLETED 节点 dependency_count=0 会二次入队重新生成覆盖（run 被复用或断点续传场景），无防重入保护。
- **TS7 BLOCKED 恢复依赖 dependency_count 归零**——:416 `node.dependency_count = 0` 未保存原值，若 BLOCKED 时仅部分上游完成（计数已递减但未归零），恢复置 0 跳过剩余依赖检查（:409-413 虽检查 all_completed 兜底，但计数语义已失真）。

## 3. 演化方向

### 3.1 调度器与生成链的契约

scheduler.run 返回 `success` 是 spec_first 判定整体成功的关键信号（:313-319）。TS1 使该信号在故障路径失真——「存在≠正确」主线在调度执行端的实例：**调度器能运行 ≠ 文件真生成成功**。修复应让 success 语义收紧为「全部文件 COMPLETED」，超时/取消/异常统一走终态标记。

### 3.2 与文件生成链的衔接

file_generator（spec_first:897）内部已含断点续传/交叉验证/精炼循环等重逻辑，scheduler 只做状态机编排。TS1 修复后在 spec_first:1193 run 返回处增加「非终态节点检查」即可让错误暴露。

## 4. 主线关联

- **「存在≠正确」执行端**：TS1（调度能跑但 success 失真）与 UT5（沙箱验证空转）、MEM1（embedding 恒空）同主线——故障路径静默成功
- **取消语义**：TS2（取消不落 FAILED）与 CS3（压缩中途失败丢历史）同族
- **参数虚设**：TS3（timeout_per_file 死参数）与 CLH2/SL2（data_dir/cache_dir）同族

## 5. 测试状态

无 topology_scheduler 专项测试。HeartbeatTracker 被 react_engine 使用但无独立测试；scheduler 状态机（含全局超时/取消路径）零覆盖——TS1 从未被测试暴露。
