/**
 * API PPT 生成模块
 *
 * 后端端点:
 * - POST /pptx/generate_task       - 异步任务生成
 * - GET  /pptx/download/{ppt_id}   - 下载
 * - GET  /pptx/preview/{ppt_id}    - HTML 预览
 * - GET  /pptx/{ppt_id}/slides     - 幻灯片数据
 * - DELETE /pptx/{task_id}/cancel  - 取消任务
 * - POST /pptx/{task_id}/update    - 增量更新
 * - POST /pptx/{task_id}/modify    - 视觉增强修改
 * - GET  /pptx/{task_id}/analyze   - 分析 PPT 状态
 * - GET  /pptx/templates           - 获取模板列表
 * - GET  /pptx/history             - 获取历史记录
 * - DELETE /pptx/history/{task_id} - 删除历史记录
 * - GET  /pptx/history/stats       - 获取统计信息
 * - WS   /ws/ppt/{task_id}         - WebSocket 进度推送
 */
export function createPptClient(client) {
  return {
    async createOutline(payload) {
      const response = await client.post('/pptx/outlines', payload)
      if (response.ok) return await response.json()
      const error = await response.json()
      throw new Error(error.detail || '创建大纲失败')
    },

    async updateOutline(outlineId, payload) {
      const response = await client.patch(`/pptx/outlines/${outlineId}`, payload)
      if (response.ok) return await response.json()
      const error = await response.json()
      throw new Error(error.detail || '更新大纲失败')
    },

    async deleteOutline(outlineId) {
      const response = await client.delete(`/pptx/outlines/${outlineId}`)
      if (response.ok) return await response.json()
      const error = await response.json()
      throw new Error(error.detail || '删除大纲失败')
    },

    async approveOutline(outlineId) {
      const response = await client.post(`/pptx/outlines/${outlineId}/approve`)
      if (response.ok) return await response.json()
      const error = await response.json()
      throw new Error(error.detail || '批准大纲失败')
    },

    async generateFromOutline(outlineId, qualityMode = 'standard', outlineVersion = null) {
      const response = await client.post(`/pptx/outlines/${outlineId}/generate`, {
        quality_mode: qualityMode,
        outline_version: outlineVersion,
      })
      if (response.ok) return await response.json()
      const error = await response.json()
      throw new Error(error.detail || '创建 PPT 任务失败')
    },

    async getQualityReport(taskId) {
      const response = await client.get(`/pptx/${taskId}/quality-report`)
      if (response.ok) return await response.json()
      return null
    },

    async regenerateOutlineSlide(outlineId, slideId, qualityMode = 'standard', slide = null) {
      const response = await client.post(`/pptx/outlines/${outlineId}/slides/${slideId}/regenerate`, {
        quality_mode: qualityMode,
        slide,
      })
      if (response.ok) return await response.json()
      const error = await response.json()
      throw new Error(error.detail || '页面再生成失败')
    },

    async createPptTask(prompt, conversationId = null, api_key_token = null, options = {}) {
      const response = await client.post('/pptx/generate_task', {
        prompt,
        conversation_id: conversationId,
        api_key_token,
         template: options.template || options.template_id || 'auto',
         slide_count: options.slide_count || 10,
         options: {
           auto_images: options.auto_images !== false,
           enable_animation: options.enable_animation !== false,
         },
        output_format: options.output_format || 'pptx',
      })
      if (response.ok) {
        return await response.json()
      } else {
        const error = await response.json()
        throw new Error(error.detail || 'Create task failed')
      }
    },

    async getPPTSlides(pptId) {
      try {
        const response = await client.get(`/pptx/${pptId}/slides`)
        if (response.ok) {
          return await response.json()
        }
        return null
      } catch (e) {
        console.debug('[ppt] 获取幻灯片失败:', e.message)
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
      } catch {
        return null
      }
    },

    async downloadPPT(pptId, format = 'pptx') {
      try {
        if (format === 'pdf') return await this.downloadPDF(pptId)
        const response = await client.get(`/pptx/download/${pptId}?format=${format}`)
        if (response.ok) {
          return await response.blob()
        }
        throw new Error('Download failed')
      } catch (error) {
        throw new Error(error.message || 'Download failed', { cause: error })
      }
    },

    async downloadPDF(pptId) {
      const response = await client.get(`/pptx/download/${pptId}/pdf`)
      if (response.ok) return await response.blob()
      const error = await response.json().catch(() => ({}))
      throw new Error(error.detail || 'PDF 下载失败')
    },

    async cancelPptTask(taskId) {
      try {
        const response = await client.delete(`/pptx/${taskId}/cancel`)
        if (response.ok) {
          return await response.json()
        }
        return { success: false }
      } catch {
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

    async modifyPpt(taskId, userInput, apiKeyToken = null, analyzeBeforeModify = true) {
      try {
        const response = await client.post(`/pptx/${taskId}/modify`, {
          user_input: userInput,
          api_key_token: apiKeyToken,
          analyze_before_modify: analyzeBeforeModify,
        })
        if (response.ok) {
          return await response.json()
        }
        const error = await response.json()
        throw new Error(error.detail || 'Modify failed')
      } catch (error) {
        throw new Error(error.message || 'Modify failed', { cause: error })
      }
    },

    async analyzePpt(taskId, slideNumber = null) {
      try {
        const url = slideNumber
          ? `/pptx/${taskId}/analyze?slide_number=${slideNumber}`
          : `/pptx/${taskId}/analyze`
        const response = await client.get(url)
        if (response.ok) {
          return await response.json()
        }
        return null
      } catch {
        return null
      }
    },

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
      } catch {
        return { templates: [] }
      }
    },

    async getHistory(page = 1, pageSize = 20) {
      try {
        const response = await client.get(
          `/pptx/history?page=${page}&page_size=${pageSize}`
        )
        if (response.ok) {
          return await response.json()
        }
        return { records: [], total: 0 }
      } catch {
        return { records: [], total: 0 }
      }
    },

    async deleteHistory(taskId) {
      try {
        const response = await client.delete(`/pptx/history/${taskId}`)
        if (response.ok) {
          return await response.json()
        }
        return { success: false }
      } catch {
        return { success: false }
      }
    },

    async getStats() {
      try {
        const response = await client.get('/pptx/history/stats')
        if (response.ok) {
          return await response.json()
        }
        return { total: 0, completed: 0, failed: 0 }
      } catch {
        return { total: 0, completed: 0, failed: 0 }
      }
    }
  }
}

export default { createPptClient }
