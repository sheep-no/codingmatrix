/**
 * API 文件管理模块
 */
export function createFileClient(client) {
  return {
    async uploadFile(file, conversationId = null) {
      try {
        const formData = new FormData()
        formData.append('file', file)
        if (conversationId) {
          formData.append('conversation_id', conversationId)
        }

        const response = await fetch(`${import.meta.env.VITE_API_BASE || '/api/v1'}/files/upload`, {
          method: 'POST',
          body: formData,
          credentials: 'include'
        })

        if (response.ok) {
          return await response.json()
        } else {
          const error = await response.json()
          throw new Error(error.detail || 'Upload failed')
        }
      } catch (error) {
        throw error
      }
    },

    async initMultipartUpload(filename, fileSize, conversationId = null) {
      try {
        const response = await client.post('/files/multipart/init', {
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
      } catch (error) {
        throw error
      }
    },

    async uploadChunk(fileId, chunkIndex, chunk) {
      try {
        const formData = new FormData()
        formData.append('file_id', fileId)
        formData.append('chunk_index', chunkIndex)
        formData.append('chunk', chunk)

        const response = await fetch(
          `${import.meta.env.VITE_API_BASE || '/api/v1'}/files/multipart/upload`,
          {
            method: 'POST',
            body: formData,
            credentials: 'include'
          }
        )

        if (response.ok) {
          return await response.json()
        } else {
          const error = await response.json()
          throw new Error(error.detail || 'Chunk upload failed')
        }
      } catch (error) {
        throw error
      }
    },

    async getFiles() {
      try {
        const response = await client.get('/files')
        if (response.ok) {
          return await response.json()
        }
        return { files: [] }
      } catch (error) {
        console.error('Failed to load files:', error)
        return { files: [] }
      }
    },

    async getFileDetail(fileId) {
      try {
        const response = await client.get(`/files/${fileId}`)
        if (response.ok) {
          return await response.json()
        }
        return null
      } catch (error) {
        return null
      }
    },

    async deleteFile(fileId) {
      try {
        const response = await client.post('/files/delete', { file_id: fileId })
        if (response.ok) {
          return await response.json()
        }
        return { success: false }
      } catch (error) {
        return { success: false }
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
