# 提交 API 流程合扫（github.py 保存/提交流程 + aicloud.py 审批提交流程）

> 第一百四十轮补扫 | v1.141 | 2026-08-24 | 分析对象：`app/api/v1/github.py`（260 行，首次深扫）+ `app/api/v1/aicloud.py` 审查提交链（`/read` :382-441 → `/write` :444-507 → `/reviews` :621-712）+ 依赖 `app/utils/aicloud/review_queue.py`（242 行）、`sandbox_operator.py`（146 行）、`app/schema/aicloud.py`、`app/models/aicloud.py`
>
> 结论：**github.py「保存/提交」链存在任意路径写入（project_name 路径穿越）、git 子进程无超时、token 经异常/日志泄露、config 端点为假存储；aicloud 审批链在第一百三十八轮 RQ1 基础上确认仍在 + 新增 approve 无 pending 状态校验、read 审查批准空转、write 端点缺保护路径检查**。

## 一、两条提交流程定位

| 流程 | 端点 | 链路 | 接线状态 |
|------|------|------|----------|
| GitHub 提交 | POST `/github/save` | `save_project_to_github`（:72）→ `use_github=True` 走 `_save_to_github`（:103，临时目录→git init/add/commit→httpx 建仓库→push main）/ `False` 走 `_save_to_local_git`（:186，`projects/{user_id}/`→备份→写文件→git init/add/commit） | 活跃，无沙箱 |
| GitHub 配置 | POST/GET `/github/config`（:49/:242） | `set_github_config` **假存储**（:63-64 注释「可以存储…目前只返回确认信息」）；`get_github_config` 恒返回空默认（:257-260） | **零持久化——配置从未保存** |
| 审批提交 | POST `/aicloud/write` | `write_file`（:444）→ `ensure_user_sandbox` → `SandboxFileOperator.write_with_review`（auto_approve 恒不可达，SO1）→ `create_review` 入库原文（:484）→ 返回 pending | 活跃 |
| 审批读取 | POST `/aicloud/read` | `read_file`（:382）→ `read_with_review` → ai 未过 + require_review → `create_review`（operation_type="read"，:417） | 活跃 |
| 审批动作 | GET `/reviews` / POST `/reviews/approve` / `/reviews/reject` | `get_reviews`（:621 无 user 过滤）→ `approve_review`（review_queue.py:85，**无 pending 校验**）→ 若 write 直接 `open(file_path,"w")` 写回（:683） | 活跃 |

### 依赖链

| 方向 | 模块/位置 | 说明 |
|------|-----------|------|
| 被消费 | `review_queue.create_review` :21 | write/read 端点真实消费（内容入库原文） |
| 被消费 | `review_queue.approve_review/reject_review` :85/:115 | approve/reject 端点真实消费（无状态守卫） |
| 被消费 | `sandbox_operator.write_with_review` :111 | write 端点真实消费（auto_approve 分支死，SO1） |
| 未消费 | `review_queue.get_pending_reviews` :173 | **get_reviews 端点自建 query 不走库函数**（第一百三十八轮 RQ2 已记） |
| 未消费 | `review_queue.process_review_request` :200 / `get_user_review_preferences` :152 | 全库零调用（第一百三十八轮 RQ2 已记） |
| 未消费 | `/github/config` 存储 | **GET/POST 两端均无 DB/会话持久化——纯空壳** |

## 二、缺陷清单

### P2（7 项）

