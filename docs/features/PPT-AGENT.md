# PPT Agent - 智能演示文稿生成

> 最后更新：2026-05-29 | 版本：v5.11.0

## 功能概述

PPT Agent 是一个基于 AI 的智能演示文稿生成系统，支持从自然语言描述自动生成结构化的 PPT 大纲，并自动完成排版、配图和文件生成。

## 核心功能

### 1. 自然语言生成 Agent

输入简单的主题或描述，AI 自动理解需求并生成结构化大纲。

**使用方式**：
- 前端：选择"AI Agent 生成"模式，输入主题描述
- API：调用 `POST /api/v1/ppt/generate-text` 端点

**示例输入**：
```
帮我做一个关于 2026 年人工智能发展趋势的技术汇报，包含市场分析、技术突破、应用场景和未来展望
```

**生成的大纲结构**：
```json
{
  "title": "2026年人工智能发展趋势",
  "slides": [
    {
      "type": "title",
      "title": "2026年人工智能发展趋势",
      "bullets": [],
      "image_keywords": ["AI", "technology"]
    },
    {
      "type": "content",
      "title": "市场分析",
      "bullets": ["全球AI市场规模突破5000亿美元", "中国AI产业增速达35%"],
      "image_keywords": ["market", "growth"]
    }
  ]
}
```

### 2. 文本防溢出

自动处理长文本，防止内容溢出幻灯片边界。

**处理策略**：
- **自动换行**：超过 70 字符的行自动拆分
- **行数限制**：每页最多 6 行内容
- **字号建议**：超出时建议缩小字号
- **截断处理**：超出部分显示 "... (已省略超出部分)"

**实现位置**：`app/api/v1/aiGeneratorPptx.py:prevent_text_overflow()`

### 3. 自动搜图配图

根据幻灯片内容的关键词自动搜索并插入图片。

**工作流程**：
1. 从大纲中提取 `image_keywords`
2. 使用 DuckDuckGo 搜索图片
3. 下载并缓存到本地 (`./static/images/cache/`)
4. 自动插入到幻灯片右侧区域

**配置**：
- 每页最多搜索 2 个关键词
- 图片缓存使用 MD5 哈希作为文件名
- 超时时间：10 秒

### 4. 智能排版布局

根据内容类型自动选择最佳版式。

**布局规则**：
- **封面页**：居中标题 + 副标题 + 装饰框
- **内容页**：左侧标题 + 右侧配图 + 下方要点列表
- **章节页**：大标题 + 目录列表
- **结束页**：居中"谢谢" + 装饰

**配图位置**：右侧 (9, 2) 英寸，尺寸 3.5x2.5 英寸

## API 端点

### 1. 生成大纲（仅返回结构化数据）

```
POST /api/v1/ppt/generate-text
```

**请求参数**：
```json
{
  "topic": "PPT 主题",
  "description": "详细描述（可选）",
  "num_slides": 10,
  "model": "Qwen/Qwen2.5-7B-Instruct"
}
```

**响应**：
```json
{
  "title": "PPT 标题",
  "slides": [...],
  "total_slides": 10
}
```

### 2. 端到端生成（大纲 -> 搜图 -> PPTX）

```
POST /api/v1/ppt/generate-from-text
```

**请求参数**：同上

**响应**：
```json
{
  "task_id": "uuid",
  "task_type": "ppt_generation",
  "status": "pending",
  "progress": 0,
  "progress_message": "等待中..."
}
```

### 3. 查询任务状态

```
GET /api/v1/tasks/{task_id}
```

**响应**：
```json
{
  "task_id": "uuid",
  "status": "completed",
  "progress": 100,
  "result_data": {
    "filename": "uuid.pptx",
    "download_url": "/api/v1/pptx/download/uuid?format=pptx",
    "preview_url": "/api/v1/pptx/preview/uuid"
  }
}
```

## 文件结构

```
app/
├── agent/
│   └── ppt_agent.py              # PPT Agent 核心逻辑
├── api/v1/
│   └── aiGeneratorPptx.py        # API 端点 + 渲染逻辑 + 防溢出 + 搜图
└── utils/
    └── visual.py                  # 视觉决策模块

src/views/
└── PPTGenerate.vue                # 前端 UI (支持 Agent/手动模式切换)
```

## 配置选项

### 模板风格

支持 8 种预设模板：

| 模板 | 主色调 | 字体 | 适用场景 |
|------|--------|------|----------|
| modern | #2563eb | Arial | 现代简约 |
| business | #1e40af | Georgia | 商务专业 |
| creative | #dc2626 | Verdana | 创意设计 |
| minimal | #000000 | Helvetica | 极简主义 |
| academic | #0369a1 | Times New Roman | 学术研究 |
| tech | #3b82f6 | Consolas | 科技蓝调 |
| education | #16a34a | Comic Sans MS | 教育培训 |
| medical | #059669 | Arial | 医疗健康 |

### 幻灯片类型

| 类型 | 说明 | 示例用途 |
|------|------|----------|
| title | 封面页 | 第一页 |
| chapter | 章节页 | 目录、分节 |
| content | 内容页 | 主体内容 |
| bullet | 要点页 | 列表说明 |
| image | 图片页 | 展示图片 |
| chart | 图表页 | 数据可视化 |
| end | 结束页 | 最后一页 |

## 使用示例

### 前端使用

1. 访问 PPT 生成页面
2. 选择"AI Agent 生成"模式
3. 输入主题：`帮我做一个关于 Python 异步编程的技术分享`
4. 设置页数：10
5. 点击"一键生成 PPT"
6. 等待生成完成，下载 PPTX 文件

### API 调用

```bash
# 生成大纲
curl -X POST "http://localhost:3000/api/v1/ppt/generate-text" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "topic": "Python 异步编程最佳实践",
    "num_slides": 8
  }'

# 端到端生成
curl -X POST "http://localhost:3000/api/v1/ppt/generate-from-text" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "topic": "Python 异步编程最佳实践",
    "num_slides": 8
  }'
```

## 注意事项

1. **API Key 配置**：使用前需在设置页面配置 SiliconFlow API Key
2. **生成时间**：端到端生成约需 30-60 秒（含搜图时间）
3. **图片搜索**：依赖外部网络，可能受网络状况影响
4. **缓存机制**：搜图结果会缓存，相同关键词不会重复搜索
5. **文件清理**：生成的 PPTX 文件保存在 `./pptx_output/` 目录

## 相关文档

- [项目功能介绍](PROJECT-INTRODUCTION.md) - 整体功能概览
- [API 文档](../api/API-DOCUMENTATION.md) - 完整 API 端点
- [Agent 功能](AGENT.md) - Agent 协作开发
- [架构设计](../architecture/ARCHITECTURE.md) - 系统架构
