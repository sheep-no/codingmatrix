# FixPatternCache 深扫（fix_pattern_cache.py，266 行）

> 第七十三轮推演 | 2026-08-09 | 定位：§5.1 学习闭环「成功模式复用」组件（学习闭环四组件最后一块拼图）

## 1. 模块定位

FixPatternCache 存储已验证的修复策略：add_pattern 记录修复成功，update_pattern_success 反馈成功率（成功 +0.1 / 失败 -0.2），失败 ≥3 且成功率 <0.3 标记为反模式并排除；find_pattern 精确签名匹配（error_type:subtype:project:file 的 md5），find_similar_patterns 用 BM25 模糊匹配跨项目迁移（v4.7.0 替代向量嵌入）。模块级单例 `fix_pattern_cache`（:266）。

### 依赖链

| 方向 | 模块/位置 | 说明 |
|------|-----------|------|
| 依赖 | `error_classifier.ErrorClassification`（:19） | 分类契约（error_type/subtype/description/suggested_fix_strategy/confidence） |
| 被消费 | **生产代码零消费方** | rg 全库 `fix_pattern_cache|FixPatternCache` 仅自身文件 |

## 2. 深扫发现

### P2 项

- **FPC1 生产代码零消费方（死代码模块）——学习闭环四组件全部确认**——模块级单例 `fix_pattern_cache`（:266）从未被导入；rg 全库仅自身文件。§5.1 学习闭环四组件（strategy_learner SE3 死代码 / user_preference_learner 零调用 / fix_pattern_cache FPC1 / cloud_learning_hub CLH1）**全部零生产调用方**，修复模式复用能力从未接线。修复方向：error_recovery 失败分支查询 fix_pattern_cache（find_pattern 精确命中 → 复用 fix_strategy）是唯一激活路径——它与 feedback_learner（FL1 死代码）是「修复-复用」闭环的两端，需同时接线。
- **FPC2 `find_similar_patterns` 无关错误类型误命中（实测确认）**——BM25 相似度把 `project_type`/`file_type` 作为**打分词**（:249 `doc_text` 拼接 error_type/subtype/project/file/fix_strategy），实测：缓存「import/ModuleNotFoundError」模式，查询「syntax/IndentationError」**完全无关错误类型**时，仅凭共享词 web/python（:241 query_text 也含 project/file）累计分数即 ≥0.8 阈值 → **返回 1 个不相关修复模式**。相似度语义错误：project/file 是上下文过滤条件而非错误特征信号；且 BM25 分数无归一化（:216-237 标准 BM25，分数随查询词数/文档集合规模漂移），0.8 阈值量纲不固定（单词查询 vs 多词查询阈值效果不同）。修复方向：相似度只在 error_type/error_subtype 维度计算，project/file 作硬性过滤。
- **FPC4 反模式判定需 4 次失败（实测确认）**——docstring「failed_count >= 3 且成功率 < 0.3」（:5/:47），但 success_rate 步长失败 -0.2（:153）从 1.0 起：实测 3 次失败后 rate=0.4（is_anti=False），**第 4 次才 rate=0.2 触发反模式**——阈值文档与增量步长不匹配，反模式追踪实际门槛比声明高 33%。

### P3 项

- **FPC5 30 天衰减作用于成功率本值**——:176-178 `success_rate *= 0.5` 且 `last_hit_time = current_time` 重置防重复衰减——**统计值（历史成功率）被当排序权重衰减**，长期未用模式即使 100% 成功也逐步归零；多次 30 天周期反复减半，历史数据失真。衰减应作用于排序分数而非成功率本身。
- **FPC6 中文分词无效 + BM25 每查询 O(N) tokenize**——`_tokenize`（:207-214）按空格 split 无中文分词器：中文连续错误描述（如「语法错误：缩进不正确」）整句成单 token，词级匹配失效（FL5/MEM5 中文关键词家族）；`_bm25_score` 每查询对全 patterns 重新 tokenize（:231/:250）无预索引，N=1000 时每次查询 O(N×doc_len)。
- **FPC7 异步保存线程风暴**——find_pattern/add/update 每操作 spawn 一个 daemon 线程（:92/:117/:144/:161），高频生成链下线程堆积、无节流/合并，多线程并发写同文件。
- **FPC8 cache_file 默认相对 CWD + 模块加载即建单例**——:54 `Path("fix_patterns_cache.json")`（SE6/FL5 家族）；:266 单例 import 时即创建（加载文件 + 潜在建目录）。

## 3. 演化方向

### 3.1 修复-复用闭环的接线路径

fix_pattern_cache 的语义前提是「修复模式被验证过」（update_pattern_success 有真实反馈）。当前 feedback_learner（FL1）与修复链均未接线，cache 无数据流入也无消费流出。演化顺序：① error_recovery 修复成功 → add_pattern；② 修复失败 → update_pattern_success（feedback_learner 的反模式/成功率语义与 FPC 重叠——两处 FixPattern 定义**同名异构**（feedback_learner.FixPattern 15 字段 vs fix_pattern_cache.FixPattern 14 字段），需统一）；③ 失败分支 → find_pattern 复用。FPC2 误命中在接线前必须修复（否则错误模式被复用）。

### 3.2 与 FeedbackLearner 的职责边界

feedback_learner.FixPattern（含 embedding/频率统计）vs fix_pattern_cache.FixPattern（含反模式/命中统计）**同一概念两个 dataclass**——学习闭环的「模式」契约分裂（CR1 双轨并存家族），演化目标：单一 FixPattern 定义，cache 为持久化实现，feedback_learner 为分析/学习实现。

## 4. 主线关联

- **学习闭环主线（四组件全灭确认）**：FPC1（复用死代码）+ SE1（评估无输入）+ DMR15（学习路由无写入）+ CLH1（共享无消费）+ FL1（反馈拦截误伤）——§5.1 学习闭环全链路无一处接线，本模块是四组件深扫的最后一块
- **相似度失真**：FPC2（BM25 无关误命中）与 MEM1（embedding 恒空）是「跨项目知识迁移」两个候选实现——BM25 实现有误命中、embedding 实现未接线，两个方案都不可用
- **契约分裂**：FPC 与 feedback_learner 双 FixPattern（CR1 家族）
- **中文失效**：FPC6 词级 split（FL5/MEM5 家族）

## 5. 测试状态

无 fix_pattern_cache 专项测试；全库仅 find_pattern 精确路径可被隐式覆盖，find_similar_patterns 的 BM25 误命中/中文分词无任何测试暴露。
