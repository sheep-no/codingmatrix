# CodingMatrix 模块说明

> 最后更新：2026-06-09 | 后端代码：356 文件 / 99,618 行 | 前端代码：~58,000 行 | 端点：226+ | Agent 模块：76 + 3 子包

## 项目结构概览

```
codingmatrix/
├── app/                         # 后端 (FastAPI, Python 3.11, 356 文件 / 99,618 行)
│   ├── agent/                   # Agent 核心 (76 模块 + 3 子包, 34,166 行)
│   │   ├── adapters/            # 语言适配器 (generic/python/javascript)
│   │   ├── orchestrator_generation/   # 4 mixin: spec_first/traditional/incremental/evaluate
│   │   ├── orchestrator_requirements/ # 3 层需求关联 + 双模型对抗
│   │   └── *.py                 # 76 个核心 Agent 模块
│   ├── api/                     # API 路由 (25 个 include_router, 16,080 行)
│   │   ├── v1/                  # 19 个用户功能模块
│   │   │   └── ai_agent/        # 5 子路由聚合 (orchestrate/generate/association/knowledge/performance)
│   │   └── v2/                  # 8 个管理功能模块
│   ├── core/                    # 核心配置 (4 文件, 1,042 行)
│   ├── db/                      # 数据库 + 业务表 (12 文件)
│   ├── middleware/              # 4 个中间件 (765 行)
│   ├── models/                  # ORM 数据模型 (14 文件, 833 行)
│   ├── schema/                  # Pydantic Schema
│   ├── services/                # 服务层 (14 文件, 3,277 行)
│   ├── tasks/                   # 异步任务
│   └── utils/                   # 工具函数 (65+ 文件, 15,734 行)
│       ├── aicloud/             # AI Cloud 子包 (28 文件)
│       ├── workflow/            # 工作流引擎子包
│       ├── pptx/                # PPT 生成子包 (11 文件)
│       └── validators/          # 验证器子包
├── src/                         # 前端 (Vue 3, 58,155 行)
│   ├── api/                     # API 客户端 (16 模块)
│   ├── components/              # Vue 组件 (69 + 13 Agent 子组件)
│   │   ├── agent/               # Agent 子组件 (7 layout + 6 modal)
│   │   ├── settings/            # 设置相关
│   │   └── ui/                  # 通用 UI
│   ├── composables/             # 组合式 API (13 个, 含 1 wrapper)
│   ├── constants/
│   ├── router/                  # Vue Router (16 路由)
│   ├── stores/                  # Pinia 状态 (9 stores)
│   ├── styles/
│   ├── utils/                   # 前端工具
│   └── views/                   # 页面视图 (9 视图)
├── tests/                       # 测试 (88 单元 + 2 集成 + 77 E2E)
│   ├── archive/                 # 归档的旧测试
│   ├── e2e/                     # Playwright E2E (77 spec.js)
│   ├── fixtures/                # Playwright fixtures
│   ├── frontend/                # 前端测试
│   ├── integration/             # 集成测试 (2 文件, 历史归档于 archive/)
│   ├── performance/             # 性能测试
│   └── unit/                    # 单元测试 (88 文件 / 1376 用例)
├── configs/                     # 配置文件
├── data/                        # 数据目录 (SQLite, model_config, learning_data)
├── docs/                        # 文档中心
├── migrations/                  # Alembic 数据库迁移 (11 个版本)
├── projects/                    # 用户项目上传目录
├── scripts/                     # 运维脚本
├── sessions/                    # Agent 会话数据
├── logs/                        # 日志目录
├── cache/                       # 缓存目录
├── keys/                        # 密钥目录 (RSA)
├── .claude/                     # AI Agent 配置
├── .monkeycode/                 # 项目级记忆与规格
├── .github/                     # CI/CD 配置
├── main.py → app/main.py        # 项目启动入口
├── Makefile                     # Make 命令集
├── pyproject.toml               # Python 项目配置
└── playwright.config.js         # Playwright 根级配置
```

