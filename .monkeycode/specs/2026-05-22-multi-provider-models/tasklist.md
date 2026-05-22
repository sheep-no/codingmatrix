# Implementation Task List

Feature: multi-provider-models
Created: 2026-05-22
Status: In Progress

---

## Task 1: 创建供应商配置和枚举

- [x] 1.1 创建 `ModelProvider` 枚举类（SiliconFlow、DashScope、Zhipu、DeepSeek、OpenAI、Anthropic、Ollama）
- [x] 1.2 创建 `ProviderConfig` 数据类（api_key、base_url、timeout、enabled）
- [x] 1.3 更新 `app/core/config.py` 添加多供应商环境变量支持
- [x] 1.4 编写单元测试验证配置加载

## Task 2: 创建供应商路由器

- [x] 2.1 创建 `ProviderRouter` 类实现模型到供应商的映射
- [x] 2.2 实现故障转移逻辑（`get_fallback_providers()`）
- [x] 2.3 创建单例模式和全局访问函数
- [x] 2.4 编写单元测试验证路由和故障转移

## Task 3: 创建供应商适配器基类

- [x] 3.1 创建 `BaseProviderAdapter` 抽象基类
- [x] 3.2 实现统一调用接口 `call_llm()`
- [x] 3.3 实现消息构建和响应解析方法
- [x] 3.4 编写单元测试验证基类功能

## Task 4: 实现具体供应商适配器

- [x] 4.1 创建 `SiliconFlowAdapter`（复用现有逻辑）
- [x] 4.2 创建 `DashScopeAdapter`（阿里百炼）
- [ ] 4.3 创建 `ZhipuAdapter`（智谱 GLM）
- [ ] 4.4 创建 `DeepSeekAdapter`（DeepSeek 官方）
- [x] 4.5 创建 `OpenAIAdapter`
- [ ] 4.6 创建 `AnthropicAdapter`（可选）
- [ ] 4.7 编写适配器单元测试

## Task 5: 创建统一调用函数

- [x] 5.1 创建 `app/utils/aicloud/llm_caller.py`
- [x] 5.2 实现 `call_llm()` 统一函数
- [ ] 5.3 实现故障转移和重试逻辑
- [ ] 5.4 保持 `call_siliconflow()` 向后兼容
- [ ] 5.5 编写集成测试

## Task 6: 更新 Agent 使用新架构

- [ ] 6.1 更新 `app/agent/specialist_base.py` 使用 `call_llm()`
- [ ] 6.2 更新 `app/agent/multi_model_agent.py` 导入新函数
- [ ] 6.3 更新 `app/utils/vision.py` 使用视觉模型适配器
- [ ] 6.4 验证 Agent 能调用不同供应商的模型
- [ ] 6.5 编写 Agent 集成测试

## Task 7: 文档和测试

- [ ] 7.1 创建 `docs/MULTI_PROVIDER_SETUP.md` 配置指南
- [ ] 7.2 更新 `docs/architecture/MODELS.md` 添加供应商信息
- [ ] 7.3 更新 `.env.example` 添加新供应商配置示例
- [ ] 7.4 运行所有测试确保通过

---

## Notes

- 向后兼容性是关键：现有 `call_siliconflow()` 必须继续工作
- 所有 API Key 不得在日志中明文输出
- 故障转移不应无限重试（最多 3 次）

## Prerequisites

- 现有 SiliconFlow 调用逻辑正常工作
- Python 3.10+ 环境
- 各供应商 API Key（测试用）
