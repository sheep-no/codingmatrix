/**
 * 任务通知 Composable
 *
 * 提供 Vue 组件中使用的响应式任务状态
 */
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { useTaskStore } from '../stores/task.js'
import { taskNotificationService } from '../utils/taskNotification.js'
import api from '../utils/api.js'

export function useTaskNotifications() {
  const taskStore = useTaskStore()
  const isConnected = ref(false)
  const taskUpdates = ref(new Map())

  onMounted(() => {
    taskStore.initNotifications()
    isConnected.value = taskStore.isConnected
  })

  onUnmounted(() => {
    taskStore.disconnectNotifications()
  })

  /**
   * 订阅特定任务的更新
   */
  function subscribeToTask(taskId, callback) {
    return taskStore.subscribeToTask(taskId, data => {
      taskUpdates.value.set(taskId, data)
      if (callback) {
        callback(data)
      }
    })
  }

  /**
   * 获取任务列表
   */
  async function fetchTasks(params = {}) {
    const result = await api.getApiClient().listTasks(params)
    if (result && result.tasks) {
      result.tasks.forEach(task => {
        taskStore.tasks.set(task.task_id, task)
        if (task.status === 'pending' || task.status === 'running') {
          taskStore.addActiveTask(task)
        }
      })
    }
    return result
  }

  /**
   * 获取单个任务
   */
  async function fetchTask(taskId) {
    const task = await api.getApiClient().getTask(taskId)
    if (task) {
      taskStore.tasks.set(taskId, task)
    }
    return task
  }

  /**
   * 创建新任务
   */
  async function createTask(taskType, params = {}, priority = 'medium') {
    const result = await api.getApiClient().request('/tasks', {
      method: 'POST',
      body: JSON.stringify({
        task_type: taskType,
        params: params,
        priority: priority
      })
    })
    if (result) {
      taskStore.addActiveTask(result)
    }
    return result
  }

  /**
   * 取消任务
   */
  async function cancelTask(taskId) {
    const success = await api.getApiClient().cancelTask(taskId)
    if (success) {
      taskStore.updateTaskStatus(taskId, 'cancelled')
    }
    return success
  }

  /**
   * 重试任务
   */
  async function retryTask(taskId) {
    const result = await api.getApiClient().retryTask(taskId)
    if (result) {
      taskStore.addActiveTask(result)
    }
    return result
  }

  return {
    isConnected,
    taskUpdates,
    taskStore,
    subscribeToTask,
    fetchTasks,
    fetchTask,
    createTask,
    cancelTask,
    retryTask
  }
}

export default useTaskNotifications
