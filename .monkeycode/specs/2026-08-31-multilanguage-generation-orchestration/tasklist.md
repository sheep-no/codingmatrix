# 多语言代码生成稳定性实施计划

- [x] 1. 实现结构化生成计划和依赖上下文包
  - 修改 `app/agent/dependency_graph.py`，提供可序列化的上下文包、依赖关系、签名、相关实现片段和截断元数据；对应需求 2.1-2.4、设计正确性属性 5。
  - 修改 Spec-First 和传统生成入口，统一使用目标文件上下文包，并保留现有脱敏审计；对应需求 1.1-1.4、2.1、3.1-3.3。
  - [x] 1.1 为上下文包编写边界和属性测试，覆盖空依赖、超预算、无签名依赖和敏感信息预览；对应设计正确性属性 5。

- [x] 2. 实现单文件产物清单和拓扑调度门禁
  - 为生成文件记录 hash、导入、导出、语言、校验状态和诊断，并阻止无效上游释放下游节点；对应需求 4.1-4.4、设计正确性属性 3-4。
  - 统一 Spec-First、传统生成和增量修改路径的状态记录；对应需求 1.2、1.4、4.2。
  - [x] 2.1 为产物清单和拓扑释放规则编写单元及属性测试；对应设计正确性属性 1-4。专项测试 `tests/unit/test_shared_context.py` 已通过。

- [x] 3. 实现分级修复路由和修复预算
  - 按计划、语法、导入、类型、业务和测试错误选择修复路径，并限制修复文件范围；对应需求 5.1-5.3。
  - 实现单类错误最多 3 轮、任务累计最多 5 轮的计数和终止状态；对应需求 5.4、设计正确性属性 6。
  - [x] 3.1 为修复路由和轮次预算编写单元测试；对应需求 5.1-5.4。专项测试 `tests/unit/test_repair_router.py tests/unit/test_error_recovery.py` 已通过（4/4）。

- [x] 4. 云端基础校验边界和本地验证动作衔接
  - 确保云端结果统一标记 `cloud_syntax`，运行时、依赖、构建、单元测试和 E2E 进入现有 VS Code Agent Host 子规格；对应需求 3.3-3.4。
  - 对未知语言和验证入口返回 `unsupported`，保留已完成产物和诊断；对应需求 3.2、6.4。
  - [x] 4.1 增加云端到本地验证动作的集成测试；对应现有子规格需求 15.1-15.5。验证节点与 Host 回传专项测试 `tests/unit/test_validation_nodes.py tests/unit/test_local_validation_adapter.py` 已通过（25/25）。

- [ ] 5. 检查点：完成第一批云端编排验证
  - 主规格相关测试已通过：`49/49`；`python3 -m compileall -q app` 和 `git diff --check` 已通过。
  - Redis 启动后全量 Python 回归结果：`1842 passed, 2 skipped`；`tests/unit/test_orchestrator.py::TestDynamicModelRouter` 已改为校验兼容层默认角色分配并通过。
  - `python3 -m compileall -q app` 和 `git diff --check` 已通过；仓库归档测试目录仍包含历史语法不完整文件，未纳入 `pyproject.toml` 测试路径。
  - 仓库当前没有固定多文件评测样例，90% 最终成功率尚未形成可计算的评测证据。
  - 最小真实 SSE 生成链路已触发：认证、API 路由、任务创建、SSE 进度和模型调用均可用；Provider 凭据已生效，部分文件完成生成和语言校验。
  - 本次真实任务在 `tests/test_database.py` 的后续处理阶段持续发送 heartbeat 超过 3 分钟，未产生 `done` 事件，也未形成可用输出目录，已终止后台任务；实际生成结果仍不可判定。
  - 已修复调度器单文件超时、取消后的内部任务回收、未完成节点终态收敛和成功判定；新增专项回归测试，相关测试 `21/21` 通过。
  - 修复后相关回归集合共 `78 passed, 2 warnings`，覆盖调度器、依赖图、上下文、修复路由、验证节点和编排器。
  - 修复后的同进程真实 SSE 验证成功：HTTP 200，收到 `done`，生成 6 个文件，耗时约 161 秒；任务状态 `success=true`，未运行动态测试。
  - 实测会话目录 `projects/1/untitled_20260831_092924` 当前只包含 `.git` 和 `.gitignore`，生成文件未落盘；代码核对确认实际路径解析正确，`orchestrator_files.py` 在关闭 review/validation 的正常分支未写入文件即发送 `file` 事件，需修复“成功结果与磁盘产物不一致”问题。
  - 已修复单文件生成主路径：所有内容处理完成后统一使用 `write_file_atomic()`，写入失败返回文件级失败并阻止 `file` 事件；新增 `tests/unit/test_orchestrator_files.py`，相关编排器回归为 `44 passed`。
  - 已增加显式文件集合识别：需求包含“只需要/仅需要 ... 文件”时，架构完整性补全保留指定路径并停止追加依赖、README 和前端文件；严格集合专项回归纳入后共 `45 passed`。
  - 按确认的严格 6 文件和原始结果诊断策略重测时，模型实际扩展出额外文件（日志出现 `src/repositories/todos_repository.py`），任务超过 7 分钟仍持续 heartbeat，未产生终态；会话目录 `projects/1/untitled_20260831_095157` 为空，端到端 CRUD 验证因此无法开始。额外文件来自架构完整性/依赖补全逻辑，停滞点仍需为传统生成路径补充阶段级超时和日志。

