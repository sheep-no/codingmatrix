# react_agent.py 演化深扫文档

> 版本：v0.1 | 扫描日期：2026-08-05 | 状态：已完成
> 归属：Agent 引擎 / A7 验证修复（ReActAgent 修复闭环入口）
> 路径：`app/agent/react_agent.py`（200 行）
> 索引：[TASKS.md](../TASKS.md)

## 1. 模块作用与功能

核心职责：**ReActEngine 的薄封装**（docstring :2-5「保留 ReActAgent 接口以维持向后兼容，内部委托给 ReActEngine(full 模式)」）——供 error_recovery 修复闭环调用。

主要类 / 函数：

| 类 / 函数 | 位置 | 功能 |
|-----------|------|------|
| `ReActStepType`（兼容枚举） | :24-29 | 步骤类型常量 |
| `ReActStep`（dataclass） | :32-40 | 步骤（向后兼容，timestamp/success 新字段） |
| `ReActResult`（dataclass） | :43-51 | 结果（success/final_answer/steps/execution_time） |
| `ReActAgent` | :54-199 | 主类：process 委托 ReActEngine + _call_llm 走顶层体系 |
| `DEFAULT_STAGE_MODELS` | :61-67 | 阶段模型映射（glm-z1-9b/qwen3-8b/qwen3.5-4b） |
| `process` | :113-182 | 构建工具表 → ReActEngine(full) → 转兼容格式 |
| `_call_llm` | :184-198 | 调 `app.utils.call_llm` 顶层体系，解析 OpenAI dict |

## 2. 依赖与被依赖（跨模块引用链）

### 2.1 依赖（import）

- `app.agent.executor`（:14）：EnhancedExecutor / ToolResult —— 工具注册表来源
- `app.agent.react_engine`（:15）：ReActEngine / ReActStep / ReActResult —— **被委托的引擎**
- `app.utils`（:16）：`call_llm`（= llm_caller.py:179 顶层体系，返回 OpenAI dict）
- `app.agent.memory`（:13）：AgentMemory（reflection）
- `app.agent.multi_model_agent`（:17）：ModelRegistry
- `app.agent.specialist_base`（:18）：SPECIALIST_TOOLS（fallback）

### 2.2 被消费方

- **`orchestrator_generation/error_recovery.py:19`**（唯一生产使用方）：`_try_react_auto_fix`（:9-33）构造 `ReActAgent(model_name=fallback or "Qwen/Qwen3-8B", max_iterations=5, ...)` → `process(task, {"project_path": output_dir})`
- 链路：spec_first 修复闭环 → ErrorRecoveryMixin._try_react_auto_fix → ReActAgent → ReActEngine

### 2.3 测试覆盖

- test_error_recovery.py：**1 passed**（未覆盖工具调用路径，契约断裂未被捕获——与 §9.1 同模式）

## 3. 已探明 Bug（含 bug 代码）

### RA1 [P0] 工具调用契约断裂：executor wrapper 签名不兼容 ReActEngine 注入（第二层断裂，当前被短路遮蔽）

- **现象**：ReActAgent.process 触发工具调用时，ReActEngine._execute_tool 注入 `project_path` 参数导致 TypeError
- **重要修正（2026-08-05 react_engine 深扫）**：此 TypeError **当前实际不会被触发**——react_engine.py:344 的 `project_path` 空串短路（RE1）在工具调用前就已跳过整个 ReAct 循环。RA1 是短路修复后的**第二层断裂**（react_agent.py:149 project_path="" 修好后必然触发）
- **Bug 代码**（跨模块三方）：

```python
# react_agent.py:131-139 - ReActAgent 用 ToolRegistry 的 wrapper 作为工具 fn
for name, tool_info in self.executor.tool_registry._tools.items():
    fn = tool_info.get("func")          # executor 的 wrapper（签名 wrapper(params)）
    if fn:
        tools[name] = {"fn": fn, ...}

# react_engine.py:208-209 - ReActEngine 统一注入 project_path
fn = self.tools[tool_name]["fn"]
result = fn(project_path=self.project_path, **tool_params)   # ← 关键字注入

# executor.py:204 - wrapper 签名只有 params 一个位置参数
async def wrapper(params: Dict) -> ToolResult:
```

- **根因**：`SPECIALIST_TOOLS` 的 fn 签名首参 `project_path`（兼容注入），而 ToolRegistry 的 wrapper 签名 `wrapper(params)`（只收一个 dict）——ReActAgent 用后者构建工具表，ReActEngine 按前者调用 → TypeError 被 :220-225 except 吞掉返回 `{"error": ...}`
- **实测验证**：`await fn(project_path='', file_path='...')` → `TypeError: wrapper() got an unexpected keyword argument 'project_path'`；`await fn({'file_path': '...'})` → 成功
- **影响**：error_recovery 修复闭环的工具调用全部失败（executor.md B1 的 §9.1 单例问题之上叠加的**第二层断裂**）；第一层为 react_engine.md RE1（project_path 短路，当前遮蔽本 bug）
- **触发条件**：RE1 修复（project_path 正常传递）后，任何 action 步骤必 TypeError

