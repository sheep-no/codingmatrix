/**
 * API Agent 专属模块 (快照/知识库/需求联想/性能/学习)
 */
export function createAgentClient(client) {
  // 统一错误处理
  function handleError(error, context) {
    console.error(`${context}:`, error)
    throw new Error(error.message || `${context}失败`)
  }

  // 统一请求封装
  async function request(method, url, data = null, params = null) {
    try {
      let response
      if (method === 'get') {
        response = await client.get(url, params)
      } else if (method === 'post') {
        response = await client.post(url, data)
      } else if (method === 'put') {
        response = await client.put(url, data)
      }

      if (response.ok) {
        return await response.json()
      }
      return null
    } catch (error) {
      console.error(`Request ${method} ${url} failed:`, error)
      return null
    }
  }

  return {
    // ========== 快照管理 ==========
    async getSnapshots(sessionId) {
      return await request('get', `/agent/snapshots/${sessionId}`) || { snapshots: [] }
    },

    async rollbackToSnapshot(sessionId, tag) {
      try {
        const response = await client.post(`/agent/rollback/${sessionId}?target_tag=${encodeURIComponent(tag)}`)
        if (response.ok) {
          return await response.json()
        }
        throw new Error('回滚失败')
      } catch (error) {
        handleError(error, '回滚')
      }
    },

    async getSnapshotDiff(sessionId, fromTag, toTag) {
      return await request('get', '/agent/snapshot/diff', null, {
        session_id: sessionId,
        from_tag: fromTag,
        to_tag: toTag
      }) || { diffs: [] }
    },

    // ========== 知识库管理 ==========
    async addKnowledge(content, category = '', tags = []) {
      try {
        const response = await client.post('/agent/knowledge', {
          content,
          category,
          tags
        })
        if (response.ok) {
          return await response.json()
        }
        throw new Error('添加知识失败')
      } catch (error) {
        handleError(error, '添加知识')
      }
    },

    async listKnowledge(category = '') {
      return await request('get', '/agent/knowledge', null, category ? { category } : {}) || { entries: [] }
    },

    async searchKnowledge(query) {
      return await request('get', '/agent/knowledge/search', null, { query }) || { results: [] }
    },

    // ========== 需求联想 ==========
    async getRequirementAssociations(requirement) {
      return await request('post', '/agent/requirement-association', { requirement }) || { associations: [] }
    },

    async confirmAssociation(associationId) {
      return await request('post', '/agent/requirement-association/confirm', { association_id: associationId }) || { success: false }
    },

    async submitAssociationHelpful(associationId, helpful) {
      return await request('post', '/agent/requirement-association/helpfulness', {
        association_id: associationId,
        helpful
      }) || { success: false }
    },

    async getAssociationStats() {
      return await request('get', '/agent/requirement-association/stats') || {}
    },

    // ========== 性能监控 ==========
    async getPerformanceMetrics() {
      return await request('get', '/agent/performance') || {}
    },

    async getPerformanceTrends() {
      return await request('get', '/agent/performance/trends') || {}
    },

    async exportPerformance() {
      return await request('post', '/agent/performance/export') || null
    },

    // ========== 学习反馈 ==========
    async getLearningStats() {
      return await request('get', '/agent/learning/stats') || {}
    },

    async getCommonErrors(fileType) {
      return await request('get', `/agent/learning/common-errors/${fileType}`) || { errors: [] }
    },

    // ========== 并发限制 ==========
    async getRecommendedConcurrentLimits() {
      return await request('get', '/agent/concurrent-limits/recommended') || {}
    },

    async updateConcurrentLimits(limits) {
      try {
        const response = await client.put('/agent/concurrent-limits', limits)
        if (response.ok) {
          return await response.json()
        }
        throw new Error('更新并发限制失败')
      } catch (error) {
        handleError(error, '更新并发限制')
      }
    },

    async getConcurrentLimitsHistory() {
      return await request('get', '/agent/concurrent-limits/history') || { history: [] }
    },

    // ========== 缓存管理 ==========
    async getCacheStats() {
      return await request('get', '/agent/cache/stats') || {}
    },

    async clearCache() {
      try {
        const response = await client.post('/agent/cache/clear')
        if (response.ok) {
          return await response.json()
        }
        throw new Error('清除缓存失败')
      } catch (error) {
        handleError(error, '清除缓存')
      }
    },

    // ========== Token 使用统计 ==========
    async getTokenUsage() {
      return await request('get', '/agent/token-usage') || {
        total_tokens: 0,
        prompt_tokens: 0,
        completion_tokens: 0,
        total_messages: 0,
        today_tokens: 0,
        this_month_tokens: 0,
        by_model: {}
      }
    }
  }
}

export default { createAgentClient }
