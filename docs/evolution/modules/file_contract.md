# FileContract 深扫（file_contract.py，141 行）

> 第八十二轮推演 | 2026-08-13 | 定位：文件契约与审查数据模型——从 multi_model_agent 拆分而来（docstring :4），承载文件操作安全验证（路径 + 内容）+ 审查结果/任务步骤数据模型

## 1. 模块定位

三个职责：① `FileContract` 路径安全验证（validate_path）与内容安全验证（validate_content）；② 审查数据模型（ReviewResult）；③ 任务步骤模型（TaskStep）与降级步骤构造（_degrade_step）。是 multi_model_agent 编排层文件操作安全的校验载体，也是 task_planner 降级路径的步骤产出源。

### 依赖链

| 方向 | 模块/位置 | 说明 |
|------|-----------|------|
| 消费方 | `multi_model_agent.py:225-236` | FileContract 前置验证（只调 validate_path，不调 validate_content），生产活跃 |
| 消费方 | `multi_model_agent.py:209` | reviewer.review_plan（AIReviewer 唯一被调用的方法） |
| 消费方 | `task_planner.py:17/:112/:122/:125` | _degrade_step 三处降级分支产出 ai_call 步骤，生产活跃 |
| 依赖 | `ai_reviewer.py:122-140` | review_file_operation 用 validate_path + validate_content，**该方法全库零消费方** |
| 测试 | tests/unit/test_file_contract.py | 路径/内容验证单测 |

## 2. 深扫发现

### P2 项

- **FCT1 降级路径必定产出 ai_call 空转步骤（AE1 触发链闭环）**——task_planner 三处降级分支（:112 解析失败 / :122 schema 错误 / :125 异常）都返回 `_degrade_step(task)` → 构造 `type: "ai_call"` 步骤（:137-138）。而 agent_executor.execute 对 ai_call 返回 `{"status": "pending"}` 占位（AE1，:101-102）。串联链路：**decompose 解析失败 → 降级 ai_call 步骤 → execute 返回 pending → multi_model_agent:238 append results → `success: True`（:245 只检查 review 通过，从不检查 results 内容）**——任务「降级执行」实际什么都没执行，但整体报告成功。这是 AE1 的真正触发面：**只要 LLM 分解响应非 JSON/schema 不合法/异常（LLM 输出不稳定时高概率发生），任务静默空转完成**——降级路径的本意是「至少执行任务」，实际是「什么都不做还报告成功」。
- **FCT2 `validate_content` 安全检查生产零执行（写文件危险模式拦截是死能力）**——validate_content 的唯一生产消费方是 ai_reviewer.review_file_operation（:135），而 **review_file_operation（:105-142）全库零消费方**——multi_model_agent 只调 reviewer.review_plan（:209，LLM 审查计划不查内容）；multi_model_agent:225-236 的 FileContract 前置验证只调 `validate_path`（:234）**从不调 validate_content**。**危险代码写入拦截（rm -rf/os.system/subprocess shell/eval 等 16 条模式，:85-108）整个生产链路从未执行**——文件内容级安全验证是声明完整但零触达的能力。
- **FCT3 `protected_files` 子串误伤（合法项目文件被拒）**——:59 `if protected in abs_path_str` 用**子串包含**判断（protected_paths 用 startswith :50 正确，protected_files 退化为 `in`）：实测 `/workspace/projects/user_x/id_rsa_backup.py` 命中 `id_rsa`、`known_hosts_notes.txt` 命中 `known_hosts`——**合法项目文件被误判敏感文件拒绝**；`.git/config`/`id_ed25519`/`authorized_keys`/`.env` 同理子串误伤（如 `id_rsa_new.pem`、`my_known_hosts.py`）。CV2/CR2/UT10 子串假阳性家族。

### P3 项

- **FCT5 validate_content 危险模式正则双面缺陷（漏检危险变体 + 误伤安全写法）**——`:87 r"rm\s+-rf\s+/"` 只匹配 `rm -rf /`，`rm -rf ./data`（空格后 `.` 不匹配 `\s+/`）**漏检**；`subprocess\.call\s*\(`（:92）匹配**任何** subprocess.call（含安全列表参数 `subprocess.call(["ls"])`）**误伤**；`eval\s*\(`（:96）注释/字符串内 eval( 误伤（SHS4 家族）。正则即非 AST 又方向单面。
- **FCT6 TaskStep.type 声明 4 种 vs execute 只实现 2 种**——TaskStep.type 字面量（:128）声明 `file_operation/code_generation/tool_call/ai_call` 四种，但 agent_executor.execute 只处理 file_operation/ai_call（:99/:101），**code_generation/tool_call 落「未知步骤类型」错误**（:104）——planner prompt（task_planner:85-88）引导 LLM 产出 4 种类型，其中 2 种产出即失败（AE1 家族：声明与执行面不符）。

## 3. 演化方向

### 3.1 降级路径语义修复（与 AE1 联动）

FCT1 的修复必须与 AE1 同时进行：降级步骤不应产出空转 ai_call——要么 execute 对 ai_call 真正执行（LLM 处理 task 参数），要么 _degrade_step 产出 `code_generation`/`file_operation` 等可执行步骤，要么降级时标记 `degraded: True` 并让 multi_model_agent:245 的 success 判定改为 `all(r.status != "pending" for r in results)`。当前「降级执行」的语义承诺与实际「空转报成功」严重不符（§5.6 支柱 1 产物协议反例）。

### 3.2 安全检查接线（与 AE2 联动）

FCT2 与 AE2 是同一主线两面：AE2 是执行面绕开（execute_analysis 工具路径绕 FileContract），FCT2 是能力面空转（validate_content 从未接线）。方向：把 validate_path + validate_content 统一下沉到 tools.py 真实工具层（写文件/删除工具内先校验），并让 multi_model_agent:225 的 step 路径与 execute_analysis 路径共用同一校验——FCT3 子串误伤（改为路径段精确匹配）与 FCT5 正则（AST 化/白名单化）随下沉一并修复。

## 4. 主线关联

- **「降级=空转」家族**：FCT1 使 AE1 从「若 planner 产出 ai_call」变成「planner 解析失败必然触发」——降级语义失真（CD2/DMR1 降级语义不符家族）在步骤执行端的确凿实例
- **声明与执行面不符**：FCT6（TaskStep 4 类型 vs execute 2 实现）与 AE1（ai_call 空转）、SM2（增量检测未接线）同主线——prompt/类型系统声称的能力实现面未兑现
- **安全验证空转**：FCT2（validate_content 零执行）与 AE2（分析路径绕 FileContract）、UT5（沙箱验证空转）、CV2（验证假阳性）——验证栈在「文件内容安全」维度的完整失效：声明存在 + 校验路径断裂 + 正则有缺陷
- **子串假阳性家族**：FCT3 与 CV1（is_critical_file 子串）、CR2（版本检查子串）、UT10（"NO" 子串）同族

## 5. 测试状态

tests/unit/test_file_contract.py 存在（路径/内容验证正反例），但：validate_content 生产零执行（FCT2）测试无法暴露；protected_files 子串误伤（FCT3）无 `id_rsa_backup.py` 类合法文件名反例；TaskStep/execute 类型对齐（FCT6）无跨模块集成测试；降级路径 ai_call 空转（FCT1）无 task_planner→execute 串联测试（test_agent_executor 的 test_ai_call_step 反而固化了 pending 为正确行为）。
