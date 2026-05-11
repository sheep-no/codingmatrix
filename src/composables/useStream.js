import { ref } from 'vue'
import { streamManager } from '@/utils/streamManager'
import { useToast } from '@/composables/useToast'
import { useUserStore } from '@/stores/user'
import { api } from '@/utils/api/index'

export function useStream() {
  const isStreaming = ref(false)
  const isLoading = ref(false)
  const streamError = ref(null)
  const canRetry = ref(false)

  const { error: showError, success: showSuccess } = useToast()
  const userStore = useUserStore()

  const MAX_RETRIES = 2
  const RETRY_DELAY = 1000

  async function sendStreamMessage({
    prompt,
    conversationId,
    useReasoning = false,
    useHybrid = false,
    onChunk,
    onComplete,
    onError,
    onStatusChange,
    retryCount = 0
  }) {
    const requestId = `req_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`
    streamManager.currentRequestId = requestId

    const abortController = streamManager.createAbortController(requestId)
    isStreaming.value = true
    isLoading.value = true
    streamError.value = null
    canRetry.value = false

    streamManager.saveStreamRequestState(
      { prompt, useReasoning, useHybrid, requestId },
      { content: prompt },
      conversationId
    )

    try {
      const response = await api.post(
        '/chat/stream',
        {
          prompt,
          conversation_id: conversationId,
          use_reasoning: useReasoning,
          use_hybrid: useHybrid
        },
        {
          signal: abortController.signal
        }
      )

      if (!response.ok) {
        if (response.status === 401) {
          userStore.clearUser()
          throw new Error('登录已过期，请重新登录')
        }
        if (response.status === 502 || response.status === 503) {
          throw new Error(`服务器繁忙 (${response.status})，请稍后重试`)
        }
        const data = await response.json().catch(() => ({}))
        throw new Error(data.detail || `请求失败 (${response.status})`)
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let fullContent = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const data = line.slice(6).trim()
            if (data === '[DONE]') {
              isStreaming.value = false
              isLoading.value = false
              streamManager.clearStreamRequestState()
              onComplete?.(fullContent)
              return
            }

            try {
              const parsed = JSON.parse(data)
              if (parsed.content) {
                fullContent += parsed.content
                onChunk?.(parsed.content, fullContent, parsed)
              }
              if (parsed.status) {
                onStatusChange?.(parsed.status)
              }
            } catch (e) {
              // 忽略解析错误
            }
          }
        }
      }
    } catch (error) {
      if (error.name === 'AbortError') {
        isStreaming.value = false
        isLoading.value = false
        return
      }

      isStreaming.value = false
      isLoading.value = false
      streamError.value = error.message

      const shouldRetry =
        retryCount < MAX_RETRIES &&
        (error.message.includes('502') ||
          error.message.includes('503') ||
          error.message.includes('网络'))

      if (shouldRetry) {
        canRetry.value = true
        showError(`${error.message}，${MAX_RETRIES - retryCount} 秒后自动重试...`)

        setTimeout(
          () => {
            canRetry.value = false
            sendStreamMessage({
              prompt,
              conversationId,
              useReasoning,
              useHybrid,
              onChunk,
              onComplete,
              onError,
              onStatusChange,
              retryCount: retryCount + 1
            })
          },
          RETRY_DELAY * (retryCount + 1)
        )
      } else {
        canRetry.value = true
        showError(error.message)
        onError?.(error)
      }
    }
  }

  function abortStream() {
    const aborted = streamManager.abortCurrentRequest()
    isStreaming.value = false
    isLoading.value = false
    canRetry.value = false
    streamManager.clearStreamRequestState()
    return aborted
  }

  function retryStream(options) {
    if (canRetry.value) {
      canRetry.value = false
      return sendStreamMessage(options)
    }
    return Promise.reject(new Error('无法重试'))
  }

  function resetStreamState() {
    isStreaming.value = false
    isLoading.value = false
    streamError.value = null
    canRetry.value = false
    streamManager.clearStreamRequestState()
  }

  return {
    isStreaming,
    isLoading,
    streamError,
    canRetry,
    sendStreamMessage,
    abortStream,
    retryStream,
    resetStreamState
  }
}
