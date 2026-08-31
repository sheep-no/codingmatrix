/**
 * API 文件管理模块 (v5.0.2 端点修复)
 * 后端端点:
 * - POST /api/v1/files/upload
 * - GET /api/v1/files/{file_id}/download
 * - POST /api/v1/files/upload/init
 * - POST /api/v1/files/upload/chunk/{file_id}/{chunk_index}
 * - POST /api/v1/files/upload/merge/{file_id}
 */
export function createFileClient(client) {
  return {
    async uploadFile(file, conversationId = null) {
      const formData = new FormData()
      formData.append('file', file)
      if (conversationId) {
        formData.append('conversation_id', conversationId)
      }

      const response = await client.request('/files/upload', {
        method: 'POST',
        body: formData
      })

      if (response.ok) {
        return await response.json()
      } else {
        const error = await response.json()
        throw new Error(error.detail || 'Upload failed')
      }
    },

    async initMultipartUpload(filename, fileSize, conversationId = null) {
      const response = await client.post('/files/upload/init', {
        filename,
        file_size: fileSize,
        conversation_id: conversationId
      })
      if (response.ok) {
        return await response.json()
      } else {
        const error = await response.json()
        throw new Error(error.detail || 'Init multipart failed')
      }
    },

    async uploadChunk(fileId, chunkIndex, chunk) {
      const formData = new FormData()
      formData.append('file_id', fileId)
      formData.append('chunk_index', chunkIndex)
      formData.append('chunk', chunk)

      const response = await client.request(`/files/upload/chunk/${fileId}/${chunkIndex}`, {
        method: 'POST',
        body: formData
      })

      if (response.ok) {
        return await response.json()
      } else {
        const error = await response.json()
        throw new Error(error.detail || 'Chunk upload failed')
      }
    },

    async mergeChunks(fileId) {
      const response = await client.post(`/files/upload/merge/${fileId}`)
      if (response.ok) {
        return await response.json()
      } else {
        const error = await response.json()
        throw new Error(error.detail || 'Merge chunks failed')
      }
    },

    async downloadFile(fileId, filename) {
      try {
        const response = await client.get(`/files/${fileId}/download`)
        if (response.ok) {
          const blob = await response.blob()
          const url = window.URL.createObjectURL(blob)
          const a = document.createElement('a')
          a.href = url
          a.download = filename || `file_${fileId}`
          document.body.appendChild(a)
          a.click()
          document.body.removeChild(a)
          window.URL.revokeObjectURL(url)
          return true
        }
        return false
      } catch (error) {
        return false
      }
    }
  }
}

export default { createFileClient }
