# 技术债务跟踪

> 最后核对：2026-09-03

`已解决` 表示当前代码保持对应修复；`仍在` 表示当前实现可直接定位；`部分解决` 表示原修复范围仍有同类残留。历史测试数字保留其发生时的范围。

## 既有编号逐项复核

| # | 原问题 | 当前状态 | 当前依据 |
|---:|---|---|---|
| 1 | 启动时清空 history 表 | 已解决 | `app/main.py` 保留辅助函数定义，启动流程未调用 |
| 2 | superadmin 权限值不匹配 | 已解决 | `app/utils/security.py` 校验 `permission_level == "superadmin"` |
| 3 | admin config router 重复注册 | 已解决 | `app/main.py` 仅在 `/api/v2` 挂载一次 |
| 4 | drain middleware 缺少 `JSONResponse` | 已解决 | middleware 分支内显式导入 |
| 5 | Celery signal 使用异步 task | 已解决 | `app/celery_app.py` signal handler 使用同步 SQLAlchemy `Session` |
| 6 | 无时区 `datetime.utcnow()` | 部分解决 | 主要模型列已迁移，`app/models/file.py` 与 `app/models/aicloud.py` 仍有残留调用 |
| 7 | WebSocket Manager 单连接 | 已解决 | `app/services/websocket_manager.py` 按用户保存连接列表 |
| 8 | CORS host 正则未转义 | 仍在 | `app/main.py` 仍直接执行 `ALLOWED_HOSTS.replace(",", "|")` |
| 9 | PostgreSQL UUID 未使用导入 | 已解决 | `app/models/chat_history.py` 已无该导入 |
| 10 | `CHUNKS_DIR` 定义顺序 | 已解决 | `app/api/v1/file_upload.py` 在使用前定义常量 |
| 11 | SQL LIKE 未转义 | 已解决 | `app/db/search_history.py` 使用 `escape_like_pattern` 和显式 escape |
| 15 | login 限流标识不一致 | 已解决 | 检查、失败和成功记录统一使用 `identifier` |
| 18 | health 版本来源分裂 | 仍在 | `app/api/v1/health.py` 为 `v5.10.0`，`app/services/health_checker.py` 为 `v3.0`，`CHANGELOG.md` 最新版本为 `5.15.0` |
| 19 | cloudflared 遗留注释 | 仍在 | `app/main.py` 末尾仍有 Windows cloudflared 命令注释 |
| 20 | 旧 Agent router 备份残留 | 已解决 | 备份残留已移除 |
| 21 | FeatureSwitchMiddleware 路径 | 已解决 | `app/middleware/feature_switch.py` 使用 `/api/v1/agent` |
| 22 | evaluate 角色缺用户模型上下文 | 已解决 | Architect、CodeReviewer 传递 token 与 provider ID |
| 23 | evaluate LLM 调用缺 token | 已解决 | 相关调用传递 `api_key_token` |
| 24 | recovery auto-fix 硬编码模型 | 已解决 | 使用 `model_assignment.fallback_model` 并传 token |
| 25 | ReAct Agent 调用缺 token | 已解决 | `app/agent/react_agent.py` 传递用户 token |
| 26 | fallback chain 绑定单一供应商 | 已解决 | `app/agent/error_recovery.py` 提供供应商链和 provider 检测 |
| 27 | `ReActWithFallback` 死代码 | 已解决 | 当前无该符号，调用链使用 `ReActEngine` |
| 28 | 未使用的 `call_siliconflow` | 已解决 | `app/utils/AiCodeUtil.py` 已无该函数；适配器仍有过时注释 |

## 当前仍在技术债

