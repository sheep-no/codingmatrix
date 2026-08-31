/**
 * API GirlAI 模块 (v6.0 - 新增自定义角色、搜索、偏好)
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
      const response = await client.get('/GirlAi/history', { limit, offset })
      if (response.ok) {
        return await response.json()
      }
      const error = await response.json()
      throw new Error(error.detail || 'Load history failed')
    },

    async deleteGirlAiHistory(recordIds = [], deleteAll = false) {
      const params = new URLSearchParams({ all: String(deleteAll) })
      recordIds.forEach(id => params.append('record_ids', id))
      const response = await client.delete(`/GirlAi/history?${params.toString()}`)
      if (response.ok) {
        return await response.json()
      }
      const error = await response.json()
      throw new Error(error.detail || 'Delete history failed')
    },

    async searchGirlAiHistory(query, limit = 20) {
      try {
        const response = await client.get('/GirlAi/history/search', { q: query, limit })
        if (response.ok) {
          return await response.json()
        }
        return { records: [] }
      } catch (error) {
        console.error('Failed to search GirlAI history:', error)
        return { records: [] }
      }
    },

    async getCustomCharacters() {
      try {
        const response = await client.get('/GirlAi/characters/custom/list')
        if (response.ok) {
          return await response.json()
        }
        return { characters: [] }
      } catch (error) {
        console.error('Failed to load custom characters:', error)
        return { characters: [] }
      }
    },

    async createCustomCharacter(data) {
      const response = await client.post('/GirlAi/characters/custom', data)
      if (response.ok) {
        return await response.json()
      }
      const error = await response.json()
      throw new Error(error.detail || 'Create character failed')
    },

    async deleteCustomCharacter(characterId) {
      try {
        const response = await client.delete(`/GirlAi/characters/custom/${characterId}`)
        if (response.ok) {
          return await response.json()
        }
        return { success: false }
      } catch (error) {
        console.error('Failed to delete custom character:', error)
        return { success: false }
      }
    },

    async getUserPreferences() {
      try {
        const response = await client.get('/GirlAi/preferences')
        if (response.ok) {
          return await response.json()
        }
        return { preferences: [] }
      } catch (error) {
        console.error('Failed to load preferences:', error)
        return { preferences: [] }
      }
    },

    async deletePreference(preferenceId) {
      try {
        const response = await client.delete(`/GirlAi/preferences/${preferenceId}`)
        if (response.ok) {
          return await response.json()
        }
        return { success: false }
      } catch (error) {
        console.error('Failed to delete preference:', error)
        return { success: false }
      }
    }
  }
}

export default { createGirlClient }
