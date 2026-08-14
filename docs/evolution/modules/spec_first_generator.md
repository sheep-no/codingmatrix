# spec_first_generator.py 演化深扫文档

> 版本：v0.1 | 扫描日期：2026-08-05 | 状态：已完成
> 归属：Agent 引擎 / Spec-First 生成器（架构师角色，A2 规范阶段）
> 路径：`app/agent/spec_first_generator.py`（536 行）
> 索引：[TASKS.md](../TASKS.md)

## 1. 模块作用与功能

核心职责：**规范先行生成器**——在任何代码生成之前，把需求转化为四类可验证规范基线，作为后续代码生成的引用标准：

1. **OpenAPI 规范**（:170-280）：全部 API 端点/请求响应/数据模型——**主链，失败即整个流程失败**
2. **类型定义**（:282-336）：语言原生类型（python pydantic / ts interface / go struct / java POJO / rust serde），**依赖 OpenAPI**
3. **数据库 Schema**（:338-401）：表结构/关系/索引（SQLAlchemy / Prisma / GORM / JPA / SeaORM），**依赖 OpenAPI**
4. **配置规范**（:403-451）：环境变量 + .env.example + 配置类（pydantic-settings / dotenv / Viper / yml / config crate），独立

**执行链**：`generate_all_specs`（:123-168）→ OpenAPI 失败则中断；types/db/config 失败仅 warning 继续。后续代码生成经 `get_spec_context_for_file`（:501-536）按文件类型注入对应规范。

**与 spec_first_generate.py（2383 行 SpecFirstGenerateMixin）关系**：非近似重复——本类是**独立生成器**（536 行），被 refinement_loop/incremental_modify 复用；spec_first_generate 是 orchestrator 层完整编排（含缓存/复杂度/验证）。

## 2. 依赖与被依赖（跨模块引用链）

### 2.1 依赖（import）

- `app.utils`（:20）：`call_llm`（顶层直连，**非 LLMClient**——无并发控制/成本追踪，§10.1 直连文件）
- `app.agent.shared_context`（:21）：SharedContext（specs 存取/start_phase/error 记录）
- `app.agent.models`（:117）：DEFAULT_ARCHITECT_MODEL
- `app.agent.orchestrator`（:119）：LayeredModelRouter（**经 orchestrator 中转导入**，实为 dynamic_model_router.py:707 的 DynamicModelRouter 别名）
- `app.agent.json_parser`（:457）/ `app.agent.utils`（:465）：运行时导入

### 2.2 被消费方

| 使用方 | 位置 | 用途 |
|--------|------|------|
| `refinement_loop.py:522` | 精炼循环 | **只读** `get_spec_context_for_file`（不生成） |
| `spec_first_generate.py:110` | orchestrator 编排 | 完整生成（language + api_key_token） |
| `incremental_modify.py:243` | 增量修改 | 完整生成 |
| `get_spec_budget` 调用方 | spec_first_generate.py:405/:965、incremental_modify.py:729/:941 | 静态方法，4 处（**非死代码**） |

### 2.3 测试覆盖

- 查 tests：需确认是否有 test_spec_first_generator（test_spec_first_generator.py 存在，见下）

## 3. 已探明 Bug（含 bug 代码）

### SFG1 [P1] `generate_all_specs` 返回值语义与实现不符

- **Bug 代码**：

```python
# spec_first_generator.py:131-133 - docstring 声称语义
"""Returns:
    True 如果所有规范都成功生成
"""
# spec_first_generator.py:168 - 实际只检查 OpenAPI
return openapi_success
```

- **根因**：types/db/config 失败仅 `add_warning`（:149/:156/:163）不改变返回值——「全部成功」vs「仅 OpenAPI 成功」调用方无法区分
- **影响**：调用方（spec_first_generate/incremental_modify）对规范链完整性判断失真

### SFG2 [P1] 规范链部分失败不阻断：依赖链断裂但流程照常

- **Bug 代码**：OpenAPI 失败 return False（:142）；types/db **依赖 OpenAPI**（:284/:340）但失败仅 warning（:149/:156）——OpenAPI 成功 + types 失败的「半规范」状态被当作可继续
- **影响**：后续代码生成在类型/DB 规范缺失时仍进行（默认类型兜底），规范先行理念打折

### SFG3 [P2] OpenAPI 生成不走 model_config：max_tokens/temperature 硬编码

> **实测确认（2026-08-05，静态断言）**：grep `self.model_config` 仅 :317/:382/:432（types/db/config 三处）引用；OpenAPI 主链调用 :199-200 硬编码 `max_tokens=8192, thinking_budget=4096`（:120 计算后未传入）——OpenAPI 是主链（失败即整个流程失败），却绕开按上下文窗口动态计算的模型配置。

