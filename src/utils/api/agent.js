/**
 * API Agent 专属模块 (快照/知识库/需求联想/性能/学习)
 */
export function createAgentClient(client) {
  return {
    // ========== 快照管理 ==========
    async getSnapshots(sessionId) {
      try {
        const response = await client.get(`/agent/snapshots/${sessionId}`)
        if (response.ok) {
          return await response.json()
        }
        return { snapshots: [] }
      } catch (error) {
        console.error('Failed to load snapshots:', error)
        return { snapshots: [] }
      }
    },

    async rollbackToSnapshot(sessionId, tag) {
      try {
        const response = await client.post(`/agent/rollback/${sessionId}?target_tag=${encodeURIComponent(tag)}`)
        if (response.ok) {
          return await response.json()
        }
        throw new Error('回滚失败')
      } catch (error) {
        throw new Error(error.message || '回滚失败')
      }
    },

    async getSnapshotDiff(sessionId, fromTag, toTag) {
      try {
        const response = await client.get('/agent/snapshot/diff', {
          session_id: sessionId,
          from_tag: fromTag,
          to_tag: toTag
        })
        if (response.ok) {
          return await response.json()
        }
        return { diffs: [] }
      } catch (error) {
        console.error('Failed to get snapshot diff:', error)
        return { diffs: [] }
      }
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
        throw new Error(error.message || '添加知识失败')
      }
    },

    async listKnowledge(category = '') {
      try {
        const params = category ? { category } : {}
        const response = await client.get('/agent/knowledge', params)
        if (response.ok) {
          return await response.json()
        }
        return { entries: [] }
      } catch (error) {
        console.error('Failed to load knowledge:', error)
        return { entries: [] }
      }
    },

    async searchKnowledge(query) {
      try {
        const response = await client.get('/agent/knowledge/search', { query })
        if (response.ok) {
          return await response.json()
        }
        return { results: [] }
      } catch (error) {
        console.error('Failed to search knowledge:', error)
        return { results: [] }
      }
    },

    // ========== 需求联想 ==========
    async getRequirementAssociations(requirement) {
      try {
        const response = await client.post('/agent/requirement-association', {
          requirement
        })
        if (response.ok) {
          return await response.json()
        }
        return { associations: [] }
      } catch (error) {
        console.error('Failed to get associations:', error)
        return { associations: [] }
      }
    },

    async confirmAssociation(associationId) {
      try {
        const response = await client.post('/agent/requirement-association/confirm', {
          association_id: associationId
        })
        if (response.ok) {
          return await response.json()
        }
        return { success: false }
      } catch (error) {
        return { success: false }
      }
    },

    async submitAssociationHelpful(associationId, helpful) {
      try {
        const response = await client.post('/agent/requirement-association/helpfulness', {
          association_id: associationId,
          helpful
        })
        if (response.ok) {
          return await response.json()
        }
        return { success: false }
      } catch (error) {
        return { success: false }
      }
    },

    async getAssociationStats() {
      try {
        const response = await client.get('/agent/requirement-association/stats')
        if (response.ok) {
          return await response.json()
        }
        return {}
      } catch (error) {
        return {}
      }
    },

    // ========== 性能监控 ==========
    async getPerformanceMetrics() {
      try {
        const response = await client.get('/agent/performance')
        if (response.ok) {
          return await response.json()
        }
        return {}
      } catch (error) {
        return {}
      }
    },

    async getPerformanceTrends() {
      try {
        const response = await client.get('/agent/performance/trends')
        if (response.ok) {
          return await response.json()
        }
        return {}
      } catch (error) {
        return {}
      }
    },

    async exportPerformance() {
      try {
        const response = await client.post('/agent/performance/export')
        if (response.ok) {
          return await response.json()
        }
        return null
      } catch (error) {
        return null
      }
    },

    // ========== 学习反馈 ==========
    async getLearningStats() {
      try {
        const response = await client.get('/agent/learning/stats')
        if (response.ok) {
          return await response.json()
        }
        return {}
      } catch (error) {
        return {}
      }
    },

    async getCommonErrors(fileType) {
      try {
        const response = await client.get(`/agent/learning/common-errors/${fileType}`)
        if (response.ok) {
          return await response.json()
        }
        return { errors: [] }
      } catch (error) {
        return { errors: [] }
      }
    },

    // ========== 并发限制 ==========
    async getRecommendedConcurrentLimits() {
      try {
        const response = await client.get('/agent/concurrent-limits/recommended')
        if (response.ok) {
          return await response.json()
        }
        return {}
      } catch (error) {
        return {}
      }
    },

    async updateConcurrentLimits(limits) {
      try {
        const response = await client.put('/agent/concurrent-limits', limits)
        if (response.ok) {
          return await response.json()
        }
        throw new Error('更新并发限制失败')
      } catch (error) {
        throw new Error(error.message || '更新并发限制失败')
      }
    },

    async getConcurrentLimitsHistory() {
      try {
        const response = await client.get('/agent/concurrent-limits/history')
        if (response.ok) {
          return await response.json()
        }
        return { history: [] }
      } catch (error) {
        return { history: [] }
      }
    },

    // ========== 缓存管理 ==========
    async getCacheStats() {
      try {
        const response = await client.get('/agent/cache/stats')
        if (response.ok) {
          return await response.json()
        }
        return {}
      } catch (error) {
        return {}
      }
    },

    async clearCache() {
      try {
        const response = await client.post('/agent/cache/clear')
        if (response.ok) {
          return await response.json()
        }
        throw new Error('清除缓存失败')
      } catch (error) {
        throw new Error(error.message || '清除缓存失败')
      }
    },

    // ========== Token 使用统计 ==========
    async getTokenUsage() {
      try {
        const response = await client.get('/agent/token-usage')
        if (response.ok) {
          return await response.json()
        }
        return {
          total_tokens: 0,
          prompt_tokens: 0,
          completion_tokens: 0,
          total_messages: 0,
          today_tokens: 0,
          this_month_tokens: 0,
          by_model: {}
        }
      } catch (error) {
        console.error('Failed to get token usage:', error)
        return {
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
}

export default { createAgentClient }
