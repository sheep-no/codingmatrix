# tools.py 演化深扫文档

> 版本：v0.1 | 扫描日期：2026-08-05 | 状态：已完成
> 归属：Agent 引擎 / 工具层（ReActEngine 与 ToolRegistry 两栈共用）
> 路径：`app/agent/tools.py`（1292 行）
> 索引：[TASKS.md](../TASKS.md)

## 1. 模块作用与功能

核心职责：**Specialist 内置工具的唯一实现源**——20 个工具函数 + `SPECIALIST_TOOLS` 注册表（v1.10 四域：文件 10 / git 4 / 搜索 3 / 执行 2）。从 specialist_base 拆分而来（docstring :5）。

区域划分（13 个功能区）：

| 区域 | 行段 | 函数 |
|------|------|------|
| 安全路径 | :22-49 | `set_allowed_file_paths` / `_safe_join`（符号链接解析后路径越界校验） |
| 代码分析辅助 | :113-155 | `_get_patterns_for_file` / `_extract_module_name`（9 语言符号正则） |
| 文件读取 | :161-215 | `_tool_read_file` / `_tool_list_files` / `_scan_dir` |
| 代码分析精读 | :219-359 | `_tool_read_symbols` / `_tool_read_imports` / `_tool_summarize_file` |
| 写入/验证 | :363-493 | `_tool_partial_update` / `_tool_insert_content` / `_tool_regex_replace` |
| 沙箱执行 | :497-611 | `_tool_execute_code` / `_execute_python_sandbox` / `_execute_js_sandbox` |
| 命令执行 | :651-715 | `_tool_run_command`（黑名单+白名单） |
| 搜索 | :720-832 | `_tool_search_files` |
| 写入 | :836-949 | `_tool_write_file` / `_validate_file_syntax` |
| Git | :953-1069 | `_run_git` / `_tool_git_status/diff/commit/log` |
| 网络 | :1073-1146 | `_tool_web_search` / `_tool_http_request`（SSRF 防护） |
| 文件删除 | :1152-1179 | `_tool_delete_files_by_pattern` |
| 注册表 | :1184-1292 | `SPECIALIST_TOOLS`（20 工具） |

## 2. 依赖与被依赖（跨模块引用链）

### 2.1 tools.py 被消费方（8 个生产引用，实码确认）

| 消费方 | 位置 | 消费内容 | 用途 |
|--------|------|---------|------|
| specialist_base.py | :17 | `SPECIALIST_TOOLS` | ReActEngine 栈工具注册 |
| spec_first_generate.py | :311/:876 | `set_allowed_file_paths` | 生成前设置写入白名单 |
| backend_engineer.py | :251/:299 | `SPECIALIST_TOOLS` | 后端工程师角色专用工具 |
| frontend_engineer.py | :221/:269 | `SPECIALIST_TOOLS` | 前端工程师角色专用工具 |
| mcp_client.py | 全局 | `SPECIALIST_TOOLS` | MCP 工具合并参考 |
| executor.py | :17-36 | 18 个 `_impl_*` | ToolRegistry 栈（ReActAgent 消费） |
| agent_executor.py | :20 | `SPECIALIST_TOOLS` 子集 | 分析任务只读工具 |
| react_agent.py | :142-143 | `SPECIALIST_TOOLS` | ToolRegistry 为空时 fallback |

> **注**：Aicode.py（chat 接口，app/api/v1/Aicode.py）**未直接调用** tools.py/SPECIALIST_TOOLS（grep 实测）——chat→工具 的调用是经 Agent 编排间接发生，非直接依赖。

### 2.2 tools.py 运行期跨模块依赖

- `app.core.config.settings`（:500 沙箱开关/语言白名单）
- `app.agent.utils.is_placeholder_content`（:844，write_file 占位内容判断）
- 外部设置方：`TopologyScheduler.build_from_dependency_graph()` 调 `set_allowed_file_paths`（:18 注释）
- 标准库：subprocess（:522/:568/:653/:744/:888/:955）、httpx（:1075/:1098）、ipaddress/socket（:1097/:1115，SSRF 防护）、glob/re/tempfile

> **数据库依赖：无**（tools.py 无任何 DB 调用；executor docstring 提到的 database 工具类型在注册表中不存在，属过时注释）。

### 2.3 测试覆盖

- test_executor.py（17 passed，经 executor 间接覆盖 read/write/git 等）
- test_agent.py（2 failed 为 §9.1 路径越界，非 tools.py 自身）
- **沙箱/HTTP/删除/搜索工具无直接单测**（本轮验证缺口）

