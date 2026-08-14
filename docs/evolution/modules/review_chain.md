# 审查链深扫详档（code_reviewer.py + ai_reviewer.py + multi_angle_review.py）

> 版本：v1.64 | 日期：2026-08-09 | 文件：`code_reviewer.py`（168 行）+ `ai_reviewer.py`（223 行）+ `multi_angle_review.py`（331 行）
> 结论：**P2 3 项（CR2 实测、CR1/CR3 静态）、P3 3 项**｜单元测试：零（test_error_recovery.py 用 mock reviewer，非直接覆盖）

## 定位

生成链的**审查门禁**：代码生成后由审查员判定 approved/needs_fix，决定是否进入修复循环或放行。本库存在**三套审查实现**，生成链实际生效的是 CodeReviewer（Specialist 子类）。

## 跨模块引用链

| 方向 | 模块 | 位置 | 用途 |
|------|------|------|------|
| 被消费（活跃） | mixin.py | :88 `CodeReviewer("审查员", _get_model("reviewer_model"...), task_type="review")` | spec_first/传统链的 reviewer gate |
| 被消费 | error_recovery.py | `reviewer` 注入（`if strategy_id` 同链） | 修复循环审查 |
| 被消费 | specialists.py | re-export CodeReviewer | 统一出口 |
| 被消费（孤儿） | multi_model_agent.py | :71 `AIReviewer(default_model, api_key_token=...)`；:209 `self.reviewer.review_plan(steps)` | 重构 re-export 壳内使用，**生成链不用** |
| 被消费（死链） | agent_skills.py | `MultiAngleReviewSkill`（:66-139） | skill 框架内多角度审查——YAML checklist 模板，唯一消费方 pre_modify_review 零调用，仅 helpers.py:197 元数据展示 |
| 依赖 | specialist_base.call_llm | CodeReviewer 走 `-> str` 契约（:88 标注，与 AR3 同一来源） | LLM 调用 |
| 依赖 | app.utils.call_llm（llm_caller.py:179） | AIReviewer 走 `-> Union[dict, AsyncIterator[str]]` 契约 | LLM 调用 |
| 依赖 | app.agent.json_parser.safe_parse_json + file_contract.ReviewResult | AIReviewer 解析 | 结果契约 |
| 依赖 | .claude/skills/orchestrator/（multi_angle） | prompt 目录（存在，有默认兜底） | 角色 prompt |
| 测试 | — | — | **零直接测试** |

## 关键代码路径

