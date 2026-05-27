# 工作流引擎 (Workflow Engine)

基于 DAG 的可视化工作流编排引擎，支持自然语言驱动的任务分解与自动化执行。

## 架构

```
自然语言请求 → TaskDecomposer (LLM) → TaskGraph → GraphValidator → WorkflowExecutor → 节点执行
```

## 节点类型（9 种）

| 类型 | 说明 | 关键参数 |
|------|------|----------|
| `web_search` | 网络搜索 | query, count, lang, with_summary |
| `code_execution` | 执行代码 | code, language, timeout |
| `chart_generation` | 生成图表 | chart_type, title, data, x_label, y_label |
| `file_processing` | 处理文件 | operation, path, content |
| `llm_call` | LLM 调用 | prompt, model, system_prompt, temperature, max_tokens, input_variable, output_variable |
| `conditional` | 条件分支 | variable, operator, value, true_branch, false_branch |
| `human_approval` | 人工审批 | prompt, options, default_option, timeout, input_variable |
| `http_request` | HTTP 请求 | url, method, headers, body, params, timeout |
| `data_transform` | 数据转换 | operation, input_variable, output_variable, config |

## 状态流转

```
pending → running → completed
                  → failed
                  → waiting_approval → completed
                                     → failed
                  → skipped (on_failure=skip)
```

| 状态 | 说明 |
|------|------|
| `pending` | 等待执行 |
| `running` | 执行中 |
| `completed` | 执行完成 |
| `failed` | 执行失败 |
| `waiting_approval` | 等待人工审批 |
| `skipped` | 已跳过（失败策略为 skip 时） |

## 重试机制

每个节点可配置重试策略：

```json
{
  "retry": {
    "max_retries": 3,
    "retry_delay": 1.0,
    "backoff_factor": 2.0
  },
  "on_failure": "fail"
}
```

- `max_retries`: 最大重试次数（0-5）
- `retry_delay`: 初始重试延迟（秒）
- `backoff_factor`: 退避因子（延迟倍增系数）
- `on_failure`: 失败策略 - `fail`（中断）/ `skip`（跳过继续）

## 条件分支

`conditional` 节点支持 12 种运算符：

`==`, `!=`, `>`, `>=`, `<`, `<=`, `in`, `not_in`, `contains`, `is_empty`, `is_not_empty`, `starts_with`, `ends_with`

分支通过 `true_branch` 和 `false_branch` 指定后续节点 ID 列表。

## 数据转换

`data_transform` 节点支持 12 种操作：

`map`, `filter`, `reduce`, `pick`, `rename`, `merge`, `template`, `sort`, `slice`, `flatten`, `unique`, `jsonpath`

## 资源限制（8C8G 环境）

| 参数 | 值 |
|------|-----|
| 最大并发节点数 | 4 |
| 单节点超时 | 300s |
| 工作流超时 | 1800s |
| 节点内存限制 | 512MB |

## API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/v1/workflow/execute` | POST | 自然语言执行工作流（流式 NDJSON） |
| `/api/v1/workflow/{id}/execute` | POST | 执行已导入的工作流 |
| `/api/v1/workflow/status/{id}` | GET | 获取工作流状态 |
| `/api/v1/workflow/import` | POST | 导入工作流 JSON |
| `/api/v1/workflow/export/{id}` | GET | 导出工作流 JSON |
| `/api/v1/workflow/{id}` | DELETE | 删除工作流 |
| `/api/v1/workflow/history` | GET | 获取历史记录 |

## 提示词管理

工作流分解提示词存放在 `skills/workflow-planner/system_prompt.md`，修改提示词无需改代码。

## 前端组件

| 组件 | 说明 |
|------|------|
| `Workflow.vue` | 工作流编排页面 |
| `EphemeralWorkflow.vue` | 临时工作流弹窗 |
| `WorkflowDAG.vue` | DAG 图可视化 |
| `WorkflowLogViewer.vue` | 执行日志查看器 |
