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

### AUT1 [P1] 跨用户响应缓存泄露（auth.py:444-484）
- `@cache_response(ttl=...)` 装饰三个端点：profile（:444-448，ttl=300）、history（:288-289，ttl=60）、conversations（:478-484，ttl=120）
- 缓存 key 由 `cache_decorator.py:51 _generate_cache_key` 生成，kwargs 排除表为 `"request","db","token","current_user","user_id","background_tasks"`——**user 身份不入 key**
- 三端点经 FastAPI `**values` 全 kwargs 传入，key 恒定 → 全站共享单条缓存
- 影响：用户 A 请求 profile 后，用户 B 在 ttl 窗口内拿到 A 的 email/档案；history/conversations 同理（跨用户会话列表泄露）
- 这是全库第 17 个 P1；修复方向：缓存 key 强制并入 token.sub，或对三端点摘除装饰器
- Backlog：#1195

## P2 发现（7 项）

### APY1 [P2] batch_import 恒败假功能（apikey.py:438-510）
- 每条调用 `store_key(encrypted_key=key_data['encrypted_key'])`，而 `store_key` 签名为 `(user_id, provider, api_key, ttl, remark)`（apikey_manager.py:155-162），无 `encrypted_key` 参数且 `api_key` 必填
- 恒 TypeError → 每条记 failed → 批量导入 100% 失败
- Backlog：#1196

### APY2 [P2] provider 同步跨用户 Key 覆盖（apikey.py:50-88）
- `_sync_provider_models` 用全局单例 CustomProviderManager，按 `user_{provider}` 命名（无 user 维度）
- :71 `existing.api_key = api_key` —— 后提交者覆盖先提交者的 Key（同 provider 名），跨用户盗用/覆盖面
- 与 PRV1 同族：custom provider 生态整体无用户隔离
- Backlog：#1197

### TQ2 [P2] task_id 用内存地址 id(body)（task_queue.py:67）
- `task_id = f"task_{user_id}_{id(body)}"` —— 对象回收后地址复用 → task_id 碰撞 → Celery AsyncResult 状态覆盖 + DB task_id 混淆
- Backlog：#1198

### TQ3 [P2] WebSocket 零认证（task_queue.py:338-353）
- `/tasks/ws/{user_id}`：user_id 路径参数直连 ws_manager.connect，无 token 校验
- 任意连接者可订阅任意用户任务推送（int 可枚举）
- Backlog：#1199

### GIR1 [P2] fire-and-forget 复用请求级 session（GirlAi.py:533-535）
- `asyncio.create_task(_extract_user_preferences(user_id, body.prompt, ai_content, db))` 把请求级 AsyncSession 传入后台任务
- 响应返回后 get_db teardown 关闭 session → 任务内 execute 恒败（:316 except 吞掉）→ 偏好提取静默恒败；任务句柄未保存可被 GC
- Backlog：#1200

### SKY1 [P2] skills 全端点零认证（skills.py 全文件）
- upload/list/get/update/delete/upload-file/reload 全部无 verify_token，author 硬编码 "api_user"（:71 TODO 自认）
- 自定义 skill 为全局共享库：任何人可改写 prompt skill，直接影响 kolors 自定义风格注入（kolors_api.py:228-267 `_load_custom_image_styles` 从同一 registry 读 Markdown）——未认证用户可改写全站生成行为
- Backlog：#1201

### PRV1 [P2] 动态供应商全局共享无归属（providers.py 全文件）
- get_dynamic_provider_manager() 全局单例，DynamicProvider 无 user 字段（dynamic_provider.py:37 类定义确认）
- 任意认证用户可 list/get/delete/toggle/test 全局 provider 池，并消费他人 api_key 发起 test/sync 请求
- Backlog：#1202

## P3 发现（31 项）

