# v1 API 收尾清点：剩余 10 文件合扫（第 153 轮 / v1.154）

- 轮次：153（内部编号 v1.154）
- 扫描对象：`app/api/v1/` 收官批次，auth.py(550) / apikey.py(585) / task_queue.py(352) / health.py(196) / Aicode.py(938) / GirlAi.py(855) / kolors_api.py(875) / kolors_history.py(152) / file_upload.py(467) / skills.py(241) / providers.py(238)，合计约 5449 行
- 此前已覆盖的 v1 文件（不重扫）：aiGeneratorPptx/workflow/aicloud_knowledge/vision_api/model_manager（147 轮）、github.py + aicloud.py（140 轮）、ai_agent/（142 轮）、AiProjectCode.py（143 轮）
- 至此 `app/api/v1/` 全目录扫描完成

## 三态判定

| 文件 | 判定 | 依据 |
|------|------|------|
| auth.py | 活跃 | 登录/注册/profile 全站入口 |
| apikey.py | 活跃 | provider key CRUD + batch_import |
| task_queue.py | 活跃 | Celery 任务下发 + WS 推送 |
| health.py | 活跃 | 健康检查/metrics |
| Aicode.py | 活跃 | /code 代码生成 SSE |
| GirlAi.py | 活跃 | 女友角色对话 |
| kolors_api.py | 活跃 | Kolors 文生图/图生图/修复 |
| kolors_history.py | 活跃 | 绘图历史 CRUD |
| file_upload.py | 活跃 | 单文件 + 分片上传链 |
| skills.py | 活跃 | 自定义 skill 全生命周期（零认证，见 SKY1） |
| providers.py | 活跃 | 动态供应商管理（aicloud 配套） |

11 文件全部活跃，无未接入/废弃文件。`app/api/v1/` 至此无遗留盲区。

## P1 发现

### AUT1 [P1] 跨用户响应缓存泄露（auth.py:444-484）（已修复）
- `@cache_response(ttl=...)` 装饰三个端点：profile（:444-448，ttl=300）、history（:288-289，ttl=60）、conversations（:478-484，ttl=120）
- 缓存 key 由 `cache_decorator.py:51 _generate_cache_key` 生成，kwargs 排除表为 `"request","db","token","current_user","user_id","background_tasks"`——**user 身份不入 key**
- 三端点经 FastAPI `**values` 全 kwargs 传入，key 恒定 → 全站共享单条缓存
- 影响：用户 A 请求 profile 后，用户 B 在 ttl 窗口内拿到 A 的 email/档案；history/conversations 同理（跨用户会话列表泄露）
- 这是全库第 17 个 P1；修复方向：缓存 key 强制并入 token.sub，或对三端点摘除装饰器
- **已修复**：`cache_decorator.py` 新增 `_extract_user_identity`，从 `token`/`current_user`/`user_id` 提取主体并拼进缓存键（`_generate_cache_key` :85-87）；`_serialize_cache_param` 同时补齐 dict/list/请求体序列化。回归测试 `tests/unit/test_cache_response_user_isolation.py`
- Backlog：#1195

## P2 发现（7 项）

### APY1 [P2] batch_import 恒败假功能（apikey.py:438-510）（已修复）
- 每条调用 `store_key(encrypted_key=key_data['encrypted_key'])`，而 `store_key` 签名为 `(user_id, provider, api_key, ttl, remark)`（apikey_manager.py:155-162），无 `encrypted_key` 参数且 `api_key` 必填
- 恒 TypeError → 每条记 failed → 批量导入 100% 失败
- **已修复**：现改为先 `key_manager.decrypt` 得到明文，再 `store_key(user_id=..., provider=..., api_key=..., ttl=..., remark=...)`，签名一致
- Backlog：#1196

### APY2 [P2] provider 同步跨用户 Key 覆盖（apikey.py:50-88）（已修复）
- `_sync_provider_models` 用全局单例 CustomProviderManager，按 `user_{provider}` 命名（无 user 维度）
- :71 `existing.api_key = api_key` —— 后提交者覆盖先提交者的 Key（同 provider 名），跨用户盗用/覆盖面
- 与 PRV1 同族：custom provider 生态整体无用户隔离
- **已修复**：条目改按 `user_<user_id>_<provider>` 命名，`_sync_provider_models` 接收 `user_id`；启动恢复 `_restore_user_providers` 由「按 provider 去重」改为按 `(user_id, provider)` 逐用户恢复，不再折叠多用户。回归测试 `tests/unit/test_apikey_provider_isolation.py`
- Backlog：#1197

