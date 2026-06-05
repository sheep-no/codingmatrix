/**
 * API PPT 生成模块 (v6.0 - 全面改进版)
 * 后端端点:
 * - POST /pptx/generate_task - 异步任务生成
 * - POST /pptx/generate - 同步生成
 * - GET /pptx/download/{ppt_id} - 下载
 * - GET /pptx/preview/{ppt_id} - 预览
 * - GET /pptx/{ppt_id}/slides - 幻灯片数据
 * - DELETE /pptx/{task_id}/cancel - 取消任务
 * - POST /pptx/{task_id}/update - 增量更新
 * - GET /pptx/templates - 获取模板列表
 * - GET /pptx/history - 获取历史记录
 * - DELETE /pptx/history/{task_id} - 删除历史记录
 * - GET /pptx/preview/html/{ppt_id} - HTML 预览
 * - WS /ws/ppt/{task_id} - WebSocket 进度推送
 */
export function createPptClient(client) {
  return {
    async generatePPT(pptData) {
      const response = await client.post('/pptx/generate', pptData)
      if (response.ok) {
        return await response.json()
      } else {
        const error = await response.json()
        throw new Error(error.detail || 'Generate failed')
      }
    },

    async getPPTSlides(pptId) {
      try {
        const response = await client.get(`/pptx/${pptId}/slides`)
        if (response.ok) {
          return await response.json()
        }
        return null
      } catch {
        return null
      }
    },

    async createPptTask(prompt, conversationId = null, api_key_token = null, options = {}) {
      const response = await client.post('/pptx/generate_task', {
        prompt,
        conversation_id: conversationId,
        api_key_token,
        template_id: options.template_id || 'modern',
        slide_count: options.slide_count || 10,
        auto_images: options.auto_images !== false,
        enable_animation: options.enable_animation !== false,
        output_format: options.output_format || 'pptx', // pptx, pdf, both
      })
      if (response.ok) {
        return await response.json()
      } else {
        const error = await response.json()
        throw new Error(error.detail || 'Create task failed')
      }
    },

    async generatePptx(prompt, conversationId = null, params = {}, api_key_token = null) {
      const response = await client.post('/pptx/generate', {
        topic: prompt,
        conversation_id: conversationId,
        api_key_token,
        ...params
      })
      if (response.ok) {
        return await response.json()
      } else {
        const error = await response.json()
        throw new Error(error.detail || 'Generate failed')
      }
    },

    async previewPPT(pptId) {
      try {
        const response = await client.get(`/pptx/preview/${pptId}`)
        if (response.ok) {
          return await response.text()
        }
        return null
      } catch (error) {
        return null
      }
    },

    async previewPPTHtml(pptId) {
      try {
        const response = await client.get(`/pptx/preview/${pptId}`)
        if (response.ok) {
          return await response.text()
        }
        return null
      } catch (error) {
        return null
      }
    },

    async downloadPPT(pptId, format = 'pptx') {
      try {
        const response = await client.get(`/pptx/download/${pptId}?format=${format}`)
        if (response.ok) {
          return await response.blob()
        }
        throw new Error('Download failed')
      } catch (error) {
        throw new Error(error.message || 'Download failed', { cause: error })
      }
    },

    async cancelPptTask(taskId) {
      try {
        const response = await client.delete(`/pptx/${taskId}/cancel`)
        if (response.ok) {
          return await response.json()
        }
        return { success: false }
      } catch (error) {
        return { success: false }
      }
    },

    async updatePpt(taskId, data) {
      try {
        const response = await client.post(`/pptx/${taskId}/update`, data)
        if (response.ok) {
          return await response.json()
        }
        throw new Error('Update failed')
      } catch (error) {
        throw new Error(error.message || 'Update failed', { cause: error })
      }
    },

    // 新增：获取模板列表
    async getTemplates(category = null) {
      try {
        const url = category
          ? `/pptx/templates?category=${category}`
          : '/pptx/templates'
        const response = await client.get(url)
        if (response.ok) {
          return await response.json()
        }
        return { templates: [] }
      } catch (error) {
        console.error('获取模板列表失败:', error)
        return { templates: [] }
      }
    },

    // 新增：获取历史记录
    async getHistory(page = 1, pageSize = 20) {
      try {
        const response = await client.get(
          `/pptx/history?page=${page}&page_size=${pageSize}`
        )
        if (response.ok) {
          return await response.json()
        }
        return { records: [], total: 0 }
      } catch (error) {
        console.error('获取历史记录失败:', error)
        return { records: [], total: 0 }
      }
    },

    // 新增：删除历史记录
    async deleteHistory(taskId) {
      try {
        const response = await client.delete(`/pptx/history/${taskId}`)
        if (response.ok) {
          return await response.json()
        }
        return { success: false }
      } catch (error) {
        return { success: false }
      }
    },

    // 新增：获取统计信息
    async getStats() {
      try {
        const response = await client.get('/pptx/history/stats')
        if (response.ok) {
          return await response.json()
        }
        return { total: 0, completed: 0, failed: 0 }
      } catch (error) {
        return { total: 0, completed: 0, failed: 0 }
      }
    },

    // 新增：下载 PDF
    async downloadPDF(pptId) {
      // PDF 导出暂未实现，后端会回退到 PPTX 格式
      console.warn('PDF 导出暂未实现，将下载 PPTX 格式')
      return this.downloadPPT(pptId, 'pptx')
    }
  }
}

export default { createPptClient }
