# 模块详档：app/models/（ORM 模型层）

> 轮次：第一百四十九轮 | 日期：2026-08-28 | 文件数：13 | 总行数：885
> 扫描范围：__init__ / base / Permission / saved_project / history / user / aicloud_knowledge / chat_history / aicloud / server_config / file / task / agent_memory

## 1. 模块定位与状态判定

ORM 模型层，定义全部 13 张核心表的 SQLAlchemy 模型（user/permission/history/chat 三表/file/task/saved_projects/server_config 两表/aicloud 两文件四表/agent_memory 六表）。全文件活跃（__init__.py 导出 22 个模型，被 db 层/scheduler/celery/各 API 消费）。

| 文件 | 行数 | 状态 | 核心表/内容 |
|------|------|------|------------|
| user.py | 68 | 活跃 | User + 8 个 ORM 关系（cascade 全声明） |
| agent_memory.py | 144 | 活跃 | AgentSession/MemoryEntry/AgentReflection/KnowledgeEntry/ToolExecutionLog/ModelUsageStats |
| task.py | 121 | 活跃 | Task + 三个状态枚举（枚举消费见 MD7） |
| file.py | 99 | 活跃 | File（含解析缓存方法三件套 + to_dict） |
| server_config.py | 92 | 活跃 | ServerConfig（14 项 DEFAULT_CONFIGS）+ **ServerStats（死表，MD5）** |
| aicloud.py | 88 | 活跃 | AicloudSession/Message/Review/AuditLog |
| chat_history.py | 75 | 活跃 | ChatHistory/ChatSummary/CustomCharacter/UserPreference |
| aicloud_knowledge.py | 73 | 活跃 | AicloudKnowledgeDoc/Chunk（user_id 裸列无 FK） |
| user.py 之外小件 | — | 活跃 | History(28)/saved_project(24)/Permission(17)/base(5)/__init__(51) |

## 2. 缺陷清单

### P2（1 项）

**MD1 [P2] 用户删除级联矩阵混乱：delete_user 端点直删 User，五类关联表的级联行为分裂**
- user_manage.py:235/:256 `delete_user` 端点 `await db.delete(user)` 直删。
- 级联覆盖现状：User.py 声明 ORM cascade 的仅 8 个关系（chat_histories/chat_summaries/permission/saved_projects/agent_sessions/memory+reflections 随 session 级联/knowledge_entries/model_usage_stats/custom_characters/user_preferences）✅；**History（user.py:18）无 ORM cascade 且 FK 无 ondelete** → 删 User 时 History（含对话全文 prompt/response/thinking）残留孤儿或 FK 报错；**File/Task 仅 DB 层 ondelete=CASCADE**（file.py:28/task.py:74），ORM 层无声明——且全库无 `PRAGMA foreign_keys=ON` 设置代码（grep app/db 无命中）→ **SQLite 部署下 DB 级联全部失效**；**AicloudSession/AicloudReview/AicloudAuditLog（aicloud.py:22/:59-60/:77）有 FK 无 ondelete、无 ORM 关系**；**AicloudKnowledgeDoc/Chunk user_id 裸 Integer 无 FK**（aicloud_knowledge.py:19/:56）→ 必然孤儿。
- 两种部署两种坏行为：SQLite（FK off）→ History/Aicloud*/KnowledgeDoc 全部孤儿残留（对话与审计数据泄露面）；MySQL（FK enforce）→ 删 User 报 FK 错误 500（delete_user 功能失效）。模型注释自认「兼容 SQLite 和 MySQL」（aicloud_knowledge.py:4）但级联行为不兼容。
- 修复：统一层级——History 补 ORM cascade；File/Task 补 ORM cascade 或确认 DB enforce；Aicloud 三表补关系 + ondelete；KnowledgeDoc 补 FK。删除用户改为显式逐表清理事务亦可。

### P3（7 项）

