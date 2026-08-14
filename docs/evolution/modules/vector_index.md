# VectorIndex 深扫（vector_index.py，181 行）

> 第七十四轮推演 | 2026-08-09 | 定位：历史项目语义检索层（FAISS + embedding）

## 1. 模块定位

VectorIndexManager 用 FAISS（IndexFlatIP + L2 归一化 = 余弦相似度）对历史项目元数据（requirement/domain/feature_list 拼接文本）建向量索引，支撑「历史需求 → 语义关联」检索（layer2_semantic 层）。构建（build_from_metadata）/增量（add_project）/检索（search）都经 `AiCodeUtil.get_embedding`。常量：EMBEDDING_DIM=768、SIMILARITY_THRESHOLD=0.35、MAX_RESULTS=10，路径 `./data/vector_index/`（相对 CWD）。

### 依赖链

| 方向 | 模块/位置 | 说明 |
|------|-----------|------|
| 依赖 | `utils/AiCodeUtil.py:94` get_embedding（:59/:98/:128） | embedding 入口（MEM3 不可用） |
| 依赖 | faiss（可选导入 :7-10） | **本环境未安装（实测确认）** |
| 被消费 | `orchestrator_requirements/layer2_semantic.py:17-22` | **唯一生产消费方**（语义检索 → 降级 keyword） |
| 被消费 | `project_metadata.py` | 元数据来源（get_all_projects） |
| 伪消费 | `spec_cache.py:479` | 仅字符串键 "vector_index_size"，非实际调用 |

## 2. 深扫发现

### P2 项

- **VI2 faiss 可选依赖导入模式缺陷（实测确认 faiss 未安装）**——模块级 `try: import faiss except ImportError: faiss=None`（:7-10），但 `load_or_create`（:36）/`_create_empty_index`（:53）/`_save_index`（:173）方法内**裸 `import faiss`**。实测本环境 faiss 未安装：`load_or_create` 的 :36 import 失败进 except → :48 `self._create_empty_index()`（在 try 块外）→ :53 裸 import 抛**未捕获 ImportError**。layer2_semantic 外层 try（:20/:45-47）兜住 → 每轮静默降级 keyword fallback；若无该外层则直接崩溃。**可选依赖声明为可选但使用路径全部裸 import 未保护**——依赖缺失时既不清脆降级也不报明确错误（TR2「不可用=未执行」家族）。
- **VI1 embedding 链四断升级（语义检索本环境不可用）**——build_from_metadata/add_project/search 全部 `await get_embedding(text)`，本环境 MEM3（空 key → `Illegal header value b'Bearer '`）使每次调用先失败——向量索引**构建与检索都不可用**；embedding 失效面扩至四层：MEM1（内存态不写入）+ MEM3（入口不可用）+ AGM2（DB 层不写入）+ **VI1（索引构建/检索失败）**。layer2_semantic 检索恒空 → 恒降级 keyword → MIN_VECTOR_RESULTS 门槛（history 关联）从未真实触发。
- **VI5 `SIMILARITY_THRESHOLD=0.35` 弱阈值 + 长文本拼接**——IndexFlatIP 余弦相似度 0.35 是弱相关门槛，未做过相关性校准；`_project_to_text`（:161-169）把 requirement/domain/30 条 feature 拼成一个长文本 embedding（:167 `[:30]` 截断 feature 数但文本可超 embedding 模型输入上限 → 截断丢语义）。

### P3 项

- **VI3 `build_from_metadata` 假设 JSON 顶层为 list**——:67-68 `projects = json.load(f)` 直接 `for project in projects`——若元数据文件是 dict 结构，遍历的是 keys（str）→ :72 `.get` AttributeError → except 吞 → count=0 静默「构建 0 条」。且 METADATA_PATH 与 project_metadata.py 的实际输出路径/格式是否一致未验证（消费方 project_metadata 用 get_all_projects 兜底取 feature_list 也说明格式脆弱）。
- **VI6 search/add_project 并发无锁**——多协程并发 add/search 写 faiss index 无锁（MCP1/CS1 家族）；add_project 加载态与 search 读取态无一致性保护。
- **VI7 `EMBEDDING_DIM=768` 硬编码与模型维度未验证**——bce-embedding-base_v1 实际维度未确认（若 ≠768，faiss add 报维度不匹配被 except 吞 → 构建全失败静默）；维度应由模型能力表驱动而非硬编码。

## 3. 演化方向

### 3.1 语义检索的激活前提

vector_index 的可用性依赖两个前置：① faiss 安装（VI2 修复可选依赖保护——**依赖缺失应显式报「不可用」而非静默降级**，与 MEM3 的「embedding 不可用」可辨识状态同语义）；② embedding 入口可用（MEM3 修复）。当前 layer2_semantic 的 try/except 把「faiss 缺失/embedding 失败/索引损坏」混为一类降级 keyword——**静默降级是四端失真（检测端）的另一例**：上层以为「没有语义相似项目」，实际是「检索能力不可用」。演化：能力探测 + 显式不可用状态，keyword fallback 只在「确实无相似」时触发。

### 3.2 与 memory embedding 的收敛

vector_index（历史项目语义）+ memory.py（会话语义）+ DB MemoryEntry（长期知识语义）共用 AiCodeUtil.get_embedding——**三个语义检索层共享同一入口**，MEM3 修复后全部激活；维度/阈值/归一化应收敛为统一 embedding 配置（§5.4 语义存储雏形）。

## 4. 主线关联

- **embedding 链四断**：MEM1 + MEM3 + AGM2 + **VI1**——语义能力在全部四层（内存/DB/入口/向量索引）不可用，是本项目最大跨层失效面
- **「存在≠正确」检测端**：VI2/layer2_semantic 静默降级 keyword——「无语义相似」vs「语义能力不可用」被混同
- **可选依赖**：VI2 裸 import 与 TR2/UT5「不可用=未执行」家族
- **路径漂移**：VECTOR_INDEX_DIR 相对 CWD（SE6/FL5 家族）

## 5. 测试状态

无 vector_index 专项测试；layer2_semantic 的降级路径（keyword fallback）可能在编排层测试中被覆盖，但「语义路径实际不可用」从未被测试暴露——测试固化「降级成功」为预期（TR2 家族）。
