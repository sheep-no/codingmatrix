# Workflow 节点类型（node_types/ 10 节点合扫）

> 第一百三十六轮补扫 | v1.137 | 2026-08-17 | 分析对象：`app/utils/workflow/node_types/` 全目录——`__init__.py`（40 行）+ `base.py`（136 行）+ `web_search.py`（187 行）+ `llm_call.py`（149 行）+ `http_request.py`（199 行）+ `code_execution.py`（211 行）+ `conditional.py`（213 行）+ `file_processing.py`（200 行）+ `human_approval.py`（150 行）+ `data_transform.py`（307 行）+ `chart_generation.py`（313 行）
>
> 结论：**节点层是「规划功能未生效」家族的集中爆发点——条件分支不参与调度、LLM 数据流变量契约断裂、人工审批恒自动拒绝、代码执行无沙箱**。本轮确认 executor 会调 `validate_params()` 与 `set_approval_callback()`（executor.py:222-225），但 `_approval_callback` 在 API 层恒为 None。

## 一、模块定位

| 组件 | 位置 | 接线状态 |
|------|------|----------|
| NodeFactory | executor.py:45-65 | 真实消费——映射全部 9 种 TaskType 到节点类 |
| TaskNodeBase / NodeResult | base.py | executor/aggregator 真实消费；**merge_context（base.py:112）全库零消费——死方法** |
| WebSearchNode | web_search.py:40 | executor.py:223 经 NodeFactory 创建，validate_params + execute 均被调用 |
| LLMCallNode | llm_call.py:21 | 同上（直连顶层 `call_llm`） |
| HTTPRequestNode | http_request.py:31 | 同上 |
| CodeExecutionNode | code_execution.py:36 | 同上 |
| ConditionalNode | conditional.py:35 | 同上；**但 branch_path 输出对调度零影响** |
| FileProcessingNode | file_processing.py:36 | 同上 |
| HumanApprovalNode | human_approval.py:36 | 同上；**审批回调恒未设置** |
| DataTransformNode | data_transform.py:40 | 同上 |
| ChartGenerationNode | chart_generation.py:48 | 同上；cleanup_all_temp_files 被 executor._cleanup 引用（唯一消费方） |

链路（承接第一百三十五轮）：TaskDecomposer 规划节点 → GraphValidator 校验 → NodeFactory.create → `validate_params()` → `execute(context)`，context 由 ResultAggregator 以 `{node_id}_result` 键构建。

## 二、缺陷清单

### P2（11 项）