- [x] 6. 建立 Orchestrator Core 契约和状态机
  - 新建 `app/agent/orchestration/` 包，定义 `OrchestrationCommand`、`OrchestrationState`、`StageResult`、`OrchestrationResult` 和终态枚举；对应需求 7.1-7.4、设计正确性属性 7、13。
  - 实现显式阶段转换、revision、唯一终态事件和 checkpoint 恢复游标；对应需求 7.2-7.4、11.1。
  - [x] 6.1 编写状态转换、非法转换、重复终态、幂等事件和 checkpoint 恢复测试。专项测试 `18/18`、状态与编排相关回归 `38/38` 通过，编排内核 `compileall` 和 `git diff --check` 通过。

- [x] 7. 实现文件计划策略和冻结计划
  - 从需求结构化结果生成 `strict` 或 `extensible` 策略，统一规范化文件路径；对应需求 8.1-8.4。
  - `strict` 策略校验集合外文件，`extensible` 策略记录新增来源和理由，计划通过后生成不可变版本；对应设计正确性属性 1、9。
  - [x] 7.1 编写显式文件集合、多语言路径、扩展来源和计划版本属性测试。专项测试 `24/24`、计划与编排相关回归 `63/63` 通过，编排包 `compileall` 和 `git diff --check` 通过。

- [x] 8. 实现 ModelGateway 和四级执行预算
  - 为每次模型调用传递任务、阶段、文件、调用和 ReAct 轮次标识；对应需求 9.1、11.1-11.2。
  - 实现模型调用墙钟总预算，流式保活数据不延长 deadline；对应需求 9.1、9.5。
  - 实现模型、文件、阶段和任务取消传播及子任务回收；对应需求 9.2-9.4、设计正确性属性 11-12。
  - [x] 8.1 使用可控挂起流编写总预算、读取活动、取消和信号量释放测试。新增 `tests/unit/test_orchestration_model_gateway.py`，任务 8 与相关编排回归 `101/101` 通过，编排包和共享调用层 `compileall`、`git diff --check` 通过。

- [x] 9. 实现 ArtifactCommitter 和成功门禁
  - 统一路径校验、原子写入、磁盘回读、非空、大小和 hash 校验；对应需求 10.1-10.3。
  - 仅在提交成功后登记 `ArtifactManifest` 并发布 `file_completed`；对应需求 10.2、设计正确性属性 8、10。
  - 在任务终态前比较冻结计划、完成事件、产物清单和磁盘文件集合；对应需求 10.4-10.5。
  - [x] 9.1 编写写入失败、回读失败、hash 不一致、重复提交和集合差异测试。新增 `tests/unit/test_orchestration_artifact_committer.py`，任务 9 专项与 Core 集成测试 `27/27`、任务 6-9 相关回归 `75/75` 通过，编排包 `compileall` 和 `git diff --check` 通过。

