# Sprint 1: 用户与权限系统 (RBAC)

## 1. 需求概述

为 AI Workspace 平台构建企业级多租户用户权限管理系统，支持角色权限控制、部门组织架构、租户隔离、用户认证与审计日志。

---

## 2. 功能需求

### 2.1 多租户管理

**FR-001: 租户创建**
- 系统应支持创建租户（企业/组织）
- 每个租户拥有独立的标识符、名称、域名前缀
- 租户创建时需指定管理员账号

**FR-002: 租户切换**
- 用户可属于多个租户
- 用户可在不同租户间切换上下文
- 切换租户后仅显示该租户下的数据

**FR-003: 租户数据隔离**
- 所有数据查询必须包含租户 ID 过滤
- 跨租户数据访问必须拒绝并记录审计日志

---

### 2.2 用户管理

**FR-010: 用户注册与激活**
- 支持通过管理员邀请链接注册
- 新用户注册后状态为"待激活"
- 管理员可手动激活用户

**FR-011: 用户信息管理**
- 用户可编辑个人资料（头像、姓名、邮箱、手机号）
- 管理员可修改其他用户的任意信息
- 支持批量导入用户（CSV）

**FR-012: 用户状态管理**
- 状态包括：待激活、活跃、禁用、已删除
- 禁用用户无法登录
- 软删除保留数据 30 天后物理删除

---

### 2.3 角色权限系统 (RBAC)

**FR-020: 角色定义**
系统预置以下角色：

| 角色 | 标识 | 描述 |
|------|------|------|
| 超级管理员 | `super_admin` | 平台级管理，所有权限 |
| 租户管理员 | `tenant_admin` | 租户内所有权限 |
| 部门主管 | `dept_manager` | 部门管理 + 部门内成员管理 |
| 项目管理员 | `project_admin` | 项目管理 + 项目成员管理 |
| 普通用户 | `user` | 基础功能访问 |
| 访客 | `guest` | 只读权限 |

**FR-021: 自定义角色**
- 租户管理员可创建自定义角色
- 自定义角色可勾选权限点
- 角色可设置是否允许分配

**FR-022: 权限点定义**
权限采用 `资源:操作` 格式：

```
user:read          # 查看用户
user:write         # 编辑用户
user:delete        # 删除用户
user:invite        # 邀请用户
role:read          # 查看角色
role:write         # 编辑角色
dept:read          # 查看部门
dept:write         # 管理部门
project:read       # 查看项目
project:write      # 编辑项目
project:delete     # 删除项目
setting:read       # 查看设置
setting:write      # 修改设置
```

**FR-023: 角色继承**
- 支持角色继承关系
- 子角色自动获得父角色所有权限

---

### 2.4 部门组织架构

**FR-030: 部门树管理**
- 支持无限层级部门树
- 每个部门包含：名称、编码、负责人、上级部门、排序
- 支持拖拽调整部门顺序

**FR-031: 部门成员**
- 用户必须属于至少一个部门
- 用户可属于多个部门（设置主部门）
- 部门负责人自动获得部门管理权限

**FR-032: 部门数据权限**
- 可查看本部门及子部门数据
- 可配置是否允许查看其他部门数据

---

### 2.5 认证与安全

**FR-040: 登录认证**
- 支持邮箱 + 密码登录
- 支持手机号 + 验证码登录
- 支持第三方登录（GitHub、钉钉、企业微信）

**FR-041: 会话管理**
- JWT Token 有效期 2 小时
- Refresh Token 有效期 7 天
- 支持踢出其他设备登录

**FR-042: 密码安全**
- 密码最小 8 位，包含大小写字母和数字
- 密码连续错误 5 次锁定账号 15 分钟
- 密码 90 天过期提醒

**FR-043: 双因素认证 (2FA)**
- 支持 TOTP (Google Authenticator)
- 管理员可强制要求 2FA

---

### 2.6 审计日志

**FR-050: 操作日志**
- 记录所有敏感操作（登录、权限变更、数据删除）
- 日志包含：操作人、操作时间、IP 地址、操作类型、操作对象、结果
- 日志不可篡改，保留 180 天

