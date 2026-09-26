# Workflow 核心执行链（executor + state_machine + graph_validator）

> 第一百三十四轮补扫 | v1.135 | 2026-08-17 | 分析对象：`app/utils/workflow/executor.py`（440 行）+ `state_machine.py`（466 行）+ `graph_validator.py`（176 行）+ 消费方 `app/api/v1/workflow.py`（676 行）
>
> 结论：**工作流引擎三核心组件首次建档——executor 主循环有状态撒谎缺陷（执行结束却返回 status=running）、cancel 不取消运行中节点、API 侧内存工作流无 TTL/无所有权校验/状态查询恒失真**——「执行已结束但状态撒谎」与「报告≠实际」家族在任务编排层的实例。

## 一、模块定位

| 组件 | 位置 | 消费状态 |
|------|------|----------|
| WorkflowExecutor | executor.py:69 | app/api/v1/workflow.py:187/:327/:427 真实消费 |
| NodeFactory（按 TaskType 创建节点） | executor.py:45 | executor._execute_node:219 使用 |
| WorkflowStateMachine | state_machine.py:64 | 仅 executor 实例化（:308） |
| GraphValidator / validate_task_graph | graph_validator.py:26/:151 | workflow.py:127/:371 真实消费 |
| ResultAggregator | result_aggregator.py | executor:311（本轮仅确认，详扫下一轮） |
| TaskDecomposer | task_decomposer.py | workflow.py:124（LLM 分解，详扫下一轮） |

执行链路：`POST /api/v1/workflow/execute` → TaskDecomposer.decompose（LLM 自然语言→TaskGraph）→ GraphValidator.validate → WorkflowExecutor.execute（NodeFactory 按类型建节点 → state_machine 管理生命周期 → ResultAggregator 聚合）→ SSE 流式返回。

## 二、缺陷清单

### P2（10 项）

- **WFE1 [P2] 无法继续执行时状态卡 RUNNING——执行已结束但状态撒谎**——executor.py:337-340 主循环 `if not executable and not running: break` 直接退出，不标记 FAILED——配合 state_machine `_check_workflow_completion`（state_machine.py:414-442 只检查「全节点 done」）与 `_check_workflow_stuck`（:282-308 只在 fail_node 时触发）——**场景**：图 = A→B（A 失败）+ C 独立节点。fail_node(A) 触发 stuck 检查时 C 尚可执行 → 不标记；C 完成后 complete_node(C) 触发 completion 检查——B 仍 PENDING → all_nodes_done=False → 不标记——**之后 B 永远无法执行、工作流以 status="running" 返回**——API 的 `workflow_completed` 事件 status=running、WorkflowHistory.status=running——「执行已结束但状态撒谎」（TR1/MAR8 成功态谎报家族的**失败态镜像**）。修复方向：executor break 前若 failed 非空则 state_machine 标记 FAILED；complete_node 后补查 stuck。
- **WFE2 [P2] `cancel()` 只置 cancel_event 不取消运行中的节点任务——节点资源泄漏**——executor.py:429-432——主循环检查 is_set 后 break，但运行中节点的 `_execute_node` 任务（LLM/HTTP 调用）未被 cancel——`finally: await self._cleanup()` 只 clear dict 不 cancel task——**运行中调用继续执行至自然结束**（LLM 计费/资源泄漏）。修复方向：break 前 `for t in self._running_tasks.values(): t.cancel()`。
- **WF1 [P2] 内存工作流/会话字典无 TTL 清理——无界增长**——workflow.py:45-49 `_workflows`/`_session_workflows` 进程内 dict——`_workflows` 仅用户 DELETE 才删、`_session_workflows` 永不清理——task_graph 全量常驻（含节点参数），多用户长跑后内存膨胀（MCP1/GRD2 内存无界家族）。
- **WF2 [P2] status/export/delete 端点无用户所有权校验——跨用户越权**——workflow.py:315-355/:538-567/:581-591 只查 `_workflows[workflow_id]`——`:149/:385` 存入的 `user_id` **从不参与鉴权**——任何登录用户可读取他人工作流 task_graph（含业务参数/LLM 分解结构）并删除——跨用户信息泄漏 + 越权删除（CS 越权家族）。
- **WF3 [P2] `get_workflow_status` 永远返回 running——状态查询端点恒失真**——workflow.py:322-334——execute 流程（:145-150）只存 task_graph/request/user_id，**从不回写 aggregator**——status 端点 `workflow_data.get("aggregator")` 恒 None → 新建空 executor → 空 ResultAggregator → `is_complete()`=False → status 恒 "running"——**每次调用新建实例、永远拿不到真实执行进度**。
- **WF4 [P2] 客户端断开不取消执行——后台节点继续跑**——workflow.py:216-232——StreamingResponse generator 被关闭后 `executor_task` 无 finally cancel——SSE 断连 → LLM 分解/节点执行继续至自然结束——与 WFE2 叠加整条取消链缺失（LMC6 信号量泄漏同族触发面）。
- **STM2 [P2] `check_node_timeout` 从未被调用——节点超时检测死代码**——state_machine.py:351-370——executor 用 `asyncio.timeout` 包裹节点（executor.py:251），state_machine 的节点级超时方法全库零调用——**两套超时机制并存、状态机侧为死路径**。
- **GV1 [P2] `validate` 无参数语义校验——import 只查结构放行、运行时才失败**——graph_validator.py:40-58 只校验 ID 唯一/依赖存在/类型合法/环/条件分支引用——**不校验 `node.params` 与类型匹配**（code_execution 缺 code、llm_call 缺 prompt、conditional 缺 condition/true_branch、human_approval 缺消息等）——`POST /workflow/import`（workflow.py:358）任意 JSON 放行——「接线≠正确」家族在任务图验证层（DGV1 同族）。
- **GV2 [P2] `on_failure` 取值不校验——未知策略行为未定义**——schema/workflow.py:61 `on_failure: str = "fail"` 无 Literal 约束——GraphValidator 不校验取值——executor `_execute_node` 对未知取值落 fallback 分支行为未定义（skip/fail/fallback 三态之外的任意字符串）。
- **WF5 [P2] 内存态工作流多 worker 不可用 + 重启丢失**——process 级 dict 状态——gunicorn 多 worker 下 execute 请求落 worker A、status 请求落 worker B 查不到 → 404——重启后全部工作流/会话丢失（CS1/TM3/GRD2 内存态家族）。

