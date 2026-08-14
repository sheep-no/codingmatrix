# Architect 演化深扫文档

> 版本：v0.1 | 扫描日期：2026-08-09 | 状态：已完成
> 归属：Agent 大系统 / 支撑模块（架构设计 Specialist）
> 路径：app/agent/architect.py（987 行）
> 索引：[TASKS.md](../TASKS.md)

## 1. 模块作用与功能

架构设计专家（Specialist 子类）：根据需求生成项目架构设计（api_spec/db_schema/file_plan/project_spec），含语言检测、JSON 容错解析、LLM 辅助提取降级、file_plan 完整性补充、依赖驱动扩展。是生成链路的架构设计端。

- **核心类**：`Architect`（:16，继承 Specialist）。方法：design_architecture（:107 236 行大方法）、_extract_json_with_llm（:343）、_validate_and_enhance_api_spec（:368）、_validate_and_enhance_db_schema（:392）、_safe_parse_json（:419）、_get_default_architecture（:423）、_build_default_project_spec（:549）、_parse_import_to_module（:619）、_ensure_file_plan_completeness（:652）、expand_file_plan（:794）、_generate_batch_files（:875）。

## 2. 依赖与被依赖

- **生产使用方**（4 处）：specialists.py:2 导出、orchestrator_generation/mixin.py:85（_initialize_components 实例化）、incremental_modify.py:611-612、evaluate_mixin.py:43。Architect 继承 Specialist（specialist_base.call_llm 返回 str，:88）。
- **跨模块引用**：LanguageDetector（:117）、language_detector.LanguageDetector（:425）、adapters.LanguageAdapterRegistry/ImportInfo（:676/:762）、dependency_graph.DependencyGraph（:822）。
- **测试覆盖**：tests/unit 无 architect 测试。

## 3. 已探明 Bug

### AR3 [P2] `_extract_json_with_llm` 恒失败：LLM 辅助提取 JSON 契约错配（实测）

- **Bug 代码**：

```python
# :359-366 - response 是 str（Specialist.call_llm 契约），但按 dict 解析
response = await self.call_llm(extract_prompt, "")    # → str
content = response.get("choices", [{}])[0].get("message", {}).get("content", "")   # :362 str.get → AttributeError
```

- **根因**：`Specialist.call_llm`（specialist_base.py:88）返回 `str`（委托 LLMClient.call），但 :362 用 OpenAI dict 契约（`choices[0].message.content`）访问 → str 无 `.get` → AttributeError → 被 :364-366 except 捕获返回 None。**LLM 辅助提取从未工作**（v1.11 两套 LLM 契约双轨主线的第 N 处混淆）。
- **影响**：降级链 design_architecture :286-291 = `_safe_parse_json` 失败 → `_extract_json_with_llm`（恒 None）→ **返回默认 3 文件架构**。LLM 输出稍非标准 JSON 时架构设计整体退化为默认架构，降级路径完全失效。
- **验证方式**：实测（mock call_llm 返回 str → `'str' object has no attribute 'get'`）。

### AR8 [P2] `expand_file_plan` 依赖 DG3 死方法：依赖图完整性补充分支永不执行

- **Bug 代码**：

```python
# :829-833 - get_missing_files 恒空（DG3：add_dependency 静默丢弃缺失依赖）
missing_from_graph = dep_graph.get_missing_files()
if missing_from_graph:    # :831 - DG3 确认恒 False
    architecture = dep_graph.add_missing_files(architecture)
```

- **根因**：DependencyGraph.get_missing_files（DG3 已实测恒 `[]`——add_dependency 静默丢弃缺失依赖）→ :831 条件恒 False → 依赖图完整性补充分支是死代码。expand_file_plan 只能靠 LLM 分批补充（:847 `_generate_batch_files`）。
- **影响**：依赖驱动的缺失模块识别（:830 声称「用依赖图验证完整性」）从未生效，与 DG 详档 DG3 闭环。
- **验证方式**：DG3 已实测（代码级引用）。

### AR2 [P2] `_validate_and_enhance_api_spec` 默认 api_spec 只有 health 检查

- **Bug 代码**：

```python
# :373-381 - 无 api_spec 时只生成健康检查
api_spec = {"paths": {"/api/v1/health": {"get": {...}}}}
```

- **根因**：架构师未输出 api_spec 时，默认 spec 只含 `/api/v1/health`——**业务 API 定义全部缺失但架构继续**。api_spec 缺失不阻断、不提示。
- **影响**：后端项目 API 契约无定义即进入生成 → 后续 API 契约校验（api_contract_checker/AC 链）无参照物，契约一致性形同虚设；db_schema（AR4）同源。

### AR4 [P3] `_validate_and_enhance_db_schema` 默认 users 表 + 强制 id/created_at

- **Bug 代码**：

```python
# :399-414 - 无 db_schema 时硬编码 users 表；已有表强制补 id/created_at
db_schema = {"users": {"columns": {"id": "INTEGER PRIMARY KEY AUTOINCREMENT", "created_at": ...}}}
for table, schema in db_schema.items():
    if "id" not in columns: columns["id"] = "INTEGER PRIMARY KEY AUTOINCREMENT"
```