**FR-051: 登录日志**
- 记录所有登录尝试（成功/失败）
- 异常登录告警（异地登录、新设备）

---

## 3. 前端需求

### 3.1 页面列表

| 页面 | 路径 | 功能 |
|------|------|------|
| 用户管理 | `/admin/users` | 用户列表、搜索、筛选、状态管理 |
| 角色管理 | `/admin/roles` | 角色列表、权限配置、角色分配 |
| 部门管理 | `/admin/departments` | 部门树展示、拖拽排序、部门成员 |
| 租户管理 | `/admin/tenants` | 租户列表、租户详情、租户切换 |
| 审计日志 | `/admin/audit-logs` | 日志列表、时间筛选、类型筛选 |
| 安全设置 | `/admin/security` | 密码策略、2FA 设置、会话管理 |

### 3.2 组件需求

**用户列表组件**
- 表格展示，支持分页
- 搜索（姓名/邮箱/手机号）
- 筛选（状态/角色/部门）
- 批量操作（启用/禁用/分配角色）

**角色权限配置组件**
- 树形权限选择器
- 权限分组展示
- 全选/半选/取消状态

**部门树组件**
- 可拖拽排序
- 展开/折叠
- 显示部门人数统计

---

## 4. 后端需求

### 4.1 API 接口

**租户 API**
```
GET    /api/v1/tenants              # 租户列表
POST   /api/v1/tenants              # 创建租户
GET    /api/v1/tenants/:id          # 租户详情
PUT    /api/v1/tenants/:id          # 更新租户
DELETE /api/v1/tenants/:id          # 删除租户
```

**用户 API**
```
GET    /api/v1/users                # 用户列表
POST   /api/v1/users                # 创建用户
GET    /api/v1/users/:id            # 用户详情
PUT    /api/v1/users/:id            # 更新用户
DELETE /api/v1/users/:id            # 删除用户
POST   /api/v1/users/:id/activate   # 激活用户
POST   /api/v1/users/:id/disable    # 禁用用户
POST   /api/v1/users/batch-import   # 批量导入
GET    /api/v1/users/me             # 当前用户信息
PUT    /api/v1/users/me             # 更新当前用户
```

**角色 API**
```
GET    /api/v1/roles                # 角色列表
POST   /api/v1/roles                # 创建角色
GET    /api/v1/roles/:id            # 角色详情
PUT    /api/v1/roles/:id            # 更新角色
DELETE /api/v1/roles/:id            # 删除角色
GET    /api/v1/permissions          # 权限点列表
```

**部门 API**
```
GET    /api/v1/departments          # 部门树
POST   /api/v1/departments          # 创建部门
PUT    /api/v1/departments/:id      # 更新部门
DELETE /api/v1/departments/:id      # 删除部门
POST   /api/v1/departments/:id/members  # 添加成员
DELETE /api/v1/departments/:id/members/:uid  # 移除成员
```

**认证 API**
```
POST   /api/v1/auth/login           # 登录
POST   /api/v1/auth/register        # 注册
POST   /api/v1/auth/refresh         # 刷新 Token
POST   /api/v1/auth/logout          # 登出
POST   /api/v1/auth/2fa/enable      # 启用 2FA
POST   /api/v1/auth/2fa/verify      # 验证 2FA
GET    /api/v1/auth/sessions        # 活跃会话列表
DELETE /api/v1/auth/sessions/:id    # 终止会话
```

**审计 API**
```
GET    /api/v1/audit-logs           # 操作日志
GET    /api/v1/audit-logs/login     # 登录日志
```

---

## 5. 数据库设计

### 5.1 表结构

