# Interfaces

## Flutter 会话历史与重连

- `GET /api/v1/agent/sessions`：返回当前账号最近会话，`limit` 限制为 1 至 50，按最近活动时间降序排列。
- `GET /api/v1/agent/sessions/{session_id}`：返回当前账号会话详情，包含 `output_dir`、文件计数、错误信息和 `reconnectable`。
- `POST /api/v1/agent/orchestrate/stream`：显式重连传递原 `session_id`、`is_resume: true` 及必填 `requirement`；恢复路径仅订阅既有任务队列。任务已结束、进程内无任务或已有订阅返回 409，缺少会话 ID 返回 422。

`reconnectable` 表示会话处于 running、当前进程任务存活且订阅已断开。当前恢复能力覆盖未消费及后续事件，已消费事件、决策重放与进程重启续跑待实现。

## GitHub 配置

- `GET /api/v1/github/config`：返回 `username`、`token` 和 `use_github`；当前后端返回默认空配置。
- `POST /api/v1/github/config`：接收 `username`、`token`、`use_github`，返回 `success`、`message`、`username`、`use_github`；当前仅返回确认信息。

## Flutter 候选业务模块盘点

- 聊天：`POST /api/v1/chat`、`POST /api/v1/chat/stream`，另有 `/api/v1/aicloud/chat` 和 `/api/v1/aicloud/chat/stream` 双轨实现；主契约、会话字段和错误格式待确定。
- PPT：`/api/v1/pptx/outlines`、生成、质量报告、预览、下载和历史端点已挂载；涉及大纲、异步任务、质量报告和文件下载。
- 绘图：Kolors 路由已挂载，但 Flutter 所需的输入、历史、进度和结果字段尚未完成契约核对。
- 工作流：`/api/v1/workflow/import`、`/{workflow_id}/execute`、`/status/{workflow_id}`、`/history/{workflow_id}` 和 `export`；执行流使用 NDJSON，状态包含 task_graph 和 summary。
- 文件上传：`POST /api/v1/upload` 支持 100MB 单文件和 SHA256 去重；另有 `/upload/init`、`/upload/chunk/{file_id}/{chunk_index}`、`/upload/merge/{file_id}` 分片流程。

Flutter 当前未接入这些候选模块。D4 需要确定优先级、主聊天实现以及绘图输入输出后再实施页面和客户端。

聊天第一阶段已采用网页端同步接口 `POST /api/v1/chat`。Flutter 发送 `prompt`、`stream: false` 和可选 `conversation_id`，读取 `response` 与返回的 `conversation_id`。当前页面未开放模型、联网搜索、推理和文件附件选项。

聊天历史使用 `POST /api/v1/history` 获取会话列表，使用 `POST /api/v1/conversation/history` 获取详情；Flutter 页面支持选择历史会话并恢复消息。

Flutter 页面对 Token 执行密码输入和提交后清理，并显示“尚未验证绑定”。仓库/分支、持久化绑定和连接验证没有已核实的后端契约。

## 认证与公共 API

- `GET /api/v1/csrf-token`：返回 csrf_token 并设置同名 Cookie（Path=/、Max-Age=3600）。
- `POST /api/v1/login`：接收 email/password，要求 CSRF Cookie 和 X-CSRF-Token 一致且在服务端有效；返回 access_token、username、permission_level，设置 refresh_token（HttpOnly、Path=/api/v1、Max-Age=604800）并轮换 csrf_token Cookie。
- `POST /api/v1/refresh`：使用 refresh_token Cookie 和有效 CSRF 双提交；返回新访问令牌和用户信息，只轮换 csrf_token Cookie，原 refresh_token Cookie 继续保留。生产环境两种 Cookie 均为 Secure，SameSite=lax。
- `POST /api/v1/register`：注册用户。
- 服务端 logout 接口尚未找到；Flutter 退出为本地凭据与缓存清理，不发送撤销接口或 Agent stop。
- `GET /api/v1/health`：检查数据库和 Redis 状态。
- `GET /api/v1/public-key`：读取前端加密所需的公开密钥。

## Chat API

- `POST /api/v1/chat`：主聊天接口，支持流式输出、会话历史、文件理解和联网搜索。
- `POST /api/v1/code`：主聊天兼容别名，客户端迁移到 `/api/v1/chat`。
- `POST /api/v1/history`：按当前用户列出或搜索会话摘要。请求字段为 `prompt_keyword`、`limit`、`offset`；响应为 `{items, total, limit, offset}`。`items` 含 `id`、`conversation_id`、`prompt`、`response`、`thinking`、`title`、`created_at` 和 `metadata`。侧栏「搜索历史」使用该接口。
- `POST /api/v1/conversation/history`：按 `conversation_id` 读取同一会话的消息，可选 `last_history_id` 和 `limit`。

## GirlAI API

- `GET /api/v1/GirlAi/characters`：返回内置角色列表。
- `GET /api/v1/GirlAi/characters/custom/list`：返回当前认证用户拥有的自定义角色。
- `POST /api/v1/GirlAi/characters/custom`：创建用户自定义角色；角色通过 `custom_<id>` 作为对话请求的 `character_id`。
- `POST /api/v1/GirlAi`：生成一轮虚拟姬对话。自定义角色按角色 ID 和用户 ID 校验归属；模型调用成功后，legacy `chat_histories` 与 unified `sessions/messages` 在同一事务中写入。
- `POST /api/v1/GirlAi/companion/turn`：生成结构化虚拟姬伙伴回合，返回助手文本、标准化情绪和对话意图、关怀策略、最多三个文字建议、带持久化 ID 的待确认记忆候选、模型上下文、`conversation_id`、`turn_id`、`state_revision` 和能力降级信息；成功回合同步写入 legacy 与 unified 历史。同一 `turn_id` 的完成请求直接回放，活跃或失败请求返回 `409`，超过租约的 processing 请求可恢复执行。伙伴回合保持纯对话，不创建任务、不调用工具和不触发提醒。
- `GET /api/v1/GirlAi/companion/state`：返回当前认证用户的伙伴会话、最近完成回合的情绪、意图、关怀策略、文字建议、记忆授权、`state_revision` 和文字/语音能力状态。
- `POST /api/v1/GirlAi/voice/transcriptions`：接收供应商无关的标准化转写文本、置信度和时长，并使用同一 `turn_id` 进入伙伴回合；当前语音输出返回 `unavailable` 状态并保留文字回复。
- `GET /api/v1/GirlAi/memories?limit=20&offset=0&status=candidate`：分页返回当前用户的活跃记忆，可按 `candidate`、`confirmed` 或 `rejected` 状态筛选。
- `POST /api/v1/GirlAi/memories/{memory_id}/confirm`：确认并可修订当前用户的候选记忆，设置 `conversation_only` 或 `companion_allowed` 可见性。
- `DELETE /api/v1/GirlAi/memories/{memory_id}`：软删除当前用户的记忆并立即撤销后续伙伴上下文检索；跨用户资源统一返回 `404`。
- `GET /api/v1/GirlAi/history`：按 `limit` 和 `offset` 查询当前用户历史，结果按最新记录优先返回。
- `GET /api/v1/GirlAi/history/search`：搜索当前用户历史记录。
- `DELETE /api/v1/GirlAi/history?all=true`：清空当前用户 legacy 和 unified GirlAI 消息。
- `DELETE /api/v1/GirlAi/history?all=false&record_ids=<id>`：删除指定 legacy 记录，并按 `legacy_message_id` 同步清理 unified 消息。

