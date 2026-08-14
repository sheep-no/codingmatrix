# Agent 子系统详细推演 · 批3：支撑层

> 版本：v1.3 | 日期：2026-08-05 | 范围：A8 测试运行 + A9 工具执行 + A10 学习记忆 + A11 RAG 检索 + A12 依赖分析 + A13 语言适配 + A14 MCP + A15 基础工具（8 个子系统，39 模块：A8=5 + A9=9 + A10=7 + A11=5 + A12=5 + A13=4 + A14=1 + A15=3）
>
> 本文是 `TASKS.md` A 组演化路径清单的**详细推演版**。原则：**先修正确性（P0 Bug/依赖）、再统一机制、后智能增强**。
>
> **v1.3（2026-08-05 最终确认推演）**：**全量行数断言复核零偏差**——38 模块表（A8=5 + A9=9 + A10=7 + A11=5 + A12=5 + A13=4 + A15=3）+ A14 mcp_client 513（文字列出）= 39 模块全部与实测精确一致；file:line 复核（test_runner:237 非 Python 分支、docker_runner 三使用方、mcp_client:41/:346/:396）全部精确。header 模块数「约 36」修正为 **39**（A8-A15，含 A14 mcp_client）。
>
> **v1.2（2026-08-05 实测复核）**：A8-A15 全部行数复核精确（test_runner 811 / orchestrator_testing 306 / test_selector 215 / test_framework_config 88 / service_config_templates 461；executor 451 / agent_executor 164 / code_patcher 629 / git_operations 346 / snapshot_manager 213 / global_constraint 359 / impact_analyzer 205 / architecture_inspector 510；feedback_learner 428 / failure_clusterer 219 / memory 580；vector_index 181 / project_metadata 194 / spec_cache 605 / template_extractor 153 / project_profiler 791；language_adapter 281 / python 400 / javascript 486 / generic 416；mcp_client 513；complexity 172 / shadow_scanner 84）；A14 行号精确（MCPServerConnection:41 / get_tools_as_specialist_format:346 / MCPClientManager:396）。**补全 A10 孤儿模块行数**：user_preference_learner 487 / fix_pattern_cache 266 / cloud_learning_hub 336 / conversation_store 317。用例数对齐 AGENT-ENGINE v1.9（单测 1506、E2E 413）。
>
> **v1.1（2026-08-04 实测复核）**：**docker_runner 修正为非孤儿**（原「802 行孤儿」判定错误，实测 3 个生产使用方：orchestrator_testing:213 / code_tasks:102 / project_tasks:88，废弃前须迁移引用）；mcp_client `MCPServerConnection` 定义在 :41（原写 :44）；A10/A12 孤儿清单（user_preference_learner/fix_pattern_cache/cloud_learning_hub/multi_language_parser）实测全部成立。**方法数校正**（含 async def 精确统计）：language_adapter 21→17、python 10→9、javascript 10→8、generic 13→12、code_patcher 14→13；git_operations 22 / architecture_inspector 21 / snapshot_manager 4 / impact_analyzer 5 / global_constraint 11 / framework_detector 5 / language_detector 8 / multi_language_parser 11 / dependency_graph 42 / utils 27 / complexity 4 / shadow_scanner 2 全部精确。

## 总览

| 子系统 | 模块数 | 关键现状 | 代表演化点 |
|--------|--------|---------|-----------|
| A8 测试运行 | 5 | test_runner 811 行跑真实依赖安装+服务容器 | 收敛为轻量验证（P0） |
| A9 工具执行 | 9 | ToolRegistry 单例闭包 Bug、tools 1292 行 | 闭包修复（P0）、错误中间件（P1） |
| A10 学习记忆 | 7 | 三处余弦相似度重复、3 孤儿 | 相似度收敛（P2）、学习闭环（P2） |
| A11 RAG 检索 | 5 | faiss 未安装、spec-first 不写索引 | faiss 安装（P0） |
| A12 依赖分析 | 5 | dependency_graph 1340 行、import 验证非真实解析 | 拆分（P1） |
| A13 语言适配 | 4 | python/js/generic 三 adapter 注册生效 | 新语言扩展（P2） |
| A14 MCP | 1 | mcp_client 513 行，有 get_tools_as_specialist_format | 工具注册（P2） |
| A15 基础工具 | 3 | utils 1383 行、complexity 独立 | utils 拆分（P1） |

