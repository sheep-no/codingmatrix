# PPT Agent - 智能演示文稿生成

> 最后更新：2026-09-03

PPT Agent 将主题、大纲、素材、渲染和质量检查组织为可追踪的生成流程。主 API 位于 `app/api/v1/aiGeneratorPptx.py`，当前前端采用“配置、大纲审阅、批准生成”三步交互。

## 推荐工作流

1. 调用 `POST /api/v1/pptx/outlines` 创建用户作用域的大纲草稿。
2. 使用 `PATCH /api/v1/pptx/outlines/{outline_id}` 编辑标题、页面及排序；每次更新产生新版本。
3. 调用 `POST /api/v1/pptx/outlines/{outline_id}/approve` 批准当前版本。
4. 调用 `POST /api/v1/pptx/outlines/{outline_id}/generate`，从已批准快照创建异步任务。
5. 读取任务状态、预览或下载产物，并通过质量报告查看逐页问题和修复记录。
6. 需要调整单页时，调用页面重生成接口生成新的已批准版本和任务。

生成接口会拒绝尚未批准的大纲。大纲读取、修改、生成和质量报告均按用户所有权隔离。

## 大纲与质量 API

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/pptx/outlines` | 创建大纲草稿 |
| GET | `/api/v1/pptx/outlines/{outline_id}` | 读取当前或指定版本 |
| PATCH | `/api/v1/pptx/outlines/{outline_id}` | 创建编辑版本 |
| POST | `/api/v1/pptx/outlines/{outline_id}/approve` | 批准当前版本 |
| POST | `/api/v1/pptx/outlines/{outline_id}/generate` | 从已批准快照生成 |
| POST | `/api/v1/pptx/outlines/{outline_id}/slides/{slide_id}/regenerate` | 重生成指定页面 |
| GET | `/api/v1/pptx/{task_id}/quality-report` | 获取质量报告 |

`OutlineDraft` 的页面语义包含 `slide_type`、`narrative_role`、`key_message`、`content_blocks`、`asset_intent` 和 `evidence_sources`。语义规划器使用容量预算和布局候选控制页面密度，渲染器为页面生成稳定的语义元数据。

## 生成编排

Celery 任务按以下阶段推进：

```text
planning -> assets -> rendering -> rule_qa -> reflow -> vision_qa -> completed
```

- `planning`：读取批准的大纲并准备页面计划。
- `assets`：准备页面所需素材。
- `rendering`：生成 PPTX 和页面元数据。
- `rule_qa`：执行确定性规则检查。
- `reflow`：根据问题自动调整布局并记录修复动作。
- `vision_qa`：`refined` 质量模式可调用视觉 reviewer；复审不可用时记录降级阶段和问题。
- `completed`：保存质量报告、状态和产物引用。

阶段名称代表任务状态边界；具体任务中部分阶段可仅转交状态或复用既有产物。

## 质量报告

质量报告包含：

- 总体分数和逐页分数。
- 规则或视觉检查发现的问题。
- reflow 尝试与修复动作。
- 质量模式、状态和发生降级的阶段。
- 关联的大纲 ID 与版本。

质量检查先运行确定性规则和自动 reflow，`refined` 模式随后追加视觉复审。

## 主题与模板

渲染代码提供 9 种主题：

`academic`、`business`、`creative`、`education`、`elegant`、`medical`、`modern`、`minimal`、`tech`。

`app/utils/pptx/templates/presets.py` 维护 5 套专业模板预设。模板预设负责可复用模板配置，渲染主题负责页面视觉令牌，两者数量和用途各自独立。

## 兼容接口

系统继续保留早期生成和文件操作入口：

- `POST /api/v1/generate-text`
- `POST /api/v1/generate-from-text`
- `POST /api/v1/pptx/generate_task`
- `POST /api/v1/pptx/generate`
- `GET /api/v1/pptx/download/{ppt_id}`
- `GET /api/v1/pptx/preview/{ppt_id}`
- `GET /api/v1/pptx/{ppt_id}/slides`
- `DELETE /api/v1/pptx/{task_id}/cancel`
- `POST /api/v1/pptx/{task_id}/update`
- `POST /api/v1/pptx/{task_id}/modify`
- `GET /api/v1/pptx/{task_id}/analyze`
- 模板、历史、文件生成、自定义模板、PDF 下载和 WebSocket 进度接口。

新功能应优先采用版本化大纲工作流，以获得批准门禁、质量报告和单页重生成能力。

## 前端

- `src/views/PPTGenerate.vue`：配置生成参数、编辑和排序大纲、批准后选择质量模式并创建任务。
- `src/views/PPTPreview.vue`：预览页面，展示总分、逐页分数、问题、修复动作和单页重生成入口。
- `src/utils/api/ppt.js`：封装 PPT API。

## 运行与依赖

- PPTX 生成依赖 `python-pptx` 和 Pillow。
- 产物默认写入 `./pptx_output`；生产 Compose 使用 `ppt-artifacts:/app/pptx_output` 在 API 与 Celery Worker 间共享文件。
- PDF 接口的实际 PPT 转换只调用 LibreOffice；缺少 LibreOffice 时返回 HTTP 501。Poppler 可用于 PDF 后处理，但不能替代该转换命令。当前 `Dockerfile` 与 Compose 定义未安装 LibreOffice。
- 图片搜索和视觉复审依赖外部服务可用性，失败会影响素材或质量阶段，任务状态和报告用于呈现结果。

## 相关文件

- `app/schema/ppt_outline.py`
- `app/services/ppt_state_service.py`
- `app/services/ppt_generation_orchestrator.py`
- `app/services/ppt_quality_orchestrator.py`
- `app/tasks/ppt_tasks.py`
- `app/utils/pptx/semantic_planner.py`
- `app/utils/pptx/semantic_renderer.py`
- `app/utils/pptx/quality.py`
- `app/utils/pptx/design_tokens.py`