模型供应商异常由 GirlAI 路由转换为通用 `502`，请求事务回滚，供应商原始错误细节不会返回给客户端。

GirlAI 分类阈值由 `GIRLAI_EMOTION_CONFIDENCE_THRESHOLD` 和 `GIRLAI_INTENT_CONFIDENCE_THRESHOLD` 配置，默认均为 `0.6`；单次分类超时由 `GIRLAI_CLASSIFICATION_TIMEOUT_SECONDS` 配置，回合预留租约由 `GIRLAI_TURN_RESERVATION_TIMEOUT_SECONDS` 配置。低置信度结果保留原始标签和置信度，同时对外采用 `neutral` 情绪或 `unknown` 意图。

## Agent API

- `POST /api/v1/agent/generate`：生成项目。
- `POST /api/v1/agent/modify`：修改项目或执行分析请求。
- `POST /api/v1/agent/orchestrate`：同步编排项目生成。
- `POST /api/v1/agent/orchestrate/stream`：SSE 流式编排。
- `POST /api/v1/agent/stop/{session_id}`：停止 Agent 会话。
- `POST /api/v1/agent/complete/{session_id}`：完成 Agent 会话。
- `POST /api/v1/agent/search_sessions`：查询当前用户会话。
- `GET /api/v1/agent/generate/files`：列出生成项目文件。
- `GET /api/v1/agent/generate/read`：读取生成文件内容。
- `GET /api/v1/agent/generate/download/{project_path}`：下载生成项目。
- `GET /api/v1/agent/token-usage`：读取 token 使用统计。
- `GET /api/v1/agent/sessions/{session_id}/model-context`：读取当前用户 Agent 会话的最新模型上下文；旧会话返回当前运行时默认上下文。
- `PUT /api/v1/agent/sessions/{session_id}/model-context`：合并角色模型、当前模型、调用统计和降级记录，并创建独立模型上下文 Checkpoint。

VS Code 工作台使用 `POST /api/v1/agent/orchestrate/stream` 接收 SSE Agent 事件。Agent Host 使用独立的握手会话完成本地动作协作；工作台界面提供需求输入和会话控制，Web 工作台继续提供完整的会话历史、文件管理和模型配置 UI。

## PPT API

- `POST /api/v1/pptx/outlines`：创建可编辑 PPT 大纲草稿；支持主题和素材文件 ID 输入。`num_slides=N` 表示包含系统封面的最终总页数，响应包含 `N-1` 个可编辑内容页。
- `GET /api/v1/pptx/outlines/{outline_id}?version=N`：读取指定或最新大纲版本。
- `PATCH /api/v1/pptx/outlines/{outline_id}`：创建修改后的大纲版本。
- `POST /api/v1/pptx/outlines/{outline_id}/approve`：校验并批准当前大纲版本。
- `POST /api/v1/pptx/outlines/{outline_id}/generate`：基于批准的大纲版本创建带质量模式的生成任务，任务总页数为批准快照的内容页数量加 1。
- `OutlineCreateRequest.material_file_ids`：可选素材文件 ID 列表，与主题输入共用大纲审批流程。
- `OutlineSlide.content_blocks[].metadata`：商业页面结构化字段，按叙事角色保存指标、目标、成本、周期、风险、依据、交付物、门槛、负责人和时限。
- `OutlineSlide.narrative_role`：支持 `opportunity_map`、`evidence_story`、`strategic_choice`、`execution_roadmap` 和 `decision_close`，用于选择页面商业构图。
- `GET /api/v1/pptx/{task_id}/quality-report`：读取当前用户任务的最新质量报告，包括整体分、逐页分、问题及其 `fix_action` 和重排记录；前端根据高严重度问题和两次重排记录推导人工复核页，同时兼容显式 `manual_review_slides` 标记。
- `PPTGenerate.vue` 的三步前端链路由大纲创建、版本更新、审批和按版本生成组成；生成完成后通过 WebSocket 结果中的 `ppt_id` 跳转 `PPTPreview.vue`，预览页读取质量报告并提供 PPTX 下载。

语义规划与渲染规则分别位于 `app.utils.pptx.semantic_planner` 和 `app.utils.pptx.semantic_renderer`：规划器保留页面及内容块顺序，输出容量预算、兼容布局候选、布局版本、令牌版本和确定性评分，并限制连续相同布局；渲染器将页面类型统一归一到 11 类并映射稳定视觉骨架，图片按比例适配内容框并记录裁切焦点、素材关键词和模板视觉回退规则，数据页根据关系选择柱状图、折线图、环图或散点图并生成来源占位信息与图表规则 metadata。
实际 PPTX 生成通过 `layout_type_for_slide_type()` 将语义页面接入旧布局计划；共享样式适配器把同一任务级设计令牌应用到封面和全部内容页。模板管理器注册九套独立令牌预设，规范模板 ID `business_report`、`pitch_deck` 分别进入 `business`、`creative` 构图；`business`、`creative`、`modern`、`minimal`、`tech`、`academic`、`education`、`medical` 和 `elegant` 根据 `narrative_role` 进入独立构图分支。学术主题优先显示 `evidence_sources` 的首个来源，来源缺失时显示明确的待补来源提示；教育主题使用 `Aptos`/`Arial` 回退字体并保持课程卡片的投屏字号；医疗主题提供临床证据来源占位；`elegant` 主题提供 `BOARD RECOMMENDATION` 等董事会决策语义标签。
PDF 生成采用临时 PPTX 转换链路，调用 `libreoffice --headless --convert-to pdf`；服务器缺少 LibreOffice 时返回 501，并提示安装 `libreoffice-impress`。

视觉回归工具位于 `app.utils.pptx.visual_regression`，用于生成稳定的语义布局 manifest、比较页面差异和计算 PNG 像素变化比例。服务器通过 LibreOffice 生成 PDF，再由 `pdftoppm` 生成 PNG 页面。
当前页数与模板专项验收：后端单元测试 `1947 passed, 2 skipped`，其中 PPT 相关测试 `236 passed`；大纲 API 集成测试 `5 passed`，前端全量 `51 passed`，Vite 生产构建通过；真实 PPTX 测试确认请求最终总页数 5 时输出 5 页，并验证模板主色写入生成文件。固定大纲真实生成了 PPTX、PDF 和 `1280x720` PNG 预览图。视觉复审评分为 `business 8.0/10`、`creative 8.8/10`、`modern 8.3/10`、`minimal 8.6/10`、`tech 8.0/10`，`academic` 路线页二轮评分为 `8.2/10`，`education` 代表页评分约 `7.0-7.6/10`；医疗与 `elegant` 主题 6 页真实样稿均无元素越界，`elegant` 证据页与路线页二轮评分为 `9.0/10` 和 `8.5/10`。
- `POST /api/v1/pptx/generate_task`：创建异步 PPT 任务。文本请求使用 `prompt`、`template`、`slide_count`、`output_format` 和 `options`；`options` 支持 `auto_images` 与 `enable_animation`。
- `GET /api/v1/pptx/history`：返回 `{records, total}`，前端按 `records` 消费历史列表。
- `GET /api/v1/pptx/download/{ppt_id}?format=pptx`：下载生成文件。
- `GET /api/v1/pptx/preview/{ppt_id}`：返回 PPTX 快照预览页面。
- `GET /api/v1/pptx/{ppt_id}/slides`：读取预览所需的幻灯片快照。
- `DELETE /api/v1/pptx/{task_id}/cancel`：取消生成任务。
- `GET /api/v1/ws/ppt/{task_id}`：接收进度、完成和错误事件；事件回放使用 `payload.message` 或 `payload.result` 承载详细数据。

