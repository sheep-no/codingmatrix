# app/schema Schema 层 演化深扫文档

> 版本：v0.1 | 扫描日期：2026-08-28 | 状态：已完成（第一百五十二轮，合扫）
> 归属：接口契约层 / 请求响应模型（对应 SERVICES-EVOLUTION.md H 组公共底座，服务 v1/v2 全部路由）
> 路径：app/schema/（13 文件 828 行：aicloud 164 + codeRequest 172 + workflow 106 + nginxConf 88 + task_schema 71 + file_schema 69 + girl_request 45 + manageUser 34 + history 31 + user 25 + ppxRequest 11 + token 8 + guardian 4）
> 索引：[TASKS.md](../TASKS.md)

## 0. 模块定位与状态判定（三态）

| 文件 | 状态 | 判定依据 |
|------|------|---------|
| aicloud.py | **活跃** | api/v1/aicloud.py:24 导入 17 符号（ChatRequest/ChatResponse/ChatStreamRequest/FileRead*/FileWrite*/AuditLogResponse/Session*/Review*/MessageResponse/ModelInfoResponse/ModelsListResponse/CodeExecute*），aicloudRouter main.py:312 挂载 |
| codeRequest.py | **活跃** | 4 消费族：Aicode.py:26（CodeRequest :712）、AiProjectCode.py:23 + ai_agent/helpers.py:20 + ai_agent/generate_endpoints.py:20（GenerateRequest/GenerateResponse/AgentConfig）、utils/agent_core.py:19（ToolDefinition/AgentConfig）；tests/archive 2 文件 |
| workflow.py | **活跃** | api/v1/workflow.py + utils/workflow/ 10 文件（task_decomposer/state_machine/result_aggregator/graph_validator/executor + node_types/ 9 节点）+ tests/unit 7 文件，全库消费面最广的 schema |
| nginxConf.py | **活跃** | api/v2/nginx_api.py:33 显式导入 6 符号（NginxConf/NginxCheck/NginxGenerateRequest/NginxGenerateResponse + Deploy 对），nginxRouter main.py:317 挂载；nginx_ai.py star import 为未接入文件旁路（146 轮：router 零挂载恒 404） |
| task_schema.py | **活跃** | api/v1/task_queue.py（TaskCreateRequest/TaskPriorityEnum/TaskResponse/TaskListResponse）+ AiProjectCode.py:33（TaskResponse/TaskStatusEnum）+ tests/unit/test_task_queue.py；taskQueueRouter main.py:309 挂载 |
| file_schema.py | **活跃（半死）** | 活跃面：FileUploadResponse/FileListResponse 被 file_upload.py 消费（fileUploadRouter main.py:308 挂载）；死面：FileDownloadResponse/FileCreate/FileResponse/validate_page/validate_page_size 五符号零生产消费（SD3） |
| girl_request.py | **活跃（含死符号）** | GirlAi.py:21 导入 4 符号（GirlRequest/GirlResponse/HistoryRecord/HistoryResponse，:408-:607 消费），GirlAiRouter main.py:306 挂载；HistoryQuery 死符号（SD6） |
| manageUser.py | **活跃** | api/v2/user_manage.py star import（UserCreateRequest :115 / ResetPasswordRequest :272），userManageRouter main.py:319 挂载 |
| history.py | **活跃** | api/v1/auth.py:14 star import（HistoryRequest :291 / ConversationHistoryRequest :330 历史列表/详情端点） |
| user.py | **活跃** | api/v1/auth.py:12-13（UserLoginEncrypted 显式 + star；UserLogin/UserRegister 登录 :81/:106 与注册 :234 端点） |
| token.py | **活跃** | api/v1/auth.py:10（Token 登录响应模型） |
| guardian.py | **活跃** | api/v2/guardian_router.py:14（StartGuard :86 start_guard 端点），guardian_router main.py:321 挂载；restart_cmd 直通 shell 执行链（SD7） |
| ppxRequest.py | **未接入（死文件）** | 全库零生产消费，唯一引用 tests/archive/legacy/test_pptx_kolors_refactor.py；PPT 生成实际请求模型是 aiGeneratorPptx.py:83 自带的 PPTGenerationRequest（SD4） |