---

## A8. 测试运行（5 模块）

### 1. 现状基线

| 模块 | 行数 | 职责 |
|------|------|------|
| `test_runner.py` | 811 | `IsolatedTestRunner`（docker 优先）+ `_start_service_containers`(325) 服务容器启动 |
| `orchestrator_testing.py` | 306 | `TestingMixin`：`_run_dynamic_tests`/`_select_tests`/`_cluster_test_failures`/`_detect_test_command`/`_collect_all_tests` |
| `test_selector.py` | 215 | `TestSelector`：同目录/高依赖/smoke 测试选择 |
| `test_framework_config.py` | 88 | `TestFrameworkConfig` 框架检测 |
| `service_config_templates.py` | 461 | `ServiceTemplate`，已接线 service_container_manager:392 |

**实测确认（2026-08-02，AGENT-ENGINE.md 2.1 决策）**
- 验证策略定案：**最终产物在用户本地 IDE 运行**（C 方案分层验证），舍弃云端运行验证与网页预览
- 云端只保留静态验证 + mock 单测（`test_runner.py:237` 非 Python 分支直接在宿主原目录执行 `mvn verify`，无隔离无资源限制，16C16G 并发 2 个即告急）
- 主路径 0 次 test_runner 调用，只有 traditional 路径用（将在 A2 删除）

### 2. 演化目标

```
【近期】收敛止血：test_runner 只留静态+mock 轻量验证（P0）
  ↓
【中期】本地入口：VSCode 插件「本地运行测试」复用框架检测/输出解析
  ↓
【长期】协议化：验证报告 JSON 结构化，云端+本地统一格式
```

### 3. 分阶段路径

**阶段一（近 1 迭代）：test_runner 收敛**
- 砍掉最重两块：真实依赖安装 + 服务容器启动（`_start_service_containers`），保留 `run_tests` 的 mock 单测分支
- `docker_runner.py`（app/utils/，802 行）**非孤儿**：3 个生产使用方（orchestrator_testing.py:213、code_tasks.py:102、project_tasks.py:88）——废弃动作须**先迁移这 3 处引用**再标记废弃（承接 AGENT-ENGINE.md 阶段一 1.1 收敛顺序）
- 验收：test_runner 不再安装依赖/起容器；mock 单测仍驱动生成-验证-修复闭环；docker_runner 引用已迁移

**阶段二（近 2 迭代）：本地 IDE 验证入口**
- VSCode 插件提供「本地运行测试」，复用 `run_tests` 的框架检测与输出解析逻辑，执行端移到插件
- 测试结果回传云端进入 `error_recovery` 修复循环（承接 A7）
- 验收：插件可本地跑测试并回传结果，云端静态验证不依赖它

**阶段三（中期）：报告协议化**
- 验证报告 JSON 结构化输出（云端静态 + 本地真实统一格式，可交叉比对）
- 验收：两种验证结果可交叉比对，格式统一

### 4. 风险与依赖

| 风险 | 应对 |
|------|------|
| 砍云端真实验证使修复循环失反馈 | 静态验证 + mock 单测仍回传 error_recovery；插件回传补充（AGENT-ENGINE 2.1 收敛顺序） |
| 插件开发成本高 | 只做「本地跑测试+回传」最小闭环，避免从零开发 |
| 与 A7 Java/Go 静态验证依赖 | 收敛同步补齐静态验证（A7 阶段一 P0） |

---

## A9. 工具执行（9 模块）

### 1. 现状基线