- **GH1 [P2] `_save_to_local_git` project_name 路径穿越——任意目录/文件写入**——github.py:193 `project_path = projects_dir / request.project_name`——`project_name` 为请求字段无任何清洗——`project_name="../../../tmp/evil"` → `project_path.resolve()` = `/tmp/evil`（:210 的 startswith 校验对比的正是穿越后的基路径，**穿越本身不受拦截**）→ 文件写入 `/tmp/evil/` 任意位置、`project_path.rename` 备份（:199）移动任意目录——**任意用户可向服务器文件系统写任意内容**（进程权限内）。`_save_to_github` 同构（:108 `temp_dir / project_name`）但因 tempdir 深度使穿越范围受限（:117-119 校验同样仅对 tempdir 内生效）。**与 RQ1/SO2 同族：校验点在校验后行为，缺少「基路径本身受控」前置约束**。
- **GH2 [P2] git 子进程全部无 timeout——网络挂起无界**——github.py:125-132/:162-165/:217-224 共 8 处 `subprocess.run(check=True)` 无 `timeout=`——`git push`（:164）对慢/不可达网络可永久阻塞——请求挂起占满 worker（LA7/OT 无超时家族）。
- **GH3 [P2] token 经异常消息与日志泄露**——github.py:161 `remote_url = f"https://{username}:{token}@github.com/..."` 把 PAT 嵌入 URL——`git push` 失败时 `CalledProcessError` 的 `str(e)` 含完整命令行（含 token），被 :180 `logger.error(f"Git 操作失败: {e}")` 写入日志，且 :181/:184 HTTPException detail 也回传 `str(e)`（token 进响应体）——**PAT 泄露至日志 + 客户端**。正确做法：token 走 `credential.helper` 或 URL 用占位符、异常脱敏。
- **GH4 [P2] `startswith` 前缀碰撞绕过路径校验**——github.py:118/:210 `str(full_path).startswith(str(project_path.resolve()))`——字符串前缀而非 `is_relative_to`——`project_path=/tmp/foo` 时 `/tmp/foobar/x` 也通过（配合 GH1 project_name 穿越使基路径可越界）——与 `_validate_path` 的 `startswith(base + os.sep)`（file_operator.py:128，SB1 家族）同类但**更宽松（无 os.sep 边界）**。
- **GH5 [P2] approve 无 `pending` 状态校验——可重复审批/审批已拒绝记录**——review_queue.py:105-107 无条件置 `approved`——approve_review_endpoint（aicloud.py:660）与 reject（:694）均不检查 `review.status == "pending"`——已批准/已拒绝的 review 可再次批准（状态机无守卫）；配合 RQ1 跨用户审批（不校验 `requested_by == user_id`）放大：**任意用户可反复批准同一审查、覆盖他人审批结果**（跨用户越权家族，RQ1 更新）。
- **GH6 [P2] approve 写文件 `open()` 直接写 + TOCTOU/symlink**——aicloud.py:683 `open(review.file_path,"w")` 绕过 SandboxFileOperator 与 `is_protected_path`——`file_path` 是 create 时存入的绝对路径（沙箱内）——但 approve 时刻与 create 时刻之间**文件系统状态可被篡改**：沙箱内文件可被替换为 symlink（CE2 代码执行可创建）→ approve 沿 symlink 写出沙箱；且 write 端点只校验 `base_path` 内（GH 基线），approve 用裸 `open()` 无任何解析。**审批写回路径完全脱离沙箱校验体系**（RQ1 :683 同位置，本轮从 TOCTOU/symlink 维度补充）。
- **GH7 [P2] `/github/config` 假存储——「保存配置」从未兑现**——github.py:63-64 注释自认「目前只返回确认信息」——POST 不写 DB/会话，GET :257-260 恒返回空默认——`save_project_to_github` 每次从请求体现取 `github_config`（:90/:94）从不读已存配置——**config 端点纯空壳，前端「保存配置」产生成功假象**（「规划功能未生效」家族 +1，ADP1 同族）。

### P3（5 项）