### P3（7 项）

- **WFE3 [P3] `_compute_topological_order`/`order_index` 死代码**——executor.py:320-321 计算结果从未使用（只 log 长度）——实际调度由 `_get_executable_nodes` 动态 BFS 承担——拓扑排序是重复死实现。
- **STM1 [P3] `_lock` 定义了从未使用**——state_machine.py:95 `self._lock = asyncio.Lock()` 全文件零引用——同步方法在单事件循环原子故无实际竞态，但文档误导 + `get_snapshot`/`get_execution_summary` 跨协程读取非原子。
- **STM3 [P3] cancel_workflow 将 RUNNING 节点置为 FAILED**——state_machine.py:326-329——节点级无 CANCELLED 概念——summary 中 failed 计数含被取消节点——取消与失败语义混淆。
- **STM4 [P3] `_check_workflow_stuck` 判定窗口局限**——state_machine.py:282-308 只在 fail_node 触发且只查「当前无任何可执行节点」——失败节点 + 独立节点路径时序下漏判（WFE1 根因），complete_node 后不复查。
- **STM5 [P3] `get_execution_summary` 跨协程非原子读取**——state_machine.py:444-466 状态与节点计数分步读取——与外部并发调用时计数可能不一致。
- **GV3 [P3] `_check_node_id_uniqueness` 用 `node_ids.count(id)` O(N²)**——graph_validator.py:64——大图 import 性能退化。
- **GV4 [P3] 无节点数/图规模上限**——graph_validator 无 max_nodes 校验——大图 import/LLM 分解无保护（DoS 面）。

## 三、全库交叉确认

- **「报告≠实际」状态撒谎家族**：WFE1（执行完 status=running）与 TR1/TG4/DR7（成功态谎报）同族——**任务编排层同时存在「失败态谎报」与「成功态谎报」双向失真**；WF3（status 端点恒 running）是其 API 侧暴露点。
- **内存态状态家族**：WF1/WF5 与 CS1（CSRF）、TM3（任务状态内存/Redis 分裂）、GRD2（限流内存）同族——**工作流/会话/任务状态全部进程内存，多 worker 部署集体失效**。
- **越权家族**：WF2 与 PG1（游标伪造越权遍历）同族——**所有进程内存工作流接口缺所有权校验**。
- **取消链缺失**：WFE2/WF4 与 LMC6（流式信号量泄漏）叠加——**SSE 断连后 executor 与 LLM 层都没有可靠回收**。
- **验证语义缺失**：GV1 与 DGV1（依赖图验证兜底通过）、CV1 同族——**「结构验证放行、语义运行时才失败」在任务图验证层再现**。
- **死代码家族累计第 12 处**：STM2（check_node_timeout）+ WFE3（拓扑排序）——executor 侧两套调度/超时实现并存、state_machine 侧为影子。
- **与 orchestrator_generation 的对比**：app/agent 侧也有 DependencyGraphValidator（依赖图验证，第一百零三/九十五轮建档）——app/utils/workflow 的 GraphValidator 验证任务图（TaskGraph），两者语义不同非双轨，但**验证器兜底失效模式（DGV1）在 GraphValidator 侧表现为「结构过、语义漏」**——同一失效方向不同形态。

## 四、测试状态

