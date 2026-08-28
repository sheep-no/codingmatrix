# AI Agent API 端点包首扫（orchestrate_endpoints + helpers + generate_endpoints + schemas + 其余小端点）

> 第一百四十二轮推演 | v1.143 | 2026-08-26 | 分析对象：`app/api/v1/ai_agent/` 9 文件——`orchestrate_endpoints.py`（1582 行）+ `helpers.py`（755 行）+ `generate_endpoints.py`（470 行）+ `schemas.py`（424 行）+ `association_endpoints.py`（126 行）+ `knowledge_endpoints.py`（102 行）+ `performance_endpoints.py`（78 行）+ `project_config.py`（42 行）+ `router.py`（14 行），共 3596 行
>
> 结论：**AI Agent 对外端点包第一次建档。会话操作端点存在跨用户越权硬缺口（AA1 队列短路绕过归属校验、AA2 快照三端点零归属校验）——「越权家族」从 aicloud 审查链扩散到 Agent 生成链；同时「归属校验正确书写但被绕过」「路径校验前缀匹配」「schema 定义未接线」三类模式在本包内各再现一例**。

## 一、模块定位

| 文件 | 职责 | 路由挂载 |
|------|------|----------|
| router.py:9 | `APIRouter(prefix="/agent")`，聚合 5 个子路由 | — |
| orchestrate_endpoints.py | 主编排端点：`/modify`（SSE 增量）、`/orchestrate`、`/orchestrate/stream`（SSE）、`/stop`、`/complete`、快照三端点、会话操作、token 统计等 | `router.py:4` |
| generate_endpoints.py | 生成/文件端点：`/generate`、`/generate/download`、`/generate/files`、`/generate/read`、`/generate/file`（DELETE）、`/save`、`/saved` | `router.py:3` |
| helpers.py | 会话管理工具：路径校验、会话创建/状态/僵尸清理、意图检测、zip 打包、单例获取 | 被 orchestrate/generate 消费 |
| schemas.py | Pydantic 请求/响应模型 + 输入安全校验 | — |
| association_endpoints.py | 需求联想：`/requirement-association`（POST/confirm/helpfulness/stats） | `router.py:5` |
| knowledge_endpoints.py | 记忆知识：`/knowledge`（POST/GET/search） | `router.py:6` |
| performance_endpoints.py | 性能监控：`/performance`（GET/trends/export） | `router.py:7` |
| project_config.py | 常量：`./projects` 基目录、MIME 表、白名单包、跳过目录 | 被 helpers/generate 消费 |

### 依赖链

| 方向 | 模块/位置 | 说明 |
|------|-----------|------|
| 被消费 | app/api/v1/AiProjectCode.py `create_agent_session` :39 / `log_tool_execution` :62 / `update_model_stats` :87 | orchestrate_endpoints.py:105、:457、:482-496——AiProjectCode 本体未建档（下轮候选） |
| 被消费 | app/agent/orchestrator.py `OrchestratorAgent` | orchestrate_endpoints.py:19、:347、:465、:776、:1328 |
| 被消费 | app/utils/security.py `verify_token` | 全部端点 |
| 被消费 | app/db/database.py `get_db` / `async_session` | 全部 DB 端点 |
| 被消费 | app/db/models.py `ProjectSession` | helpers/orchestrate |
| 被消费 | app/agent/session_manager / spec_cache / feedback_learner / conversation_store / git_operations / snapshot_manager / impact_analyzer / project_profiler / test_selector / failure_clusterer / multi_model_agent | orchestrate_endpoints.py:121、helpers.py:242-264 等——均为已建档模块 |
| 被消费 | app/utils/guardrails.py `check_disk_space` / `check_rate_limit` / `validate_session_id` | orchestrate_endpoints.py:122-124、:254-261、:519-526 |
| 被消费 | app/utils/dynamic_concurrent.py `ConcurrentLimitManager` | orchestrate_endpoints.py:687-689、:819 |
| 被消费 | app/utils/system_config.py `system_config_manager` | orchestrate_endpoints.py:528、:1253-1280 |
| 被消费 | app/models/saved_project.py `SavedProject` | generate_endpoints.py:22 |
| 被消费 | app/services/agent_memory_service.py `AgentMemoryService` | knowledge_endpoints.py:7 |
| 被消费 | app/utils/performance_metrics.py `metrics_collector` | performance_endpoints.py:9 |
| 测试 | 包内零测试（app/api/v1/ai_agent/ 无 test 文件） | |

