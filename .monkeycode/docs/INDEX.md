# CodingMatrix 项目文档

- [架构文档](ARCHITECTURE.md)：FastAPI、Vue、StateGraph、统一状态和部署拓扑。
- [接口文档](INTERFACES.md)：认证、Agent、任务、Agent Host、State 和验证契约。
- [前端架构](FRONTEND.md)：Vue 路由、Pinia 状态、Agent 页面和 Vite 代理。
- [测试指南](TESTING.md)：Python、Vitest、Playwright 和 VS Code 扩展测试。
- [开发者指南](DEVELOPER_GUIDE.md)：环境初始化、启动、构建、迁移和排障流程。
- [项目规格](../specs/)：按功能保存的需求、设计和实施记录。
- `../specs/2026-08-28-stategraph-rag-orchestration/`：StateGraph RAG 编排的目标设计、迁移记录和任务清单；其中本地验证与完整多阶段生产接线仍待运行环境验收。
- `../specs/2026-08-29-vscode-local-validation-extension/`：Web 与 VS Code 双工作台 Agent Host SSD，包含需求、技术设计和实施任务清单。
- `../specs/2026-08-30-user-scoped-skills/`：系统、用户和工作区 Skills 的命名空间、用户隔离与跨工作台同步设计。
- `../../docs/evolution/TASKS.md`：全项目演化任务索引、SSD 规范和第 156-161 轮运行时补扫记录。
- `../specs/2026-08-29-followup-module-state-migration/`：AICloud、GirlAI、Agent、Workflow 及兼容映射、归档和切换的后续模块迁移 SDD。
- GirlAI 接口、双写状态和真实验证说明分别见 `INTERFACES.md`、`ARCHITECTURE.md` 和 `DEVELOPER_GUIDE.md`。
- `../specs/2026-09-01-agent-model-context/`：Agent 会话模型配置、当前模型、调用统计和降级记录的后端 Checkpoint 管理设计。
- `../specs/2026-09-01-mobile-agent-interface/`：Agent Dashboard 手机端单列布局、会话抽屉和文件抽屉设计。

## 文档边界

- `.monkeycode/docs/` 保存当前项目知识和开发文档。
- `.monkeycode/specs/` 保存功能规格；部分规格目录受 Git 忽略规则影响，提交时需显式暂存。
- `docs/` 保存仓库历史演化记录和较早的专项报告，内容更新状态以本目录为准。
