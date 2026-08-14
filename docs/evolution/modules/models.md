# models.py 深扫详档（ModelRegistry / ModelRouter）

> 版本：v1.88 | 日期：2026-08-13 | 行数：385 | 位置：`app/agent/models.py`
>
> 定位：从 multi_model_agent 拆出的**模型注册表与路由器**，是 TaskType/AgentRole/ModelCapability 三枚举 + ModelInfo 数据类 + ModelRegistry（静态注册表）+ ModelRouter（route / route_dynamic / get_role_model / route_by_content）的单一文件。multi_model_agent 的路由消费端（:156/:183/:184/:124/:179）与 task_planner 的默认模型都依赖此文件。

## 关联链（消费方 / 被依赖 / 测试覆盖）

| 方向 | 关联 | 说明 |
|------|------|------|
| 消费 route/route_dynamic | multi_model_agent.py:156/:183-185 | 分析类与步骤路径模型选择 |
| 消费 route_by_content | multi_model_agent.py:124/:179 | task_type 推断 |
| 消费 DEFAULT_*_MODEL | orchestrator_files.py（:373/:571-575/:677/:721/:774-779）、error_recovery.py（:45-47/:466-473）、template_extractor.py（:10-11）、project_metadata.py（:13-14）、refinement_loop.py（:87-88）、spec_first_generator.py（:117-118）、orchestrator_generation/*（mixin:75-88、evaluate_mixin:43-48、incremental_modify:613-625、spec_first_generate:487/:1048/:1654/:2162/:2248） | 大量当 model name 传 call_llm |
| get_role_model | **零消费方** | 完整实现无人调用 |
| 测试 | 无专项测试 | test_providers 测的是 aicloud ProviderRouter（同名 route 无关） |

## 发现清单

### MDL1 [P3] DEFAULT_*_MODEL 常量语义双轨 + 注释错误（实测）
- :66 注释「与 ModelRegistry 中的 key 对应」**与事实相反**：4 个常量值全是 **name 格式**（`nex-agi/Nex-N2-Pro` / `deepseek-ai/DeepSeek-R1-0528-Qwen3-8B` / `THUDM/GLM-Z1-9B-0414` / `Qwen/Qwen3-8B`），对应 key 是 `nex-n2-pro` / `deepseek-r1-qwen3-8b` / `glm-z1-9b` / `qwen3-8b`
- 实测：`ModelRegistry.get(DEFAULT_CODE_MODEL)` 等 4 个按 key 查**全 None**，`get_by_name` 才命中
- 业务代码把它们当 name 传 call_llm 是**正确用法**（大量消费方无碍），但 `ModelRegistry.get()`（期望 key）与 DEFAULT 常量（name）双轨并存无护栏，任何 `get(DEFAULT_*)` 的误用静默得 None
- orchestrator_files.py:774-779 的 alt_map 混用常量（name）与字面量 `"Qwen/Qwen3-8B"`（:776，同 name），进一步固化双轨
- 方向：注释修正 + 常量改为直接引用注册表（或提供 `get_default_model(role)` 统一入口），消除 key/name 双轨

### MDL2 [P2] get_role_model 零消费方（5×5 角色路由孤立）——「能力未接线」家族第六例
- `get_role_model`（:288-334）完整实现（COMPLEXITY_LEVELS 校验 + get_assignment_with_learning + role_to_attr + role_fallbacks）但 **rg 全库零调用**——5×5 角色分配矩阵路由从未接入任何业务代码
- multi_model_agent 的模型选择实际走 route/route_dynamic（:156/:183-185）；reviewer 模型切换是 :199-207 的**内联重复实现**（get_dynamic_router + get_assignment_with_learning + ModelRegistry.get + 写 self.reviewer.model），既不调 get_role_model 也未复用其 role_to_attr/role_fallbacks 映射
- 与 UPL1/SL1/FPC1/SHS1/CC1 同族：模块存在、实现完整、从未被调用；MMA3 的 reviewer 切换竞态点（:203 写共享实例）正落在内联副本上
- 方向：multi_model_agent:199-207 收敛为调用 get_role_model（或依赖注入），消除第二份映射表

### MDL3 [P3] get_role_model 的 complexity 参数虚设（实测，MMA7 深化）
- :306-307 只校验 complexity ∈ COMPLEXITY_LEVELS（非法回退 MEDIUM），此后 **complexity 从未参与任何决策**——get_assignment_with_learning() 不带 complexity 参数，静态 fallback 也不看复杂度
- docstring「基于 5×5 模型分配矩阵」（:294）名不副实：无矩阵表，只有角色维度，复杂度维度只是合法参数检查
- 与 MMA7（route_dynamic 签名无 complexity）呼应：**复杂度在路由端有两个入口都未生效**（route_dynamic 没收、get_role_model 收而不用）
- 方向：要么给 get_assignment_with_learning 传 complexity 真正影响分配，要么删掉参数；5×5 矩阵复杂度维度需要真实映射表

### MDL4 [P2] route_by_content 关键词顺序歧义（实测）
- 分类器顺序敏感：IMAGE_GENERATION → OCR → VISUAL → CODE_REVIEW → REASONING → FILE_OPERATION → CODE_GENERATION → FAST_RESPONSE → GENERAL，先到先得无优先级设计
- 实测歧义两例：
  - `'分析文件内容'` → **reasoning**（REASONING 的「分析」:370 抢走本属 FILE_OPERATION 的「文件」:373）
  - `'帮我检查一下环境配置'` → **code_review**（CODE_REVIEW 的「检查」:367 误伤运维类输入）
- 反例证明非全坏：`'读取文件并总结'`→file_operation、`'检查代码质量'`→code_review、`'识别图片中的文字'`→ocr 均正确
- 方向：关键词打分制（每类权重累加取最高）替代先到先得；「检查」/「分析」等泛词需要限定词（代码/文件/内容）消歧

### MDL5 [P3] route_by_content 死代码分支（实测）
- :379 第二个 REASONING 分支**恒不可达**：关键词集合（推理/reasoning/思考/分析）被 :370 完全覆盖，且含 `" reasoning"`（前导空格）拼写残留
- 实测 `'写个函数计算和'`→code_generation、`'hello world'`→fast_response 说明主链路正常，死分支纯冗余

### MDL6 [P3] TASK_MODEL_MAP 覆盖不全
- TaskType 12 枚举值只映射 10 个：**REACT / PLANNING 缺失**，route 与 route_dynamic 对这两类都落默认 `["deepseek-r1-qwen3-8b"]`（:247/:272）
- 多模型路由的「多模型」承诺在 2 个任务类型上退化为单模型

### MDL7 [P3] route_dynamic 每次调用导入 + 实例化路由器
- :270/:278/:283 三处每次调用都 `from app.agent.dynamic_model_router import get_dynamic_router` + `await get_dynamic_router()`——单例重复获取（DMR 本身设计为单例，此处无功能错误，但每任务 3 次导入 + 异步工厂调用，MMA3 同类）
- 方向：router 实例作为模块级缓存或依赖注入

## 主线关联

- **「能力未接线」家族第六例**：UPL1 + SL1 + FPC1 + SHS1 + CC1 + **MDL2**——get_role_model 是模型中实现最完整却零消费的方法，且其内联副本（multi_model_agent:199-207）恰好是 MMA3 竞态点，收敛为单一调用既是接线又是去重
- **复杂度虚设家族**：MMA7（route_dynamic 无 complexity）+ **MDL3**（get_role_model 收而不用）——「按角色+复杂度路由」文档承诺的复杂度维度在两个入口都未生效
- **key/name 双轨**：MDL1 是模型标识双语义（DMR6 的 model key 语义同源）——注册表按 key 索引、业务按 name 传参，注释与实现相反
- **分类器歧义**：MDL4 与 CR2/CD3/UPL5 同属关键词/子串启发式家族——顺序敏感分类器在「分析文件内容」场景实测误判，消歧方向 = 打分制 + 限定词

## 测试状态

- **零专项测试**：无 test_models.py；models 相关断言只存在于 multi_model_agent/task_planner 的间接测试
- MDL1（key/name 错配）、MDL3（complexity 虚设）、MDL4（歧义）、MDL5（死分支）全部实测可复现但**未被任何测试捕获**
- test_providers.py 的 `router.route(...)` 是 aicloud 的 ProviderRouter，与 ModelRouter 无关（同名干扰）