- [x] 10. 收敛统一 GenerationScheduler
  - 复用现有动态拓扑调度器，统一小项目和依赖分层项目的调度路径；对应需求 4.3、9.2-9.4。
  - 使用结构化并发管理活动文件任务，文件超时、阶段超时和用户取消后回收所有子任务；对应需求 7.3、9.2-9.4。
  - 无效上游将下游收敛为 `blocked`，调度完成后所有节点进入终态；对应设计正确性属性 4、12。
  - [x] 10.1 编写挂起文件、并发完成、上游失败、死锁、取消和终态收敛测试。新增 `app/agent/orchestration/generation_scheduler.py` 与 `tests/unit/test_orchestration_generation_scheduler.py`，专项测试 `8/8` 通过。

- [ ] 11. 渐进迁移传统生成入口
  - 已实现 `TraditionalAdapter`、`GenerationRequest` 和 `AdapterResult`，将现有架构规划和单文件生成转换为内核接口；对应需求 11.3-11.5。
  - 保持 `OrchestratorAgent` 构造参数、HTTP、SSE、会话和错误契约；对应设计正确性属性 14。
  - 已增加入口级 legacy/core 路由、无源码影子状态对比和 checkpoint `engine_version` 元数据；Core 生产生成入口仍等待 11.1 契约与真实生成验收后切换。
  - [ ] 11.1 运行传统生成契约测试、严格 6 文件真实生成、落盘 hash、语法、服务启动、CRUD 和 SQLite 持久化验证。
    - 2026-08-31 首次执行已确认 HTTP/SSE 入口可达（HTTP 200），模型阶段因服务进程未加载 `siliconflow` provider 配置失败，未生成产物；需补充用户项目供应商配置后重试。
    - 第 4 轮真实验收完成 6 个文件生成：HTTP 200、单一 `done`、零 SSE error、磁盘严格文件集合、SHA-256 和 AST 语法均通过；CRUD 收集因 `main.py` 导入严格集合外的 `.routers` 失败。已增加架构文件集合和顶层导入约束。
    - 第 5 轮真实验收再次完成严格 6 文件生成：HTTP 200、单一 `done`、零 SSE error、磁盘文件集合、SHA-256 和 AST 语法均通过，耗时 275.7 秒；CRUD 收集因顶层 `from . import crud` 失败，SQLite 持久化门禁因此未执行。
    - 已确定性修复第 5 轮暴露的两项问题：顶层 `from . import module` 归一化为直接导入；架构返回 `unknown/other` 类型时改用路径规则推断，并补充 `crud.py` repository 类型规则。相关专项测试 `29/29`、最终编排回归 `160/160` 和 `git diff --check` 通过。
    - 已达到任务累计 5 轮限制，本轮停止新增真实生成。11.1 保持未完成，下一验收窗口仅需复验 CRUD 和 SQLite 门禁；默认路由继续保持 legacy。
    - 最新真实验收于 145.6 秒返回结构化 `error`：`database.py` 连续生成混用 `sqlite3` 与 SQLAlchemy 的实现，重复静态错误指纹终止修复，下游文件按依赖门禁阻断；该轮没有发生网络超时。
    - 已将传统单文件生成的 120 秒活动 tracker 贯通到 Specialist 和 simple ReAct；流式模型 chunk 刷新活动时间，无活动调用会被取消并进入既有内容恢复重试，静态修复重试复用同一 tracker。心跳、模型预算和调度相关回归 `111/111` 通过。

- [ ] 12. 迁移 Spec-First 和增量修改入口
  - 实现 `SpecFirstAdapter`，将规范文件计划作为冻结计划输入；对应需求 11.5。
  - 实现 `IncrementalAdapter`，将影响文件集合转换为 strict 变更计划；对应需求 8.1-8.4、11.5。
  - [ ] 12.1 为两类入口运行 legacy/core 契约、恢复、取消和产物一致性测试。

