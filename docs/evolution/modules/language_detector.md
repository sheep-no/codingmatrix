# language_detector.py 深扫详档

> 版本：v1.61 | 日期：2026-08-09 | 文件：`app/agent/language_detector.py`（775 行）｜方法 11 个（detect 主链 6 策略 + LLM 辅助 2 + 工具 3）
> 结论：**P2 5 项、P3 3 项**（全部实测或静态确认）｜单元测试：零

## 定位

需求文本 → 目标语言 + 适配器名 + 语言规则。全库语言决策唯一入口，架构生成（architect）、文件生成（backend/frontend_engineer）、增量修改（incremental_modify）、spec_first 生成（spec_first_generate）的**第一道决策**。

## 跨模块引用链

| 方向 | 模块 | 位置 | 用途 |
|------|------|------|------|
| 被消费 | architect.py | :285 `ln.detect(requirement)`；:55-102 `get_language_specific_rules` 构建 prompt 语言规则 | 主链语言决策 |
| 被消费 | frontend_engineer.py / backend_engineer.py | `ln.ln(project_language)` | 语言规则注入 prompt |
| 被消费 | incremental_modify.py / spec_first_generate.py | `ln.detect(requirement)` | 增量/spec 链语言决策 |
| 被消费 | architect.py | `LanguageAdapterRegistry.ln(files_for_detection)` → adapters/language_adapter.py | 文件级语言识别（detect 的下游） |
| 消费 | adapters/language_adapter.py | `_adapters["generic"]`（generic.py:416） | `adapter_name="generic"` 的落点存在 |
| 测试 | — | — | **零测试** |

## 关键代码路径

`detect()`（:210）检测链：策略 0 全栈检测 → 策略 1 框架推断（FRAMEWORK_LANGUAGE，命中即 return 0.95）→ 策略 2 语言关键词（按长度降序 `\b` 匹配，命中即 return）→ 策略 3 文件扩展名（0.85）→ 策略 4 项目类型默认（0.60）→ 策略 5 中文模式（0.70/0.40）→ 默认 Python 0.30。

## Bug 清单

### P2

**LD1 [P2] C# 关键词 `\bc#\b` 边界失效 → 最常见 C# 需求全部降级默认 Python（实测）**

- 位置：`:69` 关键词 'c#' + `:266` `\b` + `re.escape` 通用边界匹配
- 现象：`#` 是 `\W`，`\b` 只在 `\w`↔`\W` 交界生效。"请用 C# 写一个项目"（`#` 后空格）与 "用C#开发工具"（`c` 前中文 `\w`）前后边界都不成立
- 实测：
  ```
  detect("请用 C# 写一个项目")  → python 0.30（默认 fallback）
  detect("开发一个 C# 桌面应用") → python 0.30
  detect("用C#开发工具")         → python 0.30
  detect("开发 ASP.NET Core...") → csharp 0.95（asp.net 无 # 边界问题，正常）
  ```
- 影响：C# 是顶层关键词（:69）且有规则（get_language_specific_rules 无 csharp → 见 LD5），但最常见表达「C# 写/开发」全数漏检 → 架构层得到 python 0.3 → 错误语言规则进 prompt。**与策略 3 扩展名 `.cs` 无联动（ext map 也不含 cs）**，两条自救路径都断
- 修复方向：特殊字符关键词（`c#`、`c sharp`、`asp.net`）用自定义 pattern（如 `(?:^|[\s(（])c#\s`），`\b` 仅适用于纯 `\w` 关键词

**LD2 [P2] 策略 3 扩展名正则吞中文 → "app.py文件" 漏配（实测）**

- 位置：`:285` `r'\.(\w+)(?:\s|，|。|,|\.|$)'` —— `\w` 默认含中文，`\w+` 贪婪吞下紧贴的中文；分隔符白名单不含中文
- 实测：`detect("用 app.py文件 开发")` → 扩展名阶段 `ext_matches=['py文件']` 不在地图 → 跳过策略 3；而 `"main.py 和 utils.js"` → `['py','js']` 正常
- 影响：中文需求（库主场景）里「xx.py文件」「xx.js文件」是最常见提法，全部漏配 → 依赖策略 2 的 'py'/'js' 关键词（同样 `\bpy\b` 对 "py文件" 有效因为 py 后是中文 `\w` 边界成立）——即靠关键词兜底，扩展名策略形同虚设
- 修复方向：`\w` 换 `[A-Za-z0-9_]+`，且后接 `(?=\s|[，。;；,\.]|$)` 或 `(?![\u4e00-\u9fff])`

**LD3 [P2] LLM 辅助检测是死代码——docstring 宣称的策略 5 从未接线（静态确认）**