- **MD2 [P3]** Permission 表缺 `UniqueConstraint(user_id)`（Permission.py:13-18）——user 关系 `uselist=False`，多行即 MultipleResultsFound 崩溃；permission_level String 无 CHECK 约束（V2U1 提权链的 DB 层约束缺位，全靠应用层 pattern）；文件名大写 `Permission.py` 与全小写命名风格不一致。
- **MD3 [P3]** 时间语义三态混用（SLG3 家族模型层）：aicloud.py 同文件混用 naive `default=datetime.utcnow`（Review:63/AuditLog:83）与 aware `lambda: datetime.now(timezone.utc)`（Session:23-24）；file.py created_at 用 aware lambda 但列无 timezone=True，缓存三方法全 naive utcnow（:65/:82/:98）；aicloud_knowledge.py 全套 naive + 无 timezone 列——与其他表 timezone=True 混用，跨表时间比较/排序语义漂移。
- **MD4 [P3]** 向量存储三处 JSON/Text 列缺 pgvector：MemoryEntry.embedding JSON（agent_memory.py:49）、AicloudKnowledgeChunk.embedding Text JSON（aicloud_knowledge.py:61）——VK3「检索全表加载 O(N)」与 AME1 检索的模型层根因，向量列无法索引。
- **MD5 [P3]** ServerStats 死表（server_config.py:79-92）：全库唯一引用是 resource_config.py:12 的 import（导入未使用），零写入零读取——**死代码家族第 36 处**（模型级）；ServerConfig.updated_by 无 FK（轻量可接受但与「记录操作人」意图不符）。
- **MD6 [P3]** chat_history.py 三点：CustomCharacter.temperature Integer 存 `0.8*100`（:54 注释约定）——跨层缩放约定易错（消费方忘 ÷100 即温度×100）；max_tokens 默认 180 过小（长回复恒截断）；UserPreference 缺 (user_id, preference_key) 唯一约束——同一偏好 key 可无限重复插入（user_preference_learner 的 confidence 更新变追加行）。
- **MD7 [P3]** 枚举形同虚设：TaskStatus/TaskType/TaskPriority（task.py:11-32）定义后消费方（scheduler/task_queue/file_upload/celery_app/task_manager）全用裸字符串读写 status/task_type——枚举与列约束双重缺位，非法状态值可入库（task_manager AJP1 家族的模型层注脚）；is_deleted Integer 0/1（file.py:38）vs chat_history Boolean 风格分裂；history.py:26 `extend_existing: True` 遮蔽标志残留（重名定义隐患的自白）。
- **MD8 [P3]** File.to_dict（file.py:55-66）返回 parsed_content 全文 → file_upload.py:180/:211 `FileUploadResponse(**existing_file.to_dict())` 上传/秒传响应携带全量解析文本（响应膨胀面）；KnowledgeEntry 缺 (user_id, knowledge_key) 唯一约束（agent_memory.py:85-86）——agent_memory_service.add_knowledge 同 key 重复插入。

## 3. 交叉确认记录

| 疑点 | 结论 |
|------|------|
| AME1 cascade（上轮遗留） | **部分实锤**：AgentSession→MemoryEntry/AgentReflection ORM cascade ✅ 级联正常；**ToolExecutionLog 无 ORM 关系无 cascade 且 session_id FK 无 ondelete**（agent_memory.py:104-120）→ services 层 delete_session 残留工具日志孤儿（AME1 补充证据，并入 MD1 同族问题） |
| ServerStats 消费方 | resource_config.py:12 import 未使用 → 死表实锤（MD5） |
| delete_user 删除方式 | user_manage.py:256 `db.delete(user)` 直删 → MD1 主证据 |
| Task 枚举消费方 | 零消费（消费方全用裸字符串）→ MD7 |
| File.to_dict 消费方 | file_upload.py 4 处，:180/:211 进 FileUploadResponse → MD8 |
| PRAGMA foreign_keys | app/db 无设置代码 → MD1 的 SQLite 级联失效推定（待 app/db 轮终审） |
| ModelUsageStats 唯一约束 | :143 `unique (user_id, model_key)` ✅ 为上轮 AME1 读改写竞态兜底（并发插入 IntegrityError 而非双行）——正面点名 |

## 4. 正面点名

- **ModelUsageStats 唯一约束**（agent_memory.py:143）——services 层读改写竞态的 DB 层兜底设计正确。
- **file.py:47 + task.py:91 双向外键关系声明**（foreign_keys 显式指定）与 **Task.parent_task 自引用 ondelete=SET NULL**（task.py:62/:77）——自引用级联正确示范。
- **AicloudKnowledgeChunk 双索引设计**（idx_doc_user/idx_user_collection，aicloud_knowledge.py:49-52）——查询路径覆盖合理。

## 5. 修复建议优先级

1. **立即**：MD1 级联矩阵统一（History 补 cascade；Aicloud 三表补关系；确认部署 DB 的 FK enforce 状态）。
2. **短期**：MD2 Permission 唯一约束 + CHECK；MD5 删 ServerStats 死表与无效 import；MD6/MD8 唯一约束与响应瘦身。
3. **中期**：MD4 向量列迁移 pgvector（与 VK3 联动）；MD3 时间语义统一（timezone=True + aware 全套）；MD7 枚举接线或删除。

