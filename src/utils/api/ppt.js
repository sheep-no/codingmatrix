/**
 * API PPT 生成模块 (v5.0.2 端点修复)
 * 后端端点:
 * - POST /pptx/generate_task - 异步任务生成
 * - POST /pptx/generate - 同步生成
 * - GET /pptx/download/{ppt_id} - 下载
 * - GET /pptx/preview/{ppt_id} - 预览
 * - GET /pptx/{ppt_id}/slides - 幻灯片数据
 * - DELETE /pptx/{task_id}/cancel - 取消任务
 * - POST /pptx/{task_id}/update - 增量更新
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

    async createPptTask(prompt, conversationId = null, api_key_token = null) {
      const response = await client.post('/pptx/generate_task', {
        prompt,
        conversation_id: conversationId,
        api_key_token
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

    async downloadPPT(pptId) {
      try {
        const response = await client.get(`/pptx/download/${pptId}`)
        if (response.ok) {
          return await response.blob()
        }
        throw new Error('Download failed')
      } catch (error) {
        throw new Error(error.message || 'Download failed')
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
        throw new Error(error.message || 'Update failed')
      }
    }
  }
}

export default { createPptClient }
