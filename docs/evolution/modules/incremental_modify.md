# IncrementalModifyMixin 演化深扫文档

> 版本：v1.0 | 扫描日期：2026-08-05 | 状态：已完成
> 归属：Agent 大系统 / 编排层·增量修改（补扫，不在原 13 模块索引内）
> 路径：`app/agent/orchestrator_generation/incremental_modify.py`（1028 行）
> 索引：[TASKS.md](../TASKS.md)｜关联：[mixin.md 组装](traditional_generate.md)｜[dynamic_model_router.md](dynamic_model_router.md)

## 1. 模块作用与功能

- **核心职责**：增量修改主流程（`generate_incremental`）——加载持久化依赖图（`.dep_graph.json`）→ 架构师分析变更计划 → 按 add/modify/delete 分派 → 动态拓扑并行生成 → 更新依赖图。P3 快速模式（跳过复杂度/规范/交叉验证）
- **主要类/函数**：
  - `generate_incremental`（:29-282）——主流程，依赖图缺失/计划为空时回退 `generate_with_spec_first`
  - `_analyze_changes_with_architect`（:307-382）——架构师变更计划（含 24h 缓存）
  - `_generate_with_dynamic_topology_incremental`（:429-581）——按依赖图分层并行生成 + P5 降级模型重试
  - `_retry_with_fallback_model`（:673-775）——硬编码降级链重试
  - `_generate_file_with_model`（:904-1016）——单文件生成（含内容提取/恢复/重试）
  - `_update_dependency_graph_incremental`（:777-804）/`_extract_imports_from_content`（:806-853）——依赖图增量更新
  - `_content_already_satisfies`（:862-902）——P7 内容已满足启发式跳过
  - `_get_model_semaphore`（:1018-1028）——按模型信号量
- **对外接口**：`generate_incremental(requirement, callback)`——入口（由 mixin 组装层暴露）

## 2. 依赖与被依赖

- **导入依赖**：DependencyGraph（load/save）、LanguageDetector、LanguageAdapterRegistry、LayeredModelRouter、get_global_llm_semaphore、Architect/FrontendEngineer/BackendEngineer、SpecFirstGenerator、`write_file_atomic`/`extract_engineer_content`/`is_valid_code_content`
- **生产使用方**：`mixin.py:23` 组装进 `GenerationMixin`（增量修改入口）；与 `incremental_generate.py`（IncrementalGenerateMixin，会话恢复模式）是**两套增量实现并存**
- **测试覆盖**：无活跃测试（与 spec_first_generate/cross_validator 同为零覆盖）

## 3. 已探明 Bug

### IM1 [P1] 简单变更与降级重试硬编码模型名——绕开动态模型路由

- **Bug 代码**：

```python
# incremental_modify.py:482-483 - 简单变更强制轻量模型
engineer = self._select_engineer(file_path, force_model="THUDM/GLM-4-9B-0414")
model_name = "THUDM/GLM-4-9B-0414"
# :688-692 - 降级链硬编码
fallback_models = [
    "THUDM/GLM-4-9B-0414",
    "deepseek-ai/DeepSeek-R1-0528-Qwen3-8B",
    "Qwen/Qwen3-8B"
]
```

- **根因**：增量修改路径绕过 dynamic_model_router 的模型分配，硬编码 SiliconFlow 专属模型名
- **影响**：①非 SiliconFlow provider（dashscope/zhipu/deepseek）下这些模型名不存在 → 简单变更与降级重试**必然调用失败**；②与 DMR 的模型分配/降级体系不一致（双重降级链：本模块硬编码 vs dynamic_model_router 配置链）
- **触发条件**：增量修改且命中简单变更，或某文件首轮生成失败走降级重试

### IM2 [P2] `_content_already_satisfies` 关键词启发式误跳过

- **Bug 代码**：

```python
# incremental_modify.py:878-891 - reason 含 "add"/"添加" 且内容含关键词即判已满足
if "添加" in reason or "add" in reason_lower:
    keywords = []
    if "/health" in reason_lower or "健康检查" in reason_lower: keywords.append("/health")
    ...
    for keyword in keywords:
        if keyword in content_lower:
            return True   # ← 内容已有 /health 字符串即跳过，不管逻辑是否真实实现
```

- **影响**：如需求「添加 /health 端点并返回数据库状态」，原文件已有 `/health` 路由字符串但业务逻辑缺失 → **被误判已满足而跳过修改**——与 SPFG1 断点续传启发式同类（文件/内容存在≠实现正确）
- **验证方式**：构造 `original_content` 含 `/health` 字符串、reason 含「添加 /health」→ 返回 True

### IM3 [P2] 增量模式 LLM 生成无单文件语法/有效性校验

- **Bug 代码**：`_generate_with_dynamic_topology_incremental` :532/:552 直接把生成结果 `result[:8000]` 存入 `generated_contents`——与 spec_first_generate 的 `_validate_content_syntax` 不同，**增量路径无 is_valid_code_content 校验**（仅 `_generate_file_with_model` 内 :990 对空内容校验，语法/占位符不校验）
- **影响**：生成坏内容（含占位符/语法错）直接写盘并被依赖图引用——下游文件基于坏内容继续生成

### IM4 [P2] `_extract_imports_from_content` 仅解析 Python——多语言依赖图增量更新失效

- **Bug 代码**：

```python
# incremental_modify.py:824 - 只识别 Python import 语句
if line.startswith('import ') or line.startswith('from '):
```

- **影响**：JS/TS（`import x from 'y'`、`require(...)`）、Go（`import "fmt"`）等非 Python 项目增量修改后依赖关系不更新——依赖图与实际 import 脱节，后续增量生成顺序错误