### TQ2 [P2] task_id 用内存地址 id(body)（task_queue.py:67）（已修复）
- `task_id = f"task_{user_id}_{id(body)}"` —— 对象回收后地址复用 → task_id 碰撞 → Celery AsyncResult 状态覆盖 + DB task_id 混淆
- **已修复**：现用 `task_id=str(uuid.uuid4())` 生成，不再依赖对象地址
- Backlog：#1198

### TQ3 [P2] WebSocket 零认证（task_queue.py:338-353）（已修复）
- `/tasks/ws/{user_id}`：user_id 路径参数直连 ws_manager.connect，无 token 校验
- 任意连接者可订阅任意用户任务推送（int 可枚举）
- **已修复**：握手读取 `?token=`，经 `verify_token_ws` 校验，并要求 token 主体与路径 `user_id` 一致，否则 `close(1008)`；与 `/ws/ppt/{task_id}`、`/Controller/sys-status` 同模式。回归测试 `tests/unit/test_task_ws_auth.py`
- Backlog：#1199

### GIR1 [P2] fire-and-forget 复用请求级 session（GirlAi.py:533-535）（已修复）
- `asyncio.create_task(_extract_user_preferences(user_id, body.prompt, ai_content, db))` 把请求级 AsyncSession 传入后台任务
- 响应返回后 get_db teardown 关闭 session → 任务内 execute 恒败（:316 except 吞掉）→ 偏好提取静默恒败；任务句柄未保存可被 GC
- **已修复**：`_extract_user_preferences` 不再接收 `db`，内部 `async with async_session() as db` 自建会话，调用点同步去掉 `db` 实参。残留次要项：`create_task` 句柄仍未保存引用
- Backlog：#1200

### SKY1 [P2] skills 全端点零认证（skills.py 全文件）（已修复）
- upload/list/get/update/delete/upload-file/reload 全部无 verify_token，author 硬编码 "api_user"（:71 TODO 自认）
- 自定义 skill 为全局共享库：任何人可改写 prompt skill，直接影响 kolors 自定义风格注入（kolors_api.py:228-267 `_load_custom_image_styles` 从同一 registry 读 Markdown）——未认证用户可改写全站生成行为
- **已修复**：upload/list/get/update/delete/upload-file 均加 `Depends(verify_token)`，author 由硬编码 `"api_user"` 改为 `token.sub`，并传入 `owner_user_id` 做归属过滤；`migrate-legacy` 另有管理员校验。`/categories` 为静态分类表保持公开；`/reload` 见 SKY2
- Backlog：#1201

### PRV1 [P2] 动态供应商全局共享无归属（providers.py 全文件）（已修复）
- 归属过滤已落地：`DynamicProvider.owner_id`（`dynamic_provider.py:44`）与 manager 的 `get/list/delete/toggle` 的 owner 过滤（:67-102）均存在；`providers.py` 全部端点现以 `owner_id = str(token.get("sub", "default_user"))` 传参，list/get/delete/toggle/sync/test 只能作用于本人 provider，add 仍要求 admin。原「DynamicProvider 无 user 字段」描述已与实现不符
- 残留（未改，待确认设计意图）：模型路由 `get_by_model`（`dynamic_provider.py:71`）仍无 owner 过滤，`llm_caller.py:614` / `provider_router.py:115` / `dynamic_model_router.py:991` 会命中任一启用 provider 的 api_key。因 add 需 admin，实际形态是「普通用户按模型名消费管理员配置的 provider Key」；若动态供应商本意即系统级共享则属预期，若为 per-user 仍需按用户收口
- Backlog：#1202

## P3 发现（31 项）