- 位置：`_detect_with_llm_sync`（:502）/`_detect_with_llm`（:533）定义于类内，**全库无任何调用方**（rg 确认仅本文件两处定义）
- 现象：`detect()`（:210-387）六策略无一处调用 LLM 分支；`_check_language_conflict`（:472）返回值只写 evidence（:272-273 注释自认「仅用于日志记录，不改变检测结果」）
- 影响：`detection_method` 字段恒 "rule"；模块 docstring 承诺的「检测结果可能存在冲突时使用 LLM 上下文感知检测」未实现。冲突场景（如 "用 Python 但提到 express"）无仲裁机制，直接按首个命中关键词返回
- 修复方向：在策略 2 命中冲突（`_check_language_conflict` 返回非 None）或置信度过低时触发 `_detect_with_llm_sync`，并用结果覆盖——正是 §5.6 支柱 1 的契约化体现

**LD4 [P2] LLM 分支 typescript 必被拒（静态确认）**

- 位置：`:594-601` `lang_aliases = {"ts": "typescript", ...}` → `:603` `if primary_lang not in valid_languages`（valid_languages = LANGUAGE_KEYWORDS.keys()）
- 现象：LANGUAGE_KEYWORDS 无 "typescript" 键（typescript 被归入 javascript 列表 :51）；LLM 若按常识返回 `"primary_language": "typescript"`，alias 后仍是 "typescript"，`not in valid` → `return None` → 整个 LLM 检测失败
- 影响：即使 LD3 修复接线，LLM 对 TS 需求（前端主流）的处理路径仍断裂。规则层 `detect("用 typescript 写")` 返回 javascript（实测），LLM 层却拒绝——两层语义不一致
- 修复方向：valid 校验用 adapter_map 键集或显式允许 "typescript"→"javascript" 归一化

**LD5 [P2] csharp 规则返回 needs_clarification=True——顶层语言被当未知语言（实测）**

- 位置：`get_language_specific_rules`（:748-762）fallback 分支，`LANGUAGE_EXTENSION_MAP.get("csharp")` 为 None（:122-146 无 csharp 键）→ 返回 `needs_clarification=True`
- 现象：csharp 在 LANGUAGE_KEYWORDS（:69）、adapter_map（:633）均是一等语言，唯独扩展名映射表缺项
- 影响：architect `_build_language_rules_text`（:58-61）收到 clarification → 让 LLM「根据语言名称推断扩展名」（放弃内置规则），且与 LD1（C# 检测失效）叠加时架构 prompt 完全无 C# 语言约束
- 修复方向：LANGUAGE_EXTENSION_MAP 补 `"csharp": ".cs"`；顺带核对其他一等语言是否缺项（php 有、ruby 有、kotlin/swift/dart 有，仅 csharp 缺）

### P3

**LD6 [P3] `\bgo\b` 匹配英文动词（实测）**

- 位置：`:62` 关键词 'go'
- 实测：`detect("Please go to the market")` → go 0.95（「关键词匹配: 'go' → go」）
- 影响：英文需求（README/API 文档式描述）出现 "go" 动词即误判 Go 语言。中文需求风险低
- 修复方向：关键词加 `golang`/`go 语言`/`go lang`，'go' 单字降权（置信度打折）或仅在无其他命中时考虑

**LD7 [P3] 冲突检测只记录不裁决（静态确认）**

- 位置：`:269-273` conflict 仅 append evidence；`:247/:281/:317/:331` 各策略命中即 return，multi 检测结果只进 `all_languages` 字段
- 现象：`detect("Python 后端 + Rust 性能模块")` → python，evidence 含「检测到冲突（已忽略）: 检测到 python，但需求中也提到了 rust」——冲突被静默忽略
- 影响：与 LD3 同源（裁决机制缺失）；all_languages 正确时架构侧能拿到额外语言，不算功能断裂
- 修复方向：并入 LD3 统一处理

**LD8 [P3] adapter_map 含 "typescript" 但 LANGUAGE_KEYWORDS 无此键（静态确认）**

- 位置：`:629` `"typescript": "javascript"`；:38-119 无 "typescript" 语言键
- 现象：`_get_adapter_name("typescript")` 可达但 detect 永不产出该语言名；`valid_languages` 校验（:591）不认 "typescript" → 与 LD4 同源
- 修复方向：并入 LD4

## 与既有主线闭环

- **「存在≠正确」验证链延伸**：语言决策（LD1/LD2 漏检 → 错误语言/默认 python）→ architect prompt 语言规则错误 → 生成错误语言代码 → 验证执行端（UT5 空转）不拦截 —— 检测端 + 验证端双失效叠加
- **LLM 契约双轨**：detect 返回 dataclass（契约正确方），但 LLM 分支 JSON 契约（`r'\{[^{}]+\}'` 只匹配无嵌套对象 :576）与 AR3 同类脆弱；规则层优先 0.95 恒定，LLM 辅助因死代码（LD3）永不竞争
- **§5.6 支柱 1（契约先行）**：语言检测是所有生成链的入口决策，应作为统一协议首验对象；LD3/LD4 是「检测结果可能冲突→LLM 裁决」缺失契约的直接后果