**层定位澄清**：schema 层是纯 Pydantic 契约（无业务逻辑），其「活性」完全由消费方路由挂载状态决定——13 文件中 12 活跃 + 1 死文件（ppxRequest），无「未接入但保留」的灰色态；v2 全线 9 路由已在 main.py:317-324 挂载（146 轮结论「nginx_ai 未接入」仅指该文件，nginxConf 本体活跃）。

## 1. 模块作用与功能

- 核心职责：v1/v2 全部路由的请求体验证与响应模型声明（Pydantic v2.13.4），含字段约束（长度/正则/枚举/范围）、自定义校验器（codeRequest 5 个 field_validator + nginxConf 3 个 v1 validator）、认证响应结构（Token）与流式事件结构（WorkflowStreamEvent）
- 主要符号：`ChatRequest`/`ChatStreamRequest`/`CodeExecuteRequest`（aicloud.py:14/:24/:143 附近）；`CodeRequest`/`GenerateRequest`/`AgentConfig`/`ALLOWED_MODELS_LIST`（codeRequest.py）；`TaskGraph`/`TaskNode`/`WorkflowRequest`/`WorkflowStreamEvent`（workflow.py:64/:51/:73/:90）；`NginxGenerateRequest`/`NginxDeployRequest`（nginxConf.py:18/:76）；`TaskCreateRequest`/`TaskStatusEnum`/`TaskPriorityEnum`（task_schema.py:34/:9/:27）；`GirlRequest`/`HistoryResponse`（girl_request.py）；`UserCreateRequest`/`ResetPasswordRequest`（manageUser.py:13/:33）；`HistoryRequest`/`ConversationHistoryRequest`（history.py）；`UserLogin`/`UserLoginEncrypted`/`UserRegister`（user.py:5/:11/:22）；`Token`（token.py:4）；`StartGuard`（guardian.py）
- 对外接口：被 app/api/v1（auth/Aicode/GirlAi/aicloud/task_queue/file_upload/workflow）与 app/api/v2（user_manage/nginx_api/guardian_router）10 个路由文件 + utils/agent_core.py + utils/workflow/ 10 文件消费
- 内部子功能划分：AI 对话契约（aicloud/codeRequest）+ 工作流契约（workflow/task_schema）+ 管理面契约（manageUser/nginxConf/guardian）+ 认证契约（user/token/history）+ 业务附加契约（girl_request/file_schema/ppxRequest）

## 2. 依赖与被依赖

- 导入依赖：pydantic（BaseModel/Field/EmailStr/validator/field_validator）、typing、enum、datetime——零内部依赖（纯契约层，不 import app 任何模块）
- 生产使用方：见 §0 判定依据列；10 路由文件全部经 FastAPI 请求体/响应模型消费，agent_core/workflow 子包经符号导入消费
- 测试覆盖：tests/unit/test_task_queue.py（TaskCreateRequest/TaskPriorityEnum/TaskTypeEnum/TaskResponse）、tests/unit/test_workflow 系 7 文件（TaskGraph/TaskNode/TaskType/TaskStatus/WorkflowStatus）、tests/archive/legacy 4 文件（CodeRequest/GenerateRequest/PptRequest/FileCreate）；**管理面契约（manageUser/nginxConf/guardian）与认证契约（user/token/history）零单测**——SD1 密码策略分裂正落在零测试区

## 3. 已探明 Bug（含 bug 代码）

### SD1 [P2] 密码强度策略分裂：管理面 6 位 vs 认证面 8 位，管理员可创建被登录端点锁死的弱密码账号

- **现象**：同一系统两套密码策略并存——认证契约要求 8-72 位（含 bcrypt 72 字节上限意识），管理契约仅要求 6 位且无上限无复杂度；管理员创建/重置的 6 位密码账号，经明文兼容登录端点将被 422 拒绝
- **Bug 代码**：

```python
# app/schema/user.py:8（UserLogin）与 :24（UserRegister）— 认证面 8-72 位
password: str = Field(min_length=8, max_length=72)

# app/schema/manageUser.py:16（UserCreateRequest）与 :34（ResetPasswordRequest）— 管理面仅 6 位
password: str = Field(..., min_length=6)          # 无 max_length、无复杂度
new_password: str = Field(..., min_length=6)      # 同上
```