| 优先级 | 问题 | 实际位置 | 状态 |
|---|---|---|---|
| P1 | CORS host 字符串直接拼为正则 | `app/main.py` | 仍在 |
| P2 | 开发测试使用 Python 3.11，Dockerfile 使用 3.10 | `Dockerfile` | 仍在 |
| P2 | lifespan 与 startup hook 并存 | `app/main.py` | 仍在 |
| P2 | 多 API worker 下进程内 scheduler 可能重复执行 | `app/main.py`、`app/db/scheduler.py` | 仍在 |
| P2 | `/api/v1/health` 与部署侧 `/health` 契约分裂 | `app/api/v1/health.py`、部署配置 | 仍在 |
| P2 | health 响应版本来源分裂 | `app/api/v1/health.py`、`app/services/health_checker.py`、`CHANGELOG.md` | 仍在；分别为 `v5.10.0`、`v3.0`、`5.15.0` |
| P2 | StateGraph 生产入口仍以单节点 legacy wrapper 为主 | `app/agent/state/`、`app/agent/workflow_registry.py` | 仍在 |
| P2 | 统一检索尚未接入生产 Agent 主链 | `app/agent/retrieval/` | 仍在 |
| P2 | 跨工作台续跑与多 worker 恢复缺独立验收 | `app/api/v1/agent_host.py`、`app/agent/state/` | 仍在 |
| P3 | 无时区时间调用在模型、状态、PPT 和 Skill 模块仍有残留 | `app/models/`、`app/services/` | 仍在 |
| P3 | VS Code 发布元数据与真实状态栏适配仍需收尾 | `vscode-extension/package.json`、`vscode-extension/src/status-view.ts` | 部分解决；构建、Node 测试和 Host E2E 已通过 |
| P3 | Makefile `clean` 指向已归档脚本 | `Makefile`、`scripts/_archive/cleanup.sh` | 仍在 |
| P3 | ModelAdapter 注释引用已删除函数 | `app/adapter/model_adapter.py` | 仍在 |

## 当前验收基线

- 后端 unit/integration 最近完整记录：`1784 passed, 2 skipped`。
- 前端全量 Vitest：`36 passed`，Vite 生产构建成功。
- PPT 专项：`141 passed`；`elegant` 统一生成测试 `24 passed`。
- VS Code 扩展 Node 测试：`62 passed`，Extension Development Host E2E 已完成。
- 2026-06-06 的 `1622 passed / 0 failed` 与更早 `1244 passed / 3 skipped` 属于历史阶段结果。

## 历史修复记录

### 已修复的问题

### P0: 严重 Bug (4 项)

| # | 问题 | 文件 | 修复内容 |
|---|------|------|----------|
| 1 | 启动时清空 history 表 | `app/main.py` | 移除 `clear_history_table()` 调用 |
| 2 | require_superadmin 权限值不匹配 | `app/utils/security.py` | `"super"` → `"superadmin"` |
| 3 | adminConfigRouter 重复注册 | `app/main.py` | 移除 `/api/v1` 前缀的重复注册 |
| 4 | drain_mode_middleware 缺少导入 | `app/main.py` | 添加 `JSONResponse` 导入 |

### P1: 高危问题 (5 项)

| # | 问题 | 文件 | 修复内容 |
|---|------|------|----------|
| 5 | Celery 信号 asyncio.create_task | `app/celery_app.py` | 改用同步数据库操作 |
| 6 | datetime.utcnow() 无时区 | 历史修复覆盖部分模型时间列 | 改用 `datetime.now(timezone.utc)`；当前仍有残留 |
| 7 | WebSocket Manager 单连接 | `app/services/websocket_manager.py` | 支持同一用户多连接 |
| 8 | CORS ALLOWED_HOSTS 正则 | `app/main.py` | 历史曾记录修复；当前实现已回归 |
| 10 | file_upload.py CHUNKS_DIR | `app/api/v1/file_upload.py` | 移动配置到类定义之前 |

### P2: 中等问题 (3 项)

| # | 问题 | 文件 | 修复内容 |
|---|------|------|----------|
| 9 | PostgreSQL UUID 导入 | `app/models/chat_history.py` | 移除未使用的导入 |
| 11 | SQL LIKE 查询转义 | `app/db/search_history.py` | 添加 `escape_like_pattern()` 函数 |
| 15 | login 端点限流不一致 | `app/api/v1/auth.py` | 统一使用 `identifier` 格式 |

### P3: 低等问题 (4 项)

| # | 问题 | 文件 | 修复内容 |
|---|------|------|----------|
| 18 | health.py 版本号 | `app/api/v1/health.py` | 历史上更新为 `v5.10.0`；当前仍与 `health_checker.py` 的 `v3.0` 及 `CHANGELOG.md` 的 `5.15.0` 分裂 |
| 19 | main.py 遗留注释 | `app/main.py` | 历史曾记录移除；当前注释仍存在 |
| 20 | 旧 Agent router 备份残留 | 已移除 | 删除历史残留文件 |
| 21 | FeatureSwitchMiddleware 路径 | `app/middleware/feature_switch.py` | `/api/v1/project` → `/api/v1/agent` |

### P4: Agent 架构级 Bug (4 项)

