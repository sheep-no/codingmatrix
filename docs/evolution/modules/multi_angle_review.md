# multi_angle_review.py 深扫详档（多角度审查系统）

> 版本：v1.89 | 日期：2026-08-13 | 行数：331 | 位置：`app/agent/multi_angle_review.py`
>
> 定位：3 角色（性能/安全/可维护性）LLM 并行多角度审查 + 魔鬼代言人兼容副本。ReviewChain 三件套（code_reviewer / ai_reviewer / multi_angle_review）最后成员。

## 关联链（消费方 / 被依赖 / 测试覆盖）

| 方向 | 关联 | 说明 |
|------|------|------|
| multi_angle_review 入口 | **零消费方** | rg 无任何 `from app.agent.multi_angle_review import` |
| devil_advocate_review | **零消费方（本模块版本）** | 实际消费的是 orchestrator_requirements/devil_advocate.py 的同名函数 |
| MultiAngleReviewSkill | agent_skills.py:66-139 | **同名不同实现**（YAML checklist 模板），:339 实例化 |
| pre_modify_review | **零消费方** | agent_skills 中调用 MultiAngleReviewSkill.review 的唯一方法，自身无人调用 |
| get_skills_manager | api/v1/ai_agent/helpers.py:197 | 仅 `get_all_skills_context()` 元数据展示 |
| devil_advocate.py（活） | mixin.py:112 → evaluate_mixin.py:93/:274 + association_endpoints.py:72 | 真实链路：需求联想魔鬼代言人 → 评估/API 展示 |
| 测试 | **零直接测试** | multi_angle_review.py / MultiAngleReviewSkill 均无测试 |

## 发现清单

### MAR1 [P2] multi_angle_review.py 顶层模块零消费方（孤儿模块）——「能力未接线」家族第七例
- `multi_angle_review` / `parallel_multi_review` / `_review_with_role` / `devil_advocate_review` / `parse_multi_review_response` / `parse_devil_response` **全库零调用**——3 角色 LLM 并行审查（docstring 声称的「严格：+ 多视角审查」）从未接线到任何生成/审查流程
- 与 UPL1/SL1/FPC1/SHS1/CC1/MDL2 同族：模块存在、实现完整、从未被调用
- 讽刺：docstring（:9-12）描述「审查严格度配置：严格 = 多视角审查」是真实存在的能力，但没有任何调用方把 severity 设成 STRICT

### MAR2 [P2] 「多角度审查」四实现同名并存（CR1 认知修正，实测）
- **CR1 第三轨定性错误已修正**：review_chain.md 原描述「MultiAngleReviewSkill：3 角色（性能/安全/可维护性）并行 review」**实测不符**——agent_skills.py:66-139 的 `MultiAngleReviewSkill` 是 **YAML checklist 模板**（_load_checklist :72-81 读 REVIEW_CHECKLIST_PATH，6 类：compatibility/security/performance/testing/documentation/operations），**纯模板生成无任何 LLM 调用**；真正的「3 角色 LLM 并行」实现是 multi_angle_review.py（本模块，孤儿）
- 全景：**四个「多角度审查」实现并存**——① code_reviewer.py CodeReviewer（活，specialist 链）② ai_reviewer.py AIReviewer（孤儿，ARV2）③ multi_angle_review.py 3 角色 LLM（孤儿，MAR1）④ agent_skills.MultiAngleReviewSkill YAML 模板（死链：唯一消费方 pre_modify_review 零调用，仅 helpers.py:197 元数据展示）
- 影响：同是「多角度审查」，四个文件、四种实现（LLM str 契约 / pydantic dict / 3 角色并行 / YAML 模板），CR1「三套」升级为「四套」；§5.6 支柱 1 的收敛对象 +1

### MAR3 [P2] 魔鬼代言人双副本 JSON 契约不一致（实测对比）
- 两个 `devil_advocate_review`：**devil_advocate.py（活）** vs **multi_angle_review.py:238（死副本）**——同一概念两套输出键：
  - 活版本（devil_advocate.py:38-48）：JSON 键 `challenges` / `target_item` / `challenge`，parse 后输出同键（:74-78）
  - 死副本（multi_angle_review.py:269-282）：JSON 键 `reviews` / `target` / `issue`，parse 后输出 `target`/`issue` + 额外 `role: "devil_advocate"`（:310-317）