| 模块 | 行数 | 职责 |
|------|------|------|
| `executor.py` | 451 | `EnhancedExecutor` + `ToolRegistry` 模块级单例（含闭包 Bug） |
| `tools.py` | 1292 | 20 个工具（文件/git/搜索/执行） |
| `agent_executor.py` | 164 | Agent 执行器，已接 react_agent |
| `code_patcher.py` | 629 | 代码打补丁（13 方法） |
| `git_operations.py` | 346 | git 操作（22 方法） |
| `snapshot_manager.py` | 213 | 快照管理（4 方法） |
| `global_constraint.py` | 359 | 全局约束（11 方法） |
| `impact_analyzer.py` | 205 | 影响分析（5 方法） |
| `architecture_inspector.py` | 510 | 架构检查（21 方法） |

**实测确认（2026-08-02，AGENT-ENGINE.md 9.1）**
- **P0 Bug**：`ToolRegistry` 单例闭包捕获 `project_path`。`_register_default_tools` 中 `_adapt_sync`/`_adapt_async` 闭包捕获 `self.project_path`（首实例 `"."`），因 `_tools` 非空跳过重新注册，后续实例永久复用首实例路径 → 多项目文件错位（数据错位级，已复现）
- 工具错误处理散落各 `_tool_*` 内部与 `_wrap_sync` try/catch，模型拿不到结构化错误

### 2. 演化目标

```
【近期】修复 P0：ToolRegistry 闭包 Bug
  ↓
【中期】统一中间件：工具错误结构化回传 LLM 决策
  ↓
【长期】域分组：tools 拆分 + 与 workflow 对齐
```

### 3. 分阶段路径

**阶段一（近 1 迭代）：P0 修复**
- `ToolRegistry` 工具调用改为按调用时传入 `project_path`（wrapper 签名带参数），消除闭包捕获
- 或每次实例化重新注册工具（去掉 `if not self.tool_registry._tools` 短路）
- 补回归单测：两个不同 `project_path` 实例先后写入，验证落位各自根目录
- 验收：双目录回归测试通过，多项目文件不错位

**阶段二（近 2 迭代）：工具错误处理中间件**
- 在 `executor.py` 引入 `tool_call_middleware`：工具异常统一转为结构化结果（错误类型 + 可读描述 + 建议动作）
- 失败结果回传 LLM（ReAct 循环），由模型决定重试/换工具/降级
- 与 `error_recovery` 闭环打通：工具级失败 → 错误分类 → 策略修复（承接 A7）
- 验收：模型可读结构化错误并自主重试；闭包 Bug 彻底消除

**阶段三（中期）：tools 拆分与对齐**
- `tools.py`（1292 行）按域分组：文件/git/搜索/执行
- 工具与 Workflow 节点对齐：节点复用 Agent 工具，共享执行上下文（承接 G2 工作流）
- 验收：工具按域组织，Workflow 节点可复用工具执行

### 4. 风险与依赖

| 风险 | 应对 |
|------|------|
| 单例改造影响所有工具调用 | 保留 get_instance() 接口，仅改 wrapper 签名，全量单测回归 |
| 中间件改变错误行为 | 灰度切换，错误分类不兼容时回退原 try/catch |
| 工具拆分破坏 import | 保持对外符号 re-export，拆分后 E2E 通过 |

---

## A10. 学习与记忆（7 模块）

### 1. 现状基线

| 模块 | 行数 | 职责 | 接线状态 |
|------|------|------|---------|
| `feedback_learner.py` | 428 | FixPattern/ErrorPattern/FeedbackLearner 学习器 | ✅ |
| `failure_clusterer.py` | 219 | FailureClusterer 失败聚类 | ✅ |
| `memory.py` | 580 | BaseMemory/ConversationMemory 语义搜索（:198 余弦） | ✅ |
| `user_preference_learner.py` | 487 | 用户偏好建模 | ⚠️ 孤儿（仅测试） |
| `fix_pattern_cache.py` | 266 | 修复模式缓存 | ⚠️ 孤儿（仅测试） |
| `cloud_learning_hub.py` | 336 | 跨项目知识共享 | ⚠️ 孤儿（仅测试） |
| `conversation_store.py` | 317 | 会话历史持久化 | ✅ 已接线 orchestrate_endpoints |

