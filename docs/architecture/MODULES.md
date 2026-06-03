# CodingMatrix 模块说明

> 最后更新：2026-06-02 | 版本：v5.12.0+

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

### Agent 引擎 (app/agent/)

| 模块 | 路径 | 行数 | 描述 |
|------|------|------|------|
| **动态依赖图** | **`dependency_graph.py`** | **~500** | **解析 14 种语言 import/require、BFS 影响分析、跨文件 Patch、`__init__.py` 最后生成** |
| **智能会话恢复** | **`helpers.py`** | **~150** | **v5.11.0+ 新增：resolve_resume_session 语义匹配 + Qwen3-8B 默认** |
| Orchestrator | `orchestrator.py` | ~1900 | 总指挥：复杂度分析、模型分配、角色协作、验证审查 |
| OrchestratorFiles | `orchestrator_files.py` | **~600** | **v5.12.0+ 增强：Edit marker 检测、Git stash 原子回滚** |
| OrchestratorGeneration | `orchestrator_generation/` | **~3000** | **v5.12.0+ 增强：动态批处理、is_existing_file 模式** |
| MultiModelAgent | `multi_model_agent.py` | ~850 | 多模型协调：任务路由、规划、执行、审查 |
| ReActAgent | `react_agent.py` | ~500 | ReAct 自我反思：Thought→Action→Observation→Reflection |
| Executor | `executor.py` | ~750 | 执行器：12 种工具类型 (文件/代码/搜索/HTTP/Git)、ToolRegistry |
| SpecialistBase | `specialist_base.py` | **~800** | **v5.12.0+ 增强：13 工具、编辑追踪、代码沙箱、call_llm_with_tools** |
| Specialists | `specialists.py` | ~800 | 专家角色：架构师、前端/后端工程师、代码审查员 |
| DynamicModelRouter | `dynamic_model_router.py` | **~900** | **v5.12.0+ 增强：健康度评分、熔断、5×5 模型分配 v2.0** |
| SessionManager | `session_manager.py` | **~500** | **v5.12.0+ 增强：5 状态机、僵尸检测、429 响应** |
| CodeValidator | `code_validator.py` | **~600** | **v5.12.0+ 修复：完整模块路径提取、sys.path 自动配置** |
| **多角度审查** | **`multi_angle_review.py`** | **340** | **v5.8.1 新增：性能/安全/可维护性并行审查** |

（其余模块保持不变...）

---

## v5.12.0+ 新增详细模块

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

### Specialist Tools (13 工具)

**文件**: `app/agent/specialist_base.py`

**9 个只读工具**:
1. `read_file` - 读取文件
2. `list_files` - 列目录
3. `search_in_files` - 搜索
4. `glob_files` - glob 匹配
5. `read_symbols` - 读符号
6. `find_definition` - 找定义
7. `read_imports` - 读导入
8. `find_references` - 找引用
9. `summarize_file` - 文件摘要

**4 个写入/验证工具**:
1. `partial_update` - 局部更新
2. `insert_content` - 插入内容
3. `regex_replace` - 正则替换
4. `execute_code` - 沙箱执行

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

最后更新：2026-06-02
