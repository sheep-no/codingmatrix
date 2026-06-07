# CodingMatrix 模块说明

> 最后更新：2026-06-06 | 测试基线：1622 passed / 0 failed | Agent 模块：76 | Vue 组件：69

## 项目结构概览

```
codingmatrix/
├── app/                         # 后端 (FastAPI, Python 3.11)
│   ├── agent/                   # Agent 核心 (76 模块)
│   ├── api/                     # API 路由 (26 个)
│   ├── db/                      # 数据库模型
│   ├── middleware/              # 中间件
│   ├── models/                  # 数据模型
│   ├── schema/                  # Pydantic Schema
│   ├── services/                # 服务层
│   └── utils/                   # 工具函数
├── src/                         # 前端 (Vue 3)
│   ├── components/              # Vue 组件 (69)
│   ├── composables/             # 组合式 API
│   ├── stores/                  # Pinia 状态管理
│   ├── utils/                   # 工具函数
│   └── views/                   # 页面视图
├── tests/                       # 测试
│   ├── e2e/                     # E2E 测试 (76 spec)
│   └── unit/                     # 单元测试 (1622)
├── docs/                        # 文档
├── configs/                     # 配置文件
├── scripts/                     # 运维脚本
├── cache/                       # 缓存目录
├── data/                        # 数据目录
├── keys/                        # 密钥目录
├── logs/                        # 日志目录
├── migrations/                  # 数据库迁移
├── projects/                    # 用户项目
├── sessions/                    # Agent 会话
│
├── .claude/                     # AI Agent 配置
├── .monkeycode/                 # 项目文档
├── .github/                     # CI/CD 配置
│
├── main.py                      # 启动入口
├── Makefile                     # 命令集
└── pyproject.toml              # 项目配置
```
codingmatrix/
├── app/                         # 后端 (FastAPI, Python 3.11)
├── src/                         # 前端 (Vue 3, Vite 5)
├── tests/                       # 测试 (Pytest + Playwright)
├── docs/                        # 文档 (全部 Markdown)
├── configs/                     # 配置文件
├── scripts/                     # 运维脚本
├── cache/                       # 缓存目录 (embedding_cache, spec_cache)
├── data/                        # 数据目录 (SQLite, dependency_graph, learning_data)
├── keys/                        # 密钥目录 (RSA 密钥对，cookies)
├── logs/                        # 日志目录
├── migrations/                  # Alembic 数据库迁移
├── projects/                    # 用户项目上传目录
├── sessions/                    # Agent 会话数据
│
├── .claude/                     # AI Agent 配置 (Skills/Rules)
├── .monkeycode/                 # MonkeyCode 项目文档
├── .github/                     # GitHub CI/CD 配置
│
├── main.py                      # 项目启动入口
├── Makefile                     # Make 命令集
├── pyproject.toml               # Python 项目配置
```

## v5.14.0 项目规模扩展 (2026-06-06)

### 1. Agent 模块扩展

| 模块类型 | 数量 | 说明 |
|----------|------|------|
| **Agent 核心** | 76 | 多角色协作系统 |
| **Orchestrator Mixins** | 25 | 生成流程协调 |
| ** Specialists** | 5 | 角色专家 (Architect/Frontend/Backend/Reviewer/Fallback) |
| **工具函数** | 21+ | 文件读写/代码分析/命令执行 |

### 2. 前端组件扩展

| 组件类型 | 数量 | 说明 |
|----------|------|------|
| **Vue 组件** | 69 | UI 组件库 |
| **Pinia Stores** | 8 | 状态管理 |
| **Composables** | 15 | 组合式 API |
| **API 客户端** | 14 | 后端接口封装 |

### 3. API 路由扩展

| 路由模块 | 端点数 | 说明 |
|----------|--------|------|
| **Agent** | 20+ | 项目生成/会话管理/快照 |
| **Code** | 5 | 代码生成/流式输出 |
| **Aicloud** | 15+ | 沙箱执行/审查队列 |
| **Workflow** | 8 | DAG 编排 |
| **Kolors** | 6 | 图像生成 |
| **PPTX** | 4 | PPT 生成 |
| **其他** | 20+ | 认证/文件/用户等 |

### 4. 测试覆盖

| 测试类型 | 数量 | 状态 |
|----------|------|------|
| **E2E Spec** | 76 | 全部通过 |
| **单元测试** | 1622 | 0 failed |

## v5.12.0+ 核心变化

### 1. 新增 v5.12.0+ 子系统

| 子系统 | 文件 | 描述 |
|--------|------|------|
| **动态模型路由** | `app/agent/dynamic_model_router.py` | 健康度 0-100 评分、熔断、5 复杂度档 × 5 角色模型 |
| **ReAct 工具调用** | `app/agent/react_agent.py` | 5 阶段循环，阶段化模型路由 |
| **13 工具 Specialist** | `app/agent/specialist_base.py` | 9 只读 + 4 写/验证工具 |
| **代码沙箱** | `specialist_base.py` (内嵌) | Python AST + JavaScript Node.js |
| **Git Stash 编辑回滚** | `orchestrator_files.py` | 原子回滚机制 |
| **编辑追踪** | `specialist_base.py` | `_edited_files` 列表 |
| **Session 生命周期** | `app/agent/session_manager.py` | 5 状态机、僵尸检测、429 响应 |

### 2. 修改的关键文件

| 文件 | v5.12.0+ 修改 |
|------|---------------|
| `app/agent/orchestrator_files.py` | 添加 `_git_stash_push/pop/drop`、`_is_edit_marker()` |
| `app/agent/orchestrator_generation/spec_first_generate.py` | 传递 `is_existing_file`、处理 edit marker |
| `app/agent/orchestrator_generation/incremental_generate.py` | 重写，删除 `_apply_patches_incremental` |
| `app/agent/orchestrator_generation/architect.py` | `expand_file_plan()` 改为 `while True` 循环 |
| `app/agent/orchestrator_utils.py` | 删除 `_should_use_patch_mode` |
| `app/agent/backend_engineer.py` | `generate_file()` 添加 `is_existing_file` 参数 |
| `app/agent/frontend_engineer.py` | 同上 |
| `app/agent/dependency_graph.py` | `__init__.py` 优先级 1→5，添加同包依赖边 |
| `app/agent/code_validator.py` | `validate_runtime_imports` 修复 sys.path + 完整模块路径提取 |
| `app/core/config.py` | 添加 `ENABLE_CODE_SANDBOX`、`SANDBOX_LANGUAGES` |
| `app/api/v2/admin_config.py` | **新增** `sandbox-config` 端点 |

## 动态依赖图 (v5.8.1) - 全语言支持

### 支持的语言

| 语言 | 扩展名 | Import 语法 | 解析器状态 |
|------|--------|------------|-----------|
| **Python** | .py, .pyw | `import x`, `from x import y` | ✅ 完成 |
| **JavaScript** | .js, .jsx, .mjs | `import x from 'y'`, `require('y')` | ✅ 完成 |
| **TypeScript** | .ts, .tsx | `import x from 'y'`, `require('y')` | ✅ 完成 |
| **Java** | .java, .groovy | `import package.Class` | ✅ 完成 |
| **Go** | .go | `import "package"` | ✅ 完成 |
| **Rust** | .rs | `use crate::module`, `mod x` | ✅ 完成 |
| **C/C++** | .c, .cpp, .h, .hpp | `#include <x>`, `#include "x"` | ✅ 完成 |
| **Ruby** | .rb, .gemspec | `require 'x'`, `include X` | ✅ 完成 |
| **PHP** | .php | `require 'x'`, `use X\Y` | ✅ 完成 |
| **Swift** | .swift | `import Module` | ✅ 完成 |
| **Kotlin** | .kt, .kts | `import package.Class` | ✅ 完成 |
| **C#** | .cs | `using Namespace` | ✅ 完成 |
| **Scala** | .scala | `import package._` | ✅ 完成 |
| **R** | .R, .r | `library(x)`, `require(x)` | ✅ 完成 |

