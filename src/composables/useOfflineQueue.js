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

    for (let i = 0; i < messagesToSend.length; i++) {
      try {
        await sendCallback(messagesToSend[i])
      } catch (e) {
        console.warn('[useOfflineQueue] 发送失败，加入重试队列:', e.message)
        // 失败消息及其后续消息按原顺序保留，避免被丢弃
        pendingMessages.value.push(...messagesToSend.slice(i))
        break
      }
    }

    saveQueue()
  }

  function saveQueue() {
    try {
      localStorage.setItem(OFFLINE_QUEUE_KEY, JSON.stringify(pendingMessages.value))
    } catch (e) {
      console.debug('[useOfflineQueue] 存储队列失败（容量已满？）:', e.message)
    }
  }

  function restoreQueue() {
    try {
      const saved = localStorage.getItem(OFFLINE_QUEUE_KEY)
      if (saved) {
        pendingMessages.value = JSON.parse(saved)
      }
    } catch (e) {
      console.debug('[useOfflineQueue] 恢复队列失败（已损坏，重置）:', e.message)
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

    if (pendingMessages.value.length === 0) return

    if (!isOnline.value) {
      showWarning(`有 ${pendingMessages.value.length} 条消息等待发送`)
      return
    }

    // 已在线的恢复队列不会收到 online 事件，等挂载流程结束后再补发
    setTimeout(() => {
      if (isOnline.value) flushQueue()
    }, 0)
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