PPT 生成支持 `pptx`、`html` 和 `markdown` 格式的严格产物分流。下载或预览请求的格式必须对应实际产物；API 与 Celery 使用共享 `ppt-artifacts` 产物卷时可以跨容器读取同一文件。HTML 标题和内容经过服务端转义，上传链路采用分块写盘。

## 图表编辑器本地契约

图表编辑器当前使用浏览器本地状态，不新增后端 API：

- 数据文件支持 `xlsx`、`xls`、`csv` 和 `json`，单文件大小上限为 2 MB。
- 自动草稿 key 为 `chart-editor-draft-v1:{username}`；草稿保存数据源 `id`、文件名、字段头、缺失值统计、图表配置和选择状态，并带有 `savedAt`、`expiresAt`。原始行数据只保留在当前页面会话内。
- 项目导出文件类型为 `chart-editor-project`，当前 `version` 为 `1`，文件名为 `chart-editor-project.json`；配置包含数据源元数据和图表配置，导入后数据源的 `data` 为空并标记为 `needsRelink`。
- 文件重新关联按数据源文件名和字段头匹配；匹配成功后重新解析原始文件并恢复关联图表，字段头变化时保留配置并提示重新选择原始文件。

该契约支持浏览器间迁移图表配置，文件内容需要由用户在目标浏览器重新选择。`localStorage` 草稿过期后由页面加载流程清理，当前会话中的撤销和重做历史使用内存快照维护。

## Web 性能快照契约

`src/utils/performanceMetrics.js` 在应用启动时安装浏览器性能采集器，并公开 `window.__performanceSnapshot`。页面每次更新指标时派发 `codingmatrix:performance-snapshot` 自定义事件，事件 `detail` 与当前快照一致：

```js
{
  schemaVersion: 1,
  buildVersion: 'string',
  route: 'string',
  navigationMs: 'number | null',
  lcp: 'number | null',
  inp: 'number | null',
  cls: 'number',
  measuredAt: 'ISO 8601 string'
}
```

`navigationMs` 记录 Vue Router 成功导航从守卫开始到确认完成的耗时；失败或取消的导航不会替换上一份成功结果。LCP 和 INP 单位为毫秒，CLS 为无单位分值。浏览器缺少对应 `PerformanceObserver` entry type 时，该指标保持 `null` 或初始值。

同步生成接口 `POST /api/v1/pptx/generate` 适用于需要即时结果的场景。请求体使用 `prompt`、`template`、`slide_count` 和 `output_format` 等字段；认证依赖 access token，接口生成任务级 PPTX 并返回 `download_url`、`preview_url` 和可编辑内容页 `slides`。响应中的 `slide_count` 与 `slides` 长度表示内容页数量，系统封面由渲染器额外生成，因此请求 `slide_count=16` 时响应包含 15 个内容页并输出 16 页 PPTX。

同步生成的大纲优先使用模型结果。模型调用失败时，游戏 AI 主题选择 `app.utils.pptx.commercial_content.build_game_ai_page_blueprint()` 作为领域化回退；其他主题使用通用商业回退。请求未提供 `api_key_token` 时跳过视觉分析并使用本地布局，视觉分析异常也会保留内容和本地布局结果。生成成功后通过同一用户归属校验下载文件。

模型上下文包含 `schema_version`、`config_version`、`roles`、`current_model`、`current_agent`、`assignments`、`fallback_history` 和 `updated_at`。接口仅接收模型标识和运行统计，不接收供应商凭据。

同步与流式编排共用 `OrchestratorRequest`：`engine` 为可选 `legacy|core`，省略时沿用服务端配置（缺省 `legacy`）；`contracts` 为可选对象，`framework` 和 `runtime` 为可选的 1–100 字符字符串。`_core_request_metadata()` 结构化传递这些字段及 `required_validation_scopes`、`allowed_files`、`change_plan`，同时派生 `requested_paths` 和 `user_requirement`。同步显式 Core 请求跳过单文件快捷路径。

HTTP body 合同由 `code_synthesis_contracts.HttpContract` 描述，`contracts.routes[]` / `contracts.endpoints[]` 可提供 `request_body_schema`、`response_body_schema`（JSON Schema 对象或布尔值）和 `serialization_guidance`（字符串），三项均可省略。索引保留旧合同的额外字段，使用 `exclude_unset=True` 保持省略字段的原有形状和摘要；body schema 或指导变化会改变索引摘要。`contracts` 请求字段继续接受旧字典结构；端点透传至 Core，索引构造时校验新增字段类型。

序列化指导应明确 HTTP JSON body 必须是 JSON 可序列化值，领域模型应按项目实际框架和版本编码。Pydantic v2 可使用 `model_dump(mode="json")`；v1 的 `dict()` 适用于 JSON 原生字段，日期、UUID 等类型还需 JSON 编码。此内容通过合同数据提供给调用方、服务端和测试生成器。`EvaluationCase.http_contracts` 默认为空，评测 runner 按 method/path 合并到旧 routes；首次与 repair 共用 `build_case_contract()`，结构化合同独立于有长度限制的需求文本。

同步响应 `output_dir` 返回 agent 实际输出目录的绝对路径；`generation_metrics` 合并 Core 的 `node_attempts/schedule_status` 与请求级 `model_call_count/token_count`。`context_summary` 对象经 JSON 序列化为字符串。评测首次请求及 repair 均显式发送 `engine="core"`；repair 将响应实际目录映射为 `PROJECTS_BASE_DIR` 下的相对路径，同时写入 `project_path/output_dir`，经端点解析和 Orchestrator 构造后落到同一目录。本地变更计划与复验使用响应实际目录，基目录本身和基目录外路径在 HTTP 请求前抛出 `ValueError`。

## State Contracts

Core 同步响应增加 `repair_feedback`：`task_id` 关联检查点，`status` 为 Core 终态，`diagnostics` 保留结构化失败原因和运行输出，`candidate_fingerprint` 为完整调度候选的内容摘要（未形成完整候选时为 null），`rolled_back` 标记具有候选文件的增量失败已回滚。该字段由 `execute_core_generation()` 投影并由 `OrchestratorResponse` 保留，旧 `errors` 字符串列表继续提供摘要。Profile 非零退出保留各最多 4000 字符的 stdout/stderr。客户端后续修复应优先使用最新候选证据，并继续以磁盘复验判断最终交付状态。

`app.agent.state.models` 定义 `State`、`StateDelta` 和 `MessageEnvelope`。State 包含 session/task 标识、revision、status、消息、计划变更、生成文件、验证结果、待执行动作、错误和 metadata。该模型已实现为可序列化契约，完整多阶段生产编排仍在迁移中。

云端生成编排使用 `app.agent.shared_context.SharedContext` 保存单文件 `FileArtifact`。产物清单通过 `get_artifact_manifest()` 输出路径、内容 hash、导入、导出、语言、依赖、状态和诊断，`is_file_ready()` 与 `are_dependencies_ready()` 用于阻止无效上游释放下游生成。

修复编排使用 `app.agent.repair_router.RepairRouter` 和 `RepairBudget`。基础语法、导入、名称和类型错误进入自动修复；业务逻辑、测试断言和未知错误进入用户确认；默认单类错误最多 3 次、任务累计最多 5 次。

`StateReducer.apply()` 要求 delta 的 `expected_revision` 等于当前 revision。成功合并后 revision 递增；具有相同 `event_id` 的消息和验证结果只应用一次，纯重复验证结果保持 revision 不变。