### 架构图

```
┌─────────────────────────────────────────────────────────────┐
│ Multi-Language Dependency Parser (v5.8.1)                   │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. 语言检测层                                              │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ 根据文件扩展名检测 14 种编程语言                       │   │
│  │ Python, JS/TS, Java, Go, Rust, C/C++, Ruby, PHP...  │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  2. 语法解析层 (各语言专用 Parser)                          │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐              │
│  │ Python     │ │ JavaScript │ │ Java       │              │
│  │ import     │ │ import/req │ │ import     │              │
│  └────────────┘ └────────────┘ └────────────┘              │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐              │
│  │ Go         │ │ Rust       │ │ C/C++      │              │
│  │ import     │ │ use/mod    │ │ #include   │              │
│  └────────────┘ └────────────┘ └────────────┘              │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐              │
│  │ Ruby       │ │ PHP        │ │ Swift      │              │
│  │ require    │ │ use/req    │ │ import     │              │
│  └────────────┘ └────────────┘ └────────────┘              │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐              │
│  │ Kotlin     │ │ C#         │ │ Scala      │              │
│  │ import     │ │ using      │ │ import     │              │
│  └────────────┘ └────────────┘ └────────────┘              │
│                                                             │
│  3. 标准化层                                                │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ 将不同语言的 import 语法转换为统一文件路径格式            │   │
│  │ Python: module.sub → module/sub.py                  │   │
│  │ JS: ./module → module.js                            │   │
│  │ Java: com.example.Cls → com/example/Cls.java        │   │
│  │ Rust: crate::mod → crate/mod.rs                     │   │
│  │ ...                                                 │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  4. 图构建层                                                │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  nodes: 文件节点 (path, lang, imports, imported_by) │   │
│  │  edges: 依赖边 (from → to, lang, type)              │   │
│  │  layers: 分层结果 [L0, L1, L2, ...]                 │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  5. 应用层                                                  │
│  ┌───────────────┐ ┌───────────────┐ ┌───────────────┐    │
│  │ 分层并发      │ │ 增量修改      │ │ 跨文件 Patch   │    │
│  │ (层内并行)    │ │ (变更影响)    │ │ (自动传播)    │    │
│  └───────────────┘ └───────────────┘ └───────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

### 依赖关系示例

```
项目依赖拓扑图：

    .env.example
        │
        ▼
    config/database.py ──────┐
        │                    │
        ▼                    │
    services/user.py ◄───────┘
        │
        ├──► api/v1/users.py
        │
        └──► services/auth.py
                │
                ▼
            api/v1/auth.py