### IM5 [P2] `_retry_with_fallback_model` 重试 engineer 无信号量/成本追踪/供应商

- **Bug 代码**：

```python
# incremental_modify.py:710-715 - 新构造工程师，未传 semaphore/cost_tracker/provider_id
engineer = FrontendEngineer("前端工程师", model_name, task_type="generate",
                            api_key_token=self.api_key_token, cancel_event=self.cancel_event)
```

- **影响**：降级重试不受全局信号量约束（并发失控）、成本不计入（成本恒 0 又一贡献点）、provider 不传

### IM6 [P3] 闭包内局部 `model_semaphores`/`MAX_CONCURRENT_PER_MODEL` 死代码

- **Bug 代码**：:466-467 闭包外定义 `model_semaphores = {}` 与 `MAX_CONCURRENT_PER_MODEL = 2`，闭包内实际用 `self._get_model_semaphore`（:490）——**局部变量从未使用**（实例方法 :1023 有另一份 MAX_CONCURRENT_PER_MODEL=2）
- **影响**：死代码 + 并发上限双处定义（:467/:1023），后续调整一处不同步

### IM7 [P3] `generate_single_file` 的 `tracker` 参数恒 None（死参数）

- **Bug 代码**：:469 默认 `tracker=None`，:519 调用不传 → `heartbeat_tracker` 恒 None——死参数（心跳追踪未接线）

### IM8 [P3] 变更计划缓存 key 不稳定

- **Bug 代码**：:318-319 `hashlib.sha256(f"{requirement}:{project_summary}")`——project_summary（:284-305）由依赖图节点遍历顺序/描述拼接，节点顺序或描述微变即缓存 miss；缓存文件 `.cache/change_plans.json` 只增不减（24h 过期但无清理）
- **影响**：缓存命中率低 + 文件无限增长

### IM9 [P3] 增量依赖图缺失/计划为空时静默回退全量生成

- **Bug 代码**：:66/:87 `return await self.generate_with_spec_first(requirement, callback)`——依赖图不存在或架构师返回空计划时**回退全新全量生成**
- **影响**：增量项目若 .dep_graph.json 丢失（如 /tmp 清理），增量修改静默变成全量重新生成——可能覆盖已有文件、耗时剧增；无告警提示用户

## 4. 潜在问题与未知点

- `_is_simple_change`（:637-671）关键词列表（"健康检查"/"add endpoint"/"重构"等中英混合）——新增文件默认简单变更（:667）用轻量模型，复杂新文件可能被低估
- `_extract_imports_from_content` 的 `from xxx import` 路径猜测（:843-847 只试 src/xxx.py、xxx.py 等 3 种）——包路径 miss 时依赖缺失
- `generated_contents[file_path] = result[:8000]`（:532/:552）——上游内容 8000 字符截断注入（与 spec_first 的 8000 截断同策略）
- delete 分派直接 `full_path.unlink()`（:198）——无 git 备份保护（对比 incremental_generate 有 `_git_stash_push`）

## 5. 修改建议（改什么 → 达成什么目的）

| # | 优先级 | 修改动作 | 达成目的 | 涉及位置 | 对应 Backlog |
|---|--------|---------|---------|---------|-------------|
| 1 | P1 | IM1：简单变更/降级重试模型改走 dynamic_model_router（get_assignment/fallback chain） | 非 SiliconFlow provider 下增量可用，统一模型管理 | incremental_modify.py:482/:688 | 新增 |
| 2 | P2 | IM2：`_content_already_satisfies` 改为校验关键实现语义（必要时 LLM 判定）而非关键词存在 | 杜绝真实缺失被误跳过 | incremental_modify.py:862-902 | 新增 |
| 3 | P2 | IM3：增量生成结果复用 `is_valid_code_content` 校验，失败走重试 | 坏内容不进入依赖图 | incremental_modify.py:532/:552 | 新增 |
| 4 | P2 | IM4：`_extract_imports_from_content` 按语言适配器解析 import | 多语言增量依赖图正确更新 | incremental_modify.py:806-853 | 新增 |
| 5 | P2 | IM5：重试 engineer 复用主链路（传 semaphore/cost_tracker/provider_id） | 并发受控、成本计入 | incremental_modify.py:710-715 | 新增 |
| 6 | P3 | IM6：删除闭包死代码，并发上限收敛到单处 | 消除双定义 | incremental_modify.py:466-467/:1023 | 新增 |
| 7 | P3 | IM8：缓存 key 用稳定的依赖图哈希；加文件大小上限/清理 | 缓存命中稳定、文件不膨胀 | incremental_modify.py:318/:405-427 | 新增 |
| 8 | P3 | IM9：回退全量生成前告警/确认；删除文件前 git 备份 | 增量回退不静默、删除可回滚 | incremental_modify.py:66/:198 | 新增 |

## 6. 演化方向关联

- **双套增量并存**：IncrementalModifyMixin（依赖图驱动）vs IncrementalGenerateMixin（会话恢复驱动）——演化应收敛，统一增量入口按 session 状态选择策略
- **IM1/IM5** → 演化蓝图「模型路由统一」（dynamic_model_router 是唯一模型决策源），硬编码模型名违背 DMR 体系
- **IM3/IM2** → 与 SPFG1/SPFG2（文件启发式校验缺陷）同类——「存在≠正确」验证语义是验证层演化主线（LangGraph Evaluator-optimizer 条件回边方向）
- **IM9** → 断点续传/回退策略显式化（Checkpointer 对照：增量进度应持久化检查点而非依赖图存在性）
