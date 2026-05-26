/**
 * API 聊天历史模块
 */
export function createChatClient(client) {
  return {
    async getChatHistory(limit = 100, offset = 0) {
      try {
        const response = await client.get('/code/history', { limit, offset })
        if (response.ok) {
          return await response.json()
        }
        return { history: [] }
      } catch (error) {
        console.error('Failed to load chat history:', error)
        return { history: [] }
      }
    },

    async getConversationHistory(conversationId) {
      try {
        const response = await client.get(`/code/conversation/${conversationId}`)
        if (response.ok) {
          return await response.json()
        }
        return { messages: [] }
      } catch (error) {
        console.error('Failed to load conversation history:', error)
        return { messages: [] }
      }
    },

    async deleteChatHistory(conversationIds) {
      const ids = Array.isArray(conversationIds) ? conversationIds : [conversationIds]
      const params = ids.map(id => `conversation_ids=${id}`).join('&')
      const url = `/code/history?${params}`
      
      // 返回原始 Response 对象，与 api.post 等行为保持一致
      return await client.request(url, {
        method: 'DELETE'
      })
    }
  }
}

export default { createChatClient }
