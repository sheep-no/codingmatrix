# 会话生命周期

> 最后更新：2026-06-02 | 版本：v5.12.0+

会话生命周期是 v5.12.0+ 增强的核心子系统，负责管理 Agent 项目会话的创建、运行、暂停、取消、清理全过程。

---

## 概述

CodingMatrix 的 Agent 会话（Project Session）代表一次完整的项目生成或修改任务。会话生命周期包括：

1. **创建**: 用户提交需求时创建
2. **运行**: Orchestrator 执行 5 阶段生成
3. **暂停**: 用户主动暂停
4. **恢复**: 继续执行
5. **取消**: 用户主动取消
6. **完成**: 成功/失败结束
7. **清理**: TTL 过期后自动清理

---

## 5 状态机

```
                    创建
                     ↓
                 ┌────────┐
                 │running │ ←──┐
                 └────┬───┘    │
                      │        │ 恢复
              ┌───────┼────┐   │
              ↓       ↓    ↓   │
        ┌────────┐ ┌──────┐ ┌──┴──┐
        │completed│ │failed│ │paused│
        └────────┘ └──────┘ └──────┘
              ↑       ↑
              │       │ 取消 / 异常
              │  ┌────────┐
              └──│cancelled│
                 └────────┘

              ↓ 30 天 TTL 过期
        ┌────────┐
        │expired │
        └────────┘
```

| 状态 | 描述 | 终态 |
|------|------|------|
| `running` | 正在执行 | ❌ |
| `paused` | 已暂停 | ❌ |
| `completed` | 成功完成 | ✅ |
| `failed` | 执行失败 | ✅ |
| `cancelled` | 用户取消 | ✅ |
| `expired` | TTL 过期 | ✅ |

---

## 核心配置

```python
# app/core/config.py
MAX_PROJECT_SESSIONS_PER_USER = 2  # 并发限制
SESSION_TTL_DAYS = 30              # TTL
MAX_SESSIONS_PER_USER = 500         # 累计上限
SESSION_CLEANUP_INTERVAL_HOURS = 24 # 清理周期
```

---

## 并发限制（429 响应）

每个用户最多同时运行 2 个项目会话。超出时返回 409 响应：

```json
{
  "error": "session_limit_reached",
  "message": "已达到项目会话并发上限（2个）",
  "active_sessions": [
    {
      "session_id": "uuid-1",
      "requirement": "创建一个博客系统",
      "started_at": "2026-06-02T10:00:00Z",
      "elapsed_seconds": 120
    },
    {
      "session_id": "uuid-2",
      "requirement": "添加用户登录功能",
      "started_at": "2026-06-02T10:05:00Z",
      "elapsed_seconds": 60
    }
  ]
}
```

**前端处理**（`AgentChat.vue`）:
- 显示 429 对话框
- 列出活跃会话
- 提供"取消并新建"或"等待"选项

---

## 僵尸会话检测

v5.12.0+ 之前存在僵尸会话问题：DB 中状态为 `running`，但内存中已不存在。v5.12.0+ 引入检测机制：

### 检测逻辑

```python
async def detect_zombie_sessions(self):
    """检测 DB 与内存不一致的会话"""
    # 1. 查询 DB 中所有 running 状态的会话
    db_running = await self.db.query(ProjectSession).filter(
        ProjectSession.status == "running"
    ).all()
    
    for session in db_running:
        # 2. 检查内存中是否存在
        in_memory = self._sessions.get(session.session_id)
        if in_memory is None:
            # 3. 标记为 expired
            session.status = "expired"
            session.completed_at = datetime.utcnow()
            await self.db.commit()
            logger.warning(f"Zombie session detected: {session.session_id}")
```

### 触发时机

- **会话创建前**: `_cleanup_old_session()` 清理已存在的僵尸会话
- **定期任务**: APScheduler 每 24 小时扫描一次
- **启动时**: 应用启动时执行一次

