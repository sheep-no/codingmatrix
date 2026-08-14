# Utils 演化详档

- 文件：`app/agent/utils.py`（1383 行）
- 扫描日期：2026-08-09
- 状态：✅ 已完成
- 模块定位：Agent 公共工具层——代码提取、内容有效性、沙箱验证、占位符检测、原子写入。**全库最广共享层（51 个文件消费）**

## 职责

1. `clean_code_block`（:13）/`extract_engineer_content`（:39-174）：LLM 输出 → 最终文件内容的三路提取（工具编辑/编辑标记/完整内容）
2. `is_valid_code_content`（:243）/`validate_syntax_for_extension`（:303）：内容有效性 + 快速语法
3. SandboxValidator 族（:365-751）：Python/JS/Go/Rust/Generic 按扩展名验证器，`validate_in_sandbox`（:884-978）bwrap 执行
4. `validate_language_with_llm`（:1028）：LLM 语言检测
5. `is_placeholder_content`（:1074）：占位符检测
6. `write_file_atomic`（:1165）：原子写入 + 占位符拦截
7. `validate_content_quality`（:1205）：LLM 思考泄漏检测

## 消费方（51 文件，核心生成链路全覆盖）

- `spec_first_generate.py`/`traditional_generate.py`/`incremental_modify.py`：生成主链路高频调用 validate_in_sandbox / write_file_atomic / extract_engineer_content / is_valid_code_content
- `cross_validator.py`/`refinement_loop.py`/`spec_first_generator.py`：clean_code_block 修复链
- `orchestrator_files.py`：文件编排出口统一走 write_file_atomic
- `backend_engineer.py`/`frontend_engineer.py`：get_expected_language_for_file
- 测试状态：**零单元测试**（tests/unit 无对应文件）

## 实测确认的 bug

### UT5 [P2] 沙箱验证失效静默通过——bwrap 缺失/超时一律判「通过」

- 位置：:973-978
- 实测（本环境）：`shutil.which("bwrap")` = None → `validate_in_sandbox("", {"x.py": "print('hi')"}, level="syntax")` → **返回 `(True, [])`**——bwrap 不存在时 FileNotFoundError 被 :976-978 except 捕获 → 静默通过。超时（:973-975）同样返回 True
- 影响：**在无 bwrap 环境（如本开发环境）沙箱验证从未真正执行，所有生成链路的 sandbox_ok 恒 True**——spec_first_generate/traditional_generate 的语法/导入验证全部空转。「存在≠正确」主线在验证执行端的又一确认
- 修复方向：bwrap 缺失必须显式降级（返回可辨识状态或记录验证缺失），不能让调用方误以为已验证

### UT10 [P2] LLM 语言检测 "NO" 子串假阳性——"Note:..." 误拒合法代码

- 位置：:1066 `if result and "NO" in result.upper()`
- 实测：LLM 回答 `"Note: this is Python code"`（内容确为 Python）→ `"NO" in "NOTE:..."` → "NO" 命中 "NOTE" 前两位 → 误判「语言不匹配」→ extract_engineer_content :100-102 返回 None → 触发调用方恢复流程（重生成/修复），**对合法代码做无效重试**
- 修复方向：整词匹配（`re.search(r'\bNO\b', ...)`）或解析首词

### UT6 [P2] `_generate_script_with_ai` 在 async 上下文调用协程 LLM 必抛

- 位置：:862-865 `asyncio.get_event_loop().run_until_complete(llm_caller(prompt))`
- 事实：若 llm_caller 是协程函数且本函数在运行中的事件循环内被调用（本库全 async），`get_event_loop()` 返回当前 loop、`run_until_complete` 在 loop 已运行时抛 `RuntimeError: This event loop is already running` → 捕获后降级通用验证器
- 影响：未注册扩展名的 AI 验证脚本生成在 async 上下文恒降级为 GenericSandboxValidator（括号匹配）

## 其余发现

### UT14 [P3] JS/Go/Rust 验证器忽略 level——import/run 等价 syntax

- 位置：JavaScriptSandboxValidator :571（只 node --check）、GoSandboxValidator :622（只 go vet）、RustSandboxValidator :673（只 rustc --check）
- 影响：非 Python 语言的 import/run 级别验证等于 syntax，`validate_project_in_sandbox`（import 级）对 JS 项目无跨文件验证——与 FD1/OP3 JS 系判定失效同主线

### UT7 [P3] GenericSandboxValidator 括号匹配无意义 + run 级执行任意代码

- 位置：:741-743 括号计数（引号/注释内括号也计）；:472-557 PythonSandboxValidator run 级实例化所有类/调用所有函数
- 影响：兜底验证器形同虚设；run 级在沙箱内执行生成代码（`--ro-bind / /` 可读全系统），与 CV2（code_validator 执行任意代码）同族

### UT13 [P3] 快速语法检查只覆盖 .json/.py

- 位置：:320-338 其他扩展名恒 `return True, ""`
- 影响：非 Python/JSON 文件的快速语法过滤为空，全依赖 LLM 语言检测——而 LLM 检测仅在 expected_language + llm_caller 都存在时触发（:96/:162），否则跳过

### UT11 [P3] `files_repr = repr(files)` 嵌入生成脚本——内容含引号/反斜杠破坏脚本

- 位置：:404/:576/:627/:679 Python/JS/Go/Rust 验证器都 `repr(py_files)` 拼进 f-string
- 影响：文件内容含 `'''` 或 `\x` 转义序列时生成脚本可能语法破坏或语义变化（repr 的转义对 Python 字面量安全，但路径分隔符 `\\` 双转义在 .replace('\\\\', '.') 等处的正确性依赖 f-string 层级）

## 修复优先级

| 项 | 级别 | 关键点 |
|---|---|---|
| UT5 | P2 | 验证栈在无 bwrap 环境整体空转 |
| UT10 | P2 | 合法代码被误拒触发无效重试 |
| UT6 | P2 | async 上下文降级 |
| UT14 | P3 | 多语言验证级别 |
| UT7 | P3 | 兜底验证器 |
| UT13 | P3 | 快速语法覆盖 |
| UT11 | P3 | 脚本生成健壮性 |

## 关联

- **「存在≠正确」主线**：UT5 是最直接的证据——验证执行端在依赖缺失时静默通过（与 CV2/TR1/TG2/IM2/RL3/FD2 同源）
- **LLM 契约双轨（v1.11 主线）**：UT10/UT6 都隐含对 llm_caller 返回类型的假设不一致
- **五支柱（EVOLUTION.md §5.6 支柱 2）**：沙箱验证应是 Gate 的执行器，UT5 使 Gate 在缺依赖时形同虚设
- **演化方向**：utils 是「存在≠正确」门禁的执行端，应先固化「验证工具不可用=验证未执行」的可辨识语义，再谈验证器协议统一（CV8）
