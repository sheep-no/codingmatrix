# 模块详档：app/utils/pptx/ 工具包（第一百四十四轮，v1.145）

## 模块定位与状态判定

**PPT 工具包（13 文件 + templates/ 子包，约 5000 行）——按三态判定：一条活跃链 + 一个「仅导出未接入」面。** 消费入口仅两个：`app/api/v1/aiGeneratorPptx.py`（PPT 生成 API）+ `app/utils/visual/layout_decider.py`（PPT5 双轨体系下游）。

**三态划分（经全库 grep 逐一确认）**：

| 文件 | 状态 | 判定依据 |
|---|---|---|
| text_processor.py（223 行） | 活跃 | aiGeneratorPptx:45-46 导入 |
| image_search.py（294 行） | 活跃 | aiGeneratorPptx:48 import，:1481/:1489/:1500/:1534-1536 真实调用 |
| ppt_style.py（109 行） | 活跃 | aiGeneratorPptx:49 + layout_decider:463 |
| custom_template.py（1101 行） | 活跃 | aiGeneratorPptx:1919 上传端点延迟导入 |
| visual_modifier.py（300 行） | 活跃 | aiGeneratorPptx:1262/:1323 调用其两顶层函数 |
| modify_intent_parser.py（248 行） | 活跃（包内） | visual_modifier:30-33 引用 |
| ppt_modifier.py（214 行） | 活跃（包内） | visual_modifier:34 引用 |
| visual_analyzer.py（276 行） | 活跃（包内） | visual_modifier:29 引用 |
| slide_renderer.py（439 行） | 活跃（包内） | visual_analyzer:21 + visual_modifier:28 引用 |
| templates/base.py（226 行） | **半活跃** | TemplateConfig/TemplateCategory/SlideLayout 被 custom_template:14/:615 依赖；TemplateBase 仅 presets 继承 |
| templates/manager.py（218 行） | 未接入 | TemplateManager 仅 `__init__` 导出，`from app.utils.pptx import` 全库零消费 |
| templates/presets.py（369 行）+ presets/save_test.json | 未接入 | 5 套内置模板仅 manager 延迟导入，manager 本身不实例化 |
| layout_engine.py（25,860 字节） | 未接入 | LayoutOptimizer 仅 `__init__.py:5` 导出，外部零引用 |
| image_upgrader.py（52,637 字节） | 未接入 | ImageStrategy/ImageCacheManager 仅 `__init__.py:6` 导出，外部零引用 |
| animation_engine.py（18,941 字节） | 未接入 | AnimationEngine 等仅 `__init__.py:8` 导出，外部零引用 |

**关键判定**：`from app.utils.pptx import X` / `import app.utils.pptx` 全库零消费（所有消费方均深层 `from app.utils.pptx.<module> import`）→ **`__init__.py` 导出的 15 个符号（TemplateManager/LayoutOptimizer/ImageStrategy/AnimationEngine 等）运行时从不加载**。

## 活跃链缺陷清单

- **PPX1 [P2] 自定义模板上传端点「接线即崩」（DG1/SCT1/DR6 家族）**——aiGeneratorPptx.py:1925 `config = parser.parse(str(template_path))` 调用 `CustomTemplateParser.parse`，该类只有 `parse_template_file`（custom_template.py:32）→ **恒 AttributeError** → 上传端点 :1941 except 捕获后返回 `config: None`——**用户上传自定义模板的自动解析从未成功**。且 :1929 `_json.dump(config, ...)` 对 TemplateConfig dataclass 直接 json.dump 亦 TypeError（修 parse 后下一处即崩）。

- **PPX2 [P2] `_apply_colors_to_presentation` 主题色应用恒空操作**——custom_template.py:865-871：`theme_colors_el.findall(qn("a:srgbClr"))` 取得颜色元素列表后，对每个 `clr` 再 `clr.find(qn("a:srgbClr"))`（在 srgbClr 内部找 srgbClr 子元素）→ 恒 None → `val_el.set("val", ...)` 永不执行（且 break 在 if 内）——**应用模板配置时主题色从未真正写入**。应直接 `clr.set("val", color_map[i])`。影响：TemplateConverter.apply_config_to_presentation（:813）与 merge 路径的配色全部失效。