### RA2 [P1] `process` 的 context 参数未使用 → error_recovery 传入的项目路径被丢弃

- **Bug 代码**：

```python
# error_recovery.py:26 - 意图传项目路径
result = await react_agent.process(task_description, {"project_path": str(self.output_dir)})

# react_agent.py:113-182 - process 从未读取 context
async def process(self, task: str, context: Dict[str, Any] = None) -> ReActResult:
    ...   # 全文无 context 引用
    engine = ReActEngine(..., project_path="", ...)   # :149 project_path 硬编码空串
```

- **根因**：process 声明 context 参数但未消费；ReActEngine 创建时 `project_path=""`（:149）
- **影响**：修复闭环的工具路径上下文丢失（叠加 RA1，工具调用双重失效）
- **触发条件**：error_recovery 正常调用

### RA3 [P1] `ReActResult.success` 判定缺陷：纯文本回答任务恒判失败

- **Bug 代码**：

```python
# react_agent.py:176 - 仅当存在 action 步骤才可能成功
success=any(s.success for s in steps if s.step_type == "action"),
```

- **根因**：`any([])` = False——LLM 未调用工具直接给出 final_answer 的任务（无 action 步骤）恒判失败
- **影响**：error_recovery 对「无需工具的直接修复」也判失败（:27 `if result.success` 不成立 → 不触发验证重跑）
- **触发条件**：任何无工具调用的 process

### RA4 [P2] `DEFAULT_STAGE_MODELS` 死配置：定义未消费

- **Bug 代码**：react_agent.py:61-67 定义 5 阶段模型；:94 存入 self.stage_models；**process（:113-182）与 _call_llm（:184-198）从未引用 stage_models**——实际 LLM 调用只用 self.default_model
- **影响**：阶段模型配置无效（与 PPTAgent quality 死参同类）

### RA5 [P2] 工具 params 类型全退化

- **Bug 代码**：react_agent.py:138 `"params": {p: "string" for p in ...}`——integer/bool/array 类型信息丢失（executor 注册时保留了 JSON Schema，此处重建时退化）
- **影响**：ReActEngine 的工具 schema 全 string，LLM 参数生成质量下降

### RA6 [P2] `_call_llm` 细节

- :192 `temperature=0.7` 硬编码（忽略 `self.default_model.temperature` :87）
- :196-198 异常返回 `""`（无错误信号，空串被当 LLM 输出）
- :188 `self.default_model.name`——error_recovery:20 fallback `"Qwen/Qwen3-8B"` 硬编码模型名

## 4. 潜在问题与未知点

- **§13.2 表述修正**：「两套 ReAct 循环」应修正为「**一个引擎两个入口**」——ReActAgent 委托 ReActEngine（:146/:158），非独立第二套循环；真正的差异在 **LLM 入口**（顶层 call_llm vs LLMClient）与 **工具注册表**（ToolRegistry wrapper vs SPECIALIST_TOOLS fn）
- RA1 修复方向：wrapper 改为接受 `project_path`（并入 #6 统一工具 Schema），或 ReActAgent 直接用 SPECIALIST_TOOLS
- ReActEngine 对空 system_prompt（:158 `engine.run(task, "")`）的处理未深验
- `memory.reflection.get_insights()`（:181）调用两次，可缓存

## 5. 修改建议（改什么 → 达成什么目的）

| # | 优先级 | 修改动作 | 达成目的 | 涉及位置 | 对应 Backlog |
|---|--------|---------|---------|---------|-------------|
| 1 | P0 | RA1：统一工具 fn 签名（wrapper 接受 project_path，或 ReActAgent 用 SPECIALIST_TOOLS 构建工具表） | 修复闭环工具调用恢复 | react_agent.py:131-139 / executor.py:204 | #6、#11 |
| 2 | P1 | RA2：process 消费 `context["project_path"]` 传入 ReActEngine | 修复闭环路径上下文正确 | react_agent.py:113-149 | #11 |
| 3 | P1 | RA3：success 判定改为基于 final_answer 或任意完成步骤 | 纯文本修复不再误判失败 | react_agent.py:176 | §9.x 新增 |
| 4 | P2 | RA4：删除 DEFAULT_STAGE_MODELS 或接线 stage_models | 消除死配置 | react_agent.py:61-67 | - |
| 5 | P2 | RA5：保留工具参数类型信息 | LLM 参数生成质量 | react_agent.py:138 | #6 |
| 6 | P2 | RA6：temperature 用 default_model 值；异常返回结构化错误 | 调用参数一致、错误可观测 | react_agent.py:184-198 | - |

## 6. 演化方向关联

- **阶段二（统一收敛 §4.2/#12）**：ReActAgent 栈是「新旧路径并存」的收敛对象——与其调用方 error_recovery 一并决策（迁移到 specialist_base 体系或修复本栈）
- **统一工具 Schema（§11.4 #6）**：RA1 是工具 fn 签名统一的关键节点
- **§9.1 修复**：executor.md B1 修复须同时验证 ReActAgent 消费路径（#11）
- **Backlog 关联**：#6、#11、#12
