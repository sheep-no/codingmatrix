# 模块详档：app/api/v1/AiProjectCode.py（第一百四十三轮，v1.144）

## 模块定位：半废弃遗留文件判定

**结论先行：AiProjectCode.py（651 行，文件头注释 `# /api/agent.py`）是「遗留文件 + 新体系借用其工具函数」的半废弃件。** 文件主体（3 个路由 + zip 上传体系 + 知识积累链 + 6 个工具旧副本 + 3 个死类）全部废弃，仅 3 个会话/统计工具函数被新 ai_agent 体系活跃消费。

文件内 3 个路由（`upload_project_zip` :520 / `list_user_uploads` :606 / `delete_user_upload` :631）的 router（prefix `/agent`）**从未被挂载**：
- `app/main.py:70` 仅 `from app.api.v1.ai_agent import router as agentRouter`，其 `ai_agent/router.py:11-15` include 的 generate/orchestrate/association/knowledge/performance 五个子 router 均不含本文件
- 全库 grep 零 `include_router(AiProjectCode...)` / 零 `from app.api.v1.AiProjectCode import router`
- 三个端点对外恒 404，是历史版本（曾以 `/agent` 前缀独立挂载，故文件头注释 `# /api/agent.py`）被新 ai_agent 包取代后的废弃残留

## 活跃面（被新体系消费，仅此一处）

| 符号 | 消费方 | 说明 |
|---|---|---|
| `create_agent_session` :39 | orchestrate_endpoints.py:105 import，:457 调用 | `POST /agent/orchestrate`（:439）每条请求都经过 |
| `log_tool_execution` :62 | orchestrate_endpoints.py:105 import，:382/:482 调用 | 工具执行日志落库 |
| `update_model_stats` :87 | orchestrate_endpoints.py:105 import，:491 调用 | 模型统计落库 |
| `ProjectGeneratorAgent`（re-export，:31 自 agent_core import） | project_tasks.py:39 | 实际类定义在 agent_core.py:1288，此处仅是再导出 |

## 废弃面盘点（全库零外部引用，经 grep 逐一确认）

1. **3 个路由**（zip 上传/列表/删除）——router 未挂载，不可达
2. **zip 上传安全体系**：`USER_UPLOADS_DIR` / `_validate_zip_safety` / `_sanitize_project_name` / `USER_UPLOADS_MAX_SIZE` / `ZipUploadResponse` / `UploadedProjectInfo` 全库零引用
3. **知识积累链**：`accumulate_knowledge` :135 + `log_generation_result` :192 互相调用但无任何入口，整链死
4. **6 个工具旧副本**：`_validate_project_path` / `_collect_files` / `_build_agent_config` / `_safe_update_progress` / `_create_zip_archive_safe` / `_cleanup_temp_dir` —— 新版在 `ai_agent/helpers.py`（generate_endpoints.py:29-30 走新版），此处为旧残留
5. **死类**：`SearchMatch` :435（无 `__init__` 无 BaseModel 的无主类）、`ThinkingStreamer` :381、`ProjectTreeNode` :443
6. **死常量**：`MAX_SAVED_PROJECTS_PER_USER = 3`（:274，新体系 project_config.py:43 为 50，值不一致且本文件内零使用）

## 缺陷清单

### 活跃面（正常定 P 级）

- **AIC1 [P3] `PROJECTS_BASE_DIR = "./projects"`（:232）相对路径依赖 CWD**——与 ai_agent/project_config.py:1 同源（helpers.py:23 亦 import 此值）。当前以 `uwsgi/gunicorn` 从项目根启动时恰好正确，但多 worker / systemd / cron 启动 CWD 漂移时 `_validate_project_path`（helpers.py:47）/ `resolve_output_dir` 全部路径错位——活跃面路径体系的基础假设是「CWD=项目根」，无启动时 CWD 校验。

- **AIC2 [P3] `update_model_stats` 更新分支不维护 `avg_execution_time`（:108-115）**——仅首次创建时赋值（:125），此后 request_count/total_tokens/success/failure/last_used_at 递增但 `avg_execution_time` 恒为首次值。orchestrate 端点每请求调用，统计失真（AGM5 已记分母含失败请求，此处补充「字段从不更新」面）。

- **AIC3 [P3] project_tasks.py:39 经本文件 re-export 引用 `ProjectGeneratorAgent`（实际定义 agent_core.py:1288）**——脆弱间接引用：AiProjectCode 仅 `from app.utils.agent_core import ProjectGeneratorAgent`（:31）后即被 project_tasks 再导出消费。迁移/删除本文件将直接破坏该 Celery 任务，修复方向是 project_tasks 改直接 `from app.utils.agent_core import ProjectGeneratorAgent`。

### 废弃面（按用户指示不按活跃定 P 级，标注「废弃代码内逻辑缺陷」）

