# Orchestrator 演化深扫文档

> 版本：v0.1 | 扫描日期：2026-08-09 | 状态：已完成
> 归属：Agent 大系统 / 支撑模块（编排器组装核心）
> 路径：app/agent/orchestrator.py（138 行）
> 索引：[TASKS.md](../TASKS.md)

## 1. 模块作用与功能

OrchestratorAgent 组装核心：`OrchestratorAgent` 继承 6 个 Mixin（ProgressMixin/GenerationMixin/FilesMixin/TestingMixin/UtilsMixin/RequirementAssociationMixin），`__init__` 集中声明全部配置与子组件属性——是 13 模块主链路的编排器本体。

- **核心类**：`OrchestratorAgent`（:35，继承 6 Mixin）。`__init__`（:44-138，24 参数）。
- **职责**：输出目录解析（:69-77）、配置开关存储（:78-103）、子组件初始化声明（:111-126，全 None 由 `_initialize_components`（mixin.py:39）统一注入）、状态容器初始化（:128-135）、成本追踪器（:138）。

## 2. 依赖与被依赖

- **生产使用方**：__init__.py:2 `from app.agent.orchestrator import OrchestratorAgent`（主入口导出）。
- **继承 Mixin**：orchestrator_progress（ProgressMixin）、orchestrator_generation（GenerationMixin）、orchestrator_files（FilesMixin）、orchestrator_testing（TestingMixin）、orchestrator_utils（UtilsMixin）、orchestrator_requirements（RequirementAssociationMixin）——6 份详档均已覆盖。
- **子组件**：ComplexityAnalyzer/CodeValidator/specialists/ErrorRecoveryLoop/APIContractChecker/CodePatcher/CrossFilePatcher/DependencyGraph/SessionManager/SpecCache/FeedbackLearner/memory/LayeredModelRouter（`_initialize_components` 注入，mixin.py:39-90）。
- **测试覆盖**：orchestrator.py 无独立测试（Mixin 组合体）；相关集成在 tests/archive。

## 3. 已探明 Bug

### OA12 [P2] `dependency_graph` 开关死配置 + `dependency_graph_obj` 死属性：共享依赖图从未建立

- **Bug 代码**：

```python
# orchestrator.py:52/:83 - 开关声明但全库零消费
dependency_graph: bool = True       # :52
self.dependency_graph = dependency_graph   # :83
# :126 - 属性声明 None，全库零赋值
self.dependency_graph_obj: Optional[DependencyGraph] = None
```

- **根因**：`self.dependency_graph`（bool 开关）在 orchestrator_files.py:342/:364/:630 消费的是 `self.dependency_graph_obj`（DependencyGraph 实例）——**开关与对象是两个独立属性**。`dependency_graph_obj` 全库无任何赋值点（`_initialize_components`（mixin.py:39-90）初始化 analyzer/model_router/architect/engineer/reviewer/validator/error_recovery，**不初始化 dependency_graph_obj**）→ 恒 None。
- **实际使用模式**：DependencyGraph 并非编排器共享属性，而是生成器**方法内局部实例化**——architect.py:826-827、traditional_generate.py:161-162、spec_first_generate.py:222-223/:249-250 各自 `DependencyGraph(language_adapter=...)` + `build_from_architecture(architecture)`。
- **影响**：orchestrator_files.py 三处消费恒空——:342-343 `dependency_graph_obj.get_context_for_file(...)`（依赖上下文注入）恒 None 走空、:364/:630 `dependency_graph_obj.nodes.keys()`（全文件枚举）恒 `[]`。**「共享依赖图」能力从未建立**；开关是死配置（DG 详档补充：不仅两套构建方法死代码，编排器消费属性也未接线）。

### OA1 [P3] 输出目录归一化分叉：`./projects` 前缀字符串判断 + 两套相对路径语义

- **Bug 代码**：

```python
# :72-77 - 只有非 ./projects 前缀的相对路径才拼 PROJECTS_BASE_DIR
if not self.output_dir.is_absolute() and not str(self.output_dir).startswith("./projects"):
    try:
        self.output_dir = Path(PROJECTS_BASE_DIR) / self.output_dir
    except ImportError:
        pass    # :76-77 - ImportError 静默保持相对路径
```

