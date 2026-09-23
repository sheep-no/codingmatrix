# mcp_client.py 演化深扫文档

> 版本：v0.1 | 扫描日期：2026-08-05 | 状态：已完成
> 归属：Agent 引擎 / MCP 工具集成（工具层）
> 路径：`app/agent/mcp_client.py`（513 行）
> 索引：[TASKS.md](../TASKS.md)

## 1. 模块作用与功能

核心职责：**MCP（Model Context Protocol）客户端**——连接外部 MCP Server（stdio 子进程 / HTTP），将工具列表转换为 SPECIALIST_TOOLS 格式合并进 ReAct 引擎工具集：

1. **MCPServerConnection**（:41-393）：stdio 子进程 JSON-RPC 通信（initialize → initialized 通知 → tools/list → tools/call）、HTTP 直连（简化）、超时/断开清理
2. **MCPClientManager**（:396-513）：全局单例 `_instance`（:399），多 server 管理、工具注册、默认配置生成

## 2. 依赖与被依赖（跨模块引用链）

### 2.1 依赖

- `data/mcp_servers.json`（:29/:429，运行时读取，文件存在 973 字节）
- httpx（HTTP 传输）、asyncio subprocess（stdio 传输）

### 2.2 被消费方（4 处）

| 使用方 | 获取方式 | 行为 |
|--------|---------|------|
| executor.py:166 | **`MCPClientManager()` new** | load_servers → 注册到 ToolRegistry |
| mixin.py:105 | **`MCPClientManager()` new** | load_servers → _all_tools |
| agent_executor.py:140 | `get_instance()` | 读取单例工具 |
| specialist_base.py:150 | `get_instance()` | 合并 MCP 工具到 REACT 工具集 |
| mcp_admin.py（v2 API） | 管理接口 | 配置/连接管理 |

### 2.3 测试覆盖

- **活跃且较完整**：test_mcp_client.py 40 个测试方法（连接/发送/闭包/管理器/单例与重复加载，2026-09-23 由 33 增至 40）+ test_mcp_admin_api.py——**模块深扫以来测试覆盖最佳**

## 3. 已探明 Bug（含 bug 代码）

### MCP1 [P1] 单例竞争：2 处使用方直接 new 替换全局 _instance

- **Bug 代码**：

```python
# mcp_client.py:405-417 - 每次 __init__ 替换单例并断开旧实例
old_instance = MCPClientManager._instance
MCPClientManager._instance = self
if old_instance and old_instance._servers:
    logger.warning("MCPClientManager 被重新创建，旧实例的连接将在后台断开")
    loop.create_task(old_instance.disconnect_all())   # ← 旧连接被杀

# executor.py:166 / mixin.py:105 直接 new（非 get_instance）
manager = MCPClientManager()
```

- **根因**：`_instance` 是类属性单例，但 executor.py:166 与 mixin.py:105 都直接 `MCPClientManager()` 构造——每次构造替换单例并**后台断开旧实例全部连接**。executor 与 mixin 加载交错时，先加载的 server 连接被后 new 者断开
- **影响**：已注册工具的闭包（见 MCP2）运行时取到新 _instance，若新实例未 load_servers → 所有 MCP 工具返回「MCP Server 不存在」；连接反复断开重连

- **已修复（2026-09-23）**：`MCPClientManager` 改为真正的进程内单例——新增 `__new__`（`_instance` 为空才创建）与 `__init__` 复用守卫，删去原「替换单例并后台断开旧实例」逻辑；新增 `get_or_create_instance()` 作为统一入口。`executor.py` 与 `orchestrator_generation/mixin.py` 两处直接 `MCPClientManager()` 改为 `get_or_create_instance()`。回归：`test_repeated_construction_reuses_singleton`（二次构造同一对象且不断开既有连接）、`test_get_or_create_instance`；回退源码即失败。

### MCP2 [P1] 工具闭包运行时依赖全局 _instance，不持有 server 引用

- **Bug 代码**：

