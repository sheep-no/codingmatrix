# Workflow 聚合与分解（result_aggregator + task_decomposer）

> 第一百三十五轮补扫 | v1.136 | 2026-08-17 | 分析对象：`app/utils/workflow/result_aggregator.py`（309 行）+ `task_decomposer.py`（263 行）
>
> 结论：**聚合器与分解器首次建档——task_decomposer 丢弃 LLM 规划的 retry/on_failure 字段（「提取≠生效」）、用户请求含花括号即分解失败；result_aggregator 流式输出切片索引错误（若接入即丢事件）且 stream_results/export_results 全库零消费**。

## 一、模块定位

| 组件 | 位置 | 消费状态 |
|------|------|----------|
| ResultAggregator | result_aggregator.py:20 | executor.py:311/:350/:375/:397 真实消费；workflow.py:333/:354（status 端点，上轮 WF3 确认恒拿不到真实实例 → 实际死路径） |
| TaskDecomposer | task_decomposer.py:86 | workflow.py:124/:125 真实消费 |
| stream_results / export_results | result_aggregator.py:230/:276 | **全库零消费——死代码（executor 用自身事件回调流）** |
| get_upstream_results | result_aggregator.py:86 | 全库零消费——死方法（executor 用 get_context 替代） |
| validate_result | task_decomposer.py:218 | 全库零消费——与 GraphValidator 重复死实现 |
| decompose_request | task_decomposer.py:248 | 全库零消费——workflow.py 直接实例化 TaskDecomposer |

链路（承接第一百三十四轮）：`POST /workflow/execute` → TaskDecomposer.decompose（LLM 自然语言→TaskGraph）→ GraphValidator.validate → WorkflowExecutor.execute → ResultAggregator.record_result/get_context/get_workflow_summary。

## 二、缺陷清单

### P2（7 项）

- **TDC1 [P2] LLM 规划的 `retry`/`on_failure` 字段被丢弃——失败策略/重试策略从未生效**——task_decomposer.py:203-208 `TaskNode(id=..., type=..., params=..., depends_on=...)` **只取四字段**——而系统提示词（:44-45）明确要求 LLM 返回 `retry: {"max_retries":2,...}` 与 `on_failure: "fail|skip"`——schema TaskNode 有 on_failure 字段（schema/workflow.py:61）——**LLM 规划的容错策略整块丢失，所有节点回落到默认 fail**——「提取≠生效」家族（GC2/PM2 同族）。修复方向：透传 retry/on_failure 到 TaskNode。
- **TDC2 [P2] 用户请求含花括号 → `str.format` 抛异常 → 分解接口报错**——task_decomposer.py:152 `USER_PROMPT_TEMPLATE.format(request=request)`——用户自然语言请求含 `{...}`（「帮我生成 {'name': 'x'} 的配置」）→ **KeyError/ValueError 在 :138 被 except 捕获 → 抛 TaskDecomposerError「任务分解失败」**——真实用户输入（LLM 任务规划场景常见 JSON/模板示例）直接使分解失败（PL1 同族：str.format 只适合受控模板）。
- **TDC3 [P2] `validate_result` 与 GraphValidator 重复死实现——双轨验证器且都验证不充分**——task_decomposer.py:218-245 与 graph_validator.py:40-58 逻辑重叠（ID 唯一/依赖存在/类型合法）——**validate_result 全库零消费**（workflow.py:127 用 GraphValidator）——重复实现 + 两者都不校验参数语义（上轮 GV1）——**同一能力双实现且都漏语义校验**。
- **TDC4 [P2] decompose 内部零校验——LLM 输出重复 id/无效依赖直接构造 TaskGraph**——task_decomposer.py:194-209 无任何查重/依赖存在检查——`validate_result`（:218）本可内联却未调用——完全依赖下游 GraphValidator 拦截，LLM 输出劣质图时白跑一次 LLM 调用（GV1 同族）。
- **RSA1 [P2] `stream_results` 切片索引错误——首次轮询只发最后一个节点事件**——result_aggregator.py:253 `self._completed_order[last_count - 1:]`——last_count 初始 0 → 首次进入 `_completed_order[-1:]` **取最后一个**——之前的节点完成事件全部丢失（本应 `last_count:` 或先加 1）——当前零消费未暴露，**接入 SSE 即事件错乱**。
- **RSA2 [P2] `stream_results` + `export_results` 零消费死代码——聚合器三套输出结构并存**——executor 用自身回调事件流 + `get_workflow_summary`（:397）——stream_results（:230）/export_results（:276）全库零调用——**死代码家族累计第 13 处**。
- **RSA3 [P2] `is_complete()`/summary 与 WFE1 呼应——未执行节点使完成率失真**——result_aggregator.py:149 `len(_node_results) == len(nodes)`——WFE1 场景（B 永久 PENDING）下 _node_results 缺 B → is_complete=False → executor 已 break 但 summary 返回 pending_nodes>0、completion_rate<1.0——API 的 workflow_completed 事件 status=running + completion_rate 不齐——「报告≠实际」家族在聚合层的镜像。

