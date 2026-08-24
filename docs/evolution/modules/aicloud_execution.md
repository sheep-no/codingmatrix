# AI Cloud 执行链（code_executor + auto_executor + sandbox + sandbox_operator + content_analyzer + context_isolator + sensitive_filter + review_queue + knowledge_processor）

> 第一百三十八轮补扫 | v1.139 | 2026-08-17 | 分析对象：`app/utils/aicloud/` 执行链 9 文件——`code_executor.py`（324 行）+ `auto_executor.py`（174 行）+ `sandbox.py`（165 行）+ `sandbox_operator.py`（146 行）+ `content_analyzer.py`（194 行）+ `context_isolator.py`（168 行）+ `sensitive_filter.py`（166 行）+ `review_queue.py`（242 行）+ `knowledge_processor.py`（231 行）+ 消费方 `app/api/v1/aicloud.py`、`app/api/v1/aicloud_knowledge.py`、`app/api/v1/aiGeneratorPptx.py`
>
> 结论：**三语言代码执行沙箱全部可逃逸（Python/Go 文件系统、JS 网络）；execute_code 端点将任意代码执行直接暴露给用户；沙箱写文件恒走人工审查无自动通过路径；审查队列无用户隔离支持跨用户审批写文件；chunk_text 用户可控死循环 DoS；上下文隔离器/偏好体系/安全过滤为纯声明**。docstring「禁用网络访问」「设置沙箱环境」与实现不符。

## 一、模块定位

| 组件 | 位置 | 接线状态 |
|------|------|----------|
| CodeExecutor（三语言执行） | code_executor.py:47 | aicloud.py:916 execute_code 真实消费 + auto_executor:141 消费 |
| BANNED_PYTHON_MODULES / BANNED_JS_MODULES | code_executor.py:34/:40 | 静态子串/AST 检查（可绕过，见 CE2/CE3/CE5） |
| extract_code_blocks / is_safe_code | auto_executor.py:43/:48 | execute_with_llm_loop 真实消费（is_safe_code 可绕过，见 AE1） |
| execute_with_llm_loop | auto_executor.py:63 | aicloud.py:213 chat 端点真实消费 |
| SANDBOX_BASE_DIR / get_sandbox_path / ensure_user_sandbox / validate_sandbox_path | sandbox.py:12/:15/:41/:60 | aicloud.py:142/:457 真实消费 |
| get_absolute_sandbox_path / sanitize_path / is_path_safe | sandbox.py:82/:100/:113 | **全库零消费——死代码** |
| SandboxFileOperator（read_with_review / write_with_review） | sandbox_operator.py:14/:72/:111 | aicloud.py:401/:459 真实消费 |
| analyze_content / deep_content_analysis / check_malicious_pattern | content_analyzer.py:72/:159/:103 | sandbox_operator 真实消费（write 恒需审查，见 SO1/CA5） |
| check_dangerous_extensions | content_analyzer.py:122 | **全库零消费——死代码** |
| ContextIsolator / is_protected_path / is_protected_file | context_isolator.py:47/:130/:143 | aicloud.py:395 真实消费（setup_sandbox env 未应用，见 CI1） |
| filter_sensitive_content / mask_api_keys / detect_sensitive_info | sensitive_filter.py:32/:52/:132 | sandbox_operator/content_analyzer 真实消费 |
| create_review / approve_review / reject_review | review_queue.py:21/:85/:115 | aicloud.py 真实消费 |
| process_review_request / get_pending_reviews / get_user_review_preferences | review_queue.py:200/:173/:152 | **全库零消费——死代码** |
| parse_document / chunk_text / embed_chunks / search_similar_chunks | knowledge_processor.py:92/:108/:161/:207 | aicloud_knowledge.py / aiGeneratorPptx.py / aicloud.py 真实消费 |

## 二、缺陷清单

### P2（10 项）