```python
# mcp_client.py:372-383 - 闭包不捕获 server 对象，运行时查全局单例
async def _mcp_tool_fn(project_path: str = "", _sn=server_name, _tn=tool_name, **kwargs):
    manager = MCPClientManager._instance          # ← 运行时全局
    if not manager:
        return {"success": False, "error": "MCPClientManager 未初始化"}
    server = manager.get_server(_sn)              # ← 依赖当前实例已加载
    if not server:
        return {"success": False, "error": f"MCP Server {_sn} 不存在"}
```

- **根因**：闭包只捕获 server/tool 名（_sn/_tn），不捕获连接对象——工具注册后可用性完全取决于 `_instance` 是否仍是加载时的实例且 server 未断开（叠加 MCP1 必现）

- **已修复（2026-09-23）**：`get_tools_as_specialist_format` 生成的闭包改为直接捕获本连接对象（`_server=self`），运行时不再查全局 `_instance`；单例被清空/替换后已注册工具仍指向原连接。失败路径由 `call_tool` 的 `MCPError` 统一转成 `{"success": False, "error": ...}`（未连接时即「MCP Server xxx 未连接」）。回归：`test_mcp_tool_fn_uses_captured_server` / `test_mcp_tool_fn_survives_manager_replacement` / `test_mcp_tool_fn_without_connection_returns_error` / `test_mcp_tool_fn_propagates_mcp_error`（原两个「依赖全局单例」的用例已按新契约重写）。

### MCP3 [P2] HTTP 传输无初始化握手（非标准 MCP）

> **实测确认（2026-08-05）**：起严格标准行为的 Streamable HTTP server（首请求必须是 initialize，否则返回 -32000）——`load_servers` 时服务端收到的第一个请求 method = **tools/list**（非 initialize）→ 被标准 server 拒绝（"Server not initialized"）→ `load_servers` 成功连接数 = 0，HTTP 模式完全无法连接标准 MCP HTTP server。

- **Bug 代码**：:132-142 `_connect_http` 不发 initialize/notifications/initialized 直接 `_initialized = True`（:140）——stdio 分支有完整握手（:115-127），HTTP 分支缺失；且无 SSE/streamable HTTP 支持，仅单次 POST——标准 MCP HTTP server 会拒绝 tools/list 或连接失败

### MCP4 [P2] HTTP 无 headers/auth 支持

- **Bug 代码**：:139 `httpx.AsyncClient(timeout=MCP_CALL_TIMEOUT)`——config 中的 headers/Authorization 不被读取，受保护 HTTP MCP server 无法连接

### MCP5 [P2] 空工具集 server 被当作连接失败断开

- **Bug 代码**：:455-461 `if tools:` 才保留 server，否则 `await server.disconnect()`——合法但暂未声明工具的 server 被断开

### MCP6 [P2] 重复 load_servers 不清旧连接、_all_tools 累积

- **Bug 代码**：:446-458 同名 server 直接覆盖 `self._servers[name]`（旧进程未 disconnect）；:458 `self._all_tools.update(...)` 与旧工具残留

- **已修复（2026-09-23）**：`load_servers` 改为幂等——先断开并从 `_servers` 摘除新配置中已禁用/移除的 server，已连接的同名 server 直接复用（不重复 `connect`），最后由存活 server 重建 `_all_tools`（而非 `update` 累积），返回值改为存活 server 总数。MCP1 单例化后，`_init_mcp_tools` 每个 orchestrator 实例都会在同名单例上重复 load，本项是防止子进程泄漏与工具累积的必要配套。回归：`test_load_servers_reuses_connected_server` / `test_load_servers_drops_disabled_server` / `test_load_servers_rebuilds_tools_without_accumulation`。

### MCP7 [P2] 工具参数无 schema 校验，值全为字符串

- **Bug 代码**：:360-364 仅把 schema 属性转字符串描述，`_mcp_tool_fn` 的 kwargs 直接透传 `server.call_tool(_tn, kwargs)`（:380）——MCP server 期望数字/布尔参数时收到字符串

### MCP8 [P2] call_tool 非 text 内容退化

- **Bug 代码**：:290-294 仅提取 `type == "text"` 内容，非 text 类型（image/resource 等）回退 `str(content)`——结构化返回信息丢失（与 executor.md B3「MCP 返回 `{"success": bool, "result": str}`」契约关联）

## 4. 潜在问题与未知点