- **PPX3 [P2] PPT 视觉分析链「分析结果零消费」+ 预览图生成即弃**——visual_modifier.py `_analyze_target_slides`（:180-205）收集的 analysis（含视觉模型 deepseek-ai/DeepSeek-OCR 每页一次的调用结果）存入 `ModifyResult.analysis` 后**从不参与修改决策**（:106 apply_modifications 仅用 intent），docstring「结合视觉分析结果和修改意图，生成修改方案」名不符实——**视觉模型调用纯开销、输出无消费者**；`_generate_previews`（:207-231）渲染的 preview_images 在 `modify_ppt_visual` 返回 dict（:259-278）只报 `preview_count`，图片字节全部丢弃（Pillow 渲染白费）。

- **PPX4 [P2] 字号修改能力死链**——modify_intent_parser.py:127 三元表达式 `font_value if modify_type=="font" else color_value if modify_type=="color" else None` 只给 font/color 赋 property_value，**size 类型 property_value 恒 None** → ppt_modifier.py:124 `elif target.property_name=="size" and target.property_value:` 永不触发——「把字号改成 18pt」解析成功（modify_types 含 size）但执行端永远跳过，**字号修改意图从不生效**（解析端与执行端契约断裂）。

- **PPX5 [P3] ppt_modifier 目标元素过滤恒真**——:146-150 `element_type=="text"` 分支 `if para.font.size < Pt(24): return True; return True` 无条件放行；`_modify_slide`（:107-111）只遍历 has_text_frame 顶层形状（group/table/placeholders 变体不处理）——`element_type` 限定形同虚设，「把标题改成 X」会同时改到正文（font.size 判断不可靠）。

- **PPX9 [P3] `get_compatibility_score` 评分中断 + 字体检查错位**——custom_template.py:787 `layout.shapes[0]`：shapes 为空时 IndexError 逃逸（:784-791 无 try，score 卡在 +0.55）；且 `has_valid_font` 应检查遍历中的 `shape` 却硬编码 `layout.shapes[0]`——兼容性评分失真。

- **PPX10 [P3] image_search 缓存语义不一致 + 下载无大小限制**——`get_cached_image`（:208-216）只查 `cache_path.exists()` 不过期检查（过期仅 cleanup_cache 手动触发删除，**命中路径与过期路径语义不一致**）；`download_and_cache`（:218-237）`resp.read()` 无大小上限（大图全量入内存）；`FallbackImageSearch`（:146-148）恒用 `PLACEHOLDER_URLS.get("default")`，tech/business/minimal 三种占位模板从未使用。

- **PPX11 [P3] text_processor 中英文混排宽度计数失真 + 死函数**——`smart_split_line`（:40-95）CJK 字符按 1 计数（全角实际≈2 半角宽）→ 中英混排行溢出判断偏差；`prevent_text_overflow_simple`（:189-201）「兼容旧接口」但全库零消费（死函数）。

- **PPX12 [P3] `merge_configs` 类属性比较失真**——custom_template.py:1022/:1031 `custom_val != getattr(TemplateConfig, key, None)`：对**无 class 级默认值**的字段（template_id/name/name_zh/description/category）getattr 返回 None → custom_val != None 恒真 → 恒用 custom；对**有默认值**的字段比较的是类默认而非 base 实例值——合并语义两条路径都失真。

## 未接入面缺陷清单（按用户指示标注「未接入」，不逐条修复，接线或废弃时再处理）