- [ ] 13. 完成评测、切换和重复逻辑收敛
  - 建立固定多语言评测集，统计计划一致性、产物一致性、终态收敛、P95 耗时和 90% 端到端成功率；对应需求 6.3、11.2。
  - 传统生成、Spec-First 和增量修改依次通过门禁后切换默认路由；对应需求 11.4-11.5。
  - 清理已迁移 Mixin 中的重复生命周期、调度、写盘和终态逻辑，保留兼容适配器；对应设计实施阶段 7.3。

- [x] 14. 建立统一 GenerationPlan 和接口注册表
  - 新建 `app/agent/generation_plan.py`，统一保存项目语言、框架、运行时、文件角色、依赖闭包、计划策略和版本；对应设计 3.1、3.7 和正确性属性 1、9。
  - 新建 `app/agent/interface_registry.py`，登记模块 owner、公共符号、参数、返回类型、async 属性和可见性；对应需求 2.1-2.4、设计正确性属性 2、10。
  - 新建 `app/agent/dependency_manifest.py`，冻结标准库、项目模块、运行时依赖、测试依赖和禁止依赖；对应需求 3.1-3.4。
  - 将 Architect、DependencyGraph、TraditionalAdapter、SpecFirstAdapter 和 IncrementalAdapter 的输入统一转换为不可变计划版本；对应需求 8.1-8.4、11.3-11.5。
  - [x] 14.1 为计划闭包、接口唯一 owner、依赖白名单和多语言路径编写单元及属性测试；对应设计正确性属性 1、2、9。专项测试 `tests/unit/test_generation_contracts.py tests/unit/test_orchestration_plan.py` 已通过（29/29）。

- [x] 15. 收敛文件调度、产物状态和终态事实源
  - 修改 `app/agent/dependency_graph.py` 和 `app/agent/topology_scheduler.py`，使依赖图和拓扑层只从当前 GenerationPlan 派生，禁止静默删除或追加计划节点；对应需求 4.1-4.4。
  - 修改 `app/agent/orchestrator_generation/traditional_generate.py`、`spec_first_generate.py` 和 `orchestrator_files.py`，统一使用 GenerationScheduler、ArtifactCommitter 和 ArtifactManifest；对应设计 3.4、3.5、3.9。
  - 将文件生成、磁盘落盘、hash、验证状态和 SSE `file_completed` 事件统一绑定到产物提交结果；对应设计正确性属性 3、8、10。
  - 将 workflow、session、Core 和 SSE 的成功、失败、阻断、取消状态映射到唯一终态事件；对应设计 3.6、3.12 和正确性属性 7。
  - [x] 15.1 增加计划集合、调度集合、磁盘集合、事件集合一致性测试，以及失败级联和恢复测试；对应需求 4.1-4.4、设计正确性属性 3、4、7、8、9。专项回归 `tests/unit/test_orchestrator_files.py tests/unit/test_orchestration_artifact_committer.py tests/unit/test_orchestration_adapters.py` 已通过（100/100）。

- [x] 16. 建立统一 ValidationReport 和受控修复路由
  - 新建 `app/agent/validation_report.py`，统一收集语法、导入、依赖、导出、签名、async、类型、框架启动、测试和持久化结果；对应需求 3.1-3.4、5.1-5.4。
  - 将 `orchestrator_files.py` 中的 SQLAlchemy、import、参数和 Schema 修复器改为按错误类别注册的安全修复器；对应设计 3.5 和正确性属性 6。
  - 删除基于同名符号猜测 owner、删除业务字段掩盖契约错误、静默增加第三方依赖和生成空壳文件的成功路径；对应需求 2.2、3.1、4.4、5.2。
  - 为每类错误建立一次计划修订、一次接口修订或一次文件修复的重试预算，并记录候选版本、诊断版本和上下文 hash；对应需求 5.3-5.4、9.1-9.5。
  - [x] 16.1 为未知依赖、错误导出、async/sync、fixture 生命周期和业务字段缺失编写回归与属性测试；对应设计正确性属性 6、10。专项测试 `tests/unit/test_validation_report.py tests/unit/test_repair_router.py tests/unit/test_orchestrator_files.py` 已通过。