零单元测试（grep tests/ 无 workflow/executor/state_machine/graph_validator 引用）。WFE1（stuck 卡 RUNNING）、WF2（越权）、WF3（status 恒 running）、GV1（缺参数放行）全部实码可证但无任何用例保护。修复建议：① WFE1 补 stuck 复查 + break 前标记 FAILED 测试；② WFE2 取消运行中任务测试；③ WF2 所有权校验；④ WF3 注册活跃 executor 到 _workflows；⑤ WF1/WF5 TTL 清理或落库；⑥ GV1 参数 schema 校验；⑦ 后续轮次扫 result_aggregator/task_decomposer 与 node_types/ 10 节点。

## 五、状态更新（2026-09-18 核实）

按当前代码逐条核实。文档成文后本模块已被大幅修复，实际状态如下：

**已修复**

- **WFE1 已修**：`WorkflowStateMachine.complete_node` 末尾新增 `self._check_workflow_stuck()`（state_machine.py:249-252），节点完成后复查失败节点是否阻塞全部剩余路径，避免以 RUNNING 永久挂起。
- **WFE2 已修**：`WorkflowExecutor.cancel()` 除置位 `_cancel_event` 外，同步 `task.cancel()` 运行中节点任务（executor.py:435-444）。
- **WF2 已修**：`get_workflow_status`/`export_workflow`/`delete_workflow` 均校验 `workflow_data["user_id"]` 与 token 主体一致，不一致返回 404（workflow.py:364-366/:583-590 等）。
- **WF3 已修**：status 端点优先从 `workflow_data["executor"].get_aggregator()` 取聚合器，`status` 取 `workflow_data["status"]`（execute 流程收尾回写），不再每次新建空 executor（workflow.py:369-375）。
- **WF4 已修**：流式响应 `finally` 块调用 `executor.cancel()` 并 `executor_task.cancel()`（workflow.py:281-286）。
- **GV2 已修**：`TaskNode.on_failure` 已改为 `Literal["fail", "skip", "fallback"]`（app/schema/workflow.py:61），`TaskDecomposer` 另有 `_normalize_on_failure` 兜底非法取值。

**本轮修复**

- **GV3 已修**：`_check_node_id_uniqueness` 由 `node_ids.count(id)` 的 O(N^2) 改为 `Counter` 单次遍历（graph_validator.py:60-66）。行为不变，纯复杂度优化。新增 `tests/unit/test_workflow_graph_validator.py`（2 项）；因属行为保持的重构，回退源码后测试仍通过。
- **GV1 已修（导入入口）**：`GraphValidator.validate` 新增 `check_semantics` 开关（默认 False，保持既有结构校验契约），开启时调用 `_check_node_params`——按 `TaskType` 延迟加载对应节点类并复用其 `validate_params()`，校验必填项与取值。`POST /workflow/import` 显式传入 `check_semantics=True`，外部 JSON 缺 `query`/`code`/`prompt` 等必填参数在导入即被拦截，不再放行到运行时报错。自然语言 `execute` 流程与 executor 逐节点校验保持原状，未改动其行为。新增 3 项回归测试（缺参数拦截、合法参数通过、默认关闭）。

**GV4 已修**

- **GV4 已修**：`GraphValidator` 新增 `MAX_NODES = 200` 类常量与 `_check_graph_size` 校验（`__init__(max_nodes=MAX_NODES)` 可覆盖），`validate` 首先检查节点总数，超大图在校验阶段即被拒绝，阻断 LLM 分解/外部导入超大图带来的资源耗尽。既有 `test_unique_node_ids_pass`（500 节点）关注唯一性而非规模，已显式传 `max_nodes=1000` 保留其构造意图。新增 3 项回归测试。

**仍存在（需产品口径或较大改动）**

- **WF1 TTL 已补（2026-09-26）**：`_workflows` 已有 `_MAX_WORKFLOWS = 500` 上限并在写入时淘汰最旧项，`_session_workflows` 亦有 `_MAX_SESSION_WORKFLOWS = 200` 上限与按 `updated_at` 淘汰最旧会话。本轮补齐缺失的**按 TTL 过期**：新增 `_is_expired` / `_prune_expired`，`_workflows` 条目补记 `updated_at`（创建、置 running、完成回写三处均刷新），写入新工作流与 `_remember_session_workflow` 时惰性清理超过 24h 的条目。`keep_running=True` 使 `status == "running"` 的工作流不被清理，避免误断正在执行的任务；缺时间戳或格式非法的条目视为未过期，避免误伤。回归 `tests/unit/test_workflow_cache_ttl.py`（6 项，回退 `workflow.py` 后 5 项失败）；容量淘汰用例 `test_session_workflows_evict_oldest` 的时间戳已改为相对当前时间以适配 TTL。**仍未改**：超限淘汰是 FIFO 而非 LRU，属优化项。
- **WF5**：进程内存态在多 worker 部署下仍不可用、重启即丢失（与 WF1 同根）。修复需把工作流/会话状态落库（`WorkflowHistory` 已存在，但 status/continue 链路尚未改走 DB），属架构级改动。
- **STM2**：`check_node_timeout` 仍全库零调用，节点超时由 executor 侧 `asyncio.timeout` 承担，状态机侧方法为死代码。删除涉及公共方法面，保留待确认。
