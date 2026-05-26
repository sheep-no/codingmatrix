/**
 * API AiCloud 沙箱环境模块
 * 后端端点: /api/v1/aicloud
 */
export function createAiCloudClient(client) {
  return {
    // ========== 聊天 ==========
    async chat(message, params = {}, api_key_token = null) {
      const response = await client.post('/aicloud/chat', {
        message,
        api_key_token,
        ...params
      })
      if (response.ok) {
        return await response.json()
      }
      throw new Error('AiCloud 聊天失败')
    },

    async chatStream(message, signal, params = {}, api_key_token = null) {
      const response = await client.stream('/aicloud/chat/stream', {
        message,
        api_key_token,
        ...params
      }, signal)
      if (response.ok) {
        return response
      }
      throw new Error('AiCloud 流式聊天失败')
    },

    // ========== 沙箱文件操作 ==========
    async readFile(path) {
      const response = await client.post('/aicloud/read', { path })
      if (response.ok) {
        return await response.json()
      }
      throw new Error('读取沙箱文件失败')
    },

    async writeFile(path, content) {
      const response = await client.post('/aicloud/write', { path, content })
      if (response.ok) {
        return await response.json()
      }
      throw new Error('写入沙箱文件失败')
    },

    async executeCode(code, language = 'python') {
      const response = await client.post('/aicloud/execute', {
        code,
        language
      })
      if (response.ok) {
        return await response.json()
      }
      throw new Error('沙箱代码执行失败')
    },

    // ========== 历史消息 ==========
    async getHistory(limit = 50, offset = 0) {
      try {
        const response = await client.get('/aicloud/history', { limit, offset })
        if (response.ok) {
          return await response.json()
        }
        return { messages: [] }
      } catch (error) {
        return { messages: [] }
      }
    },

    async searchHistory(query) {
      try {
        const response = await client.get('/aicloud/history/search', { query })
        if (response.ok) {
          return await response.json()
        }
        return { results: [] }
      } catch (error) {
        return { results: [] }
      }
    },

    async exportHistory(sessionId) {
      try {
        const response = await client.get(`/aicloud/history/export/${sessionId}`)
        if (response.ok) {
          return await response.json()
        }
        return null
      } catch (error) {
        return null
      }
    },

    async deleteHistory(sessionId) {
      try {
        const response = await client.delete(`/aicloud/history/${sessionId}`)
        if (response.ok) {
          return await response.json()
        }
        return { success: false }
      } catch (error) {
        return { success: false }
      }
    },

    // ========== 审查列表 ==========
    async getAuditLogs(params = {}) {
      try {
        const response = await client.get('/aicloud/audit-logs', params)
        if (response.ok) {
          return await response.json()
        }
        return { logs: [] }
      } catch (error) {
        return { logs: [] }
      }
    },

    async getReviews() {
      try {
        const response = await client.get('/aicloud/reviews')
        if (response.ok) {
          return await response.json()
        }
        return { reviews: [] }
      } catch (error) {
        return { reviews: [] }
      }
    },

    async approveReview(reviewId) {
      try {
        const response = await client.post('/aicloud/reviews/approve', {
          review_id: reviewId
        })
        if (response.ok) {
          return await response.json()
        }
        return { success: false }
      } catch (error) {
        return { success: false }
      }
    },

    async rejectReview(reviewId) {
      try {
        const response = await client.post('/aicloud/reviews/reject', {
          review_id: reviewId
        })
        if (response.ok) {
          return await response.json()
        }
        return { success: false }
      } catch (error) {
        return { success: false }
      }
    },

    async toggleReview(enabled) {
      try {
        const response = await client.post('/aicloud/reviews/toggle', {
          enabled
        })
        if (response.ok) {
          return await response.json()
        }
        return { success: false }
      } catch (error) {
        return { success: false }
      }
    },

    // ========== 模型列表 ==========
    async getModels() {
      try {
        const response = await client.get('/aicloud/models')
        if (response.ok) {
          return await response.json()
        }
        return { models: [] }
      } catch (error) {
        return { models: [] }
      }
    },

    // ========== 知识库 ==========
    async uploadKnowledge(file, metadata = {}) {
      const formData = new FormData()
      formData.append('file', file)
      Object.keys(metadata).forEach(key => {
        formData.append(key, metadata[key])
      })

      const response = await fetch(
        `${import.meta.env.VITE_API_BASE || '/api/v1'}/aicloud/knowledge/upload`,
        {
          method: 'POST',
          body: formData,
          credentials: 'include'
        }
      )
      if (response.ok) {
        return await response.json()
      }
      throw new Error('上传知识库文档失败')
    },

    async listKnowledgeDocs() {
      try {
        const response = await client.get('/aicloud/knowledge/docs')
        if (response.ok) {
          return await response.json()
        }
        return { docs: [] }
      } catch (error) {
        return { docs: [] }
      }
    },

    async deleteKnowledgeDoc(docId) {
      try {
        const response = await client.delete(`/aicloud/knowledge/docs/${docId}`)
        if (response.ok) {
          return await response.json()
        }
        return { success: false }
      } catch (error) {
        return { success: false }
      }
    },

    async searchKnowledge(query) {
      try {
        const response = await client.post('/aicloud/knowledge/search', { query })
        if (response.ok) {
          return await response.json()
        }
        return { results: [] }
      } catch (error) {
        return { results: [] }
      }
    }
  }
}

export default { createAiCloudClient }