- 若误接线死副本，消费方（mixin:112 → evaluate_mixin:93 拿 `devil_review_items`）会拿到键名不同的 dict——**两份实现连契约都没对齐**
- 修复方向：删死副本，活版本收敛为唯一实现

### MAR4 [P3] devil_advocate_review（multi_angle_review.py:238）architect 参数死参数
- :238-242 接收 architect，:248 起**完全不再引用**（devil_advocate.py:12 的活版本同样收了 architect 但 :14 `if not architect or len(items) < 3: return []` 只用它的存在性做空检查）
- STRICT 模式 parallel_multi_review（:125）**不传** architect，STANDARD 传（:121）——architect 在 STRICT 下静默丢弃

### MAR5 [P3] 正则贪婪匹配 `\{[\s\S]*\}` 跨块误吞（实测模式）
- :210（parse_multi_review_response）/ :300（parse_devil_response）/ devil_advocate.py:66 同款
- LLM 输出若含多个 JSON 块或围栏后补文字，从**第一个 { 贪婪吞到最后一个 }**，中间混入非 JSON 内容 → JSONDecodeError 或解析错对象（CR2 正则假阳性家族 + CV2 同类）
- 无 LLM 输出格式护栏（无重试/无多候选尝试），失败即 return [] 静默

### MAR6 [P3] DEVILS_ADVOCATE_MODEL 硬编码 + 三处直连 call_llm（LCL1）
- :197/:287（multi_angle_review.py）+ :53（devil_advocate.py）都 `from app.utils import call_llm` 直连，不走 LLMClient 信号量/成本/熔断（LCL1 家族，与 TP3/MMA3/ARV3 同源）；模型从 orchestrator_requirements/constants 硬编码导入

### MAR7 [P3] LIGHT 模式声称「仅契约检查+交叉验证」实际直接 return []
- :114-117 注释「轻量模式：仅契约检查 + 交叉验证」，实现 `return []`——**三档严格度实际只有 STANDARD/STRICT 有动作**，LIGHT 承诺的「契约检查+交叉验证」完全不存在（文档承诺 vs 实现不符家族，TP5/FD1 同类）

### MAR8 [P3] 审查失败与零问题同返回 []（静默）
- multi_angle_review / parallel_multi_review（:167-169 失败只 warning）/ devil_advocate_review 失败都 return []——消费方（mixin:112）无法区分「审查通过」vs「审查未执行」vs「审查失败」，`devil_review_items=[]` 三种语义一种表示（成功态家族，MMA2/TP7 同类）

### MAR9 [P3] parallel_multi_review role 索引依赖 REVIEW_ROLES dict 顺序
- :166 `role_name = list(REVIEW_ROLES.keys())[i]` 依赖 dict 插入序（Python 3.7+ 保序侥幸成立）——若 REVIEW_ROLES 改排序，审查结果与角色名错配

## 主线关联

- **「能力未接线」家族第七例**：UPL1 + SL1 + FPC1 + SHS1 + CC1 + MDL2 + **MAR1**；ReviewChain 三件套里两件（AIReviewer + multi_angle_review.py）是孤儿，只有 CodeReviewer 活
- **CR1 认知修正（自我纠错）**：review_chain.md 将 MultiAngleReviewSkill 描述为「3 角色并行 review」——实测它是 YAML checklist 模板且死链；真正的 3 角色 LLM 是 multi_angle_review.py 且孤儿。「多角度审查」实际是**四实现并存**（CR1 三套 + agent_skills 模板）
- **双副本契约不一致**：MAR3 是「同一概念两套输出键」——与 CR1（三套结果 schema）/DMR6（key/name 双轨）/MDL1 同属契约不一致家族；修复方向 = 死副本删除，活版本收敛
- **静默语义家族再增例**：MAR8 与 MMA2（success 恒定）/TP7（空步骤报成功）同类——失败路径无显式信号，消费方拿默认值当正常

## 测试状态

- **零测试**：multi_angle_review.py 与 MultiAngleReviewSkill 均无任何测试
- MAR1（孤儿）、MAR3（双副本键不一致）、MAR5（贪婪正则）、MAR7（LIGHT 空转）、MAR8（静默）全部可静态/实测确认但零覆盖
