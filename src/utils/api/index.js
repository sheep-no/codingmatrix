/**
 * API 客户端统一导出
 *
 * 模块化拆分:
 * - base.js      - 核心客户端 + Token 管理
 * - auth.js      - 认证相关
 * - project.js   - 项目生成相关
 * - girl.js      - GirlAI 对话相关
 * - chat.js      - 聊天历史相关
 * - file.js      - 文件管理相关
 * - task.js      - 任务队列相关
 * - ppt.js       - PPT 生成相关
 * - admin.js     - 系统管理相关
 * - websocket.js - WebSocket 管理器
 * - config.js    - 配置常量
 *
 * Token 安全原则:
 * 1. 永不打印 Token
 * 2. 错误信息不暴露 Token
 * 3. 刷新失败时自动清除
 */
import { API_CONFIG } from './config'
import { createBaseClient, apiUrl } from './base'
import { createAuthClient } from './auth'
import { createProjectClient } from './project'
import { createWorkflowClient } from './workflow'
import { createGirlClient } from './girl'
import { createChatClient } from './chat'
import { createFileClient } from './file'
import { createTaskClient } from './task'
import { createPptClient } from './ppt'
import { createAdminClient } from './admin'
import { WebSocketManager } from './websocket'

export {
  API_CONFIG,
  createBaseClient as createApiClient,
  apiUrl,
  createAuthClient,
  createProjectClient,
  createWorkflowClient,
  createGirlClient,
  createChatClient,
  createFileClient,
  createTaskClient,
  createPptClient,
  createAdminClient,
  WebSocketManager
}

let userStoreInstance = null
let defaultClient = null

function createDefaultClient(store) {
  userStoreInstance = store
  const baseClient = createBaseClient(store)

  return {
    ...baseClient,
    ...createAuthClient(baseClient),
    ...createProjectClient(baseClient),
    ...createWorkflowClient(baseClient),
    ...createGirlClient(baseClient),
    ...createChatClient(baseClient),
    ...createFileClient(baseClient),
    ...createTaskClient(baseClient),
    ...createPptClient(baseClient),
    ...createAdminClient(baseClient)
  }
}

export function initApiClient(store) {
  defaultClient = createDefaultClient(store)
  window.api = defaultClient
  return defaultClient
}

export const api = createDefaultClient(null)

export default {
  API_CONFIG,
  createBaseClient,
  createApiClient: createBaseClient,
  createAuthClient,
  createProjectClient,
  createWorkflowClient,
  createGirlClient,
  createChatClient,
  createFileClient,
  createTaskClient,
  createPptClient,
  createAdminClient,
  WebSocketManager,
  initApiClient,
  api
}