## 二、缺陷清单

### P2（3 项）

- **AA1 [P2] 会话操作越权：队列存在即跳过所有权校验**——orchestrate_endpoints.py:1440-1452 `_verify_session_ownership_or_queue`：`if session_id in _approval_queues or session_id in _decision_queues: return`——**任何登录用户只要知道一个运行中会话的 session_id，即可通过 `/session/{session_id}/action?action=cancel`（:1348-1412）取消他人项目、删除他人项目文件（cleanup_session_files rmtree）、或 approve/reject 注入审批结果；也可 `/session/{session_id}/decision`（:1415-1437）注入架构决策**——session_id 格式 `{user_id}_{resolved_name}`（:98 `f"{user_id}_{resolved_name}"`，resolved_name 常为 `untitled_{时间戳}`）可被枚举/从共享链接推测——`verify_session_ownership`（helpers.py:475-510）书写的归属校验被此短路完全绕过——**跨用户越权家族（GH5/RQ1 同族）在 Agent 生成链再现，且比审查链更直接（cancel 会物理删除文件）**。
- **AA2 [P2] 快照三端点零归属校验 + session_id 路径直拼**——orchestrate_endpoints.py:1178-1194 `list_snapshots`、:1197-1223 `rollback_to_snapshot`、:1226-1244 `diff_snapshots`——均无 token 用户归属校验、无路径净化——`project_dir = Path(f"orchestrator/{session_id}")`（:1186）session_id 用户可控（可含 `../`）——`rollback` 默认 `delete_branch=True`（:1201）对任意目录执行 `git checkout --hard + branch -D`（快照管理器行为，git_operations GO2/GO12 缺陷一并暴露）——**任何登录用户可越权读取/回滚任意 git 仓库**（跨用户越权家族 + 路径穿越）。
- **AA3 [P2] ModifyRequest.session_id 无格式校验 → delete_session_endpoint 的 rmtree 路径注入**——schemas.py:307-320 `ModifyRequest.session_id` 无 validator（对比 `OrchestratorRequest.session_id` :246-249 有 `validate_session_id`）——`modify` 端点（orchestrate_endpoints.py:294）直接取 `request.session_id` 建会话记录——攻击者先用恶意 session_id（如 `../foo`）创建记录，再 `DELETE /sessions/{session_id}`（:1455-1488）——DB 归属校验命中（记录属于攻击者）→ 清理阶段对 `./projects/orchestrator/{session_id}` 等三路径执行 `shutil.rmtree`（:1481-1486）——session_id 含 `..` 可删除 projects 目录之外任意子目录（URL 规范化降低实际利用概率，但**校验与清理两侧路径语义不一致**的结构漏洞成立）。

### P3（7 项）

