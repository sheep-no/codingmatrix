# Workflow Planner Skill

工作流任务分解技能，将自然语言请求分解为结构化任务图。

## 触发条件

当用户请求执行工作流、任务编排、多步骤自动化时触发。

## 使用方法

调用 `TaskDecomposer` 将自然语言分解为 `TaskGraph`。

## 支持的节点类型

| 类型 | 说明 | 关键参数 |
|------|------|----------|
| `web_search` | 网络搜索 | query, count, lang, with_summary |
| `code_execution` | 执行代码 | code, language, timeout |
| `chart_generation` | 生成图表 | chart_type, title, data |
| `file_processing` | 处理文件 | operation, path, content |
| `llm_call` | LLM 调用 | prompt, model, system_prompt, input_variable, output_variable |
| `conditional` | 条件分支 | variable, operator, value, true_branch, false_branch |
| `human_approval` | 人工审批 | prompt, options, timeout, input_variable |
| `http_request` | HTTP 请求 | url, method, headers, body, params |
| `data_transform` | 数据转换 | operation, input_variable, output_variable, config |

## 条件运算符

`==`, `!=`, `>`, `>=`, `<`, `<=`, `in`, `not_in`, `contains`, `is_empty`, `is_not_empty`, `starts_with`, `ends_with`

## 数据转换操作

`map`, `filter`, `reduce`, `pick`, `rename`, `merge`, `template`, `sort`, `slice`, `flatten`, `unique`, `jsonpath`

## 失败策略

- `fail` - 中断工作流（默认）
- `skip` - 跳过继续执行

## 重试配置

```json
{
  "retry": {
    "max_retries": 3,
    "retry_delay": 1.0,
    "backoff_factor": 2.0
  }
}
```

## 资源限制（8C8G 环境）

- 最大并发节点：4
- 节点超时：300s
- 工作流超时：1800s
- 节点内存限制：512MB
