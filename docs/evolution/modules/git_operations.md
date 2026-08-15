# GitOperations 深扫（git_operations.py，346 行 + snapshot_manager.py 213 行）

> 第九十三轮推演 | 2026-08-15 | 定位：Agent 项目快照系统（分支 + 提交 + 标签 + 回滚），快照链路活跃接线但核心语义多处失真

## 1. 模块定位

Agent 生成链的快照基础设施：`GitOperations`（裸 git 子进程封装，分支管理/提交/标签/回滚/列表/差异）+ `SnapshotManager`（快照业务编排：保存/回滚/会话结束合并）。**活跃生产模块**，消费方 4 处：

- `app/agent/orchestrator.py:106-109`：OrchestratorAgent 实例化 `git_ops + snapshot_mgr`（但仅用于传递，本文件不直接调用快照方法）
- `app/agent/orchestrator_utils.py:339-347`：`_git_save_snapshot` → 每次生成结束（`traditional_generate.py:338`）调 `snapshot_mgr.save_snapshot`
- `app/api/v1/ai_agent/orchestrate_endpoints.py:1179-1243`：`list_snapshots` / `rollback_to_snapshot` / `diff_snapshots` 三个快照端点（每次请求新建 GitOperations + SnapshotManager）
- `app/agent/snapshot_manager.py`：GitOperations 业务编排层（save_snapshot 流程 = init_repo → get_current_branch → create_branch → commit_snapshot → create_tag）

### 依赖链

| 方向 | 模块/位置 | 说明 |
|------|-----------|------|
| 被消费 | `orchestrator_utils.py:339-347` | `_git_save_snapshot` → `save_snapshot`，生成链活跃接线（传统链路每次生成结束保存快照） |
| 被消费 | `orchestrate_endpoints.py:1204-1216` | `rollback_to_snapshot`（默认 `delete_branch=True`） |
| 被消费 | `orchestrate_endpoints.py:1179-1190` | `list_snapshots`（git tag 列表 + 每 tag 查 commit） |
| 被消费 | `orchestrate_endpoints.py:1233-1241` | `diff_snapshots`（git diff 两 tag，返回截断 5000 字符） |
| 未消费 | `SnapshotManager.finalize_session`（:162-213） | **全库零调用方**（grep 确认：只定义 + FinalizeResult import，无任何生产调用） |
| 未消费 | `GitOperations.get_head_commit`（:331-346） | **全库零调用方**（孤儿方法） |
| 测试 | **零测试覆盖**（tests/unit/test_v4_8_features.py:336-351 仅测 `SnapshotInfo` dataclass 构造） | |

## 2. 深扫发现

### P2 项

- **GO1 [P2] `--allow-empty` 使「无变更跳过」永不触发，每次生成都产生空提交（实测）**——`commit_snapshot` 用 `git commit --allow-empty`（git_operations.py:132），实测无任何变更时连续两次提交返回**不同 hash**（h1≠h2，均创建空提交）→ `:137-139` 的「无变更或失败返回 None」分支只对失败生效，对无变更永不触发 → `save_snapshot` 中 `if not commit_hash: "无变更需要提交" return None`（snapshot_manager.py:98-100）**成为死分支**。传统链路每次生成结束（`_git_save_snapshot`）无论是否有文件变更都产出空提交 + tag，git 历史被垃圾提交污染，快照列表含大量空快照。
- **GO2 [P2] rollback 后删除当前分支永远失败（实测）**——`rollback_to_snapshot` 的 `revert_to_commit` 用 `git reset --hard`（:240）回滚后，当前分支仍是 feature 分支（reset 只移动当前分支指针，不切换分支）；`if delete_branch and current_branch != "main": delete_branch(current_branch)`（:152-153）尝试删除**当前检出的分支**——git 明确禁止删除当前分支（实测 `git branch -D feature2` 返回 False）→ **默认 `delete_branch=True` 的分支清理永远失败且失败被静默忽略**（:153 不检查返回）。快照分支永久残留。rollback 端点暴露给外部用户（任意 session_id + target_tag），误调还叠加 GO13 破坏性。
- **GO7 [P2] rollback 结果谎报 `current_tag="main"` + files_restored 语义错位（实测）**——`rollback_to_snapshot` 恒返回 `current_tag="main"`（:158），但回滚后实际仍在 feature 分支（实测：回滚到快照后 `git branch --show-current` = feature2，与返回的 "main" 不符）→ 端点响应 `current_tag` 误导前端。且 `files_restored=snapshot.files_changed`（:159）用的是**保存时的内存变更列表**（`orchestrator_utils:343` 传的是恒空 `files_changed=[]`），而非 git 实际恢复的文件——回滚成功但恢复文件列表恒空。

