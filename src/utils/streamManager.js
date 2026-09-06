/**
 * 流式请求状态管理工具
 * 用于：
 * 1. 保存正在进行的流式请求状态
 * 2. 刷新后恢复流式输出
 * 3. 管理请求中断功能
 * 4. 支持请求优先级队列
 * 5. 支持请求限流和并发控制
 */

const STORAGE_KEY = 'streamRequestState'
const ABORT_CONTROLLERS_KEY = 'streamAbortControllers'
const REQUEST_QUEUE_KEY = 'streamRequestQueue'
const MAX_REQUESTS = 5 // 最大并发请求数

// 调试开关（生产环境关闭）
const DEBUG = import.meta?.env?.DEV ?? false
const log = (...args) => { if (DEBUG) console.log(...args) }
const logError = (...args) => console.error(...args)
const SENSITIVE_KEYS = new Set(['api_key', 'api_key_token', 'access_token', 'authorization', 'password', 'secret'])

const sanitizePersistedValue = value => {
  if (Array.isArray(value)) return value.map(sanitizePersistedValue)
  if (!value || typeof value !== 'object') return value

  return Object.fromEntries(
    Object.entries(value)
      .filter(([key]) => !SENSITIVE_KEYS.has(key.toLowerCase()))
      .map(([key, nestedValue]) => [key, sanitizePersistedValue(nestedValue)])
  )
}

/**
 * 请求优先级枚举
 */
export const RequestPriority = {
  HIGH: 'high',
  NORMAL: 'normal',
  LOW: 'low'
}

/**
 * StreamManager 类
 */
class StreamManager {
  constructor() {
    this.abortControllers = new Map()
    this.currentRequestId = null
    this.requestQueue = []
    this.processingCount = 0

    // 从 sessionStorage 恢复 AbortController 代理
    this.restoreAbortControllers()
    // 恢复请求队列
    this.restoreRequestQueue()
  }

  /**
   * 保存流式请求状态到 localStorage
   * @param {Object} requestData - 请求数据
   * @param {Object} messageData - 消息数据
   * @param {number} conversationId - 对话ID
   */
  saveStreamRequestState(requestData, messageData, conversationId) {
    const state = {
      requestId: this.currentRequestId,
      requestData: sanitizePersistedValue(requestData),
      messageData: sanitizePersistedValue(messageData),
      conversationId,
      timestamp: Date.now(),
      isStreaming: true
    }

    localStorage.setItem(STORAGE_KEY, JSON.stringify(state))
    log('[SUCCESS] Stream request state saved:', state)
  }

  /**
   * 获取保存的流式请求状态
   * @returns {Object|null}
   */
  getStreamRequestState() {
    try {
      const savedState = localStorage.getItem(STORAGE_KEY)
      if (!savedState) return null

      const state = JSON.parse(savedState)

      // 检查状态是否过期（超过5分钟）
      if (Date.now() - state.timestamp > 300000) {
        localStorage.removeItem(STORAGE_KEY)
        return null
      }

      return state
    } catch (error) {
      logError('[ERR] Get stream request state failed:', error)
      return null
    }
  }

  /**
   * 清除流式请求状态
   */
  clearStreamRequestState() {
    localStorage.removeItem(STORAGE_KEY)
    this.currentRequestId = null
    log('[SUCCESS] Stream request state cleared')
  }

  /**
   * 创建新的 AbortController
   * @param {string} requestId - 请求ID
   * @returns {AbortController}
   */
  createAbortController(requestId) {
    const controller = new AbortController()
    this.abortControllers.set(requestId, controller)
    this.currentRequestId = requestId

    // 保存到 sessionStorage
    const controllersData = Array.from(this.abortControllers.entries()).map(([id]) => ({
      id,
      timestamp: Date.now()
    }))
    sessionStorage.setItem(ABORT_CONTROLLERS_KEY, JSON.stringify(controllersData))

    log('[SUCCESS] Created AbortController:', requestId)
    return controller
  }

