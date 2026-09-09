# PPT 模板现状分析

## 模板注册与渲染

`app/utils/pptx/templates/manager.py` 在初始化时注册 9 个内置模板。模板由 `TemplateConfig` 描述颜色、字体、尺寸、布局和版本化 design tokens；`aiGeneratorPptx.py` 的渲染器按 `style.template_name` 选择 academic、business、pitch、modern 等渲染函数，随后通过 `TemplateManager.resolve_design_tokens()` 应用令牌。

## 模板选择接入状态

本次新增的 `TemplateManager.select_template()` 当前只有单元测试调用，生产业务入口仍使用 `resolve_topic_template()`，模板推荐 API 直接调用 `recommend_for_scenario()`。因此该选择接口尚未接入生成流程，无法改变现有生成行为；后续接入需要统一显式模板、别名和自动场景选择的优先级。

## 已知缺口

- 注册能力存在，`register()` 只支持进程内注册；自定义模板保存/加载与渲染入口之间仍需要明确生命周期。
- 内置模板有配置和渲染实现，布局枚举也已定义；各模板的布局配置尚未形成前端可消费的统一缩略图描述。
- 前端目前缺少与模板注册表对应的模板缩略图资源和稳定的预览数据接口，因此模板选择界面无法完整展示真实布局效果。
- design tokens 已支持版本字段，但生成入口仍把部分主题别名映射到旧式 `PPTStyle`，存在两套选择语义。

## 范围结论

当前只保留分析，不扩大模板实现范围。下一阶段应先统一生成入口的模板选择协议，再补充模板预览元数据和前端缩略图，最后验证自定义模板的持久化与成品渲染一致性。
