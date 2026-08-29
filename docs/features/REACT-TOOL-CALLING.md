# ReAct 工具调用

> 最后更新：2026-06-04 | 测试基线：1244 passed

ReAct（Reasoning + Acting）工具调用是 v5.12.0+ 的核心子系统之一，让 LLM 自主决定调用哪些工具来获取所需信息，而不是预注入全部上下文。

---

## 概述

v5.12.0+ 之前，Agent 系统的 Engineer 角色是"被动生成器"——接收 prompt，一次性输出完整代码。当 LLM 不知道某个函数的具体实现时，会"猜"或省略关键细节。v5.12.0+ 引入 ReAct 工具调用后，LLM 可以：

1. **思考**（Thought）：分析当前任务需要什么信息
2. **行动**（Action）：调用工具获取信息
3. **观察**（Observation）：分析工具返回结果
4. **决定下一步**：继续调用工具或进入最终生成

---

## 设计哲学

### 核心理念：让 LLM 决定需要什么

```python
# v5.12.0- 的做法：预注入所有依赖上下文（可能 50K+ tokens）
prompt = f"""
依赖文件内容：
{src_utils_content}  # 20K
{src_models_content}  # 15K
{src_config_content}  # 10K
{src_helpers_content}  # 5K
... 共 50K tokens

请基于以上内容生成 src/api/users.py
"""

# v5.12.0+ 的做法：让 LLM 自主决定
prompt = """
请生成 src/api/users.py，需要使用 src/utils 中的工具函数。
如果需要查看具体实现，可调用 read_file 工具。
"""
```

### 模型自适应

| 模型 | 工具调用行为 | 效果 |
|------|------------|------|
| DeepSeek-R1 | 主动调用工具 | 高质量，理解更准确 |
| Qwen3-8B | 中等调用 | 平衡速度与质量 |
| Qwen3.5-4B | 不调用工具 | 零开销，普通质量 |

**弱模型不调用工具 = 零性能损耗**。这是 ReAct 设计的核心优势——系统对所有模型都是安全的。

---

## 架构

```
┌─────────────────────────────────────────────────────────────┐
│ react_engine.py (578 行, 统一 ReAct 引擎)                    │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ ReActEngine.run()                                    │   │
│  │                                                      │   │
│  │  mode="simple" (Specialist 使用):                     │   │
│  │    Thought → Tool → Result 循环                       │   │
│  │    自然终止（LLM 不返回工具调用即结束）                 │   │
│  │    安全阀: max_rounds 轮后强制生成                     │   │
│  │                                                      │   │
│  │  mode="full" (ReActAgent 使用):                       │   │
│  │    Thought → Action → Observation → Reflection → Final│   │
│  │    反射终止 (Reflection 判断 task_complete)            │   │
│  │    max 3-10 轮 (按复杂度分级)                         │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ 工具历史管理 (滑动窗口)                               │   │
│  │  • 最近 3 条工具调用保留完整结果                       │   │
│  │  • 更早的条目压缩为一行摘要（只保留第一行）            │   │
│  │  • 总字符上限 6000，超出截断早期摘要                   │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ 工具来源 (动态合并)                                   │   │
│  │  • SPECIALIST_TOOLS: 18 个内置工具 (tools.py)         │   │
│  │  • MCP 工具: mcp_{server}_{tool} (mcp_client.py)     │   │
│  │  • 对 ReActEngine 完全透明，统一名为 tools dict       │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### 流程图

```
[Engineer 接收任务]
   ↓
[判断 is_existing_file]
   ├─ 新文件 → 简化 prompt (只读工具)
   └─ 现有文件 → 完整 ReAct 流程 (读+写工具)
       ↓
[ReActEngine.run(mode="simple")]
   ↓
[Round 1: Thought]
   LLM: "我需要查看 utils.py 的实现"
   ↓
[Round 1: Tool Call]
   LLM: {"tool": "read_file", "params": {"path": "src/utils.py"}}
   ↓
[工具执行] 返回 utils.py 内容 (滑动窗口记录)
   ↓
[Round 2: Thought]
   LLM: "我还需要知道数据模型"
   ↓
[Round 2: Tool Call]
   LLM: {"tool": "read_symbols", "params": {"file": "src/models.py"}}
   ↓
[工具执行] 返回 User 类定义
   ↓
