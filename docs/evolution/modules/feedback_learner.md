# feedback_learner.py 深扫详档

> 版本：v1.65 | 日期：2026-08-09 | 文件：`app/agent/feedback_learner.py`（428 行）｜方法 17 个
> 结论：**P2 3 项（FL1 实测、FL2/FL3 静态）、P3 4 项**｜单元测试：零

## 定位

修复经验的**反馈学习器**：记录 RefinementLoop/修复循环的修复模式，形成 FixPattern 库，供生成时注入预防提示 + 反模式拦截。是 §5.3「基于经验反馈改进生成」的落点。

## 跨模块引用链

| 方向 | 模块 | 位置 | 用途 |
|------|------|------|------|
| 被消费 | orchestrator_files.py | :332 `get_prevention_prompt(...)` 注入 prevention_hints；:474 `record_fix(...)` | 预防提示 + 修复记录 |
| 被消费 | orchestrator_utils.py | :16 `_is_anti_pattern(requirement)` 用 `pattern.error_pattern` 正则搜需求文本 → True 拦截整个生成；:26 `_cache_review_gate` 复用 | **反模式需求拦截** |
| 被消费 | traditional_generate.py | `get_prevention_prompt` + `compute_error_embeddings` + `record_fix` | 传统链 |
| 被消费 | cloud_learning_hub.py | `from app.agent.feedback_learner import FixPattern` | 云端学习 |
| 被消费 | api/v1/ai_agent/helpers.py / orchestrate_endpoints.py | 单例 `get_feedback_learner()` | 生命周期 |
| 死代码 | 同步 `_find_relevant_patterns`（:340）、`async_record_fix`/`async_save_patterns`（:422/:426） | 无消费方（rg 确认） | 与 async 版重复/未用 |
| 测试 | — | — | **零测试** |

## 关键代码路径

`record_fix`（:84）→ FixPattern 库 + `_save_patterns`（:393 写 `./data/learning_data/fix_patterns.json`）。`get_prevention_prompt`（:167）→ embedding 或 frequency 匹配 → 前 5 条注入 prompt。`_is_anti_pattern`（orchestrator_utils:16）→ `re.search(pattern.error_pattern, requirement)` → 命中即整单拒绝。

## Bug 清单

### P2

**FL1 [P2] `_build_error_regex` 生成 OR 关键词正则 → 反模式拦截整单误伤（实测）**

- 位置：`_build_error_regex`（:278-282）`keywords = re.findall(r'[\u4e00-\u9fff]+|[a-zA-Z_]+', error_msg); return "|".join(keywords[:5])`——英文错误消息被拆成**单个单词**做 OR；消费方 orchestrator_utils:21 `re.search(pattern.error_pattern, requirement, re.IGNORECASE)` 用它对**需求文本**做子串正则
- 实测：
  ```
  反模式 FixPattern(error_message="module 'flask' has no attribute 'Foo'", failed_count=4, success_rate=0.0)
  error_pattern = 'module|flask|has|no|attribute'
  _is_anti_pattern("用 flask 写一个用户系统") → True   # 命中单词 'flask'
  _is_anti_pattern("开发一个电商网站") → False
  ```
- 影响：一个曾因「flask 属性 Foo」失败 3 次的反模式，会让所有含 "flask" 一词的新需求被**整单拒绝**（orchestrator_utils:22-23 拦截 → 生成不启动）。而 error_pattern 本应匹配「错误信息」，却用于匹配「需求文本」，语义错位 + OR 拆词放大误伤面
- 修复方向：error_pattern 应对整条错误消息归一化后精确匹配（如 `re.escape` + 可选行号通配），且反模式拦截应只作用于「同 error_type 且错误消息相似」的验证反馈，不应横跨到需求文本的单词级匹配

**FL2 [P2] 反模式拦截机制本身二态失真（静态确认）**

- 位置：orchestrator_utils:16 `_is_anti_pattern`；判定标准 FixPattern.is_anti_pattern（:49 `failed_count >= 3 and success_rate < 0.3`）
- 现象：低频错误（总尝试 <3）永不触发拦截；冷启动空库恒 False（无防护）；一旦达到反模式阈值 + FL1 假阳性 → 整单误杀。**「要么不触发、要么误伤」，缺少中间档（如：反模式只注入强化预防提示而非拒绝生成）**
- 影响：防护语义没有缓冲，配合 FL1 使反模式机制实际弊大于利

**FL3 [P2] `_find_relevant_patterns` 同步版死代码 + 与 async 版逻辑分叉（静态确认）**

- 位置：同步版（:340）无任何消费方（rg 仅 def 行）；async 版（:208）被 get_prevention_prompt 使用；两版逻辑**有差异**——async 版 :220 多 `not pattern.is_anti_pattern()` 过滤、success_rate>0.3，同步版 :359 只有 success_rate>0.3 无 anti 过滤
- 影响：同一「模式匹配」语义两份实现 + 一份死代码；同步版若被误接线会漏掉反模式过滤

### P3

**FL4 [P3] async_record_fix / async_save_patterns 死代码**

- :422/:426 异步包装无消费方（rg 零结果），与 spec_cache SC1 的 async 包装同族死代码

**FL5 [P3] learning_dir 相对路径 + session_records 不持久化**

- :25 `LEARNING_DIR = Path("./data/learning_data")` 依赖工作目录（同 spec_cache SC1 / strategy_evaluator SE6）；:152-163 `_session_records` 只存内存，重启丢失

**FL6 [P3] `_is_anti_pattern` 跨模块访问私有 `_fix_patterns`**

- orchestrator_utils:19 直接 `self.feedback_learner._fix_patterns.values()`——破坏封装，FeedbackLearner 无公开查询 API

**FL7 [P3] `compute_error_embeddings` 逐条串行调用 embedding**

- :332 循环内 `await get_embedding(...)` N 次串行网络往返，无批量/并发；错误列表大时阻塞生成链

## 与既有主线闭环

- **§5.3 Evaluator-optimizer 延伸**：FeedbackLearner 是「经验反馈」的存储侧，与 strategy_evaluator（SE1 无数据）成对——一个记录修复经验但拦截逻辑误伤（FL1/FL2），一个评估策略但无输入（SE1），反馈闭环两端都有缺陷
- **「存在≠正确」主线**：FL1 是拦截侧过严的又一实例（CR2 审查假阳性之外），配合 UT5 执行空转——**拦截侧多处过严、执行侧过松的双向失真持续累积**
- **§5.6 支柱 4（检查点）**：fix_patterns.json 是「经验检查点」，路径相对化（FL5）与 spec_cache/strategy_evaluator 同属持久化路径规范问题
