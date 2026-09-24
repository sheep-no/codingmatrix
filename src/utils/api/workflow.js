/**
 * API 工作流模块
 */
export function createWorkflowClient(client) {
  return {
    async executeWorkflowStream(naturalLanguageRequest, sessionId = null, signal = null) {
      const response = await client.stream(
        '/workflow/execute',
        {
          natural_language_request: naturalLanguageRequest,
          export_workflow: true,
          session_id: sessionId || undefined
        },
        signal
      )

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`)
      }

      return response
    },

    async executeWorkflow(naturalLanguageRequest, sessionId = null) {
      const response = await client.post('/workflow/execute', {
        natural_language_request: naturalLanguageRequest,
        export_workflow: true,
        session_id: sessionId || undefined
      })

      return response
    },

    async getWorkflowStatus(workflowId) {
      const response = await client.get(`/workflow/status/${encodeURIComponent(workflowId)}`)
      if (!response.ok) throw new Error(`获取工作流状态失败 (${response.status})`)
      return response.json()
    },

    async importWorkflow(taskGraph) {
      const response = await client.post('/workflow/import', taskGraph)
      if (!response.ok) throw new Error(`导入工作流失败 (${response.status})`)
      return response.json()
    },

    async exportWorkflow(workflowId) {
      const response = await client.get(`/workflow/export/${encodeURIComponent(workflowId)}`)
      if (!response.ok) throw new Error(`导出工作流失败 (${response.status})`)
      return response.json()
    },

    async listWorkflowHistory(params = {}) {
      const response = await client.get('/workflow/history', params)
      if (!response.ok) throw new Error(`获取工作流历史失败 (${response.status})`)
      return response.json()
    },

    async deleteWorkflowHistory(workflowId) {
      const response = await client.delete(`/workflow/history/${encodeURIComponent(workflowId)}`)
      if (!response.ok) throw new Error(`删除工作流历史失败 (${response.status})`)
      return response.json()
    },

    async getWorkflowHistoryDetail(workflowId) {
      const response = await client.get(`/workflow/history/${encodeURIComponent(workflowId)}`)
      if (!response.ok) throw new Error(`获取工作流历史详情失败 (${response.status})`)
      return response.json()
    }
  }
}

export default { createWorkflowClient }
