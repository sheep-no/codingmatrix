# FrontendEngineer 演化详档

- 文件：`app/agent/frontend_engineer.py`（326 行）
- 扫描日期：2026-08-09
- 状态：✅ 已完成
- 模块定位：前端工程师 Specialist——生成前端文件、分析模式。与 BackendEngineer 同构（姊妹模块）

## 职责

1. `SYSTEM_PROMPT`（:17）：skill_registry → 默认 → 兜底
2. `_infer_file_type_from_path`（:40-55）：从路径推断前端 file_type（template/frontend_style/frontend_page/frontend_component/test）
3. `_build_spec_constraints`（:58+）：project_spec 约束 → prompt
4. `generate_file`（:87-239）：生成单个前端文件；ReAct 只读工具循环
5. `analyze`（:240-326）：只读分析

## 消费方

- `spec_first_generate.py`/`traditional_generate.py`/`incremental_modify.py`：generate_file 三链路消费（前端文件）
- 测试状态：**零单元测试**

## 实测确认的 bug

### FE1 [P2] `_infer_file_type_from_path` 子串假阳性（BackendEngineer BE1 姊妹 bug）

- 位置：:47-52 `'page' in path_lower or 'view' in path_lower` / `'component' in path_lower` / `'test' or 'spec' in path_lower`
- 实测：
  - `preview.js` → 'frontend_page'（view 命中 preview——**普通 JS 组件误判为页面**）
  - `interval/page.tsx` → 'frontend_page'（page 命中 interval）
  - `passage.ts` → 'frontend_component'（未被 page/view 命中，走 endswith 兜底）
- 影响：file_type 决定 :130 `project_spec.get(file_type)` 约束注入——前端页面/组件/样式约束错配（如页面级路由约束注入组件）
- 对照：:43-46 对 .html/.css 用 endswith 精确匹配（正确），:47 起退化子串

### FE7 [P2] `analyze` 工具访问键 'function' 错误（BackendEngineer BE7 姊妹 bug）

- 位置：:280 `list_files_tool['function']`
- 实测：`SPECIALIST_TOOLS['list_files']` 键是 'fn'（tools.py:1184）→ 'function' 恒 KeyError → except 吞掉 → project_files 恒空 → analyze 项目结构读取从未生效
- 对照：generate_file 走 call_llm_with_tools → ReActEngine `_execute_tool`（react_engine.py:208）用 `["fn"]` 正确

## 其余发现

### FE5 [P3] SYSTEM_PROMPT 每次调用重新加载（同 BE5）

- 位置：:17 property

## 修复优先级

| 项 | 级别 | 关键点 |
|---|---|---|
| FE1 | P2 | 前端 file_type 误判 → 约束错配 |
| FE7 | P2 | analyze 结构读取恒空 |
| FE5 | P3 | 提示词重复加载 |

## 关联

- **BE1/BE7 姊妹问题**：BackendEngineer 与 FrontendEngineer 同款两个 bug——工具键 'function' vs 'fn' 已在全库出现 2 处（generate_file 路径全对、analyze 路径全错），提示 `SPECIALIST_TOOLS` 访问应封装统一 getter
- **LLM 契约双轨**：generate_file 返回 call_llm 的 str（契约正确方）
- **五支柱（§5.6 支柱 1）**：前端产物生产者，BE1 姊妹问题同样污染产物内容