层化结果：
├── Layer 0: .env.example, config/database.py
├── Layer 1: services/user.py
├── Layer 2: services/auth.py
└── Layer 3: api/v1/users.py, api/v1/auth.py

并发策略：同层内文件可并行生成，层间按拓扑序串行
```

### 核心方法

| 方法 | 说明 | 返回值 |
|------|------|--------|
| `add_file(path, imports)` | 添加文件节点及其导入依赖 | - |
| `build_from_existing_project()` | 从已有项目解析 import/require | 完整依赖图 |
| `get_affected_files(changed_files, max_depth=10)` | BFS 遍历，找出所有受影响的下游文件 | List[affected_files] |
| `get_layers()` | 按拓扑排序分层 | List[layers] |
| `update_on_file_change(file_path, old_imports, new_imports)` | 增量更新图 | - |
| `detect_cycles()` | 检测循环依赖 | List[cycles] |

### BFS 影响分析算法

```python
def get_affected_files(self, changed_files, max_depth=10):
    """
    BFS 遍历依赖图，找出所有受影响的下游文件
    
    算法:
    1. 将变更文件加入队列
    2. 逐层遍历直接依赖者 (import 当前文件的文件)
    3. 标记访问过的节点，避免重复
    4. 深度达到 max_depth 时停止
    
    复杂度: O(V + E), V=文件数，E=依赖边数
    """
    queue = deque([(f, 0) for f in changed_files])
    visited = set(changed_files)
    affected = []
    
    while queue:
        current, depth = queue.popleft()
        if depth >= max_depth:
            continue
        
        # 找出所有依赖当前文件的文件
        for importer in self.imported_by[current]:
            if importer not in visited:
                visited.add(importer)
                affected.append(importer)
                queue.append((importer, depth + 1))
    
    return affected
```

### 跨文件 Patch 传播

```
变更：services/user.py 添加了新函数 get_user_profile()

影响分析:
┌────────────────────────────────────────┐
│ 变更文件：services/user.py             │
│   └─ 添加函数：get_user_profile()      │
└────────────────────────────────────────┘
         │
         ▼ get_affected_files()
┌────────────────────────────────────────┐
│ 直接依赖 (深度 1):                      │
│   - services/auth.py                   │
│   - api/v1/users.py                    │
└────────────────────────────────────────┘
         │
         ▼ get_affected_files()
┌────────────────────────────────────────┐
│ 间接依赖 (深度 2):                      │
│   - api/v1/auth.py                     │
│   - api/v1/admin.py                    │
└────────────────────────────────────────┘

