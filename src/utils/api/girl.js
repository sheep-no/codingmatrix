/**
 * API GirlAI 模块 (v6.0 - 新增自定义角色、搜索、偏好)
 * 后端端点: /GirlAi (注意大写)
 */
async function parseResponse(response, fallback, message) {
  let data = fallback
  try {
    if (response.status !== 204) {
      if (typeof response.text === 'function') {
        const text = await response.text()
        data = text ? JSON.parse(text) : fallback
      } else if (typeof response.json === 'function') {
        data = await response.json()
      }
    }
  } catch (cause) {
    if (response.ok) throw new Error(message, { cause })
  }

  if (!response.ok) {
    const error = new Error(data?.detail || message)
    error.name = 'ApiError'
    error.status = response.status
    error.detail = data?.detail
    throw error
  }
  return data
}

export function createGirlClient(client) {
  return {
    async sendGirlAiMessage(prompt, characterId = 'gentle') {
      const response = await client.post('/GirlAi', {
        prompt,
        character_id: characterId
      })

      return parseResponse(response, {}, 'Send message failed')
    },

    async getGirlAiHistory(limit = 100, offset = 0) {
      const response = await client.get('/GirlAi/history', { limit, offset })
      return parseResponse(response, { records: [], total: 0, has_more: false }, 'Load history failed')
    },

    async deleteGirlAiHistory(recordIds = [], deleteAll = false) {
      const params = new URLSearchParams({ all: String(deleteAll) })
      recordIds.forEach(id => params.append('record_ids', id))
      const response = await client.delete(`/GirlAi/history?${params.toString()}`)
      return parseResponse(response, { status: 'deleted', count: 0 }, 'Delete history failed')
    },

    async searchGirlAiHistory(query, limit = 20) {
      const response = await client.get('/GirlAi/history/search', { q: query, limit })
      return parseResponse(response, { records: [] }, 'Search history failed')
    },

    async getCustomCharacters() {
      const response = await client.get('/GirlAi/characters/custom/list')
      return parseResponse(response, { characters: [] }, 'Load custom characters failed')
    },

    async createCustomCharacter(data) {
      const response = await client.post('/GirlAi/characters/custom', data)
      return parseResponse(response, {}, 'Create character failed')
    },

    async deleteCustomCharacter(characterId) {
      const response = await client.delete(`/GirlAi/characters/custom/${characterId}`)
      return parseResponse(response, { success: false }, 'Delete custom character failed')
    },

    async getUserPreferences() {
      const response = await client.get('/GirlAi/preferences')
      return parseResponse(response, { preferences: [] }, 'Load preferences failed')
    },

    async deletePreference(preferenceId) {
      const response = await client.delete(`/GirlAi/preferences/${preferenceId}`)
      return parseResponse(response, { success: false }, 'Delete preference failed')
    }
  }
}

export default { createGirlClient }