**实测确认（2026-08-02，AGENT-ENGINE.md 4.3/9.7）**
- 三处余弦相似度实现重复：`memory.py`/`feedback_learner.py`/`spec_cache.py`
- 3 个孤儿模块：`user_preference_learner`/`fix_pattern_cache`/`cloud_learning_hub`（仅测试引用）

### 2. 演化目标

```
【近期】孤儿决策：接线或删除
  ↓
【中期】相似度收敛：统一 utils/similarity.py
  ↓
【长期】学习闭环：record_fix 全覆盖 + 跨会话记忆
```

### 3. 分阶段路径

**阶段一（近 1 迭代）：孤儿决策**
- `user_preference_learner`：接线会话生命周期（生成前读偏好注入 prompt）
- `fix_pattern_cache`：优先接入 error_recovery；若与 feedback_learner 重叠则删除
- `cloud_learning_hub`：阶段四跨会话长记忆基础，暂保留
- 验收：grep 确认孤儿模块有生产调用方或废弃标记（承接 AGENT-ENGINE 4.5）

**阶段二（近 2 迭代）：相似度收敛**
- 三处余弦相似度实现统一到 `utils/similarity.py`（memory/feedback_learner/spec_cache）
- `memory.search_async` 统一走 embedding 检索，去掉重复实现
- 验收：grep 无重复余弦实现，对话记忆与历史项目检索共用模块

**阶段三（中期）：学习闭环**
- `record_fix` 在所有修复路径触发（承接 A7 阶段三），错误聚类 → 策略学习 → 预防 prompt
- ε-greedy 学习数据与 strategy_learner 合并（承接 A6 阶段三）
- 验收：学习数据覆盖率 90%+ 修复路径，embedding 命中缓存率 >80%

### 4. 风险与依赖

| 风险 | 应对 |
|------|------|
| 孤儿接线引入不稳定 | 先「记录-观察」模式上线，Q-Learning 离线回放 |
| 相似度收敛改动记忆检索 | 统一后跑记忆相关单测，行为一致 |
| 依赖 embedding API | AiCodeUtil 已有双层缓存，可复用 |

---

## A11. RAG 与检索（5 模块）

### 1. 现状基线

| 模块 | 行数 | 职责 | 接线状态 |
|------|------|------|---------|
| `vector_index.py` | 181 | `VectorIndexManager` FAISS 索引（load_or_create/_create_empty_index） | ⚠️ faiss 未装降级 |
| `project_metadata.py` | 194 | `ProjectMetadataManager` 项目元数据 | ✅ |
| `spec_cache.py` | 605 | `SpecCache` spec 缓存（含余弦实现） | ✅ |
| `template_extractor.py` | 153 | `TemplateExtractor` 模板提取 | ✅ |
| `project_profiler.py` | 791 | `ProjectProfiler` 项目画像（LanguageProfile/ArchitectureInfo/RiskAreas/TestPatterns） | ✅ |

**实测确认（2026-08-02，AGENT-ENGINE.md 1.3/9.5）**
- **P0**：faiss 未安装 → `VectorIndexManager.search` 抛异常，`layer2_semantic` 降级关键词匹配，向量检索从未生效
- **P1**：spec-first 主路径无 `extract_and_save` 调用，历史项目库只有传统路径数据
- embedding 正常：`AiCodeUtil.get_embedding`（bce-embedding-base_v1, 768 维），内存 1h + 磁盘 24h 双层缓存

### 2. 演化目标

```
【近期】链路打通：faiss 安装 + spec-first 写入索引（P0/P1）
  ↓
【中期】质量增强：相关性过滤/去重、embedding 可配置
  ↓
【长期】跨会话长记忆：历史项目检索升级为长记忆源
```

### 3. 分阶段路径

**阶段一（近 1 迭代）：链路打通**
- faiss-cpu 加入 `configs/requirements.txt`，`except ImportError` 改为显式告警 + 依赖登记
- `spec_first_generate.py` 收尾调用 `extract_and_save_feature_list`（承接 A2 阶段二）
- 补 `layer2_semantic` 测试断言走向量分支
- 验收：faiss 可导入，spec-first 生成后 FAISS 新增记录，layer2 命中

