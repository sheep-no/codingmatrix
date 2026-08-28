# 第一百四十七轮：app/api/v1/ 余下五文件合扫

> 扫描日期：2026-08-28
> 状态判定：5 文件全部「活跃」（main.py:307/:313/:314/:316/:328 全部 include）；aicloud.py 已于第一百四十轮建档（submission_api.md），本轮不含

## 模块定位与状态判定

| 文件 | 行数 | 三态 | 挂载（main.py） | 端点 |
|------|------|------|-----------------|------|
| aiGeneratorPptx.py | 2133 | **活跃** | :307 pptxRouter（prefix=/api/v1） | /pptx/* 16 端点 + /generate-text + /generate-from-text + WS /ws/ppt/{task_id} |
| workflow.py | 676 | **活跃** | :314 workflowRouter（无 prefix，自带 /api/v1/workflow） | execute/status/import/export/delete/history 10 端点 |
| aicloud_knowledge.py | 346 | **活跃** | :313 aicloudKnowledgeRouter | /aicloud/knowledge/* 4 端点 |
| vision_api.py | 310 | **活跃** | :316 visionRouter | /vision/* 4 端点 |
| model_manager.py | 209 | **活跃** | :328 modelManagerRouter | /models/* 5 端点 |

**模块定位**：v1 余量五文件是用户侧功能 API（PPT 生成/工作流/知识库/视觉/模型浏览）。全部走 verify_token，但**归属校验系统性缺失**（仅 cancel 端点校验 user_id）与 **task_manager 状态转移语义断裂**（失败恒报成功）是两条主线。aiGeneratorPptx.py 同时是 visual/pptx 两包的消费编排层（VPX1 await 崩点与 PPX1 parse 崩点都在本文件）。

## 活跃面

1. **PPT 生成主链（aiGeneratorPptx.py）**：generate_task（异步任务）/generate（同步）/update（增量）/modify（视觉修改）/generate_from_file（文件上传）+ download/preview/slides/history/templates/upload + WS 进度。大纲生成 → 视觉决策（VPX1 崩点恒降级）→ 渲染 → 落盘 pptx_output。
2. **workflow API（workflow.py）**：自然语言分解（TaskDecomposer）→ GraphValidator → WorkflowExecutor 流式执行（NDJSON SSE）；import/export/status/history。
3. **知识库（aicloud_knowledge.py）**：上传（parse→chunk→embed→DB）/列表/删除/检索（余弦相似度）。
4. **视觉 API（vision_api.py）**：analyze/ocr/code-from-image/check-safety，临时文件 finally 清理完善。
5. **模型浏览（model_manager.py）**：registry 列表/默认模型/能力枚举/agent-config 只读。

## 未接入面

无（5 文件全活跃；文件内死符号见 AJP12）。

## 废弃面

无。

## 缺陷清单

### aiGeneratorPptx.py（AJP 前缀）

| 编号 | P 级 | 位置 | 描述 |
|------|------|------|------|
| AJP1 | P2 | :820-821/:914-932/:1640/:1685/:1687/:1799/:1846/:1848 | **任务失败态谎报**（「报告成功」与实际结果分离家族，TR1/WFE1/TM3 同族）：四处任务入口的包装 update_progress 签名收 status/result_data 但**只转发 progress/message**（task_manager.update_progress 仅 3 参且仅 RUNNING 态更新）+ run_* 函数 catch 全部异常后正常返回 → task_manager 内部包装恒标 SUCCESS——**生成失败/被取消的任务状态=success**，WS 推送 completed、前端误判成功；错误只残留在 progress_message |
| AJP2 | P2 | :1361-1394/:1397-1413 | **PPT 历史与文件全站共享无用户隔离**（越权家族，AA2/WF2 同族）：list_ppt_history `glob("*_slides.json")` 扫全站返回**所有用户**的标题/页数/时间（user_id :1368 取了不用，docstring「用户的 PPT」谎言）；delete_ppt_history 无归属校验——任意登录用户可删他人 PPT 全部文件（slides.json+pptx+html+md unlink） |
| AJP3 | P2 | :682/:766-775 | **预览页与 HTML 导出存储型 XSS**：HTML 导出 f-string 直拼 LLM 输出（title/content 无转义）+ 预览页 fetch slides 后 `card.innerHTML = ${slide.title}/${slide.content}` 直插——用户 topic 引导 LLM 输出 `<script>`/`<img onerror>` → 查看预览/下载 HTML 者执行（预览 URL 可分享，存储型 XSS 面） |
| AJP4 | P3 | :405/:846-853 | 素材绑定只传文件名（「绑定≠消费」家族，PPX3 同族）：material_file_ids 查 DB 后仅把 filename 列表拼 prompt，素材**内容从未读取进 LLM**——「素材上传绑定」名不符实 |
| AJP5 | P3 | :882-884/:878 | PDF 输出格式假实现（「规划功能未生效」家族）：OutputFormat.PDF 枚举与 ext_map "pdf" 键存在，命中即 logger.warning 恒回退 PPTX——用户选 PDF 得 PPTX 无前端提示 |
| AJP6 | P3 | :452/:461-496 | 大纲 JSON 提取贪婪跨块（MAR5/SPFG16 家族第 N 处）+ LLM 失败降级恒 4 页固定大纲（PPT2 页数语义家族：请求 10 页得 4 页模板页） |
| AJP7 | P3 | :1000-1086/:1115-1132/:1235-1302/:1305-1334 | download/preview/slides/update/modify/analyze 六端点无归属校验（uuid4 缓解枚举但 URL 分享即越权读写他人 PPT 内容；对比 cancel :1101 有 user_id 校验——同文件不对称） |
| AJP8 | P3 | :2029-2116 | WS 进度推送无认证 + 0.5s 轮询 Redis（无 token 验证匿名可连——V2C1 同族；task_manager 无 pub/sub，每连接每秒 2 次 Redis 查询） |
| AJP9 | P3 | :1127-1132/:1136 | update_ppt_task 外层 task_id 读他人中间状态 + 闭包参数新 id 写——跨用户内容读取（他人 PPT 大纲成为攻击者新 PPT 的基底） |
| AJP10 | P3 | :64/:1751/:1900 | pptx_output/uploads/configs 相对路径 CWD 依赖（GRD3/AIC1 家族）+ pptx_output 无清理机制磁盘无界（VPX3 同族） |
| AJP11 | P3 | :1757-1759/:1907-1909/:1770 | 文件上传先全量读入内存后查大小（50MB/20MB）+ generate_from_file 端点内同步 parse_document 阻塞事件循环（VK1 同族） |
| AJP12 | P3 | :1489/:1503/:1520/:1625-1626/:1925/:1962/:1661 | **死代码家族第 34 处**：download_image/search_image_url/IMAGE_CACHE_DIR 定义后全文件零调用 + 4 处函数内重复 import（uuid/TaskResponse/json as _json）+ :1661 hasattr(req,'template') 死分支（OutlineGenerationRequest 无该字段恒 else） |
| AJP13 | P3 | :1998-2003 | LibreOffice 转换同步 subprocess.run 阻塞事件循环 60s（GH2/LA7 家族）+ 每次下载重复转换无缓存 |
| AJP14 | P3 | :91/:108/:1729 | api_key_token 经请求体/Form 传输（Key 走 body 落访问日志风险，SEC 家族）+ PPX1 实锤点 :1921 parser.parse 恒 AttributeError 被降级包装为 200+config=None |

### workflow.py（WFA 前缀，与 WF 核心/STM/GV 区分）

| 编号 | P 级 | 位置 | 描述 |
|------|------|------|------|
| WFA1 | P2 | :89-91/:103-109/:266-274 | **会话工作流跨用户读取**（越权家族，AA1 同族）：`_session_workflows.get(session_id)` 无 user_id 校验——用户 B 传 A 的 session_id 即可读取 A 的 previous_request 全文（continuation_context 事件回传）并基于其继续生成（污染）；:272 写入时记录 user_id 但读取从不校验 |
| WFA2 | P2 | :396-414/:527-567/:570-591 | **execute_imported/export/delete 无归属校验**（WF2 实锤位置）：任意登录用户可执行他人导入的工作流（与 CE1 无沙箱 code_execution 组合=在服务器跑他人节点代码）、导出他人工作流（HTTP 节点 header 可含 token）、删除他人工作流 |
| WFA3 | P3 | :358-393 | import 无归属/数量限制：workflow_id 用户可控直接作 dict 键——可覆盖他人同 ID 条目；重复 import 不同 ID 无上限（WF1 内存无界叠加） |
| WFA4 | P3 | :146-150/:216-232/:322-334 | _workflows 条目永久残留（executor 异常路径无清理）+ 存入 dict 从未存 aggregator/status 键 → status 端点新建空 executor 恒报 running（WF1/WF3 的 API 层实锤） |
| WFA5 | P3 | :610-613/:576/:80 | history total 全表加载计数（len(all()) 应 count()）+ delete docstring copy-paste「导出工作流」+ user_id（str sub）写入 WorkflowHistory.user_id 类型漂移致历史保存静默失败 |

### aicloud_knowledge.py（VK 前缀，与 KP utils 区分）

| 编号 | P 级 | 位置 | 描述 |
|------|------|------|------|
| VK1 | P2 | :100/:128-131 | **上传链同步阻塞事件循环 + 无大小限制**：parse_document/chunk_text 同步 CPU/IO 直接在 async 端点内调用（docstring :74「异步处理文档」谎言）+ `await file.read()` 无大小限制全量进内存——大 PDF 上传期间全服务请求冻结（可用性 DoS） |
| VK2 | P3 | :68-69 | chunk_size/chunk_overlap 用户可控无 ge/le 校验——**KP1 死循环 DoS 的用户可控入口**（chunk_size=0/负数或 overlap≥size 即协程永久阻塞，KP1 修复需同步本处） |
| VK3 | P3 | :150/:284-321 | 检索全表加载 O(N)：embedding 存 JSON 字符串列 → search 拉取用户全部 chunks 进内存 json.loads + Python 余弦，无 pgvector/无 LIMIT |
| VK4 | P3 | :47-48 | 硬编码绝对路径 `/workspace/data/knowledge` + import 时 mkdir 副作用（GRD3 反向变体：部署环境绑定 /workspace） |
| VK5 | P3 | :134-137/:151 | 失败上传文件残留磁盘（status=failed 后文件不清理）+ embedding_model 字符串硬编码与 embed_chunks 内部模型漂移面 |

### vision_api.py（VA 前缀，与 VS utils 区分）

| 编号 | P 级 | 位置 | 描述 |
|------|------|------|------|
| VA1 | P3 | :104-105/:182-187/:230-235/:282-287/:129 | 四端点先全量读入内存后查 10MB 上限（超限前已占内存）+ :129 畸形 data URI（无冒号）split IndexError → 500 |
| VA2 | P3 | :194/:84 | OCR model_used 硬编码 "deepseek-ai/DeepSeek-OCR" 与实际降级链不符（谎报模型）+ docstring「JSON body」与 multipart Form 实现不符 |
| VA3 | P3 | 四端点 | 视觉模型调用无 rate limit（每次调用消耗外部视觉模型 token，成本面 V2N3 同族） |

### model_manager.py（MM 前缀）

| 编号 | P 级 | 位置 | 描述 |
|------|------|------|------|
| MM1 | P3 | :73-77/:108/:127/:190 | list_models/get_default/list_capabilities/get_model_info 四端点无认证（匿名可浏览全模型清单含 model_key/供应商）+ **free_only 参数收而不用**（:76 声明 :78 docstring「免费模型」实际从不检查——MR2 的 API 层实锤） |
| MM2 | P3 | :142-187 | get_agent_model_config 暴露内部模型配置（roles/fallback_chain/models 全量 model_key）给任意登录用户 + :174-176 v2.0 兼容分支 MEDIUM 缺失时静默用 LARGE（语义漂移） |
| MM3 | P3 | :61/:197 | `_runtime_default_model` 模块级全局定义处（model_admin /models/default 修改的目标——V2M2 重启失效/多 worker 不同步的源头）+ :197 404 detail 泄露全模型键列表 |

## 交叉确认

- **AJP1 实锤链**：task_manager.py:231 `update_progress(task_id, progress, message)` 仅 3 参且 :237 只在 `status == RUNNING` 更新 → aiGeneratorPptx 包装层 :820/:1640/:1799 丢弃 status/result_data → run_* 全 catch 正常返回 → task_manager 内部包装（:143-176 _update_status）恒标 SUCCESS。WS 端点 :2067 按 status=="success" 推送 completed——谎报直达前端。
- **归属校验不对称**：aiGeneratorPptx 仅 cancel_ppt_task（:1101）与素材查询（:846 File.user_id 过滤）校验归属；workflow 仅 history 三端点（:606/:639/:661）过滤 user_id；knowledge 全部端点按 user_id 过滤 ✅（本轮唯一归属完备文件）。
- 与既往缺陷关联：WFA2+CE1（无沙箱执行组合）、VK2+KP1（死循环入口）、AJP5「规划功能未生效」家族、AJP6 PPT2/MAR5 家族、AJP10 GRD3/VPX3 家族、AJP13 GH2/LA7 家族、AJP14 SEC 家族、MM1 free_only=MR2、MM3=V2M2 源头、VA3=V2N3 同族、AJP8=V2C1 同族。
- **双轨盘点**：PPTAgent.generate_outline（agent/ppt_agent，:1584）vs generate_ppt_outline（本文件 :393）——两套大纲生成链并存（双轨家族 +1，PPT5 家族延伸）；三套任务入口（generate_task/generate_from_file/generate-from-text）共享同一套带缺陷的 update_progress 包装。
- PPX1（:1921 parser.parse）与 VPX1（:608-618 await 同步方法）两个「接线即崩」点均位于本文件消费侧，详档见 pptx_toolkit.md/visual_package.md。

## 测试状态

- 无针对五文件的 API 层测试（tests/ 未见 aiGeneratorPptx/workflow API/knowledge API 端点用例）。
- AJP1 状态谎报无任何用例保护；WFA1/WFA2 越权面无用例；VK2 KP1 死循环无用例。

## 修复建议

1. **AJP1（P2 优先）**：包装 update_progress 透传 status/result_data 或改用 task_manager.fail_task/cancel_task 显式 API；run_* 不要吞异常（让内部包装正确标 failed）。
2. **AJP2/WFA1/WFA2（P2）**：history 列表按 user_id 过滤（文件名前缀存 user_id 或 DB 化）；delete 校验归属；_session_workflows/_workflows 读取校验 user_id（:272 已存即用）。
3. **AJP3（P2）**：预览页 innerHTML 改 textContent 或 html.escape；HTML 导出走模板转义。
4. VK1：parse_document/chunk_text 包 `asyncio.to_thread` + 上传加 Content-Length/大小上限（对齐 AJP11 一起改）。
5. VK2：chunk_size ge=100 le=10000、chunk_overlap ge=0 lt=chunk_size（KP1 联动）。
6. WFA4：executor 完成后回写 aggregator 或直接存 executor 引用；异常路径 del _workflows 条目。
7. MM1：四端点补 verify_token 或明确公开 API 定位；free_only 落地或删参。
8. AJP12 死符号删除；AJP5 PDF 要么接 LibreOffice 链路（:1982 已有转换端点可复用）要么从枚举移除。

## 下轮候选

- app/services 16 文件（model_config_manager/resource_config/feature_switch/log_config/rate_limit_config/websocket_manager/audit_logger 等——本轮与 v2 轮的共同依赖方）
- app/schema 13 / app/models 12 / app/db 12 / app/core/middleware 4 / app/tasks 3
- v1 收尾清点（Aicode.py/GirlAi.py/kolors*/health/apikey/auth/file_upload/skills/task_queue/providers/github 已扫否需对照补扫清单）
