# 临时工作流

## 需求

### 用户故事

1. 作为用户，我希望快速创建和执行一次性工作流
2. 作为用户，我希望导入/导出工作流定义
3. 作为用户，我希望查看工作流执行历史

## 设计

### API

| 端点 | 方法 | 描述 |
|------|------|------|
| /api/v1/workflow/execute | POST | 执行工作流 |
| /api/v1/workflow/status/{id} | GET | 状态查询 |
| /api/v1/workflow/import | POST | 导入 |
| /api/v1/workflow/{id}/execute | POST | 执行导入的 |
| /api/v1/workflow/export/{id} | GET | 导出 |
| /api/v1/workflow/{id} | DELETE | 删除 |
| /api/v1/workflow/history | GET | 历史列表 |
| /api/v1/workflow/history/{id} | GET | 历史详情 |
| /api/v1/workflow/history/{id} | DELETE | 删除历史 |

### 工作流格式

```json
{
  "nodes": [
    {"id": "1", "type": "search", "config": {"query": "..." }},
    {"id": "2", "type": "generate", "config": {"model": "qwen2.5"}}
  ],
  "edges": [
    {"from": "1", "to": "2"}
  ]
}
```

## 实现状态: 完成