跨文件 Patch 流程:
1. 为 services/user.py 生成主 patch
2. 为 api/v1/users.py 生成调用补丁 (添加 get_user_profile 调用)
3. 为 services/auth.py 生成导入补丁 (添加 import)
4. 无法自动 patch 的文件 → "manual review required"
```

### 依赖关系类型

| 类型 | 描述 | 示例 |
|------|------|------|
| env → config | 环境变量被配置文件使用 | `.env` → `config/database.py` |
| config → service | 配置被服务模块使用 | `config/database.py` → `services/user.py` |
| service → api | 服务被 API 路由使用 | `services/user.py` → `api/v1/users.py` |
| docker-compose → env | docker-compose 依赖环境变量 | `docker-compose.yml` → `.env.example` |
| service → service | 服务间相互依赖 | `services/user.py` → `services/auth.py` |

### 性能指标

| 指标 | 数值 | 说明 |
|------|------|------|
| 支持语言数 | **14** | Python, JS/TS, Java, Go, Rust, C/C++, Ruby, PHP, Swift, Kotlin, C#, Scala, R |
| 解析速度 | ~100 文件/秒 | 单语言 AST 解析 |
| BFS 遍历 | O(V+E) | V=文件数，E=依赖边数 |
| 最大深度 | 10 | 防止循环依赖无限遍历 |
| 缓存命中率 | 85% | 重复查询时使用缓存 |
| 增量更新 | <1ms | 单文件变更增量更新图 |
| 混合语言项目 | ✅支持 | 同一项目可包含多种语言 |

### 实际案例

#### 案例 1: 新增 API 端点

```python
# 变更：api/v1/users.py 添加新路由 GET /api/v1/users/{id}/profile
dependencies.get_affected_files(['api/v1/users.py'])

# 返回受影响文件：
[
    'src/views/UserProfile.vue',      # 前端组件 (调用新 API)
    'src/api/user.js',                 # API 客户端
    'docs/api.md'                      # API 文档
]
```

#### 案例 2: 修改数据库 Model

```python
# 变更：models/user.py 添加新字段 avatar_url
dependencies.get_affected_files(['models/user.py'])

