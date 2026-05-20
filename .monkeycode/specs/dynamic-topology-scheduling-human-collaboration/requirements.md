# Requirements Document

## Introduction

CodingMatrix 使用 7B/9B 级别小模型生成大型项目时面临两个核心挑战：
1. 工程调度问题：分层并发生成导致同层文件之间"互相不知道对方输出"，产生接口对接错误
2. 模型能力问题：小模型在"全局架构合理性"上存在本质短板，无法独立做出高质量的设计决策

本需求文档定义两项互补性优化：动态拓扑调度和轻量级人机协作。

## Glossary

- **动态拓扑调度**: 基于依赖图的实时调度策略，保证任意文件生成时其所有上游代码已确定
- **依赖图**: 以待生成文件为节点，import/调用关系为有向边的图结构
- **就绪队列**: 依赖计数为 0 的文件集合，可并行执行
- **关键决策点**: 需求分析完成后、代码生成开始前的架构决策时机
- **架构巡检**: 生成完成后通过静态规则识别架构坏味的轻量级检查
- **全局约束**: 用户通过自然语言描述的技术栈偏好、架构模式、非功能约束

## Requirements

### Requirement 1: 动态拓扑调度核心机制

**User Story:** AS 系统, I want 基于依赖图的动态调度, so that 每个文件生成时能看到所有上游代码，杜绝接口猜测

#### Acceptance Criteria

1. WHEN 需求分析完成, 系统 SHALL 构建完整依赖图，以每个待生成文件为节点，import/调用关系为有向边
2. WHILE 生成过程运行, 系统 SHALL 维护实时就绪队列，包含所有依赖计数为 0 的文件
3. WHEN 文件加入就绪队列, 系统 SHALL 立即启动该文件的生成任务
4. WHEN 文件生成完毕, 系统 SHALL 遍历所有下游文件，将依赖计数减 1
5. IF 下游文件依赖计数变为 0, 系统 SHALL 立即将该文件加入就绪队列
6. WHILE 就绪队列非空或存在未完成文件, 系统 SHALL 持续执行调度循环

### Requirement 2: 依赖图构建与管理

**User Story:** AS 系统, I want 完整准确的依赖图, so that 调度决策基于真实的代码依赖关系

#### Acceptance Criteria

1. WHEN 依赖图构建启动, 系统 SHALL 解析架构规划中的文件列表和模块关系
2. WHILE 构建依赖图, 系统 SHALL 为每个文件节点计算初始依赖计数（上游文件数量）
3. IF 文件 A 引用文件 B, 系统 SHALL 在依赖图中建立 A → B 的有向边
4. WHILE 生成过程, 系统 SHALL 动态更新依赖图状态，反映已完成文件
5. WHEN 所有文件生成完成, 系统 SHALL 销毁依赖图实例

### Requirement 3: 并行执行与资源控制

**User Story:** AS 系统, I want 最大并行度且受控的资源使用, so that 生成效率最优且不超载

#### Acceptance Criteria

1. WHILE 执行就绪队列中的任务, 系统 SHALL 使用 asyncio.gather 实现并行执行
2. IF 就绪队列文件数超过并发上限, 系统 SHALL 按优先级选择部分文件执行
3. WHEN 并发任务数达到上限, 系统 SHALL 等待至少一个任务完成后再接受新任务
4. IF 任务执行失败, 系统 SHALL 记录失败状态，不影响其他任务执行
5. WHEN 任务失败, 系统 SHALL 将失败文件标记为阻塞状态，阻止下游文件就绪

### Requirement 4: 关键决策点提问

**User Story:** AS 用户, I want 在生成前被询问关键架构决策, so that 用 30 秒决策注入全局架构方向

#### Acceptance Criteria

1. WHEN 需求分析完成且代码生成开始前, 系统 SHALL 自动提炼 1-3 个架构假设
2. WHILE 提炼架构假设, 魔鬼代言人（GLM-Z1） SHALL 选择其最没有把握的决策点
3. WHEN 架构假设提炼完成, 系统 SHALL 以选择题形式向用户提问
4. IF 用户选择某个选项, 系统 SHALL 将该决策注入后续所有生成 prompt
5. IF 用户跳过提问, 系统 SHALL 使用魔鬼代言人的默认建议继续生成
6. WHEN 用户做出决策, 系统 SHALL 记录决策日志供后续追溯

### Requirement 5: 生成后架构优化建议

**User Story:** AS 用户, I want 生成完成后收到架构优化建议清单, so that 快速定位深层架构问题

#### Acceptance Criteria

1. WHEN 项目生成完成且通过测试, 系统 SHALL 启动轻量级架构巡检
2. WHILE 架构巡检执行, 系统 SHALL 应用静态规则检查架构坏味
3. IF 发现文件行数超过阈值, 系统 SHALL 生成拆分建议（如"order_service.py 800行，建议拆分")
4. IF 发现跨层调用或代码重复, 系统 SHALL 在建议清单中标注问题位置
5. WHEN 架构巡检完成, 系统 SHALL 输出只读优化建议清单，绝不自动修改代码
6. WHILE 输出建议清单, 系统 SHALL 为每条建议提供简要修复方案

### Requirement 6: 自然语言全局约束

**User Story:** AS 用户, I want 用自然语言自定义项目架构规则, so that 领域模板灵活适配特殊需求

#### Acceptance Criteria

1. WHEN 用户输入需求, 系统 SHALL 同时识别技术栈偏好、架构模式、非功能约束描述
2. WHILE 识别约束, 系统 SHALL 将自然语言描述转化为硬约束格式
3. WHEN 约束识别完成, 系统 SHALL 将约束注入后续所有生成 prompt
4. IF 用户描述"订单模块需要高并发，用 Redis 做库存扣减", 系统 SHALL 在订单模块生成时强制使用 Redis
5. IF 用户描述"所有 service 函数都用 async/await", 系统 SHALL 在所有 service 文件生成时检查 async 标记
6. WHILE 约束生效, 系统 SHALL 验证生成代码是否符合约束，IF 不符合则提示修正

### Requirement 7: 接口一致性验证

**User Story:** AS 系统, I want 动态拓扑调度的接口一致性保障可被验证, so that 调度策略效果可量化

#### Acceptance Criteria

1. WHEN 文件生成完成, 系统 SHALL 验证该文件对所有上游文件的 import 语句有效
2. IF import 目标文件尚未生成, 系统 SHALL 暂停当前文件生成，等待上游完成
3. WHILE 调度过程, 系统 SHALL 记录每个文件的等待时间和完成时间
4. WHEN 项目生成完成, 系统 SHALL 统计接口对接错误率，目标为 0%
5. IF 接口对接错误发生, 系统 SHALL 标记为调度异常并记录原因

### Requirement 8: 与现有架构集成

**User Story:** AS 系统, I want 动态拓扑调度集成到现有 orchestrator_generation.py, so that 改动最小化且不影响其他模块

#### Acceptance Criteria

1. WHEN 集成开始, 系统 SHALL 在 orchestrator_generation.py 中新增调度逻辑层
2. WHILE 集成, 系统 SHALL 保持现有 OrchestratorAgent 接口不变
3. WHEN 调用 OrchestratorAgent.generate, 系统 SHALL 自动选择调度策略（动态拓扑或静态分层）
4. IF 用户未指定调度策略, 系统 SHALL 默认使用动态拓扑调度
5. WHEN 集成完成, 系统 SHALL 确保所有现有测试通过