## 项目规模 (2026-06-09)

### 后端规模

| 维度 | 数量 | 同比 v5.14.0 |
|------|------|--------------|
| Python 文件 | **356** | 持续扩展 |
| 代码总行数 | **99,618** | +20% |
| Agent 模块 | **76 + 3 子包** | 一致 |
| API 路由模块 | **25** (include_router 次数) | 26→25 修正 |
| API 端点 | **226+** | +20 |
| 中间件 | **4** | 一致 |
| 服务层 | **14** | 新增列项 |
| 单文件 1000+ 行 | **6** | cross_validator/tools/dynamic_model_router/dependency_graph/agent_core/aiGeneratorPptx |

### 前端规模

| 维度 | 数量 | 备注 |
|------|------|------|
| Vue 文件 | **69** | 与 v5.14.0 一致 |
| 前端代码总行数 | **58,155** | 含 views/components/composables |
| Pinia Stores | **9** | v5.14.0 报告 8, **多出 `providers`** |
| Composables | **13** | v5.14.0 报告 15, **多报 2 个**（实际 12 业务 + 1 wrapper） |
| API 客户端模块 | **16** | v5.14.0 报告 14, **多出 2 个** |
| 视图页面 | **9** | v5.14.0 报告 8, **多出 `Docs.vue`** |
| 路由 | **16** | 含 1 通配、1 重定向、1 别名 |
| Agent 子组件 | **7 layout + 6 modal** | 新模块文档化 |

### 测试规模

