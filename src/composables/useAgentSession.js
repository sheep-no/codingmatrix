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
        const idx = sessionHistory.value.findIndex(s => s.id === currentSessionId.value)
        if (idx !== -1) {
          sessionHistory.value[idx] = { ...sessionHistory.value[idx], ...state }
        }
      }
      localStorage.setItem(STATE_KEY, JSON.stringify(state))
      localStorage.setItem(SESSION_KEY, JSON.stringify(sessionHistory.value))
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

  function createNewSession(data, stateRefs) {
    const newId = Date.now().toString()
    const newSession = {
      id: newId,
      prompt: projectPrompt.value || '',
      timestamp: Date.now(),
      filesCount: 0,
      files: [],
      logs: [],
      thinking: [],
      steps: [],
      workflowStages: [],
      pendingDecisions: [],
      decisionHistory: [],
      currentPhase: '',
      currentStep: '',
      totalSteps: 0,
      startTime: null,
      modelAssignments: {},
      recoveryAttempts: 0
    }
    sessionHistory.value = [newSession, ...sessionHistory.value].slice(0, MAX_HISTORY_ENTRIES)
    try {
      localStorage.setItem(SESSION_KEY, JSON.stringify(sessionHistory.value))
    } catch (e) {
      console.error('Failed to save session history:', e)
    }
    currentSessionId.value = newId

    // 清空工作区状态（但保留 prompt）
    const gen = stateRefs?._generation
    const ws = stateRefs?._workspace
    const fl = stateRefs?._files
    if (fl) fl.generatedFiles = []
    if (ws) {
      ws.logs = []
      ws.thinkingMessages = []
      ws.executionDetails = []
      ws.pendingDecisions = []
      ws.decisionHistory = []
    }
    if (gen) {
      gen.workflowStages = []
      gen.currentPhase = ''
      gen.currentStep = ''
      gen.totalSteps = 0
      gen.startTime = null
      gen.modelAssignments = {}
      gen.recoveryAttempts = 0
    }

    return newId
  }

  function switchSession(id, stateRefs) {
    const gen = stateRefs?._generation
    const ws = stateRefs?._workspace
    const fl = stateRefs?._files

    // 先保存当前会话状态
    if (currentSessionId.value) {
      const currentState = {
        prompt: projectPrompt.value,
        files: fl?.generatedFiles ?? [],
        logs: ws?.logs ?? [],
        thinking: ws?.thinkingMessages ?? [],
        steps: ws?.executionDetails ?? [],
        workflowStages: gen?.workflowStages ?? [],
        pendingDecisions: ws?.pendingDecisions ?? [],
        decisionHistory: ws?.decisionHistory ?? [],
        currentPhase: gen?.currentPhase ?? '',
        currentStep: gen?.currentStep ?? '',
        totalSteps: gen?.totalSteps ?? 0,
        startTime: gen?.startTime ?? null,
        modelAssignments: gen?.modelAssignments ?? {},
        recoveryAttempts: gen?.recoveryAttempts ?? 0
      }
      const idx = sessionHistory.value.findIndex(s => s.id === currentSessionId.value)
      if (idx !== -1) {
        sessionHistory.value[idx] = { ...sessionHistory.value[idx], ...currentState }
      }
      localStorage.setItem(SESSION_KEY, JSON.stringify(sessionHistory.value))
    }

    // 切换到目标会话
    currentSessionId.value = id

    // 恢复目标会话状态
    const target = sessionHistory.value.find(s => s.id === id)
    if (target) {
      projectPrompt.value = target.prompt || ''
      // 通过 reactive 对象设置值，Vue 会自动处理 ref 的 .value
      if (fl) fl.generatedFiles = target.files || []
      if (ws) {
        ws.logs = target.logs || []
        ws.thinkingMessages = target.thinking || []
        ws.executionDetails = target.steps || []
        ws.pendingDecisions = target.pendingDecisions || []
        ws.decisionHistory = target.decisionHistory || []
      }
      if (gen) {
        gen.workflowStages = target.workflowStages || []
        gen.currentPhase = target.currentPhase || ''
        gen.currentStep = target.currentStep || ''
        gen.totalSteps = target.totalSteps || 0
        gen.startTime = target.startTime || null
        gen.modelAssignments = target.modelAssignments || {}
        gen.recoveryAttempts = target.recoveryAttempts || 0
      }
    }
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