  /**
   * 获取 AbortController
   * @param {string} requestId - 请求ID
   * @returns {AbortController|undefined}
   */
  getAbortController(requestId) {
    return this.abortControllers.get(requestId)
  }

  /**
   * 中断请求
   * @param {string} requestId - 请求ID
   */
  abortRequest(requestId) {
    const controller = this.abortControllers.get(requestId)
    if (controller) {
      controller.abort()
      this.abortControllers.delete(requestId)
      this.clearStreamRequestState()
      log('[SUCCESS] Request aborted:', requestId)
      return true
    }
    return false
  }

  /**
   * 中断当前请求
   */
  abortCurrentRequest() {
    if (this.currentRequestId) {
      return this.abortRequest(this.currentRequestId)
    }
    // 尝试中断第一个可用的请求
    for (const [requestId, controller] of this.abortControllers.entries()) {
      controller.abort()
      this.abortControllers.delete(requestId)
      log('[SUCCESS] Request aborted:', requestId)
      return true
    }
    return false
  }

  /**
   * 从 sessionStorage 恢复 AbortController 代理
   * 注意：页面刷新后旧的 AbortController 无法恢复，这里只是清理
   */
  restoreAbortControllers() {
    try {
      const savedControllers = sessionStorage.getItem(ABORT_CONTROLLERS_KEY)
      if (savedControllers) {
        const controllers = JSON.parse(savedControllers)
        // 清理过期的 AbortController（旧页面刷新后的）
        const currentTime = Date.now()
        const validControllers = controllers.filter(c => currentTime - c.timestamp < 60000)

        if (validControllers.length === 0) {
          sessionStorage.removeItem(ABORT_CONTROLLERS_KEY)
          log('[SUCCESS] Cleaned up expired AbortControllers')
        }
      }
    } catch (error) {
      logError('[ERR] Restore AbortControllers failed:', error)
    }
  }

  /**
   * 检查是否有正在进行的请求
   * @returns {boolean}
   */
  hasActiveRequest() {
    return this.abortControllers.size > 0 || this.getStreamRequestState() !== null
  }

  /**
   * 清理所有 AbortController
   */
  cleanup() {
    for (const [requestId, controller] of this.abortControllers.entries()) {
      controller.abort()
    }
    this.abortControllers.clear()
    sessionStorage.removeItem(ABORT_CONTROLLERS_KEY)
    this.clearStreamRequestState()
  }

  /**
   * 添加请求到队列
   * @param {Object} request - 请求数据
   * @param {string} request.url - 请求 URL
   * @param {Object} request.data - 请求数据
   * @param {string} request.priority - 请求优先级（high|normal|low）
   * @returns {string} 返回请求 ID
   */
  enqueueRequest(request) {
    const requestId = `req_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`
    const queueItem = {
      id: requestId,
      url: request.url,
      data: request.data,
      priority: request.priority || RequestPriority.NORMAL,
      timestamp: Date.now(),
      status: 'pending'
    }

    // 按优先级排序插入队列
    const priorityOrder = {
      [RequestPriority.HIGH]: 0,
      [RequestPriority.NORMAL]: 1,
      [RequestPriority.LOW]: 2
    }
    let insertIndex = this.requestQueue.length

    for (let i = 0; i < this.requestQueue.length; i++) {
      if (priorityOrder[queueItem.priority] < priorityOrder[this.requestQueue[i].priority]) {
        insertIndex = i
        break
      }
    }

    this.requestQueue.splice(insertIndex, 0, queueItem)
    this.saveRequestQueue()

    log('[SUCCESS] Request added to queue:', requestId, 'priority:', queueItem.priority)
    return requestId
  }