### P3 项

- **GO3 [P3] `get_current_branch` 非 git 仓库谎报 "main"（实测）**——`git branch --show-current` 在非 git 目录返回空 stdout，`result.stdout.decode().strip() or "main"`（:323）→ 返回 "main"。snapshot_manager:83/:150 用该值判断是否建分支/删分支——在 git init 失败的目录下（GO9）谎报 main 使分支语义判断全部失真。
- **GO4 [P3] `get_head_commit` 无提交仓库返回字面量 "HEAD"（实测）**——`git rev-parse HEAD` 在无提交仓库输出 `HEAD`（exit 1），直接 `stdout.strip()` 返回 "HEAD" 而非 hash。当前零调用方（孤儿方法），一旦被消费会在无提交仓库返回无效值。
- **GO5 [P3] `list_snapshots` 用 `|` 分隔符解析 commit message 截断（实测）**——`git log --format=%H|%s|%ci`（:271）+ `split("|")`（:276）。实测 message 含 `|` 时（`msg with | pipe`）parts 拆坏，`parts[1]` 截断为 `msg with `（`:279` message 取第一个 `|` 前）——commit message 是快照描述（用户需求文本），含 `|` 的描述在快照列表中被截断。
- **GO6 [P3] 分支已存在时 create_branch 返回 None → save_snapshot 静默 commit 到错误分支**——`git checkout -b name` 若 name 已存在返回非 0 → 返回 None（:93-95）；save_snapshot 只打 warning（:86-87）后**继续 commit 到当前分支**（不在 branch_name 分支上）——「声明的分支」与实际提交分支不一致。当前生产调用（`_git_save_snapshot`）不传 branch_name 未触发，但该路径一旦启用即分支语义失效。
- **GO8 [P3] `finalize_session` 全库零调用方（能力未接线，方法级）**——docstring 声称「会话结束自动合并 feature 到 main + 创建最终标签 + 提议回滚」（:169-183），全库无任何调用方。「成功合并 / 失败提议回滚」的会话结束能力从未接线，与 GO2 的分支残留叠加使 feature 分支生命周期无收口。
- **GO9 [P3] `init_repo` 的 `git init` returncode 不检查 + 谎报成功路径**——`_init` 中 `git init` 子进程 returncode 被忽略（:46-51），只要 `.gitignore` 写入成功即返回 True——git init 因配置/权限失败但 gitignore 可写时谎报成功（路径不存在时 write_text 抛异常被 :61-63 兜住返回 False，实测确认，但「init 失败 + gitignore 成功」路径仍返回 True）。
- **GO10 [P3] `commit_snapshot` 的 `git add -A` returncode 不检查**——add 失败（非 git 目录/权限）后仍执行 commit，靠 commit 失败兜底返回 None——错误面依赖 commit 而非 add，日志信息失真。
- **GO11 [P3] `merge_branch` 的 `git checkout target` returncode 不检查**——target（默认 main）分支不存在时 checkout 失败仍执行 `git merge branch`，可能 merge 到错误分支或失败；与 GO2/GO6 同属「子进程 returncode 选择性忽略」家族。
- **GO12 [P3] `revert_to_commit` 用 `reset --hard` 无备份无确认**——`git reset --hard`（:240）直接丢弃工作区全部未提交变更，无备份、无确认、返回前不告知。作为回滚端点（外部暴露）的底层，任何误调/参数错误都不可恢复（代码被回滚为项目数据，reset 丢失的工作无还原路径）。

