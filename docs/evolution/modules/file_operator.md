# file_operator.py 演化深扫文档

> 版本：v0.1 | 扫描日期：2026-08-17 | 状态：已完成
> 归属：Agent 引擎 / 路径安全文件操作层
> 路径：`app/utils/file_operator.py`（703 行）
> 索引：[TASKS.md](../TASKS.md)

## 1. 模块定位

「公共文件操作工具」——项目内文件的统一读写操作层，声明三层安全特性：
1. 禁止操作系统关键路径（/etc、/root、/proc、/sys、/var、/tmp 等，PROTECTED_PATHS）
2. 禁止敏感文件（.env、*.key、*.pem、id_rsa、.git/config 等，PROTECTED_FILES）
3. 白名单扩展名检查（SAFE_EXTENSIONS）

提供 read/write/create/delete/move/copy/list_dir/search/grep/tree/stats 及 async 变体；`_validate_path` 为统一路径安全入口。

## 2. 依赖链与消费方

**活跃消费**：
- `agent_core.py:2622`——ProjectFileManager 包装（`FileOperator(base_path=projects 目录)`，**有目录边界**）
- `multi_model_agent.py:72`——`FileOperator()` **无 base_path**（活跃 agent 另一套）
- `workflow/node_types/file_processing.py:37`——`FileOperator()` **无 base_path**
- `agent_executor.py:12`、`sandbox_operator.py:14`（SandboxFileOperator 子类，有 base_path=user_id 目录）
- `acloud.py:401/459`——SandboxFileOperator

**allow_protected_paths 生产零使用**——全库无调用传 True（默认 False）。

## 3. 发现

### FO1 [P2] PROTECTED_FILES ".env" 子串匹配误伤——项目内 .env* 文件/目录全拒（FCT3/PP8 家族，全库确认）

- **Bug 代码**：:140-142 `protected_file.lower() in abs_path_str`——PROTECTED_FILES 含 ".env"（:50）——**子串匹配**——任何路径含 ".env" 子串全拒：`/projects/myapp/.env.example`（SAFE_EXTENSIONS :59/:71 明确允许 .env/.env.example）被 :141 拦截抛 PathSecurityError——**SAFE_EXTENSIONS 白名单与 PROTECTED_FILES 黑名单对 .env 矛盾**；:147-148 的 `.env` 扩展名豁免 `if ".env" not in abs_path_str` 被 :141 前置拦截——**该豁免是死代码**。
- **影响**：LLM 生成项目含 .env.example（常见模板要求）时写入被拒；项目含 `.env_bak`/`.env.production` 路径同样被误伤——白名单/黑名单设计冲突。

### FO2 [P3] allow_protected_paths=True 可完全关闭路径防护（DGV1 潜在风险）

- **Bug 代码**：:89/:97/:101 allow_protected_paths——True 时跳过 PROTECTED_PATHS/PROTECTED_FILES 全部检查（:135-142）——注释「危险，仅用于测试」但无强制约束；生产当前零调用传 True（消费方全默认 False）——潜在误配风险（未来调用方误传即全裸）。

### FO3 [P3] 扩展名白名单仅 create 生效——write/delete/move 全 check_extension=False（安全语义不一致）

- **Bug 代码**：:272 create 默认 check_extension=True；:192 read、:234 write、:296 delete、:323/:324 move、:349/:350 copy、:383 list_dir、:586 tree 全部 check_extension=False——SAFE_EXTENSIONS 白名单实际只在 create 生效；且白名单本身超全（.env/.gitignore/.lock/.recipe/任意常见扩展名）——**扩展名检查形同虚设**（write 可写任意扩展名文件）。

### FO4 [P3] `FileOperator()` 无 base_path——黑名单制范围失控（可写 /home//opt 等非系统路径）

- **Bug 代码**：:130-131 base_path=None 时 `target = Path(path).resolve()` 无目录边界——仅受 PROTECTED_PATHS 黑名单（:135-142）限制——黑名单覆盖有限：`/home/*`、`/usr/local/`、`/opt/` 等不在列表——multi_model_agent.py:72、file_processing.py:37 用无 base_path 实例——LLM 文件工具可读写任意非系统路径（有黑名单防护但覆盖不足，区别于 AC1 完全无校验）。

### FO5 [P3] read 全量 readlines + 无文件大小上限（性能）

- **Bug 代码**：:198 `f.readlines()` 一次性读全文件——大文件（MB 级）全量入内存后分页——read 语义上只需 offset/limit 页——无大小上限保护；read_async（:671）只是 to_thread 包装（不解决内存）。

### FO6 [P3] _collect_files 隐藏目录全跳——search/grep/stats 对隐藏内容不可见

- **Bug 代码**：:164 `part.startswith('.')`——所有点开头目录/文件跳过——.github/.env.example 等隐藏内容在 search/grep/stats/list_dir 中全部不可见（与 FO1 叠加：既不可见也不可写）。