- **CE1 [P2] 代码执行无沙箱——LLM 生成的代码直接在宿主机跑**——code_execution.py:154-158 `asyncio.create_subprocess_exec('python3', temp_file)`——docstring（:23-25）声称「在安全环境中执行」，但**实际没有任何沙箱/隔离**——LLM 生成的 code 可任意读写文件系统、访问网络、读取环境变量——与 docker_runner/process_guard 的沙箱承诺矛盾——**LLM 工作流能力边界直接等同宿主权限**（LLM 不可信输入进宿主执行，安全关键）。
- **HRQ1 [P2] SSRF 检查 TOCTOU + DNS rebinding——解析两次可不同 IP**——http_request.py:94 `_check_ssrf` 在 validate 阶段 socket 解析一次，:135 httpx 请求时再解析一次——**两次解析结果可不同（DNS rebinding）**；且 :96 DNS 解析异常返回 None（放行）——「解析失败即放行」语义颠倒（检查失败应拒绝）。
- **HRQ2 [P2] 变量替换绕过 SSRF——validate 查模板 URL，execute 跑替换后 URL**——http_request.py:125 url 经 `_replace_variables` 从上下文取值替换后才请求——**替换后的目标（内网 IP 可来自上游节点数据）不再做 SSRF 检查**——validate 阶段只检查原始 url 模板——上下文驱动的 SSRF 直通。
- **LLM2 [P2] input_variable/output_variable 数据流契约断裂——规划变量从未生效**——llm_call.py:100 `context[input_variable]`——executor 用 ResultAggregator 以 `{node_id}_result` 键构建 context，而 TaskDecomposer 系统提示词要求 LLM 规划 `input_variable`——**LLM 规划的变量名（如 "web_data"）在 context 中不存在 → prompt 永远不插入上游数据**；output_variable（默认 "llm_result"）同样从未写入 context——**LLM 节点输出只存在于 result_data，下游 data_transform 按 input_variable 读不到**——「规划功能未生效」家族（TDC1/GC2 同族）在节点层的延伸。
- **LLM3 [P2] `call_llm` 返回 OpenAI 兼容 dict——提取逻辑取不到 content → 输出整个 JSON 字符串**——llm_call.py:130-131 `response.get("content", response.get("text", str(response)))`——顶层 `call_llm` 非流式返回 `{"choices":[...]}`（llm_caller.py:179），**无顶层 content/text 键 → 落到 `str(response)`——LLM 输出变成含 choices 结构的完整响应 dict 字符串**——下游拿到的「结果」不可用（契约断裂，上轮 TDC8 已指出同类）。
- **CON1 [P2] 条件分支不参与调度——branch_path 只是结果字段**——conditional.py:128 计算 branch_path 放入 result_data，但 executor `_get_executable_nodes`（executor.py:187-193）只查 `dep in completed`——**从不读 conditional 节点的 condition_result/branch_path**——true_branch/false_branch 对后续执行路径零影响——**条件分支功能形同虚设**（「规划功能未生效」家族）。
- **HA1 [P2] 审批回调永不注册——「人工审批」节点实际恒自动拒绝**——human_approval.py:140-150 无回调 → 超时后 auto_reject——executor.py:222-223 只在 `self._approval_callback` 非空时 set——而 `app/api/v1/workflow.py` 创建 WorkflowExecutor 时**从不传 approval_callback（构造参数 executor.py:96 默认 None）→ 回调恒 None**——HUMAN_APPROVAL 节点永远走拒绝路径，且 API 层无任何审批端点——**承诺的「人工审批」能力从未兑现**。
- **FP1 [P2] 无边界 FileOperator——工作流节点可读写任意路径**——file_processing.py:37 `self._operator = FileOperator()` 无 base_path 黑名单（FO4 家族）——配合 CE1（无沙箱）与 CE1 的宿主执行，**LLM 规划的工作流可直接读写宿主任意文件**（.env/数据库/密钥）。
- **CE2 [P2] 子进程输出无界收集——恶意代码输出可撑爆内存**——code_execution.py:171 `stdout.decode()` 全量收集——LLM 代码 `print('x'*10**9)` 直接内存膨胀（DR13 家族）。
- **DT1 [P2] merge 操作从节点 config 读变量而非上下文——数据流断裂**——data_transform.py:171-176 `variables = config.get("variables", [])` + `var_value = config.get(var_name)`——**应从上一步 context 读合并对象，实际从自身 params 读**——params 里不存在该键时静默跳过——merge 操作在 LLM 规划场景下必然拿到空合并（「规划功能未生效」家族）。
- **BSE1 [P2] `merge_context` 死方法——上下文构建双轨**——base.py:112-133 与 result_aggregator.py `_build_node_context` 逻辑相同（`{node_id}_result` 键）——**merge_context 全库零消费，executor 走 aggregator**——**双轨家族第 15 处 + 死代码家族累计第 14 处**。

### P3（16 项）

