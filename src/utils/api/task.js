/**
 * API 任务队列模块 (v5.0.2 端点修复)
 * 后端端点:
 * - GET /tasks - 列表
 * - GET /tasks/{task_id} - 详情
 * - DELETE /tasks/{task_id} - 取消
 * - POST /tasks/{task_id}/retry - 重试
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
        const response = await client.delete(`/tasks/${taskId}`)
        if (response.ok) {
          return await response.json()
        }
        return { success: false }
      } catch (error) {
        console.error('Failed to cancel task:', error)
        return { success: false }
      }
    },

    async retryTask(taskId) {
      try {
        const response = await client.post(`/tasks/${taskId}/retry`)
        if (response.ok) {
          return await response.json()
        }
        return { success: false }
      } catch (error) {
        console.error('Failed to retry task:', error)
        return { success: false }
      }
    }
  }
}

export default { createTaskClient }
