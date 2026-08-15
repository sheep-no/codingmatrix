# PPTAgent 演化深扫文档

> 版本：v1.0 | 扫描日期：2026-08-14 | 状态：已完成
> 归属：Agent 引擎 / PPT 生成（D 大系统关联）
> 路径：app/agent/ppt_agent.py（420 行）
> 索引：[TASKS.md](../TASKS.md)

## 1. 模块作用与功能

- PPT Agent——自然语言到 PPT 大纲：接收自然语言主题/描述，调用 LLM 生成结构化 JSON 大纲（`PresentationOutline`），输出符合 aiGeneratorPptx.py PPTX 引擎消费的格式；支持重试、校验、格式化回退。
- 主要组成：
  - `SlideType` 枚举（:26-34）：7 种幻灯片类型。
  - `SlideOutline` / `PresentationOutline` dataclass（:37-63）：大纲数据模型，含 to_dict / to_json 序列化。
  - `PPTAgent` 类（:66）：
    - `generate_outline`（:82-128）：主入口，prompt → call_llm → JSON 解析（LLM 兜底）→ 重试 3 次 → fallback。
    - `_build_prompt`（:130）：构造生成 prompt（页数/title/end/字数约束）。
    - `_parse_with_llm_fallback`（:161-194）：JSON 解析失败时走 LLM 辅助提取。
    - `_extract_json_with_llm`（:196-259）：用 LLM 从非标准输出提取 JSON（raw_text 前 3000 字符）。
    - `_validate_outline`（:261-295）：校验并转换 JSON → `PresentationOutline`（类型白名单、强制 title/end、超页 pop(-2) 截断）。
    - `_fallback_outline`（:297-311）：重试耗尽后的模板大纲（title+目录+内容+end）。
    - `adapt_for_pptx_engine`（:313-327）：静态方法，适配为 PPTX 引擎格式。
    - `modify_outline`（:329-407）：根据修改请求修改已有大纲（LLM + 重试 + 降级返回原大纲）。
    - `_dict_to_outline`（:409-420）：字典 → `PresentationOutline`。
- 对外接口：`generate_outline` / `modify_outline` / `adapt_for_pptx_engine` / `PPTAgent`。

## 2. 依赖与被依赖

- 导入依赖：`app.utils.call_llm`（直连顶层 LLM 调用，不走 LLMClient）、`app.agent.architect_json_parser.ArchitectJsonParser`、`app.services.skill_registry.get_skill`（自定义 system_prompt，异常静默）。
- 生产使用方：`app/api/v1/aiGeneratorPptx.py` 3 处——:1582 `generate_ppt_from_text`（结构化大纲接口）、:1624 `generate_ppt_from_text_task`（端到端任务）、:1637 `adapt_for_pptx_engine`（转引擎格式）。两接口均 `PPTAgent(model=req.model)` 实例化。
- 测试覆盖：**零测试**。tests/ 下无 ppt_agent / PPTAgent 引用（AJP1 的 json_parser 用例也未测 PPT 消费路径）。

## 3. 已探明 Bug（含 bug 代码）

### PPT1 [P2] `modify_outline` 加页请求被 `_validate_outline` 截断删错页（实测）

- **现象**（实测）：existing 大纲 4 页（title+c1+c2+end），用户请求「加一页」，LLM 正确返回 5 页（插入 NEW），但 `modify_outline` 传 `len(existing.slides)=4` 作 num_slides → `_validate_outline` `while len(slides) > 4: pop(-2)` 删倒数第二页 c2 → 返回 4 页 `['T', 'c1', 'NEW', '谢']`——**新增页保留但原有 c2 被删，页数不变**，用户请求的加页未生效且丢失原有内容。
- **Bug 代码**：
  ```python
  # ppt_agent.py:392-397 modify_outline 把「现有页数」当目标页数
  outline = await self._parse_with_llm_fallback(
      content,
      existing_outline.get("title", "PPT"),
      len(existing_outline.get("slides", [])),   # 强制与修改前页数相同
      api_key_token
  )
  # ppt_agent.py:289-290 _validate_outline 超页从倒数第二删
  while len(slides) > num_slides:
      slides.pop(-2)
  ```
- **根因**：`modify_outline` 不应限制修改后页数等于原页数；且 `pop(-2)` 从倒数第二删会优先删掉靠近结尾的内容页（可能正是新增/修改的页）。
- **影响**：修改大纲的「增删页」能力失效——加页被截断回原页数并误删内容页；用户对生成结果的编辑信任被破坏。
- **触发条件**：修改请求导致 LLM 返回页数 > 原页数。
- **验证方式**：见上实测——existing 4 页 + LLM 返回 5 页 → 结果 4 页且 c2 被删。

### PPT2 [P2] `generate_outline` 不遵守 num_slides（少页不补，实测）

