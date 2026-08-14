# Agent Memory 深扫（models/agent_memory.py 144 行 + services/agent_memory_service.py 367 行）

> 第七十一轮推演 | 2026-08-09 | 定位：§5.1 记忆闭环的 DB 持久化层（模型 + service）

## 1. 模块定位

`models/agent_memory.py` 定义 6 张 SQLAlchemy 表：AgentSession（会话）、MemoryEntry（记忆条目，含 embedding JSON 列）、AgentReflection（反思）、KnowledgeEntry（知识）、ToolExecutionLog（工具日志）、ModelUsageStats（模型统计）。`services/agent_memory_service.py` 提供全部 CRUD。这是 agent 记忆的 **DB 持久化层**——与 `app/agent/memory.py`（运行时内存态，MEM1-MEM7）构成两套记忆体系。

### 依赖链

| 方向 | 模块/位置 | 说明 |
|------|-----------|------|
| 依赖 | `models/base.py`（Base） | SQLAlchemy 基类 |
| 被消费 | `services/agent_memory_service.py` | 唯一 service 层 |
| 被消费 | `api/v1/ai_agent/knowledge_endpoints.py:25/:58/:88` | AgentMemoryService 唯一生产实例化点，仅用 add_knowledge/search_knowledge/get_user_knowledge |
| 被消费 | `api/v1/AiProjectCode.py:25/:47/:144` | **直接 ORM** 操作 AgentSession/KnowledgeEntry，绕过 service |
| 运行时 | `app/agent/memory.py`（MEM1-MEM7） | **并行内存态记忆，不落 DB** |

## 2. 深扫发现

### P2 项

- **AGM1 两套记忆体系完全割裂（记忆闭环断裂根因）**——运行时链（react_agent/memory.py/session_manager）使用内存态 `app/agent/memory.py`，**从不调用 DB 层**；DB 层 `AgentSession`/`MemoryEntry`/`AgentReflection`/`ToolExecutionLog`/`ModelUsageStats` 的 service 方法在**生产代码零调用方**（AgentMemoryService 只被 knowledge_endpoints 实例化，且只用知识三方法；AiProjectCode 直接 ORM 走另一条路）。后果：① agent 运行时的对话记忆/反思/工具日志**从未落库**——DB 层五张表实际只记录「API 端点级」零散数据；② MEM6「纯内存无持久化 + 秒级 session_id 冲突」的根因即此割裂——持久化能力存在但未与运行时接线；③ `AgentReflection` 反思表、`ToolExecutionLog` 工具日志表全库无生产写入方（零数据）。修复方向：运行时记忆写入 DB 的桥接层（session_id 对齐 UUID 36 字符）——这是 §5.1 记忆闭环落地的唯一路径。
- **AGM2 embedding 链三断（语义搜索三层全灭）**——DB 层 `MemoryEntry.embedding`（models:49 JSON 列）由 service `add_memory_entry`（:88-107）写入，但 **service 签名无 embedding 参数 → 恒 None**；`KnowledgeEntry` 甚至无 embedding 字段；DB 层 `search_knowledge`（:199-221）只能 ilike 字面匹配。与 MEM1（内存态 `MemoryEntry.embedding` 恒 None）+ MEM3（AiCodeUtil.get_embedding 入口不可用）叠加 → **「语义搜索」在运行时态、DB 持久态、embedding 入口三层全部从未生效**。embedding 依赖链从双断升级为三断。
- **AGM3 同一能力三实现并存**——会话创建：service `create_session`（:30-45）+ AiProjectCode `create_agent_session`（:42-60 直接 ORM，context_summary 截断 500 字符、session_type 硬编码 "code_generation"）+ 测试路径；知识写入：service `add_knowledge`（:176-197）+ AiProjectCode `accumulate_knowledge`（:144-，直接 ORM，**无 knowledge_key、无 dedupe、无 importance 语义**——每轮生成都写「项目使用了 X 技术栈」重复堆积）。同一 ORM 模型被多层各自实现 CRUD，无统一仓储层（CR1/OF1 双轨并存家族）。
- **AGM4 `AgentSession.context_summary` 死字段 + 记忆上下文无压缩**——models:23 定义但全库无写入点（grep 确认）；`get_memory_context`（:126-139）按 `max_entries=50` **条数**截断、无 token 预算、无摘要压缩，且 reversed 后按 created_at desc 取最新 50 条**包含 TOOL 类型条目**（:136 role=TOOL）混入上下文（CS4/memory MEM4 字符当 token + 压缩缺失家族）。