[Round 3: Final]
   LLM: 基于所有观察，生成最终代码 (自然终止)
   ↓
[返回代码 / Edit marker]
```

---

## 21 个内置工具 (tools.py)

### 代码分析工具（6 个）

| 工具 | 描述 | 参数 |
|------|------|------|
| `read_file` | 读取文件内容 | `path` |
| `list_files` | 列出目录下文件 | `path`, `pattern` |
| `read_symbols` | 读取代码符号 | `file`, `kind` (def/class/all) |
| `read_imports` | 读取文件所有 import | `file` |
| `summarize_file` | 文件摘要 | `file` |
| `git_status` / `git_diff` / `git_log` | Git 操作 | - |

### 写入工具（4 个）

| 工具 | 描述 | 参数 |
|------|------|------|
| `partial_update` | 局部精准替换 | `file`, `target`, `replacement` |
| `insert_content` | 锚点插入内容 | `file`, `anchor`, `content`, `position` |
| `regex_replace` | 正则批量替换 | `file`, `pattern`, `replacement` |
| `write_file` | 完整写入文件 | `path`, `content` |

### 执行工具（2 个）

| 工具 | 描述 | 参数 |
|------|------|------|
| `execute_code` | 沙箱执行代码 | `code`, `language` (python/javascript) |
| `run_command` | 运行命令 | `command`, `timeout` |

### 网络工具（2 个）

| 工具 | 描述 | 参数 |
|------|------|------|
| `web_search` | DuckDuckGo 搜索 | `query`, `limit` |
| `http_request` | HTTP 请求 (SSRF 防护) | `method`, `url`, `headers`, `body` |

### MCP 扩展工具（动态加载）

通过 MCP 协议接入的外部工具，命名格式 `mcp_{server}_{tool}`。配置见 `data/mcp_servers.json`。

---

## 工具调用格式

v5.12.0+ 使用简化的 JSON 格式（非 OpenAI-like 复杂格式）：

```json
{
  "tool": "read_file",
  "params": {
    "path": "src/utils.py"
  }
}
```

解析逻辑（`specialist_base.py`）:

```python
def parse_tool_call(response: str):
    # 尝试从响应中提取 JSON
    json_match = re.search(r'\{[^{}]*"tool"[^{}]*\}', response, re.DOTALL)
    if not json_match:
        return None
    return json.loads(json_match.group(0))
```

如果 LLM 不返回工具调用（普通响应），则直接使用响应作为最终输出。

---

## Edit Marker 协议

当工程师调用写工具时，会触发以下流程：

### 协议格式

LLM 调用写工具后，返回 JSON marker：

```json
{
  "action": "edited",
  "files": ["src/api/users.py"],
  "summary": "修复了 create_user 函数的类型注解"
}
```

### Orchestrator 检测

```python
def _is_edit_marker(content: str) -> bool:
    """检测工程师返回的是 Edit marker 还是代码"""
    try:
        data = json.loads(content.strip())
        return data.get("action") == "edited"
    except (json.JSONDecodeError, AttributeError):
        return False
```

### 处理流程

```python
async def _generate_single_file(self, file_path):
    content = await engineer.generate_file(file_path)
    
    if self._is_edit_marker(content):
        # Edit marker 模式：从磁盘读取已修改文件
        marker = json.loads(content)
        edited_files = marker.get("files", [])
        actual_content = self._read_files_from_disk(edited_files)
        return actual_content
    else:
        # 正常模式：使用 LLM 返回的内容
        return content
```

---

## 工程师现有 vs 新文件模式

```python
async def generate_file(
    self,
    file_path: str,
    requirements: str,
    is_existing_file: bool = False,
    ...
):
    if is_existing_file:
        # 现有文件：可调用工具读取 + 主动编辑
        return await self._generate_existing_file(file_path, requirements)
    else:
        # 新文件：直接生成
        return await self._generate_new_file(file_path, requirements)
```

**现有文件模式**:
- 提供完整 13 个工具
- 鼓励先读取再编辑
- 优先使用 `partial_update` / `regex_replace`
- 只在必要时使用 `execute_code` 验证

**新文件模式**:
- 提供只读工具
- 生成完整文件内容
- 不需要 Edit marker（直接返回内容）

---

## `__init__.py` 特殊处理

`__init__.py` 文件使用专门 prompt：

```
生成 __init__.py 时：
1. 先调用 list_files 列出同包内所有 .py 文件
2. 调用 read_file 读取每个文件
3. 提取 def / class / 常量名称
4. 基于实际导出编写 __init__.py
5. 包内文件之间的导入必须使用相对导入
   （如 from .utils import greet，不要 from src.utils import greet）
