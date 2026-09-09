# Chat 回答质量技术设计

## 1. 设计原则

沿用现有 `/chat`、SSE 流和 `File` 解析缓存，采用最小字段改动。联网模式使用字符串三态 `auto/on/off`，后端兼容旧的 `enable_search` 布尔值映射为 `on/off`。当前阶段仍由一个已选模型完成回答。

## 2. 请求契约

`CodeRequest` 增加 `search_mode: Literal['auto', 'on', 'off']`，默认 `auto`，保留 `enable_search` 读取兼容。`search_mode` 为 `on/off` 时优先于旧 `enable_search`；仅在 `auto` 时旧布尔值生效。前端只在用户选择了模型时传 `model`，深度模式传 `use_reasoning`，联网传 `search_mode`。

显式模型优先级为：请求中的非空 `model` > 后端 `select_model_for_prompt(prompt, use_reasoning, has_files)`。后端路由和流式恢复状态均允许空模型，避免 UI 默认值遮蔽自动选模。

## 3. 上下文阶段

`_build_context` 按历史、附件、搜索顺序构建上下文，通过回调和异步队列实时发送阶段事件，响应生成器关闭会取消上下文任务。普通附件通过 `asyncio.to_thread` 调用已有解析器，支持 TXT/MD/PY/JS/TS/JSON/YAML/YML/CSV/LOG、文本型 PDF、DOCX；图片沿用视觉理解。旧 DOC、扫描型 PDF OCR 和其他二进制格式留作后续能力，当前返回格式或空正文提示。错误同时进入上下文与结构化 warnings。

搜索策略：`on` 尝试搜索；`off` 跳过；`auto` 匹配问题时效性、明确联网意图，以及附件场景中的核查、核对、检索、搜索意图。查询使用最多 260 字符的问题和成功解析的真实附件名；正文只从前 2000 字符的前 30 行提取一个明确标注的公司、产品或标题字段，字段最多 60 字符，总查询上限 400 字符。复杂实体消歧留作后续增强。`search_with_sources` 返回上下文和网页来源，无来源或异常时显示失败提示。

`_build_context` 接受可选的异步或同步 stage callback，并在实际操作前后报告 `started/completed/failed/skipped`。流式调用收集并发送这些结构化事件；非流式调用收集 warnings。搜索系统 fallback 没有网页 URL 时状态为 failed/unavailable，不能伪报 completed。普通文件来源使用 `kind=file,title=filename`，网页来源使用 `title/url/snippet`。来源和 warnings 写入 `History.metadata_json`；历史 API 将其解析为 `metadata` 字段返回。

## 4. 文件缓存

解析正文后复用 `File.update_parse_cache` 和现有 TTL。缓存元数据增加 `parsed` 类型；解析结果为空视为失败并反馈。图片缓存路径保持不变。

## 5. 深度与后续联合回答

深度模式是后端自动选择 reasoning model 并使用 `REASONING_PROMPT`，当前适配器没有统一推理预算契约，因此本阶段不声称支持或传递独立推理预算。后续联合回答可在阶段事件中增加 `models` 和 `aggregation` 字段，但本阶段不调用多个模型。

## 6. 验证

### 搜索深度扩展

新增 `search_depth: Literal['shallow', 'multi'] = 'shallow'`，与联网模式、深度回答分别控制。浅搜索调用一轮搜索服务；多轮固定最多两轮，单轮服务内部仍可执行供应商回退。首轮有效来源的标题和摘要片段用于生成第二轮查询，保留原查询主题，采用确定性裁剪且总长最多 400 字符。首轮无来源或无可用文本则提前结束并提示，第二轮失败保留首轮上下文和来源。两轮原始文本按轮次进入上下文，来源按 URL 去重。

真实搜索修正：附件名和已提取实体放在问题摘要之前，实体部分最多 140 字符，为问题保留最多 260 字符。第二轮在前三个来源中按标题、摘要与原查询的词语交集数量降序选择，相同分数保留供应商顺序；此启发式只改善词语匹配，不代表语义相关性或时效性判断。验证记录应分别报告查询变化、来源新增数量和人工相关性观察。

搜索事件增加 `round`、`total_rounds`，前端显示第几轮搜索。输入控件的联网关闭或项目模式下禁用搜索深度；默认浅搜索。`search_depth` 贯穿前端请求和恢复状态、流式与非流式入口、历史 metadata。测试验证调用次数、第二次查询对首轮内容的依赖、失败保留、去重以及关闭搜索的优先级。

后端使用 pytest 验证模式优先级、来源、附件缓存与解析失败、阶段顺序及上下文取消；前端使用 Vitest 验证请求参数、自动和显式选模、来源展示及历史恢复。完成后执行前端构建和平台本地预览。外部搜索可用性、真实模型质量及成本对比需另行实测。