### auth.py（4 项）
- **AUT2 [P3] 已核实（非缺陷）**：:126 明文登录 email 全量进日志，加密模式 :115 打码 `email[:3]***`；生产入口 `main.py:100` 调用 `setup_logging()`，全局 `SensitiveDataFilter`（`app/core/logging_config.py:18-75`）的 `email` 规则会命中完整邮箱并替换为 `***EMAIL_REDACTED***`，且已挂载到 console/file_app/file_error 三个 handler（:117-149）。明文分支的邮箱落盘前即被脱敏，属过滤器兜底的日志 PII 纵深防御，无需改动
- **AUT3 [P3]** 无 /logout 端点，refresh token（7 天 JWT）无吊销机制
- **AUT4 [P3] 已修复**：`register` 中 `check_email_exists` 与 `db.flush()` 之间存在 TOCTOU，并发注册同一邮箱时 `User.email` 唯一约束触发 `IntegrityError` 逃逸为 500。修复：flush 包 try/except IntegrityError → rollback 并返回与预检一致的 400「邮箱已存在」。回归测试 `tests/unit/test_auth_register_and_error_leak.py`
- **AUT5 [P3] 已修复**：实际泄露点在 `get_conversations` 异常分支 `detail=str(e)`（原文档 :322-325/:354-357 的 history/conversation 分支现已返回通用文案）。修复：改返回「查询会话列表失败」，内部错误仅进日志。回归测试 `tests/unit/test_auth_register_and_error_leak.py`

### apikey.py（2 项）
- **APY3 [P3] 已修复（部分）**：`batch_import` 补齐与单条提交一致的 `_sync_provider_models` 后台同步（仅 OpenAI 兼容供应商，且同一批次内同一供应商去重只同步一次），此前批量导入的 Key 不会被同步模型列表，缺少 context_length 等元数据。**TTL 双语义一项经核实不成立**：batch 将原始 `ttl` 交给 `store_key` → `resolve_ttl`，与单条走同一条解析链，预设字符串与自定义秒数（int/数字字符串）均被接受，见 `test_batch_import_custom_ttl_still_accepted`。回归测试 `tests/unit/test_apikey_batch_import_sync.py`（2 项）
- **APY4 [P3] 已修复（部分）**：`UpdateContextLengthsRequest.context_lengths` 增 `field_validator` —— 条目 ≤200、模型名为非空 str 且 ≤200 字符、值必须为 int（先排除 bool，避免 `true` 被当作 1）且落在 1-10,000,000；`UpdateFallbackPreferenceRequest.custom_fallback_chain` 增校验 —— 元素 ≤20、每个为非空 str 且 ≤200 字符。**刻意不引入模型名白名单**：自定义供应商允许任意模型名，白名单会误伤合法用法，故只做格式/规模约束。消费方 `get_context_length` 本就有 `val > 0` 兜底与 try/except，本次是写入侧收敛。回归测试 `tests/unit/test_apikey_request_validation.py`

### task_queue.py（3 项）
- **TQ4 [P3] 已修复（核实）**：`TASK_NAMES`（`app/api/v1/task_queue.py`）已覆盖 `TaskTypeEnum` 全部 4 值（project_generate/code_generate/modify_with_test/ppt_generate），create/retry/recover 共用同一映射源；未知类型在 create 中且仅在其中返回 400。`test_task_type_contract_matches_implemented_tasks` 与 `test_build_task_kwargs_covers_every_supported_type` 锁定该契约，docstring 与实现一致。
- **TQ5 [P3] 已修复**：Celery ID 复用部分已在 PR #88 修复（retry/recover 均以 `result.id` 覆盖 `celery_task_id`）。本次修复幽灵任务：原实现先置 `status="pending"` 再判断 `celery_task_name`，无映射时状态已改却无派发。现改为在改状态/`transition_task`/写事件之前先校验映射，缺失则返回 400，状态保持不变。回归测试 `tests/unit/test_task_dispatch_contract.py` 新增 2 项（retry/recover 各一）
- **TQ6 [P3] 已修复**：`_merge_task_runtime_state` 原直接 `celery_state.lower()` 透传，Celery 的 `FAILURE`/`RETRY`/`REVOKED`/`STARTED` 会变成 `failure`/`retry`/`revoked`/`started`，超出 `TaskStatusEnum` 声明词表（前端 `retry`/`revoked` 落到默认 `queued`，任务失败/被撤销时状态显示错误）。新增 `_CELERY_STATE_TO_STATUS` 归一化：pending/received→pending、started→running、retry→retrying、success→success、failure→failed、revoked→cancelled；未识别的 Celery 状态保留 DB 口径，持久化终态（success/failed/cancelled）优先不变。另：原条目「cancel 白名单含 retrying，DB 层无此值」经核实不成立——`TaskStatusEnum.RETRYING = "retrying"` 存在且 `celery_app.py:115` 会写入该值，cancel 白名单正确。回归测试 `tests/unit/test_task_dispatch_contract.py` 新增 10 项（7 项状态映射参数化 + 词表约束 + 未知状态回退 + 终态优先）