- **现象**（实测）：请求 `num_slides=10`，LLM 返回 3 页（title+content+end），`_validate_outline` 只做超页截断不做少页补齐 → 返回 3 页。prompt 要求「总页数必须等于 {num_slides}」（:137）但结果页数与请求页数可任意不符。
- **Bug 代码**：
  ```python
  # ppt_agent.py:289-291 只有超页收缩，无少页补齐
  while len(slides) > num_slides:
      slides.pop(-2)
  return PresentationOutline(title=..., slides=slides)  # 3 页 → 3 页
  ```
- **根因**：`_validate_outline` 页数校验单向（只缩不补）；prompt 约束靠 LLM 自觉，无程序强制。
- **影响**：用户请求 10 页得到的 PPT 可能只有 3 页；`/generate-text` 响应的 `total_slides` 与实际页数不符（OutlineGenerationResponse.total_slides=len(outline.slides)，aiGeneratorPptx.py:1604）。
- **触发条件**：LLM 返回页数 < num_slides（常见于 LLM 压缩内容）。
- **验证方式**：mock call_llm 返回 3 页 JSON，`generate_outline('T','',10)` 返回 3 页。

### PPT3 [P2] AJP1 认知修正：null/标量 JSON 在 ppt_agent 路径**静默降级不崩溃**，但消耗全部重试（实测）

- **现象**（实测）：`safe_parse_json('null')` 返回 None 后 `_validate_outline(None)` **不抛 AttributeError 崩溃**——`_validate_outline` 内部 `try: ... except Exception: return None`（:263/:293-295）捕获 AttributeError 返回 None → `_parse_with_llm_fallback` 返回 None → `generate_outline` 进入下一重试 → 3 次耗尽后走 `_fallback_outline`。
- **Bug 代码**：
  ```python
  # ppt_agent.py:180-184 _parse_with_llm_fallback 只捕获 ValueError
  try:
      data = parser.safe_parse_json(raw)          # null → None 不 raise
      return self._validate_outline(data, ...)    # None → 内部捕获返回 None
  except ValueError:                              # AttributeError 不在此
      ...
  ```
- **根因**：architect_json_parser.md AJP1 记录「ppt_agent.py:258 data.get 抛 AttributeError 且外层 except ValueError 捕获不了 → 未处理崩溃」——**该断言对当前版本不成立**：`_validate_outline` 自带 `except Exception` 兜底，实际行为是「静默降级为模板大纲」。崩溃路径只在 architect.py:277（TypeError 无兜底）成立。
- **影响**：LLM 输出 null/标量/非 JSON 时，PPT 生成静默得到模板占位大纲，用户无错误提示；且每次 null 输出消耗一次完整 LLM 调用（3 次重试全浪费）。
- **触发条件**：LLM 返回顶层标量（`null`/`123`/`"文本"`）或非法 JSON。
- **验证方式**：`_validate_outline(None, 'T', 5)` 返回 None（日志「大纲验证失败: 'NoneType' object has no attribute 'get'」），generate_outline 重试 3 次后 fallback。

### PPT4 [P2] `_fallback_outline` 页数边界不符（num_slides=1/2 仍返回 3 页，实测）

- **现象**（实测）：`_fallback_outline('T', 1)` / `('T', 2)` 都返回 3 页（title+chapter+end）——`range(2, num_slides-1)` 在 num_slides≤2 时为空但 title+chapter+end 固定 3 页，请求 1 页却得 3 页。
- **Bug 代码**：
  ```python
  # ppt_agent.py:297-311
  slides = [SlideOutline(type="title", ...), SlideOutline(type="chapter", title="目录", ...)]
  for i in range(2, num_slides - 1):   # num_slides=2 → range(2,1) 空
      ...
  slides.append(SlideOutline(type="end", ...))
  ```
- **根因**：fallback 模板页数硬编码（title+chapter+end 至少 3 页），不校验 num_slides 下界。
- **影响**：极端页数请求（1/2 页）的降级输出页数不符；与 PPT2 构成页数语义在正常/降级两路径都不一致的完整面。
- **触发条件**：`num_slides ≤ 2` 且 LLM 全部失败走 fallback。
- **验证方式**：`_fallback_outline('T', 1)` 返回 3 页。

### PPT5 [P2] 模型硬编码双份 + call_llm 直连（LCL1 家族）

- **现象**（静态）：`PPT_DEFAULT_MODEL = "THUDM/GLM-Z1-9B-0414"` 在 `ppt_agent.py:23` 与 `aiGeneratorPptx.py:62` **两份定义**；`generate_outline`（:104）/`_extract_json_with_llm`（:238）/`modify_outline`（:379）三处直连 `app.utils.call_llm`，不走 LLMClient 信号量/成本记录/流式超时；无 DynamicModelRouter 路由（模型名硬编码，绕 DMR）。
- **Bug 代码**：
  ```python
  # ppt_agent.py:23 与 aiGeneratorPptx.py:62 双份常量
  PPT_DEFAULT_MODEL = "THUDM/GLM-Z1-9B-0414"
  # ppt_agent.py:104/238/379 直连
  raw = await call_llm(model=self.model, prompt=prompt, ...)
  ```