# 返回受影响文件：
[
    'schemas/user.py',                 # Pydantic Schema
    'services/user_service.py',        # Service 层
    'api/v1/users.py',                 # API 层
    'migrations/003_add_avatar.py',    # 数据库迁移
]
```

### 配置参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| MAX_DEPTH | 10 | BFS 最大深度 |
| CACHE_TTL | 300 | 缓存过期时间 (秒) |
| ENABLE_CACHE | True | 启用缓存 |
| SUPPORTED_LANGUAGES | [py, js, ts] | 支持的文件类型 |

---

## 后端模块 (app/)

### 核心框架

| 模块 | 路径 | 行数 | 描述 |
|------|------|------|------|
| 主应用 | `app/main.py` | 311 | FastAPI 应用入口，8 层中间件，22 个路由注册 |
| Celery 配置 | `app/celery_app.py` | - | Celery 异步任务配置 |
| 配置 | `app/core/config.py` | - | 全局配置，pydantic-settings 环境变量加载 |
| 日志配置 | `app/core/logging_config.py` | - | 日志系统配置 |
| 优雅关闭 | `app/core/graceful_shutdown.py` | - | GracefulShutdownManager，Drain 模式 |
| 数据库 | `app/db/database.py` | - | SQLAlchemy 异步引擎，会话管理 |
| 调度器 | `app/db/scheduler.py` | - | APScheduler 定时任务配置 |

### Agent 引擎 (app/agent/) - 80 个模块, ~20,000 行

| 模块 | 路径 | 行数 | 描述 |
|------|------|------|------|
| **tools.py** | `tools.py` | **996** | **唯一工具实现源，21 个内置工具 + SPECIALIST_TOOLS 注册表** |
| **react_engine.py** | `react_engine.py` | **578** | **统一 ReAct 引擎，simple + full 双模式，滑动窗口历史** |
| **mcp_client.py** | `mcp_client.py` | **462** | **MCP Client，stdio/HTTP 双传输，MCPClientManager 单例** |
| **llm_client.py** | `llm_client.py` | **164** | **统一 LLM 调用层，并发信号量 + 超时 + 成本追踪** |
| **json_parser.py** | `json_parser.py` | **343** | **统一 JSON 解析，5 层链路 + 工具调用 3 种策略** |
| Orchestrator | `orchestrator.py` | 123 | 总指挥：6 mixin 组合 |
| MultiModelAgent | `multi_model_agent.py` | 243 | 多模型协调：任务路由、规划、执行、审查 |
| SpecialistBase | `specialist_base.py` | 177 | Specialist 基类，委托 LLMClient + json_parser |
| DynamicModelRouter | `dynamic_model_router.py` | 995 | 健康度评分、熔断、5x5 模型分配、学习路由 |
| ComplexityAnalyzer | `complexity.py` | 245 | 5 级复杂度分析 (SIMPLE→ENTERPRISE) |
| ModelRegistry | `models.py` | 373 | 12 种任务类型、7 种能力、10 个模型注册 |
| CodeValidator | `code_validator.py` | 755 | 语法/导入/运行时/API 兼容性验证，LRU 缓存 |
| DependencyGraph | `dependency_graph.py` | 983 | 依赖图核心，拓扑排序 + BFS 影响分析 |
| DependencyRules | `dependency_rules.py` | 183 | 外部化依赖规则 |
| SignatureExtractor | `signature_extractor.py` | 144 | 函数签名提取 |
| ShadowScanner | `shadow_scanner.py` | 83 | 影子扫描 |
| TopologyScheduler | `topology_scheduler.py` | 372 | 动态拓扑调度器 |
| ErrorRecovery | `error_recovery.py` | 710 | 验证-修复-重试 + 模型降级 |
| FeedbackLearner | `feedback_learner.py` | 434 | 修复模式学习 + 向量匹配 |
| Memory | `memory.py` | 571 | 对话记忆 + 知识记忆，自动压缩 |
| SharedContext | `shared_context.py` | 337 | 全局共享上下文 |
| TaskPlanner | `task_planner.py` | 177 | 任务拆解，支持 ReAct 探索模式 |
| CodeReviewer | `code_reviewer.py` | 158 | 代码审查员 |
| CrossValidator | `cross_validator.py` | 1347 | 双模型生成 + 裁判选择 |
| SpecFirstGenerator | `spec_first_generator.py` | 461 | 规范先行生成 (OpenAPI→类型→DB→配置) |
| RefinementLoop | `refinement_loop.py` | 515 | 迭代修复循环 |
| FileContract | `file_contract.py` | 141 | 文件操作安全契约 |
| Tracing | `tracing.py` | 246 | OpenTelemetry 分布式追踪 |
| SessionManager | `session_manager.py` | 512 | 5 状态机、僵尸检测、429 响应 |
| **OrchestratorGeneration** | `orchestrator_generation/` | **~1400** | **spec_first/traditional/incremental/evaluate 4 个 mixin** |
| **OrchestratorRequirements** | `orchestrator_requirements/` | **~900** | **3 层需求关联 + 双模型对抗 + 魔鬼代言人** |
| **Adapters** | `adapters/` | **~1600** | **语言适配器：generic/python/javascript/language_adapter** |

---

## v5.12.0+ 新增详细模块

### MCP Client (MCP 协议扩展)

**文件**: `app/agent/mcp_client.py` (462 行)

**职责**:
- MCP Server 连接管理 (stdio/HTTP 双传输)
- JSON-RPC 2.0 协议实现
- 工具发现与调用
- 自动转换为 SPECIALIST_TOOLS 格式

**关键类**:
- `MCPServerConnection`: 单 Server 连接，支持 stdio (子进程) + HTTP (POST)
- `MCPClientManager`: 多 Server 管理 (单例)，load_servers/get_all_tools/disconnect_all
- `MCPError`: MCP 调用错误异常

**工具命名**: `mcp_{server_name}_{tool_name}` 前缀避免冲突

**集成点**:
- `executor.py`: `load_mcp_tools()` 注册到 ToolRegistry
- `agent_executor.py`: `execute_analysis()` 合并到 ANALYSIS_TOOLS
- `specialist_base.py`: `call_llm_with_tools()` 合并到 SPECIALIST_TOOLS
- `orchestrator_generation/mixin.py`: `_init_mcp_tools()` 初始化

**配置**: `data/mcp_servers.json`
```json
{
  "mcp_servers": {
    "filesystem": {"enabled": false, "transport": "stdio", "command": "npx", "args": [...]},
    "brave-search": {"enabled": false, "transport": "stdio", "command": "npx", "args": [...]},
    "sqlite": {"enabled": false, "transport": "stdio", "command": "uvx", "args": [...]},
    "custom-http": {"enabled": false, "transport": "http", "url": "http://..."}
  }
}
```

**前端管理**: `/api/v2/mcp/servers` CRUD + test + toggle

### DynamicModelRouter (动态模型路由)

**文件**: `app/agent/dynamic_model_router.py` (~900 行)

**职责**:
- 模型健康度追踪（0-100 分）
- 熔断器（CLOSED/OPEN/HALF_OPEN）
- 5 复杂度档 × 5 角色模型分配
- Fallback 链管理
- LRU 缓存模型分配

**关键方法**:
- `get_assignment(complexity_level, role)` - 获取模型分配
- `record_call_result(model, success, latency)` - 记录调用
- `is_healthy(model)` - 检查健康
- `get_fallback(primary, role)` - 获取备选
- `reset_health(model)` - 重置分数

详见 [DYNAMIC-MODEL-ROUTER.md](../features/DYNAMIC-MODEL-ROUTER.md)

### ReActAgent (ReAct 自主循环)

**文件**: `app/agent/react_agent.py` (~500 行)

**职责**:
- 5 阶段循环：思考/行动/观察/反思/最终
- 阶段化模型路由
- ToolRegistry 集成
- 流式输出

**关键方法**:
- `process(task, context)` - 主入口
- `_think(context)` - 思考阶段
- `_act(thought)` - 行动阶段
- `_observe(action, result)` - 观察阶段
- `_reflect(observation)` - 反思阶段
- `_final_answer(reflections)` - 最终生成

详见 [REACT-TOOL-CALLING.md](../features/REACT-TOOL-CALLING.md)

### SessionManager (会话生命周期)

**文件**: `app/agent/session_manager.py` (~500 行)

**职责**:
- 5 状态机管理
- 内存 ↔ DB 同步
- 僵尸会话检测
- TTL 清理
- 429 并发限制

**关键方法**:
- `create_session()` - 创建
- `pause_session(id)` - 暂停
- `resume_session(id)` - 恢复
- `cancel_session(id)` - 取消
- `cleanup_expired()` - 清理
- `detect_zombie_sessions()` - 僵尸检测
- `sync_from_db()` - 从 DB 恢复
- `persist_state(id)` - 持久化

详见 [SESSION-LIFECYCLE.md](../features/SESSION-LIFECYCLE.md)

### 工具系统 (tools.py, 996 行)

**文件**: `app/agent/tools.py` — 唯一工具实现源，21 个内置工具

**代码分析工具 (6)**:
1. `read_file` - 读取文件内容
2. `list_files` - 列出目录下文件
3. `read_symbols` - 读取代码符号 (def/class)
4. `read_imports` - 读取文件所有 import
5. `summarize_file` - 文件摘要
6. `git_status` / `git_diff` / `git_log` - Git 操作

**写入工具 (4)**:
1. `partial_update` - 局部精准替换
2. `insert_content` - 锚点插入内容
3. `regex_replace` - 正则批量替换
4. `write_file` - 完整写入文件

**执行工具 (2)**:
1. `execute_code` - Python AST 安全检查 + JS 子进程隔离，30s 超时
2. `run_command` - 危险命令黑名单 + 命令前缀白名单，60s 超时

**网络工具 (2)**:
1. `web_search` - DuckDuckGo 搜索
2. `http_request` - SSRF 防护的 HTTP 请求

**注册表**:
- `SPECIALIST_TOOLS`: 18 个工具 (供 Specialist 使用)
- `ANALYSIS_TOOLS`: 6 个只读工具子集 (供 AgentExecutor 分析任务)
- `ToolRegistry` (executor.py): 18 个工具 (供 ReActAgent 使用)

### Code Sandbox (代码沙箱)

**位置**: `specialist_base.py` 内嵌

**Python 沙箱**:
```python
# AST 安全检查
ast.parse(code)
# 禁止节点: exec/eval/compile/__import__/open/getattr/setattr
# 限制性 builtins: print/len/range/list/dict/set/tuple/str/int/float/bool
# 30s 超时
```

**JavaScript 沙箱**:
```python
# Node.js 子进程
node --experimental-vm-modules
# 禁止模式: child_process/fs/eval/Function/process.exit/process.env
# 30s 超时
```

**API 端点**:
- `GET /api/v2/admin/sandbox-config` - 查看
- `PUT /api/v2/admin/sandbox-config` - 修改（superadmin）

**配置**:
```python
ENABLE_CODE_SANDBOX = True
SANDBOX_LANGUAGES = "python,javascript"
```

---

最后更新：2026-06-04
