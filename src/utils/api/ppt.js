/**
 * API PPT 生成模块
 */
export function createPptClient(client) {
  return {
    async generatePPT(pptData) {
      try {
        const response = await client.post('/aiGeneratorPptx/generate', pptData)
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
        const response = await client.get(`/aiGeneratorPptx/ppt/${pptId}`)
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
        const response = await client.post('/aiGeneratorPptx/create_task', {
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
        const response = await client.post('/aiGeneratorPptx/generate_pptx', {
          prompt,
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
    }
  }
}

export default { createPptClient }