## 3. 演化方向

快照系统是 Agent 生成链的版本管理底座，但**「保存」与「回滚」两侧语义都失真**：
- **保存侧（GO1）**：`--allow-empty` 使空提交常态化，快照失去「有变更」语义，历史与快照列表被垃圾提交/空快照稀释。修复方向：去掉 `--allow-empty`，让「无变更返回 None」真实生效（`save_snapshot` 的 dead branch 复活）；或保留 allow-empty 但显式表达「每次生成都建快照」的意图并让调用方理解。
- **回滚侧（GO2/GO7/GO12）**：删除当前分支失败 + current_tag 谎报 main + files_restored 恒空 + reset --hard 破坏性——回滚端点是外部暴露的核心能力，当前行为（回滚后分支残留、前端看到错误的 main、恢复文件列表为空）与用户预期严重不符。修复方向：回滚前先 `checkout main`（或至少切换到非目标分支）再删分支；current_tag 用实际分支；files_restored 用 git diff 统计真实恢复文件。
- **收口侧（GO8）**：`finalize_session`（会话结束合并）从未接线，feature 分支生命周期无收口——与 GO2 的分支残留同源，接线 finalize 需先解决「删除当前分支」与「checkout main」的先后问题。
- **边界侧（GO9/GO10/GO11）**：三个子进程 returncode 选择性忽略，错误路径依赖兜底而非显式处理——非 git 项目（`user_uploads/{session_id}` 上传目录）在快照链路下行为不可控。

**修复优先级**：GO1（空提交污染）> GO2（删除分支失败 + 分支残留）> GO7（回滚结果谎报）> GO12（reset 破坏性）> GO8（finalize 未接线）> GO3/GO9（非 git 边界）> GO4-GO6/GO10/GO11（设计瑕疵）。

## 4. 主线关联

- **「子进程 returncode 选择性忽略」家族**：GO9/GO10/GO11 与 OU9（裸 git 实现同源）、SC 家族、CLH 家族同族——同一项目内**两套 git 快照实现**（`orchestrator_utils._git_save_snapshot` 的裸 git vs `git_operations` 封装）并存，且两处都用了 `--allow-empty`，是「同一能力双实现」收敛对象。
- **「能力未接线」家族**：GO8（finalize_session 零调用）与 UPL1/SL1/FPC1/SCT5/GC6 同族——本模块保存/回滚活跃、会话结束合并死代码，同一模块内活跃与未接线并存。
- **「存在≠正确」验证语义主线**：GO7（回滚返回成功但 files_restored 恒空、current_tag 谎报）——**「报告成功」与「实际结果」分离**的又一实例（与 OP1 成本恒零、TR1 无测试=通过、JP2 截断补全同族）：端点用户看到 `success=True` 但恢复文件列表为空、当前分支与返回不符。
- **数据安全主线**：GO12（reset --hard 无备份）与 OF2（回滚写安全）、CP1（LLM 幻觉补丁破坏代码）同族——快照回滚是最底层的数据破坏面。

## 5. 测试状态

**零测试覆盖**——tests/unit/test_v4_8_features.py:336-351 仅测 `SnapshotInfo` dataclass 构造（3 个字段赋值断言），无任何 GitOperations/SnapshotManager 方法用例。GO1/GO2/GO3/GO4/GO5/GO7 全部实测可复现但无用例保护。快照链路（保存 → 回滚 → 删除分支）是生成链的版本管理底座，端到端无任何回归保护，且 `--allow-empty` 的空提交行为从未被测试暴露。
