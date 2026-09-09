# CodingMatrix 项目文档

## 当前状态（2026-09-07）

- Agent Web 工作台与 VS Code 工作台的核心链路已实现：云端流式 Agent、会话控制、本地 Host 动作、审批、本地验证、Skill 同步和断线结果恢复均已接入并完成对应测试。
- Web 首页与 Agent Dashboard 已统一一级导航、输入操作和移动抽屉协议；1440px、768px、390px 三档视口验收覆盖桌面栏位、单列工作区、遮罩与 Escape 关闭、焦点恢复、输入字号和横向溢出。Agent、Workflow、PPT 和绘图工作区已接入共享 `TaskFeedback` 六字段模型，支持局部增量合并、运行耗时、连接状态、重复事件过滤、序列缺口检测和 PPT WebSocket 断线续传与快照恢复；统一操作反馈覆盖运行取消、失败重试、暂停恢复及完成后的预览、导出或下载。
- Web 生产构建已接入 manifest 驱动的性能预算检查，覆盖首屏 JavaScript、首屏 CSS、图片和入口直接动态导入的路由 chunk；当前四项基线均在预算内。应用入口同时采集成功路由导航耗时及页面级 LCP、INP、CLS，并通过浏览器性能快照和自定义事件提供诊断入口。长会话使用实测高度窗口化，聊天与 Agent thinking 采用帧级流式批处理，图片附件优先加载 320px 缩略图，消息编辑器和快捷键帮助保持独立动态 chunk。
- VS Code 扩展流式请求使用 `/api/v1/agent/orchestrate/stream`，安装包已生成于 `vscode-extension/codingmatrix-local-validation-0.1.0.vsix`。
- PPT 生成链路已完成共享产物卷、格式严格分流、HTML 输出转义、分块上传，以及五类叙事角色和九套独立主题构图；页数统一表示包含系统封面的最终总页数，初始大纲生成 `N-1` 个内容页，渲染边界归一重复封面并限制内容页预算；版本化设计令牌已覆盖实际 PPTX 颜色、字体和背景样式；Web 三步流程支持大纲新增、删除、重排、编辑、预计总页数和批准校验，预览页展示逐页质量分、问题和修复动作；游戏 AI 主题拥有领域化回退大纲，模型凭据缺失时跳过视觉分析并继续本地布局；后端单元测试为 `1947 passed, 2 skipped`，PPT 单元回归为 `236 passed`，前端全量测试为 `51 passed`。
- GirlAI 伙伴回合已接入标准化情绪与工作意图分类、低置信度中性策略、关怀工作选项和统一 `session_events` 恢复；回合预留使用 `turn_id` 幂等约束、90 秒租约和 attempt fencing，支持完成回放、并发冲突和中断后的过期接管。
- GirlAI 语音适配已提供标准化转写入口，转写回合复用文字伙伴流程；语音输出能力通过同回合状态声明，供应商能力不可用时保留文字回复并记录降级。
- 图表编辑器已支持 XLSX、XLS、CSV、JSON 导入，六类基础图表、字段聚合、PNG 导出、撤销重做和移动端操作；草稿使用用户作用域 `localStorage` 保存元数据并在两天后过期，项目 JSON 支持配置迁移，恢复后通过重新选择同名且字段一致的文件关联数据。
- 当前 Web 工作台的完整会话历史、模型选择、文件版本、性能面板等 UI 尚未完整迁移到 VS Code 原生 Webview。

- [架构文档](ARCHITECTURE.md)：FastAPI、Vue、StateGraph、统一状态和部署拓扑。
- [接口文档](INTERFACES.md)：认证、Agent、任务、Agent Host、State 和验证契约。
- [前端架构](FRONTEND.md)：Vue 路由、Pinia 状态、Agent 页面和 Vite 代理。
- `FRONTEND.md` 的“图表编辑器”章节：数据导入、浏览器缓存、项目 JSON 迁移和文件重新关联流程。
- [测试指南](TESTING.md)：Python、Vitest、Playwright 和 VS Code 扩展测试。
- [开发者指南](DEVELOPER_GUIDE.md)：环境初始化、启动、构建、迁移和排障流程。
- 游戏 AI PPT 真实生成 E2E：`tests/e2e/test_ppt_game_ai.e2e.spec.js`，覆盖临时用户注册、真实生成接口、领域化内容断言和 PPTX 下载。
- [项目规格](../specs/)：按功能保存的需求、设计和实施记录。
- [运行诊断与有界重试实测](CORE_REPAIR_EVALUATION_2026-09-08.md)：Core 候选诊断投影、rollback 证据保留和自动 repair 实测结果。
- `../specs/2026-08-28-stategraph-rag-orchestration/`：StateGraph RAG 编排的目标设计、迁移记录和任务清单；其中本地验证与完整多阶段生产接线仍待运行环境验收。
- `../specs/2026-08-29-vscode-local-validation-extension/`：Web 与 VS Code 双工作台 Agent Host SSD，包含需求、技术设计和实施任务清单。
- `../specs/2026-08-30-user-scoped-skills/`：系统、用户和工作区 Skills 的命名空间、用户隔离与跨工作台同步设计。
- `../specs/2026-08-31-multilanguage-generation-orchestration/`：多语言代码生成稳定性与 Orchestrator Core 重构主规格，统一生命周期、文件计划、执行预算、GenerationScheduler、产物成功门禁，以及 Python、TypeScript、Java、Go、Rust 的语言 Adapter、官方脚手架导入、Toolchain 自动探测和工作区 Profile 晋级门禁已实现；受约束代码合成控制面已完成动态 IR、策略路由、Core 计划投影、Profile/语言/脚手架能力桥接、FastAPI/Express/Go/Spring 独立 Stack Adapter，以及 V0-V6 分层验证、候选预算、确定性重排和最小诊断反馈，Spec-First 与增量生产分支已接入 Core。
- `../../docs/evolution/TASKS.md`：全项目演化任务索引、SSD 规范和第 156-161 轮运行时补扫记录。
- `../specs/2026-08-29-followup-module-state-migration/`：AICloud、GirlAI、Agent、Workflow 及兼容映射、归档和切换的后续模块迁移 SDD。
- GirlAI 接口、双写状态和真实验证说明分别见 `INTERFACES.md`、`ARCHITECTURE.md` 和 `DEVELOPER_GUIDE.md`。
- `../specs/2026-09-01-agent-model-context/`：Agent 会话模型配置、当前模型、调用统计和降级记录的后端 Checkpoint 管理设计。
- `../specs/2026-09-01-mobile-agent-interface/`：Agent Dashboard 手机端单列布局、会话抽屉和文件抽屉设计。
- `../specs/2026-09-03-girlai-companion-enhancement/`：GirlAI 纯对话伙伴回合、记忆、情绪意图和语音适配的需求、设计与实施计划。
- `../specs/2026-09-06-flutter-desktop-agent-client/`：Flutter Windows 桌面 Agent 客户端的需求、设计与实施计划；当前已完成工程骨架和认证基础层。

## 文档边界

- `.monkeycode/docs/` 保存当前项目知识和开发文档。
- `.monkeycode/specs/` 保存功能规格；部分规格目录受 Git 忽略规则影响，提交时需显式暂存。
- `docs/` 保存仓库历史演化记录和较早的专项报告，内容更新状态以本目录为准。