- **PPX6 [P3 未接入] `__init__.py` 导出体系运行时零执行（能力未接线家族）**——`from app.utils.pptx import` / `import app.utils.pptx` 全库零消费，`__init__.py` 导入的 layout_engine（LayoutOptimizer 排版引擎）/ image_upgrader（ImageStrategy/ImageCacheManager 智能配图）/ animation_engine（AnimationEngine/AnimationPresets/TransitionEffect/EntranceEffect 动画系统）/ templates（TemplateManager）**运行时从不加载**。其中 image_upgrader 与 image_search.py 构成**两套图片搜索/缓存实现并存**（缓存目录同为 `./pptx_output/image_cache`，双轨家族收敛对象）。

- **PPX7 [P3 未接入] templates/manager + presets 未接线 + 测试残留**——TemplateManager/recommend_template 全库零消费，5 套内置模板（presets.py 369 行，商务/学术/路演/教育/简约）零使用；`presets/save_test.json`（「保存测试模板」测试残留数据）躺在生产目录。

- **PPX8 [P3 未接入] slide_renderer 顶层函数死 + 中文渲染豆腐块**——`render_slide_preview`/`get_slide_metadata` 被 visual_analyzer.py:21 import 但从未调用（仅用 SlideRenderer 类）；`render_all_previews` 全库零引用（死函数，死代码家族第 32 处）；且 `_draw_text`/`_draw_title`（:296-324）用 Pillow **默认字体**绘制——中文渲染为豆腐块（□），视觉模型只能看到色块+方块。

## 交叉确认

- aiGeneratorPptx.py 活跃消费点：text_processor（:45-46 含 `prevent_text_overflow as prevent_text_overflow_v2` 别名）/ image_search（:48，`get_image_search_manager` 单例 :1474-1487）/ ppt_style（:49，无本地副本——**ppt_style 是唯一模板数据源，无双轨**）/ visual_modifier（:1262/:1272/:1323/:1325）/ custom_template（:1919 上传端点，PPX1）
- aiGeneratorPptx 上传端点自身缺陷（本轮连带发现）：template_id 用 `custom_{user_id}_{uuid}`（:1906）但 :1962 列表查询用 `f"custom_{user_id}_"` 前缀过滤，可匹配；`./configs/ppt/custom_templates` 相对路径依赖 CWD（AIC1 家族）
- layout_decider.py:463 用 `PPTStyle()` 默认 modern 模板——layout_decider 与 aiGeneratorPptx 双轨共用 ppt_style（PPT5 已记双份实现，样式层已收敛到 ppt_style）
- custom_template.py:14 依赖 templates/base.py 的 TemplateConfig——base.py 通过此链实际活跃（manager/presets 非活跃）
- 前序详档关联：ppt_agent.md PPT5（模型/LLM 双份）本轮确认扩展到「图片搜索双实现」（image_search 活跃 vs image_upgrader 未接入）

## 测试状态

零专项测试。活跃链各模块均无单测；PPX1（接线即崩）与 PPX4（size 死链）均未被测试拦截。

## 修复建议

1. PPX1：aiGeneratorPptx.py:1925 改 `parse_template_file` + :1929 用 dataclasses.asdict 序列化
2. PPX2：`_apply_colors_to_presentation` 直接 `clr.set("val", ...)`（删除内层 find）
3. PPX3：删除 `_analyze_target_slides` 的视觉模型调用（保留元数据分析）或将 visual_description 纳入修改决策；`modify_ppt_visual` 返回 preview_images 字节
4. PPX4：parse 提取字号值（如 `(\d+)pt`）给 size 赋 property_value，或执行端允许 size 无值应用默认
5. PPX6-PPX8：未接入面按接线计划（layout_engine 接入生成链 / image_upgrader 与 image_search 二选一收敛 / TemplateManager 接线）或归档删除；save_test.json 移出生产目录
6. 活跃链小修：PPX5 元素过滤改基于 shape 占位符类型、PPX9 shapes[0] 改遍历 shape、PPX10 下载限流 + 命中过期检查

## 下轮候选

app/utils/pptx/ 已闭合。转 app/utils/visual/（3 文件，layout_decider 是 PPT5 双轨下游）或 app/api/v2/ 8 文件。