### Orchestrator Core Contracts

`app.agent.orchestration` 定义下一代生成编排的独立内部契约。`OrchestrationCommand` 保存 task、session、生成模式、请求和 `engine_version`；`OrchestrationState` 保存 stage、status、revision、恢复游标、已应用事件、唯一终态事件和结构化诊断；`StageResult` 与 `OrchestrationResult` 用于阶段和任务返回。所有模型使用 Pydantic 严格字段校验，checkpoint 通过 JSON round-trip 恢复。

`advance_state()` 只接受 `created -> planning -> scheduling -> generating -> persisting -> validating -> finalizing` 的相邻转换。`terminate_state()` 允许活动阶段进入 `failed`、`timed_out` 或 `cancelled`，`completed` 仅从 `finalizing` 进入。转换要求 `expected_revision`，首次应用的 `event_id` 递增 revision，已持久化的重复 `event_id` 返回原状态。

`OrchestrationStore` 是异步 checkpoint 协议，`OrchestrationCheckpointStore` 提供原子 JSON 文件实现。`OrchestratorCore` 提供 `run()`、`execute()`、`advance()`、`finish()`、`cancel()` 和 `resume()`；`execute()` 负责规划、调度、提交、成功门禁和终态收敛。`planning` checkpoint 可重新进入完整执行，其他活动阶段返回 `orchestration.resume_stage_unsupported`，已有终态 checkpoint 直接返回幂等结果。

`build_file_plan()` 将现有文件字典列表转换为不可变 `GenerationPlan`。传入 `requested_paths` 时产生 `strict` 策略，计划文件集合必须与规范化请求集合一致；省略该参数时产生 `extensible` 策略，`origin=extension` 的新增文件必须携带 `source` 和 `reason`。`normalize_plan_path()` 统一 POSIX 相对路径表示并拒绝绝对路径、父目录遍历、受保护项目文件和不受支持的分隔符。

`GenerationPlan` 保存 `version`、策略、请求路径、不可变 `PlannedFile` 元组、SHA-256 digest 和冻结时间。构建过程以结构化 `PlanIssue` 返回重复文件、缺失请求文件、范围外文件、缺失依赖、自依赖和扩展来源错误；计划模型在 JSON 恢复时重新验证文件集合、依赖集合和 digest。

`ExecutionBudget` 定义 `task_seconds`、`stage_seconds`、`file_seconds` 和 `model_call_seconds`，要求模型预算不超过文件预算、文件预算不超过阶段预算、阶段预算不超过任务预算。`OrchestrationCommand.budgets` 在任务创建时复制到 `OrchestrationState.budgets`，checkpoint 恢复保持原任务预算。

`ModelCallContext` 保存 `task_id`、`stage_id`、`file_path`、`call_id`、`react_round`、`started_at` 和绝对 `deadline_at`。`ModelGateway.call()` 约束非流式调用，`ModelGateway.stream()` 将流创建和完整迭代纳入同一墙钟 deadline；保活数据只更新 `last_keepalive_at`，业务 token 更新 `last_model_data_at`，两者均不会延长 deadline。预算到期抛出带 `model_timeout` 诊断的 `ModelCallTimeout`，取消事件抛出带 `model_cancelled` 诊断的 `ModelCallCancelled`，外部 asyncio 任务取消保持 `CancelledError` 传播并关闭底层流。
`ModelCallContext` 可选携带 `context_hash`，模型错误诊断在该字段存在时回传同一 hash，用于关联生成上下文与验证证据。
`ModelCallTelemetry` 由 `ModelGateway.telemetry_for(call_id)` 查询，保存调用起止时间、耗时、`finish_reason`、prompt/completion/total tokens、输入字符数和 `max_tokens`。非流式 OpenAI 兼容响应和流式 SSE JSON chunk 都会合并可用的 usage 与终止原因；纯文本 chunk 继续参与内容和活动追踪。

`ArtifactCommitter.commit()` 接收计划内相对路径、生成内容和模型名称，执行非空、UTF-8 大小、原子写入、磁盘回读和 SHA-256 校验。首次成功返回带稳定 `event_id` 的 `ArtifactCompletionEvent` 并登记 `SharedContext` 产物清单；相同路径和内容的重复提交返回 `idempotent=true` 且不产生第二个完成事件。写入、路径、大小或回读失败返回 `artifact_commit_failed`，磁盘与内存或清单 hash 不一致返回 `artifact_consistency_failed`。

`check_artifact_success_gate()` 比较 `GenerationPlan`、ArtifactManifest、`ArtifactCompletionEvent` 和输出目录中的业务文件集合，并校验事件、清单与磁盘 hash 以及清单验证终态。隐藏路径作为编排元数据豁免；增量模式可通过 `preserved_paths` 声明未受影响的既有业务文件，事件和清单仍严格等于冻结计划。`OrchestratorCore.finish(..., status=completed)` 要求传入成功的 `ArtifactConsistencyResult`；失败的门禁结果将任务收敛到 `failed` 并保存一致性诊断。

`ValidationReport` 位于 `app.agent.validation_report`，由 `ValidationFinding` 和 `RepairEvidence` 组成。每条 finding 包含 `category`、`message`、`file_path`、`scope`、可选错误码和 `context_hash`；报告包含稳定 `report_hash`，`passed` 表示 finding 集合为空。`authorize_repair()` 根据 finding 类别调用 `RepairRouter`，仅自动路由允许的代码/依赖修复，并通过 `RepairBudget` 记录 attempt、candidate hash 和是否应用；业务、测试与未知错误保留人工确认路径。

框架能力模型位于 `app.agent.capabilities`，内置 `http_api`、`orm`、`database`、`authentication`、`websocket`、`dependency_injection`、`test_client`、`migrations`、`command_line` 和 `frontend_ui` 能力。`app.agent.framework_profiles` 提供 Python、TypeScript、Java、Go 和 Rust 的版本化 Profile；JavaScript 与 JS 别名统一解析到 TypeScript Profile，未知框架通过 `LookupError` 暴露待配置状态。`validation_profile()` 优先选择明确框架，Go 和 Rust 可回退到唯一语言默认 Profile。
`app.agent.database_profiles` 提供 `DatabaseContract` 和 `DatabaseProfileRegistry`。内置 Profile 覆盖 SQLite、PostgreSQL 和 MySQL，记录 dialect、driver、ORM、迁移工具、事务/测试能力和测试数据库策略；未知数据库返回 `status=unsupported` 及结构化诊断，供生成和验证阶段安全降级。
`profile_context(workspace)` 将解析到的数据库契约序列化为 `database` 字段。它从项目 manifest 识别 PostgreSQL 和 MySQL，Web 项目在没有明确数据库线索时使用 SQLite CRUD 默认契约，其他未知数据库保留 `unsupported` 状态。

`GenerationScheduler.run()` 接收冻结的 `GenerationPlan`、`GeneratedContent` 异步生成器和 `ExecutionBudget`。`FileGenerationContext` 为生成器提供计划文件、已完成上游内容、尝试次数和取消事件；文件提交统一经过 `ArtifactCommitter`。`GenerationNodeStatus` 支持 `pending`、`ready`、`running`、`completed`、`failed`、`timed_out`、`cancelled` 和 `blocked`，`GenerationScheduleResult` 返回每个节点状态、完成事件、调度终态、并发统计，以及 `root_causes`、`blocked_nodes`、`timeouts` 和 `truncations` 分类结果。无效上游阻断所有后代；无就绪节点且仍存在未完成节点时记录死锁并将其收敛为 `blocked`。