## 6. 下轮候选

app/middleware 4 文件（912 行：rate_limiter 429 / input_validator 297 / feature_switch 93 / security_headers 93——RLC2 交叉确认在本轮完成）或 app/db（12 文件：PRAGMA foreign_keys 终审 + scheduler）。

## 7. 状态更新（2026-09-18 核实）

按行号逐条核实代码现状后的结论（以当前代码为准，原文档行号已漂移）：

- **MD1 [P2] 已修**：`delete_user` 在 `db.delete(user)` 前新增 `_purge_user_owned_data`（`app/api/v2/user_manage.py`），按外键依赖顺序显式清理用户数据，再删除 User 本体。
  - 实证旧行为：用户只要有 `history`/`files`/`tasks` 行，删除即报 `NOT NULL constraint failed: files.user_id`——`User.histories` 无 cascade，`File.uploader`/`Task.user` 的 backref 也无 cascade，SQLAlchemy 在删父行时把子表外键置空。
  - 实证新行为（PR #18 开启 SQLite 外键约束后）：`aicloud_*`、`github_user_configs` 等仅有无 `ondelete` 外键的表会以 `FOREIGN KEY constraint failed` 阻断删除；`aicloud_knowledge_*`、`app/db/models.py` 的 `project_sessions`/`workflow_history`/`image_generation_history`/`conversation_messages` 的 `user_id` 是裸列，静默残留孤儿。
  - 清理范围：`history`/`files`/`tasks`、`aicloud_sessions`+`aicloud_messages`、`aicloud_reviews`、`aicloud_audit_logs`、`aicloud_knowledge_docs`+`aicloud_knowledge_chunks`、`github_user_configs`、`tool_execution_logs`（按用户会话归属）、`project_sessions`/`workflow_history`/`image_generation_history`/`conversation_messages`（字符串 `user_id`）。仅依赖 DB `ondelete=CASCADE` 的 `sessions`/`messages` 等由数据库级联兜住。
  - 决策：项目无迁移框架，故不改 schema（未给 Aicloud 三表补 `ondelete`、未给 KnowledgeDoc 补 FK），改用显式事务清理以兼容既有 SQLite/MySQL 库；Agent 子系统模型未改动，仅在删除路径清理其从属数据。
- **新发现（原文档未列，已修）**：`ToolExecutionLog`（AME1 补充证据）在 PR #18 后同样阻断删除用户——它无 ORM 关系、`session_id` 外键无 `ondelete`，`User.agent_sessions` 级联删会话时触发外键错误。现已纳入 `_purge_user_owned_data`。
- **新增回归**：`tests/unit/test_user_deletion_cascade.py`（1 项，覆盖 18 张表的清理与另一用户数据不受影响）；回退 `user_manage.py` 后该测试失败。
- **MD2 [P3] 已修（唯一约束部分）**：`Permission.__table_args__` 增加 `UniqueConstraint("user_id", name="uq_permission_user_id")`。`user.permission` 为 `uselist=False`，同用户多行会让读取抛 `MultipleResultsFound`。新增回归 `tests/unit/test_permission_unique_constraint.py`，回退模型后测试失败。
  - **未加 CHECK 约束**：代码库测试与 token 仍在使用 `"super"`/`"user"` 等不在 `PERMISSION_LEVELS` 内的级别（如 `tests/unit/test_database_services.py`、`tests/conftest.py`），加 `permission_level IN (...)` 会直接破坏既有用例；且生产代码只用三级值，CHECK 属可选的防御加固，留待与权限级别口径统一时处理。
  - **既有库不受约束保护**：项目无迁移框架，`create_all` 不会为已存在的 `permission` 表补约束，仅新库生效；`PermissionService.create_permission` 仍是裸插入，并发下可能 IntegrityError 而非静默重复（较重复行更可取）。
- **MD5 [P3] 已修**：删除 `ServerConfig` 文件末尾的 `ServerStats` 死表（零写入零读取），同时移除 `app/services/resource_config.py` 的未使用导入及 `server_config.py` 中随之失效的 `relationship`/`BigInteger`/`Float` 导入。
- **MD3/MD4/MD6/MD7/MD8 未处理**：其中 MD6 建议的 `UserPreference(user_id, preference_key)` 唯一约束与 `CompanionMemoryService` 的软删除语义冲突（`status="deleted"` 行会保留、同 key 允许再建 candidate），不可直接添加；MD8 的「响应携带全量 parsed_content」经核实不成立（`FileUploadResponse` 未声明该字段，Pydantic v2 默认忽略额外键）。其余待后续。