- **GH8 [P3] `project_data` json.loads 无大小/结构限制**——github.py:113/:205——大 JSON 字符串全量解包 + 逐个写盘——超大 project_data 内存/磁盘 DoS（无 FileWriteRequest 侧的大小校验可比）。**且 json.loads 失败 → :99-101 统一 500**。
- **GH9 [P3] git commit 无 `--allow-empty` 也无变更检查**——github.py:131/:223——`project_data` 空对象或全空文件时 commit 直接失败 → CalledProcessError → 500（与 git_operations.py GO1 `--allow-empty` 反义：那边空提交泛滥、这边空项目提交失败，两套 git 封装行为分裂）。
- **GH10 [P3] 三套 git 封装并存**——github.py 内嵌 subprocess 一套 + git_operations.py 一套 + orchestrator_utils._git_save_snapshot 又一套——**git 操作三实现、提交消息/分支名/空提交语义互不一致**（SERVICES-EVOLUTION H9「与 git_operations 统一」目标未落地，**双轨家族第 22 处**）。
- **GH11 [P3] read 类型审查批准空转**——`create_review(operation_type="read")`（:417）入队后——approve 端点 :678 `if review.operation_type == "write"` 只对 write 写文件——**read 审查批准后无任何动作**（文件早已返回给请求者、审核只是事后记录）——审查流程对 read 仅产生噪音记录。
- **GH12 [P3] write 端点缺保护路径检查（与 read 不对称）**——read_file :395 有 `is_protected_path/is_protected_file` 前置拦截，write_file :444-457 **只有 `ensure_user_sandbox` 无 is_protected_path**——写入保护依赖 SandboxFileOperator._validate_path 的 `PROTECTED_PATHS`（sandbox_operator.py:24-27 自维护清单）——同一套保护逻辑在 read/write 两处实现不一致（SB4 已记双份清单，本轮确认 write 侧额外缺失端点层检查）。

## 三、全库交叉确认

- **提交链双流程均无 SSRF**：`_save_to_github` 的 httpx 请求（:147-152）host 固定 `api.github.com`、push 的 remote host 固定 github.com——不构成新服务端外连面（对比 PAPI2/CE3）。
- **审批链用户隔离缺口闭合确认**：`get_reviews`（:634-637）只按 status 过滤无 `user_id`——全站待审队列可见（RQ1 原记录）；approve/reject 不校验 `review.requested_by == user_id`（RQ1）；本轮新增 GH5（无 pending 守卫）与 GH6（TOCTOU/symlink）使审批链「越权 + 状态机失控 + 写出沙箱」三缺口并存。
- **与第一百三十八轮衔接**：SO1（auto_approve 恒不可达）使 write 端点**永远走 create_review pending 分支**（:484-507），故 approve 的 `open()` 写回（:683）是 write 内容的**唯一落盘路径**——GH6 因此是 write 链安全的关键闸门（现为裸 open）。
- **「规划功能未生效」家族累计**：GC2/PM2/TDC1/LLM2/CON1/DT1/CI1/SO1/KP2/ADP1/**GH7**。
- **跨用户越权家族**：RQ1（审批无归属校验）+ GH5（重复审批）——与 PAPI1/CS 越权同根因（用户归属数据无隔离校验）。
- **双轨家族第 22 处**：GH10（三套 git 封装）。

## 四、测试状态

零单元测试（github.py 与 aicloud 审批端点均无 tests/unit 覆盖）。GH1（路径穿越）、GH2（无 timeout）、GH3（token 泄露）、GH5（重复审批）、GH6（approve 裸写）全部实码可证。修复建议：① GH1 对 `project_name` 做 `Path` 基路径白名单（只允许单段名称）+ 改用 `is_relative_to`；② GH2 所有 `subprocess.run` 加 `timeout=`；③ GH3 token 不嵌入 URL、异常/日志脱敏；④ GH5 approve/reject 前校验 `status=="pending"`；⑤ GH6 approve 写回改走 SandboxFileOperator + realpath 解析 + 归属校验；⑥ GH7 删除 config 空壳或落地真实持久化；⑦ GH10 三套 git 封装收敛到 git_operations.py；⑧ GH12 read/write 统一保护路径检查；⑨ 下轮转 `app/api/v1/ai_agent/`（orchestrate_endpoints.py 1243 行等）或 `validators/` 5 文件。