```
tenants (租户表)
├── id (UUID, PK)
├── name (VARCHAR)
├── slug (VARCHAR, UNIQUE)
├── domain_prefix (VARCHAR)
├── status (ENUM)
├── settings (JSON)
├── created_at (TIMESTAMP)
└── updated_at (TIMESTAMP)

users (用户表)
── id (UUID, PK)
── tenant_id (UUID, FK)
├── email (VARCHAR, UNIQUE)
├── phone (VARCHAR)
├── password_hash (VARCHAR)
├── display_name (VARCHAR)
├── avatar_url (VARCHAR)
├── status (ENUM)
├── last_login_at (TIMESTAMP)
├── created_at (TIMESTAMP)
└── updated_at (TIMESTAMP)

roles (角色表)
├── id (UUID, PK)
├── tenant_id (UUID, FK)
├── name (VARCHAR)
├── code (VARCHAR, UNIQUE)
├── description (TEXT)
── parent_id (UUID, FK, NULL)
├── is_system (BOOLEAN)
── is_assignable (BOOLEAN)
├── created_at (TIMESTAMP)
└── updated_at (TIMESTAMP)

permissions (权限表)
── id (UUID, PK)
├── name (VARCHAR)
├── code (VARCHAR, UNIQUE)
── group (VARCHAR)
├── description (TEXT)
└── created_at (TIMESTAMP)

role_permissions (角色权限关联表)
├── role_id (UUID, FK)
── permission_id (UUID, FK)
└── created_at (TIMESTAMP)

user_roles (用户角色关联表)
├── user_id (UUID, FK)
├── role_id (UUID, FK)
── created_at (TIMESTAMP)

departments (部门表)
├── id (UUID, PK)
├── tenant_id (UUID, FK)
├── name (VARCHAR)
── code (VARCHAR)
├── parent_id (UUID, FK, NULL)
├── manager_id (UUID, FK, NULL)
── sort_order (INTEGER)
├── created_at (TIMESTAMP)
└── updated_at (TIMESTAMP)

user_departments (用户部门关联表)
├── user_id (UUID, FK)
├── department_id (UUID, FK)
├── is_primary (BOOLEAN)
└── created_at (TIMESTAMP)

audit_logs (审计日志表)
├── id (UUID, PK)
├── tenant_id (UUID, FK)
├── user_id (UUID, FK)
├── action (VARCHAR)
├── resource_type (VARCHAR)
── resource_id (VARCHAR)
├── request_data (JSON)
├── response_data (JSON)
├── ip_address (VARCHAR)
├── user_agent (TEXT)
── result (ENUM)
├── created_at (TIMESTAMP)

login_logs (登录日志表)
├── id (UUID, PK)
├── tenant_id (UUID, FK)
├── user_id (UUID, FK, NULL)
├── login_type (VARCHAR)
├── ip_address (VARCHAR)
── user_agent (TEXT)
├── device_info (JSON)
├── status (ENUM)
├── failure_reason (VARCHAR)
└── created_at (TIMESTAMP)

user_sessions (用户会话表)
├── id (UUID, PK)
├── user_id (UUID, FK)
├── token_hash (VARCHAR)
├── device_info (JSON)
├── ip_address (VARCHAR)
├── expires_at (TIMESTAMP)
├── created_at (TIMESTAMP)
└── revoked_at (TIMESTAMP)
```

---

## 6. 测试需求

### 6.1 单元测试
- 权限验证中间件测试
- RBAC 权限检查逻辑测试
- 密码哈希与验证测试
- Token 生成与验证测试

### 6.2 集成测试
- 用户 CRUD API 测试
- 角色权限分配测试
- 部门树操作测试
- 租户数据隔离测试

### 6.3 E2E 测试
- 登录流程测试（密码/验证码/第三方）
- 角色权限 UI 测试
- 部门管理拖拽测试
- 用户批量导入测试

---

## 7. 验收标准

| 编号 | 验收项 | 标准 |
|------|--------|------|
| AC-01 | 多租户隔离 | 不同租户用户无法看到对方数据 |
| AC-02 | 权限控制 | 无权限用户访问接口返回 403 |
| AC-03 | 角色继承 | 子角色自动拥有父角色权限 |
| AC-04 | 部门树 | 支持无限层级，拖拽排序正常 |
| AC-05 | 审计日志 | 所有敏感操作均有日志记录 |
| AC-06 | 密码安全 | 弱密码被拒绝，错误锁定生效 |
| AC-07 | 会话管理 | 可踢出其他设备，Token 过期正常 |