- **根因**：PPT 链路独立于 Agent 引擎主生成链路，未接入统一 LLM 层（架构收敛前遗留）。
- **影响**：PPT 生成无并发信号量保护（高并发 PPT 请求直接打满上游）、无成本记录（OP1 成本主线）、模型不可路由/熔断。
- **触发条件**：持续存在——所有 PPTAgent LLM 调用。
- **验证方式**：`grep -n "call_llm" app/agent/ppt_agent.py` 三处 + `grep -c "PPT_DEFAULT_MODEL" app/api/v1/aiGeneratorPptx.py` 3 处引用（:62/:87/:1560）。

### PPT6 [P3] `quality` 参数收而不用（声明即空转）

- **现象**（静态）：`__init__(self, model=None, quality="balanced")`（:72-80）收取 quality 但仅注释「保留用于未来扩展」，从不影响 prompt/temperature/页数——调用方 aiGeneratorPptx.py:1584/:1628 传 `PPTAgent(model=req.model)` 也未传 quality。
- **Bug 代码**：
  ```python
  # ppt_agent.py:78
  quality: str = "high_quality/balanced/fast/creative" - 保留用于未来扩展
  # 构造后 self.quality 从不被任何方法读取
  ```
- **根因**：API 面预留参数未接线（CLH2/SL2 data_dir 虚设家族同类）。
- **影响**：前端若暴露质量选择，实际不生效；API 契约（请求含 quality 字段）与实现空转。
- **触发条件**：调用方传入非默认 quality。
- **验证方式**：`rg "self.quality" app/agent/ppt_agent.py` 无读取点（仅 :72 参数与 docstring）。

### PPT7 [P3] bullets/image_keywords 静默截断无提示

- **现象**（静态）：`_validate_outline` 每页 `bullets=[:6]`（:272）、`image_keywords=[:3]`（:273）静默截断，prompt 约束（:138「每页 bullets 不超过 6 条」）外 LLM 超量内容被丢弃零日志。
- **Bug 代码**：
  ```python
  # ppt_agent.py:272-273
  bullets=s.get("bullets", [])[:6],
  image_keywords=s.get("image_keywords", [])[:3],
  ```
- **根因**：截断无标记（JP2 静默补全/截断家族）。
- **影响**：用户要求展示 8 条要点时静默丢 2 条；配图关键词超 3 个被丢弃影响配图质量。
- **触发条件**：LLM 返回 bullets>6 或 image_keywords>3。
- **验证方式**：构造 10 条 bullets 的 JSON 走 `_validate_outline` → 结果 6 条。

### PPT8 [P3] bullets 单条 40 字上限无强制校验

- **现象**（静态）：prompt 要求「每条不超过 40 字」（:138），但 `_validate_outline` 无长度校验——LLM 输出超长 bullet 原样透传。
- **Bug 代码**：`ppt_agent.py:268-278` 无任何 `len(bullet) > 40` 检查。
- **根因**：prompt 软约束无程序强制（约束注入 vs 强制执行落差家族）。
- **影响**：超长 bullet 进入 PPTX 渲染可能导致溢出/换行错乱（aiGeneratorPptx 无再校验）。
- **触发条件**：LLM 返回超 40 字 bullet。
- **验证方式**：构造 60 字 bullet 走 `_validate_outline` → 原样保留。

### PPT9 [P3] `_extract_json_with_llm` 截断无标记

- **现象**（静态）：`_extract_json_with_llm` 用 `raw_text[:3000]`（:214）截断输入，无「已截断」标记——LLM 修复基于不完整文本。
- **Bug 代码**：
  ```python
  # ppt_agent.py:214
  {raw_text[:3000]}
  ```
- **根因**：截断语义与 JP2 同类（TR2 家族：无标记的静默截断）。
- **影响**：超长 LLM 输出提取 JSON 时后半段丢失，修复结果残缺。
- **触发条件**：raw_text > 3000 字符且首轮解析失败。
- **验证方式**：构造 4000 字符输入走 `_extract_json_with_llm`（mock call_llm 断言收到的 prompt 截断）。

## 4. 潜在问题与未知点