- **CE2 [P2] 三语言沙箱文件系统逃逸——BANNED 覆盖缺口（pathlib/os 未禁）**——code_executor.py:34-38 `BANNED_PYTHON_MODULES` 无 `pathlib`——`from pathlib import Path; Path("/etc/passwd").read_text()` 直接读任意系统文件（读写端点只禁 open() 函数）；Go 侧 :251 只禁 `["net","os/exec","syscall","unsafe"]`，`import "os"` 合法 → `os.ReadFile/WriteFile` 任意读写——**Python 与 Go 的「安全执行」承诺全部落空**。
- **CE3 [P2] JS 沙箱仅 require 子串检查——Node 全局对象裸奔 + 全局 fetch SSRF**——:188-190 只查 `require('mod')`/`require("mod")` 字面子串——`process.env`（Node 全局，无需 require）直接泄露环境变量、Node 18+ 全局 `fetch()` 无需任何 require 即任意网络请求（**第五处服务端外连面**）、`require( 'fs' )`（空格）/`process.mainModule.require('fs')` 绕过子串——docstring「禁用网络访问」（:5）不成立。
- **CE4 [P2] MAX_MEMORY_MB=256 死配置——内存炸弹无拦截**——:52 定义常量但 subprocess 执行（:122-133/:202-208/:286-291）无任何 rlimit/ulimit 内存限制——`[0]*10**9` 内存炸弹可拖垮宿主容器（**死配置，死代码家族累计第 17 处**）。
- **AE1 [P2] is_safe_code 子串检查可绕过 + 文件操作检查空操作——auto_executor 安全层形同虚设**——auto_executor.py:48-60 `DANGEROUS_KEYWORDS`（:36-40）纯 `keyword in code` 大小写敏感子串——`import os  `（尾随空格）/`import\tos`/`IMPORT OS`/`exec (`（空格）全绕过；:56-58 `if "open(" in code and "/sandbox" not in code: pass`——**文件操作安全检查是空操作**（注释宣称默认相对路径在沙箱）。真正拦截依赖 CodeExecutor 的 AST 检查，而 AST 检查自身可绕过（CE5）。
- **SB1 [P2] SandboxFileOperator 路径校验不解析符号链接——sandbox 内 symlink 逃逸读任意文件**——sandbox_operator.py:51 `validate_sandbox_path` 用 `os.path.normpath`（对比 sandbox.py:74 官方版用 `realpath` 解析 symlink）——**双实现语义不一致（双轨家族第 20 处）**——沙箱内 symlink → 沙箱外文件，read 时 normpath 判断在沙箱内放行——配合 CE2（代码执行逃逸可创建 symlink）+ aicloud.py:395 `is_protected_path`（只查用户原始相对路径，不解析 symlink 目标）→ **完整任意文件读取链**。
- **SO1/CA5 [P2] write 恒需人工审查——auto_approve 分支恒不可达**——content_analyzer.py:96-98 `analyze_content` 对 `operation_type=="write"` 无条件 `warnings.append("File write requires review for safety")` → `deep_content_analysis`（:184-192）warnings 非空恒 `require_human_review` → sandbox_operator.py:135 `if analysis.get("action") == "auto_approve"` **恒 False 死分支**——**沙箱写文件永远 pending 人工审查，即使完全安全内容**——`get_user_review_preferences` 的 `auto_approve_safe_content=True`（review_queue.py:169）恒不生效（「规划功能未生效」家族）。
- **SO2 [P2] 敏感过滤仅作用于展示层——raw_content 原样入库与写回**——sandbox_operator.py:99-105 返回过滤后 content + 原样 raw_content——aicloud.py:421/:488 `create_review(content=raw_content)` 原文入库（敏感信息进 review 表）；approve 后 :683 `open(review.file_path,"w")` 写回原始内容——**敏感过滤只影响 read 响应展示，存储与写回均为原文**。
- **RQ1 [P2] 审查队列无用户隔离 + 跨用户审批写文件**——aicloud.py:621 `get_reviews` 只按 status 过滤无 `user_id`——任何有 aicloud 权限用户可看**所有用户**待审内容（含 raw_content 原文）；`approve_review_endpoint`（:660-691）不校验 `review.requested_by == user_id`——跨用户审批，且 :683 直接用 `open()` 写 `review.file_path`（绕过 SandboxFileOperator 校验）——**跨用户写入沙箱文件**（与 PAPI1 同根因：review 明确有 requested_by 字段 → 用户归属 → 应按用户隔离）。
- **CI1 [P2] ContextIsolator.setup_sandbox 产出的环境变量从未应用——沙箱环境纯声明**——context_isolator.py:61-65 设置 `sandbox_env`（HOME/WORK_DIR）——但 CodeExecutor 执行时 env=`{**os.environ, ...}`（code_executor.py:127-131）完全不用 sandbox_env——**「设置沙箱环境」承诺未兑现**（「规划功能未生效」家族）。
- **KP1 [P2] chunk_text 死循环——chunk_overlap ≥ chunk_size 时无限循环（用户可控 DoS）**——knowledge_processor.py:154 `start = end - chunk_overlap`；:155-156 只救 `start <= 0`——当 overlap ≥ size：`start_new = end - overlap = start + (size - overlap) ≤ start` 永不前进 → **无限循环**——aicloud_knowledge.py:68-69 `chunk_overlap=Form(50)` 用户可控且无上限校验——恶意请求 `chunk_size=100&chunk_overlap=100` → 请求线程卡死。

