# spec_cache.py 深扫详档

> 版本：v1.62 | 日期：2026-08-09 | 文件：`app/agent/spec_cache.py`（605 行）｜方法 22 个（核心：lookup/save + 索引构建/持久化 + 4 个 async 包装）
> 结论：**P2 3 项（全实测）、P3 3 项**｜单元测试：2 个（tests/unit/test_spec_cache.py，仅覆盖同进程精确命中 + miss）

## 定位

需求 → 架构产物（specs/architecture/file_plan/dependency_graph）的**语义缓存**，spec_first 与传统两条生成链的复用层，架构 LLM 调用的主要成本削减手段（命中即跳过架构生成）。

## 跨模块引用链

| 方向 | 模块 | 位置 | 用途 |
|------|------|------|------|
| 被消费 | spec_first_generate.py | :46 `lookup(requirement)`（**不传 vector**）；:104-132 命中后复用 specs/architecture/file_plan + `DependencyGraph.from_dict(cached.dependency_graph)`；:775 `save(..., dependency_graph=...)` | 命中复用 + 写缓存 |
| 被消费 | traditional_generate.py | :31 `get_embedding(requirement)` → :34 `lookup(requirement, requirement_vector=...)`；:43 `_cache_review_gate`（命中后 reviewer 复核）；:60-62 复用架构 | 命中复用 |
| 被消费 | orchestrator_utils.py | :153 `save(...)`（无 dependency_graph，tech_stack 取 `architecture.get("tech_stack")`） | 反馈学习路径写缓存 |
| 被消费 | orchestrator.py / api/v1/ai_agent/helpers.py / orchestrate_endpoints.py | 单例构造与注入 | 生命周期 |
| 依赖 | embedding（get_embedding） | traditional:31 | requirement_vector 来源 |
| 依赖 | DependencyGraph.from_dict | spec_first:132 | dependency_graph 反序列化 |
| 测试 | tests/unit/test_spec_cache.py | 2 个用例（同进程 save→lookup 命中、miss） | **盲区：跨重启/持久化/模糊阈值全未覆盖** |

## 关键代码路径

`lookup`（:280）：精确 hash 命中（同进程内）→ tech_stack 索引预过滤 → embedding 余弦（带 vector 时）→ **Jaccard 关键词降级**（0.85 阈值）。`save`（:407）：内存 + `_save_entry`（独立 `<hash>.json` 完整数据）+ `_save_index`（index.json **显式清空大字段**）。

## Bug 清单

### P2

**SC1 [P2] 磁盘索引懒加载是死代码 → 进程重启缓存全丢（实测）**

- 位置：`_ensure_index_loaded`（:111）/`_async_load_index`（:122）设计为异步懒加载，但**全库无任何调用方**（rg 确认 async_save/async_lookup/async_clear_expired/async_clear_all/_ensure_index_loaded 零外部引用）
- 实测：
  ```
  sc.save(相同需求)            # 写内存 + 磁盘（index.json + <hash>.json）
  sc2 = SpecCache(新实例=模拟重启)
  sc2.lookup(相同需求)         # → None，sc2._cache 大小为 0
  ```
  磁盘数据完整存在，但 `_cache` 从不从 index.json 加载
- 影响：所有消费方（spec_first:46、traditional:34）走同步 lookup/save，同步路径不触发磁盘加载 → **缓存只存活于单进程内存**，每次部署/重启后全部 miss 并重新跑 LLM 架构生成——缓存的主要价值（成本削减）跨请求会话失效。与测试的 2 个用例同进程 save→lookup 命中通过不冲突（盲区）
- 修复方向：`lookup`/`save` 同步路径开头调用 `_load_index_sync`（幂等），或 API 层初始化后显式预加载

**SC2 [P2] dependency_graph 缓存不持久化 + async_save 缺参（实测）**

- 位置：`save` 存入内存（:431 `dependency_graph=dependency_graph or {}`），但 `_save_entry`（:538-551）与 `_save_index`（:171-187）的序列化 dict **均无 dependency_graph 键**；`async_save` 签名（:575-590）也无该参数
- 实测：`save(..., dependency_graph=dg)` 后读落盘 `<hash>.json` → 无 `dependency_graph` 键；读 index.json → 同样无
- 影响：spec_first_generate.py:129-132 命中缓存后 `DependencyGraph.from_dict(cached.dependency_graph)` → **恒 from_dict({}) → 空依赖图**。DG3 修复后（架构补缺从依赖图驱动）缓存命中路径的依赖图数据源是空的——补缺主线在缓存路径上失效
- 修复方向：`_save_entry`/`_save_index` 补 dependency_graph 键；`async_save` 补参数

**SC3 [P2] Jaccard 0.85 阈值恒不达 → spec_first 模糊命中形同虚设（实测）**

- 位置：`lookup` :385-402 Jaccard 降级；`compute_similarity` :241-260；`SIMILARITY_THRESHOLD=0.85`（:34）；spec_first:46 `lookup(requirement)` **不传 requirement_vector** → embedding 分支永不触发 → 恒走 Jaccard
- 实测：
  ```
  compute_similarity("开发一个用户管理系统，支持登录注册、用户 CRUD，用 Flask + MySQL",
                     "开发一个用户管理后台，包含登录注册和用户增删改查，使用 Flask 和 MySQL 数据库") → 0.5
  compute_similarity("写一个博客系统", "开发一个博客平台") → 0.25
  ```
  extract_keywords 是 ~40 个粗粒度词的列表，Jaccard 结构上到不了 0.85
