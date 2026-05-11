# Girl AI V2 升级完成

## 升级日期: 2026-04

## 升级内容

### 新增功能

| 功能 | 描述 |
|------|------|
| 多角色支持 | 支持多种 AI 角色性格 |
| 历史管理 | 完整的对话历史管理 |
| 角色列表 | GET /api/v1/GirlAi/characters |

### API 变更

| 端点 | 变更 |
|------|------|
| POST /api/v1/GirlAi | 新增 character_id 参数 |
| GET /api/v1/GirlAi/history | 新增 |
| DELETE /api/v1/GirlAi/history | 新增 (清空历史) |

### 前端变更

- 新增角色选择器
- 优化聊天界面
- 支持历史浏览和清空

## 测试结果

所有 GirlAi 相关测试通过。
