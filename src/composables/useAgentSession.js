import { ref, reactive, onUnmounted } from 'vue'

const STATE_KEY = 'agent_project_state'
const SESSION_KEY = 'agent_project_sessions'
const MAX_LOG_ENTRIES = 100
const MAX_THINKING_ENTRIES = 50
const MAX_HISTORY_ENTRIES = 10

export function useAgentSession() {
  const currentSessionId = ref(null)
  const projectPrompt = ref('')
  const sessionHistory = ref([])

  let autoSaveTimer = null

  function saveSessionState(data) {
    try {
      const state = {
        ...data,
        sessionId: currentSessionId.value,
        prompt: projectPrompt.value,
        timestamp: Date.now()
      }
      if (currentSessionId.value) {
        const sessions = [...sessionHistory.value].reverse()
        sessions[0] = { ...sessions[0], ...state }
        sessionHistory.value = sessions.reverse()
      }
      localStorage.setItem(STATE_KEY, JSON.stringify(state))
    } catch (e) {
      console.error('Failed to save session state:', e)
    }
  }

  function restoreSessionState() {
    try {
      const saved = localStorage.getItem(STATE_KEY)
      if (saved) {
        return JSON.parse(saved)
      }
    } catch (e) {
      console.error('Failed to restore session state:', e)
    }
    return null
  }

  function clearSessionState() {
    localStorage.removeItem(STATE_KEY)
  }

  function loadSessionHistory() {
    try {
      const saved = localStorage.getItem(SESSION_KEY)
      if (saved) {
        sessionHistory.value = JSON.parse(saved)
      }
    } catch (e) {
      console.error('Failed to load session history:', e)
      sessionHistory.value = []
    }
  }

  function createNewSession(data) {
    const newId = Date.now().toString()
    const newSession = {
      id: newId,
      prompt: projectPrompt.value,
      timestamp: Date.now(),
      filesCount: data?.generatedFiles?.length || 0
    }
    sessionHistory.value = [newSession, ...sessionHistory.value].slice(0, MAX_HISTORY_ENTRIES)
    try {
      localStorage.setItem(SESSION_KEY, JSON.stringify(sessionHistory.value))
    } catch (e) {
      console.error('Failed to save session history:', e)
    }
    currentSessionId.value = newId
    return newId
  }

  function switchSession(id) {
    currentSessionId.value = id
  }

  function deleteSession(id, callback) {
    sessionHistory.value = sessionHistory.value.filter(s => s.id !== id)
    try {
      localStorage.setItem(SESSION_KEY, JSON.stringify(sessionHistory.value))
    } catch (e) {
      console.error('Failed to save session history:', e)
    }
    if (currentSessionId.value === id) {
      currentSessionId.value = null
    }
    callback?.()
  }

  function startAutoSave(shouldSave, saveFn) {
    stopAutoSave() // 确保只有一个定时器
    autoSaveTimer = setInterval(() => {
      if (shouldSave?.()) {
        saveFn?.()
      }
    }, 30000)
  }

  function stopAutoSave() {
    if (autoSaveTimer) {
      clearInterval(autoSaveTimer)
      autoSaveTimer = null
    }
  }

  // 组件卸载时自动清理定时器
  try {
    onUnmounted(() => {
      stopAutoSave()
    })
  } catch (e) {
    // onUnmounted 只能在 setup 期间调用，忽略非 setup 上下文的错误
  }

  return reactive({
    currentSessionId, projectPrompt, sessionHistory,
    saveSessionState, restoreSessionState, clearSessionState,
    loadSessionHistory, createNewSession, switchSession, deleteSession,
    startAutoSave, stopAutoSave,
    MAX_LOG_ENTRIES, MAX_THINKING_ENTRIES, MAX_HISTORY_ENTRIES
  })
}