`ContractIndex.from_generation_plan()` 从冻结计划的接口、文件和 HTTP contracts 创建不可变共享索引，并生成稳定 `digest`。`GenerationScheduler` 向同一任务的所有文件生成器传递同一个索引快照；`GeneratedContent.contract_refs` 声明使用的契约名称，提交前会校验这些名称已登记，缺失项返回 `operation_contract_missing`。

增量 `generation_contract.frozen_file_set` 包含变更文件和经快照、磁盘及显式授权校验的保留文件；`writable_file_set` 仅包含调度计划文件。`validate_candidate()` 的 `planned_contents` 同时包含当前候选与真实保留依赖内容，保留模块的导出符号仍需匹配导入。评测 runner 的 `project_files` 精确排除根目录 `.dep_graph.json` 编排元数据，其他隐藏文件及嵌套同名文件仍参与严格集合比较。

`ProjectSnapshot.scan()` 和 `check_artifact_success_gate()` 共用字节码缓存路径规则：仅直接位于 `__pycache__` 下的 `.pyc` 文件豁免；缓存目录中的其他新增文件仍触发计划外变化或集合差异。

`TraditionalAdapter`、`SpecFirstAdapter` 和 `IncrementalAdapter` 实现 `GenerationModeAdapter`。Spec-First 从规范或架构的 `file_plan` 冻结 strict 计划；增量模式只计划受影响文件、加载计划外依赖内容并声明 `preserved_paths`，add/modify/delete/rename 统一由 `IncrementalFileTransaction` 管理，删除-only 请求使用空生成计划。Core 内容生成返回 `GeneratedContent`，正常文件提交统一由 `ArtifactCommitter` 完成。`execute_core_generation()` 构造独立 `SharedContext` 和 checkpoint store，调用 `OrchestratorCore.execute()`，再把 adapter 终态投影为现有 API 响应。`route_generation()` 按 `AGENT_ORCHESTRATION_ENGINE` 或显式请求选择 `legacy`/`core`，默认选择 `legacy`；可选 shadow 执行只比较成功状态和文件路径集合。legacy workflow checkpoint 会记录 `engine`、`engine_version` 和 `engine_route`。

`app.agent.context_assembler` 提供 `ContextItem`、`ContextEnvelope`、`SkillPolicy` 和 `MCPToolDescriptor`。`ContextAssembler.assemble()` 按优先级排序并去重需求、计划、Retrieval、Memory 和 MCP/Skill 输入，输出稳定 `context_hash`；MCP 描述通过读写 scope、项目 scope、依赖、超时和审计字段表达权限边界。`app.agent.languages` 的 `get_language_adapter()` 和 `get_language_capabilities()` 为 Python、JavaScript/TypeScript、Java、Go 和 Rust 提供统一语言入口。

语言适配器还提供 `extract_signatures(content, file_path)` 接口。依赖图优先通过目标语言适配器提取接口，适配器可以接入语言专用解析器或受控工具链，失败时回退到内置解析器。

`app.agent.toolchain.ToolchainRunner` 只执行 `CommandSpec` 参数数组，固定使用 `shell=false`，并施加工作目录、超时和输出大小限制。子进程 `cwd` 和覆盖后的 `PYTHONPATH` 均为解析后的工作区绝对路径，其他环境从宿主复制，父进程环境保持原值；该行为防止宿主同名包遮蔽生成项目的普通包或 namespace package。`ToolchainAction` 覆盖 inspect、install、build、format、lint、typecheck、test、start、smoke 和 health；Shell 解释器和 Shell 操作符会在 `CommandSpec` 校验阶段被拒绝，Gradle/Maven wrapper 必须解析到工作区内的真实文件。
`detect_toolchain(workspace)` 返回 `ToolchainProbePlan`，包含 `status`、manifest `evidence` 和按 action 唯一的 `CommandSpec`。Node 项目只投影实际存在的 package scripts，Python 项目读取 `pyproject.toml` 工具配置，Go、Cargo、Maven 与 Gradle 项目提供各自的安装、检查、构建和测试命令；未知工作区返回 `status=unsupported`。
`official_scaffold_request(language, framework, target_dir)` 返回固定版本、参数化的 `ScaffoldRequest`；`execute_official_scaffold()` 通过安全 Toolchain 执行后调用 `import_scaffold_plan()`。导入结果包含真实文件集合、Language Adapter 解析的文件依赖和 import、`InterfaceRegistry` 公共符号以及 `DependencyManifest` manifest 依赖，并以 strict `GenerationPlan` 返回。

`app.agent.evaluation_matrix` 提供六种历史 CRUD 技术栈样例和 24 个固定评测矩阵 case，覆盖 Python、TypeScript、Go、Java、单文件/小型多文件/模块化多文件及 deterministic/llm 策略。`EvaluationRecord` 兼容旧字段，并支持首次、候选、修复后三阶段结果、独立的 `model_call_count` 和 `token_count`；`build_report()` 聚合最终成功率、Token 数、P95、缺失样例、非法指标、失败分类和按策略阶段指标。`evaluation_runner` 通过 `python3 -m app.agent.evaluation_runner <records.json>` 输出稳定 JSON 报告。旧记录缺少数据库字段时默认使用 `supported`；数据库状态为 `unsupported` 或 `experimental` 时进入 `database` 失败分类。

`app.agent.profile_discovery` 提供 `discover_profile()` 和 `probe_profile()`。发现结果包含语言、框架、应用域、证据、能力、能力缺口和 Profile 状态；manifest 识别覆盖 Pygame、Scrapy、FastAPI、Flask、Django、Python CLI、Electron、React Native、Express、NestJS、React Vite、Next.js、Go stdlib/Gin/Echo、Rust CLI/Axum/Actix Web、Spring Boot Maven/Gradle 和 Android Gradle。`build_probe_plan()` 将内置 Profile 的 lint、typecheck、build、test 和 smoke 阶段投影为安全参数数组。
`ProfileCache.record_probe()` 持久化探针状态，`promote_supported()` 要求画像处于 `experimental` 且完整 conformance checks 通过后才升级为 `supported`。
`WorkspaceProfileDocument` 是工作区 Profile 的版本化 JSON 契约，字段包含 `schema_version`、`workspace_id`、`owner_id`、`profile` 和内容 `digest`。`load_workspace_profile()` 校验文件位于授权工作区且作用域匹配；`probe_workspace_profile()` 执行 allowlist 内的有限探针并返回 `WorkspaceProfileProbeResult`；`promote_workspace_profile()` 只接受完整成功证据，并强制逐级晋级。
`profile_context()` 输出适合嵌入项目上下文的 JSON 结构，生成入口可据此读取应用域、能力集合和待处理能力缺口。
`app.agent.capability_resolver.resolve_capabilities()` 返回 `ResolvedCapabilities`，包含 required、available、missing、generation_constraints、validation_steps 和 ready 字段。
`ResolvedCapabilities.required_components` 为领域生成计划提供组件角色提示，例如游戏的 rules/renderer/input_loop、爬虫的 fetcher/parser/pipeline 和桌面应用的 window/event_handler。
`ResolvedCapabilities.component_file_plan()` 将组件角色映射为相对文件路径和组件类型，供 GenerationPlan 生成文件节点。
`add_profile_components()` 接收 Profile 上下文和现有文件计划，在 `extensible` 策略下追加领域组件及依赖，在 `strict` 策略下保持请求文件集合不变。
`ValidationCoordinator` 将 Profile 的 `validation_steps` 转换为安全 Toolchain 命令；`execute()` 返回命令结果，`to_report()` 生成统一 `ValidationReport`。

