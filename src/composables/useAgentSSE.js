import { ref } from 'vue'

export function useAgentSSE() {
  const isStreaming = ref(false)
  const streamContent = ref('')
  const streamEvents = ref([])
  const error = ref(null)

  async function streamRequest(url, body, options = {}) {
    const { onChunk, onEvent, onComplete, onError } = options

    isStreaming.value = true
    streamContent.value = ''
    streamEvents.value = []
    error.value = null

    try {
      const token = localStorage.getItem('access_token')
      const headers = { 'Content-Type': 'application/json' }
      
      if (token) {
        headers['Authorization'] = `Bearer ${token}`
      }

      const response = await fetch(url, {
        method: 'POST',
        headers,
        body: JSON.stringify(body)
      })

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`)
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6))
              streamEvents.value.push(data)

              if (data.type === 'content' || data.type === 'token') {
                streamContent.value += data.data.content || data.data.token || ''
                onChunk?.(streamContent.value, data)
              }

              onEvent?.(data)
            } catch (e) {
              console.warn('SSE parse error:', e)
            }
          }
        }
      }

      onComplete?.(streamContent.value, streamEvents.value)
    } catch (err) {
      error.value = err.message
      onError?.(err)
    } finally {
      isStreaming.value = false
    }
  }

  function abort() {
    isStreaming.value = false
  }

  return {
    isStreaming,
    streamContent,
    streamEvents,
    error,
    streamRequest,
    abort
  }
}