**阶段二（近 2 迭代）：质量增强**
- 检索结果注入 prompt 前相关性过滤 + 去重（避免低分项目污染）
- embedding 模型可配置化（settings 增加配置，替换硬编码默认值）
- 索引健康检查：损坏自动重建（现 load_or_create 失败仅警告）
- `memory.search_async` 统一走 utils/similarity.py（承接 A10 阶段二）
- 验收：低分项目不进注入，索引损坏自动重建，embedding 可配置

**阶段三（中期）：跨会话长记忆**
- `vector_index` 构建项目级长期记忆，跨会话复用架构决策/修复经验（承接 AGENT-ENGINE 6.4）
- 与 spec_cache 合并为统一「项目知识库」
- 验收：跨会话检索历史项目可复用，重复错误显著减少

### 4. 风险与依赖

| 风险 | 应对 |
|------|------|
| faiss-cpu 需 C 扩展 | wheel 无编译依赖，锁版本入 requirements-test，单测 mock embedding |
| 检索污染需求分析 | 相关性阈值 + 灰度对比关键词/向量命中质量 |
| 索引损坏 | 健康检查自动重建，原子更新 |

---

## A12. 依赖分析（5 模块）

### 1. 现状基线

| 模块 | 行数 | 职责 | 接线状态 |
|------|------|------|---------|
| `dependency_graph.py` | 1340 | 依赖图构建/拓扑/完整性/LLM 推断（42 方法） | ✅ |
| `dependency_rules.py` | 183 | 依赖规则（无方法，纯常量/数据） | ✅ |
| `framework_detector.py` | 188 | 框架检测（5 方法） | ✅ |
| `language_detector.py` | 775 | 语言检测（8 方法） | ✅ |
| `multi_language_parser.py` | 392 | 多语言依赖解析（11 方法） | ⚠️ 孤儿（被 language_adapter 取代） |

**实测确认（2026-08-02）**
- `validate_imports` 分析 import 语句 AST，`validate_runtime_imports` 仅检查模块可导入——无法发现「模块存在但符号缺失」（AGENT-ENGINE 2.1 已接受，插件回传补充）

### 2. 演化目标

```
【近期】拆分：dependency_graph 1340 行拆 4 部分
  ↓
【中期】孤儿处置：multi_language_parser 决策
  ↓
【长期】真实解析：import 验证增强（插件回传反馈）
```

### 3. 分阶段路径

**阶段一（近 1-2 迭代）：拆分**
- `dependency_graph.py` 拆：图构建/拓扑计算/完整性校验/LLM 推断
- 验收：模块 <800 行，依赖图行为不变，E2E 通过

**阶段二（近 1 迭代）：孤儿处置**
- `multi_language_parser`（被 `language_adapter` 取代）删除候选，全库引用扫描确认零引用后归档
- 验收：grep 确认孤儿状态，处置标记明确

**阶段三（中期）：验证增强**
- import 验证的「符号缺失」局限：插件本地跑测试回传补充（承接 A8 阶段二）
- 验收：真实错误经插件回传进修复循环

### 4. 风险与依赖

| 风险 | 应对 |
|------|------|
| 依赖图拆分破坏拓扑调度 | 拆分后保留对外接口，全量单测回归 |
| 孤儿删除误伤 | 删除前全库扫描 + git 快照回滚 |

---

## A13. 语言适配（4 模块）

### 1. 现状基线

| 模块 | 行数 | 职责 | 接线状态 |
|------|------|------|---------|
| `language_adapter.py` | 281 | 语言适配基类（17 方法） | ✅ |
| `python.py` | 400 | Python 适配（9 方法） | ✅ 注册 :400 |
| `javascript.py` | 486 | JS 适配（8 方法） | ✅ 注册 :486 |
| `generic.py` | 416 | 通用适配（12 方法） | ✅ 注册 :416 |