```

**依赖图调整**:
- `__init__.py` 优先级从 1 改为 5
- 添加同包内所有文件 → `__init__.py` 的依赖边
- 确保 `__init__.py` 最后生成

---

## SSE 事件

ReAct 流程会推送 3 个新事件类型：

### `react_tool_call`

工具调用请求：

```json
{
  "type": "react_tool_call",
  "round": 1,
  "tool": "read_file",
  "params": {"path": "src/utils.py"},
  "file_path": "src/api/users.py"
}
```

### `react_tool_result`

工具执行结果：

```json
{
  "type": "react_tool_result",
  "round": 1,
  "tool": "read_file",
  "result": "def greet(name):\n    return f'Hello, {name}!'",
  "truncated": false,
  "file_path": "src/api/users.py"
}
```

### `react_generating`

最终生成中：

```json
{
  "type": "react_generating",
  "round": 3,
  "model": "deepseek-r1",
  "file_path": "src/api/users.py"
}
```

---

## 阶段化模型路由

不同 ReAct 阶段可以使用不同模型：

| 阶段 | 推荐模型 | 理由 |
|------|---------|------|
| 思考 | qwen3-8b | 快速理解 |
| 行动 | qwen3-8b | 简单工具调用 |
| 观察 | qwen3-8b | 简单分析 |
| 最终生成 | deepseek-r1 / 对应角色模型 | 高质量输出 |

**配置**: `data/agent_model_config.yaml`

```json
{
  "react_stage_models": {
    "thinking": "qwen3-8b",
    "action": "qwen3-8b",
    "final": "{role_default}"
  }
}
```

---

## 性能特性

### 智能降级

| 情况 | 行为 |
|------|------|
| 无 `project_path` | 跳过 ReAct，使用普通 `call_llm` |
| 工具调用解析失败 | 直接使用响应作为最终输出 |
| 弱模型不调用工具 | 正常 ReAct 流程（1 轮 = 普通 LLM） |
| 工具执行失败 | 返回错误信息，LLM 决定下一步 |

### 限制

- **simple 模式最大轮数**: 3-10 轮 (按复杂度分级)
- **full 模式最大轮数**: 3-10 轮
- **单文件最大行数**: 600-1600 行（动态调整）
- **工具执行超时**: 30s（沙箱）/ 60s（命令）
- **滑动窗口**: 最近 3 条完整 + 更早摘要，6000 字符上限

---

## 实施状态

| 角色 | ReAct 集成 | 13 工具 | Edit 模式 |
|------|----------|--------|----------|
| Architect | ✅ | ✅ (只读) | ❌ |
| Frontend Engineer | ✅ | ✅ (完整) | ✅ |
| Backend Engineer | ✅ | ✅ (完整) | ✅ |
| Reviewer | ✅ | ✅ (只读) | ❌ |
| Tester | ✅ | ✅ (只读) | ❌ |

---

## API 端点

### `POST /api/v1/agent/react`

直接调用 ReAct Agent：

```json
{
  "task": "分析 src/api/users.py 的依赖",
  "max_iterations": 10,
  "model": "deepseek-r1",
  "tools": ["read_file", "search_in_files"]
}
```

---

## 故障排查

### 工程师不调用工具

1. 检查模型是否在 `react_capable_models` 列表中
2. 验证 prompt 中是否包含工具说明
3. 查看 `react_tool_call` 事件是否触发

### 工具执行失败

1. 检查 `read_file` 的 `path` 是否在项目目录内
2. 检查 `execute_code` 的沙箱是否启用
3. 查看 `app.log` 工具执行日志

### Edit marker 检测失败

1. 确认 LLM 返回的 JSON 格式正确
2. 检查 `action: "edited"` 字段
3. 验证 `files` 数组中的文件实际被修改

---

## 相关文档

- [Agent 系统](AGENT.md)
- [动态模型路由](DYNAMIC-MODEL-ROUTER.md)
- [安全架构](../security/SECURITY-OVERVIEW.md#代码沙箱)
- [架构文档](../architecture/ARCHITECTURE.md)
