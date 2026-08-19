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
