/**
 * API 任务队列模块
 */
export function createTaskClient(client) {
  return {
    async listTasks(params = {}) {
      try {
        const response = await client.get('/tasks', params)
        if (response.ok) {
          return await response.json()
        }
        return { tasks: [] }
      } catch (error) {
        console.error('Failed to load tasks:', error)
        return { tasks: [] }
      }
    },

    async getTask(taskId) {
      try {
        const response = await client.get(`/tasks/${taskId}`)
        if (response.ok) {
          return await response.json()
        }
        return null
      } catch (error) {
        return null
      }
    },

    async cancelTask(taskId) {
      try {
        const response = await client.post('/tasks/cancel', { task_id: taskId })
        if (response.ok) {
          return await response.json()
        }
        return { success: false }
      } catch (error) {
        return { success: false }
      }
    },

    async retryTask(taskId) {
      try {
        const response = await client.post('/tasks/retry', { task_id: taskId })
        if (response.ok) {
          return await response.json()
        }
        return { success: false }
      } catch (error) {
        return { success: false }
      }
    }
  }
}

export default { createTaskClient }