### P3 项

- **AGM5 `update_model_stats` avg 语义失真**——:301-305 滚动平均的分母 `total_requests = success_count + failure_count`，失败请求 execution_time 可能为 0 会拉低 avg；首次创建成功但 failure_count=0 时 avg 只含成功样本，后续失败插入使 avg 突变；且 `ModelUsageStats` **无成本（USD）字段**——orchestrator_progress OP1「成本金额恒零」在 schema 侧同样缺支撑。
- **AGM6 `get_memory_context` 最新 N 条截断**——按条数截取而非 token/语义（CS4/MEM4 家族，P3 定位因 service 无生产消费方降低影响面）。
- **AGM7 `log_tool_execution` tool_result 硬编码截断 10000 字符**（:263）——静默截断无标记（TR2 家族）。
- **AGM8 并发读改写竞态**——`update_model_stats`（:283-324）select→modify→commit 无行锁、`increment_knowledge_usage`（:223-229）读改写（CS1/MCP1 家族）。
- **AGM9 `KnowledgeEntry.knowledge_key` 无 unique 约束**（models:86 index 非 unique）——DB 层允许同 key 重复，与 MEM7（内存态同 key 覆盖 importance 降级）语义不一致——两套知识存储对「同 key」的行为互相矛盾。

## 3. 演化方向

### 3.1 记忆闭环的接线路径

AGM1 是核心：DB 层是记忆持久化的**正确落点**（schema 完备：session/memory/reflection/knowledge/tool_log/model_stats 六表覆盖全记忆域），但运行时从未写入。演化顺序：① 桥接层——runtime memory.py 的 add/search/compress 落到 DB 层（AGM1）；② 同源 embedding——AGM2 让 embedding 在三层统一（先修 MEM3 入口，再让 add 写 embedding）；③ 统一仓储——消除 AGM3 三实现，AiProjectCode/端点/运行时统一走 AgentMemoryService。**在 AGM1 接线前，DB 层五表是空壳**——这解释了 MEM6 纯内存无持久化的根因不是「没有持久化实现」而是「持久化层未接线」。

### 3.2 记忆域与 memory.py 的职责边界

`app/agent/memory.py`（运行时窗口记忆，快存取）vs `models/agent_memory.py`（长期知识，慢存取）。演化目标：运行时窗口 → 会话内，长期知识 → DB；`AgentSession.context_summary`（AGM4）作为窗口→长期的下沉点。两套 KnowledgeEntry 需合并语义（AGM9）。

## 4. 主线关联

- **embedding 链三断**：MEM1（运行时态不写入）+ MEM3（入口不可用）+ **AGM2（DB 层不写入）**——「语义搜索」三层全灭，是本项目最大的跨层失效面之一
- **记忆闭环断裂**：AGM1 使 DB 持久化与运行时记忆互不相通——§5.1 记忆闭环从未闭合
- **双轨并存**：AGM3 三实现 + AGM9 两套 Knowledge 语义矛盾（CR1 家族）
- **压缩/截断**：AGM4 context_summary 死字段 + 条数截断（CS4/MEM4 家族）
- **成本**：AGM5 无成本字段（OP1 家族 schema 侧）

## 5. 测试状态

无 agent_memory 专项测试；knowledge_endpoints 端点测试若存在也只覆盖知识三方法；service 的 session/memory/reflection/tool_log/model_stats 方法全部无生产消费方也无测试覆盖。