- **Bug 代码**：

```python
# spec_first_generator.py:199-201 - OpenAPI 固定值
max_tokens=8192, thinking_budget=4096, temperature=0.5,
# 同文件 :317/:382/:432 - types/db/config 用 model_config
max_tokens=self.model_config["max_tokens"], thinking_budget=self.model_config["thinking_budget"],
```

- **影响**：模型配置（按上下文窗口动态计算）对 OpenAPI 生成不生效；`self.model_config` 只在 :317/:382/:432 用，:120 计算后对 OpenAPI 无效

### SFG4 [P2] `_generate_types` 无 openapi 类型防御（与 `_generate_db_schema` 不一致）

- `_generate_db_schema` 有 str 类型防御（:342-346 重新解析）；`_generate_types` 仅 `if not openapi_spec`（:284-286）——若 openapi_spec 为 str，:307 `json.dumps(openapi_spec, ...)` 输出字符串字面量浪费 token

### SFG5 [P2] OpenAPI list 递归提取逻辑复杂

- **Bug 代码**：:216-267 多级 while/for 嵌套（list→dict/list/str 三型分支 × 策略 1/2/3），维护困难；`[[], []]` 空 list 分支（:222-224）依赖 while 条件 `len>0` 退出——能终止但语义晦涩

### SFG6 [P2] 四步生成直连 call_llm：无并发控制/成本追踪/动态路由

- 全部走 `call_llm`（:195/:313/:378/:428）非 LLMClient——§10.1 直连文件之一；且 architect_model 单模型固定（:118），无故障转移/降级链（除 call_llm 内部 fallback）

### SFG7 [P2] LayeredModelRouter 经 orchestrator 中转导入

- **Bug 代码**：:119 `from app.agent.orchestrator import LayeredModelRouter`——orchestrator.py:20 从 dynamic_model_router re-export（动态模型路由体系），llm_client.py:22 直接从 dynamic_model_router 导入——**同一类两条导入路径**，spec_first_generator 多一层间接（且 orchestrator 是编排层，作为类依赖来源引入循环风险）

### SFG8 [P2] `_report_progress` 的 callback task fire-and-forget

- :480-482 task 引用 + done_callback discard（正确模式），但生成流程结束时不等待 pending tasks——流式回调可能滞后

## 4. 潜在问题与未知点

- 四步 LLM 调用**串行**（OpenAPI→types→db→config 顺序依赖），总时延高；无并行化（config 独立本可并行）
- `context.save_spec`（:274/:330/:395/:445）每次都全量保存 spec——无增量/去重
- architect_model 从 `context.model_assignment`（:118）读取——模型分配与 §13 的动态路由体系衔接待验
- get_spec_context_for_file 的 `max_chars_per_spec` 截断（:517/:523/:529/:534）为粗粒度 `[:N]`——JSON 规范可能被截断成非法 JSON 注入 prompt（`json.dumps(...)[:N]` 切在中间）

## 5. 修改建议（改什么 → 达成什么目的）

| # | 优先级 | 修改动作 | 达成目的 | 涉及位置 | 对应 Backlog |
|---|--------|---------|---------|---------|-------------|
| 1 | P1 | SFG1：返回值改为 `(openapi, types, db, config)` 或记录失败清单 | 调用方可感知规范链完整性 | spec_first_generator.py:168 | 新增 |
| 2 | P1 | SFG2：types/db 失败时降级策略显式化（标记 spec 缺失状态） | 规范链断裂可感知 | spec_first_generator.py:146-163 | 新增 |
| 3 | P2 | SFG3：OpenAPI 也走 model_config | 模型配置全局一致 | spec_first_generator.py:199-201 | 新增 |
| 4 | P2 | SFG7：改从 dynamic_model_router 直接导入 | 消除编排层依赖 | spec_first_generator.py:119 | 新增 |
| 5 | P2 | SFG-截断：截断按 `json.dumps` 前先 parse 再截或截断后补全 | prompt 注入合法 JSON | spec_first_generator.py:517 | 新增 |

## 6. 演化方向关联

- **§15（双 spec_first 文件）**：本类是独立生成器，spec_first_generate 是编排——**生成逻辑唯一性确认**（规范生成不重复）
- **§10.1 直连体系**：SFG6 是 26 直连文件之一（无并发/成本控制）
- **Backlog 关联**：#7、#12，新增 SFG1-SFG7
