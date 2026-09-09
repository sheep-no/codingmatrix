export function createVisionClient(client) {
  async function uploadRequest(path, file, fields = {}) {
    const formData = new FormData()
    formData.append('file', file)
    Object.entries(fields).forEach(([key, value]) => {
      if (value !== undefined && value !== null) formData.append(key, value)
    })
    const response = await client.request(`/vision/${path}`, { method: 'POST', body: formData })
    if (!response.ok) throw new Error(`视觉服务请求失败 (${response.status})`)
    return response.json()
  }

  return {
    analyzeImage(file, prompt, model) {
      return uploadRequest('analyze', file, { prompt, model })
    },
    recognizeImageText(file) {
      return uploadRequest('ocr', file)
    },
    generateCodeFromImage(file, requirement) {
      return uploadRequest('code-from-image', file, { requirement })
    },
    checkImageSafety(file) {
      return uploadRequest('check-safety', file)
    }
  }
}

export default { createVisionClient }
