"""
Ephemeral Workflow - 临时上下文工作流

基于 API 请求链路的任务编排系统，通过临时上下文串联多个子任务，
无需数据库持久化存储。用户可导出工作流配置为 JSON，便于复用。

模块结构：
- task_decomposer: AI 任务分解器
- graph_validator: 任务图验证器
- executor: 工作流执行器
- state_machine: 内存状态机
- result_aggregator: 结果聚合器
- node_types: 任务节点类型实现
"""