### auth.py（4 项）
- **AUT2 [P3]** :126 明文登录 email 全量进日志，加密模式 :115 打码 `email[:3]***` —— 日志 PII 双轨
- **AUT3 [P3]** 无 /logout 端点，refresh token（7 天 JWT）无吊销机制
- **AUT4 [P3]** :249-254 注册 check_email_exists TOCTOU → 并发双注册第二个 commit IntegrityError → 500
- **AUT5 [P3]** :322-325/:354-357 except 返回 detail=str(e) 内部错误泄露（内部泄露家族）

### apikey.py（2 项）
- **APY3 [P3]** batch TTL 仅允许 TTL_OPTIONS 预设字符串，单条支持自定义 int —— 双语义不一致；batch_import 无 _sync_provider_models（单条有），行为不一致
- **APY4 [P3]** :331-353 update_context_lengths 值无校验；:368-400 fallback chain 元素为任意字符串（模型名无白名单）

### task_queue.py（3 项）
- **TQ4 [P3]** :53-57 task_map 双向失配：TaskTypeEnum 4 值中 ppt_generate/file_process 无映射 → 400；modify_with_test 不在枚举 → 死分支；docstring 与实现不符
- **TQ5 [P3]** :304-306 retry 复用同一 task_id 重发 Celery（覆盖旧结果）+ :303 celery_task_id 为空的失败任务跳过 send_task 但 status 已改 pending → 幽灵任务
- **TQ6 [P3]** :126 celery "failure" ≠ DB "failed" 状态语义漂移；:247 cancel 白名单含 retrying（DB 层无此值）——SD5 家族 API 层实证

### Aicode.py（6 项）
- **AIC1 [P3]** :464-476 enable_search=True 与 None 行为相同——「允许搜索」按钮实际由关键词表决定
- **AIC2 [P3]** 断点续传三断链：CodeRequest 无 resume_id 字段（:775 getattr 恒 None）+ 客户端断开分支 :590 yield 至断连不可达 + /code/resume 恢复 conversation_id=None 会话断裂；写入侧 :583 活跃
- **AIC3 [P3]** :675 result["choices"][0]... 无 KeyError 防护，:635 except 元组 (ValueError/TypeError/RuntimeError/OSError/SQLAlchemyError) 缺 KeyError/IndexError → 500（DB5 家族）
- **AIC4 [P3]** :360-367 非图片文件仅返回 "[文件：name]" 占位符，文本内容从未读出（docstring 承诺理解内容）
- **AIC5 [P3]** :109-173 ai_decide_search「AI 自主判断」实为硬编码关键词表（子串误报 + 2024-2027 年份硬编码）；:204-218 select_model_for_prompt 同为关键词表（4 模型均在 ALLOWED_MODELS_LIST 白名单内，合法）
- **AIC6 [P3]** :46-47 _partial_response_cache 模块级字典多 worker 不共享（RLM3 家族）；:543 resume_from 恢复不校验 user_id（端点层 :879 有校验）
- 已排除项：verify_file_access 有 File.user_id == user_id 过滤（:402），跨用户文件访问嫌疑解除

### GirlAi.py（3 项）
- **GIR2 [P3]** :511-512 response["choices"][0]... / response["usage"]["total_tokens"] 无 KeyError 防护（DB5 家族同款）
- **GIR3 [P3]** :704 int(float(body.get("temperature"))) ValueError 未捕获 → 500；:703 自定义角色 model 无白名单（任意模型名）
- **GIR4 [P3]** :377 ilike(f"%{q}%") LIKE 通配符注入；:400 total=len(records) 分页 total 失真（ND 家族）
- 已排除项：girl_request.py 有 character_id/temperature/max_tokens 字段，getattr 兜底对齐无害；:215-229 _clean_response 正则安全；:346-353 头像端点静态 SVG 无害

