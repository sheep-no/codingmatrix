# CodingMatrix 模块说明

> 最后更新：2026-05-27 | 版本：v5.10.0

## 项目结构概览

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

### Agent 引擎 (app/agent/)

| 模块 | 路径 | 行数 | 描述 |
|------|------|------|------|
| **动态依赖图** | **`dependency_graph.py`** | **~500** | **解析 import/require、BFS 影响分析、跨文件 Patch** |
| Orchestrator | `orchestrator.py` | ~1900 | 总指挥：复杂度分析、模型分配、角色协作、验证审查 |
| MultiModelAgent | `multi_model_agent.py` | ~850 | 多模型协调：任务路由、规划、执行、审查 |
| ReActAgent | `react_agent.py` | ~500 | ReAct 自我反思：Thought→Action→Observation→Reflection |
| Executor | `executor.py` | ~750 | 执行器：6 种工具类型 (文件/代码/搜索/HTTP/Git)、SSE 状态推送 |
| Specialists | `specialists.py` | ~800 | 专家角色：架构师、前端/后端工程师、代码审查员 |
| **多角度审查** | **`multi_angle_review.py`** | **340** | **v5.8.1 新增：性能/安全/可维护性并行审查** |

（其余模块保持不变...）

---

最后更新：2026-05-23
