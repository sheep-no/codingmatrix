/**
 * 任务状态管理 Store
 *
 * 管理任务列表、实时状态更新、WebSocket 连接等
 */
import { defineStore } from 'pinia'
import { taskNotificationService } from '../utils/taskNotification.js'

export const useTaskStore = defineStore('task', {
  state: () => ({
    tasks: new Map(),
    activeTasks: [],
    completedTasks: [],
    failedTasks: [],
    isConnected: false,
    unsubscribeFn: null,
    pollingIntervals: new Map()
  }),

  getters: {
    getTaskById: state => taskId => {
      return state.tasks.get(taskId)
    },

    pendingTasks: state => {
      return Array.from(state.tasks.values()).filter(t => t.status === 'pending')
    },

    runningTasks: state => {
      return Array.from(state.tasks.values()).filter(t => t.status === 'running')
    },

    taskCount: state => state.tasks.size,

    hasActiveTasks: state => {
      return state.activeTasks.length > 0
    }
  },

  actions: {
    /**
     * 初始化任务通知连接
     */
    initNotifications() {
      if (this.unsubscribeFn) {
        return
      }

      this.unsubscribeFn = taskNotificationService.connect((taskId, data) => {
        this.handleTaskUpdate(taskId, data)
      })

      this.isConnected = true
    },

    /**
     * 断开任务通知连接
     */
    disconnectNotifications() {
      if (this.unsubscribeFn) {
        this.unsubscribeFn()
        this.unsubscribeFn = null
      }
      this.isConnected = false
    },

    /**
     * 处理任务更新
     */
    handleTaskUpdate(taskId, data) {
      const existingTask = this.tasks.get(taskId)

      if (existingTask) {
        Object.assign(existingTask, data)

        if (data.status === 'progress') {
          existingTask.progress = data.progress || 0
          existingTask.progressMessage = data.message || ''
        } else if (data.status === 'success') {
          existingTask.status = 'success'
          existingTask.progress = 100
          this.moveToCompleted(taskId)
        } else if (data.status === 'failure') {
          existingTask.status = 'failed'
          existingTask.errorMessage = data.error || ''
          this.moveToFailed(taskId)
        } else if (data.status === 'cancelled') {
          existingTask.status = 'cancelled'
          this.moveToCompleted(taskId)
        }

        this.tasks.set(taskId, existingTask)
      }
    },

    /**
     * 添加任务到活动列表
     */
    addActiveTask(task) {
      if (!this.activeTasks.find(t => t.task_id === task.task_id)) {
        this.activeTasks.push(task)
      }
      this.tasks.set(task.task_id, task)
    },

    /**
     * 移动任务到完成列表
     */
    moveToCompleted(taskId) {
      const task = this.tasks.get(taskId)
      if (task) {
        this.activeTasks = this.activeTasks.filter(t => t.task_id !== taskId)
        if (!this.completedTasks.find(t => t.task_id === taskId)) {
          this.completedTasks.unshift(task)
        }
        if (this.completedTasks.length > 50) {
          this.completedTasks.pop()
        }
      }
    },

    /**
     * 移动任务到失败列表
     */
    moveToFailed(taskId) {
      const task = this.tasks.get(taskId)
      if (task) {
        this.activeTasks = this.activeTasks.filter(t => t.task_id !== taskId)
        if (!this.failedTasks.find(t => t.task_id === taskId)) {
          this.failedTasks.unshift(task)
        }
        if (this.failedTasks.length > 50) {
          this.failedTasks.pop()
        }
      }
    },

    /**
     * 更新任务进度
     */
    updateTaskProgress(taskId, progress, message = '') {
      const task = this.tasks.get(taskId)
      if (task) {
        task.progress = progress
        task.progressMessage = message
        this.tasks.set(taskId, task)
      }
    },

    /**
     * 更新任务状态
     */
    updateTaskStatus(taskId, status, data = {}) {
      const task = this.tasks.get(taskId)
      if (task) {
        task.status = status
        Object.assign(task, data)
        this.tasks.set(taskId, task)

        if (status === 'success') {
          this.moveToCompleted(taskId)
        } else if (status === 'failed') {
          this.moveToFailed(taskId)
        }
      }
    },

    /**
     * 订阅特定任务的通知
     */
    subscribeToTask(taskId, callback) {
      return taskNotificationService.subscribeToTask(taskId, callback)
    },

    /**
     * 清除所有任务
     */
    clearAllTasks() {
      this.tasks.clear()
      this.activeTasks = []
      this.completedTasks = []
      this.failedTasks = []
    },

    /**
     * 清除已完成任务
     */
    clearCompletedTasks() {
      this.completedTasks = []
    },

    /**
     * 清除失败任务
     */
    clearFailedTasks() {
      this.failedTasks = []
    },

    /**
     * 删除任务
     */
    removeTask(taskId) {
      this.tasks.delete(taskId)
      this.activeTasks = this.activeTasks.filter(t => t.task_id !== taskId)
      this.completedTasks = this.completedTasks.filter(t => t.task_id !== taskId)
      this.failedTasks = this.failedTasks.filter(t => t.task_id !== taskId)
    }
  }
})

export default useTaskStore
