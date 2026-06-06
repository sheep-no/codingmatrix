/**
 * API 聊天历史模块
 */
export function createChatClient(client) {
  return {
    async getChatHistory(limit = 20, offset = 0, promptKeyword = null) {
      try {
        const body = { limit, offset }
        if (promptKeyword) body.prompt_keyword = promptKeyword
        const response = await client.post('/history', body)
        if (response.ok) {
          return await response.json()
        }
        return { items: [], total: 0 }
      } catch (error) {
        console.error('Failed to load chat history:', error)
        return { items: [], total: 0 }
      }
    },

    async getConversationHistory(conversationId, lastHistoryId = null, limit = 50) {
      try {
        const response = await client.post('/conversation/history', {
          conversation_id: conversationId,
          last_history_id: lastHistoryId,
          limit
        })
        if (response.ok) {
          return await response.json()
        }
        return { items: [] }
      } catch (error) {
        console.error('Failed to load conversation history:', error)
        return { items: [] }
      }
    },

    async deleteChatHistory(conversationIds, all = false) {
      const ids = Array.isArray(conversationIds) ? conversationIds : [conversationIds]
      const params = ids.map(id => `conversation_ids=${encodeURIComponent(id)}`).join('&')
      const url = `/code/history?${params}&all=${all}`
      return await client.request(url, {
        method: 'DELETE'
      })
    }
  }
}

export default { createChatClient }