- **AIC4 [P3 废弃面] 3 个路由能力未接线**——zip 上传/用户项目列表/删除三能力设计存在但 router 从未挂载（能力未接线家族 SCT5 同族）。归档依据：这是判定「文件废弃」的第一证据。若未来需要 zip 上传能力，应在新 ai_agent 包内重写而非复活本文件。

- **AIC5 [P3 废弃面，复活即 P0] 路径校验可绕过 → 跨用户删空 user_uploads**——`delete_user_upload`（:631）：`_sanitize_project_name`（:467）允许 `.` 通过（`.` 在 `[\w\-_.\u4e00-\u9fff]` 白名单内），`project_name="."` → `target_dir = USER_UPLOADS_DIR/`.` = USER_UPLOADS_DIR 自身` → :641 `str(target_dir).startswith(str(USER_UPLOADS_DIR))` 对自身恒 True → `shutil.rmtree(USER_UPLOADS_DIR)` 删除**全量用户上传目录**。且 list（:607 无 user_id 过滤按 mtime 列全量）/ upload（:553 项目名无用户隔离，同名校覆盖他人项目）三端点全部无归属校验——越权家族在废弃面的残留。当前不可达（路由未挂载），复活即 P0。

- **AIC6 [P3 废弃面] zip 上传无解压总量限制**——50MB 压缩包（:544）解压后单文件 `zf.read`（:570）无大小上限、文件总数无上限、嵌套目录深度无上限 → 压缩炸弹/磁盘耗尽。另 `_validate_zip_safety`（:488）`'..' in name` 对合法文件名子串误杀（如 `a..b.py` 被跳过），安全判定应基于路径规范化后 `is_relative_to`。

- **AIC7 [P3 废弃面] 死代码家族第 31 处**——`SearchMatch`/`ThinkingStreamer`/`ProjectTreeNode` 死类 + `accumulate_knowledge`→`log_generation_result` 知识积累链整链死（互相调用但无入口，AGM3 记过的「知识写入双轨 accumulate_knowledge」实际在活路之外）+ 死常量 `MAX_SAVED_PROJECTS_PER_USER=3`。

- **AIC8 [P3 废弃面] 6 工具函数双轨副本（双轨家族）**——`_validate_project_path`/`_collect_files`/`_build_agent_config`/`_safe_update_progress`/`_create_zip_archive_safe`/`_cleanup_temp_dir` 在 AiProjectCode.py 与 ai_agent/helpers.py 各一份，生产消费方（generate_endpoints.py）走 helpers 版。**两副本安全语义不一致**：helpers 版含 user_id 归属校验（helpers.py:59-72），旧版仅 startswith 前缀检查（:285，无 os.sep 边界，GH4/AA4 家族）——归档时直接丢弃旧副本，不得复用。

## 交叉确认

- `orchestrate_endpoints.py:105` 三条 import 的调用点 :457/:482/:491 均位于 `@router.post("/orchestrate")`（:439）活跃路由内——**AiProjectCode 活跃面的唯一载体确认**
- `agent_memory.md` AGM3 已记 `create_agent_session` 三实现并存（service.create_session + AiProjectCode.create_agent_session + ai_agent 内部），本轮确认其活跃消费方
- `docker_runner.md` DR9 已记 `ALLOWED_PACKAGES` 三份副本（AiProjectCode:235 / project_config → helpers / docker_runner），本轮补全：`PROJECT_MIME_TYPES`/`SKIP_DIRS`/`MAX_TEXT_FILE_SIZE`/`PROJECTS_BASE_DIR` 亦在 AiProjectCode 与 project_config 双份（配置收敛对象，§5.6 支柱 1 家族）
- `_build_agent_config`（:346）`shared_base_venv="/opt/base_venv"`（:359）硬编码路径，与 env 校验配置耦合，旧副本同样未迁移

## 测试状态

无专项测试。3 个死路由 + zip 体系无任何测试保护；活跃面 3 函数被 orchestrate 端点隐式覆盖（无直接单测）。

## 归档建议

**迁移 AiProjectCode 后整体退役**：
1. 将 `create_agent_session`/`log_tool_execution`/`update_model_stats` 迁入 `app/api/v1/ai_agent/`（如 helpers.py 或新建 session_stats.py），改 orchestrate_endpoints.py:105 import 指向
2. project_tasks.py:39 改直接 `from app.utils.agent_core import ProjectGeneratorAgent`
3. 删除整个 AiProjectCode.py（含 zip 上传体系、知识积累链、6 工具旧副本、3 死类）——废弃面缺陷 AIC4-AIC8 随删除归零，无需逐条修复
4. 若未来要 zip 上传能力，在新 ai_agent 包内重写并补归属隔离（user_id 子目录）+ 解压总量限制 + 路径 `is_relative_to` 校验

## 下轮候选

app/api/v1/AiProjectCode.py 已闭合（首扫即废弃判定）。转 app/utils/pptx/（13 文件，aiGeneratorPptx.py 消费方）或 app/api/v2/ 8 文件。