`validation_targets_for_workflow()` 从 Workflow IR 的节点技术栈解析验证 Profile，并按 `(language, profile)` 稳定去重；该结果用于生成 Agent Host 本地验证计划。Core 不直接执行这些 Profile 命令，产物完成后保存 `waiting_local_validation`，由本地结果适配器接收验证状态。

`app.agent.code_synthesis_contracts` 定义受约束合成协议：`ProjectModel` 保存语言、框架、运行时、模块、目标、入口、生成区和领域能力；`ArtifactSpec` 保存路径、角色、owner、操作、策略、依赖、验证 Profile、来源和前置条件；`ChangePlanIR` 对动态 Artifact 集合执行唯一路径、依赖闭包、DAG 和 SHA-256 digest 校验。`StrategyDecision` 返回 `scaffold`、`schema_codegen`、`template`、`patch` 或 `llm` 策略，并携带理由、能力证据和显式降级状态。

`SynthesisCapabilityRegistry.inspect()` 将现有语言 Adapter 与官方脚手架注册转换为 `SynthesisCapabilitySnapshot`。`StrategyRouter.route_plan()` 为每个 Artifact 生成决策；`project_change_plan()` 将 create/modify Artifact 投影为 Core `GenerationPlan`，并保留策略溯源字段。Core 生命周期语义尚未接入的 delete/rename 操作通过 `UnsupportedArtifactOperation` 阻断。`project_model_from_profile()`、`validation_profile_from_framework()` 和 `validation_plan_from_framework()` 将 `FrameworkProfile` 接入同一控制面及 `ValidationCoordinator`。

`app.agent.stack_adapters` 定义 `StackAdapter`、`StackChangeRequest`、`StackArtifactRequest`、`SymbolIndex` 和 `ScaffoldResult`。所有 Adapter 接受同一严格 Artifact 请求并输出 `ChangePlanIR`；`DEFAULT_STACK_ADAPTERS` 按语言/框架别名解析 FastAPI、Express、Go stdlib/net-http 和 Spring Boot Maven/Gradle。`detect()` 从 manifest 与源码入口构造 `ProjectModel`，`capabilities()` 返回框架 `CapabilitySet`，`synthesis_capabilities()` 返回解析、编辑、编译、测试与脚手架能力，`extract_symbols()` 委托 Language Adapter，`validation_profile()` 委托 Framework Profile bridge。官方脚手架缺失时 `scaffold()` 返回显式 unsupported 结果。

`app.agent.synthesis_validation` 定义候选验证控制面。`SynthesisCandidate` 保存候选 ID、生成策略、动态 Artifact 内容、变更行数、模型调用数和上下文 hash；`CandidateBudgetTracker` 分别限制任务总候选数和单策略候选数。`CandidateValidationRouter.validate()` 固定从 `ValidationLevel.V0` 顺序运行到 `V6`，结果必须形成从 V0 开始的连续前缀，并在首次 `failed`、`unsupported` 或 `budget_exhausted` 状态停止。

`app.agent.declarative_contracts` 定义不可变 `ContractDeclaration`、`ContractAssertion`、`ArtifactFacts`、`ContractGateResult` 和 `CandidateValidation`。声明断言引用命名事实集并选择 `equals`、`contains_all` 或 `excludes_all`；`compare_contract()` 只比较声明操作数，缺少事实解析能力时返回 `status=unsupported` 和 `contract.fact_unsupported`。`validate_candidate()` 组合声明比较、语言诊断和冻结依赖闭包检查。`LanguageAdapter.extract_contract_facts()`、`source_diagnostics()` 和 `repair_source()` 分别负责源码事实、语言语义诊断和最小修复候选；修复候选重新调用同一门禁。Python 实现仅在源码可静态确定时校验外部模块导出，并诊断无构造能力的本地普通类带参调用；最小修复可移除未引用的无效导入，或从当前文件唯一可确认的提供模块补全未定义名称。`GenerationPlan.files[].contract` 负责在冻结计划和兼容投影之间保留版本化声明。

`app.agent.orchestration.StackRepairCandidate` 兼容导出 Stack 模块的候选类型，记录 `strategy`、`file_path`、`content`、`trigger_reason`、`input_contract_digest` 和 `candidate_version`。`_contract_retry_candidate()` 保留候选构造面；固定样例源码 fallback 及 `_contract_retry_fallback()` 已从 Core adapter 移除。
`app.agent.stack_adapters.StackRepairStrategyRegistry` 按注册顺序选择首个适用策略，并拒绝重复策略名称；Core adapter 默认构造空注册表。当前活动生成路径调用语言 `repair_source()`，将候选重新送入 `validate_candidate()`，证据策略名为 `language-source-repair`。

`stack_file_handler()` 将 Stack Adapter 文件解析结果接入 V1；`validation_plan_for_level()` 和 `coordinator_handler()` 将 install/lint/typecheck/build、test、start/smoke/health 分别约束到 V2、V3、V5；V4 接受技术栈无关的契约处理器；`delivery_gate_handler()` 将既有 Artifact 一致性结果接入 V6。`rank_candidates()` 只把完整通过 V0-V6 的候选作为 winner，并使用稳定 tie-break；`build_repair_feedback()` 将失败候选路由回其原始 `GenerationStrategy`，限制诊断数量和相关上下文字符数。稳定失败分类包括 `validation_failed`、`validation_unsupported`、`task_candidate_budget_exhausted` 和 `strategy_candidate_budget_exhausted`。

传统单文件生成创建 `HeartbeatTracker` 并传递给 Specialist 与 `ReActEngine`。simple ReAct 和 full ReAct 均监控模型活动；流式 content/reasoning chunk 更新活动时间，超过无活动阈值会取消当前调用并返回空结果，由现有内容恢复链路执行有限重试。API SSE 的 5 秒 heartbeat 仅承担客户端连接保活，不参与模型活动判断。

## Workflow Contracts

`WorkflowDefinition` 包含 workflow 名称、入口节点、StateGraph 和 legacy endpoint。当前定义主要承载单节点 legacy workflow。`build_legacy_workflow()` 将旧 Agent handler 转换为 StateDelta，并在 metadata 中保留原始结果。`run_workflow()` 从可序列化 State 启动图运行。

## Retrieval Contracts

统一检索使用 `RetrievalRequest`、`RetrievalChunk` 和 `RetrievalResult`。chunk 实际携带 `source_type`、`source_id`、`content_hash`、`metadata` 和 `retrieved_at`；项目/会话范围通过请求字段和 metadata 过滤，来源信息由来源字段和 metadata 表达。服务支持排序、去重和降级结果，当前尚未接入生产 Agent 主链路。

## Validation Contracts

`app.agent.project_snapshot.ProjectSnapshot` 保存项目基线 revision、文件路径、大小和 SHA-256。`app.agent.change_plan.ChangePlan` 保存基于快照的动态 `FileChange`，支持新增、修改、删除和重命名，并通过 `verify_untouched()` 检查计划外文件变化。`IncrementalFileTransaction.stage()` 在调度前备份 modify 原文件、暂存 delete/rename 源文件并登记 add/rename 新目标；`commit()` 清除事务暂存区，`rollback()` 恢复备份并移除本轮新增目标。

