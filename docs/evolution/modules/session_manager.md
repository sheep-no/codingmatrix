# SessionManager 演化深扫文档

> 版本：v0.1 | 扫描日期：2026-08-09 | 状态：已完成
> 归属：Agent 大系统 / 支撑模块（会话管理）
> 路径：app/agent/session_manager.py（582 行）
> 索引：[TASKS.md](../TASKS.md)

## 1. 模块作用与功能

会话管理器：会话状态持久化（断点续传）、增量生成（detect_incremental_changes）、文件级 Embedding 增量检测、人机协作暂停/恢复、DB 写透同步。docstring 声称「DB 为唯一真相源，SM 为写透缓存」。

- **数据类**：`SessionStatus`（:37 Enum）、`FileStatus`（:47）、`SessionState`（:58，含 approval_queue :98、to_dict/from_dict :104/:110）。
- **核心类**：`SessionManager`（:123）。方法：create_session（:165）、resume_session（:197）、update_file_status（:236）、pause_session（:269）、resume_from_pause（:286）、complete_session（:306）、cancel_session（:325）、_get_state（:339）、cleanup_expired（:348）、cleanup_if_needed（:392）、get_session_status（:415）、detect_incremental_changes（:447）、get_file_plan_for_incremental（:541）、_compute_hash（:552）、_compute_embedding_similarity（:557）、_session_file（:561）、_save_session（:566 原子写）。
- **常量**：SESSION_DIR=./sessions（:30 相对 CWD）、TTL 30 天（:32）、MAX_ACTIVE_SESSIONS=500（:34）。

## 2. 依赖与被依赖

- **生产使用方**（3 处）：orchestrator_generation/traditional_generate.py:124/:126/:134（resume/create_session）、orchestrator_generation/incremental_generate.py（detect_incremental_changes/get_file_plan_for_incremental）、app/api/v1/ai_agent/helpers.py:242-244（`SessionManager(db_session_factory=async_session)`）。orchestrator.py:15/:55/:87-88 注入。
- **关键事实**：**`update_file_status` 全库零调用**（:236 无任何生产消费方）——file_statuses 的 content_hash/content_embedding 从未被更新。
- **测试覆盖**：tests/unit 无 session_manager 独立测试（补扫对象；需确认 tests 全量，见 §5）。

## 3. 已探明 Bug

### SM14 [P2] 小变更文件在 `state.unchanged_files` 重复（实测 `['a.py','a.py']`）

- **Bug 代码**：

```python
# :512-525 - 小变更文件先进 unchanged，又进 small_changes，:525 再拼一次
if similarity > 0.95:
    small_changes.append(file_path)
    unchanged.append(file_path)      # :515 已进 unchanged
    continue
state.changed_files = changed
state.unchanged_files = unchanged + small_changes    # :525 又拼 small_changes → 重复
```

- **根因**：:515 小变更文件同时 append 进 `unchanged` 和 `small_changes`，:525 `unchanged + small_changes` 再拼一遍 → 小变更文件在 state.unchanged_files 出现两次。语义上 unchanged 与 small_changes 集合本就重叠（small 是 unchanged 子集），拼接必然重复。
- **影响**：实测 embedding 分支触发时 `state.unchanged_files = ['a.py','a.py']`；消费方（get_file_plan_for_incremental 只看 changed_files，暂未受损）与外部读 state.unchanged_files 的接口拿到重复列表。
- **验证方式**：实测（见 §5）。

### SM2/SM3 [P2] 增量检测复用能力从未生效：update_file_status 零消费 + embedding 恒空

- **Bug 代码**：

```python
# :252-259 - update_file_status 只写 status/last_modified/error/hash，不写 content_embedding
fs.status = status
fs.last_modified = datetime.now().isoformat()
if content:
    fs.content_hash = self._compute_hash(content)   # :258 依赖调用方传 content
# :500 - detect_incremental_changes 靠 fs.content_hash 判复用
if fs and fs.status == "completed" and fs.content_hash and fs.content_hash == current_hash:
# :508 - 靠 fs.content_embedding 判语义复用
if (file_embeddings and file_path in file_embeddings and
        fs and fs.content_embedding is not None):
```

- **根因**：`update_file_status`（:236）**全库零调用** → fs.content_hash 恒空（create_session 初始 FileStatus 无 hash）、fs.content_embedding 恒 None（update_file_status 从不写此字段）。detect_incremental_changes :500（hash 复用判断）与 :508（embedding 语义复用）**恒 False** → 所有已存在文件恒判 `changed`。docstring（:457-459）声称的「文件级 Embedding 增量检测（量化变更幅度，小改动跳过）」是死能力；embedding 分支只在手工设置字段时可达（实测）。
- **影响**：断点续传/增量生成的「复用已生成文件」从未生效，每次增量全部重新生成。且 `update_file_status` 本身死代码（唯一会写 hash 的路径不可达）。
- **验证方式**：实测 embedding 分支仅手工设字段可达 + `update_file_status` 全库零消费（代码级）。

### SM10 [P2] DB 唯一真相源声明 vs 实际不同步面（create/pause/resume/update 不写 DB）

- **Bug 代码**：

```python
# :124 docstring - DB 为唯一真相源，SM 为写透缓存
# :190-194 - create_session 只存内存+磁盘，不 _sync_to_db
async with self._lock:
    self._active_sessions[session_id] = state
await self._save_session(state)
# _sync_to_db 只在 :323 complete / :330,:337 cancel / :374-384 cleanup 调用
```