| # | 问题 | 文件 | 修复内容 |
|---|------|------|----------|
| 22 | evaluate_mixin Architect/CodeReviewer 不传 api_key_token | `app/agent/orchestrator_generation/evaluate_mixin.py:43-46` | 添加 `api_key_token=self.api_key_token` + `provider_id=getattr(self, 'provider_id', None)` |
| 23 | evaluate_mixin call_llm 不传 api_key_token | `app/agent/orchestrator_generation/evaluate_mixin.py:150,219` | 添加 `api_key_token=self.api_key_token` |
| 24 | error_recovery ReAct auto-fix 硬编码 model_key | `app/agent/orchestrator_generation/error_recovery.py:18-22` | 改用 `model_assignment.fallback_model` + `api_key_token` |
| 25 | react_agent._call_llm 不传 api_key_token | `app/agent/react_agent.py:193` | 添加 `api_key_token=self.api_key_token` |

### P5: 技术债修复 (3 项)

| # | 问题 | 文件 | 修复内容 |
|---|------|------|----------|
| 26 | DEFAULT_FALLBACK_CHAIN 硬编码 SiliconFlow 模型名 | `app/agent/error_recovery.py` | 新增 `_PROVIDER_FALLBACK_CHAINS`（6 个供应商各自降级链）+ `_detect_user_provider()` 方法，改为供应商感知 |
| 27 | ReActWithFallback 死代码（硬编码模型名） | `app/agent/react_agent.py` + `__init__.py` | 删除 42 行死代码类 + 移除 import/export |
| 28 | call_siliconflow 未使用 | `app/utils/AiCodeUtil.py` | 删除 126 行死代码，统一走 `call_llm()` |

---

## 测试验证

| 测试类型 | 通过 | 失败 | 跳过 |
|----------|------|------|------|
| 单元测试 | 1622 | 0 | 0 |
| E2E 测试 | 76 spec | - | - |

---

## 已偿还的技术债务

### Agent 引擎架构重构 ✅ 已完成

**偿还日期**: 2026-06-04

**问题**: Agent 引擎代码分散、工具系统不统一、ReAct 循环重复、JSON 解析不一致

**解决方案**:
- **工具系统统一**: tools.py 作为唯一实现源 (996 行, 21 工具)，executor.py 适配后注册
- **ReAct 循环统一**: react_engine.py (578 行) 统一 simple + full 双模式
- **统一 LLM 调用层**: llm_client.py (164 行) 并发信号量 + 超时保护
- **统一 JSON 解析层**: json_parser.py (343 行) 5 层解析链
- **multi_model_agent.py 拆分**: 1202→243 行，6 个子模块
- **依赖图拆分**: 1351→983 行，新建 signature_extractor.py + shadow_scanner.py + dependency_rules.py
- **26 个 bare except pass 修复**: 全部改为 `except Exception: logger.debug(...)`
- **22 个函数内重复 import 清除**
- **硬编码模型名称统一**: 39 处/12 文件 → 4 个常量
- **45 处 alert→ElMessage** + **14 处 console 清理**

**效果**:
- 工具系统单一数据源，零重复
- ReAct 引擎统一，所有路径走 react_engine.py
- JSON 解析 5 层 fallback，小模型 JSON 输出稳定性大幅提升
- 测试基线：1244 passed / 3 skipped

### MCP Client 集成 ✅ 已完成

**偿还日期**: 2026-06-04

**问题**: 工具系统封闭，无法接入外部工具 (数据库、浏览器、搜索等)

**解决方案**:
- 新建 `mcp_client.py` (462 行): MCPServerConnection + MCPClientManager
- 支持 stdio + HTTP 双传输
- 4 个集成点: executor / specialist_base / agent_executor / orchestrator
- 前端管理: `/api/v2/mcp/servers` CRUD + test + toggle
- 配置文件: `data/mcp_servers.json`

**效果**:
- 用户可通过 MCP 协议接入任意外部工具
- MCP 工具对 ReActEngine 完全透明
- 资源增加 ~150MB 内存 + 1-3ms 延迟

### 交叉验证触发优化 ✅ 已完成

**偿还日期**: 2026-06-04

**问题**: 所有文件都触发交叉验证 (双模型生成)，浪费 token

**解决方案**:
- `is_critical_file` 加 `priority <= 2` 限制
- priority > 2 即使命中关键模式也不触发交叉验证
- 测试同步更新

**效果**:
- 交叉验证触发率降低 ~60%
- token 消耗减少

### 工具覆盖缺失 ✅ 已完成

