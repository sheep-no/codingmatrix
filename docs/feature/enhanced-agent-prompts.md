# 多模型 Agent 提示词增强

## 概述

本文档详细说明了多模型 Agent 提示词的增强方案，包括系统提示词、Orchestrator 协调器、各 Specialist Agent（架构师、前端工程师、后端工程师、代码审查员）的增强提示词设计。

## 增强要点

### 1. 系统提示词增强 (`project_generation/enhanced_system_prompt.md`)

**核心改进**：
- **角色能力明确化**：详细定义认知能力、技术专长、DevOps 能力
- **智能需求分析**：引入项目类型分类矩阵和复杂度评估
- **架构设计原则**：强调分层架构、松耦合、可测试性
- **质量保证体系**：完整的代码质量、安全、性能标准
- **多模型协作优化**：明确的模型路由策略和上下文管理

**关键技术特性**：
- 支持 10+ 种项目类型自动识别
- 包含 50+ 项技术栈选择指导原则  
- 定义完整的文件创建顺序和质量标准
- 集成安全最佳实践和性能优化指南

### 2. Orchestrator 协调器增强 (`orchestrator/enhanced_orchestrator_prompt.md`)

**核心改进**：
- **深度需求分析**：多维度需求理解（功能、约束、性能、安全）
- **项目复杂度评估**：简单/中等/复杂三级评估体系
- **架构决策矩阵**：技术栈选择的量化决策框架
- **任务分解模板**：标准化的全栈应用任务流
- **质量保证体系**：完整的验证策略和异常处理机制

**协作流程优化**：
- 明确的 Agent 分配规则和通信协议
- 完善的超时控制和并发限制
- 强化的错误恢复和状态持久化机制

### 3. Specialist Agent 增强

#### 架构师 (`enhanced_architect_prompt.md`)
- **输出格式标准化**：严格的 JSON Schema 定义
- **设计原则体系化**：技术选型、架构设计、API 设计、数据库设计四大原则
- **质量检查清单**：7 项关键质量检查点

#### 前端工程师 (`enhanced_frontend_engineer_prompt.md`)  
- **技术栈现代化**：Vue 3 Composition API / React 18 Hooks 优先
- **性能最佳实践**：懒加载、图片优化、API 优化等完整指南
- **安全考虑全面**：XSS 防护、CSRF 防护、CSP 实施
- **测试友好性**：组件隔离、Props 接口、Mock 支持

#### 后端工程师 (`enhanced_backend_engineer_prompt.md`)
- **安全最佳实践**：输入验证、SQL 注入防护、认证授权完整体系
- **性能优化指南**：数据库查询优化、缓存策略、异步处理
- **API 设计规范**：RESTful 最佳实践、状态码使用、版本控制
- **测试支持完善**：单元测试、集成测试、覆盖率目标

#### 代码审查员 (`enhanced_code_reviewer_prompt.md`)
- **审查维度全面**：安全性、正确性、可读性、性能、最佳实践五大维度
- **严重等级定义**：Low/Medium/High 三级风险评估体系
- **决策流程标准化**：基于风险等级的审批决策树
- **改进建议具体化**：提供具体的修复代码和实施步骤

## 使用方法

### 1. 文件结构
```
.claude/skills/
├── project_generation/
│   └── enhanced_system_prompt.md
└── orchestrator/
    ├── enhanced_orchestrator_prompt.md
    ├── enhanced_architect_prompt.md  
    ├── enhanced_frontend_engineer_prompt.md
    ├── enhanced_backend_engineer_prompt.md
    └── enhanced_code_reviewer_prompt.md
```

### 2. 加载机制
通过 `app/utils/prompt_loader.py` 中的增强加载函数自动加载：

```python
# 系统提示词
load_project_generation_prompt(output_dir, tools_description)

# Orchestrator 提示词  
load_orchestrator_prompt()

# Specialist Agent 提示词
load_architect_prompt()
load_frontend_engineer_prompt() 
load_backend_engineer_prompt()
load_code_reviewer_prompt()
```

### 3. 配置优先级
- 默认使用增强版提示词
- 如果增强版提示词文件不存在，回退到原始提示词
- 支持动态切换提示词版本（通过配置参数）

## 预期效果

### 质量提升
- **代码正确性**：减少语法错误和逻辑错误 50%+
- **安全性**：自动识别和防护常见安全漏洞
- **可维护性**：代码结构更清晰，注释更完整
- **性能**：自动生成性能优化的代码

### 效率提升  
- **生成速度**：通过多模型协作提升生成效率
- **成功率**：减少生成失败和重试次数
- **一致性**：确保不同 Agent 生成的代码风格一致

### 用户体验
- **交互更自然**：更好的需求理解和上下文保持
- **错误恢复**：自动从错误中恢复并继续生成
- **进度透明**：清晰的生成进度和状态反馈

## 维护建议

### 1. 提示词更新
- 定期根据用户反馈优化提示词内容
- 添加新的技术栈和最佳实践
- 更新安全防护措施和性能优化指南

### 2. 性能监控  
- 监控提示词加载和解析性能
- 跟踪生成成功率和质量指标
- 优化大提示词的 token 使用效率

### 3. 版本管理
- 使用语义化版本管理提示词变更
- 保持向后兼容性
- 提供提示词版本切换选项

## 未来扩展

### 1. 动态提示词
- 根据项目类型动态生成提示词
- 基于用户历史偏好个性化提示词
- 实时学习和优化提示词效果

### 2. 多语言支持
- 扩展支持更多编程语言的提示词
- 国际化提示词内容
- 本地化最佳实践指南

### 3. 领域专业化
- 针对特定领域（金融、医疗、游戏等）的专用提示词
- 行业合规性检查集成
- 领域特定的安全和性能要求