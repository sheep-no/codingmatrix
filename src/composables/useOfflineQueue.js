import { ref, onMounted, onUnmounted } from 'vue'
import { useToast } from '@/composables/useToast'

const OFFLINE_QUEUE_KEY = 'offlineMessageQueue'

export function useOfflineQueue() {
  const isOnline = ref(navigator.onLine)
  const pendingMessages = ref([])
  const { warning: showWarning, success: showSuccess } = useToast()

  let sendCallback = null

  function setSendCallback(callback) {
    sendCallback = callback
  }

  function handleOnline() {
    isOnline.value = true
    showSuccess('网络已恢复')
    flushQueue()
  }

  function handleOffline() {
    isOnline.value = false
    showWarning('网络已断开，消息将在网络恢复后自动发送')
  }

  function queueMessage(messageData) {
    const queuedMessage = {
      ...messageData,
      queuedAt: Date.now(),
      id: `queued_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`
    }

    pendingMessages.value.push(queuedMessage)
    saveQueue()
    showWarning('消息已加入队列，等待网络恢复')

    return queuedMessage.id
  }

  async function flushQueue() {
    if (pendingMessages.value.length === 0 || !sendCallback) return

    const messagesToSend = [...pendingMessages.value]
    pendingMessages.value = []

    for (const message of messagesToSend) {
      try {
        await sendCallback(message)
      } catch {
        pendingMessages.value.push(message)
        break
      }
    }

    saveQueue()
  }

  function saveQueue() {
    try {
      localStorage.setItem(OFFLINE_QUEUE_KEY, JSON.stringify(pendingMessages.value))
    } catch {
      // 忽略存储错误
    }
  }

  function restoreQueue() {
    try {
      const saved = localStorage.getItem(OFFLINE_QUEUE_KEY)
      if (saved) {
        pendingMessages.value = JSON.parse(saved)
        localStorage.removeItem(OFFLINE_QUEUE_KEY)
      }
    } catch {
      pendingMessages.value = []
    }
  }

  function clearQueue() {
    pendingMessages.value = []
    localStorage.removeItem(OFFLINE_QUEUE_KEY)
  }

  onMounted(() => {
    window.addEventListener('online', handleOnline)
    window.addEventListener('offline', handleOffline)
    restoreQueue()

    if (!isOnline.value && pendingMessages.value.length > 0) {
      showWarning(`有 ${pendingMessages.value.length} 条消息等待发送`)
    }
  })

  onUnmounted(() => {
    window.removeEventListener('online', handleOnline)
    window.removeEventListener('offline', handleOffline)
  })

  return {
    isOnline,
    pendingMessages,
    queueMessage,
    setSendCallback,
    clearQueue,
    flushQueue
  }
}