### Aicode.py（6 项）
- **AIC1 [P3] 已修复**：`_build_context`（`Aicode.py:809-818`）现按 `search_mode`/`enable_search` 先算 `effective_mode`——`enable_search=True` → `"on"` 直接 `should_search=True`，`False` → `"off"` 跳过，仅 `None` 才落回 `ai_decide_search` 自动判断。三态语义已区分，原「True 与 None 行为相同」不成立
- **AIC2 [P3] 部分已修复**：`CodeRequest` 已补 `resume_id: Optional[str]` 字段，`/code` 流式分支改用 `resume_from=body.resume_id`（原 `getattr(body, 'resume_id', None)` 恒 None）。残留：客户端断开分支不可达、`/code/resume` 恢复 conversation_id=None 会话断裂
- **AIC3 [P3] 已修复**：新增 `extract_response_text(result)`，用安全取值替代 `result["choices"][0]["message"]["content"]` 裸索引，结构异常（缺 choices/空 choices/缺 message/content 非 str）统一抛 `RuntimeError`，被调用方 `(…RuntimeError…)` 元组捕获为 500 友好提示。回归测试 `tests/unit/test_aicode_response_hardening.py`
- **AIC4 [P3] 已核实（非缺陷）**：`_build_context`（`Aicode.py:783-786`）实际调用 `get_or_parse_file` → `parse_document`（`app/utils/aicloud/knowledge_processor.py:93`），txt/md/py/js/ts/json/yaml/yml/csv/log/pdf/docx/doc 均解析正文并拼入 `[参考文件：name]\n{parsed_content}`；解析失败分支返回「附件处理失败」文案而非静默占位。原条目行号已漂移，描述与当前实现不符
- **AIC5 [P3] 已修复**：`ai_decide_search`（`Aicode.py:216-245`）现调用 `DEFAULT_FAST_MODEL` 走 `_SEARCH_DECISION_PROMPT` + `parse_search_decision`，仅对空串/`_GREETINGS` 短路返回 False，解析失败或调用异常时默认检索 True；不再是硬编码关键词表。`select_model_for_prompt`（:475）仍为启发式规则表，4 个候选模型均在 `ALLOWED_MODELS_LIST` 白名单内，属合法实现
- **AIC6 [P3] 部分已修复**：恢复缓存改由 `_restore_partial_prefix(resume_from, user_id)` 处理，校验缓存 `user_id` 与当前用户一致，不一致则忽略，避免他人 resume_id 注入其部分响应。残留：`_partial_response_cache` 模块级字典多 worker 不共享（RLM3 家族）
- 已排除项：verify_file_access 有 File.user_id == user_id 过滤（:402），跨用户文件访问嫌疑解除

