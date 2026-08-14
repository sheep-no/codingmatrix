# executor.py 演化深扫文档

> 版本：v0.1 | 扫描日期：2026-08-05 | 状态：已完成
> 归属：Agent 引擎 / A7 验证修复（ReActAgent 工具栈核心）
> 路径：`app/agent/executor.py`（451 行）
> 索引：[TASKS.md](../TASKS.md)

## 1. 模块作用与功能

核心职责：**统一工具适配与执行层**——将 `tools.py` 的底层工具实现适配为 `(params) -> ToolResult`，经 `ToolRegistry` 单例注册表供 ReActAgent 修复闭环消费。

主要类 / 函数（含精确位置）：

| 类 / 函数 | 位置 | 功能 |
|-----------|------|------|
| `ToolResult`（dataclass） | :41-48 | 工具执行结果（success/result/error/execution_time/tool_name） |
| `_wrap_sync` | :51-64 | 同步工具 → ToolResult 适配 |
| `_wrap_async` | :67-80 | 异步工具 → ToolResult 适配 |
| `ToolRegistry` | :83-139 | **模块级单例**工具注册表（_instance/_tools） |
| `EnhancedExecutor` | :142-421 | 主执行器：18 工具注册 + 执行 |
| `StreamingExecutor` | :424-451 | 流式输出执行器（继承 EnhancedExecutor） |

EnhancedExecutor 内部子功能：

- `__init__`（:148-154）：单例获取 + 注册短路（`if not self.tool_registry._tools`）
- `load_mcp_tools`（:156-182）：MCP 工具加载注册
- `_params_to_schema`（:184-197）：params 格式 → JSON Schema
- `_register_default_tools`（:199-370）：18 工具注册（文件 8 / git 4 / 搜索 1 / 执行 2 / 网络 2 / 删除 1）
- `execute_tool`（:372-384）、`execute`（:386-405）、`execute_file_operation`（:407-417）、`_adapt_http`（:419-421）

## 2. 依赖与被依赖

**导入依赖**：`tools.py` 18 个 `_impl_*` 函数（:17-36）。

**生产使用方**：

- `react_agent.py:14/:98` — ReActAgent 构造 `EnhancedExecutor()`，:131-138 从 `executor.tool_registry` 构建工具表
- 使用方链：`error_recovery.py:19` → ReActAgent → EnhancedExecutor → ToolRegistry（§13 记录）
- 直接实例化（非孤儿，经 ReActAgent 生产活跃）

**测试覆盖**：`test_executor.py` 17 passed（不覆盖多实例场景）；`test_agent.py` 2 failed（B1 触发，test_agent.py:102）。

## 3. 已探明 Bug（含 bug 代码）

### B1 [P0] ToolRegistry 单例闭包捕获 project_path → 路径越界（§9.1，复测仍在）

- **现象**：`EnhancedExecutor(project_path=tmp)` 传入自定义根目录后，write_file 仍报「路径越界：不在项目根目录 '.' 下」
- **Bug 代码**：

```python
# executor.py:148-153 - 单例 + 注册短路
def __init__(self, file_operator=None, project_path: str = "."):
    self.project_path = project_path
    self.tool_registry = ToolRegistry.get_instance()      # 模块级单例
    if not self.tool_registry._tools:                     # 首个实例注册后短路
        self._register_default_tools()

# executor.py:202-212 - 闭包捕获 self.project_path（首个实例的值）
def _adapt_sync(fn):
    async def wrapper(params: Dict) -> ToolResult:
        return await asyncio.to_thread(_wrap_sync, fn, self.project_path, params)
```

- **根因**：`ToolRegistry` 模块级单例（:86-93）+ 注册短路（:152-153）+ 闭包捕获 `self.project_path`（:205/:212）——后续实例永久复用首个实例的路径
- **影响**：多项目/多会话文件错位（数据错位级）；经 ReActAgent 修复闭环的工具写入同样落错目录（§13 影响面扩展）
- **触发条件**：同进程创建两个不同 project_path 的 EnhancedExecutor
- **验证**：`pytest tests/unit/test_agent.py -q` → 2 failed（test_agent.py:102 路径越界 AssertionError），57 passed 2 failed 精确

### B2 [P1] `_wrap_sync/_wrap_async` success 判定缺陷：`{"error":...}` 业务失败被判定成功

- **Bug 代码**：

```python
# executor.py:58-60 - success 判定只看 success 键，默认 True
success=result.get("success", True) if isinstance(result, dict) else True,
error=result.get("error") if isinstance(result, dict) and not result.get("success", True) else None,
```

