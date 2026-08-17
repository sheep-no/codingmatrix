# ComplexityAnalyzer 深扫（complexity.py，172 行）

> 第一百零一轮推演 | 2026-08-16 | 定位：项目复杂度/规模/技术栈/风险/成本估算（纯规则关键词分析），生成链路「架构设计前」的规模决策输入

## 1. 模块定位

对用户需求做关键词规则分析，输出 `ComplexityAnalysis`（等级/文件数/前后端/数据库/认证/技术栈/风险/token/成本），是 orchestrator_generation 链路「需求 → 架构」之间的规模预判层。

- `ProjectComplexity`（:15-21）：SIMPLE/SMALL/MEDIUM/LARGE/ENTERPRISE 五级，注释声称按文件数分级
- `ComplexityAnalysis`（:24-42）：dataclass，含 `estimated_tokens`/`estimated_cost_usd` 成本字段
- `ComplexityAnalyzer.analyze`（:58-126）：纯规则——5 组关键词 → has_* 布尔 → 文件数累加 → 等级 → token/成本估算
- `_estimate_tokens`（:128-167）：按文件数×3000 + 审查×1000 + 复杂度系数（1.0-2.0）
- `analyze_with_llm`（:169-172）：**死方法**，docstring 声称「LLM 校准/向后兼容」实际直接 return cls.analyze

**活跃模块**，消费方：

- `orchestrator_generation/mixin.py:50-51`：`self.analyzer = ComplexityAnalyzer()` + `analyze(requirement)` → complexity 注入架构 prompt（architect）
- `orchestrator_generation/evaluate_mixin.py:28-29`：同款（评价模式副本）
- `orchestrator.py:115` + `api/v1/ai_agent/orchestrate_endpoints.py:1154-1167`：`ComplexityAnalyzer()` → `LayeredModelRouter.get_assignment(complexity.level)` 决定模型分配，complexity 各字段（level/estimated_files/has_*/key_technologies/risk_factors）
- `architect.py:142-148/:272-281/:307-311/:537-546/:571-594`：complexity 注入架构设计 prompt 与约束分支
- `orchestrator_utils.py:146-150/:308`：成本估算 `_estimate_generation_cost` 的 `level` 输入（OU1 静态表）
- `orchestrator_generation/{traditional_generate,spec_first_generate,incremental_modify}.py`：complexity.level/estimated_files/has_* 注入上下文

### 依赖链

| 方向 | 模块/位置 | 说明 |
|------|-----------|------|
| 消费方 | `mixin.py:50-51` + `evaluate_mixin.py:28-29` | analyze → complexity 注入架构 prompt（活跃） |
| 消费方 | `orchestrate_endpoints.py:1154-1167` | complexity.level → LayeredModelRouter 模型分配（活跃） |
| 消费方 | `architect.py:142-148/272-281/...` | 架构 prompt 约束注入（活跃） |
| 消费方 | `orchestrator_utils.py:146-150` | `_estimate_generation_cost` 的 level 输入（OU1 静态表） |
| 测试 | `tests/unit/test_agent_capabilities.py:62-75` | 纯 print 脚本无断言（TR2 家族） |
| 测试 | `tests/unit/test_orchestrator.py:28-58` | TestComplexityAnalyzer 四用例（中等断言） |

## 2. 深扫发现

### P2 项

- **CMP1 [P2] 英文关键词子串假阳性（实测）**——`analyze` 对 5 组关键词做 `any(kw in req_lower ...)` 子串匹配，短英文词大量命中普通英文单词：实测 `"Please build a fast system"` → has_frontend=True（`'ui' in 'build'`）、`"guide to python"` → has_frontend=True（`'ui' in 'guide'`）、`"rapid development"` → has_backend=True（`'api' in 'rapid'`）、`"using a high-end device"` → has_frontend=True（`'ui' in 'using'`）——纯英文需求无前端/后端却判有前端/后端，has_* 布尔直接决定 estimated_files 累加（+5/+3）与等级（SIMPLE→SMALL）以及下游架构约束注入（architect.py:307-311/:484-493）与模型分配（orchestrate_endpoints.py:1158）——BE1/FE1/PP8 子串假阳性家族在规模决策层的实例。
- **CMP2 [P2] `estimated_tokens`/`estimated_cost_usd` 死字段 + 成本估算双轨（全库确认）**——`ComplexityAnalysis` 计算并返回 `estimated_tokens`/`estimated_cost_usd`（:110-125）但**全库零消费方**（rg 仅 complexity.py 内部，生产消费方全部只取 level/estimated_files/has_*/key_technologies/risk_factors）；实际成本估算走 `orchestrator_utils._estimate_generation_cost`（:306，OU1 静态表）→ traditional_generate.py:95-109——**同一复杂度输入，两套独立成本估算，complexity 侧的计算结果从未被使用**（CEC7/OU1 成本估算体系分裂的又一双轨实例，与 OP1 成本恒零叠加：估算字段无人读、记账金额恒零）。
- **CMP3 [P2] `analyze_with_llm` 死方法 + docstring 谎言（全库确认）**——:169-172 全库零调用（rg 仅定义处），docstring 声称「LLM 校准 / 向后兼容」但实现直接 `return cls.analyze(requirement)`，签名 `api_key_token` 参数从未使用——**声称「LLM 校准」实际纯关键词**，若未来被接线会误导（SCT5/EC8 死方法家族 + EC6 docstring 与实现不符家族）；mixin.py:50 与 evaluate_mixin.py:28 还各实例化 `ComplexityAnalyzer()` 调 classmethod（无状态，实例化无意义）。