### P3（16 项）

- **CE5 [P3] Python AST 检查可绕过（attribute 链不受限）**——code_executor.py:164-180 只拦 `ast.Name` 直调或 `__builtins__` 前缀的 Call——`().__class__.__mro__[1].__subclasses__()` 全走 attribute 链不拦（getattr/__import__ 限制可被 __subclasses__ 找到任意文件/网络对象绕过）。
- **CE7 [P3] 执行脚本明文落盘无权限限制**——code_executor.py:114-115 把代码写 `{workspace}/exec_{uuid}.py`（/sandbox/{uid}/workspace 用户可读），执行窗口内明文暴露；JS/Go 同理（:195-200/:258-264）。
- **AE2 [P3] workspace_path 缺省时 CodeExecutor 落 `/tmp`（tempfile.gettempdir()）**——code_executor.py:55 默认值——当前 aicloud.py 传真实 sandbox 路径，但任何未来调用方漏传即无沙箱目录（与 SB1 配合更弱）。
- **AE3 [P3] 循环迭代记录截断无标记**——auto_executor.py:167-169 `[:500]/[:200]/[:200]` 截断无截断标记（JP2/TR2 家族）。
- **AE5 [P3] conversation_history 收集后从不使用**——auto_executor.py:165-170 append 后无任何消费方——死数据（失败追踪/审计缺失）。
- **SB2 [P3] ensure_user_sandbox 声明 async 但纯同步 os.makedirs**——sandbox.py:41-57 无 await——协程语义虚设。
- **SB3 [P3] sandbox.py 三个函数零消费死代码**——get_absolute_sandbox_path（:82）/ sanitize_path（:100）/ is_path_safe（:113）全库零引用——**死代码家族累计第 18/19/20 处**。
- **SB4 [P3] is_path_safe 危险字符子串误伤正常文件名**——sandbox.py:123-133 `".."`/`"~"` 子串——`a..b`/`my~file` 合法名被拒（FCT3/PP8 家族）。
- **SO4 [P3] PROTECTED_PATHS 双份清单不一致**——sandbox_operator.py:24-27（7 项，无 /usr//boot//snap//srv//opt）vs context_isolator.py:14-28（13 项）——**双轨家族第 19 处**；且 SandboxFileOperator.validate_sandbox_path 实际不查 PROTECTED_PATHS（只 normpath 前缀判断）——:24 定义未使用死字段。
- **CA6 [P3] MALICIOUS_PATTERNS 正则绕过面大 + 正常用途误伤**——content_analyzer.py:14-27 无词边界无 AST——`os .system`/`subprocess.run`（只禁 .call）变体漏检；`base64.b64decode(` 正常解码用途（图片 data URL）误伤；`rm -rf /etc` 只禁 `rm -rf /`。
- **CA7 [P3] check_dangerous_extensions 零消费死代码**——content_analyzer.py:122-142 全库零引用（read/write 均未调用，文件类型检查形同虚设）——**死代码家族累计第 21 处**。
- **CI2 [P3] block_protected_paths 子串匹配误伤**——context_isolator.py:88 `pattern in normalized_path`——`/opt/` in `/workspace/opt/config` 误伤合法路径。
- **CI3 [P3] 全局单例无锁**——context_isolator.py:119-127 get_isolator 无锁（JP4 家族）。
- **SF1 [P3] password 正则仅覆盖 `password=` 等号形式**——sensitive_filter.py:19——`PASSWORD xxx`（空格分隔）/大小写变体漏检；且 replace 只替换键名保留结构，值可能残留。
- **RQ2 [P3] review_queue 三个库函数零消费 + 偏好硬编码**——process_review_request（:200）/ get_pending_reviews（:173）/ get_user_review_preferences（:152）全库零引用（get_reviews 端点自建 query 不走库函数）——**死代码家族累计第 22/23/24 处**；get_user_review_preferences 恒硬编码 `human_review_enabled=True`（:166-170）——auto-approve 分支设计上即不可达。
- **KP2 [P3] embed_chunks 失败用零向量占位——检索静默污染**——knowledge_processor.py:185 `[0.0]*768` 占位——cosine_similarity 恒 0.0，search_similar_chunks 仍返回前 top_k 个无序结果（:231）——**降级为垃圾检索且无失败标记**（「提取≠生效」家族）；KP3 :194 长度不匹配静默 0、KP4 :101-102 `.doc` 旧格式误走 python-docx 崩溃并入本条。