### GirlAi.py（3 项）
- **GIR2 [P3] 已核实（已修复）**：`_extract_llm_response`（`app/api/v1/GirlAi.py:317`）已用 try/except 捕获 `KeyError/IndexError/TypeError` 并抛 `RuntimeError("AI 服务返回了无效响应")`，空/非字符串内容抛空响应错误，`usage` 用 `response.get("usage") or {}` 取值后再 `int(... or 0)`，不存在裸索引。其余 `(raw_response.get("usage") or {})` 取值点同样安全。无需改动
- **GIR3 [P3] 已修复**：`create_custom_character` 原 `int(float(body.get("temperature", 0.8)) * 100)`、`int(body.get("max_tokens", 180))` 对非数字输入抛 ValueError/TypeError → 500；model 无白名单。修复：temperature/max_tokens 解析失败或越界（0.0-2.0 / 50-1000）返回 400，model 校验必须命中 `MODEL_REGISTRY` 的 `model_key`。前端创建角色不传这三个字段，默认值不受影响。回归测试 `tests/unit/test_girl_custom_character_validation.py`
- **GIR4 [P3] 已修复**：原 `ilike(f"%{q}%")` 未转义通配符，输入 `%`/`_` 会匹配全部记录；`total=len(records)` 实为当前页条数。修复：新增 `_escape_like` 转义 `\`/`%`/`_` 并 `ilike(..., escape="\\")`；`total` 改用独立 `select(func.count())` 统计匹配总数。回归测试 `tests/unit/test_girl_history_search.py`
- 已排除项：girl_request.py 有 character_id/temperature/max_tokens 字段，getattr 兜底对齐无害；:215-229 _clean_response 正则安全；:346-353 头像端点静态 SVG 无害

### kolors_api.py（5 项）
- **KOL1 [P3] 已修复**：`File.file_path.contains(image_path)`（img2img/inpaint 归属校验，含 mask 与 History 兜底查询）中 image_path 用户可控，`%`/`_` 会被当作 LIKE 通配符放宽匹配。新增 `_literal_contains(column, value)`（`contains(value, autoescape=True)`）替换全部 7 处用户输入匹配点。注意：下游 `image_to_image` 用的是原始用户路径而非命中的 DB 行路径，因此通配符"放宽匹配"无法直接读到不存在字面路径的文件，实际可利用性有限，本次按正确语义收敛。回归测试 `tests/unit/test_kolors_like_escaping.py`
- **KOL2 [P3] 已修复（部分）**：通配符失配部分同 KOL1 —— `get_cached_image` 的 `metadata_json.contains(cache_key)`、`contains(fingerprint)` 及 `get_generated_resource` 的 `contains(filename)` 已改用 `_literal_contains`。残留：`metadata_json LIKE` 仍是全表扫（需改 schema/索引，未在本次范围）。回归测试 `tests/unit/test_kolors_like_escaping.py`
- **KOL3 [P3] 已修复**：内联 `TextToImageRequest`/`ImageToImageRequest` 参数补 ge/le —— `num_images` 1-4、`num_inferences`/`steps` 1-100、`width`/`height` 256-1280、`guidance_scale`/`cfg_scale` 1-20、`strength`/`denoising_strength` 0-1（含别名字段）。文生图下游 `text_to_image` 原本已有 clamp，图生图 `image_to_image` 无 clamp 故这次是真实收敛；multipart 路径同样构造这两个模型，故一并被约束。前端取值（512/768/1024、steps 25、cfg 7.5、denoising 0.7）均在范围内。回归测试 `tests/unit/test_kolors_request_bounds.py`
- **KOL4 [P3] 已修复（部分）**：`cache_image_to_history` 原自行 `select(func.max(conversation_id)) + 1` 且无锁，与并发的 `save_history_to_db` 新会话写入会读到同一 max 而撞号（DB6 家族复现）。改为直接复用 `app.db.add_history.save_history_to_db`，共享其按 user_id 粒度的进程内锁与 PG advisory lock，并顺带获得历史缓存失效。标题由 `图像生成：prompt[:50]` 改为 helper 统一的 `prompt[:100]`。残留：图像缓存仍写入业务对话表 `history`，`conversation_id` 为 `nullable=False`，缓存记录会作为会话出现在 `/conversations`；彻底分离需新增独立缓存表或改列可空，属 schema 变更，未在本次范围。回归测试 `tests/unit/test_kolors_image_cache_history.py`（4 项）
- **KOL5 [P3] 已修复**：核实后属死代码——模块级 `STYLE_PROMPTS = get_style_prompts()` 快照在整个仓库无任何读取方，所有实际使用点（文生图 :404、图生图 :617、`/styles` :986）都已调用动态的 `get_style_prompts()`，故自定义 skill 风格本就无需重启。已删除该无引用的陈旧副本，只保留单一动态读取路径。回归测试 `tests/unit/test_kolors_style_prompts.py`（2 项：动态读取反映自定义风格、不再存在模块级快照）

### kolors_history.py（1 项）
- **KHS1 [P3] 已核实（非缺陷）**：`get_image_history` 现用 `select(func.count()).where(user_id)` 独立计数、分页用 offset/limit，不存在 `len(all())`；`ImageGenerationHistory.user_id` 为 `String(100)`（写入侧 `save_image_generation_history` 亦为 `str(user_id)`），故 `token.get("sub")` 直接比较语义正确，无需 `int()`。条目描述与当前代码不符，无需改动

### file_upload.py（5 项）
- **FL1 [P3] 已修复**：分片链 file_id 无归属校验——upload_chunk/merge_chunks 仅凭 uuid file_id 操作，B 知 file_id 可把 A 的分片合并记到自己名下。修复：新增 `_scoped_chunk_dir(user_id, file_id)` 将分片目录改为 `CHUNKS_DIR/<user_id>/<file_id>`（同时拒绝空值/`..`/`/`/`\` 穿越），init/upload/merge 三端点统一走该函数；`ChunkMetadata` 增可选 `base_dir` 参数。新增 `tests/unit/test_bugfixes.py::TestChunkUserIsolation`（3 项，覆盖用户隔离、穿越拒绝、元数据落盘路径）。
- **FL2 [P3] 已修复**：安全双轨收敛——分片 merge 路径补齐与单文件链对齐的三道校验：①`filename` 扩展名必须命中 `ALLOWED_EXTENSIONS`（否则 400）；②声明 `file_size` 须 `0 < size <= MAX_FILE_SIZE`（否则 413），合并后实际大小与声明不一致即 400 并删除落盘文件；③合并结果调用 `validate_file_path` 做 MIME/魔数/SVG/压缩包深度校验，失败删除文件并返回 400（原实现直接 500 或放行）。原「filename 未净化直接拼路径」一项已在上游 `Path(filename).name` 取 basename 收敛，非本次引入。已验证 uploads 无静态挂载（main.py:341-343 仅 /static），download 端点 attachment 头兜底。回归测试 `tests/unit/test_bugfixes.py::TestChunkMergeValidation`（4 项）
- **FL3 [P3] 已修复**：三处磁盘耗尽面收口。①`upload_chunk` 原 `chunk.read()` 无上限，改为 `read(CHUNK_SIZE + 1)` 并以 `len > CHUNK_SIZE` 判超限返回 413，超限分片不落盘；②`chunk_index` 原任意 int，现要求 `0 <= index < total_chunks`，`total_chunks` 要求 `1..MAX_TOTAL_CHUNKS`（由 `MAX_FILE_SIZE/CHUNK_SIZE` 推导，上限 20），非法返回 400；③`init_chunked_upload` 校验 `0 < file_size <= MAX_FILE_SIZE`（否则 413），并在入口调用 `_cleanup_stale_user_chunks` 按 `CHUNK_TTL_SECONDS`（24h）回收本用户 mtime 过期的分片目录——只扫当前用户目录、不跨用户清理，活跃上传持续刷新 mtime 故不会误删。回归测试 `tests/unit/test_bugfixes.py::TestChunkUploadLimits`、`::TestStaleChunkCleanup`
- **FL4 [P3] 已修复**：原单文件上传用 `datetime.utcnow().strftime("%Y/%m/%d")`、分片合并用 `datetime.now().strftime("%Y%m%d")`，同文件两种时钟与两种目录格式。新增 `_storage_date_dir()` 统一为 `datetime.now().strftime("%Y%m%d")`（与仓库其余 8 处日期目录惯例一致），两条路径共用。已确认全库仅有本文件使用 `UPLOAD_DIR`，`Aicode.verify_file_access` 只按 `./uploads` 根做前缀校验、不解析日期层级，下载按 DB 存储路径读取，故已有文件路径不受影响。回归测试 `tests/unit/test_bugfixes.py::TestUploadStorageDateDir`
- **FL5 [P3] 已修复**：原 `_chunk_locks` 以裸 `file_id` 为键、只增不减，锁对象随上传次数永驻内存；且未含 user 维度，不同用户传同一 file_id 会相互阻塞。改为 `_chunk_lock_scope(user_id, file_id)` 异步上下文管理器：键为 `(user_id, file_id)`，引用计数在最后一个使用者离开时回收锁与计数条目（全程在 `_chunk_locks_lock` 内增减，持有者/等待者均持引用，无回收竞态）。回归测试 `tests/unit/test_bugfixes.py::TestChunkLockRegistry`

### skills.py（1 项）
- **SKY2 [P3] 已修复**：:213-241 /reload 原零认证可达——任何人可触发提权脚本改写全局提示词文档。修复：加 `Depends(verify_token)` 与管理员校验（`permission_level in {admin, superadmin}`）。subprocess 脚本路径已用 `BASE_DIR / ".claude" / "skills" / ...` 相对根目录解析。回归测试 `tests/unit/test_skills_reload_auth.py`
- 已排除项：name 路径穿越嫌疑解除——custom_skill_manager.py:78-82 `_validate_name` 正则 `^[a-zA-Z][a-zA-Z0-9_-]{0,63}$` 且 :118 强制调用（SkillUploadRequest Field description-only 声明但强制在 manager 层）

### providers.py（1 项）
- **PRV2 [P3] 已核实（大部分非缺陷）**：①SSRF 防线已落地——`add_provider` 与库函数 `fetch_models_openai` 双层调用 `app.utils.url_safety.check_outbound_url`（校验 scheme 仅 http/https、解析 host 并拒绝 `not ip.is_global` 的内网/保留地址）；②`sync_error` 与 ③`resp.text[:100]` 的可见范围受归属校验约束——`get_provider`/`list_providers`/`test` 均以 `owner_id = str(token["sub"])` 过滤，仅 provider owner（且 add 需 admin）可见；`str(e)` 来自 `raise_for_status`，不含请求头/api_key。两者属于 owner 自身 provider 的调试信息，保留不改为通用文案。无需代码改动

## SD1 影响面修订（第 152 轮 schema_layer.md）

第 152 轮 SD1 表述「明文兼容端点 422 锁死」经本轮实证修订：
- auth.py:83 `body: dict` 直收 JSON → **明文登录完全绕过 schema 校验**，UserLogin(min_length=8) 等校验器从不生效
- 加密登录解密后同样无长度校验 → 登录链密码校验整体缺失
- 注册链有效：:234 走 UserRegister + :241 validate_password_strength
- 结论修正：SD1 的影响面从「兼容端点 422 锁死（可用性）」升级为「登录链密码强度校验整体缺失（安全性）」，P2 定级维持，影响面扩大

### SD1 已修复（登录链凭据校验）
- 真实缺陷是**类型混淆逃逸 500**：`body: dict` 下 `plain_body["email"]` 可为任意 JSON 类型，`email[:3]`（原日志行）或 `get_user_by_email` 遇非字符串输入抛 TypeError → 500；不是认证绕过（`verify_password` 已拒绝非 `$2b$` 哈希、超 72 字节及截断比较，见 `app/utils/security.py:69-77`）。
- 修复：加密/明文两分支汇合后统一校验——`email`/`password` 必须为非空 `str`，`email` 去空白后非空且 ≤254 字符，`password` UTF-8 ≤ `BCRYPT_MAX_PASSWORD_BYTES`(72)，不满足返回 400「登录数据格式错误」；校验前移，日志切片不再可能收到非字符串。
- **刻意不引入登录密码 min_length=8**：注册链已保证强度，对存量短密码用户强制最小长度会锁死登录，且 `verify_password` 本就拒绝错误密码，无安全收益。
- 回归测试 `tests/unit/test_auth_login_credential_validation.py`（10 项：9 项非法形态参数化 + 1 项合法形态仍走 401 未知用户流程）

## 家族归并累计

- DB5（KeyError/IndexError 逃逸）：+2（AIC3、GIR2）
- DB6（conversation_id 自造/越权面）：kolors 复现 1 处
- ND（全表加载计数）：+2（KHS1、GIR4）
- MD4（naive/aware 混用）：+2（health.py:195、FL4）
- 内部错误泄露（DB7/str(e) detail）：+4（AUT5、PRV2、kolors 图生图/修复 500 detail、KHS 无）
- VK 磁盘/内存耗尽：+2（FL3、KOL3）
- 全局态无用户隔离（新增家族 GLOB）：APY2、PRV1、SKY1、AIC6 —— 自定义 provider/skill/缓存四类全局单例均无 user 维度，建议专项治理
- SD5（状态语义漂移）：API 层实证 +2（TQ6）

## 数据

- 本轮：P1 1 + P2 7 + P3 31 = 39 项，Backlog #1195-#1233
- 累计：P1 17、P2 424、P3 738
- `app/api/v1/` 扫描完成；v1 收官
