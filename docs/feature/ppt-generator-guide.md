# PPT 生成指南

## 概述

CodingMatrix 支持 AI 驱动的 PPT 生成，用户只需提供主题，系统自动生成完整演示文稿。

## API 端点

| 端点 | 方法 | 描述 |
|------|------|------|
| `/api/v1/pptx/generate` | POST | 同步生成 (阻塞) |
| `/api/v1/pptx/generate_task` | POST | 异步任务 (推荐) |
| `/api/v1/pptx/download/{ppt_id}` | GET | 下载 PPT |
| `/api/v1/pptx/preview/{ppt_id}` | GET | 在线预览 |
| `/api/v1/pptx/{ppt_id}/slides` | GET | 幻灯片列表 |
| `/api/v1/pptx/{task_id}/cancel` | DELETE | 取消任务 |
| `/api/v1/pptx/{task_id}/update` | POST | 更新任务 |

## 生成流程

```
用户输入主题 -> LLM 生成大纲 -> LLM 填充内容 -> python-pptx 渲染 -> 返回 PPT 文件
```

## 请求示例

```json
{
  "topic": "AI 技术发展趋势",
  "slides_count": 10,
  "style": "modern",
  "language": "zh"
}
```

## 生成内容

每页幻灯片包含:
- 标题
- 正文内容 (要点列表)
- 可选图片/图表
- 演讲者备注

## 技术栈

- **LLM**: SiliconFlow API (生成内容)
- **PPT 库**: python-pptx (渲染文件)
- **异步**: APScheduler (后台任务)
- **预览**: 浏览器内渲染
