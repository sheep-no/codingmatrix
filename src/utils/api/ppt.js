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
    async createPptTask(prompt, conversationId = null, api_key_token = null, options = {}) {
      const response = await client.post('/pptx/generate_task', {
        prompt,
        conversation_id: conversationId,
        api_key_token,
         template: options.template || options.template_id || 'modern',
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
    },

    async downloadPDF(pptId) {
      try {
        const response = await client.get(`/pptx/download/${pptId}/pdf`)
        if (response.ok) {
          return await response.blob()
        }
        throw new Error('PDF 导出需要服务器安装 LibreOffice')
      } catch (error) {
        throw new Error(error.message || 'PDF 导出失败', { cause: error })
      }
    }
  }
}

export default { createPptClient }
