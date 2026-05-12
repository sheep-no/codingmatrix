# GitHub 集成和 Git 操作 SSE 推送

## 功能概述

CodingMatrix 现在支持完整的 GitHub 集成和 Git 操作的实时 SSE 推送。

### 主要特性

1. **GitHub 账号配置**
   - 用户可以在前端配置 GitHub 用户名和 Personal Access Token
   - 支持切换使用 GitHub 或本地 Git 保存项目
   - 提供连接测试功能

2. **灵活的项目保存**
   - 启用 GitHub：项目自动推送到用户的 GitHub 仓库
   - 禁用 GitHub：项目保存到本地 Git 仓库
   - 自动创建仓库和初始提交

3. **Git 操作 SSE 推送**
   - 所有 Git 操作通过 Server-Sent Events 实时推送
   - 支持的操作类型：
     - `git_operation_start` - 操作开始
     - `git_operation_success` - 操作成功
     - `git_operation_error` - 操作失败
   - 前端可以实时显示操作进度和结果

4. **安全考虑**
   - GitHub Token 使用 HTTPS 传输
   - 本地存储使用 base64 编码（生产环境应使用更强加密）
   - Git 操作路径安全性验证

## API 端点

### GitHub 配置
- `POST /api/v1/github/config` - 设置 GitHub 配置
- `GET /api/v1/github/config` - 获取 GitHub 配置

### 项目保存
- `POST /api/v1/github/save` - 保存项目到 GitHub 或本地 Git

### Git 工具（通过 Agent）
- `git_status` - 查看仓库状态
- `git_log` - 查看提交历史
- `git_diff` - 查看差异
- `git_checkout` - 切换分支/恢复文件
- `git_reset` - 安全重置
- `git_restore_file` - 恢复特定文件
- `git_rollback` - 项目回滚

## 前端集成

### 组件
- `GithubConfigPanel.vue` - GitHub 配置面板
- 更新的 `ProjectGenerate.vue` - 集成 GitHub 保存功能

### Store
- `github.js` - GitHub 配置状态管理

### API 客户端
- `github.js` - GitHub API 封装

## 使用流程

1. 用户访问 `/github-config` 页面配置 GitHub 账号
2. 在项目生成页面，选择是否使用 GitHub 保存
3. 生成项目后，点击"保存项目"按钮
4. 系统根据配置决定保存到 GitHub 还是本地 Git
5. 所有操作通过 SSE 实时推送到前端显示

## 安全最佳实践

1. **Token 管理**
   - 使用 Personal Access Token 而不是密码
   - Token 应具有最小必要权限（repo 权限）
   - 前端存储使用加密

2. **路径安全**
   - 所有 Git 操作路径都经过安全性验证
   - 防止路径遍历攻击

3. **错误处理**
   - 敏感信息不在错误消息中暴露
   - 提供用户友好的错误提示

## 未来扩展

1. **多仓库支持** - 允许用户选择目标仓库
2. **分支管理** - 支持创建和切换分支
3. **Pull Request** - 自动生成 PR 进行代码审查
4. **Webhook 集成** - 支持 GitHub Webhooks
5. **SSH Key 支持** - 支持 SSH 认证方式