---

## TTL 清理

### 过期时间

- **默认 TTL**: 30 天未活跃自动清理
- **活跃定义**: 状态为 `running` 或 `paused` 不算过期
- **过期检测**: `updated_at + 30天 < now()`

### 清理逻辑

```python
async def cleanup_expired_sessions(self):
    """清理过期会话"""
    cutoff = datetime.utcnow() - timedelta(days=SESSION_TTL_DAYS)
    
    expired = await self.db.query(ProjectSession).filter(
        ProjectSession.updated_at < cutoff,
        ProjectSession.status.in_(["completed", "failed", "cancelled"])
    ).all()
    
    for session in expired:
        # 1. 删除会话文件
        if session.project_path:
            shutil.rmtree(session.project_path, ignore_errors=True)
        
        # 2. 标记为 expired
        session.status = "expired"
        await self.db.commit()
```

### 累计上限

当用户会话数（`completed + failed + cancelled`）超过 500 时，删除最旧的非活跃会话。

---

## 内存与 DB 同步

v5.12.0+ 之前，DB 和内存状态可能不一致（崩溃、异常退出等）。v5.12.0+ 引入双向同步机制：

### DB → 内存

```python
async def sync_from_db(self):
    """启动时从 DB 恢复状态"""
    sessions = await self.db.query(ProjectSession).filter(
        ProjectSession.status == "running"
    ).all()
    for session in sessions:
        # 恢复内存状态
        self._sessions[session.session_id] = InMemorySession.from_db(session)
```

### 内存 → DB

```python
async def persist_state(self, session_id: str):
    """内存状态变更时持久化"""
    session = self._sessions[session_id]
    db_session = await self.db.get(ProjectSession, session_id)
    db_session.status = session.status
    db_session.current_step = session.current_step
    db_session.progress = session.progress
    await self.db.commit()
```

---

## Session 持久化存储

### 内存存储（高速）

- 用途：实时状态、当前步骤、进度
- 位置：`session_manager._sessions` dict
- 生命周期：应用进程内

### DB 存储（持久）

- 用途：历史记录、用户恢复、统计
- 位置：`project_sessions` 表
- 生命周期：30 天

### 会话内容

#### DB 字段

```python
class ProjectSession(Base):
    __tablename__ = "project_sessions"
    
    id = Column(String, primary_key=True)        # UUID
    user_id = Column(String, index=True)
    requirement = Column(Text)                    # 原始需求
    status = Column(String)                       # 5 状态
    complexity_level = Column(String)             # SIMPLE/SMALL/MEDIUM/LARGE/XLARGE
    current_step = Column(String)                 # 当前阶段
    progress = Column(Float)                      # 0.0-1.0
    project_path = Column(String)                 # 项目目录
    error_message = Column(Text, nullable=True)
    api_key_token = Column(String)                # API Key Token
    config = Column(JSON)                         # 完整配置
    created_at = Column(DateTime)
    updated_at = Column(DateTime)
    completed_at = Column(DateTime, nullable=True)
```

#### 内存内容

```python
@dataclass
class InMemorySession:
    session_id: str
    user_id: str
    status: str
    requirement: str
    current_step: str
    progress: float
    
    # 实时数据
    sse_callback: Optional[Callable]              # SSE 推送回调
    cancel_event: Optional[asyncio.Event]         # 取消信号
    paused_event: Optional[asyncio.Event]         # 暂停信号
    
    # 上下文
    orchestrator: Optional[OrchestratorAgent]
    work_dir: Path
    spec: Dict
    complexity: Dict
```

---

## 智能"继续"语义（v5.11.0+）

用户输入"继续"或类似模糊指令时：

1. **方案 1（语义匹配）**: 通过 LLM 分析用户输入与最近 20 个 session 的语义相关性
2. **方案 2（关键词匹配）**: 提取关键词，搜索 `requirement` 字段
3. **方案 3（最新优先）**: 默认返回最近一个 `paused` 或 `failed` 的 session

