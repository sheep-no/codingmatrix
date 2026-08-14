# 演化路径文档

> 本目录存放 CodingMatrix 各核心子系统的未来演化路径规划。

## 文档列表

- [全项目演化路径清单](TASKS.md) - 全项目演化路径**总索引**（A-H 大系统，模块粒度），每条列出「演化什么→为什么→演成什么样→优先级」，Agent 与 H 组详情下沉到各演化文件
- [Agent 大系统演化路径](AGENT-EVOLUTION.md) - Agent 引擎（15 子系统 A1-A15）演化文件总览与子系统演化文件映射
- [Agent 引擎演化路径](AGENT-ENGINE.md) - 编排核心、角色体系、模型路由、验证闭环、RAG 链路（faiss 修复 + spec-first 数据入库）的拆分与演进规划
- [Agent 子系统详细推演 · 批1 主链路](AGENT-EVOLUTION-BATCH1.md) - A1 编排核心 / A2 生成路径 / A3 需求分析，含现状→目标→阶段→风险
- [Agent 子系统详细推演 · 批2 能力层](AGENT-EVOLUTION-BATCH2.md) - A4 上下文压缩 / A5 角色体系 / A6 模型路由 / A7 验证修复
- [Agent 子系统详细推演 · 批3 支撑层](AGENT-EVOLUTION-BATCH3.md) - A8-A15（测试/工具/学习记忆/RAG/依赖/适配/MCP/基础工具）
- [服务与工具层子系统详细推演](SERVICES-EVOLUTION.md) - H1-H14（原 G1-G14：AI Cloud 沙箱/工作流/文件上传/任务队列/认证/API Key/视觉/GirlAi/GitHub/Nginx/模型管理/MCP/守护监控/安全）
- [Agent 子系统详细推演 · 批1 主链路](AGENT-EVOLUTION-BATCH1.md) - A1 编排核心 / A2 生成路径 / A3 需求分析，含现状→目标→阶段→风险
- [Agent 子系统详细推演 · 批2 能力层](AGENT-EVOLUTION-BATCH2.md) - A4 上下文压缩 / A5 角色体系 / A6 模型路由 / A7 验证修复
- [Agent 子系统详细推演 · 批3 支撑层](AGENT-EVOLUTION-BATCH3.md) - A8-A15（测试/工具/学习记忆/RAG/依赖/适配/MCP/基础工具）
- [前端 Agent 界面演化路径](AGENT-FRONTEND.md) - 先修正三栏排版失衡（右栏固定宽、左栏分区），再演进为对话流，补齐行级 diff、多文件标签、目录树
- [PPT 生成功能演化路径](PPT-FEATURE.md) - 修复前后端字段失配（template_id/options）、拆分 2133 行 API 文件，再统一两套大纲逻辑、合并模板系统、接线 animation/layout/image_upgrader
- [Agent 上下文压缩机制演化路径](AGENT-CONTEXT-COMPRESSION.md) - 统一 token 估算口径、压缩结果持久化、阈值感知模型窗口，再接入 LLM 语义压缩、归一为 ContextCompressor，最终沉淀为跨会话记忆
- [项目注释规范化演化路径](COMMENT-NORMALIZATION.md) - 先消除误导性注释（常量/端点/字段与代码不一致），再定义注释规范接入 ruff/ESLint CI，最终注释即文档
- [图片生成功能演化路径](IMAGE-GENERATION.md) - 修复文生图缓存失效与占位端点，再归一 AI 生成/搜图/本地绘制为 ImageProvider，最终纳入 Agent 路由与 PPT 配图联动
- [AICode 对话接口与界面演化路径](CHAT.md) - 先更名对齐（code→chat，端点/文件/schema/前端统一且旧端点兼容），再接入会话语义压缩与动态模型路由，最终对话界面收敛为 Agent 统一入口

## 编写规范

- 每个子系统一份文档，聚焦「现状基线 → 演化目标 → 分阶段路径 → 风险依赖」
- 路径分四个阶段：拆分解耦 → 统一收敛 → 智能增强 → 平台化
- 每阶段包含明确验收标准，保证向后兼容
