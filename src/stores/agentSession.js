import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useApiKeyStore } from '@/stores/apikey'
import { getPhaseLabel } from '@/constants/agentPhases'

const SESSION_KEY = 'agent_project_sessions'
const MAX_HISTORY_ENTRIES = 10

export const useAgentSessionStore = defineStore('agentSession', () => {
  // ========== Session State ==========
  const currentSessionId = ref(null)
  const projectPrompt = ref('')
  const sessionHistory = ref([])

  // ========== Generation State ==========
  const isGenerating = ref(false)
  const workflowStages = ref([])
  const currentPhase = ref('initializing')
  const currentStep = ref(0)
  const totalSteps = ref(0)
  const startTime = ref(null)
  const roles = ref(['architect', 'frontend', 'backend', 'reviewer', 'fallback'])
  const modelAssignments = ref({})
  const recoveryAttempts = ref([])

  // ========== Computed ==========
  const sessionId = computed(() => currentSessionId.value)
  const overallProgress = computed(() => {
    if (workflowStages.value.length === 0) return 0
    const total = workflowStages.value.reduce((sum, s) => sum + s.progress, 0)
    return total / workflowStages.value.length
  })

  // ========== Session Methods ==========
  function loadSessionHistory() {
    try {
      const saved = localStorage.getItem(SESSION_KEY)
      if (saved) sessionHistory.value = JSON.parse(saved)
    } catch (e) {
      console.error('Failed to load session history:', e)
      sessionHistory.value = []
    }
  }

  function _saveSessionHistory() {
    try {
      localStorage.setItem(SESSION_KEY, JSON.stringify(sessionHistory.value))
    } catch (e) {
      console.error('Failed to save session history:', e)
    }
  }

  function createNewSession() {
    const newId = Date.now().toString()
    const newSession = {
      id: newId,
      prompt: projectPrompt.value || '',
      timestamp: Date.now(),
      filesCount: 0, files: [], logs: [], thinking: [], steps: [],
      workflowStages: [], pendingDecisions: [], decisionHistory: [],
      currentPhase: '', currentStep: '', totalSteps: 0,
      startTime: null, modelAssignments: {}, recoveryAttempts: 0
    }
    sessionHistory.value = [newSession, ...sessionHistory.value].slice(0, MAX_HISTORY_ENTRIES)
    _saveSessionHistory()
    currentSessionId.value = newId
    return newId
  }

  function deleteSession(id) {
    sessionHistory.value = sessionHistory.value.filter(s => s.id !== id)
    _saveSessionHistory()
    if (currentSessionId.value === id) currentSessionId.value = null
  }

  function switchSession(id) {
    const session = sessionHistory.value.find(s => s.id === id)
    if (session) {
      currentSessionId.value = id
      projectPrompt.value = session.prompt || ''
      return true
    }
    return false
  }

  // ========== Generation Methods ==========
  function ensureStage(stageId, name) {
    let stage = workflowStages.value.find(s => s.id === stageId)
    if (!stage) {
      stage = { id: stageId, name, status: 'pending', progress: 0, thinking: [], expanded: false }
      workflowStages.value.push(stage)
      totalSteps.value = workflowStages.value.length
    }
    return stage
  }

  function updateStageStatus(stageId, status, progress = null, name) {
    const stage = ensureStage(stageId, name || stageId)
    stage.status = status
    if (progress !== null) stage.progress = progress
  }

  function addThinkingToStage(stageId, message) {
    const stage = workflowStages.value.find(s => s.id === stageId)
    if (stage) {
      if (!stage.thinking) stage.thinking = []
      stage.thinking.push(message)
    }
  }

  function resetStages() {
    workflowStages.value = []
    currentPhase.value = 'initializing'
    currentStep.value = 0
    totalSteps.value = 0
    startTime.value = Date.now()
  }

  function resetState() {
    isGenerating.value = false
    recoveryAttempts.value = []
    _buildAssignments()
  }

  function _buildAssignments() {
    const assignments = {}
    for (const role of roles.value) {
      assignments[role] = { model: '', calls: 0, successRate: 100 }
    }
    modelAssignments.value = assignments
  }

  async function fetchRoles() {
    try {
      const { api } = await import('@/utils/api')
      const response = await api.get('/api/v1/models/agent-config')
      const data = response.data || response
      if (data.roles && Array.isArray(data.roles) && data.roles.length > 0) {
        roles.value = data.roles
        const existing = modelAssignments.value || {}
        const updated = {}
        for (const role of data.roles) {
          updated[role] = existing[role] || { model: '', calls: 0, successRate: 100 }
        }
        modelAssignments.value = updated
      }
    } catch (e) {
      console.warn('Failed to fetch agent roles, using defaults:', e.message)
    }
  }

  function getETA() {
    if (!startTime.value || overallProgress.value === 0) return ''
    const elapsed = Date.now() - startTime.value
    const progress = overallProgress.value / 100
    if (progress >= 1) return '已完成'
    const remaining = (elapsed / progress) - elapsed
    if (remaining < 60000) return `${Math.ceil(remaining / 1000)}秒`
    if (remaining < 3600000) return `${Math.ceil(remaining / 60000)}分钟`
    return `${Math.ceil(remaining / 3600000)}小时`
  }

  // Initialize
  _buildAssignments()
  loadSessionHistory()

  return {
    // State
    currentSessionId, projectPrompt, sessionHistory,
    isGenerating, workflowStages, currentPhase, currentStep, totalSteps, startTime,
    roles, modelAssignments, recoveryAttempts,
    // Computed
    sessionId, overallProgress,
    // Session methods
    loadSessionHistory, createNewSession, deleteSession,
    // Generation methods
    ensureStage, updateStageStatus, addThinkingToStage,
    resetStages, resetState, fetchRoles, getETA
  }
})