### P3 项

- **CMP4 [P3] `key_technologies` 兜底硬编码 `['Python']`（实测）**——techs 识别只认 8 个框架词（vue/react/fastapi/django/flask/mysql/postgres/redis），无命中时兜底 `['Python']`：实测 `"write a REST API with Express and Node.js"`、`"构建一个 Go 微服务"` 全部 techs=['Python']——**伪技术栈注入架构 prompt**（architect.py:147 `技术栈：Python`），与 language_detector（LD）语言决策、project_profiler tech_stack 潜在冲突，「无技术栈时强推 Python」误导架构师。
- **CMP5 [P3] docstring 注释与实现不符**——:17-21 注释声称 SIMPLE「单文件脚本，<50行」/ SMALL「2-5 个文件」但实现按 `estimated_files` 阈值（:98-107 ≤3/≤8/≤20/≤50）分级，基础文件数恒 3（:70 main.py+requirements.txt+README.md）——「单文件脚本」永不可能 SIMPLE（恒 ≥3）；risk_factors 只是关键词命中的复述（:92-94「需要用户认证系统」等），无真实风险分析语义。
- **CMP6 [P3] 测试弱断言 + print 脚本伪测试（全库确认）**——test_agent_capabilities.py:62-75 是**纯 print 演示脚本无任何 assert**（TR2 家族）；test_orchestrator.py:28-58 四用例中等断言（test_medium_complexity 用 `in (MEDIUM, LARGE, ENTERPRISE)` 多值放行），CMP1 子串假阳性（build/guide/rapid 实测可复现）/CMP2 死字段/CMP3 死方法全部零用例保护。

## 3. 演化方向

规模决策层是生成链「需求 → 架构」的第一道量化输入，其失真会沿 `complexity.level` 扩散到模型分配（orchestrate_endpoints）、架构 prompt（architect）、成本估算（orchestrator_utils）三层：
- **匹配语义归一（CMP1）**：英文短词改词边界匹配（`\bui\b` 级别），或区分中英文词表，消除 build/guide/using 误判——与 BE1/FE1/PP8 子串家族统一修复方向。
- **成本估算收敛（CMP2）**：complexity 的 token/cost 估算并入 orchestrator_utils._estimate_generation_cost 单一来源（§5.6 支柱 1），消除双轨；或删除死字段。
- **死方法处置（CMP3）**：analyze_with_llm 删除或按 docstring 真正接入 LLM 校准（成本/耗时考虑，倾向删除）。
- **兜底语义（CMP4）**：无技术栈命中时兜底 'unknown'/空而非硬编码 Python，避免伪技术栈误导架构 prompt。
- **文档与实现对齐（CMP5）+ 测试补强（CMP6）**：注释同步真实分级逻辑；加子串/兜底/死字段用例。

**修复优先级**：CMP1（规模误判扩散三层）> CMP2（成本估算收敛）> CMP3（死方法）> CMP4（伪技术栈）> CMP5（注释）> CMP6（测试）。

## 4. 主线关联

- **「子串假阳性」横切家族**：CMP1 与 BE1（therapeutic/api→api）、FE1（preview.js→frontend_page）、PP8（db in web dashboard）、DR6（my_utils→utils）、EC2（精确模式漏检反向）同族——规则关键词匹配在规模决策/文件类型/风险判定多处失真，统一修复方向是词边界/语义匹配。
- **「双份实现/双轨」家族**：CMP2 成本估算双轨（complexity vs orchestrator_utils）与 CV4（三套 API 契约）、SCT6/DR3/TFC4（双份配置）、GO8（两套 git 快照）同族——§5.6 支柱 1 收敛对象。
- **「存在≠正确」数据层**：CMP4 伪技术栈（存在 techs 但内容错误）与 UPL2（默认值当偏好）、EC3（LogicError 兜底）同族。
- **「能力未接线」**：CMP3 死方法（SCT5/EC8/GC6 家族）——`analyze_with_llm` 声称 LLM 校准却从未接线，`estimated_*` 字段计算了从未消费。

## 5. 测试状态

**伪测试 + 弱断言，零行为覆盖**——test_agent_capabilities.py:62-75 纯 print 脚本无 assert（跑过即「通过」）；test_orchestrator.py:28-58 四用例只验证正向命中（simple→SIMPLE、含数据库→has_database 等），test_medium_complexity 用多值放行（MEDIUM/LARGE/ENTERPRISE 任一即过）。CMP1 三种子串假阳性（build/guide/rapid）、CMP2 死字段、CMP3 死方法、CMP4 Python 兜底全部实测可复现但零用例保护——测试固化「有关键词时命中」的正向语义，完全未覆盖「无关键词误命中/兜底失真/死代码」。