- **根因**：`startswith("./projects")` 是字符串前缀判断非路径段判断（`./projects2/foo` 也会匹配）；`1/xxx` 格式拼 PROJECTS_BASE_DIR，`./projects/xxx` 留在 CWD 下——两套相对路径语义。ImportError 时静默保持相对（无 warning）。
- **影响**：路径语义分叉，同是相对路径不同前缀落到不同根目录；`_relative_output_dir`（:69）与归一化后的 output_dir 可能不一致。

### OA4 [P3] CostTracker 实例化（OP1 恒零位置确认）

- **Bug 代码**：

```python
# :138 - 成本追踪器实例化，但 get_model_config 无成本键 → 金额恒零
self.cost_tracker = CostTracker()
```

- **根因**：与 OP1（llm_client `_record_usage` 读不存在的 `cost_per_1m_input/output` 键 → cost_usd 恒 0）同源，此处为 CostTracker 在编排器的实例化位置确认。
- **影响**：全部生成链路的成本金额恒零（token 计数正确但 USD 永远 0，LC1/DMR1/OP1 三处同源）。

### OA3 [P3] `analyzer`/`complexity` 双对象近义命名

- **Bug 代码**：

```python
# :115/:128 - ComplexityAnalyzer（分析器）与 ComplexityAnalysis（结果）双属性
self.analyzer: Optional[ComplexityAnalyzer] = None
self.complexity: Optional[ComplexityAnalysis] = None
```

- **根因**：`_initialize_components`（mixin.py:55-56）`self.analyzer = ComplexityAnalyzer(); self.complexity = self.analyzer.analyze(requirement)`——分析器与结果分存两属性，命名近义易混。
- **影响**：可读性/维护性风险；多个消费方需区分对象类型（UtilsMixin OU1 读 self.complexity.level）。

### OA6 [P3] `__init__` 延迟导入并固定实例化 GitOperations/SnapshotManager

- **Bug 代码**：

```python
# :106-109 - __init__ 内延迟导入 + 每次实例化创建 git 对象
from app.agent.git_operations import GitOperations
from app.agent.snapshot_manager import SnapshotManager
self.git_ops = GitOperations()
self.snapshot_mgr = SnapshotManager(self.git_ops)
```

- **根因**：即使不使用 git 快照，每次 OrchestratorAgent 实例化都创建 GitOperations + SnapshotManager 对象。
- **影响**：非必要对象创建；git 快照能力（OU9 双快照体系）依赖此实例。

### OA13 [P3] `__init__` 24 参数依赖注入过载

- **根因**：构造参数含 3 个可空注入（session_manager/spec_cache/feedback_learner）+ 5 个回调（callback/approval_callback/decision_callback/cancel_event）+ 8 个开关。参数过载但职责单一（纯组装），属可维护性风险。
- **影响**：新增能力需扩构造签名；组合体难以独立单测。

### OA2 [P3] 子组件全 None + `_initialize_components` 统一注入（v1.10 位置确认）

- **根因**：:115-126 全部属性初始 None，真实初始化在 `_initialize_components`（mixin.py:39，v1.10 已记录定义位置）。dependency_graph_obj 不在初始化列表（OA12 成因）。
- **影响**：初始化职责横跨 orchestration 流程；属性在 generate() 调用前访问（如 mixin 方法误用）会遇 None。

## 4. 修复建议

- **OA12**：统一依赖图生命周期——由 `_initialize_components` 按 `self.dependency_graph` 开关实例化 `dependency_graph_obj` 并 build_from_architecture，替换生成器内部 4 处局部构建为共享图；orchestrator_files 依赖上下文注入（:342）接入共享图。
- **OA1**：输出目录归一化用路径段判断（`Path.relative_to`/`resolve`），统一 `./projects` 与 `1/xxx` 语义；ImportError 记录 warning。
- **OA4**：并入 OP1 修复（model_registry.ln 成本字段接入）。
- **OA3**：合并 analyzer/complexity 或明确类型注解区分。
- **OA6**：GitOperations/SnapshotManager 惰性初始化。
- **OA13**：配置收拢为 dataclass/配置对象。
- **OA2**：dependency_graph_obj 等全部子组件纳入 `_initialize_components` 清单。

## 5. 待实测项

- OA12 为代码级确凿（`dependency_graph_obj =` 全库零匹配 + `_initialize_components` 列表确认不含）。
- OA1/OA3/OA4/OA6/OA13/OA2 为代码级结论。