详见 [AGENT.md](AGENT.md#智能会话恢复系统-v5110)

---

## API 端点

### 核心管理

| 端点 | 方法 | 描述 |
|------|------|------|
| `/api/v1/agent/sessions` | GET | 会话列表（分页、过滤） |
| `/api/v1/agent/sessions/{id}` | GET | 会话详情 |
| `/api/v1/agent/sessions/{id}` | DELETE | 删除会话 |
| `/api/v1/agent/session/{id}/action` | POST | 暂停/恢复/取消 |
| `/api/v1/agent/session/{id}/decision` | POST | 提交人工决策 |
| `/api/v1/agent/search_sessions` | POST | 语义搜索 |

### 会话动作

```json
// 暂停
POST /api/v1/agent/session/{id}/action
{"action": "pause"}

// 恢复
POST /api/v1/agent/session/{id}/action
{"action": "resume"}

// 取消
POST /api/v1/agent/session/{id}/action
{"action": "cancel"}
```

---

## 取消事件传播

v5.11.0+ 修复了取消事件不生效的问题：

```python
# session_manager.py
self._cancel_events: Dict[str, asyncio.Event] = {}

async def cancel_session(self, session_id: str):
    """取消会话"""
    if session_id not in self._cancel_events:
        self._cancel_events[session_id] = asyncio.Event()
    
    self._cancel_events[session_id].set()
    
    db_session = await self.db.get(ProjectSession, session_id)
    db_session.status = "cancelled"
    await self.db.commit()

async def is_cancelled(self, session_id: str) -> bool:
    """检查是否已取消"""
    event = self._cancel_events.get(session_id)
    return event.is_set() if event else False
```

Orchestrator 在长任务中定期检查 `is_cancelled()`，及时退出。

---

## 实施细节

**文件**: 
- `app/agent/session_manager.py` - SessionManager 类
- `app/api/v1/ai_agent/orchestrate_endpoints.py` - 端点实现
- `app/api/v1/ai_agent/helpers.py` - 辅助函数

### 关键方法

| 方法 | 描述 |
|------|------|
| `create_session()` | 创建新会话 |
| `get_session()` | 获取会话 |
| `pause_session()` | 暂停 |
| `resume_session()` | 恢复 |
| `cancel_session()` | 取消 |
| `cleanup_expired()` | 清理过期 |
| `sync_from_db()` | 从 DB 恢复 |
| `persist_state()` | 持久化到 DB |
| `detect_zombie_sessions()` | 检测僵尸 |

---

## 监控指标

### Prometheus

- `agent_session_total{status}` - 各状态会话总数
- `agent_session_duration_seconds` - 会话持续时间
- `agent_session_zombie_total` - 僵尸会话累计
- `agent_session_cleanup_total` - 清理累计

### 健康检查

```bash
curl http://localhost:8000/api/v1/agent/sessions?status=running&limit=10
```

---

## 故障排查

### 僵尸会话一直存在

1. 检查 `session_manager.detect_zombie_sessions()` 是否被调用
2. 手动调用清理：`POST /api/v1/agent/sessions/cleanup`
3. 查看应用日志中的 "Zombie session detected" 警告

### 取消不生效

1. 确认 Orchestrator 中是否检查 `is_cancelled()`
2. 检查 `_cancel_events` dict 是否正确设置
3. 验证 SSE 连接是否仍开启

### 并发限制误判

1. 检查 `MAX_PROJECT_SESSIONS_PER_USER` 配置
2. 确认已完成会话状态是否正确更新
3. 手动清理僵尸会话后再试

---

## 相关文档

- [Agent 系统](AGENT.md)
- [动态模型路由](DYNAMIC-MODEL-ROUTER.md)
- [架构文档](../architecture/ARCHITECTURE.md)