## 三、全库交叉确认

- **任意代码执行链（execute 端点完整暴露面）**：aicloud.py:897 `execute_code` 直调 CodeExecutor.execute 不经 is_safe_code——用户可提交任意 Python/JS/Go——CE2（pathlib/os 文件逃逸）+ CE3（JS fetch SSRF + process.env）+ CE5（AST attribute 链绕过）→ **任意文件读写 + 环境变量泄露 + 内网 SSRF + 内存炸弹**，全部经公开端点暴露。
- **文件读取链**：CE2 代码执行创建 symlink（或沙箱内已有）→ SB1 normpath 校验放行 → read_file 端点读任意文件（raw_content 原文返回/入库）——与 SO2/RQ1 叠加敏感信息随 review 全库可见。
- **死代码家族累计第 17-25 处**：CE4（MAX_MEMORY_MB 死配置）、SB3（sandbox 三死函数）、CA7（check_dangerous_extensions）、RQ2（review_queue 三死函数）、SO1（write auto_approve 死分支）。
- **双轨家族第 19/20 处**：SO4（PROTECTED_PATHS 双份清单）、SB1（sandbox 路径校验双实现 realpath vs normpath）。
- **「规划功能未生效」家族新增**：CI1（sandbox_env 未应用）、SO1/CA5（write 恒需人工审查，auto_approve 恒不可达）、KP2（零向量占位污染检索）——家族累计 GC2/PM2/TDC1/LLM2/CON1/DT1/CI1/SO1/KP2。
- **越权/用户隔离家族**：RQ1 与 PAPI1 同根因（review/供应商均为用户归属数据但无隔离校验）。
- **SSRF 外连面累计第五处**：CE3（JS 全局 fetch）——此前 PAPI2/DP2/WS2/HRQ1/HRQ2。
- **与第一百三十七轮衔接**：aicloud_core 建档的 PAPI1 修正（按用户隔离非 admin 门禁）在 RQ1 再次印证同一定性。

## 四、测试状态

零单元测试。CE2/CE3（沙箱逃逸）、AE1（is_safe_code 绕过）、SB1（symlink 逃逸）、SO1（write 恒 pending）、RQ1（跨用户审批）、CI1（sandbox_env 未应用）、KP1（chunk_text 死循环）全部实码可证无任何用例保护。修复建议：① CE2/CE3/CE5 沙箱改为真实隔离（docker_runner/bwrap + rlimit 内存 + 进程组 + 白名单 API），或明确降低承诺；② CE4 MAX_MEMORY_MB 用 resource.setrlimit 落地；③ AE1 用 AST/运行时拦截替代子串；④ SB1 统一 realpath 校验并解析 symlink；⑤ SO1/CA5 补安全内容自动通过路径或删死分支；⑥ RQ1 审查按 requested_by 隔离 + approve 校验所有权 + 写回走 SandboxFileOperator；⑦ CI1 将 sandbox_env 注入 subprocess 或删声明；⑧ KP1 校验 chunk_overlap < chunk_size 并设上限；⑨ 下轮转 aicloud/adapters/ 8 文件。