- **AA4 [P3] `_validate_project_path` startswith 前缀匹配——路径边界绕过**——helpers.py:46-51 `str(project_dir).startswith(str(base_dir))` 无 os.sep 边界——`/workspace/projects-evil` 通过 `/workspace/projects` 前缀检查（GH4/CE2/SB1 家族）——generate_endpoints.py 四个文件端点（download :126 / files :167 / read :208 / delete :254）全部依赖——用户归属校验（helpers.py:61-71 目录名末段匹配 user_id）部分缓解越权，但**结构缺陷与 GH4 同源（比 file_operator.py:128 更宽松）**。
- **AA5 [P3] requirement-association 反馈无用户绑定**——association_endpoints.py:77-111 `confirm`/`helpfulness` 端点——`AssociationFeedbackTracker()` 内存态、association_id 无归属校验——**任意用户可对任意 association_id 记录反馈**，stats 端点（:114-127）全站可见统计被污染（RQ1「审查队列无用户隔离」同族在反馈侧再现）。
- **AA6 [P3] 7 个 schema 定义未接线（死代码家族第 30 处）**——schemas.py 中 `FileOperationRequest` :84 / `AgentRequest` :55 / `ReActRequest` :128 / `SessionActionRequest` :280 / `ProjectSessionConfigRequest` :338 **全库零引用**（grep 仅定义处出现）；`RequirementAssociationConfirmRequest` :348 / `RequirementAssociationHelpfulnessRequest` :352 被 association_endpoints.py:9-14 import 但**端点实际用 query 参数**（:79 `association_id: int`、:99 `association_id: int`）——7 类 0 消费（「能力未接线」家族，与 SCT5 同族）。
- **AA7 [P3] `_validate_project_path`「兼容旧格式」分支冗余**——helpers.py:64-68——目录名含下划线时 `parts[-1] == parts[1]`，两分支条件等价（`len(parts)==2 and parts[1]==user_id` 与 `user_id==parts[-1]`），仅目录名无下划线时第二分支兜底（`user_id==dir_name`）——分支语义重叠、注释「兼容旧格式」误导（生成路径 :51 恒为 `{ts}_{uid}_{user_id}` 三段式，旧格式分支不可达）。
- **AA8 [P3] `/cache/clear` 无 admin 门禁**——orchestrate_endpoints.py:1290-1297——任意登录用户可清空全站 SpecCache（`mode="all"`）——普通用户可制造全站缓存失效（成本/性能面，与 GitHub GH7 假存储同属管理端点权限粒度问题）。
- **AA9 [P3] `generate_project` 无 rate limit / 磁盘检查**——generate_endpoints.py:41-124——对比 `modify`（:254-261）与 `orchestrate/stream`（:519-526）均有 `check_rate_limit` + `check_disk_space`——generate 端点防护缺失，可被刷取（每请求创建项目目录）。
- **AA10 [P3] `generate_project` 影子变量 + user_id 直拼路径**——generate_endpoints.py:45 `request: Request = None` 遮蔽模块级 `Request` 类型标注（:11 import）——:51 `f"./projects/{timestamp}_{unique_id}_{user_id}"` user_id 未校验 isdigit/字符集直接拼路径（对比 modify :250 / stream :515 强制 `user_id.isdigit()`）——`verify_token` 的 `sub` 异常值时路径注入面。

## 三、全库交叉确认