- `_send_notification`（:245-255）在 stdio 下无写锁保护（与 _send_stdio_request 的 `_write_lock` 不同步）——并发通知+请求时 stdin 写入交错（JSON-RPC 行协议下仍安全，但无锁）
- stdio initialize 使用 MCP_CONNECT_TIMEOUT=30s（:186 默认），tools/call 使用 60s（:278）——阈值合理
- `_read_loop` 断连时清理 pending futures（:166-170），但 `_send_stdio_request` 超时分支已 pop 的请求 id 后续若被 _handle_message 命中（msg_id 已不在 _pending）→ 静默忽略（:175 保护）——安全但消息丢失
- `data/mcp_servers.json` 默认包含 filesystem/brave-search 示例（:492-508，enabled: false）——默认禁用，未激活

## 5. 修改建议（改什么 → 达成什么目的）

| # | 优先级 | 修改动作 | 达成目的 | 涉及位置 | 对应 Backlog |
|---|--------|---------|---------|---------|-------------|
| 1 | P1 | ~~MCP1：使用方统一走 `get_or_create_instance()`；构造复用已有实例~~ 已修 | 消除单例竞争，工具引用稳定 | mcp_client.py:401 + executor.py + mixin.py | 新增（关联 #5 B4） |
| 2 | P1 | ~~MCP2：闭包改为捕获 `server` 对象，不依赖全局 _instance~~ 已修 | 工具调用与实例生命周期解耦 | mcp_client.py:372-383 | 新增 |
| 3 | P2 | MCP3：HTTP 分支补 initialize/initialized 握手 + SSE 支持 | 兼容标准 MCP HTTP server | mcp_client.py:132-142 | 新增 |
| 4 | P2 | MCP4：读取 config headers 传入 AsyncClient | 支持受保护 HTTP server | mcp_client.py:139 | 新增 |
| 5 | P2 | MCP7：按 inputSchema 做参数类型转换/校验 | 参数类型正确 | mcp_client.py:360-364 | 新增 |

## 6. 演化方向关联

- **executor.md B4 印证**：「MCP 工具污染全局单例」在本模块确认根因——MCPClientManager 本身是全局单例且被 2 处 new 竞争，收敛时与 executor 的 ToolRegistry 单例（§9.1 B1）一起治理
- **工具返回契约**：MCP 返回 `{"success": bool, "result": str}`（tools.md/write 契约、react_engine.md :504 result_count）——MCP 层与内置工具返回结构一致，但 result 文本化（MCP8）可能截断结构化数据
- **Backlog 关联**：#5（executor B4）、#7、#12，新增 MCP1-MCP5

## 7. 状态校准（2026-09-23 复核 + 修复）

| 编号 | 状态 | 结论 |
|------|------|------|
| MCP1 | 已修 | 见 §3 MCP1。`MCPClientManager` 单例化（`__new__` + `__init__` 复用守卫）+ `get_or_create_instance()`；删去构造时的「后台断开旧实例」。两处 `new` 调用点已改为统一入口。 |
| MCP2 | 已修 | 见 §3 MCP2。闭包捕获连接对象，与全局单例解耦。 |
| MCP3 | 待处理 | HTTP 分支仍无 initialize/initialized 握手，兼容标准 MCP HTTP server 需另立项。 |
| MCP4 | 待处理 | HTTP 未读取 config 的 headers/auth。 |
| MCP5 | 待处理 | 空工具集 server 仍被断开（保留原状，避免本批扩大改动面）。 |
| MCP6 | 已修 | 见 §3 MCP6。`load_servers` 幂等：断开陈旧 server、复用已连接 server、重建工具表。与 MCP1 配套（单例复用后必须防止重复 load 泄漏子进程/累积工具）。 |
| MCP7 | 待处理 | 工具参数仍全字符串透传，无 schema 类型转换。 |
| MCP8 | 待处理 | `call_tool` 非 text 内容仍 `str(content)` 退化。 |

本批测试：`tests/unit/test_mcp_client.py` 33 → 40，新增 9 项（MCP1 2 项、MCP2 4 项、MCP6 3 项，其中 2 项为按新契约重写的原用例）。回退 `app/agent/mcp_client.py` 后 9 项全部失败，验证测试可捕获缺陷。
