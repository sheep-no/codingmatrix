/**
 * API 工作流模块
 */
export function createWorkflowClient(client) {
  return {
    async executeWorkflowStream(naturalLanguageRequest, sessionId = null, signal = null) {
      const token =
        localStorage.getItem('access_token') ||
        localStorage.getItem('token') ||
        sessionStorage.getItem('access_token') ||
        sessionStorage.getItem('token')

      const response = await fetch('/api/v1/workflow/execute', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: token ? `Bearer ${token}` : ''
        },
        body: JSON.stringify({
          natural_language_request: naturalLanguageRequest,
          export_workflow: true,
          session_id: sessionId || undefined
        }),
        signal
      })

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`)
      }

      return response
    },

    async executeWorkflow(naturalLanguageRequest, sessionId = null) {
      const token =
        localStorage.getItem('access_token') ||
        localStorage.getItem('token') ||
        sessionStorage.getItem('access_token') ||
        sessionStorage.getItem('token')

      const response = await client.post('/workflow/execute', {
        natural_language_request: naturalLanguageRequest,
        export_workflow: true,
        session_id: sessionId || undefined
      })

      return response
    }
  }
}

export default { createWorkflowClient }
