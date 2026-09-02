# Project Documentation

- [架构文档](ARCHITECTURE.md)：系统结构、StateGraph 边界和请求流程。
- [接口文档](INTERFACES.md)：Agent API、State、workflow、retrieval 和 validation 契约。
- [开发者指南](DEVELOPER_GUIDE.md)：环境、测试命令和 StateGraph 开发约定。
- `../specs/2026-08-28-stategraph-rag-orchestration/`：StateGraph RAG 编排的目标设计、迁移记录和任务清单；其中本地验证与完整多阶段生产接线仍待运行环境验收。
- `../specs/2026-08-29-vscode-local-validation-extension/`：Web 与 VS Code 双工作台 Agent Host SSD，包含需求、技术设计和实施任务清单。
- `../specs/2026-08-30-user-scoped-skills/`：系统、用户和工作区 Skills 的命名空间、用户隔离与跨工作台同步设计。
- `../specs/2026-08-31-multilanguage-generation-orchestration/`：多语言代码生成稳定性与 Orchestrator Core 重构主规格，统一生命周期、文件计划策略、四级执行预算、产物提交、成功一致性门禁和 GenerationScheduler 已实现，入口渐进迁移继续推进；VS Code 本地验证作为配套子规格。
- `../../docs/evolution/TASKS.md`：全项目演化任务索引、SSD 规范和第 156-161 轮运行时补扫记录。
- `../specs/2026-08-29-followup-module-state-migration/`：AICloud、GirlAI、Agent、Workflow 及兼容映射、归档和切换的后续模块迁移 SDD。
- GirlAI 接口、双写状态和真实验证说明分别见 `INTERFACES.md`、`ARCHITECTURE.md` 和 `DEVELOPER_GUIDE.md`。