### P3（8 项）

- **RSA4 [P3] `_build_node_context` 每次 record 全量遍历 `_node_results`——O(n²)**——result_aggregator.py:197——大图逐步记录时反复全表扫描（只应取当前节点上游）。
- **RSA5 [P3] `get_upstream_results` 零消费死方法**——result_aggregator.py:86——executor 用 get_context 替代，此方法从未被调用。
- **RSA6 [P3] `get_workflow_summary` 返回 `_completed_order` 直接引用——外部可改内部状态**——result_aggregator.py:227（非 copy，对比 get_all_results/get_execution_order 有 copy）。
- **RSA7 [P3] `_node_results`/`_node_contexts` 无锁 + `params = node.params` 引用共享**——result_aggregator.py:38-41/:194——节点修改 params 污染全图（低危，STM1 同族）。
- **TDC5 [P3] `_load_system_prompt` 模块级 import 副作用读盘 + 文件缺失静默降级内置默认**——task_decomposer.py:93 `SYSTEM_PROMPT = _load_system_prompt()`——每次 import 读文件；skills/workflow-planner/system_prompt.md 缺失时静默用内置 prompt 无告警（AIU2/EC3 家族）。
- **TDC6 [P3] DEFAULT_MODEL 硬编码 `deepseek-ai/DeepSeek-R1-0528-Qwen3-8B` + temperature 0.3 硬编码 + 直连顶层 call_llm**——task_decomposer.py:18/:129——与 dynamic_model_router 配置脱离（LCL1/SPFG17 家族）。
- **TDC7 [P3] `decompose_request` 便捷函数零消费死代码**——task_decomposer.py:248——workflow.py 直接实例化 TaskDecomposer。
- **TDC8 [P3] 响应解析健壮性缺口**——task_decomposer.py:165-192——choices 无 content 时 `content.strip()` None 崩（:169/:177）、多 JSON 块无容错、`str(response)` dict 兜底必 json.loads 失败——解析失败抛 TaskDecomposerError（健壮性差但错误路径明确）。

## 三、全库交叉确认

- **「提取≠生效」家族**：TDC1 与 GC2（全局约束提取成功却被丢弃）、PM2（伪功能写入）同族——**LLM 分解规划重试/失败策略但下游丢弃**。
- **死代码家族累计第 13 处**：RSA2（stream_results/export_results）+ RSA5（get_upstream_results）+ TDC3（validate_result）+ TDC7（decompose_request）——聚合/分解模块内部大量完备封装未接入。
- **双轨家族第 14 处**：TDC3 validate_result vs GraphValidator——同一验证能力两实现。
- **格式串注入家族**：TDC2 与 PL1（prompt_loader str.format）同族——`str.format` 对不可控输入不安全。
- **与第一百三十四轮衔接**：RSA3 是 WFE1（executor 状态卡 RUNNING）的聚合侧表现——executor + aggregator + status 端点三处同一根因（状态生命周期未收敛）。

## 四、测试状态

零单元测试。TDC1（retry/on_failure 丢弃）、TDC2（花括号分解失败）、RSA1（切片丢事件）全部实码可证无任何用例保护。修复建议：① TDC1 透传策略字段；② TDC2 模板改占位符替换（template.replace 或 format_map 防御）；③ RSA1 修切片；④ TDC3/validate_result 删除或收敛到 GraphValidator；⑤ 下轮扫 node_types/ 10 节点文件（base.py merge_context 契约）。
