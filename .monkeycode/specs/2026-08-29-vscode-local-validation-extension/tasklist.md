# VS Code 本地验证插件实施任务清单

## 阶段 1：协议与契约

### VSCODE-001 验证动作与结果 Schema

- 状态：`completed`
- 优先级：`P0`
- 修改：插件协议模型、云端 StateGraph 验证契约
- 消费：VS Code 插件、`app/agent/nodes/validation.py`
- 契约：`PendingAction`、`LocalValidationResult`、`MessageEnvelope`
- 测试：动作解析、版本、scope 和结果序列化测试
- 验证范围：`cloud_syntax` + `local_runtime`
- 验收证据：`npm --prefix vscode-extension test` 通过（6/6），覆盖 Schema round-trip、非法 scope 拒绝、未知版本错误和工作区越界路径校验。

### VSCODE-002 插件连接与认证

- 状态：`completed`
- 优先级：`P0`
- 修改：插件连接层、云端插件接入 API
- 消费：PendingAction 拉取、结果回传和连接状态视图
- 契约：认证会话、Envelope、task/revision/event 标识
- 测试：连接、重连、断线缓存和认证失败测试
- 验证范围：`cloud_syntax` + `local_runtime`
- 验收证据：`npm --prefix vscode-extension test` 通过（10/10），覆盖 Bearer 认证、认证失败不重试、临时错误重试、断线结果缓存和恢复回传。

## 阶段 2：本地执行与安全

### VSCODE-003 工作区授权与路径校验

- 状态：`completed`
- 优先级：`P0`
- 修改：插件工作区授权和动作校验模块
- 消费：所有本地验证动作
- 契约：workspace identity、路径规范化、授权状态
- 测试：授权、撤销、工作区外路径、符号链接和多工作区测试
- 验证范围：`local_runtime`
- 验收证据：`npm --prefix vscode-extension test` 通过（15/15），覆盖授权路径、多工作区、绝对路径、未知工作区、父目录遍历、符号链接越界和授权撤销。

### VSCODE-004 验证执行器

- 状态：`planned`
- 优先级：`P0`
- 修改：插件 ValidationRunner
- 消费：依赖检查、构建、单元测试、E2E 和服务检查动作
- 契约：operation 白名单、命令参数数组、timeout、cancel
- 测试：成功、非零退出、超时、取消、输出上限和进程树清理测试
- 验证范围：`local_runtime` + `local_e2e`
- 验收证据：每种终止状态均能生成确定性结果，不残留子进程。

### VSCODE-005 结果脱敏与本地缓存

- 状态：`planned`
- 优先级：`P0`
- 修改：插件 ResultSanitizer、ResultStore
- 消费：结果回传和断线恢复
- 契约：LocalValidationResult、脱敏字段和本地缓存记录
- 测试：密钥、密码、Cookie、连接串、环境变量和多行日志测试
- 验证范围：`local_runtime`
- 验收证据：敏感信息进入阻断路径，断线结果可恢复且不重复提交。

## 阶段 3：云端合并与状态闭环

### VSCODE-006 本地结果适配与 revision 门禁

- 状态：`in_progress`
- 优先级：`P0`
- 修改：`app/agent/local_validation_adapter.py`、相关测试和插件适配层
- 消费：StateReducer、ValidationNode、插件结果提交
- 契约：task、revision、schema version、scope、source
- 测试：`tests/unit/test_local_validation_adapter.py`、revision 冲突和幂等测试
- 验证范围：`cloud_syntax` + `local_runtime`
- 验收证据：现有专项测试已覆盖本地 scope、身份校验和终态推导；插件真实 E2E 待补充。

### VSCODE-007 多验证范围终态推导

- 状态：`planned`
- 优先级：`P1`
- 修改：`app/agent/nodes/validation.py`、StateGraph 状态测试
- 消费：插件回传的 `local_runtime` 和 `local_e2e` 结果
- 契约：PendingAction、ValidationResult、terminal status policy
- 测试：部分完成、全部通过、失败、重复结果和过期结果测试
- 验证范围：`cloud_syntax` + `local_runtime` + `local_e2e`
- 验收证据：必需 scope 全部通过后才产生 `completed`。

### VSCODE-008 断线恢复与 checkpoint

- 状态：`planned`
- 优先级：`P1`
- 修改：插件 ResultStore、云端 session/checkpoint 适配
- 消费：重连、sequence replay 和 snapshot recovery
- 契约：Checkpoint、MessageEnvelope、sequence、event_id
- 测试：断线、重启、序列缺口、snapshot recovery 和重复回传测试
- 验证范围：`local_runtime`
- 验收证据：插件重启后可恢复待回传结果，云端保持幂等。

## 阶段 4：VS Code 体验与发布

### VSCODE-009 验证任务与诊断界面

- 状态：`planned`
- 优先级：`P1`
- 修改：插件 StatusView、通知、诊断和取消交互
- 消费：动作状态、执行进度和结果摘要
- 契约：状态枚举、诊断位置、用户确认操作
- 测试：授权、进度、取消、失败和拒绝界面 E2E 测试
- 验证范围：`local_e2e`
- 验收证据：真实 VS Code 工作区中可完成完整验证闭环。

### VSCODE-010 版本兼容与发布验收

- 状态：`planned`
- 优先级：`P1`
- 修改：插件 manifest、协议协商和发布流水线
- 消费：云端版本检查、旧任务恢复和升级提示
- 契约：schema_version、插件版本、兼容矩阵
- 测试：兼容版本、未知版本、升级恢复和打包安装测试
- 验证范围：`cloud_syntax` + `local_e2e`
- 验收证据：兼容矩阵、VSIX 安装、升级和真实服务端联调结果归档。