- **「越权家族」主线确认**：第一百四十轮 RQ1（审查队列无用户隔离）+ GH5（approve 无 pending 校验）→ 本轮 AA1（会话操作队列短路）与 AA2（快照三端点零校验）——**aicloud 审查链与 Agent 生成链两条会话式链路都存在「归属校验缺失或被绕过」**，模式统一：内存队列/路径直拼 + 未按 user_id 隔离。
- **SSE 修复痕迹**：PASSTHROUGH_SSE_EVENTS（orchestrate_endpoints.py:26-36）注释记录 v5.x→v6.x 修复 progress 包装错误——与 performance_monitoring PM1（BaseHTTPMiddleware 缓冲 SSE）无冲突（本端点用 StreamingResponse 直出）。
- **审批链双套并存**：本包 approval_callback（:700-731，300s 超时自动拒绝，走 `_approval_queues`）与 aicloud review_queue（submission_api GH5/GH6）——**两套审批机制**（前端会话审批 vs 沙箱审查队列），本包审批写文件走 OrchestratorAgent 内部、不经 review_queue（与 GH6 的裸 open 写出道不同，本包无直接落盘面）。
- **快照端点复用已建档缺陷模块**：list/rollback/diff 三端点直接调用 git_operations/snapshot_manager——git_operations.md GO2（删除当前分支永远失败）/GO7（current_tag 谎报）/GO12（reset --hard 无备份）缺陷在 rollback 端点行为上原样暴露。
- **路径校验双轨**：schemas.py `validate_path_safety`（:40-52，严格拒绝绝对路径 + `..`）与 `FileOperationRequest.validate_path`（:100-108，`".." in v` + startswith `/` + `\`）——两套路径校验实现（双轨家族），且 FileOperationRequest 本身是死代码（AA6）。
- **僵尸会话清理**：helpers.py:323-393 `_detect_and_clean_zombie_sessions` 按 7 天阈值 + 内存无状态判定——与 process_guard 链无冲突，但 `ProjectSession.user_id == int(user_id)`（:341）依赖调用方已 isdigit 校验（orchestrate/stream :515 有、其它端点无）。
- **与第一百四十一轮衔接**：validators 零消费与 AA6 的 7 个死 schema 同属「能力/定义未接线」模式——本包 7 类死 schema 累计死代码家族第 30 处。

## 四、潜在问题与未知点

- `_active_tasks`（:129）与 `_approval_queues`/`_decision_queues`/`_cancel_events`（:126-128）为进程内存字典——**多 worker 部署下浏览器重连/审批/取消跨 worker 全部失效**（WF5/DP1 家族），`_active_tasks` 无 TTL 清理（任务异常消亡残留）。
- `complete_project`（:983-1031）完成后**物理删除项目文件**（cleanup_session_files），与 generate 成功保留文件的语义不同——「完成」即删除与用户预期可能不符（与 stop_project :952-956 同向）。
- `_cleanup_old_session`（helpers.py:268-320）用 `History.metadata_json.contains(f'"session_id": "{...}"')` 字符串匹配删除历史——JSON 序列化格式变化即漏删（脆耦合）。
- knowledge_endpoints 的 `KnowledgeResponse.id: str`（schemas.py:170）与 service 返回的 int id——依赖未建档的 agent_memory_service，待下轮确认类型契约。
- 新增 P2 3 项、P3 7 项——Backlog 1036→1046（P2 389→392、P3 577→584）。

## 五、修改建议（改什么 → 达成什么目的）

| # | 优先级 | 修改动作 | 达成目的 | 涉及位置 | 对应 Backlog |
|---|--------|---------|---------|---------|-------------|
| 1 | P0 | `_verify_session_ownership_or_queue` 删除队列短路，或队列按 `(user_id, session_id)` 绑定后再查 DB | 关闭 AA1 越权取消/审批入口 | orchestrate_endpoints.py:1440-1452 | #1037 |
| 2 | P0 | 快照三端点补 `verify_session_ownership` 归属校验 + session_id 走 `validate_session_id` | 关闭 AA2 越权 git 操作 | orchestrate_endpoints.py:1178-1244 | #1038 |
| 3 | P0 | `ModifyRequest.session_id` 加 `validate_session_id` validator + delete 清理路径改用 resolve 后 is_relative_to 校验 | 关闭 AA3 rmtree 路径注入 | schemas.py:307-320、orchestrate_endpoints.py:1455-1488 | #1039 |
| 4 | P1 | `_validate_project_path` 改 `os.path.commonpath`/`is_relative_to` 边界校验 | 修复 AA4 前缀碰撞 | helpers.py:46-51 | #1040 |
| 5 | P1 | 反馈记录绑定 user_id + association 归属校验；或删除 confirm/helpfulness 端点 | 修复 AA5 反馈污染 | association_endpoints.py:77-111 | #1041 |
| 6 | P2 | 删除 7 个死 schema 或接线（FileOperationRequest 若为工具预留需显式声明） | 清理 AA6 死代码 | schemas.py | #1042 |
| 7 | P2 | `/cache/clear` 加 `verify_admin_token` | 修复 AA8 权限粒度 | orchestrate_endpoints.py:1290-1297 | #1043 |
| 8 | P2 | generate 端点补 rate limit/磁盘检查 + user_id isdigit 校验 | 修复 AA9/AA10 | generate_endpoints.py:41-124 | #1044 |

## 六、演化方向关联

- **越权收敛主线（§5.1 权限）**：AA1/AA2/AA3 与 RQ1/GH5 汇合——**所有「会话式长链路」（审查/审批/生成/快照）应统一走同一套 user_id 归属校验中间件**，而不是各端点自行校验再被短路。
- **路径校验收敛（§5.6 支柱 1）**：AA4 与 GH4/SB1/validate_path_safety 双实现——统一到「resolve + is_relative_to」边界语义。
- **死代码收敛（§5.4）**：AA6 的 7 个死 schema 与 validators 包级孤立同模式——「定义存在但零消费」在 API 层的新证据。
- **下轮候选**：`app/api/v1/AiProjectCode.py`（本包依赖的上游，create_agent_session/log_tool_execution/update_model_stats 未建档）或 `app/utils/pptx/` 12 文件。
