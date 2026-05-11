  async stopSession(sessionId) {
    try {
      const response = await client.post(`/agent/session/${sessionId}/action`, {
        action: "cancel"
      })
      if (response.ok) {
        return await response.json()
      }
      throw new Error('停止会话失败')
    } catch (error) {
      throw error
    }
  },

  async deleteSession(sessionId) {
    try {
      const response = await client.delete(`/agent/session/${sessionId}`)
      if (response.ok) {
        return await response.json()
      }
      throw new Error('删除会话失败')
    } catch (error) {
      throw error
    }
  },