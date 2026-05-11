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
    }
  }
}

export default { createChatClient }