- **`_build_prompt` 的 JSON Schema 用 `{{ }}` 转义正确**（:141-152），但 LLM 常输出 markdown 代码块包裹 JSON——`safe_parse_json` 的 thinking 清理层（JP3 只清 `<thinking>` 标签，不含 ```json 代码块）是否兜底未验证。
- **`adapt_for_pptx_engine` 字段冗余**：每页同时输出 `slide_type` / `type` / `content` / `bullets` 四字段（:320-324），`content` 与 `bullets` 语义重复，消费端 aiGeneratorPptx 用哪个字段未确认。
- **`get_skill("ppt_system_prompt")`**（:95-100）：异常静默 + 每次 generate_outline 调用都查 registry（CR4/FE5 SYSTEM_PROMPT 家族），且与 `_build_prompt` 内置 system_prompt 并存双源。
- **temperature 不一致**：主生成 0.7（:108）、提取 0.3（:244）、修改 0.5（:383）三个值硬编码，无配置化。
- **PPT_DEFAULT_MODEL 与 aiGeneratorPptx 请求默认值**（:87/:1560 `Field(default=PPT_DEFAULT_MODEL)`）——用户可传 model 覆盖，但默认模型名双份同步风险。

## 5. 修改建议（改什么 → 达成什么目的）

| # | 优先级 | 修改动作 | 达成目的 | 涉及位置 | 对应 Backlog |
|---|--------|---------|---------|---------|-------------|
| 1 | P2 | `modify_outline` 不传 `len(existing.slides)` 作 num_slides：改为「仅校验 title/end/类型，不限制页数」或让 LLM 输出明确目标页数 | 加页/删页修改请求真正生效，不误删内容页 | ppt_agent.py:392-397 | #471 |
| 2 | P2 | `_validate_outline` 页数双向校验：少页时按模板补内容页（复用 _fallback_outline 逻辑）到 num_slides | 生成结果页数遵守用户请求（PPT2 主修） | ppt_agent.py:289-291 | #472 |
| 3 | P2 | 修正 architect_json_parser.md AJP1 的 ppt_agent 断言：从「未处理崩溃」改为「静默降级不崩溃但消耗重试」；generate_outline 在 `_parse_with_llm_fallback` 返回 None 时提前 break 不重试 | 文档准确反映行为（认知修正）；null 输出不浪费 3 次 LLM 调用 | architect_json_parser.md / ppt_agent.py:119 | #473 |
| 4 | P2 | `_fallback_outline` 校验 num_slides 下界（<3 时去 chapter 或直接 title+end） | 极端页数降级输出符合请求 | ppt_agent.py:297-311 | #474 |
| 5 | P2 | PPTAgent 的 call_llm 统一改走 LLMClient（信号量/成本/超时），模型名经 DynamicModelRouter，删除 aiGeneratorPptx.py:62 重复常量 | PPT 链路接入统一 LLM 层（LCL1 收敛范围），成本可见、并发受控、模型可路由 | ppt_agent.py:104/238/379、aiGeneratorPptx.py:62 | #475 |
| 6 | P3 | quality 参数接线到 prompt/temperature/页数策略，或从 API 面移除 | 参数或有效或移除，消除声明空转 | ppt_agent.py:72-80 | #476 |
| 7 | P3 | bullets/image_keywords 截断加日志或加 `_truncated` 标记 | 截断可观测，用户/前端可知内容被裁 | ppt_agent.py:272-273 | #477 |
| 8 | P3 | `_validate_outline` 增加 bullet 长度校验（超 40 字截断+日志） | 防止超长内容进 PPTX 渲染 | ppt_agent.py:268-278 | #478 |
| 9 | P3 | `_extract_json_with_llm` 截断加「...（已截断）」标记 | LLM 修复时知道文本不完整 | ppt_agent.py:214 | #479 |

## 6. 演化方向关联

- **阶段判定**：PPT Agent 是独立于 Agent 引擎主链路的附属生成能力，处于「拆分解耦」遗留态——模型名/LLM 调用双份实现（PPT5），尚未收敛到统一 LLM 层。
- **LCL1 家族**：PPT5 三处直连 call_llm 是 LCL1 收敛范围的又一名成员（与 MAR6/SE4/AE3/TP3 同源）——PPT 是少数仍活跃消费 call_llm 的链路，收敛后成本记录覆盖扩面。
- **「存在≠正确」页数语义**：PPT2/PPT4 使生成页数与请求页数在正常/降级两路径都不一致，与 OU1 估算失真、SM13 不可观测同属「声称 vs 实际」落差；`total_slides` 响应字段（aiGeneratorPptx.py:1604）如实反映错误页数反而暴露不一致。
- **AJP1 认知修正**：PPT3 证实 architect_json_parser.md 对 ppt_agent 的「崩溃」断言过时（`_validate_outline` 有 except Exception 兜底）——「存在≠正确」在文档层面同样成立：AJP1 记录的行为与实际代码不符，需同步修正，避免后续按错误基线修复。
- **静默降级家族**：PPT3（null→模板大纲）/ PPT7（截断无标记）与 DMR1/MEM1 的「降级语义不符」同源——用户看到成功结果但内容是占位/残缺。