### kolors_api.py（5 项）
- **KOL1 [P3]** :484-509/:666-706 参考图归属校验用 `File.file_path.contains(image_path)`，image_path 用户可控 → LIKE 通配符注入可绕过校验；下游 image_to_base64（image_generation.py:128-143）仅扩展名白名单 + 10MB 限制，无路径白名单 → 任意图片文件读取（泄露渠道间接：原图内容进生成图），定 P3
- **KOL2 [P3]** :56-109 get_cached_image 缓存命中用 metadata_json.contains(f"image:{prompt}:{seed}") —— SQL LIKE 全表扫 + `%/` 通配符失配
- **KOL3 [P3]** 内联 TextToImageRequest/ImageToImageRequest 参数无 ge/le 约束：num_images 无上界（成本放大器，config 宣称 max 4 但校验缺失）、width/height/num_inferences 同
- **KOL4 [P3]** :126-137 缓存写 History 自造 conversation_id=max+1（DB6 家族复现）；:150-158 图像缓存混入业务对话表
- **KOL5 [P3]** :271 STYLE_PROMPTS 模块导入时求值一次，自定义 skill 风格改动需重启（热加载失效；/styles 端点 :865 用 get_style_prompts() 动态获取，两套读取并存）

### kolors_history.py（1 项）
- **KHS1 [P3]** :56-59 total 用 len(all()) 全表加载计数（ND 家族 +1）；:48 等 token.get("sub") 未 int() 转换直进 ORM where（与全库 int(token["sub"]) 惯例不一）

### file_upload.py（5 项）
- **FL1 [P3]** 分片链 file_id 无归属校验：upload_chunk/merge_chunks 仅凭 uuid file_id 操作，B 知 file_id 可把 A 的分片合并记到自己名下（uuid 不可枚举，降 P3）
- **FL2 [P3]** 安全双轨：单文件链有 validate_file_upload + validate_file_content 双层验证；分片链 merge 路径零验证（无扩展名/内容检查），可落盘任意后缀文件；:421 filename 未净化直接拼路径（uuid 前缀阻断 ".." 穿越——"uuid_.." 为字面目录名，实际可利用性低，记加固项）。已验证 uploads 无静态挂载（main.py:341-343 仅 /static），download 端点 attachment 头兜底
- **FL3 [P3]** :355 chunk.read() 无单分片大小限制（约定 5MB 无强制）；chunk_index 任意 int；.chunks 孤儿分片永不过期清理 → 磁盘耗尽家族（VK1/CS3 同族）
- **FL4 [P3]** :185 datetime.utcnow() vs :418 datetime.now() 同文件双时间语义（MD4 家族）+ 两种目录格式 %Y/%m/%d 与 %Y%m%d
- **FL5 [P3]** :37 _chunk_locks 字典只增不减，file_id 锁永驻内存（慢泄漏）

### skills.py（1 项）
- **SKY2 [P3]** :213-241 /reload 零认证可达 + subprocess 硬编码绝对路径 /workspace/.claude/skills/...（部署路径耦合）；SKY1 叠加面
- 已排除项：name 路径穿越嫌疑解除——custom_skill_manager.py:78-82 `_validate_name` 正则 `^[a-zA-Z][a-zA-Z0-9_-]{0,63}$` 且 :118 强制调用（SkillUploadRequest Field description-only 声明但强制在 manager 层）

### providers.py（1 项）
- **PRV2 [P3]** :81 base_url 无 scheme/host 校验 → test/sync 由服务器向任意地址发请求（带 api_key 头），内网可达 SSRF 面（认证 + 10/min 限流，降 P3 记加固项）；:183-186 sync 失败 str(e) 进 sync_error 返回任意用户；:234 resp.text[:100] 泄露上游响应

## SD1 影响面修订（第 152 轮 schema_layer.md）

第 152 轮 SD1 表述「明文兼容端点 422 锁死」经本轮实证修订：
- auth.py:83 `body: dict` 直收 JSON → **明文登录完全绕过 schema 校验**，UserLogin(min_length=8) 等校验器从不生效
- 加密登录解密后同样无长度校验 → 登录链密码校验整体缺失
- 注册链有效：:234 走 UserRegister + :241 validate_password_strength
- 结论修正：SD1 的影响面从「兼容端点 422 锁死（可用性）」升级为「登录链密码强度校验整体缺失（安全性）」，P2 定级维持，影响面扩大

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