- **根因**：`_sync_to_db`（:134）仅 complete_session（:323）/cancel_session（:330/:337）/cleanup_expired（:374-384）调用。**create_session、pause_session、resume_from_pause、update_file_status 均不写 DB**——「DB 为唯一真相源」声明与实际不同步面矛盾。DB 会话记录创建依赖 API 层，暂停/恢复/文件状态 DB 完全不知情。
- **影响**：DB 状态与 SM 状态不一致（DB 看不到暂停、看不到文件进度）；前端查 DB 获取的会话状态滞后。

### SM4 [P3] `detect_incremental_changes` 读文件无异常处理

- **Bug 代码**：

```python
# :494-496 - 磁盘文件读取无 try
if full_path.exists():
    with open(full_path, 'r', encoding='utf-8') as f:
        content = f.read()
```

- **根因**：文件损坏/权限异常时 open/read 异常向上抛，调用方（incremental_generate）无兜底，增量检测中断。
- **影响**：单个文件读失败导致整个增量检测失败。

### SM1 [P3] `asyncio.Queue` 在 dataclass + 跨事件循环风险

- **Bug 代码**：

```python
# :98 - asyncio.Queue 作为 dataclass 字段
_approval_queue: asyncio.Queue = field(default_factory=asyncio.Queue, repr=False)
# :106 - to_dict 排除 _ 前缀（Queue 不序列化）；:113 from_dict 重建
```

- **根因**：asyncio.Queue 绑定创建时的事件循环（3.10+ 惰性绑定到首次使用），SessionState 跨请求/事件循环复用 approval_queue 有 RuntimeError 风险。序列化时被排除（正确），但运行时契约依赖单循环。
- **影响**：多事件循环（FastAPI 多 worker）共享 SessionManager 时队列操作崩溃风险。

### SM9 [P3] `create_session` 默认 session_id 时间戳秒级冲突

- **Bug 代码**：

```python
# :174-175 - 同秒创建两个会话 ID 相同，后一个覆盖前一个
if not session_id:
    session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
```

- **根因**：秒级时间戳作默认 ID，同秒并发创建会话冲突，后写覆盖先写（_active_sessions dict key 覆盖 + 磁盘文件覆盖）。
- **影响**：并发创建会话丢失状态。

### SM8 [P3] `SESSION_DIR = Path("./sessions")` 相对 CWD

- **Bug 代码**：

```python
# :30 - 相对路径，进程 CWD 变化则会话目录漂移
SESSION_DIR = Path("./sessions")
```

- **根因**：会话存储目录基于 CWD 相对路径，进程工作目录变化（如部署切换目录）时会话文件散落多处。
- **影响**：断点续传跨进程/跨部署失效；残留会话文件。

### SM11 [P3] 两套 DB 访问方式并存

- **Bug 代码**：

```python
# :141 - _sync_to_db 用注入的 factory
async with self._db_session_factory() as db:
# :370 - cleanup_expired 直接 import 全局 async_session
from app.db.database import async_session
```

- **根因**：同一文件两套 DB 会话获取方式（注入 factory vs 全局 import），cleanup_expired 绕过注入直接依赖全局，测试/隔离场景下行为不一致。
- **影响**：DB 访问契约分裂；cleanup 路径不受注入控制。

### SM13 [P3] `get_session_status` 返回不含 hash/embedding，增量检测信息不可见

- **Bug 代码**：

```python
# :437-444 - files 只暴露 status/last_modified/error
"files": {path: {"status": fs.status, "last_modified": fs.last_modified, "error": fs.error} ...}
```

- **根因**：状态接口不含 content_hash/content_embedding，前端/消费方无法感知文件复用判定依据（与 SM2/SM3 死能力呼应）。
- **影响**：增量检测的「哪些文件复用/为何复用」对外不可观测。

## 4. 修复建议

- **SM14**：:525 改为 `state.unchanged_files = unchanged`（small_changes 本就是 unchanged 子集，无需拼接）；或语义上把 small_changes 独立于 unchanged（不互相 append）。
- **SM2/SM3**：接线 update_file_status（incremental_generate 生成后调用并传 content）；embedding 复用需明确「谁算 embedding、存哪」（当前 file_embeddings 参数来源不明）；或删除 embedding 死能力改纯 hash 复用。
- **SM10**：create/pause/resume/update 也调 `_sync_to_db`（DB 状态字段扩展），或修正 docstring 声明为「SM 为真相源、DB 为展示视图」。
- **SM4**：文件读取加 try/except，单文件失败降级为 changed 而非中断。
- **SM1**：approval_queue 移出 dataclass（属性级，构造后设置）；或限定单事件循环使用。
- **SM9**：session_id 加 uuid 后缀/纳秒。
- **SM8**：SESSION_DIR 用绝对路径/配置注入。
- **SM11**：统一走 `_db_session_factory`。
- **SM13**：状态接口补 hash/embedding 字段。

## 5. 待实测项

- SM14 已实测（embedding 分支 `state.unchanged_files = ['a.py','a.py']` 重复）。
- SM2/SM3 已实测（embedding 分支仅手工设字段可达；update_file_status 零消费为代码级确凿）。
- SM10/SM4/SM1/SM9/SM8/SM11/SM13 为代码级结论。
