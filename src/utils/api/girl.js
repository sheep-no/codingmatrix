/**
 * API GirlAI 模块
 */
export function createGirlClient(client) {
  return {
    async sendGirlAiMessage(prompt, characterId = 'gentle') {
      try {
        const response = await client.post('/girlai/chat', {
          prompt,
          character_id: characterId
        })

        if (response.ok) {
          return await response.json()
        } else {
          const error = await response.json()
          throw new Error(error.detail || 'Send message failed')
        }
      } catch (error) {
        throw error
      }
    },

    async getGirlAiHistory(limit = 100, offset = 0) {
      try {
        const response = await client.get('/girlai/history', { limit, offset })
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
        const response = await client.post('/girlai/history/delete', {
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