- 影响：spec_first 的缓存命中只可能是**精确 hash 命中**（需求文本完全一致的重启场景；同一用户重复提交同需求文本）。「相似需求复用」承诺未兑现；traditional 链带 vector 可走 embedding（依赖 get_embedding 可用），spec_first 链连 embedding 机会都没有
- 修复方向：spec_first 侧接入 embedding（与 traditional 对齐）；或 Jaccard 阈值按关键词基数自适应（`0.85` 对集合 Jaccard 不可达）

### P3

**SC4 [P3] tech_keywords 双份拷贝（DRY）**

- `extract_keywords`（:212-224）与 `_extract_tech_keywords`（:265-277）维护**完全相同的技术关键词列表**，两份独立演化，改一处不同步即索引预过滤与关键词相似度口径分裂

**SC5 [P3] 双 save 点 tech_stack 来源不一致**

- spec_first_generate.py:774 取 `ctx.complexity["key_technologies"]`，orchestrator_utils.py:159 取 `architecture.get("tech_stack")`——同一缓存两张索引口径，同一需求可能因写入路径不同建出不同 tech_index 分组

**SC6 [P3] Jaccard 降级用 requirement_preview（前 200 字符截断）计算**

- `lookup` :392 `compute_similarity(requirement, full_entry.requirement_preview)`——长需求后半段关键词被截断，相似度系统性低估（SC3 之上再放大）

## 与既有主线闭环

- **成本链路恒零延伸**：LC1（成本金额恒零）之外，spec_cache 本是最直接的成本削减手段（命中省一次架构 LLM 调用），SC1（重启全丢）+ SC3（阈值不达）使**复用率实际趋近 0**——成本主线「省」的一侧也失效
- **依赖图主线**：DG3（完整性三方法）+ DG1（多边）之上，SC2 使**缓存命中路径的依赖图恒空**——架构补缺的图驱动在缓存路径断供
- **§5.6 支柱 4（检查点 Checkpointer）**：spec_cache 在概念上就是「阶段产物检查点」，但当前是 key-value 缓存而非显式状态流（无版本、无分支、无恢复点）；SC1/SC3 修复是把它从「近乎无效的缓存」拉回「可用的检查点」的第一步
- **测试盲区**：tests/unit/test_spec_cache.py 2 用例全在同进程内（掩盖 SC1），且只测精确命中（掩盖 SC3），无 dependency_graph 断言（掩盖 SC2）——三个 P2 全在测试未覆盖路径

## 状态校准（2026-09-22）

- **SC1 [P2] 已修复**：`lookup`/`save` 同步路径开头调用新增的 `_ensure_index_loaded_sync()`，首次访问时 `_load_index_sync()` + `_build_indices()` 从磁盘 `index.json` 恢复；进程重启后缓存不再全丢。异步 `_ensure_index_loaded` 与同步加载共用 `_index_loaded` 标志，避免重复加载。
- **SC2 [P2] 已修复**：`_save_entry` 的序列化 dict 补上 `"dependency_graph"`；`async_save` 补 `dependency_graph` 参数并透传。缓存命中路径的 `DependencyGraph.from_dict(cached.dependency_graph)` 不再恒为 `{}`。
- **SPFG8 [P2] 已修复**：`save`/`lookup` 新增可选 `complexity_level`（显式 opt-in，默认空保持既有调用方行为）。级别参与 `_compute_requirement_hash`，并在 `lookup` 的候选过滤中按级别隔离；`_save_index` 持久化 `complexity: {"level": ...}` 供重启后过滤。spec_first 链 lookup/save 均传 `complexity_level`，同一需求文本在不同复杂度下命中不同条目。`traditional`/`orchestrator_utils` 未传该参数，键与行为保持原样。
- **SC3 [P2] 关键词侧已修，embedding 侧未接**：`SIMILARITY_THRESHOLD=0.85` 改名为 `JACCARD_SIMILARITY_THRESHOLD=0.75`——0.85 对粗粒度小集合结构上不可达，0.75 意味着「关键词集合近乎相同」的可达且保守判据。另限定 `action_patterns` 捕获长度为 `\w{1,12}`，避免无限定 `\w+` 把整段中文连写吞成噪声词、进一步压低 Jaccard。spec_first 链仍未传 `requirement_vector`（embedding 分支在 spec_first 恒不触发），该项留待专项决策：接入 embedding 需同时评估缓存命中复用错误架构的风险（traditional 有 `_cache_review_gate` 兜底，spec_first 没有）。
- **SC4 [P3] 已修复**：新增模块级 `TECH_KEYWORDS` 元组，`extract_keywords` 与 `_extract_tech_keywords` 共用同一份，消除两份拷贝各自演化导致的口径分裂。
- **SC5 [P3] 已修复**：新增 `_normalize_tech_stack`，在 `save` 内合并 `architecture["tech_stack"]`、显式 `tech_stack`、`complexity["key_technologies"]` 三个来源并小写归一、保序去重。两个 save 调用点不再因写入路径不同建出不同 `tech_index` 分组；归一同时修好大写技术栈（如 `"Flask"`）永远匹配不到 `_extract_tech_keywords` 小写查询的问题。
- **SC6 [P3] 已修复**：`CacheEntry` 新增 `requirement` 全文字段，`_save_entry`/`_save_index` 均持久化；`lookup` 的 Jaccard 降级改为按 `full_entry.requirement or full_entry.requirement_preview` 比较（旧条目回退预览）。长需求尾部关键词不再因 200 字符截断而漏命中。

测试：`tests/unit/test_spec_cache.py` 扩展到 10 项（精确命中、miss、复杂度级别隔离/共存、dependency_graph 持久化、跨实例重启恢复、关键词表单一来源与阈值可达、技术栈三源合并归一、按全文比较命中、近同关键词集模糊命中）。