`CodeReviewer.review_code`（code_reviewer.py:57）：`_check_version_compatibility` 本地版本检查 → call_llm（str）→ 搜 ```json 块解析 → 合并 version_issues → 返回 Dict。`AIReviewer.review_code/review_plan`（ai_reviewer.py:31/:144）：app.utils.call_llm（dict）→ safe_parse_json → `ReviewResult.model_validate`（pydantic）→ 返回 ReviewResult。

## Bug 清单

### P2

**CR1 [P2] 三套审查实现并存，LLM 契约与结果 schema 三轨（静态确认）**

- CodeReviewer（生成链活跃）：Specialist 体系——call_llm 返回 str（specialist_base.py:88），`re.search(r'```json...')` + `json.loads` 解析，返回裸 Dict（:102）；版本问题用本地子串规则
- AIReviewer（孤儿）：独立体系——app.utils.call_llm 返回 dict（llm_caller.py:179），safe_parse_json + `ReviewResult.model_validate`（pydantic，file_contract），返回类型化结果
- MultiAngleReviewSkill（skill 框架）：**YAML checklist 模板**（agent_skills.py:66-139，_load_checklist 读 REVIEW_CHECKLIST_PATH，6 类模板无 LLM 调用，死链），非「3 角色 LLM 并行」——真正的 3 角色 LLM 实现在 multi_angle_review.py（孤儿，见 [multi_angle_review.md](multi_angle_review.md) MAR1/MAR2）
- 影响：同是「审查代码」，**四套实现**（CodeReviewer 活 / AIReviewer 孤儿 / multi_angle_review.py 3 角色 LLM 孤儿 / MultiAngleReviewSkill YAML 模板死链）、三种 LLM 契约、三种结果 schema、三份解析器。§5.6 支柱 1（统一 LLM 契约/验证器协议）的直接收敛对象；修复统一后可消除两套解析器（re vs safe_parse_json）
- 修复方向：以 CodeReviewer 为唯一活跃实现收敛；AIReviewer 的 ReviewResult pydantic 模型可保留为统一结果类型，MultiAngleReviewSkill 定位为严格级扩展（注：CR1 第三轨描述已修正，原「3 角色」为认知错误）

**CR2 [P2] CodeReviewer 版本兼容检查子串假阳性 + 本环境版本误用（实测）**

- 位置：`_check_version_compatibility`（:104）——:146 `if removed_api in code`、:152 `if old_api in code` **子串匹配**（注释/字符串/文档文字均命中）；VERSION_RULES 用 `importlib.metadata.version(本环境包)` 判断生成代码
- 实测（本环境 fastapi v0.136.1）：
  ```
  注释 "# 本项目使用 Middleware 模式" → ["[fastapi v0.136.1] API 'Middleware' 在 v0.100.0+ 中已移除"]
  字符串 s = "OAuth2PasswordBearer 的使用示例" → ["[fastapi v0.136.1] 建议将 'OAuth2PasswordBearer' 改为 'tokenUrl -> token_url'"]
  干净 fastapi 代码 → []
  ```
- 影响：review_code :94-100 version_issues 合并 → `result["needs_fix"]=True` + risk_level 升 medium → **合法代码被审查 gate 拦入修复流程**（浪费一次修复循环/人工审查）。且本环境（生成环境）包版本与用户运行环境无关，版本断言语义错位
- 修复方向：子串匹配改为 import 语句 AST 级匹配（`re.findall` 的 import 已提取，但 removed/changed 的 API 检查未限定到 import 行）；或仅作提示不设 needs_fix

**CR3 [P2] AIReviewer 实际随 multi_model_agent 重构壳处于非活跃路径（静态确认）**

- multi_model_agent.py 自述「v5.14 重构：拆分为独立模块，此文件保留向后兼容 re-export」，AIReviewer 唯一实例化点 :71 在其内部；生成链（mixin:88）明确用 CodeReviewer
- 影响：AIReviewer 的 review_code/review_plan 完整实现（含 degraded 强制拒绝逻辑 :189-198）基本无人触达——**审查器的 LLM 审查能力存在两套、活跃仅一套**，属死代码收敛范围（与 CR1 同源）

### P3

**CR4 [P3] CodeReviewer.SYSTEM_PROMPT 每次调用查注册表**

- `code_reviewer.py:20` `get_skill("code_reviewer_prompt")` 每次 review 都查——同 BE5/FE5 prompt 加载问题

**CR5 [P3] VERSION_RULES 仅 4 个库硬编码 + 生成环境版本误用**

- fastapi/sqlalchemy/pydantic/passlib 4 库；判断基准是生成环境已装版本而非目标运行环境——覆盖极低且语义错位（见 CR2）

**CR6 [P3] multi_angle_review 依赖 .claude/skills/orchestrator 目录**

- `_SKILLS_DIR`（:28）相对 `__file__` 计算，目录存在时读 prompt，不存在走内置默认（:47-48 有兜底，风险低）

## 与既有主线闭环

- **§5.6 支柱 1（协议统一）**：审查链是三套实现三套契约的最典型模块——与 LLM 契约双轨（BE7/FE7 'fn'/'function'）、architect AR3（dict 契约错误方）同属「契约不一致」家族，且审查是唯一同时出现两套 LLM 客户端契约（specialist str vs app.utils dict）的横切层
- **验证语义主线**：审查 gate 是「存在≠正确」的语义闸门之一；CR2 假阳性使合法代码被拦（修复循环浪费），配合 UT5（验证执行空转）——拦截侧过严、执行侧过松，双向失真
- **§5.6 支柱 5（阶段门禁 Gate）**：审查员是生成到验证之间的门禁，三轨并存使门禁行为不可预测（走 CodeReviewer 与走 AIReviewer 结果语义不同）