  /**
   * 从队列中获取下一个请求
   * @returns {Object|null} 返回下一个请求或 null
   */
  dequeueRequest() {
    if (this.requestQueue.length === 0) {
      return null
    }

    const request = this.requestQueue.shift()
    request.status = 'processing'
    this.saveRequestQueue()

    log('[SUCCESS] Dequeued request:', request.id)
    return request
  }

  /**
   * 取消队列中的请求
   * @param {string} requestId - 请求 ID
   * @returns {boolean} 是否成功取消
   */
  cancelQueuedRequest(requestId) {
    const index = this.requestQueue.findIndex(r => r.id === requestId)
    if (index !== -1) {
      this.requestQueue.splice(index, 1)
      this.saveRequestQueue()
      log('[SUCCESS] Cancelled request in queue:', requestId)
      return true
    }
    return false
  }

  /**
   * 保存请求队列到 sessionStorage
   */
  saveRequestQueue() {
    try {
      sessionStorage.setItem(REQUEST_QUEUE_KEY, JSON.stringify(this.requestQueue))
    } catch (error) {
      logError('[ERR] Save request queue failed:', error)
    }
  }

  /**
   * 从 sessionStorage 恢复请求队列
   */
  restoreRequestQueue() {
    try {
      const savedQueue = sessionStorage.getItem(REQUEST_QUEUE_KEY)
      if (savedQueue) {
        this.requestQueue = JSON.parse(savedQueue)
        log('[SUCCESS] Restored request queue:', this.requestQueue.length, 'requests')
      }
    } catch (error) {
      logError('[ERR] Restore request queue failed:', error)
      this.requestQueue = []
    }
  }

  /**
   * 检查是否可以发送新请求
   * @returns {boolean}
   */
  canSendRequest() {
    return this.processingCount < MAX_REQUESTS
  }

  /**
   * 增加处理中的请求计数
   */
  incrementProcessingCount() {
    this.processingCount++
    log('[STATS] 处理中请求数:', this.processingCount, '/', MAX_REQUESTS)
  }

  /**
   * 减少处理中的请求计数
   */
  decrementProcessingCount() {
    this.processingCount = Math.max(0, this.processingCount - 1)
    log('[STATS] 处理中请求数:', this.processingCount, '/', MAX_REQUESTS)
  }

  /**
   * 获取队列状态
   * @returns {Object} 返回队列状态信息
   */
  getQueueStatus() {
    return {
      pending: this.requestQueue.filter(r => r.status === 'pending').length,
      processing: this.processingCount,
      abortControllers: this.abortControllers.size,
      canSendRequest: this.canSendRequest()
    }
  }

  /**
   * 批量取消所有请求
   * @returns {number} 返回取消的请求数量
   */
  cancelAllRequests() {
    let cancelledCount = 0

    // 取消队列中的请求
    cancelledCount += this.requestQueue.length
    this.requestQueue = []
    this.saveRequestQueue()

    // 取消正在进行的请求
    for (const [requestId, controller] of this.abortControllers.entries()) {
      controller.abort()
      this.abortControllers.delete(requestId)
      cancelledCount++
    }

    this.clearStreamRequestState()
    this.currentRequestId = null
    this.processingCount = 0

    log('[SUCCESS] Cancelled all requests:', cancelledCount)
    return cancelledCount
  }

  /**
   * 获取请求历史统计
   * @returns {Object} 返回统计信息
   */
  getRequestStats() {
    const now = Date.now()
    const oneHourAgo = now - 3600000

    const savedControllers = sessionStorage.getItem(ABORT_CONTROLLERS_KEY)
    if (!savedControllers) {
      return { total: 0, active: 0, lastHour: 0 }
    }

    const controllers = JSON.parse(savedControllers)
    const lastHourRequests = controllers.filter(c => c.timestamp > oneHourAgo).length

    return {
      total: controllers.length,
      active: this.abortControllers.size,
      lastHour: lastHourRequests,
      queue: this.requestQueue.length
    }
  }
}

// 导出单例
export const streamManager = new StreamManager()

export default streamManager
