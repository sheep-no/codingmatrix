# UserPreferenceLearner 深扫（user_preference_learner.py，487 行）

> 第七十六轮推演 | 2026-08-09 | 定位：§5.1 学习闭环「用户偏好建模」组件（学习闭环四组件深扫完成）

## 1. 模块定位

UserPreferenceLearner 通过 diff 分析用户对生成代码的手动修改，推断偏好（代码风格/命名/注释密度/架构/技术栈），生成可注入生成 Prompt 的偏好文本（get_preference_prompt）。数据按 user_id 存 `data_dir/{user_id}.json`（**此模块正确使用实例 data_dir，与 CLH2/SL2 不同**）。多用户单例字典 `get_user_preference_learner`（:478）。

### 依赖链

| 方向 | 模块/位置 | 说明 |
|------|-----------|------|
| 被消费 | **生产代码零消费方** | rg 精确 import 仅自身文件；10 个泛匹配文件均为 "preference" 泛词无关 |
| 被消费 | `api/v1/ai_agent/orchestrate_endpoints.py:1301` | get_learning_stats 是 strategy_evaluator 的（非本模块） |

## 2. 深扫发现

### P2 项

- **UPL1 生产代码零消费方（死代码模块）——学习闭环四组件深扫全部完成**——`record_modification` 无人调用（用户修改从未被记录）、`get_preference_prompt` 无人注入生成 Prompt。§5.1 学习闭环四组件（strategy_learner/user_preference_learner/fix_pattern_cache/cloud_learning_hub）**全部零生产调用方确认完毕**。「用户偏好建模」是整个学习闭环中唯一面向「用户反馈」的组件（其他都是内部信号），它未接线意味着**生成结果永远按默认偏好输出，用户个性化能力从未生效**。修复方向：用户修改文件后（增量修改链路/前端编辑事件）→ record_modification；生成 prompt 拼接 get_preference_prompt。
- **UPL2 `get_preference_prompt` 默认值当用户偏好输出（实测确认）**——判断条件与字段默认值不匹配：`naming_convention != "mixed"`（:410）但默认是 **"snake_case"**（:38）→ 恒 True；`type_annotations` 默认 True（:49）→ :424-427 恒输出「使用类型注解」；`layer_separation != "moderate"`（:431）但默认 **"strict"**（:55）→ 恒输出「严格分层」。实测**空画像**（从未记录修改）的 get_preference_prompt 已输出「命名风格：使用下划线命名」「类型注解：使用类型注解」「架构风格：严格分层」——**全部是默认值冒充学习结果**。若接线到 prompt，用户还没表达任何偏好就已注入三条「伪偏好」，且高置信度提示（:447-452）会随 record_modification 快速累积。修复方向：默认值判断应比较「是否等于默认值」而非硬编码 sentinel。
- **UPL3 `_analyze_modification` 行集合 diff 丢失语义**（:214-219）——`set(modified_lines) - set(original_lines)` 用**行集合**而非顺序 diff：① 修改一行内容 → 该行同时进 added 和 removed；② 相同行多次出现（列表/重复代码）集合去重失真；③ 整体重写（格式变更）集合差异爆炸 → `_analyze_naming_changes`（:261-265）把格式差异当命名趋势。命名偏好从「用户新增的行」正则推断——实际可能是重构/格式化噪声。

### P3 项

- **UPL4 置信度只增不减无纠正路径**——`_update_confidence`（:372-376）`current + delta` 永不衰减，学到错误偏好后无负反馈修正（成功预测/失败预测计数 :83-84 有定义但无更新点——successful_predictions 死字段）。
- **UPL5 分析阈值与更新阈值不一致**——`_analyze_comment_changes` 用 diff>5（:280-283）判定 more_comments，`_update_preferences` 用 diff>10（:351）/diff<-10（:355）才更新——实测新增 7 条注释：分析出 more_comments 但不产生偏好更新，5-10 区间变更被记录却无学习效果；且注释计数正则 `(?:#|//|/\*|\*/)` 把字符串/注释内的 `#` 也计入。
- **UPL6 技术变更正则误判**——`_analyze_tech_changes`（:313-320）6 个硬编码框架词，出现在注释/字符串中的框架名被当技术选型变更；新增框架无 confidence 支撑（_update_preferences :370 直接写入 frameworks 无置信度）。
- **UPL7 单例字典无限增长 + 并发竞态**——`_user_preference_learners`（:474）每 user_id 一个实例无 LRU/上限，多用户长期运行内存增长；:482 `user_id not in dict` 检查在 lock 外 → 并发下重复创建（MCP1 家族）。
- **UPL8 `_modification_history` 只内存不持久化**（:109/:191-192）——重启丢失（MEM6 家族）。

## 3. 演化方向

### 3.1 用户偏好的接线路径

UPL 是学习闭环中唯一「用户侧」输入，接线语义：**前端/增量修改链路 → record_modification → 画像更新 → get_preference_prompt 注入下一轮生成**。前置依赖：用户实际会修改生成代码（增量修改链路 IncrementalModify 是载体）。UPL2 必须先修——否则接线即注入伪偏好污染生成。

### 3.2 与其他学习组件的关系

四组件定位差异：SL（生成策略）→ FPC（修复模式）→ CLH（跨项目共享）→ UPL（用户个性化）。UPL 的偏好与 LLM 生成链路（prompt 注入）最近，是**唯一能直接改进生成质量的反馈通道**——但优先级低于 §5.3 Evaluator-optimizer（SE1）的评估数据链。

## 4. 主线关联

- **学习闭环主线（四组件全灭，正式收口）**：SL1 + FPC1 + CLH1 + **UPL1** 全部零生产调用方——学习闭环四组件深扫完成，加上 SE1/FL1/DMR15，学习域九组件无一接线
- **默认值当真实值**：UPL2（默认值输出为偏好）与 DMR14（docstring 字段名不一致参数忽略）同属「默认态被误用」家族
- **diff 语义失真**：UPL3 行集合 diff（LD1 检测失真家族）
- **统计失真**：UPL4 置信度只增（FPC5 衰减失真反向例）

## 5. 测试状态

无 user_preference_learner 专项测试；test_learning_capabilities 覆盖 feedback_learner/learning_router/cloud_learning_hub/strategy_learner，**UserPreferenceLearner 无任何测试**——UPL2 默认值 bug 从未被暴露。
