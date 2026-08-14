# memory.py 深扫详档

> 版本：v1.68 | 日期：2026-08-09 | 文件：`app/agent/memory.py`（580 行，BaseMemory 抽象 + ConversationMemory/KnowledgeMemory/ReflectionMemory/AgentMemory 四实现）
> 结论：**P2 4 项（MEM1 静态、MEM2/MEM3 实测、MEM4 静态）、P3 3 项**｜单元测试：零

## 定位

Agent 记忆系统：三类记忆（对话/知识/反思）+ `AgentMemory` 整合入口。docstring 宣称「支持语义搜索（基于 embedding 余弦相似度）」（:5）。消费方：react_agent.py:97（`self.memory = AgentMemory()`）、orchestrator.py、orchestrator_utils.py。

## 跨模块引用链

| 方向 | 模块 | 位置 | 用途 |
|------|------|------|------|
| 被消费 | react_agent.py | :97 实例化；:181 `self.memory.reflection.get_insights()` | ReActAgent 反思入口 |
| 被消费 | orchestrator.py / orchestrator_utils.py | memory 引用 | 编排层记忆 |
| 依赖 | app.utils.AiCodeUtil.get_embedding | :18 + memory.py:200/:301 | 语义搜索 embedding |
| 关联 | session_manager.py SM2/SM3 | fs.content_embedding 恒 None | **同一 embedding 依赖链** |
| 测试 | — | — | **零测试** |

## 关键代码路径

`ConversationMemory.add`（:101）：append → len>COMPRESSION_THRESHOLD(15) 触发 `_compress_old_entries` → len>max_entries(100) 截断。`search_async`（:197/:298）：get_embedding → 对 `entry.embedding` 非 None 的条目做余弦相似度过滤。`AgentMemory.get_context_for_prompt`（:469）：反思 → 知识 → 对话历史拼接。

## Bug 清单

### P2

**MEM1 [P2] embedding 恒 None → 语义搜索 search_async 恒返回空（静态确认，embedding 从未写入）**

- 位置：`MemoryEntry.embedding` 默认 None（:49）；全模块 **rg `.embedding =` 零赋值点**——add_user_message/add_assistant_message/add_tool_result/add_knowledge/add_reflection 全部路径都不计算 embedding
- 逻辑：`search_async`（ConversationMemory :209-216 / KnowledgeMemory :310-316）`if entry.embedding:` 恒 False → 正常路径**恒返回 []**；字符串搜索 fallback（:203/:304）只在 get_embedding 抛异常时触发——**语义搜索声称的能力从未生效，且正常路径比 fallback 更差（恒空）**
- 与本环境实测叠加：get_embedding 本环境抛异常（MEM3）→ search_async 恒走 fallback 字符串搜索，「碰巧」返回结果，**掩盖了 MEM1**；生产环境 get_embedding 可用时反而恒空
- 同款模式：session_manager SM2/SM3（fs.content_embedding 恒 None）、FL7（feedback_learner 逐条串行 embedding）——**embedding 声明与写入脱节是模块间重复模式**，§5.6 支柱 1 产物协议应把 embedding 归入记忆/会话产物的 schema 写入路径

**MEM2 [P2] 压缩阈值 15 远小于 max_entries=100 → 对话 16 条即摘要化、细节丢失；`_is_compressed` 死字段 + 摘要嵌套退化（实测）**

- 位置：`COMPRESSION_THRESHOLD = 15` / `COMPRESSED_ENTRIES = 5`（:90-92）；add :110 `len(self._entries) > self.COMPRESSION_THRESHOLD`；压缩 :118-157
- 实测：`ConversationMemory(max_entries=100)` 加 17 条 → `_entries` 被压成 `[summary, user×6]`（7 条）——**max_entries=100 实际永远到不了，参数虚设**；用户消息 16 条后全部细节被摘要化
- 摘要嵌套：再压 16 条后摘要内容变为 `[对话摘要] 共 11 条历史记录...主要话题: AI, 20, 条用户消息`——**摘要自身内容混入旧摘要，嵌套退化 + 关键词噪声**
- `_is_compressed`（:98 置位/:156 置位/:221 clear 复位）**全文件零读取**——死字段
- 设计冲突：压缩是主动的信息丢弃（阈值 15 太激进），截断是兜底（max_entries）——两者应统一为「接近上限或超 token 预算才压缩」

**MEM3 [P2] get_embedding 无 key 保护 → agent 环境 embedding 能力完全不可用，每次 search_async 先失败一次（实测）**

- 位置：AiCodeUtil.py:126 `"Authorization": f"Bearer {settings.SILICONFLOW_API_KEY}"`——key 为空时生成 `"Bearer "` 非法 header，httpx 抛 `Illegal header value b'Bearer '`
- 实测：`search_async` → `获取 query embedding 失败: Illegal header value b'Bearer '` → 回退字符串搜索——**每次语义搜索先做一次必失败的 API 调用**（网络/异常开销）+ 警告日志
- 影响：本环境 embedding 唯一入口不可用，memory/session_manager/cloud_learning_hub 等所有依赖方语义能力全失效（与 MEM1 叠加时「恒空」被「恒回退」掩盖）；修复方向：key 缺失时提前短路并记录「embedding 不可用」可辨识状态（UT5 家族「不可用=未执行」语义）

**MEM4 [P2] `get_with_context` 参数名 max_tokens 实际按字符数截断（英文浪费上下文窗口）**

- 位置：:163-181 `if total_chars + entry_len > max_tokens`——`len(entry_text)` 字符数与 max_tokens 比较；调用处 :486 `max_tokens // 2`
- 影响：英文 4 字符≈1 token → 实际注入的 token 远小于预算（上下文利用率低）；中文 1 字符≈1 token 尚可——**token 与字符语义错位**（OP6/OU1 成本估算家族同款「按字符当 token」）

### P3

**MEM5 [P3] 压缩摘要关键词提取对中文无效 + 停用词噪声（实测）**

- `:136-137` `content.split()[:50]` 中文无空格整句一个 token——「主要话题」对中文需求恒空；英文停用词（was/the/用户消息中的"AI"等）污染摘要（实测摘要含「AI, 20, 条用户消息」噪声词）

**MEM6 [P3] 纯内存无持久化 + 秒级 session_id 冲突**

- AgentMemory 全部记忆进程结束即丢（无序列化出口，仅 to_dict 提供手工导出）；`session_id` 基于 `int(time.time())`（:426）与 `clear_session` 的 `int(time.time())`（:516）同秒冲突（SM9 家族）

**MEM7 [P3] KnowledgeMemory add 同 key 覆盖旧知识（importance 降级）**

- `_entries[key] = entry`（:252）key=content[:100]（:249）：同内容重复添加覆盖旧条目，包括 importance 0.9 的旧知识被默认 0.5 新覆盖；无版本/合并策略

## 与既有主线闭环

- **embedding 依赖链**：MEM1（不写入）+ MEM3（入口不可用）双断——memory/session_manager（SM2/SM3）共用 AiCodeUtil.get_embedding，该链上所有语义能力从未真实生效；「存在≠正确」在语义检索层
- **SB1（specialist 无 memory）关联**：react_agent :97 实例化 AgentMemory，但 specialist_base 生成链（SB1 已证 full 模式无 memory 传递）——记忆在编排层存在、在生成层未接线
- **§5.6 支柱 4（Store/Checkpointer）映射**：MEM6 无持久化 + MEM2 无主动压缩策略——LangGraph Store 需剪枝策略（§5.4 已标注），memory 的「压缩 vs 截断」正是 Store 剪枝的雏形，当前阈值颠倒