## 3. 已探明 Bug（含 bug 代码）

### T1 [P0] `_execute_python_sandbox` 因 `os` 未导入 → Python 沙箱执行必然失败（已修复）

> 修复：函数内补充 `os` 导入，并清理冗余的 `error` 条件表达式。

- **现象**：Python 代码沙箱执行恒返回失败
- **Bug 代码**：

```python
# tools.py:8-13 - 模块级 import 无 os
import re
import json
import glob
import logging
from pathlib import Path
from typing import Dict, Optional

# tools.py:520-523 - 函数内只 import subprocess/tempfile
def _execute_python_sandbox(code: str, timeout: int) -> Dict:
    import subprocess
    import tempfile

# tools.py:559-563 - finally 引用未定义的 os
    finally:
        if tmp_path and os.path.exists(tmp_path):   # ← NameError
            try:
                os.unlink(tmp_path)
```

- **根因**：模块级（:8-13）与函数级（:522-523）均未导入 `os`；:559/:561 引用 `os` → NameError。对比：`_execute_js_sandbox`（:595 `import os`）、`_tool_run_command`（:654 `import os`）、`_tool_delete_files_by_pattern`（:1155 `import os`）均有函数内 import，**仅 python 沙箱遗漏**
- **影响**：`execute_code` 工具对 python 语言**永远失败**；ReActEngine/ToolRegistry 两栈（含修复闭环）的 Python 代码验证能力全断。影响面含 code_validator 体系依赖的沙箱验证
- **触发条件**：任何 `_execute_python_sandbox` 调用（正常 return 前 finally 必执行）
- **验证**：实测 `python3 -c "from app.agent.tools import _execute_python_sandbox; _execute_python_sandbox('print(1)', 5)"` → `NameError: name 'os' is not defined`（复现）

### T2 [P1] `_tool_run_command` cwd 校验用 `startswith` → 目录前缀绕过（已修复）

> 修复：使用 `Path.relative_to()` 校验目录是否位于项目根目录内。

- **Bug 代码**：

```python
# tools.py:666-670
work_dir = Path(project_path)
if cwd:
    work_dir = (work_dir / cwd).resolve()
    if not str(work_dir).startswith(str(Path(project_path).resolve())):
        return {"success": False, "error": "安全限制: 工作目录必须在项目路径内"}
```

- **根因**：`startswith` 前缀匹配——`project_path=/proj` 时，`cwd=../proj_evil` 解析后 `/proj_evil` 以 `/proj` 开头 → 绕过目录限制。应使用 `Path.relative_to`（对比 `_safe_join` :34-49 的正确实现）
- **影响**：命令可在项目目录之外的相似前缀目录执行（命令本身仍受白名单约束，风险中等）
- **触发条件**：cwd 指向路径前缀含 project_root 的越界目录

### T3 [P1] MAX_OUTPUT_BYTES 定义未使用 → OOM 防护失效（已修复）

> 修复：将 stdout/stderr 重定向到临时文件，读取时限制为 `MAX_OUTPUT_BYTES + 1`，返回结果继续保留尾部摘要。

- **Bug 代码**：

```python
# tools.py:677-693 - 定义 1MB 上限但 communicate() 未传 max 限制
MAX_OUTPUT_BYTES = 1024 * 1024  # 1MB
proc = subprocess.Popen(command, shell=True, ...)
stdout, stderr = proc.communicate(timeout=timeout)   # ← 全量读入内存
```

- **根因**：`MAX_OUTPUT_BYTES`（:677）仅定义，`communicate()`（:693）全量缓冲；:706-707 的 `stdout[-5000:]` 是**显示截断**非缓冲限制
- **影响**：命令输出巨大时内存耗尽（注释声称防 OOM 实际未生效）
- **触发条件**：run_command 执行产生 > 内存容量的输出（如 `find / -type f`）

### T4 [P1] `_execute_python_sandbox` error 字段表达式冗余

- **Bug 代码**：

```python
# tools.py:552 - 两个分支结果完全相同
"error": result.stderr or None if result.returncode != 0 else result.stderr or None
```

- **根因**：条件表达式两分支均为 `result.stderr or None`，无条件等价（且 T1 修复前此分支永不达）
- **影响**：无功能影响，代码异味；修复 T1 时应一并清理