### FO7 [P3] grep/search 读文件 errors='ignore'——编码损坏内容静默丢弃

- **Bug 代码**：:482/:543 errors='ignore'——含非法字节的文件内容静默丢弃后搜索——结果不完整且无告警（EC3 家族）。

## 4. 演化方向

- **规则统一**（FO1/FO3）：.env 冲突消解——PROTECTED_FILES 改精确匹配（文件名等于 .env 而非含 ".env" 子串）+ SAFE_EXTENSIONS 保留 .env.example 白名单；扩展名白名单统一应用到 write（或移除该特性避免虚假安全感）
- **范围治理**（FO4）：无 base_path 消费方强制 base_path（multi_model_agent/file_processing 传入项目根）；PROTECTED_PATHS 扩至 /home//usr//opt/ 等或改白名单制
- **一致性**：read 改流式分页（IO 上限）；_collect_files 隐藏目录策略统一（或显式声明不扫隐藏）

## 5. 主线关联

- **路径安全三轨道**：FileOperator（本模块，活跃但规则有误 FO1/FO3/FO4）+ FileContract（FCT 详档另一套）+ guardrails.PathSecurityChecker（GRD7 零消费）——**三套路径安全各自为政**；且 AC1 的 create_project_file 完全绕过 FileOperator（四条路径安全轨道，主生成工具走最弱的一条）
- **子串误伤家族**：FO1 加入 FCT3/PP8（guardrails FORBIDDEN_PATTERNS 的 `\.(env|ini|conf|cfg)$` 同族——两处对 .env 的处理都误伤合法文件）
- **死代码豁免**：FO1 的 :147 豁免逻辑与 GC6（"id" 子串恒触发）同为规则内部矛盾
- **黑名单制**：FO4 与 GRD3/AC2 相对路径漂移同源（防护依赖部署形态）

## 6. 测试状态

- **零单元测试**：tests/ 下无 FileOperator/PathSecurityError 引用（acloud 有集成测试引用但无单元覆盖）
- FO1 .env 误伤、FO3 扩展名一致性、FO4 范围失控均无测试约束（修复建议：路径安全规则参数化测试——构造 .env.example/敏感路径/越界路径三态样本断言）

## 7. 状态更新（2026-09-19 逐条核实）

本轮按当前 master 源码复核。`file_operator.py` 位于 `app/utils/`，docstring 声明供 AIProject / Workflow / AICloud 复用，消费方含 Agent（agent_core/agent_executor/multi_model_agent）与非 Agent（workflow 节点、aicloud）——属共享基础层，非 Agent 子系统。以下改动限于共享规则，未触碰任何 Agent 代码。

### 本轮修复

- **FO1 PROTECTED_FILES 子串匹配误伤**——`_validate_path` 原以 `protected_file in abs_path_str` 子串匹配，`.env` 命中任意含该子串的路径，导致 `SAFE_EXTENSIONS` 明确允许的 `.env.example` 模板被拒、`.envrc`/`notes.env.bak` 等被误伤，且 :147 的 `.env` 豁免成为被前置拦截的死代码。修复：新增 `_is_protected_file`，含 `/` 的条目（`.git/config`）按路径尾段匹配，其余按文件全名精确匹配；扩展名豁免由全路径子串判断改为文件名白名单判断，消除矛盾。

测试：新增 `tests/unit/test_file_operator.py`（7 项，覆盖 `.env` 拒绝、`.env.example` 放行、子串路径不误伤、`.git/config`/`id_rsa` 拒绝），回退源码后 4 项失败。

### 仍开放（未改）

- **FO2 `allow_protected_paths=True` 可完全关闭防护**——生产零调用传 True，维持现状；如需收敛可加日志告警或移除开关。
- **FO3 扩展名白名单仅 create 生效**——write/delete/move 均 `check_extension=False`，且白名单本身超全，属安全语义不一致；统一需评估各消费方行为，暂缓。
- **FO4 无 base_path 实例（multi_model_agent / workflow file_processing）可越界读写非系统路径**——强制 base_path 需改 Agent 消费方（multi_model_agent）与工作流节点语义，Agent 侧不碰，暂缓。
- **FO5 read 全量 readlines、FO6 隐藏目录全跳、FO7 grep/search errors='ignore'**——性能/可见性/静默丢弃问题维持原判定，改造需专项口径。

## 8. 状态更新（2026-09-25 逐条核实）

### 本轮修复

- **FO7 grep/search 静默丢弃不可解码文件**——两处原先以 `errors='ignore'` 读取：含非法 UTF-8 字节的文件内容被静默丢弃后参与搜索，结果不完整且无任何告警（`grep` 的 `except UnicodeDecodeError` 分支因 `ignore` 永不触发，属死分支）。修复：改为严格按 UTF-8 解码；`search` 改为先累积单文件匹配、整体成功后并入结果，`UnicodeDecodeError` 时记录路径到新增的 `undecodable_files` 并整体跳过（避免半截结果），`grep` 同法记录；两者返回值新增 `undecodable_files` 列表，`agent_core` 的 `search_files`/`grep_files` 工具原样透传给 LLM，消费者可知搜索结果不完整。