- [ ] 17. 实现语言 Adapter、能力模型和框架 Profile
  - 新建 `app/agent/languages/`，将 Python、TypeScript/JavaScript、Go、Java 和 Rust 的 AST、模块、签名、编译和测试能力统一为 LanguageAdapter 接口；对应需求 1.1-1.4、6.1-6.4。
  - 新建 `app/agent/capabilities/`，抽象 HTTP API、ORM、数据库、认证、WebSocket、依赖注入、测试客户端和迁移能力；对应设计 3.1、3.2。
  - 新建 `app/agent/framework_profiles/`，以版本化 YAML/JSON 描述框架依赖、能力映射、文件模板、安装、构建、测试、启动和健康检查命令；对应需求 6.1-6.4。
  - 实现 ProfileRegistry，根据语言、框架版本和能力选择 Profile，并标记正式、实验和待验证状态；对应需求 6.2、8.1-8.4。
  - [x] 17.1 为 Python/FastAPI、Python/Flask、TypeScript/Express 和 TypeScript/NestJS 建立语言解析、Profile 加载和最小 CRUD 验收测试；对应需求 6.1-6.4、设计正确性属性 10。专项回归 `tests/unit/test_languages.py tests/unit/test_framework_profiles.py` 已通过。

- [ ] 18. 接入官方脚手架、Toolchain 探测和自定义框架 Profile
  - 新建 `app/agent/scaffolding/`，通过官方 CLI 或模板创建框架基线，再将真实文件、依赖和符号导入 GenerationPlan；对应需求 6.1、8.1-8.4。
  - 新建 `app/agent/toolchain/`，自动探测安装、编译、格式检查、静态检查、测试、启动和健康检查命令，并输出统一执行契约；对应需求 3.3-3.4、6.3。
  - 增加用户工作区 Profile 的 schema、版本、作用域、命令白名单、依赖白名单和沙箱校验；对应需求 6.2、6.4、8.2。
  - 将用户新增框架先标记为 `custom_pending`，通过语法、安装、启动、CRUD 和持久化探针后再升级为 `experimental` 或 `supported`；对应需求 6.3、6.4。
  - [x] 18.1 编写内置 Profile、用户 Profile 隔离、恶意命令拒绝、版本兼容和 Toolchain 探针测试；对应需求 6.2-6.4、设计正确性属性 10、11。专项回归 `tests/unit/test_framework_profiles.py tests/unit/test_toolchain.py tests/unit/test_scaffolding.py` 已通过（16/16）。

- [ ] 19. 统一 ContextEnvelope、MCP、RAG、Skills 和 Memory
  - 新建 `app/agent/context_assembler.py`，将需求、GenerationPlan、接口注册表、依赖地图、框架 Profile、检索结果、Memory 和反馈提示按来源、优先级和作用域组装；对应需求 2.1-2.4、9.1-9.5。
  - 将 RetrievalService、Agent Knowledge Base、Agent Memory 和 AI Cloud RAG 接入代码生成前的上下文装配流程，并记录 context hash；对应需求 9.1-9.5。
  - 将 Skills 转换为带阶段、优先级、适用语言/框架、硬约束和验证规则的结构化策略；对应需求 5.1-5.4、6.1-6.4。
  - 将 MCP 工具描述扩展为能力、读写范围、项目作用域、依赖、超时和审计字段，并接入 Toolchain 和 ValidationCoordinator；对应设计 3.8、3.10-3.12。
  - 统一 `ModelGateway`、动态路由、LearningRouter 和反馈事件，记录模型、阶段、文件、计划版本、上下文 hash 和验证结果；对应需求 9.1-9.5、11.1-11.2。
  - 已将 ContextEnvelope 接入传统、Spec-First 和增量修改入口；ModelCallContext 与结构化模型诊断支持可选 context hash，并保持旧诊断字段兼容。
  - [x] 19.1 编写 ContextEnvelope 来源优先级、敏感信息过滤、MCP 权限、RAG 注入和 Memory 检索测试；对应需求 9.1-9.5、设计正确性属性 5、11。专项回归 `tests/unit/test_context_assembler.py` 已通过（3/3）。