**实测确认**：虽极少直接 import，但经 `adapters/__init__.py` 导出，由 `LanguageAdapterRegistry.register` 模块加载时注册（AGENT-ENGINE 9.7 非孤儿确认）

### 2. 演化目标

- **阶段一**：扩展新语言仅加 adapter 文件，配置化启用（P2）
- **阶段二**：Java/Go 适配器与 code_validator 静态验证扩展对齐（承接 A7 阶段一，P1）
- **验收**：新语言注册无需改引擎源码；Java/Go 语法验证生效

### 3. 风险

| 风险 | 应对 |
|------|------|
| 适配器注册遗漏新语言 | Registry 统一入口，缺省 generic 兜底 |

---

## A14. MCP 集成（1 模块）

### 1. 现状基线

- `mcp_client.py`（513 行）：`MCPServerConnection`（:41，含 `get_tools_as_specialist_format`:346）+ `MCPClientManager`（:396）
- 对应 v2 `mcp_admin.py`（servers CRUD + toggle + test，stdio/HTTP 双传输）

### 2. 演化目标

- **阶段一（P2）**：`get_tools_as_specialist_format` 产物注册进 `SPECIALIST_TOOLS`，MCP 工具进入 Agent 工具集（承接 AGENT-ENGINE 6.3 动态工具选择）
- **阶段二（P3）**：MCP 服务器健康度纳入 `dynamic_model_router`，故障自动降级
- **验收**：MCP 工具可被 Agent 调用，健康度入路由

### 3. 风险

| 风险 | 应对 |
|------|------|
| MCP 工具描述撑爆上下文 | 动态工具裁剪（按角色/权限过滤），非全量暴露 |

---

## A15. 基础工具（3 模块）

### 1. 现状基线

| 模块 | 行数 | 职责 |
|------|------|------|
| `utils.py` | 1383 | 27 方法：内容提取/沙箱/质量校验混杂 |
| `complexity.py` | 172 | 复杂度计算（4 方法） |
| `shadow_scanner.py` | 84 | 影子扫描（2 方法） |

### 2. 演化目标

- **阶段一（P1）**：`utils.py` 按内容提取/沙箱/质量校验拆 `utils/` 子包
- **阶段二（P2）**：`complexity` 与 cross_validator 关键文件判定共用（`is_critical_file` 触发率已优化 -60%，继续降 token 成本）
- **验收**：utils 子包模块 <800 行，复杂度判定单一来源

### 3. 风险

| 风险 | 应对 |
|------|------|
| utils 拆分影响全 Agent 引用 | 保持对外符号 re-export，逐模块迁移 + 回归 |

---

## 验收标准汇总（批3）

| 子系统 | 阶段一验收 | 阶段二验收 |
|--------|-----------|-----------|
| A8 测试运行 | test_runner 不再装依赖/起容器 | 插件可本地跑测试回传 |
| A9 工具执行 | 双目录回归通过，无文件错位 | 结构化错误回传，模型可重试 |
| A10 学习记忆 | 孤儿接线或标记明确 | 无重复余弦实现 |
| A11 RAG 检索 | faiss 可用 + spec-first 写索引 | 过滤去重 + 索引自愈 + embedding 可配 |
| A12 依赖分析 | dependency_graph <800 行 | 孤儿处置标记明确 |
| A15 基础工具 | utils 子包拆分完成 | 复杂度判定单一来源 |

---

## 三批推演总览

| 批次 | 子系统 | 文档 |
|------|--------|------|
| 批1 主链路 | A1 编排核心 / A2 生成路径 / A3 需求分析 | [AGENT-EVOLUTION-BATCH1.md](AGENT-EVOLUTION-BATCH1.md) |
| 批2 能力层 | A4 上下文压缩 / A5 角色体系 / A6 模型路由 / A7 验证修复 | [AGENT-EVOLUTION-BATCH2.md](AGENT-EVOLUTION-BATCH2.md) |
| 批3 支撑层 | A8-A15（测试/工具/学习/RAG/依赖/适配/MCP/基础） | [AGENT-EVOLUTION-BATCH3.md](AGENT-EVOLUTION-BATCH3.md) |