- **根因**：manageUser.py 与 user.py 由不同时期/不同人编写，密码策略未抽公共常量；管理面建号（user_manage.py:115 UserCreateRequest）与重置密码（:272 ResetPasswordRequest）走 6 位标准，用户自助注册（auth.py:234 UserRegister）走 8 位标准
- **影响**：① 管理员可创建 6 位弱密码账号（暴力破解面扩大）；② 该类账号若走明文兼容端点（UserLogin min_length=8）登录恒 422 锁死（加密主链路 UserLoginEncrypted 无长度校验，取决于解密后 service 层是否复检——未复检则 6 位账号可登录，策略分裂坐实）；③ 全系统无密码复杂度要求
- **触发条件**：管理员创建/重置密码长度 6-7 位 + 用户经明文兼容端点登录
- **验证方式**：POST /api/v2/manage/users 用 6 位密码建号成功 → 用同密码走明文登录端点观察 422

### SD2 [P3] Pydantic v1/v2 校验器风格混用：4 文件仍用废弃 API（运行时 DeprecationWarning，v3 将移除）

- **现象**：pydantic==2.13.4（configs/requirements.txt:83）下，nginxConf 的 `@validator` 与 file_schema/task_schema 的 `class Config` 均为 v1 废弃用法，每次模型定义/实例化触发 PydanticDeprecatedSince20 告警；同层 history/codeRequest 已用 v2 风格
- **Bug 代码**：

```python
# app/schema/nginxConf.py:49/:55/:62 — v1 废弃校验器 API
@validator('server_name')
@validator('config_type')
@validator('platform')

# app/schema/file_schema.py:18/:43/:56 与 task_schema.py:62 — v1 废弃配置风格
class Config:
    from_attributes = True   # v2 应为 model_config = ConfigDict(from_attributes=True)
```

- **根因**：分批迁移未收尾——codeRequest.py:86-152 field_validator×5 + :172 model_config、history.py:17 field_validator(mode='before') 已是 v2 风格，nginxConf/file_schema/task_schema 三文件漏迁
- **影响**：告警噪音掩盖真实问题；pydantic v3 升级时 @validator 直接报错（nginxConf 三个校验器全部失效，config_type/platform 失去白名单校验）；同层两种风格增加维护认知负担
- **触发条件**：每次应用启动定义模型时
- **验证方式**：`python -W error::DeprecationWarning -c "import app.schema.nginxConf"` 复现告警

### SD3 [P3] file_schema.py 死代码块（死代码家族第 39 处）：五符号零生产消费 + validator 导入未使用

- **现象**：file_schema.py 69 行中约 45 行为零消费代码——FileDownloadResponse(:30)/FileCreate(:37)/FileResponse(:47)/validate_page(:61)/validate_page_size(:66) 全库零生产引用，顶部 `from pydantic import validator`（:4）导入后从未使用
- **根因**：文件上传功能收敛后遗留——file_upload.py 仅消费 FileUploadResponse/FileListResponse 两符号；分页校验实际由 utils/pagination.py:50 独立实现（与 validate_page 同名不同实现，第三份分页逻辑双轨候选）；FileCreate 仅存于 tests/archive/legacy/test_all_features.py
- **影响**：死代码误导后续开发者以为存在文件创建/下载契约；pydantic v3 下未使用的 validator 导入将直接 ImportError
- **触发条件**：静态（永久）
- **验证方式**：`rg "FileCreate|FileDownloadResponse|validate_page" app/ --glob '!app/schema/file_schema.py'` 零命中

### SD4 [P3] ppxRequest.py 整文件未接入（死文件家族第 3 处）：PptRequest 被 aiGeneratorPptx 自带模型架空

- **现象**：PptRequest（ppxRequest.py:5-11）全库零生产消费——PPT 生成链实际请求模型是 aiGeneratorPptx.py:83 PPTGenerationRequest 与 :105 PPTModifyRequest（端点内联定义），本文件唯一引用在 tests/archive/legacy/test_pptx_kolors_refactor.py
- **根因**：PPT 功能重构时（「重构版」docstring 自证）在端点文件内联定义了新契约，旧 schema 未随之删除；文件名 "ppxRequest" 亦为 "pptx" 笔误风格
- **影响**：契约双轨——外部开发者读 app/schema/ 会误认 PptRequest 是 PPT 生成入口契约；死文件持续产生维护噪音
- **触发条件**：静态（永久）
- **验证方式**：`rg "PptRequest" app/ --glob '!app/schema/ppxRequest.py'` 仅命中 tests/archive