- **根因**：read 系列工具业务失败返回 `{"error": "文件不存在"}`（tools.py:167/:190），无 success 键 → success 默认 True、error 取不到——**业务失败被判定成功**。与 §11 react_engine._execute_tool（异常判定）构成**两套不一致的 success 语义**
- **影响**：ReActAgent 修复闭环把「读取失败」当作成功，修复循环基于错误数据继续
- **触发条件**：工具返回含 error 键但不含 success=False 的 dict（read 系列全部）

### B3 [P1] 工具能力不对称：search_files 漏注册

- **现象**：`SPECIALIST_TOOLS` 20 个（tools.py），executor 导入+注册 **18 个**，缺 `search_files`（tools.py:720 定义、:1239 注册）与 `create_file`
- **根因**：executor.py:17-36 import 清单无 `_tool_search_files`；create_file 为 `_tool_write_file` 别名（tools.py:1253，影响小）
- **影响**：ReActAgent（修复闭环）经 ToolRegistry 构建工具表（react_agent.py:131-138）**拿不到 search_files**——修复闭环无法搜索文件，两套工具栈能力不等（§13.2 补充）

### B4 [P2] MCP 工具污染全局单例

- **Bug 代码**：

```python
# executor.py:165-176 - MCP 工具注册进全局单例 ToolRegistry
manager = MCPClientManager()
connected = await manager.load_servers()
if connected > 0:
    mcp_tools = manager.get_all_tools()
    for name, tool_info in mcp_tools.items():
        self.tool_registry.register(name=name, func=tool_info["fn"], ...)
```

- **根因**：`_mcp_loaded` 是实例级（:154/:162），registry 是全局——项目 A 实例加载 MCP 工具后，同进程项目 B 实例共享这些工具（工具可见性跨项目泄漏）

### B5 [P2] `execute_tool` coroutine 分支冗余

- **Bug 代码**：executor.py:378 `if asyncio.iscoroutinefunction(func)`——所有 adapt 后工具均为 async def（:204/:211），else 分支（`asyncio.to_thread`）实际不可达（除非注册非 async 函数）
- **影响**：无功能影响，属冗余分支

## 4. 潜在问题与未知点

- `_params_to_schema`（:193）类型映射表缺部分类型，非标准类型 fallback 为 string（潜在 schema 精度损失）
- `execute_file_operation`（:407-417）operation 无校验，未知操作直接报错（符合预期）
- MCP 工具与内置工具经 ToolRegistry 共表时，工具名冲突覆盖行为未验证
- B1 修复后需回归验证 ReActAgent 修复闭环路径（Backlog #11 关联）

## 5. 修改建议（改什么 → 达成什么目的）

| # | 优先级 | 修改动作 | 达成目的 | 涉及位置 | 对应 Backlog |
|---|--------|---------|---------|---------|-------------|
| 1 | P0 | 修 B1：wrapper 改为调用时传 project_path（或每次实例化重新注册），覆盖 ReActAgent 消费路径 | 多实例文件落到各自根目录，修复闭环不写错位置 | executor.py:152-153/:205/:212，react_agent.py:131 | #11 |
| 2 | P1 | 修 B2：统一 success 判定——read 系列返回含 error 键即判失败 | 业务失败不再被当作成功 | executor.py:58-60 | #6 |
| 3 | P1 | 修 B3：executor 补注册 search_files（复用 tools.py:720） | 两套工具栈能力对齐，修复闭环可搜索文件 | executor.py:17-36/:216 | #6 |
| 4 | P2 | 修 B4：MCP 工具按实例/会话隔离或废弃全局单例 | 避免跨项目工具可见性泄漏 | executor.py:156-182 | §4.2 |
| 5 | P2 | 修 B5：清理不可达分支 | 消除冗余代码 | executor.py:378 | - |

## 6. 演化方向关联

- **阶段一（拆分解耦）**：B1 为 §9.1 P0 修复对象，优先于拆分落地
- **阶段二（统一收敛）**：executor 是 §4.2「消除新旧路径并存」的收敛节点——ReActAgent 栈（ToolRegistry/EnhancedExecutor）与 Specialist 栈（SPECIALIST_TOOLS/ReActEngine）的工具注册表收敛（§13.2/#12）
- **统一工具 Schema**：B2/B3 均并入 §11.4 #6（统一工具返回 Schema），executor 的 `_wrap_*` 是判定层收敛点之一
- **Backlog 关联**：#6、#11、#12
