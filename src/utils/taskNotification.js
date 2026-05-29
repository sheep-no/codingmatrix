/**
 * 任务通知服务
 *
 * 提供任务状态更新的发布/订阅机制
 * 用于 WebSocket 或 SSE 事件分发
 */

class TaskNotificationService {
  constructor() {
    this.subscribers = new Map()
    this.globalCallback = null
    this.isConnected = false
  }

  /**
   * 注册全局任务更新回调
   * @param {Function} callback
   * @returns {Function} 取消订阅函数
   */
  connect(callback) {
    this.globalCallback = callback
    this.isConnected = true
    
    return () => {
      this.globalCallback = null
      this.isConnected = false
    }
  }

  /**
   * 订阅特定任务的通知
   * @param {string} taskId
   * @param {Function} callback
   * @returns {Function} 取消订阅函数
   */
  subscribeToTask(taskId, callback) {
    if (!this.subscribers.has(taskId)) {
      this.subscribers.set(taskId, new Set())
    }
    this.subscribers.get(taskId).add(callback)

    return () => {
      const subs = this.subscribers.get(taskId)
      if (subs) {
        subs.delete(callback)
        if (subs.size === 0) {
          this.subscribers.delete(taskId)
        }
      }
    }
  }

  /**
   * 发布任务更新
   * @param {string} taskId
   * @param {Object} data
   */
  publishTaskUpdate(taskId, data) {
    if (this.globalCallback) {
      this.globalCallback(taskId, data)
    }

    const subs = this.subscribers.get(taskId)
    if (subs) {
      subs.forEach(callback => {
        try {
          callback(taskId, data)
        } catch (e) {
          console.error('Task notification callback error:', e)
        }
      })
    }
  }

  /**
   * 断开所有连接
   */
  disconnect() {
    this.globalCallback = null
    this.isConnected = false
    this.subscribers.clear()
  }
}

export const taskNotificationService = new TaskNotificationService()
export default taskNotificationService