### SD5 [P3] 任务状态三枚举并存（双轨家族第 19 处）：RETRYING 值无 DB 对应，语义漂移

- **现象**：同一「任务状态」概念有三个枚举实现——models/task.py:11 TaskStatus（5 值：pending/running/success/failed/cancelled，149 轮 MD7 判其零消费）、task_schema.py:9 TaskStatusEnum（6 值：多 RETRYING，AiProjectCode.py:33 唯一消费点）、workflow.py:25 TaskStatus（6 值：pending/running/waiting_approval/completed/failed/skipped，工作流域自用）
- **Bug 代码**：

```python
# app/schema/task_schema.py:9-16 — 含 RETRYING，但 DB 层枚举（models/task.py:11-17）无此值
class TaskStatusEnum(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RETRYING = "retrying"     # models/task.py TaskStatus 无对应 → 任务表永远存不出此态
```

- **根因**：task_schema（API 队列域）、workflow（临时工作流域）、models/task（DB 域）各自定义状态集，未抽公共枚举；TaskPriorityEnum（high/medium/low 字符串）与 TaskResponse.priority（int=5 默认）依赖 tasks/base.py:158 parse_priority 做 str→int 映射（high=8/medium=5），优先级语义同样双轨但功能正常
- **影响**：RETRYING 是「契约承诺了但存储层不存在」的幻影状态——前端据 TaskStatusEnum 渲染重试中态永远等不到；三枚举演化时极易只改其一造成契约-存储漂移
- **触发条件**：静态（RETRYING 永不可达）+ 演化期（枚举单边修改）
- **验证方式**：`rg "RETRYING" app/` 仅 schema 定义处命中；DB 中 status 列值域查询无 retrying

### SD6 [P3] girl_request.HistoryQuery 死符号（死代码家族第 40 处）

- **现象**：HistoryQuery（girl_request.py:23-27）零消费——GirlAi.py:21 导入清单仅含 GirlRequest/GirlResponse/HistoryRecord/HistoryResponse 四符号，历史查询参数实际在端点内联声明
- **根因**：GirlAi 历史端点改为 query 参数直传后遗留
- **影响**：死契约噪音，与 SD3/SD4 同族（schema 层死代码集中地）
- **触发条件**：静态（永久）
- **验证方式**：`rg "HistoryQuery" app/` 仅定义处命中

### SD7 [P3] StartGuard.restart_cmd 裸字符串无校验，持久化后直通 shell 执行链（V2U1 提权链终端）

- **现象**：guardian.py:5 `restart_cmd:str` 裸字段无任何格式校验/白名单，经 start_guard 端点写入守护配置并持久化，服务失活时由 process_guard 以 shell 执行
- **Bug 代码**：

```python
# app/schema/guardian.py:5 — 任意命令字符串，无校验
restart_cmd:str

# app/api/v2/guardian_router.py:95-101 — 持久化 + auto_start
cfg.update({"restart_cmd": body.restart_cmd, "auto_start": True, "learned": True})
guardian.config_manager.save_configs()

# app/utils/process_guard.py:121 — shell 执行
proc = await asyncio.create_subprocess_shell(restart_cmd, cwd=cwd, ...)
```

- **根因**：守护链（117 轮 process_guard 详档已记执行侧）设计上信任配置内容；schema 层未做命令格式约束（如仅允许 systemctl/supervisor 类受控模板）；门禁 require_superadmin（guardian_router.py:86）缓解但 146 轮 V2U1 已证 admin 可提权 superadmin——**admin → V2U1 提权 → start_guard 注册任意命令 → 端口失活触发 shell 执行**构成完整 RCE 链
- **影响**：叠加 V2U1 后为持久化 RCE 面（配置落盘重启后仍生效）；即使无提权链，superadmin 误输入也直接进 shell
- **触发条件**：恶意/失误的 restart_cmd 注册 + 被守护服务端口失活
- **验证方式**：superadmin token POST /api/v2/guard/start 注册 `restart_cmd="touch /tmp/pwned"`，停掉对应端口进程观察命令执行
- **备注**：执行侧（process_guard）与提权侧（V2U1）分别已在 117/146 轮建档，本条为 schema 层输入端归档

