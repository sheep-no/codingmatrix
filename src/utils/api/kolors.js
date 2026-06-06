/**
 * API Kolors 图像生成模块
 * 后端端点: /api/v1/kolors
 */
export function createKolorsClient(client) {
  return {
    async textToImage(prompt, params = {}, api_key_token = null) {
      const response = await client.post('/kolors/text-to-image', {
        prompt,
        api_key_token,
        ...params
      })
      if (response.ok) {
        return await response.json()
      }
      throw new Error('文生图失败')
    },

    async imageToImage(prompt, imageUrl, params = {}, api_key_token = null) {
      const response = await client.post('/kolors/image-to-image', {
        prompt,
        image_path: imageUrl,
        api_key_token,
        ...params
      })
      if (response.ok) {
        return await response.json()
      }
      throw new Error('图生图失败')
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

    async getHistory(page = 1, limit = 20) {
      try {
        const response = await client.get('/kolors/history', { page, limit })
        if (response.ok) {
          return await response.json()
        }
        return { images: [] }
      } catch (error) {
        return { images: [] }
      }
    },

    async getHistoryDetail(imageId) {
      try {
        const response = await client.get(`/kolors/history/${imageId}`)
        if (response.ok) {
          return await response.json()
        }
        return null
      } catch (error) {
        return null
      }
    },

    async deleteHistory(imageId) {
      try {
        const response = await client.delete(`/kolors/history/${imageId}`)
        if (response.ok) {
          return await response.json()
        }
        return { success: false }
      } catch (error) {
        return { success: false }
      }
    },

    async clearHistory() {
      try {
        const response = await client.delete('/kolors/history')
        if (response.ok) {
          return await response.json()
        }
        return { success: false }
      } catch (error) {
        return { success: false }
      }
    }
  }
}

export default { createKolorsClient }
