# agent_core.py 演化深扫文档

> 版本：v0.1 | 扫描日期：2026-08-17 | 状态：已完成
> 归属：Agent 引擎 / 项目生成 Agent 核心（主生成循环 + 验证体系 + 工具注册）
> 路径：`app/utils/agent_core.py`（2627 行）
> 索引：[TASKS.md](../TASKS.md)

## 1. 模块定位

项目生成 Agent 核心，包含五个部分：
1. **ConversationHistoryManager**（:37-121）：基于 session_id 的内存对话历史 + output_dir 管理（全局单例）
2. **工具基础设施**（:126-315）：ProgressType/FileModelRouter（文件类型→模型路由）/TokenEncoder（tiktoken）/ToolRegistry（动态工具注册）
3. **验证体系**（:316-1133）：CodeValidator（syntax/imports/runtime/security 四检）/ProjectValidator（文件+依赖+结构+入口）
4. **ProjectGeneratorAgent**（:1288-2483）：主生成 Agent——40 步循环、token 守卫压缩、工具调用解析（4 种格式）、动态模型切换
5. **文件工具**（:2486-2626）：ProjectFileManager（FileOperator 包装）+ 9 个 ToolRegistry 工具

## 2. 依赖链与消费方

**活跃消费**：
- `generate_endpoints.py:22/55/78`——ProjectGeneratorAgent.generate_project（活跃主消费）
- `AiProjectCode.py:31`——ProjectFileManager
- 模块内部：ToolRegistry.register 注册全部工具；conversation_history_manager 全局单例

**同名单双轨**：
- agent_core.py:351 CodeValidator vs `app/agent/code_validator.py:20` CodeValidator（orchestrator/mixin/error_recovery 活跃消费的主验证器）
- agent_core.py:795 ProjectValidator vs `app/utils/project_validator.py:43` ProjectValidator

**防护关系**：
- create_project_file（:1140）——直接 aiofiles.open，**无 FileOperator 防护**
- create_file/edit_file/delete_file 等 9 工具——走 ProjectFileManager→FileOperator（PathSecurityError 防护）

## 3. 发现

### AC1 [P2] create_project_file 无路径校验——LLM 可写任意路径（越权写文件）

- **Bug 代码**：:1182 `aiofiles.open(file_path, 'w')` 直接用 LLM 工具参数；:1177 `path.parent.mkdir` 任意目录创建——无 FileOperator._validate_path/无 PathSecurityError/无 FileContract 检查。
- **根因**：create_project_file 是生成主工具（LLM 每轮创建文件都用它），但路径完全由 LLM 输出决定——可写 `/etc/xxx`、`../outside.txt` 等任意服务进程权限内路径。
- **对照**：同模块 create_file（:2551）/edit_file（:2507）/delete_file（:2527）均走 ProjectFileManager→FileOperator（有路径防护）——**同一模块两套文件写入路径，主工具无防护**。

### AC2 [P2] _parse_tool_calls 尝试4 硬编码 file_path `./projects/user_api/`——无视 output_dir（GRD3 家族）

- **Bug 代码**：:2288 `file_path = f"./projects/user_api/{filename}"`——LLM 直接输出代码块（未走工具调用格式）时，转换工具调用**硬编码相对路径**——无视 ProjectGeneratorAgent 的 output_dir 参数。
- **影响**：LLM 直接输出代码块时文件写入错误位置（./projects/user_api/）；且相对路径 CWD 漂移（worker CWD 不同则写错目录）。

### AC3 [P3] _execute_tools 访问不存在的 self.current_output_dir——目录快照逻辑恒 AttributeError 静默失效

- **Bug 代码**：:2403 `project_root = self.current_output_dir or Path(".").resolve()`——ProjectGeneratorAgent（BaseModel）**无 current_output_dir 字段**——访问即 AttributeError → :2418 `except Exception` logger.debug 吞掉——:2400-2417 的目录快照生成块是确定性死代码（generate_project 循环 :1869 另有 list_directory 快照正常）。

### AC4 [P2] 内存级会话历史 ConversationHistoryManager——重启丢失 + 多 worker 不共享 + 清理排序失效（MCP1/GRD2 家族）

- **Bug 代码**：:37-121 全局单例内存 dict 存 messages/output_dir——进程重启丢失；多 worker 各持一份（session 历史在 worker A 创建、worker B 处理继续生成时 `has_history` False → 新生成而非继续）；:107-109 `_cleanup_if_needed` 排序 key 用 `messages[-1].get("timestamp")`——**消息 dict 无 timestamp 字段**（generate_project :1665-1668 只存 role/content）→ 恒 "" → 清理随机。
- **影响**：generate_endpoints 的「继续生成」依赖历史——多 worker/重启场景功能失效。

### AC5 [P2] 生成成功判定只看 final 步骤存在——验证失败仍 success（TR1/MAR8 家族）

- **Bug 代码**：:1994 `"success": len([s for s in steps if s.get("type") == "final"]) > 0`——只要 LLM 输出含完成关键词即 success；:1953 验证失败（runnable False）只发回调**不改 success**；:1906-1911 完成检测为纯文本子串「完成/success/done/生成完毕」——LLM 一句话「完成」即结束（AC11）。
- **影响**：与 TR1/DR7 同族——结果谎报：验证不可运行的项目返回 success=True。

### AC6 [P3] run_full_validation runnable 只计文件验证——依赖/结构/入口缺失仍 runnable=True（DGV1 放行）

