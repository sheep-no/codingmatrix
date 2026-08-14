# CloudLearningHub 深扫（cloud_learning_hub.py，336 行）

> 第六十九轮推演 | 2026-08-09 | 定位：§5.1 学习闭环「跨项目知识共享」组件

## 1. 模块定位

CloudLearningHub 设计为跨项目修复模式共享中心：项目 A 学到修复模式后上传（upload_pattern），项目 B 遇同类错误时按错误类型+关键词检索（download_similar_patterns），应用后投票反馈（vote_pattern），质量用 success_votes/failure_votes/download_count 加权。`FixPattern`（feedback_learner 定义）是唯一数据契约，模块自身有全局单例工厂 `get_cloud_learning_hub`。

### 依赖链

| 方向 | 模块/位置 | 说明 |
|------|-----------|------|
| 依赖 | `feedback_learner.FixPattern`（:20） | 修复模式数据契约，含 error_embedding 字段 |
| 被消费 | **生产代码零消费方** | rg 全库仅自身文件 + 测试引用 |
| 被消费 | `tests/unit/test_learning_capabilities.py:162-232` | TestCloudLearningHub 3 用例 |

## 2. 深扫发现

### P2 项

- **CLH1 生产代码零消费方（死代码模块）**——rg 全库 `cloud_learning_hub|CloudLearningHub|get_cloud_learning_hub` 仅自身文件与 `tests/unit/test_learning_capabilities.py`，生成/修复/编排流程无一处接线。「跨项目知识共享」从未生效。§5.1 学习闭环四组件现状核实：strategy_learner（SE3 死代码）、user_preference_learner、fix_pattern_cache、cloud_learning_hub **全部零生产调用方**——学习闭环（FL1 死代码 + SE1 无数据）外，知识共享层整体也从未接线。修复方向：反馈闭环（FL1 接线）先落地，CLH 作为其上游复用侧才有意义——当前是「无上游输入、无下游消费」的孤岛。
- **CLH2 `cache_dir` 参数虚设（实测确认）**——`__init__` 收 `cache_dir`（:79/:85）并 `self.cache_dir.mkdir`（:87），但 `_load_local_cache`（:101）/`_save_local_cache`（:130）/`clear_cache`（:311-312）全部用**模块级常量 `CLOUD_CACHE_DIR`（`./data/cloud_learning`，:25-27）**而非 `self.cache_dir`。实测：传 `cache_dir=tmp_path`，upload_pattern 后 tmp_path 空、`data/cloud_learning/cloud_knowledge.json` 不存在 → `_save_local_cache` 抛 `[Errno 2]` 被 `except Exception` 静默吞掉（:134-135）。后果三重：① 多项目/多实例隔离的唯一途径失效（所有实例共享同一文件）；② `./data/cloud_learning` 相对 CWD（SE6/FL5 家族）——CWD 不同持久化漂移或静默失败；③ **测试用 `cache_dir=tmp_path`（test_learning_capabilities:171）但断言全走内存态（stats["total_patterns"]），文件持久化路径从未被任何用例验证**——测试通过恰恰掩盖实现缺陷（TR2 家族：测试固化错误预期）。
- **CLH3 质量门槛「1 票成功即高质量」（实测确认，初始假设已修正）**——`quality_score` 无投票返回 0.5（:48-49），但 `upload_pattern` **总是带 1 票上传**（:161-162 success=True→success_votes=1 → 0.7*1+0*0.3=**0.7 恰达阈值**；success=False→0.0）。实测上传 success=True 后 `download_similar_patterns` 即返回该模式——**任何一次成功上传 = 高质量**，`is_high_quality(0.7)` 门槛被单票直接越过，质量分无最小样本量概念；且失败票稀释需成功/失败 ≥ 7:3 才回落（1 成功 3 失败=0.175），实际几乎不降级。`download_count` 计入 0.3 权重（:52）但每次下载仅 +1，热度过低。修复方向：无投票模式不应可被检索，或要求最小票数（如 ≥3）才计入高质量池。
- **CLH4 上传哈希键粒度与「只增票不改内容」**——`_compute_pattern_hash`（:94-97）用 `error_type:error_message:fix_description` 的 md5 前 16 位。同 hash 重复上传时**只累加票数不更新 pattern 内容**（:166-172）——修复模式改进后重新上传，新 fix_example/file_types/error_pattern 被丢弃，只算一次成功/失败；error_message 含时间戳/随机细节时同错误产生不同 hash 的重复条目，票数分散。下载方 `FixPattern(**cloud_pattern.pattern)`（:206）要求 pattern dict 与 FixPattern 字段严格匹配（含 error_embedding 序列化往返）。

### P3 项

- **CLH5 `clear_cache` 用 unlink 删共享文件**——`:311-312` 删除模块级 `CLOUD_KNOWLEDGE_FILE`，多实例共享该文件时一实例 clear 全实例缓存清空（CLH2 共享路径放大）。
- **CLH6 单例参数忽略后续调用者**——`get_cloud_learning_hub`（:321-336）只取首个调用者 project_id/project_type/tech_stack，后续调用者参数被忽略（ERL5 单例家族）。
- **CLH7 读写无锁**——upload_pattern/vote_pattern/download_similar_patterns 都改 `_local_patterns` 并 `_save_local_cache`，多线程并发时 last-write-wins 丢投票（FL5/SE5 家族）。

## 3. 演化方向

### 3.1 孤立组件的接线路径

CLH 的语义前提是「反馈闭环真实生效」——当前 FL1（feedback_learner 死代码）+ SE1（strategy_evaluator 无数据）之下，CLH 无上游模式可共享。演化顺序：反馈闭环接线（FL1）→ FixPattern 实际产出 → CLH 从 fix_pattern_cache 同步上传 → error_recovery 失败时查询 CLH 复用。**在闭环接线前，CLH 修复无生产价值**（但 CLH2 的 cache_dir 修复成本低，可为接线做准备）。

### 3.2 质量分建模

CLH3 暴露「单票即高质量」——真实质量需要最小样本 + 时间衰减（新上传模式不应立刻等同历史高票模式）。LangGraph 反馈沉淀（§5.1）中质量分应改为：`贝叶斯成功率（加先验）+ 时间衰减 + 项目类型适配`，CLH 的 quality_score 是雏形但阈值/样本量缺失。

## 4. 主线关联

- **学习闭环主线**：CLH1（知识共享死代码）+ FL1（反馈学习死代码）+ SE3（策略学习死代码）+ SE1（无数据）——§5.1 学习闭环组件**全部未接线或无效**，本模块是闭环链路最后一块拼图确认
- **参数虚设家族**：CLH2（cache_dir）与 MEM2（max_entries）、SM9（session_id）同族——接口收参但实现忽略
- **测试固化家族**：CLH2 被 test_learning_capabilities 内存态断言掩盖（TR2 家族）
- **路径漂移家族**：CLH2 相对 CWD（SE6/FL5 家族）

## 5. 测试状态

`tests/unit/test_learning_capabilities.py:162-232` 3 用例（upload/download/vote），**全部断言内存 dict，无文件持久化路径验证**——CLH2 的落盘失败被测试通过掩盖；`test_upload_pattern` 未断言语义（total_patterns==1 不验证 cache_dir 落盘）。
