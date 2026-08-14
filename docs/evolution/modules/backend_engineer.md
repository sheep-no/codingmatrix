# BackendEngineer 演化详档

- 文件：`app/agent/backend_engineer.py`（356 行）
- 扫描日期：2026-08-09
- 状态：✅ 已完成
- 模块定位：后端工程师 Specialist——生成后端文件、分析模式。`generate_file` 是文件生成链路的执行端之一（spec_first/traditional/incremental 三链路的 LLM 内容生产者）

## 职责

1. `SYSTEM_PROMPT`（:17）：skill_registry 自定义 → 默认加载 → 兜底
2. `_infer_file_type_from_path`（:40-63）：从路径推断 file_type（model/api/service/repository...）
3. `_build_spec_constraints`（:66-101）：project_spec 约束 → prompt
4. `generate_file`（:104-267）：生成单个后端文件；有 project_path 时走 ReAct 工具循环（只读工具），否则普通 call_llm
5. `analyze`（:270-356）：只读分析模式

## 消费方

- `spec_first_generate.py`/`traditional_generate.py`/`incremental_modify.py`：generate_file 三链路消费（内容 → extract_engineer_content 处理）
- `specialist_base.py:88 call_llm`：返回 str（v1.11 契约）
- 测试状态：**零单元测试**

## 实测确认的 bug

### BE1 [P2] `_infer_file_type_from_path` 子串假阳性——file_type 误判注入错误约束

- 位置：:43-62 `'api' in path_lower` / `'app' in path_lower` / `'db' in path_lower`
- 实测：
  - `therapeutic/api.py` → 'api'（therapeutic 含 "api" 子串，实际该文件是 controller 还是 service 未知）
  - `capital/service.py` → 'api'（capital 含 "api"——**真实 service 文件被判成 api**）
  - `apple.py` → 'entry'、`happened.py` → 'entry'（含 "app"）
  - `web/db_utils.py` → 'database'（db 超短子串）
- 影响：file_type 决定 `project_spec.get(file_type)` 注入的约束（:130-131）——**错误 file_type → 错误框架/存储/术语约束注入 prompt**，LLM 按错约束生成

### BE7 [P2] `analyze` 工具访问键 'function' 错误（实际为 'fn'）——项目结构读取从未生效

- 位置：:310 `list_files_tool['function']`
- 实测：`SPECIALIST_TOOLS['list_files']` = `{'fn': <func>, 'description': ..., 'params': {...}}`——**键是 'fn'，'function' 恒 KeyError** → except 捕获（:316-317）→ `project_files=[]` → files_info 恒空，analyze 的「先用工具读取项目结构」（:297-318）从未生效，分析 prompt 不含项目文件结构
- 对照：`generate_file` 走 `call_llm_with_tools` → ReActEngine `_execute_tool`（react_engine.py:208）用 `tools[tool_name]["fn"]`——**同一份工具表，两处用不同键访问**，generate_file 路径正确、analyze 路径错误

## 其余发现

### BE5 [P3] SYSTEM_PROMPT 每次调用都重新加载

- 位置：:17 property 每次访问都 get_skill + load_backend_engineer_prompt
- 影响：热路径重复文件读取/注册表查询；次要

## 修复优先级

| 项 | 级别 | 关键点 |
|---|---|---|
| BE1 | P2 | file_type 误判 → 错误约束注入 |
| BE7 | P2 | analyze 结构读取恒空 |
| BE5 | P3 | 提示词重复加载 |

## 关联

- **LLM 契约双轨（v1.11 主线）**：generate_file :264/:267 返回 call_llm 的 str——契约正确方（architect AR3 是错误方）
- **utils UT10/UT6**：generate_file 结果被消费方 extract_engineer_content 处理时触发 LLM 语言检测（"NO" 子串假阳性）与语言验证
- **五支柱（§5.6 支柱 1 产物协议）**：engineer 是产物生产者，其输出经 utils 门禁后进入文件编排——BE1 注入错误约束会直接污染产物内容
