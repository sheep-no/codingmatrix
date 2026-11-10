/**
 * API Kolors 图像生成模块
 * 后端端点: /api/v1/kolors
 */
async function readError(response, fallback) {
  const payload = await response.json().catch(() => ({}))
  return new Error(payload.detail || payload.message || fallback)
}

export function createKolorsClient(client) {
  return {
    async textToImage(prompt, params = {}, apiKeyToken = null, signal = null) {
      const response = await client.request('/kolors/text-to-image', {
        method: 'POST',
        body: JSON.stringify({
          prompt,
          api_key_token: apiKeyToken,
          ...params
        }),
        signal
      })
      if (!response.ok) {
        throw await readError(response, '文生图失败')
      }
      return await response.json()
    },

    async imageToImage(promptOrFormData, params = {}, apiKeyToken = null, signal = null) {
      const isFormData = typeof FormData !== 'undefined' && promptOrFormData instanceof FormData
      const response = await client.request('/kolors/image-to-image', {
        method: 'POST',
        body: isFormData
          ? promptOrFormData
          : JSON.stringify({
            prompt: promptOrFormData,
            api_key_token: apiKeyToken,
            ...params
          }),
        signal
      })
      if (!response.ok) {
        throw await readError(response, '图生图失败')
      }
      return await response.json()
    },

    async inpaint(prompt, imageUrl, maskUrl, params = {}) {
      const response = await client.post('/kolors/inpaint', {
        prompt,
        image_path: imageUrl,
        mask_path: maskUrl,
        ...params
      })
      if (response.ok) {
        return await response.json()
      }
      throw new Error('图像修复失败')
    },

    async generateAvatar(prompt, params = {}) {
      const response = await client.post('/kolors/avatar', {
        prompt,
        ...params
      })
      if (response.ok) {
        return await response.json()
      }
      throw new Error('头像生成失败')
    },

    async generateLandscape(prompt, params = {}) {
      const response = await client.post('/kolors/landscape', {
        prompt,
        ...params
      })
      if (response.ok) {
        return await response.json()
      }
      throw new Error('风景图生成失败')
    },

    async generateIcon(prompt, params = {}) {
      const response = await client.post('/kolors/icon', {
        prompt,
        ...params
      })
      if (response.ok) {
        return await response.json()
      }
      throw new Error('图标生成失败')
    },

    async getConfig() {
      try {
        const response = await client.get('/kolors/config')
        if (response.ok) {
          return await response.json()
        }
        return {}
      } catch (error) {
        return {}
      }
    },

    async getHistory(page = 1, pageSize = 20) {
      // 后端分页参数是 page_size；旧实现发 limit 会被忽略（FRESCAN-50/70）
      const response = await client.get('/kolors/history', { page, page_size: pageSize })
      if (!response.ok) {
        throw await readError(response, '获取绘图历史失败')
      }
      return await response.json()
    },

    async getHistoryDetail(imageId) {
      const response = await client.get(`/kolors/history/${imageId}`)
      if (!response.ok) {
        throw await readError(response, '获取绘图历史详情失败')
      }
      return await response.json()
    },

    async deleteHistory(imageId) {
      const response = await client.delete(`/kolors/history/${imageId}`)
      if (!response.ok) {
        throw await readError(response, '删除绘图历史失败')
      }
      return await response.json()
    },

    async clearHistory() {
      const response = await client.delete('/kolors/history')
      if (!response.ok) {
        throw await readError(response, '清空绘图历史失败')
      }
      return await response.json()
    },

    async getResourceBlob(filename) {
      const response = await client.get(`/kolors/resources/${encodeURIComponent(filename)}`)
      if (!response.ok) {
        throw await readError(response, '读取历史图片失败')
      }
      return await response.blob()
    }
  }
}

export default { createKolorsClient }