- [ ] 20. 完成多语言评测矩阵和迁移收口
  - 已建立 `app.agent.evaluation_matrix.FIXED_CRUD_CASES` 和 `build_report()`，覆盖 Python/FastAPI、Python/Flask、TypeScript/Express、TypeScript/NestJS、Go HTTP 和 Java Spring Boot，并提供成功率、P95、缺失样例、非法指标和失败分类；真实运行数据和入口迁移仍待完成。
  - 已增加 `app.agent.profile_discovery`，按项目清单发现 Web、Windows、Android、爬虫、游戏和 CLI 应用域，输出候选 Profile、能力缺口和探针结果；`build_probe_plan()` 已输出经 `CommandSpec` 校验的参数数组探针步骤，`ProfileCache` 已支持工作区画像持久化、复用和 `custom_pending -> experimental -> supported` 状态门禁。
  - 已将 `profile_context()` 接入传统、Spec-First 和增量修改入口，规划阶段会把应用域、框架、能力、缺口和画像状态传入生成上下文。
  - 已增加 `app.agent.capability_resolver`，根据应用域输出必需能力、能力缺口、生成约束和验证步骤，并将能力策略加入 `profile_context()`。
  - 能力策略已增加 `required_components`，为 Web、游戏、爬虫、Android 和 Windows 生成 handler/service、rules/renderer、fetcher/parser/pipeline、screen/navigation 和 window/event_handler 等组件提示。
  - `ResolvedCapabilities.component_file_plan()` 已将领域组件映射为可投影到 GenerationPlan 的文件节点，并通过 `profile_context()` 传入三类生成入口。
  - `add_profile_components()` 已将组件节点和顺序依赖投影到 `GenerationPlan`；strict 计划保持冻结文件集合，extensible 计划允许受控扩展。
  - 新增 `ValidationCoordinator`，将 Profile 验证步骤转换为安全 `CommandSpec`，执行结果统一映射为 `ValidationReport`；不支持步骤、超时和非零退出码均形成结构化诊断。
  - 真实 SSE 验收已验证健康检查 HTTP 200、认证、模型调用、heartbeat 和文件事件链路；修复上下文来源值 `plan` 后，第二轮仍因模型生成的 `src/main.py` 导入 `models` 与计划文件集合不一致而进入 error 终态，项目目录仅落下 `.git`、`.gitignore` 和空 `src/`，尚未形成可验收产物。
  - 后续实测已增加唯一短模块别名解析、数据库层受限延迟模型导入和“只生成以下 N 个文件”严格集合识别；最终轮确认架构计划从 5 个文件收敛为指定的 `main.py`、`todo.py`、`test_main.py`。模型输出仍引用冻结计划外的 `typer`、`src.models.todo_model` 和 `src.utils.cli_utils`，系统按门禁进入唯一 error 终态且未落盘无效文件。相关回归 `114 passed`。
  - 建立 Python/FastAPI、Python/Flask、TypeScript/Express、TypeScript/NestJS、Go HTTP 和 Java Spring Boot 的固定 CRUD 评测样例；对应需求 6.3、11.2。
  - 为每个样例记录计划一致性、接口一致性、依赖闭包、文件完整性、编译、测试、启动、持久化、Token、P95 耗时和最终成功率；对应需求 6.3、9.1-9.5、11.2。
  - Traditional、Spec-First 和 Incremental 入口依次迁移到统一执行器，完成 legacy/core 影子对比后切换默认路由；对应需求 11.3-11.5。
  - 清理重复生命周期、重复模型调用、重复终态发布和已被 ValidationReport 替代的局部修复逻辑；对应设计实施阶段 7.3。
  - [ ] 20.1 运行全量单元、属性、框架烟囱和端到端评测，形成多语言支持矩阵和失败分类报告；对应需求 6.3、11.2、11.4。