**偿还日期**: 2026-05-22 | **来源**: 历史 Agent 完成报告

以下 5 个工具已在 `app/agent/executor.py` 中实现：

| 工具名称 | 实现方法 | 说明 |
|---------|---------|------|
| `insert_content` | `_tool_insert_content` | 支持按行号或锚点文本插入内容 |
| `partial_update` | `_tool_partial_update` | 支持按 target/replacement 或 function_name 替换代码块 |
| `regex_replace` | `_tool_regex_replace` | 支持 glob 模式匹配多文件的正则批量替换 |
| `delete_files_by_pattern` | `_tool_delete_files_by_pattern` | 基于 glob 模式的批量文件删除 |
| `cross_file_patch_auto` | `_tool_cross_file_patch_auto` | 支持 unified diff patch 和 new_content 两种模式 |

工具覆盖率从 95% 提升至 100%（19/19 工具已完成）。

---

### KV Cache 命中率优化 ✅ 已完成

**偿还日期**: 2026-05-23 | **版本**: v5.8.1

**问题**: LLM 调用时重复构建相同的 System Prompt，导致 KV Cache 命中率极低 (~0%)

**解决方案**:
- 创建 `app/utils/prompt_builder.py` (230 行)
- 静态前缀缓存（系统指令 + 工具定义 + spec_cache 内容）
- 动态后缀隔离（对话历史 + 会话状态 + 任务指令）

**效果**:
- KV Cache 命中率：~0% → 75-97%
- 延迟降低：≥20%

---

### 多角度审查系统 ✅ 已完成

**偿还日期**: 2026-05-23 | **版本**: v5.8.1

**问题**: 原有魔鬼代言人仅从单一角度审查

**解决方案**:
- 创建 `app/agent/multi_angle_review.py` (340 行)
- 3 个专业审查角色并行执行：性能师、安全师、可维护性师
- 三档严格度配置：LIGHT/STANDARD/STRICT

**效果**:
- 审查覆盖率：+200%
- 严重问题发现率：+40%

---

### API Key 全局化 ✅ 已完成

**偿还日期**: 2026-05-26 | **版本**: v5.9.0

**问题**: 仅项目生成使用用户 API Key，其他功能使用系统默认 Key

**解决方案**:
- 所有前端功能（项目生成、代码对话、PPT、图像生成、AI Cloud）均使用用户自定义 API Key
- 添加 `api_key_token` 参数到所有 API 请求
- 设置页面展示 Token 使用统计

**效果**:
- 用户可完全控制 API Key
- Token 消耗可视化

---

### 技术债务批量修复 ✅ 已完成

**偿还日期**: 2026-05-26 | **版本**: v5.9.0

**问题**: 16 项技术债务累积，包括 P0 级严重 Bug

**解决方案**:
- 修复 4 个 P0 级严重 Bug（启动清空数据、权限检查、路由重复、导入缺失）
- 修复 5 个 P1 级高危问题（Celery 信号、时区、WebSocket、CORS、文件上传）
- 修复 3 个 P2 级中等问题（UUID 导入、SQL 注入、限流一致性）
- 历史处理 4 个 P3 级低等问题（版本号、注释、残留文件、路径映射）；版本来源分裂当前仍在

**效果**:
- 消除所有已知严重 Bug
- 提升系统安全性和稳定性
- 代码库整洁度提升

---

### 工作流节点类型扩展 ✅ 已完成

**偿还日期**: 2026-05-27 | **版本**: v5.10.0

**问题**: 工作流仅支持 4 种节点类型，无法满足复杂业务需求

**解决方案**:
- 新增 5 种节点类型：`llm_call`、`conditional`、`human_approval`、`http_request`、`data_transform`
- 新增重试机制：`RetryConfig`（max_retries, retry_delay, backoff_factor）
- 新增失败策略：`fail`（中断）、`skip`（跳过继续）
- 新增状态：`waiting_approval`、`skipped`
- 提取提示词到 `skills/workflow-planner/system_prompt.md`

**效果**:
- 节点类型从 4 种扩展到 9 种
- 支持 LLM 调用覆盖 80% 工作流场景
- 支持条件分支和人工审批
- 资源限制适配 8C8G 服务器（最大并发 4 节点，节点超时 300s，内存 512MB）

---

## 相关文档

- [安全架构](security/SECURITY-OVERVIEW.md)
- [权限规范](security/PERMISSION-SPEC.md)
- [服务架构](guides/SERVICES.md)

---

最后核对：2026-09-03
