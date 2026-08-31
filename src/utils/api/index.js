/**
 * API 客户端统一导出 (v5.0.2 全量补全)
 *
 * 模块化拆分:
 * - base.js      - 核心客户端 + Token 管理
 * - auth.js      - 认证相关
 * - project.js   - 项目生成相关
 * - agent.js     - Agent 专属 (快照/知识库/需求联想/性能)
 * - workflow.js  - 工作流相关
 * - girl.js      - GirlAI 对话相关
 * - chat.js      - 聊天历史相关
 * - file.js      - 文件管理相关
 * - task.js      - 任务队列相关
 * - ppt.js       - PPT 生成相关
 * - kolors.js    - AI 绘图相关
 * - vision.js    - 图片分析/OCR
 * - aicloud.js   - AI Cloud 沙箱环境
 * - admin.js     - 系统管理相关
 * - github.js    - GitHub 集成相关
 * - websocket.js - WebSocket 管理器
 * - config.js    - 配置常量
 *
 * Token 安全原则:
 * 1. 从不打印 Token
 * 2. 错误信息不暴露 Token
 * 3. 刷新失败时自动清除
 */
import { API_CONFIG } from './config'
import { createBaseClient, apiUrl } from './base'
import { createAuthClient } from './auth'
import { createProjectClient } from './project'
import { createAgentClient } from './agent'
import { createWorkflowClient } from './workflow'
import { createGirlClient } from './girl'
import { createChatClient } from './chat'
import { createFileClient } from './file'
import { createTaskClient } from './task'
import { createPptClient } from './ppt'
import { createKolorsClient } from './kolors'
import { createAiCloudClient } from './aicloud'
import { createAdminClient } from './admin'
import { createGithubClient } from './github'
import { createSkillsClient } from './skills'
import { WebSocketManager } from './websocket'

export {
  API_CONFIG,
  createBaseClient as createApiClient,
  apiUrl,
  createAuthClient,
  createProjectClient,
  createAgentClient,
  createWorkflowClient,
  createGirlClient,
  createChatClient,
  createFileClient,
  createTaskClient,
  createPptClient,
  createKolorsClient,
  createAiCloudClient,
  createAdminClient,
  createGithubClient,
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
    ...createAgentClient(baseClient),
    ...createWorkflowClient(baseClient),
    ...createGirlClient(baseClient),
    ...createChatClient(baseClient),
    ...createFileClient(baseClient),
    ...createTaskClient(baseClient),
    ppt: createPptClient(baseClient),
    ...createKolorsClient(baseClient),
    ...createAiCloudClient(baseClient),
    ...createAdminClient(baseClient),
    ...createGithubClient(baseClient),
    ...createSkillsClient(baseClient)
  }
}

export function initApiClient(store) {
  defaultClient = createDefaultClient(store)
  window.api = defaultClient
  return defaultClient
}

// 延迟获取 api，确保在运行时能访问到 window.api
export const api = new Proxy({}, {
  get(target, prop) {
    return window.api ? window.api[prop] : undefined
  }
})

export default {
  API_CONFIG,
  createBaseClient,
  createApiClient: createBaseClient,
  createAuthClient,
  createProjectClient,
  createAgentClient,
  createWorkflowClient,
  createGirlClient,
  createChatClient,
  createFileClient,
  createTaskClient,
  createPptClient,
  createKolorsClient,
  createAiCloudClient,
  createAdminClient,
  createGithubClient,
  WebSocketManager,
  initApiClient,
  api
}