| 维度 | 数量 | 备注 |
|------|------|------|
| 单元测试文件 | **88** | 1376 用例 |
| 集成测试文件 | **2** | v5.11.0 报告 20+, **已归档 21 个到 archive/integration_old/** |
| E2E spec 文件 | **77** | 409 用例 |
| 归档测试 | **56+** | tests/archive/legacy/ + integration_old/ |

### 已知技术债务

1. **巨型单文件** (需拆分):
   - `app/utils/agent_core.py` 2,393 行
   - `app/api/v1/aiGeneratorPptx.py` 1,723 行
   - `app/api/v1/ai_agent/orchestrate_endpoints.py` 1,302 行
   - `app/api/v1/aicloud.py` 928 行
   - `app/api/v1/Aicode.py` 919 行
   - `app/api/v1/kolors_api.py` 802 行
2. **重复实现**:
   - `app/utils/rate_limiter.py` (slowapi) vs `app/middleware/rate_limiter.py` (自研)
   - `app/db/models.py` vs `app/models/` (业务表分散)
   - `src/utils/crypto.js` vs `src/utils/encryption.js` (前端加密重复)
   - `src/composables/useAgentSession.js` 是 `stores/agentSession.js` 的薄包装 (死代码)
3. **废弃前端组件** (`src/components/agent/`):
   - `AgentHeader.vue` (114 行) 与 `AgentTopBar.vue` (180 行) 重叠
   - `AgentInputPanel.vue` (322 行) 与 `AgentInputBar.vue` (213 行) 重叠
4. **生产清理**: 前端 213 处 `console.*` 调用未通过 terser 清理
5. **双层架构**: `app/api/v1/aicloud.py` (928 行) 与 `app/utils/aicloud/` (28 文件) 职责重叠
6. **TODO 占位**: `spec_first_generate.py:1291-1297`, `cross_validator.py:1145,1199`

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
| 主应用 | `app/main.py` | **363** | FastAPI 应用入口，7 层中间件，25 个 include_router |
| Celery 配置 | `app/celery_app.py` | 120 | Celery 异步任务配置 |
| 配置 | `app/core/config.py` | 181 | pydantic-settings 环境变量加载，`SECRET_KEY` 校验 |
| 日志配置 | `app/core/logging_config.py` | 248 | `SensitiveDataFilter` 10 类敏感信息脱敏 |
| 优雅关闭 | `app/core/graceful_shutdown.py` | 287 | 4 状态机 (RUNNING/DRAINING/SHUTTING_DOWN/TERMINATED) |
| 文件验证 | `app/core/file_validator.py` | 292 | 文件安全验证 (新增) |
| 数据库 | `app/db/database.py` | 36 | SQLAlchemy async + `AsyncAdaptedQueuePool` |
| 调度器 | `app/db/scheduler.py` | 204 | APScheduler 定时任务 (归档 10 天/清理 30 天) |
| 聊天归档 | `app/db/chat_archiver.py` | 372 | 用户聊天归档 |

### Agent 引擎 (app/agent/) - 76 模块 + 3 子包 / 34,166 行

| 模块 | 路径 | 行数 | 描述 |
|------|------|------|------|
| **tools.py** | `tools.py` | **1,079** | **唯一工具实现源，21 个内置工具 + SPECIALIST_TOOLS 注册表** |
| **react_engine.py** | `react_engine.py` | **684** | **统一 ReAct 引擎，simple + full 双模式，滑动窗口历史 (300s 单轮超时)** |
| **mcp_client.py** | `mcp_client.py` | **513** | **MCP Client，stdio/HTTP 双传输，JSON-RPC 2.0 (协议 2024-11-05)** |
| **llm_client.py** | `llm_client.py` | **191** | **统一 LLM 调用层，并发信号量 (MAX_CONCURRENT=6) + 超时 + 成本追踪** |
| **json_parser.py** | `json_parser.py` | **345** | **统一 JSON 解析，5 层链路 + 工具调用 3 种策略** |
| Orchestrator | `orchestrator.py` | **137** | 总指挥：6 mixin 组合 (Progress/Generation/Files/Testing/Utils/Requirements) |
| MultiModelAgent | `multi_model_agent.py` | 246 | 多模型协调：任务路由、规划、执行、审查 |
| SpecialistBase | `specialist_base.py` | 177 | Specialist 基类，委托 LLMClient + json_parser |
| DynamicModelRouter | `dynamic_model_router.py` | 996 | 健康度 0-100 评分、熔断、角色模型分配、降级链、学习路由 |
| ComplexityAnalyzer | `complexity.py` | 245 | 关键词复杂度分析，用于架构决策（不影响模型选择） |
| ModelRegistry | `models.py` | 373 | 12 种任务类型、7 种能力、10 个模型注册 |
| CodeValidator | `code_validator.py` | 755 | 语法/导入/运行时/API 兼容性验证，LRU 缓存 |
| DependencyGraph | `dependency_graph.py` | 1,007 | 依赖图核心，14 语言 import 解析 + 拓扑排序 + BFS 影响分析 |
| DependencyRules | `dependency_rules.py` | 183 | 外部化依赖规则 (DEPENDENCY_RULES + PATH_TYPE_RULES) |
| SignatureExtractor | `signature_extractor.py` | 144 | 函数签名提取 (9 种语言正则) |
| ShadowScanner | `shadow_scanner.py` | 83 | 影子扫描 |
| TopologyScheduler | `topology_scheduler.py` | 372 | 动态拓扑调度器 |
| ErrorRecovery | `error_recovery.py` | 797 | 验证-修复-重试 (3 次) + 4 级降级链 + 供应商感知 |
| FeedbackLearner | `feedback_learner.py` | 434 | 修复模式学习 + 向量匹配 |
| Memory | `memory.py` | 571 | 对话记忆 + 知识记忆，自动压缩 |
| SharedContext | `shared_context.py` | 337 | 全局共享上下文 |
| TaskPlanner | `task_planner.py` | 177 | 任务拆解，支持 ReAct 探索模式 |
| CodeReviewer | `code_reviewer.py` | 158 | 代码审查员 |
| CrossValidator | `cross_validator.py` | 1,361 | 双模型生成 + 第三个模型裁判选择 |
| SpecFirstGenerator | `spec_first_generator.py` | 484 | 规范先行生成 (OpenAPI→类型→DB→配置) |
| RefinementLoop | `refinement_loop.py` | 515 | 迭代修复循环 |
| FileContract | `file_contract.py` | 141 | 文件操作安全契约 |
| Tracing | `tracing.py` | 246 | OpenTelemetry 分布式追踪 |
| SessionManager | `session_manager.py` | **582** | 5 状态机 (RUNNING/PAUSED/COMPLETED/FAILED/CANCELLED) + DB 写透 |
| **OrchestratorGeneration** | `orchestrator_generation/` | **2,364** | **spec_first/traditional/incremental/evaluate 5 个 mixin** |
| **OrchestratorRequirements** | `orchestrator_requirements/` | **1,037** | **3 层需求关联 + 双模型对抗 + 魔鬼代言人** |
| **Adapters** | `adapters/` | **~1,600** | **语言适配器：generic/python/javascript/language_adapter** |

### API 路由 (app/api/) - 25 个 include_router / 16,080 行

#### v1 用户 API (19 模块)

| 模块 | 文件 | 行数 | 端点数 | 主要端点 |
|------|------|------|--------|----------|
| **ai_agent** (子包) | `ai_agent/router.py` + 5 子路由 | **3,313** | 30+ | `POST /api/v1/agent/orchestrate[/stream]`、`/generate`、`/modify`、`/stop/{sid}`、`/rollback`、`/snapshots/{sid}`、`/analyze_complexity`、`/evaluate`、`/search_sessions`、`/requirement-association`、`/knowledge`、`/performance`、`/concurrent-limits`、`/learning/*`、`/token-usage` |
| auth | `auth.py` | 550 | 9 | `/public-key`、`/csrf-token`、`/login`、`/register`、`/refresh`、`/user/profile`、`/history`、`/conversation/history`、`/conversations` |
| Aicode | `Aicode.py` | 919 | 5+ | 流式代码生成 |
| AiProjectCode | `AiProjectCode.py` | - | - | 项目级代码生成 |
| apikey | `apikey.py` | 585 | 11 | `POST /agent/apikey`、`/test`、`/batch/import`、`PUT /{token}/enabled`、`/context-lengths`、`/fallback-preference` |
| providers | `providers.py` | 238 | 7 | `POST/GET /providers`、`/{id}/sync`、`/{id}/test` |
| model_manager | `model_manager.py` | 213 | - | `GET /models/`、`/agent-config` (用户端) |
| workflow | `workflow.py` | 676 | 9 | `/execute`、`/{wf_id}/execute`、`/status/{wf_id}`、`/import`、`/export/{wf_id}`、`/history[/...]` |
| file_upload | `file_upload.py` | 460 | - | 分片上传 (5MB), 断点续传 |
| task_queue | `task_queue.py` | 353 | - | `POST /tasks` (Celery 驱动), WebSocket 进度推送 |
| vision_api | `vision_api.py` | 310 | 4 | `/analyze`、`/ocr`、`/code-from-image`、`/safety-check` |
| aicloud | `aicloud.py` | 928 | 14 | `/chat[/stream]`、`/read`、`/write`、`/history[/search/export]`、`/audit-logs`、`/reviews` (approve/reject)、`/execute`、`/models` |
| aicloud_knowledge | `aicloud_knowledge.py` | 346 | 4 | `/upload`、`/docs`、`/docs/{id}`、`/search` |
| kolors_api | `kolors_api.py` | 802 | 6 | Kolors 图像生成 |
| aiGeneratorPptx | `aiGeneratorPptx.py` | **1,723** | 4 | PPT 生成 (最大文件) |
| github | `github.py` | - | - | GitHub 集成 |
| health | `health.py` | - | - | 健康检查 |

#### v2 管理 API (8 模块)

| 模块 | 文件 | 行数 | 端点数 | 主要端点 |
|------|------|------|--------|----------|
| Controller (v2) | `Controller.py` | 337 | 1+WS | `WS /Controller/sys-status`、系统状态 |
| user_manage | `user_manage.py` | 295 | 5 | `/Controller/users`、`/create_user`、`/update_user/{id}`、`/delete_user/{id}`、`/{id}/reset-password` |
| admin_config | `admin_config.py` | 129 | 6 | `/user-limit`、`/config` (get/post)、`/sandbox-config` |
| model_admin (v2) | `model_admin.py` | 332 | - | `/default`、`/agent-config`、`/fallback-chain`、`/error-type-model`、`/context-length` |
| mcp_admin | `mcp_admin.py` | 232 | - | `/servers` (CRUD + test + toggle) |
| guardian_router | `guardian_router.py` | **858** | - | `/guard/start`、服务监控、Guardian 管理 (最大 v2 模块) |
| nginx_api | `nginx_api.py` | 503 | - | Nginx 配置检查/生成/部署/导入导出 |

### 中间件 (app/middleware/) - 4 个 / 765 行

| 模块 | 行数 | 职责 |
|------|------|------|
| `rate_limiter.py` | 377 | 多级限流 (全局/IP/用户/端点), 内存实现, 端点级配置 |
| `input_validator.py` | 215 | SQL 注入 + XSS 检测 (10+ SQL 模式, 12+ XSS 模式), 10MB body 上限 |
| `security_headers.py` | 103 | CSP/X-Frame-Options/XSS-Protection/Referrer-Policy/Cross-Origin-* |
| `feature_switch.py` | 70 | 4 路径功能开关 (aicloud/docker/project/workflow), 禁用返回 503 |

### 服务层 (app/services/) - 14 文件 / 3,277 行

| 模块 | 行数 | 职责 |
|------|------|------|
| `apikey_manager.py` | 630 | Redis 存储 + Lua 原子脚本, 6 供应商, TTL 5 选项 + 自定义, `KeyMetadata` (含 `fallback_preference`、`custom_fallback_chain`) |
| `custom_provider_manager.py` | 273 | 用户自定义供应商, OpenAI/Anthropic 双协议, 1 小时模型缓存 |
| `audit_logger.py` | 218 | Redis List 存储 + 30 天过期, 按 user/date 双索引 |
| `health_checker.py` | 347 | API/DB/Redis/Celery/WS/系统资源六项检查 |
| `websocket_manager.py` | 193 | 用户分组连接、任务订阅、`WS_MAX_CONNECTIONS=50` |
| `feature_switch.py` | - | 服务级功能开关 (v2) |
| `log_config.py` | - | 日志配置服务 |
| `resource_config.py` | - | 资源配置服务 |
| `provider_health.py` | - | 供应商健康检查 |
| `rate_limit_config.py` | - | 速率限制配置 |
| `prometheus_metrics.py` | - | Prometheus 指标 |
| `agent_memory_service.py` | - | Agent 记忆服务层 |
| `user_preferences.py` | - | 用户偏好 |

### 核心工具 (app/utils/)

| 模块 | 行数 | 职责 |
|------|------|------|
| `agent_core.py` | **2,393** | `ProjectGeneratorAgent` 主入口 (最大工具模块, 需拆分) |
| `guardrails.py` | 452 | `PromptInjectionDetector` (11+ 模式 + 8 关键词 + 结构异常检测) |
| `cache.py` | 349 | `MemoryCache` (LRU) + `RedisCache` 双 backend 切换 |
| `csrf.py` | 164 | `CSRFTokenManager`, 双重提交 Cookie 模式 |
| `rate_limiter.py` | 38 | `slowapi` 包装, 全局 100/minute (与 middleware/ 重叠) |
| `permissions.py` | 51 | 3 级权限 (normal/admin/superadmin) |
| `aicloud/` | 28 文件 | AI Cloud 完整子模块 |
| `workflow/` | - | 工作流引擎子包 |
| `pptx/` | 11 文件 | PPT 生成子包 |
| `validators/` | - | 验证器子包 |
| `dynamic_package_manager.py` | - | 动态依赖管理 |

### 数据模型 (app/models/) - 14 文件 / 833 行

| 模型 | 说明 |
|------|------|
| `User` | 用户表 (id, username, email, password_hash, permission_level) |
| `Permission` | 权限表 (id, user_id, level, granted_at) |
| `History` | 对话历史 (id, user_id, prompt, response, created_at) |
| `ChatHistory` + `chat_history_service.py` | 新版对话 (id, user_id, session_id, message, token_usage) |
| `File` | 文件管理 (id, user_id, filename, path, size) |
| `Task` | 任务队列 (id, user_id, status, result) |
| `SavedProject` | 保存项目 (id, user_id, name, project_data) |
| `ServerConfig` + `server_stats` | 服务配置/统计 |
| `AgentSession` + `AgentMemory` + `AgentReflection` | Agent 会话/记忆/反思 |
| `KnowledgeEntry` | 知识库 |
| `ToolExecutionLog` | 工具执行日志 |
| `ModelUsageStats` | 模型使用统计 |
| `AicloudSession/Message/Review/AuditLog` | AI Cloud |
| `AicloudKnowledge*` | 知识库文档/分片 |
| `ProjectSession` (db/) | 项目会话 (v5.12.0+) |
| `WorkflowHistory` (db/) | 工作流历史 |
| `ImageGenerationHistory` (db/) | 图像生成历史 |

---

## 前端模块 (src/) - ~58,000 行

### 路由 (src/router/index.js) - 16 路由

| 路径 | 组件 | 权限 | 备注 |
|------|------|------|------|
| `/` | `components/index.vue` | requiresAuth | 默认首页 |
| `/project-generate` | (重定向 → `/agent`) | - | 旧路径兼容 |
| `/agent` | `views/AgentDashboard.vue` | requiresAuth | 核心 Agent 工作台 (384 行) |
| `/workflow` | `views/Workflow.vue` | requiresAuth | 自然语言生成工作流节点 |
| `/ppt-generate` | `views/PPTGenerate.vue` | requiresAuth | 主题+模板生成 |
| `/ppt-preview/:id` | `views/PPTPreview.vue` | requiresAuth | HTML 预览/PPTX 下载 |
| `/image-generate` | `views/ImageGenerate.vue` | requiresAuth | Kolors 文生图/图生图 |
| `/kolors` | `views/ImageGenerate.vue` | requiresAuth | `/image-generate` 别名 |
| `/aicloud` | `components/Aicloud.vue` | requiresAuth | AI Cloud 沙箱 |
| `/github-config` | `components/GithubConfigPanel.vue` | requiresAuth | GitHub 集成配置 |
| `/settings` | `views/Settings.vue` | requiresAuth | 4 Tab (providers/apikey/agent/admin) |
| `/admin` | `components/AdminPanel.vue` | requiresAuth + requiresSuper | 旧版管理面板 |
| `/admin/dashboard` | `views/AdminDashboard.vue` | requiresAuth + requiresSuper | 1870 行管理控制台 |
| `/docs` | `views/Docs.vue` | requiresAuth | 文档中心 (1140 行) |
| `/chart-editor` | `views/ChartEditorPage.vue` | requiresAuth | ECharts 数据可视化 (1304 行) |
| `/:pathMatch(.*)*` | → `/` | - | 通配 |

> 守卫逻辑：`requiresAuth` 不阻断未登录请求 (首页会弹登录框), `requiresSuper` 检查 `permissionLevel` 为 `admin` 或 `superadmin`

### Pinia Stores (src/stores/) - 9 stores

| Store | 行数 | 风格 | 核心 State | 关键 Actions |
|-------|------|------|-----------|---------------|
| `agentSession` | 194 | setup | `currentSessionId`/`projectPrompt`/`sessionHistory`(≤10)/`isGenerating`/`workflowStages`/`modelAssignments`/`roles` | `createNewSession`/`deleteSession`/`switchSession`/`fetchRoles`/`getETA` |
| `agentWorkspace` | 236 | setup | `generatedFiles`/`selectedFile`/`fileDiffs`/`logs`/`executionDetails`/`thinkingMessages`/`pendingDecisions`/`costData`/`performanceMetrics`/`testResults`/`validationResults` | `getLanguage`(27 种扩展名)/`getHighlightedCode`/`addLog`/`clearWorkspace` |
| `apikey` | 307 | setup | `tokens`/`publicKey`/`modelOverrides`/`loading` | `submitKey`(RSA 加密)/`testKey`/`deleteKey`/`listKeys`/`toggleEnabled`/`updateContextLengths` |
| `providers` | **142** | setup | `providers`/`loading` | `listProviders`/`addProvider`/`deleteProvider`/`syncModels`/`testProvider`/`getAllDynamicModels` |
| `github` | 100 | options + persist | `githubUsername`/`githubToken`(hex 编码)/`useGithub` | `setGithubToken`(hex 编/解码)/`isGithubConfigured` |
| `logs` | 194 | setup | `systemLogs`(≤500)/`filteredLogs`/`logType`/`filterLevel`/`filterKeyword` | `addLog`/`applyFilters`/`saveLogsToStorage`/`restoreLogsFromStorage` |
| `navigation` | 277 | setup + persist | 11 个 `show*` 标志 + `isCollapsed` | `showTool`/`hideTool`(互斥)/`activeTool` |
| `task` | 211 | options API | `tasks`(Map)/`activeTasks`/`completedTasks`(≤50) | `initNotifications`(订阅)/`handleTaskUpdate` |
| `user` | 159 | setup + persist | `isLoggedIn`/`username`/`email`/`permissionLevel` | `setUser`/`clearUser`/`restoreUser`/`refreshAccessToken` |

### Composables (src/composables/) - 13 个 (含 1 wrapper)

| Composable | 行数 | 职责 |
|------------|------|------|
| `useAgentBackend` | 332 | 后端操作: 项目列表/保存/下载/删除/性能指标/快照/缓存/设置/复杂度分析/停止/决策提交 |
| `useAgentFiles` | 213 | 文件状态: `generatedFiles`/`selectedFile`/`fileCategories`(前端/后端/测试/配置 4 类)/6 个快速模板 |
| `useAgentGeneration` | 118 | 生成状态: `isGenerating`/`workflowStages`/`currentPhase`/`roles`/`modelAssignments`/`recoveryAttempts` |
| `useAgentSession` | 30 | **Pinia store 的薄包装** (向后兼容, `saveSessionState` 等 no-op) |
| `useAgentStreaming` | **423** | SSE 流处理核心: 18 种消息类型, `AGENT_ROLE_ALIAS` 映射, 429 处理 |
| `useAgentWorkspace` | 207 | 工作区状态: 日志/执行详情/思考消息/待决策/版本历史/成本/性能, `importZipFile` |
| `useAuth` | 92 | 登录/注册/登出/刷新 token/更新资料 |
| `useClipboard` | 45 | 复制到剪贴板 (`navigator.clipboard` + `execCommand` fallback) |
| `useFileDrop` | 139 | 全局拖拽监听, 类型/大小校验 |
| `useKeyboardShortcuts` | 118 | 快捷键注册 (普通 + 序列, 1.5s 超时) |
| `useMarkdown` | 37 | markdown-it + DOMPurify + highlight.js |
| `useOfflineQueue` | 110 | 断网队列: online/offline 事件 + localStorage 持久化 |
| `useToast` | 39 | 全局 toast, 最多 10 条 (FIFO) |

### 视图页面 (src/views/) - 9 视图

| 视图 | 行数 | 职责 |
|------|------|------|
| `AgentDashboard.vue` | 384 | **核心页面**: 编排 6 个 composable, 渲染 5 个子组件 + 6 个 modal |
| `AdminDashboard.vue` | **1,870** | 管理控制台: 用户/会话/限制统计、并发限制、模型分配、缓存、学习反馈 |
| `ChartEditorPage.vue` | 1,304 | 图表编辑器: xlsx/csv/json 导入、ECharts 配置、字段映射、导出 |
| `Docs.vue` | 1,140 | 文档中心: 搜索 + 分类导航 + 卡片展开 |
| `ImageGenerate.vue` | 792 | Kolors 绘画: text2img/img2img 双模式、风格、分辨率、参考图 |
| `PPTGenerate.vue` | 586 | PPT 生成: 主题输入 + 6 个模板 + 幻灯片数 + 进度流式 |
| `PPTPreview.vue` | 403 | PPT 预览: HTML iframe (sandbox) + 传统卡片回退 + PDF/PPTX 下载 |
| `Workflow.vue` | 421 | 工作流编排: 自然语言 → 节点列表 + 节点卡片预览 + JSON 导出 |
| `Settings.vue` | 61 | 设置: 4 Tab (providers/apikey/agent/admin[superuser]) |

### Agent 子组件 (src/components/agent/)

**Layout 子组件 (7 个)**

| 组件 | 行数 | 用途 |
|------|------|------|
| `AgentWorkspace.vue` | 770 | 主工作区: 进度条 + 时间线 (带 thinking 展开) + 决策面板 + 测试/验证结果 |
| `AgentSidebar.vue` | 303 | 会话历史列表 + 项目文件树 + 搜索/类型过滤 |
| `AgentInputPanel.vue` | 322 | 输入面板 (带 6 个快速模板 + 模型选择 + 项目名) — **与 InputBar 重叠, 建议废弃** |
| `AgentInputBar.vue` | 213 | 底部输入条: 模型选择 + 提示词 + 发送/停止 |
| `AgentTopBar.vue` | 180 | 顶部栏: 状态徽标 + token 费用/速度 + 导入/设置/更多菜单 |
| `AgentFilePanel.vue` | 162 | 文件预览: 代码高亮 + 变更/保存/历史/复制/下载/删除 |
| `AgentHeader.vue` | 114 | 旧版页面头 — **与 TopBar 重叠, 建议废弃** |

**Modals (6 个)**

| 组件 | 行数 | 用途 |
|------|------|------|
| `SettingsModal.vue` | 85 | Agent 设置 (角色/模型/并发/各开关) |
| `PerformanceModal.vue` | 48 | 性能统计弹窗 |
| `LearningModal.vue` | 31 | 学习反馈统计 |
| `UploadModal.vue` | 29 | ZIP 导入 |
| `DiffModal.vue` | 26 | 文件 diff |
| `VersionHistoryModal.vue` | 26 | 文件版本历史/快照 |

### API 客户端 (src/api/ + src/utils/api/) - 16 模块

| 模块 | 职责 |
|------|------|
| `api/apikey.js` | API Key 管理 (RSA 加密) |
| `utils/api/base.js` | 基础 axios/fetch 封装 |
| `utils/api/auth.js` | 登录/注册/登出 |
| `utils/api/project.js` | 项目管理 |
| `utils/api/agent.js` | Agent 接口 (含 apikey 相关方法) — **与 api/apikey.js 重叠** |
| `utils/api/workflow.js` | 工作流 |
| `utils/api/girl.js` | AI 女友 |
| `utils/api/chat.js` | 对话 |
| `utils/api/file.js` | 文件 |
| `utils/api/task.js` | 任务 |
| `utils/api/ppt.js` | PPT |
| `utils/api/kolors.js` | 图像 |
| `utils/api/aicloud.js` | AI Cloud |
| `utils/api/admin.js` | 管理 |
| `utils/api/github.js` | GitHub |
| `utils/api/websocket.js` | WebSocket (websocketPool 546 行) |
| `utils/api/config.js` | 配置 |
| `utils/api/index.js` | 统一入口 (123 行) |

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
- `get_assignment(role)` - 获取角色模型分配（无复杂度参数）
- `record_call_result(model, success, latency)` - 记录调用
- `is_healthy(model)` - 检查健康
- `get_fallback(primary)` - 获取降级模型
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

最后更新：2026-06-09