### T5 [P2] `set_allowed_file_paths` 模块级全局白名单 → 多项目互相覆盖

- **Bug 代码**：

```python
# tools.py:19-31 - 模块级全局可变状态
_allowed_file_paths: Optional[set] = None
def set_allowed_file_paths(paths: set):
    global _allowed_file_paths
    _allowed_file_paths = set(paths) if paths else None
```

- **根因**：全局单例状态（与 §9.1 ToolRegistry 单例同族）——项目 A 设置白名单后，项目 B 覆盖；spec_first_generate.py:311/:876 每次生成前重设
- **影响**：多项目并发时 write_file 白名单错乱（依赖 `_safe_join` :34-49 兜底目录校验，实际越界仍被拦，风险受限）
- **触发条件**：多项目同进程交替生成

### T6 [P2] 沙箱危险模式为静态正则黑名单 → 可字符串混淆绕过

- **位置**：:525-532（python）/ :571-578（js）
- **问题**：`__import__`、`getattr` 等以纯文本正则匹配，`getattr(__builtins__,'__import__')`、字符串拼接、unicode 转义等可绕过静态检测
- **影响**：沙箱非强隔离（T1 修复后此问题浮现）；纵深不足，属已知权衡

## 4. 潜在问题与未知点

- **沙箱运行环境**：python 沙箱 `cwd='/tmp'`、env 仅 PATH/HOME（:546-547），无资源限制（CPU/内存）——与 §2.1「docker_runner 无资源限制」同问题，云端并发执行沙箱时资源告急
- **`_tool_run_command` env 全量传递 `**os.environ`**（:686）：未清理宿主敏感环境变量
- **`execute_code` 沙箱开关依赖 `settings.ENABLE_CODE_SANDBOX`**（:502）：配置未开启时 execute_code 直接禁用
- **delete_files_by_pattern**（:1152）：glob 删除有 `_safe_join` 之外的自定义目录拼接（:1157），未走 `_safe_join` 校验路径
- **跨模块**：executor.py 漏注册 search_files/create_file（executor.md B3），导致 ToolRegistry 栈能力 < SPECIALIST_TOOLS 栈能力
- **chat→工具 调用链**：Aicode.py 不直接依赖 tools.py，需确认 Agent 编排（specialist_base）对 chat 的完整链路（见模块索引后续 react_engine/specialist_base 深扫）

## 5. 修改建议（改什么 → 达成什么目的）

| # | 优先级 | 修改动作 | 达成目的 | 涉及位置 | 对应 Backlog |
|---|--------|---------|---------|---------|-------------|
| 1 | P0 | T1：`_execute_python_sandbox` 函数内补 `import os`（或模块级统一 import），并清理 T4 冗余表达式 | Python 沙箱验证恢复，修复闭环代码验证能力恢复 | tools.py:520-563 | §9.x 新增 |
| 2 | P1 | T2：cwd 校验改用 `Path.relative_to`（对齐 `_safe_join`） | 消除目录前缀绕过 | tools.py:669 | §9.x 新增 |
| 3 | P1 | T3：`communicate()` 使用限制/流式读入，落实 MAX_OUTPUT_BYTES | 输出缓冲受限，防 OOM | tools.py:677-707 | §9.x 新增 |
| 4 | P2 | T5：`_allowed_file_paths` 改为按项目/会话隔离（或并入统一配置） | 多项目白名单不再互相覆盖 | tools.py:19-31 | #6 |
| 5 | P2 | T6：沙箱升级为真实隔离（资源限制/更严格 AST 拒绝）或明确标注为弱沙箱 | 安全纵深提升 | tools.py:525-532/:571-578 | §2.1 |
| 6 | P3 | delete_files_by_pattern 改走 `_safe_join` | 统一路径校验 | tools.py:1157 | - |

## 6. 演化方向关联

- **统一工具 Schema（§11.4 #6）**：tools.py 是工具返回结构三式（业务数据/error、success/error、success/result）的**源定义方**——统一 Schema 须从本文件 20 个工具开始
- **两栈收敛（§13.2/#12）**：SPECIALIST_TOOLS 是 Specialist 栈工具源；executor.py（ToolRegistry 栈）漏注册 search_files 的能力差在本文件可补齐（executor.md B3）
- **安全基线（§2.1/阶段四）**：沙箱/命令执行/HTTP 的安全纵深（T2/T3/T6）与「云端验证收敛」决策直接关联
- **Backlog 关联**：#6、#11、#12
