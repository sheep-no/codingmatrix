/**
 * API GirlAI 模块 (v5.0.2 端点修复)
 * 后端端点: /GirlAi (注意大写)
 */
export function createGirlClient(client) {
  return {
    async sendGirlAiMessage(prompt, characterId = 'gentle') {
      const response = await client.post('/GirlAi', {
        prompt,
        character_id: characterId
      })

      if (response.ok) {
        return await response.json()
      } else {
        const error = await response.json()
        throw new Error(error.detail || 'Send message failed')
      }
    },

    async getGirlAiHistory(limit = 100, offset = 0) {
      try {
        const response = await client.get('/GirlAi/history', { limit, offset })
        if (response.ok) {
          return await response.json()
        }
        return { records: [] }
      } catch (error) {
        console.error('Failed to load GirlAI history:', error)
        return { records: [] }
      }
    },

    async deleteGirlAiHistory(recordIds = [], deleteAll = false) {
      try {
        const response = await client.delete('/GirlAi/history', {
          record_ids: recordIds,
          delete_all: deleteAll
        })
        if (response.ok) {
          return await response.json()
        }
        return { success: false }
      } catch (error) {
        console.error('Failed to delete GirlAI history:', error)
        return { success: false }
      }
    }
  }
}

export default { createGirlClient }