- **LLM1 [P3] `{{input}}` 硬编码占位符替换——prompt 无该占位符则输入数据被丢弃**——llm_call.py:105 `prompt.replace("{{input}}", str(input_value))`——契约依赖 LLM 恰好生成含 `{{input}}` 的 prompt，且 `{input}`/`{{ input }}` 变体全不匹配。
- **LLM4 [P3] FALLBACK_MODEL 死常量 + temperature/max_tokens 硬编码默认**——llm_call.py:18 `FALLBACK_MODEL` 定义后从未使用（:92 只取 model）；:94-95 temperature=0.7/max_tokens=2048 写死。
- **HRQ3 [P3] `follow_redirects=True` 重定向可跳内网**——http_request.py:143——初始 URL 过 SSRF 检查后重定向目标不再校验（SSRF 放大）。
- **HRQ4 [P3] 响应 headers 全量进 result_data**——http_request.py:155 `dict(response.headers)`——Set-Cookie/Authorization 等敏感头进上下文/日志。
- **HRQ5 [P3] 每次请求新建 httpx.AsyncClient**——http_request.py:134——无连接复用（第 7 处 HTTP 客户端模式）。
- **HRQ6 [P3] `{key}` 变量替换遍历全 context——意外替换风险**——http_request.py:191-198——context 含 workflow_id/node_id 等键，URL 中含同名 `{...}` 会被意外替换。
- **CE3 [P3] `process.kill()` 不杀进程组——子进程 fork 逃逸**——code_execution.py:180——超时后子进程派生的孙进程继续运行。
- **CE4 [P3] 临时代码明文落盘 /tmp + 无 CPU/内存资源限制**——code_execution.py:154。
- **CON2 [P3] 表达式 `{key}` 变量内插——字符串值含引号/花括号注入语法异常**——conditional.py:159-163 `expr.replace(f"{{{key}}}", f"'{value}'")`——值含 `'` 或 `{}` 时替换出非法表达式。
- **DT2 [P3] safe_eval 双实现——conditional 与 data_transform 各一套 AST 白名单**——conditional.py:178-192 vs data_transform.py:253-281——ALLOWED_NODES 集合不一致（conditional 多 ast.Attribute）——**双轨家族第 16 处**。
- **DT3 [P3] `_extract_path` 简化 JSONPath——列表展平分支返回含 None 元素**——data_transform.py:303 `[item.get(part) if isinstance(item, dict) else None ...]`——非 dict 元素静默变 None。
- **FP2 [P3] validate 用 `self.params["path"]` 直接索引——缺 path 时 KeyError 崩溃**——file_processing.py:68-72——应返回错误列表却抛异常（validate_params 契约破坏）。
- **FP3 [P3] delete 操作 recursive 可删目录树**——file_processing.py:180-183——LLM 可规划递归删除任意目录。
- **CH1 [P3] matplotlib 全局 plt 跨协程并发串扰**——chart_generation.py:14-16 模块级——单事件循环单线程下实际串行缓解，但多 worker/多线程调用时 `plt.savefig`/`plt.close` 交错 → 图表损坏。
- **CH2 [P3] `_temp_files` 全局集合无锁 + executor 崩溃/异常时泄漏**——chart_generation.py:23/:239——清理依赖 executor._cleanup 每轮执行，异常中断路径漏清。
- **CH3 [P3] `_configure_fonts` 无锁竞态（`_fonts_configured` 标志）**——chart_generation.py:54-72——多协程首调竞态（低危）。

## 三、全库交叉确认

- **「规划功能未生效」家族集中爆发**：TDC1（retry/on_failure 丢弃）→ 本轮 LLM2（input_variable/output_variable 变量）、CON1（条件分支）、DT1（merge 变量源错读）——**LLM 规划的节点参数、分支语义、数据流变量三层规划在 executor 侧全部未兑现**。家族累计：GC2 / PM2 / TDC1 / LLM2 / CON1 / DT1。
- **executor 侧关键接线确认**：`validate_params()` 被真实调用（executor.py:225）——各节点 validate 非死代码；但 `set_approval_callback` 分支条件 `self._approval_callback` 恒 False（API 层不传）→ HA1 成立。
- **双轨家族**：第 15 处 BSE1（merge_context vs `_build_node_context`）；第 16 处 DT2（两套 safe_eval）。
- **死代码家族累计第 14 处**：BSE1 merge_context。
- **SSRF 防线**：HRQ1 + HRQ2 + HRQ3 三处合围——节点层 SSRF 防护（检查 TOCTOU、变量替换绕过、重定向绕过）整条失效，配合 WS2（web_search 详情页 SSRF）构成 workflow 内网访问面。
- **与第一百三十四轮衔接**：executor 层（WFE1/WFE2/WF2）已确认缺陷，本轮下沉到节点层——`_cleanup` 回调注册 chart_generation.cleanup_all_temp_files 是唯一真实接入点，其余节点均无资源清理钩子。

## 四、测试状态

零单元测试。CE1（无沙箱执行）、HRQ1/HRQ2（SSRF 绕过）、LLM3（dict 输出字符串化）、CON1（分支不生效）、HA1（恒自动拒绝）、LLM2（变量断裂）全部实码可证无任何用例保护。修复建议：① CE1 接入 docker_runner/process_guard 沙箱或至少进程组 + 资源限制 + 输出上限；② HRQ1/HRQ2 在 execute 阶段对替换后 URL 复查 SSRF（单一解析点，拒绝而非放行）；③ LLM3 按 `response["choices"][0]["message"]["content"]` 提取；④ LLM2/CON1/DT1 收敛「LLM 规划 → executor 兑现」数据流（executor 读 branch_path 动态调整调度、context 写入 output_variable 键、merge 改读 context）；⑤ HA1 API 层提供审批端点 + executor 传回调；⑥ BSE1 删除 merge_context 收敛到 aggregator；⑦ 下轮转 aicloud/ 子包（21 文件）。