测试：`tests/unit/test_file_operator.py` 新增 3 项（grep/search 记录不可解码文件、正常文件不误报），该文件共 10 项；回退源码后 3 项失败（`KeyError: 'undecodable_files'`）。

### 仍开放（未改）

- **FO2/FO4** 维持原判定（关闭开关、无 base_path 越界），均需跨消费方或专项口径。

### FO5 修复（2026-09-25）

- **FO5 [P3] 已修（内存维度）**：`read` 原 `f.readlines()` 一次性把整个文件载入内存后再切片，现改为逐行遍历、只保留目标页（`start <= idx < end`），`total_lines` 仍逐行统计但内存占用与文件大小无关；`offset` 超出总行数时仍收敛到 `total_lines`、页内容为空，返回字段语义与旧实现一致。`stats` 的 `len(f.readlines())` 一并改为 `sum(1 for _ in f)` 流式计数。
- **回归**：`tests/unit/test_file_operator.py` 新增 `TestReadStreaming`（4 项：分页语义、offset 超界收敛、read 不调用 `readlines`、stats 流式计数），回退 `file_operator.py` 后「read 不调用 readlines」项失败。该文件共 14 项。
- **FO5 剩余**：未引入文件大小上限（超限拒绝/截断属产品口径），保留待决。

### FO3 修复（2026-09-25）

- **FO3 [P3] 已修**：`write` 原先 `check_extension=False`，使 `SAFE_EXTENSIONS` 白名单只对 `create` 生效，最常见的内容写入路径可写任意扩展名。现 `write` 改为 `check_extension=True`，与 `create` 语义一致。
- **白名单补充**：既有的 `SAFE_EXTENSIONS` 缺失多种工程常用扩展名，直接对 `write` 生效会造成新的误拒（如 `go.mod`/`go.sum` 的 `.mod`/`.sum`、Gradle 的 `.gradle`/`.kts`、.NET 的 `.csproj`/`.sln`、`.pyi`/`.mjs`/`.cjs`、`.svelte`/`.astro`、`.tf`/`.proto`/`.graphql`、`.log`/`.mdx`/`.tex`/`.jsonl`/`.ipynb` 等）。一并补齐上述明显安全的文本/构建/配置扩展名；可执行/二进制/密钥类扩展名（`.exe`/`.dll`/`.so`/`.pem`/`.key` 等）保持拒绝。
- **未改动**：`delete`/`read`/`list_dir`/`tree` 不产生新文件，`move`/`copy` 目标可能是目录（扩展名语义不成立），均维持 `check_extension=False`。
- **回归**：`tests/unit/test_file_operator.py` 新增 `TestWriteExtensionWhitelist`（10 项：write 拒绝未知扩展名、放行白名单扩展名、放行无扩展名文件、`go.mod`/`go.sum`/`build.gradle`/`app.csproj`/`schema.proto`/`app.log` 经 write 与 create 双路径放行），该文件共 24 项；回退 `file_operator.py` 后「write 拒绝未知扩展名」失败，仅还原白名单时 6 项「常见工程文件」失败。

### FO6 修复（2026-09-26）

- **FO6 [P3] 已修**：`_collect_files`（search/grep/stats）、`list_dir`、`tree` 原先一律跳过 `.` 开头的目录/文件，使 `.github/`、`.gitignore`、`.env.example`、`.eslintrc` 等工程文件在遍历中全部不可见。新增 `_should_skip_entry`，只跳过显式的 `SKIP_DIRS`（`.git`/`.venv`/`node_modules` 等 VCS/构建/缓存目录）与 `PROTECTED_FILES`（`.env`/`id_rsa` 等敏感文件），其余隐藏项正常纳入。副作用是遍历结果对敏感文件更安全：此前 `search`/`grep` 直接读文件绕过 `_validate_path`，隐藏过滤是唯一屏障；现由 `PROTECTED_FILES` 显式排除 `.env`/`id_rsa`。`tree` 的 `file_count` 改为复用 `_collect_files`，与 search/grep/stats 口径一致。
- **行为变更**：`search`/`grep`/`stats`/`list_dir`/`tree` 对隐藏工程文件的可见性提升；`.env`、`id_rsa`、`.git/config` 等仍不可见（且 `node_modules` 等 SKIP_DIRS 仍跳过）。
- **回归**：`tests/unit/test_file_operator.py` 新增 `TestHiddenVisibility`（7 项：`_collect_files` 纳入隐藏工程文件、排除 SKIP_DIRS/PROTECTED_FILES、grep 可见/不可见断言、stats 计数、list_dir 顶层与递归、tree 展示与 file_count），该文件共 31 项；回退 `file_operator.py` 后 6 项失败。