**家族归并（引用既有编号，不重复计）**：① api_key_token 请求体传凭据 3 处（aicloud.py:20/:34、codeRequest.py:34，147 轮 v1 余量合扫家族）；② workflow.py:97 WorkflowStreamEvent timestamp `default_factory=datetime.now` 本地 naive——MD3/DB11 时间语义三态家族 schema 层实例；③ codeRequest.py ALLOWED_MODELS_LIST 硬编码 8 模型名——SPFG17/OF4 硬编码家族；④ nginxConf.py:28-29/:47/:79 ssl_cert/ssl_key/nginx_path 自由路径字段——V2N2 路径穿越家族 schema 层输入端。

## 4. 潜在问题与未知点

- UserResponse.created_at（manageUser.py:10）声明 str 而 DB 模型输出 datetime——序列化路径依赖 FastAPI 隐式转换，契约与实际类型漂移（未实测响应体）
- ChatRequest/ChatStreamRequest 双模型并存（aicloud.py:14/:24）疑似流式/非流式字段复制粘贴，字段集差异未逐一比对
- task_schema.TaskTypeEnum 4 值（project_generate/code_generate/ppt_generate/file_process）与 celery 任务实际类型集的一致性未核对（tasks/ 层已扫但未对照）
- GirlRequest.model 字段无枚举校验（对照 codeRequest.model 有 ALLOWED_MODELS_LIST validator）——GirlAi 链模型名透传是否被下游兜底未验证

## 5. 修改建议（改什么 → 达成什么目的）

| # | 优先级 | 修改动作 | 达成目的 | 涉及位置 | 对应 Backlog |
|---|--------|---------|---------|---------|-------------|
| 1 | P2 | 统一密码策略为 8-72 位 + 复杂度校验，抽公共常量/可复用 Field | 消除管理面弱密码入口与明文端点锁死矛盾 | manageUser.py:16/:34、user.py:8/:24 | #1188 |
| 2 | P3 | nginxConf @validator×3 → field_validator；file_schema/task_schema class Config → model_config | 消除废弃 API 告警，解锁 pydantic v3 升级 | nginxConf.py:49/:55/:62、file_schema.py:18/:43/:56、task_schema.py:62 | #1189 |
| 3 | P3 | 删除 FileDownloadResponse/FileCreate/FileResponse/validate_page/validate_page_size + validator 导入 | 死代码家族第 39 处清零，消除分页双轨误导 | file_schema.py:4/:30/:37/:47/:61/:66 | #1190 |
| 4 | P3 | 删除 ppxRequest.py 整文件（含 archive 测试引用同步清理） | 死文件家族第 3 处清零，消除 PPT 契约双轨 | ppxRequest.py 全文件 | #1191 |
| 5 | P3 | 任务状态枚举收敛：TaskStatusEnum 去掉 RETRYING 或 DB 层补值；长期抽公共枚举包 | 消除幻影状态与三枚举漂移 | task_schema.py:16、models/task.py:11 | #1192 |
| 6 | P3 | 删除 HistoryQuery | 死代码家族第 40 处清零 | girl_request.py:23-27 | #1193 |
| 7 | P3 | restart_cmd 加格式校验/受控模板白名单（或改结构化 restart 指令枚举） | 收敛 V2U1 提权链终端的持久化 RCE 面 | guardian.py:5 | #1194 |

## 6. 演化方向关联

- 契约层是 §5.6 支柱 1「协议统一」的末端落点：密码策略（SD1）、任务状态（SD5）、分页（SD3 vs pagination.py）三类语义分裂的根治都在「公共契约包」——建议演化出 app/schema/_shared.py（密码 Field 工厂、任务状态枚举、分页参数基类），路由层只做组合
- 死代码集中度显示 schema 层是「功能收敛后的遗留垃圾场」（3/13 文件含死符号或整文件死）——v1 收尾清点时应把 schema 层死符号清理与路由收敛合并执行
- api_key_token 请求体传凭据家族的长期方向是统一到 Authorization header + Redis 短时票据（与 147 轮结论一致），schema 层字段删除是该演化的最后一步
- workflow.py 的 TaskGraph/TaskNode 是工作流域「临时状态 vs DB 持久化」双轨（与 shared_context vs dependency_graph 同构）的契约侧体现，随工作流域收敛一并处理
