/**
 * API PPT 生成模块
 */
export function createPptClient(client) {
  return {
    async generatePPT(pptData) {
      try {
        const response = await client.post('/pptx/generate', pptData)
        if (response.ok) {
          return await response.json()
        } else {
          const error = await response.json()
          throw new Error(error.detail || 'Generate failed')
        }
      } catch (error) {
        throw error
      }
    },

    async getPPTSlides(pptId) {
      try {
        const response = await client.get(`/pptx/${pptId}/slides`)
        if (response.ok) {
          return await response.json()
        }
        return null
      } catch (error) {
        return null
      }
    },

    async createPptTask(prompt, conversationId = null) {
      try {
        const response = await client.post('/pptx/create_task', {
          prompt,
          conversation_id: conversationId
        })
        if (response.ok) {
          return await response.json()
        } else {
          const error = await response.json()
          throw new Error(error.detail || 'Create task failed')
        }
      } catch (error) {
        throw error
      }
    },

    async generatePptx(prompt, conversationId = null, params = {}) {
      try {
        const response = await client.post('/pptx/generate', {
          topic: prompt,
          conversation_id: conversationId,
          ...params
        })
        if (response.ok) {
          return await response.json()
        } else {
          const error = await response.json()
          throw new Error(error.detail || 'Generate failed')
        }
      } catch (error) {
        throw error
      }
    },

    async previewPPT(pptId) {
      try {
        const response = await client.get(`/pptx/preview/${pptId}`)
        if (response.ok) {
          return await response.text()
        }
        return null
      } catch (error) {
        return null
      }
    }
  }
}

export default { createPptClient }