- **Bug 代码**：:844 `runnable = len(all_errors) == 0`——all_errors 只来自 file_validations；:826/:829/:832 的 dependency_check/structure_check/entrypoint_check **不计入 runnable**——缺 README、无 main.py 入口、requirements 缺失依赖全不影响（依赖若在 import 检查中漏报则 runnable True 谎报可运行）。

### AC7 [P3] _validate_runtime 宿主机 exec 生成代码——无沙箱无资源限制（安全）

- **Bug 代码**：:569 `exec(open(...).read())` 子进程在宿主机执行生成代码——无 docker/bwrap 隔离、无内存/CPU/网络/文件系统限制（仅 10s 超时）——生成代码含危险操作（删文件/写任意路径/网络请求）直接执行（与 docker_runner 隔离执行矛盾——两套验证执行路径：docker 隔离 + 宿主机直跑并存）。

### AC8 [P3] _check_syntax_warnings 无条件报 for 循环变量未使用——全量误报

- **Bug 代码**：:781-785 visit_For 对每个 for 循环无条件 `warnings.append("循环变量可能未使用")`——即使循环体使用变量也报——**任何 for 循环都产生警告**（全量误报注入验证结果）。

### AC9 [P3] _validate_security 'open' 列危险函数 + 安全结果恒 success（DGV1/DR2 家族）

- **Bug 代码**：:637 dangerous_calls 含 'open'——任何文件用 open() 触发「使用潜在危险函数: open」警告；:671 security 恒 success=True（:424 汇总 success 只计前三项）——**安全检查只告警不阻断**（与 DR2 同族）。

### AC10 [P3] CodeValidator/ProjectValidator 同名双轨 + validate_file 每次重建跑 pip freeze（SCT6 家族）

- **Bug 代码**：agent_core.py:351 CodeValidator vs app/agent/code_validator.py:20（orchestrator/mixin/error_recovery 活跃消费）——同名异构双轨；agent_core.py:795 ProjectValidator vs app/utils/project_validator.py:43——又一双轨；:1243 validate_file 每次调用新建 CodeValidator → __init__ :363 每次全量 `pip freeze` 子进程（性能）。

### AC11 [P3] 完成检测关键词子串误判（PP8 家族）

- **Bug 代码**：:1911 `any(indicator in pure_text.lower() ...)`——「完成」子串出现即判完成——LLM 中途说「后续将完成模块 X」即误判提前结束。

### AC12 [P3] FileModelRouter 关键词子串匹配 + 硬编码模型名（PP8/SPFG17 家族）

- **Bug 代码**：:216-225 backend/frontend 关键词 `kw in req_lower` 子串匹配（"api" 命中含 api 的任意需求）；:164-165 硬编码 "Qwen/Qwen3-8B"/"DeepSeek-R1-0528-Qwen3-8B"（与 SPFG17 硬编码 Qwen 同族）。

### 归入佐证（不单列）
- **AC-GRD1 佐证**：:2019-2025 _call_llm 消息直接拼 prompt、:1661 用户需求直接进 messages——Prompt 注入检测缺失路径的又一实例（GRD1 未接线佐证）。
- **AC-GRD3 佐证**：:2604 ProjectFileManager.PROJECT_BASE_DIR="./projects" 相对路径 CWD 漂移（与 GRD3/AC2 同族）。

## 4. 演化方向

agent_core 是活跃核心（generate_endpoints 主消费），修复优先级高：
- **路径安全**（AC1/AC2）：create_project_file 接入 FileOperator._validate_path（与同模块 9 工具统一）或 FileContract 检查；尝试4 硬编码路径改 output_dir 相对解析
- **会话持久化**（AC4）：内存历史 → Redis/DB（与 conversation_store 复用）——「继续生成」多 worker 可靠；_cleanup 排序 key 修正（存 last_update 时间戳字段）
- **结果语义**（AC5/AC6）：success 结合 validation.runnable；runnable 计入依赖/入口检查结果；完成检测改结构化信号（JSON 完成标记）而非关键词子串
- **验证执行**（AC7）：runtime 验证统一走 docker_runner 隔离执行（消除宿主机直跑路径）；AC8/AC9 误报规则重设计（for 循环用名检测、open 从危险列表移除或区分写文件场景）
- **收敛**（AC10）：两个 CodeValidator/两个 ProjectValidator 合并单一来源

## 5. 主线关联

- **路径安全双轨**：AC1（create_project_file 无防护）vs 同模块 9 工具（有防护）——防护接线的选择性遗漏；AC2 加入 GRD3 相对路径漂移家族
- **结果谎报**：AC5（验证失败仍 success）加入 TR1/MAR8/DR7 家族——生成链成功态谎报
- **内存级状态**：AC4 加入 MCP1/GRD2（InMemoryRateLimiter/ConversationHistoryManager 同为进程内全局单例）
- **DGV1 放行**：AC6/AC9（验证/安全检查不阻断）加入放行家族
- **同名双轨**：AC10 加入 SCT6（两个 CodeValidator + 两个 ProjectValidator）
- **与 spec_first 生成链**：agent_core 是传统生成链（generate_endpoints→ProjectGeneratorAgent），spec_first 是另一条（SPFG 详档）——两条生成链并存，agent_core 验证体系（AC5-AC9）与 spec_first 验证端（SPFG13）同问题家族

## 6. 测试状态

- **零单元测试**：tests/ 下无 agent_core/ProjectGeneratorAgent/CodeValidator（utils 版）引用
- AC1 路径越权、AC4 会话持久化、AC5 结果谎报、AC7 宿主执行均无测试约束——2627 行核心生成逻辑（40 步循环、4 种工具解析格式、token 守卫）全部无用例保护