- **根因**：默认 db_schema 只含空 users 表；已有表缺 id/created_at 时强制补 INTEGER 主键——自定义主键类型（UUID/字符串）的表不覆盖（:411 存在即跳过），但 created_at 无条件补（:414）。
- **影响**：无 schema 需求的项目数据库设计空洞；已有表被强制注入 created_at 约定。

### AR6 [P3] `_ensure_file_plan_completeness` 前端补充条件缺陷 + 多语言单适配器

- **Bug 代码**：

```python
# :721 - 有 template 类型但缺 css/js 时整个前端补充跳过
if frontend_language and not has_frontend_types and not has_html:
    frontend_files = [...]
    if not has_css: frontend_files.append(...)   # :726-729 在 :721 条件内，不可达（has_frontend_types True 时）
# :682 - 多语言项目只取一个适配器
adapter = LanguageAdapterRegistry.get_adapter(detected_lang)
```

- **根因**：:721 条件要求 `not has_frontend_types`——若 file_plan 已有 template 类型（has_frontend_types=True）但缺 style.css/app.js，整个前端补充跳过，css/js 永不补。且 :682 只按 detected_lang 取一个语言适配器，前端模块的 import 用后端适配器解析（:765 resolve_import_to_file）。
- **影响**：前端文件补充覆盖面依赖初始 file_plan 结构；多语言项目 import 解析错适配器。

### AR9 [P3] `expand_file_plan` while 循环无批次上限

- **Bug 代码**：

```python
# :838-869 - 每轮一次 LLM 调用，只有 added==0 才终止
while True:
    remaining = target_file_count - len(existing_plan)
    if remaining <= 0: break
    batch_files = await self._generate_batch_files(...)   # 每次 LLM 调用
    if added == 0: break
```

- **根因**：无最大批次保护，target_file_count 大时多轮 LLM 串行调用（每轮加少量文件），成本与延迟随目标文件数线性增长。
- **影响**：大项目 file_plan 扩展多轮 LLM 调用，成本/延迟不可控。

### AR10 [P3] `_generate_batch_files` 单次 LLM 调用无重试

- **Bug 代码**：

```python
# :941-987 - 单次调用，失败/空返回 return []
response = await self.call_llm(prompt, self.SYSTEM_PROMPT)
```

- **根因**：无重试、无降级；LLM 瞬时失败或空输出直接返回空列表，本轮扩展零进展。
- **影响**：扩展鲁棒性依赖 LLM 单次成功率。

### AR12 [P3] prompt f-string 双重转义 `{{{{` 示例格式瑕疵

- **Bug 代码**：

```python
# :162-167 - 示例 JSON 过度转义（{{{{ → 输出 {{），LLM 可能照输出双括号
{{{{"file_plan": [  ...  ]}}}}
```

- **根因**：f-string 里 JSON 示例用 4 层大括号转义，实际输出为双大括号 `{{"file_plan":`——给 LLM 的示例非标准 JSON，可能诱导 LLM 输出错误格式（触发 AR3 降级链）。
- **影响**：示例格式瑕疵间接放大解析失败率。

### AR14 [P3] `_safe_parse_json` 异常面：design_architecture 只捕获 ValueError

- **Bug 代码**：

```python
# :286 - 只捕获 ValueError，_safe_parse_json 抛其他异常直接向上
except ValueError:
    architecture = await self._extract_json_with_llm(...)
```

- **根因**：:286 只捕获 ValueError（JSONDecodeError 是子类），json_parser.safe_parse_json 若抛 TypeError/其他异常不捕获 → 异常向上抛中断设计。
- **影响**：容错面窄，非标准输出异常路径不全。

### AR16 [P3] `_get_default_architecture` 未知语言 dep_file="README.md"

- **Bug 代码**：

```python
# :476 - 未知语言依赖文件退化为 README.md
dep_file = "README.md"
```

- **根因**：LanguageDetector 未知语言的默认架构把依赖配置写成 README.md（非依赖清单）。
- **影响**：未知语言项目默认架构缺真实依赖文件。

## 4. 修复建议

- **AR3**：:362 按 str 契约解析（`json.loads(response)` 或 _safe_parse_json 处理），与 Specialist.call_llm 返回类型对齐。
- **AR8**：修 DG3 后此分支自动激活；或 expand_file_plan 改用 _ensure_file_plan_completeness 的 import 解析补缺。
- **AR2/AR4**：api_spec/db_schema 缺失时显式 warning 并在生成端跳过契约校验（避免形同虚设），或从需求补缺。
- **AR6**：前端补充条件改为分别检查 css/js 缺失（不依赖 has_frontend_types 整体短路）；多语言按文件类型选适配器。
- **AR9**：加 max_batch 上限。
- **AR10**：加一次重试。
- **AR12**：修正 f-string 转义为单层。
- **AR14**：扩大 except 到 (ValueError, TypeError, json.JSONDecodeError)。
- **AR16**：未知语言 fallback 到通用依赖文件命名。

## 5. 待实测项

- AR3 已实测（str.get AttributeError 确认）。
- AR8 为 DG3 已实测闭环引用（代码级）。
- AR2/AR4/AR6/AR9/AR10/AR12/AR14/AR16 为代码级结论。