云端验证使用 `source=cloud`、`scope=cloud_syntax`，并根据 `State.metadata.required_validation_scopes` 创建本地验证动作。本地结果适配器只接受 `local_runtime` 或 `local_e2e`，校验 task、session、revision、schema version、scope 和 `source=local`，并将协议字段映射到内部 `scope`、`passed`、`source=vscode` 契约。`passed`、`skipped`、`failed`、`timeout`、`rejected`、`cancelled` 和 `unsupported` 进入状态推导，其中 `skipped` 视为已完成阶段，`waiting_for_confirmation` 保持未完成；当语言能力、验证命令或契约版本不可用时使用 `unsupported`，保留 `reason` 等诊断并停止创建后续本地验证动作。适配器按已完成 scope 更新待执行动作，所有必需 scope 通过或跳过后才产生 `completed` 状态。VS Code 插件本地 E2E、Agent Host 真实 HTTP session 控制闭环和用户模型 Key 流程均已验收，模型驱动的跨工作台续跑仍属于独立场景验收。

`vscode-extension/src/protocol.ts` 提供 VS Code 端的 `PendingAction` 和 `LocalValidationResult` 类型及运行时解析器。插件端使用 `validation_scope`、`source=local` 和参数数组命令；连接层接入云端时需将 Envelope 字段映射到现有本地结果适配器的 `scope` 和 `source` 契约。

`vscode-extension/src/agent-host.ts` 提供通用 `AgentHostEnvelope`、Host Hello、能力声明、策略快照和 `AgentHostSession`。会话握手校验协议版本、工作区、扩展版本、能力清单和待执行动作；策略更新要求 `policy_version` 严格递增，支持的能力包括 `workspace`、`file`、`terminal`、`diagnostics`、`validation` 和 `skill_runtime`。

后端 `POST /api/v1/agent/host/handshake` 使用 access token 认证，接收 `workspace_id`、`extension_version`、`protocol_versions` 和 `capabilities`，返回用户绑定的 `session_id`、协议版本、初始 `policy`、`policy_version`、会话过期时间和待执行动作。`GET /api/v1/agent/host/sessions/{session_id}/actions` 拉取 session 动作，`POST /api/v1/agent/host/sessions/{session_id}/events` 接收 Host 事件并按 `message_id` 幂等，`PUT /api/v1/agent/host/sessions/{session_id}/policy` 以期望版本更新策略。当前握手会话保存于进程内存，StateGraph 动作入队仍需接入持久化任务存储。

`app.api.v1.agent_host.enqueue_state_actions()` 将 StateGraph 的 `pending_actions` 转换为版本化 `tool_action` Envelope，补齐 `session_id`、`task_id`、`revision`、`workspace_id` 和当前 `policy_version`，并按 `action_id` 去重。`run_workflow()` 在图执行完成后自动调用该适配器；已连接 Host 可通过 session actions 队列消费本地动作。session 队列、策略版本和事件确认使用 `AgentHostSessionStore` 原子写入 `data/agent_host_sessions/`，支持进程重启后的读取恢复。

`vscode-extension/src/tool-dispatcher.ts` 提供本地工具分发。文件读取和修改使用工作区授权路径、UTF-8 内容 hash、读取大小上限和 expected hash 冲突保护；诊断通过注入适配器获取；验证和终端动作复用 `ValidationRunner`，并遵守参数数组、`shell=false`、本地执行总开关和验证操作开关。

`vscode-extension/src/webview-bridge.ts` 提供 Webview 与扩展 Host 的消息、请求响应关联、超时和释放处理。`vscode-extension/src/agent-host-runtime.ts` 校验会话与策略版本，将工具动作交给 `ToolDispatcher`，并把非验证结果包装为 `tool_result` 事件或将本地验证结果提交到云端连接层；控制消息可应用单调递增的策略更新并处理审批决定。运行时按 session/message 合并并发动作、允许失败动作重投并限制幂等缓存规模；连接 generation 隔离重连前的在途轮询和结果提交，会话取消、连接替换及插件停用会向活动本地动作传播取消信号。

`vscode-extension/src/agent-workbench.ts` 提供原生 Webview 工作台控制器和安全 HTML。`codingmatrix.openAgentWorkbench` 命令由 `src/extension.ts` 注册，打开单例 Agent 面板并通过 `WebviewBridge` 连接 Host 消息。

工作台控制器订阅并转发已通过协议解析的 Webview Agent Host 消息；内置审批控件可生成 `approval_decision`，供运行时处理挂起的本地动作。

`src/extension.ts` 在存在工作区时创建本地 `AgentHostSession`、`WorkspaceAuthorization`、`ValidationRunner`、`ToolDispatcher` 和 `ApprovalBridge`，并通过 `AgentWorkbenchController` 完成事件回传。

`vscode-extension/src/approval-bridge.ts` 管理本地审批请求和决定。`AgentHostRuntime` 在会话策略关闭自动批准时暂停工具动作，发布 `approval_request`，并在批准后继续执行；拒绝决定返回 `rejected` 状态。

`vscode-extension/src/connection.ts` 提供 Bearer 认证的动作拉取和结果提交客户端，默认路径为 `/api/v1/agent/local-validation/actions` 与 `/api/v1/agent/local-validation/results`。客户端对 401/403 返回认证错误，对 408/429/5xx 执行有限重试，网络中断时将结果写入可注入的 `ResultStore`，新连接实例可刷新持久化队列并在云端确认后删除记录。

`vscode-extension/src/workspace-authorization.ts` 提供工作区授权、撤销、多工作区隔离和路径解析。路径必须相对授权根目录，验证与终端工作目录均由 workspace identity 映射；读取路径、已有写入路径、目录符号链接和悬空叶节点符号链接均通过真实文件系统 canonical path 校验工作区边界。

`vscode-extension/src/validation-runner.ts` 通过注入的进程适配器执行验证动作，固定使用参数数组和 `shell=false`，并提供 `dependency_install` 等操作白名单、超时、取消、退出码和输出上限控制。执行结果统一映射为 `LocalValidationResult`；执行计划使用 `plan_schema_version=1`、`run_id`、`step_id` 和串行依赖关系描述文件传输、hash 校验、依赖安装与验证阶段。

`vscode-extension/src/result-sanitizer.ts` 在结果回传前处理密钥、Bearer token、密码、Cookie、私钥和连接串，并对处理后的结果执行安全复检。`vscode-extension/src/result-store.ts` 通过可注入存储保存待回传结果，按 `event_id` 去重，并在云端确认后移除记录。

`vscode-extension/src/status-view.ts` 提供与 VS Code API 解耦的验证状态视图模型。`ValidationStatusView` 将授权等待、运行、通过、失败、超时、拒绝和取消映射为可展示快照，提供耗时、取消能力、通知文本和带文件位置的诊断摘要；结果兜底匹配同时校验 `session_id`、`task_id`、`revision` 和 `validation_scope`，避免多 scope 动作串写。

`vscode-extension/src/compatibility.ts` 提供启动阶段兼容性校验。云端握手必须声明支持插件当前的 `schema_version`，可选的 `plugin_version.min` 和 `plugin_version.max` 使用严格 `x.y.z` 版本格式；不兼容时返回结构化 `CompatibilityError`，调用方应阻止创建新的本地验证动作并展示升级指引。`package.json` 的 manifest 入口为 `dist/extension.js`，打包脚本为 `vsce package --no-dependencies`。

## 持久化与事件

