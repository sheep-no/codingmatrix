# v5.1.2 更新日志 - 前端修复 - 2026-05-20

## 版本概览

- **版本号**: v5.1.2
- **发布日期**: 2026-05-20
- **主题**: 前端修复 - API 客户端统一、缺失方法补全、内存泄漏修复、功能集成
- **修改文件**: 15+ 前端文件
- **新增代码**: ~500 行
- **删除代码**: ~6000 行（死代码清理）

---

## 核心更新

### 1. API 客户端统一与补全

#### 统一 API 导出 (`src/utils/api/index.js`)

- 移除独立的 `vision.js` 模块（功能已集成到聊天流程）
- 统一通过 `window.api` Proxy 导出所有 API 方法
- 确保 token 自动附加和 401 自动刷新

#### 缺失 API 方法补全

| 方法 | 文件 | 端点 | 说明 |
|------|------|------|------|
| `getSavedProjects` | `project.js` | - | `listSavedProjects()` 的别名，兼容旧调用 |
| `getFileList` | `file.js` | `GET /files` | 获取文件列表，支持分页和过滤 |
| `getFile` | `file.js` | `GET /files/{id}` | 获取单个文件信息 |
| `deleteFile` | `file.js` | `DELETE /files/{id}` | 删除文件 |
| `toggleReview` | `aicloud.js` | `POST /aicloud/reviews/toggle` | 切换 AiCloud 审查开关 |

### 2. Vision 集成到聊天流程

#### 架构变更

```
用户拖拽/选择图片
    ↓
bottominput.vue: 上传到 /api/v1/files/upload
    ↓
index.vue: 将 files 数组附加到 requestData
    ↓
POST /api/v1/code (后端自动处理)
    ↓
后端检测图片格式 → 调用 analyze_image() → 注入 prompt 上下文
```

#### 具体修改

- **`index.vue`**: `handleSendMessage` 中将图片附件通过 `files` 字段传递给 `/code` 端点
- **`bottominput.vue`**: 图片附件添加 `preview` 本地预览 URL
- **`centerContent.vue`**: 用户消息气泡中渲染图片缩略图

### 3. 增量修改功能修复

#### ProjectGenerator.vue

- "增量修改"按钮现在真正调用 `enableIncrementalModify()`
- `startGeneration()` 检测 `isIncrementalMode` 后调用 `api.modifyProjectStream()`
- 复用 `sessionId` 实现上下文保持
- 修改完成后自动退出增量模式

### 4. AgentDashboard 文件预览修复

- `selectFile()` 现在调用 `api.readProjectFile()` 从后端获取文件内容
- API 调用失败时回退到本地缓存的内容
- 显示"加载中..."过渡状态

### 5. 需求联想集成到输入框

#### bottominput.vue

- 新增联想面板 UI 组件
- 输入超过 20 字符时自动调用 `api.getRequirementAssociations()`
- 800ms 防抖，最多显示 5 条联想建议
- 点击联想项追加到输入框，标记已确认
- 组件销毁时清理定时器

### 6. AiCloud 审查开关修复

- `toggleReview()` 现在真正调用后端 `/aicloud/reviews/toggle` 端点
- API 失败时仍更新本地状态，保证 UI 响应性
- 新增 `api.toggleReview()` API 方法

### 7. 内存泄漏修复

#### AdminPanel.vue

- `setInterval(updateCurrentTime, 1000)` 未在组件销毁时清理
- `addEventListener('resize')` 未在组件销毁时清理
- 修复：保存定时器引用，提取具名事件处理函数，在 `onBeforeUnmount` 中正确清理

### 8. 空指针风险修复

| 文件 | 问题 | 修复 |
|------|------|------|
| `views/ProjectGenerate.vue:261` | `file.path.split('/')` 在 `file.path` 为 `undefined` 时抛错 | 添加三元运算符保护 |
| `views/AgentDashboard.vue:270` | 同上 | 添加相同保护 |

### 9. 调试日志清理

- 移除 `leftlist.vue` 中的 2 条 `console.log('[DEBUG]...')` 调试日志

### 10. 路由修复

- `/kolors` 路由从指向 `Aicloud.vue` 改为指向 `ImageGenerate.vue`

### 11. 死代码清理

删除 22 个未使用的文件（17 个 Vue 组件，5 个 utils/stores），节省约 5600 行代码：

| 类别 | 数量 | 示例 |
|------|------|------|
| Vue 组件 | 17 | 已迁移或废弃的功能页面 |
| Utils/Stores | 5 | 重复或废弃的工具函数 |

---

## 功能完整性验证

### 检查结果

| 检查项 | 结果 |
|-------|------|
| @click 事件处理方法定义 | 全部 250+ 个事件处理方法均已定义 |
| v-model 绑定变量定义 | 所有变量均通过 `ref()` 或 `reactive()` 正确定义 |
| API 方法调用 | 所有调用的 API 方法均在 `utils/api/` 中定义 |
| 组件导入 | 所有 `import` 的组件文件均存在 |
| 定时器清理 | 所有 `setInterval`/`addEventListener` 均在 `onBeforeUnmount` 中清理 |
| XSS 防护 | 所有 `v-html` 均使用 `DOMPurify.sanitize()` 净化 |
| 构建状态 | 成功，无错误或警告 |

---

## 修复问题列表

| # | 问题 | 严重性 | 状态 |
|---|------|--------|------|
| 1 | Vision 功能未集成到聊天流程 | 高 | ✅ 已修复 |
| 2 | 增量修改按钮为假实现 | 高 | ✅ 已修复 |
| 3 | AgentDashboard 文件预览无法获取内容 | 高 | ✅ 已修复 |
| 4 | 缺失 4 个 API 方法 | 高 | ✅ 已修复 |
| 5 | AdminPanel 内存泄漏 | 中 | ✅ 已修复 |
| 6 | AiCloud 审查开关未调用后端 | 中 | ✅ 已修复 |
| 7 | 需求联想未集成到输入框 | 中 | ✅ 已修复 |
| 8 | 空指针风险 (2 处) | 低 | ✅ 已修复 |
| 9 | 调试日志残留 | 低 | ✅ 已修复 |
| 10 | /kolors 路由指向错误组件 | 低 | ✅ 已修复 |
| 11 | 死代码未清理 | 低 | ✅ 已修复 |

---

## 构建验证

```bash
npm run build
# ✓ built in ~55s
# 无错误，无警告
```
