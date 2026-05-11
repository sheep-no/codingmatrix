/**
 * 任务通知服务
 *
 * 提供实时任务状态推送功能，支持：
 * - WebSocket 连接管理
 * - 任务状态更新
 * - 进度通知
 * - 自动重连
 */

import { wsPool } from './websocketPool.js'
import { getValidToken } from './api.js'

const TASK_WS_ENDPOINT = '/api/v1/tasks/ws'

class TaskNotificationService {
  constructor() {
    this.subscribers = new Map()
    this.taskListeners = new Map()
    this.isConnected = false
    this.unsubscribeFn = null
  }

  /**
   * 连接任务通知 WebSocket
   * @param {function} onTaskUpdate - 任务更新回调
   * @returns {function} 取消订阅函数
   */
  connect(onTaskUpdate) {
    if (this.unsubscribeFn) {
      return this.unsubscribeFn
    }

    const token = getValidToken()
    if (!token) {
      console.warn('TaskNotification: No token available, cannot connect')
      return () => {}
    }

    console.log('TaskNotification: Connecting to task WebSocket...')

    this.unsubscribeFn = wsPool.subscribe(
      TASK_WS_ENDPOINT,
      token,
      message => this.handleMessage(message),
      status => this.handleStatusChange(status)
    )

    this.subscribers.set('default', onTaskUpdate)

    return () => {
      this.disconnect()
    }
  }

  /**
   * 断开连接
   */
  disconnect() {
    if (this.unsubscribeFn) {
      this.unsubscribeFn()
      this.unsubscribeFn = null
    }
    this.subscribers.clear()
    this.taskListeners.clear()
    this.isConnected = false
  }

  /**
   * 处理接收到的消息
   * @param {Object} message - WebSocket 消息
   */
  handleMessage(message) {
    try {
      const data = typeof message === 'string' ? JSON.parse(message) : message

      if (data.type === 'task_update') {
        this.notifyTaskUpdate(data.task_id, data.data)
      } else if (data.type === 'pong') {
        console.log('TaskNotification: Received pong')
      }
    } catch (error) {
      console.error('TaskNotification: Failed to parse message', error)
    }
  }

  /**
   * 处理连接状态变化
   * @param {string} status - 连接状态
   */
  handleStatusChange(status) {
    console.log('TaskNotification: Connection status changed', status)
    this.isConnected = status === 'connected'

    if (status === 'connected') {
      this.sendPing()
    }
  }

  /**
   * 发送 ping 保持连接
   */
  sendPing() {
    wsPool.send(TASK_WS_ENDPOINT, 'ping')
  }

  /**
   * 通知任务更新给所有订阅者
   * @param {string} taskId - 任务 ID
   * @param {Object} data - 任务数据
   */
  notifyTaskUpdate(taskId, data) {
    console.log('TaskNotification: Task update received', { taskId, data })

    this.subscribers.forEach(callback => {
      try {
        callback(taskId, data)
      } catch (error) {
        console.error('TaskNotification: Subscriber error', error)
      }
    })

    if (this.taskListeners.has(taskId)) {
      this.taskListeners.get(taskId).forEach(callback => {
        try {
          callback(data)
        } catch (error) {
          console.error('TaskNotification: Task listener error', error)
        }
      })
    }
  }

  /**
   * 订阅特定任务的状态更新
   * @param {string} taskId - 任务 ID
   * @param {function} callback - 回调函数
   * @returns {function} 取消订阅函数
   */
  subscribeToTask(taskId, callback) {
    if (!this.taskListeners.has(taskId)) {
      this.taskListeners.set(taskId, new Set())
    }
    this.taskListeners.get(taskId).add(callback)

    return () => {
      const listeners = this.taskListeners.get(taskId)
      if (listeners) {
        listeners.delete(callback)
        if (listeners.size === 0) {
          this.taskListeners.delete(taskId)
        }
      }
    }
  }

  /**
   * 批量订阅多个任务
   * @param {string[]} taskIds - 任务 ID 数组
   * @param {function} callback - 回调函数
   * @returns {function} 取消订阅函数
   */
  subscribeToTasks(taskIds, callback) {
    const unsubscribes = taskIds.map(taskId => this.subscribeToTask(taskId, callback))

    return () => {
      unsubscribes.forEach(unsub => unsub())
    }
  }

  /**
   * 获取连接状态
   * @returns {boolean} 是否已连接
   */
  getIsConnected() {
    return this.isConnected
  }
}

export const taskNotificationService = new TaskNotificationService()

export default taskNotificationService