`CheckpointStore` 提供版本化 JSON checkpoint 的保存和加载能力，`progress_event_to_message()` 提供进度事件到 `MessageEnvelope` 的转换，`replay_session()` 提供带序列缺口恢复动作的回放结果。插件连接层使用 `ResultStore` 支持跨实例断线结果恢复。当前 API、SessionManager 和任务队列尚未自动调用 checkpoint 持久化，现有 SSE 仍保留原始事件出口。
Agent、Workflow 和 PPT 入口已逐步接入统一 checkpoint、Task Event 和 Artifact 持久化，现有 SSE 仍保留原始事件出口。

## Unified Task State

- `GET /api/v1/tasks/{task_id}`：按用户归属查询任务快照。
- `GET /api/v1/tasks/{task_id}/events?after_sequence=0`：从 SQL 事件日志重放任务事件。
- `DELETE /api/v1/tasks/{task_id}`：撤销 Celery 任务并写入取消事件。
- `POST /api/v1/tasks/{task_id}/recover`：恢复失败或取消任务，并为已支持的 Celery 任务重新投递。

任务状态同时写入既有 Redis/进程内任务状态和 SQL `tasks` 表。状态变化发布到 Redis `task_events:{task_id}`，SQL `task_events` 保存断线重放记录。统一实体模型位于 `app.models.unified_state`，服务入口位于 `app.services.unified_state_service`。

后续模块使用 `state_compatibility_mappings` 解析旧模块标识，使用 `state_retention_records` 管理资源归档和清理生命周期。两类记录均以统一资源类型和资源标识建立可追溯关联。

服务入口为 `upsert_compatibility_mapping`、`resolve_compatibility_mapping`、`create_retention_record` 和 `advance_retention_record`。

统一保留服务入口为 `process_retention_records`。`RetentionPolicy` 定义归档和清理时间窗口；处理器会检查活动任务、有效会话和恢复状态，归档时保留统一资源记录，清理外部 artifact 前记录固定幂等键、资源版本、删除意图和执行结果。外部存储通过 `ExternalStorageAdapter` 注入，默认 `LocalFileStorageAdapter` 支持 `file://` URI；失败记录进入 `retryable` 状态。scheduler 每天执行 `unified_state_retention`。

核对服务入口为 `record_difference`、`schedule_difference_retry` 和 `list_open_differences`，记录模型为 `state_reconciliation_records`。

模块级切换服务入口为 `build_reconciliation_report` 和 `ReadCutoverController`。报告要求 session、message、task、event、checkpoint、artifact 六类资源均有记录，并且不存在 `open` 或 `retryable` 差异；控制器按 AICloud、GirlAI、Agent、Workflow 顺序启用 unified read source，任一模块可回滚到 legacy source。

`activate_modules_in_order` 执行四模块灰度切换。`ReadCutoverController.enable(..., rollout_percentage=N)` 使用稳定用户 cohort 将模块按 0 到 100 的比例分批切换；`source_for_user` 返回当前用户的 legacy 或 unified 读源，回滚会将模块灰度比例恢复为 0。

AICloud 适配器入口为 `ensure_session`、`append_legacy_message` 和 `list_session_messages`，旧会话和消息通过 `state_compatibility_mappings` 保留可追溯关系。

GirlAI 适配器入口为 `ensure_session`、`append_conversation_turn`、`delete_messages_for_legacy_ids`、`clear_messages_for_user`、`list_messages_for_user` 和 `save_summary_checkpoint`，角色标识、legacy 消息关联和摘要来源保存在统一状态 metadata 或 checkpoint state 中。

GirlAI 结构化伙伴回合契约位于 `app.schema.girl_companion`。`parse_companion_turn()` 将供应商响应规范化为版本化回合；解析器接受完整 JSON、JSON code fence，以及 `<think>` 或说明文字之后嵌入的首个完整 JSON 对象。无法解析结构化 JSON 时保留安全的助手文本，并返回 `structured_output`、`emotion` 和 `intent` 能力降级标记；文本含内部推理模板标记或结构化字段校验失败时使用通用降级回复。伙伴结构化调用至少分配 512 个输出 token，将温度限制到最高 0.3，使用精确 JSON 系统模板，并采用 60 秒独立超时。独立分类成功后会清除主模型遗留的情绪和意图降级标记；分类请求使用正数 `thinking_budget` 兼容 reasoning 模型。`SessionEvent` 使用会话内单调递增 sequence 和唯一 `turn_id` 保存 processing、completed、degraded 或 failed 回合；内部 `reservation_token` 仅用于 lease owner fencing，响应不会暴露该字段；`state_revision` 对应事件 sequence。

AICloud 与 GirlAI 的旧历史读取回归测试覆盖兼容映射复用、缺失映射创建、用户归属隔离、消息顺序和读取数量限制。

Agent 适配器入口为 `ensure_project_session`、`save_graph_checkpoint` 和 `persist_agent_state`。`generate`、同步 `orchestrate`、增量修改 SSE 和 `orchestrate/stream` 已通过 `run_workflow(..., db=db, user_id=user_id)` 触发统一持久化。Workflow 适配器入口为 `ensure_workflow_task`、`record_workflow_stage` 和 `register_workflow_artifacts`。

PPT WebSocket `GET /ws/ppt/{task_id}?after_sequence=N` 建立连接后按 SQL `task_events.sequence` 重放事件，再发送当前任务状态变化；没有后续事件时返回 `{type: "snapshot_recovery", revision, step, state}`。Celery 任务入口为 `app.tasks.ppt_tasks.generate_ppt(task_id, user_id, request_data)`，其中 `request_data` 必须是 JSON 对象。编排器按 `quality_mode` 选择阶段：标准模式跳过 `vision_qa`，精修模式执行完整视觉复审，并支持从指定阶段恢复。

PPT Celery worker 使用统一 `heartbeat_task` 写入 90 秒 lease，进度更新会触发续租；过期 lease 的扫描和恢复由后续调度器负责。

PPT Celery worker 与旧异步入口共用 `app.services.ppt_generation_persistence`。任务在规划、规则质检和完成阶段写入版本化 Checkpoint；完成后登记主输出文件、预览、布局元数据和质量报告 Artifact。派生 Artifact 关联主输出 Artifact，主输出 metadata 可解析 `outline_version`、`template_version`、`planner_version` 和 `quality_report_version`，文件 Artifact 保存 SHA-256 内容 hash。重复 worker 执行按任务、Artifact 类型和版本幂等更新。

`app.services.worker_recovery_service.recover_expired_tasks(db, now=None, limit=100)` 执行一次过期 lease 扫描，支持 `project_generate`、`code_generate`、`ppt_generate` 和 `ppt_generation`，成功重投递后记录 `task.recovered` 事件。`app.db.scheduler` 的 `worker_lease_recovery` job 每分钟调用一次。

设置 `PPT_USE_CELERY=true` 后，`POST /pptx/generate_task` 通过 `app.services.ppt_dispatch_service.dispatch_ppt_to_celery` 创建统一任务并提交 JSON 参数；默认值保持旧任务执行路径。

Celery PPT worker 的进度写入统一 `tasks` 和 `task_events`，WebSocket 优先重放事件并在缓存缺失时读取 SQL Task 状态。

本地 Celery 运行时使用 Redis 作为 broker/backend。PPT worker 需要监听 `ppt` 队列，并注册 `app.tasks.ppt_tasks.generate_ppt`；worker lease 过期后由 `worker_lease_recovery` scheduler job 触发恢复。

P3 集成测试位于 `tests/integration/test_state_recovery.py`，覆盖 Redis Pub/Sub 消息接收、SQL 事件按序重放、最新 checkpoint 快照恢复、序列缺口的 `snapshot_recovery` 动作和任务归属校验。
