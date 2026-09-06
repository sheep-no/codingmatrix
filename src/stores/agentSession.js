import { ref, computed } from 'vue'
import { defineStore } from 'pinia'

const SESSION_KEY = 'agent_project_sessions'
const MAX_HISTORY_ENTRIES = 10
let autoSaveTimer = null

export const useAgentSessionStore = defineStore('agentSession', () => {
  // ========== Session State ==========
  const currentSessionId = ref(null)
  const projectPrompt = ref('')
  const sessionHistory = ref([])
  const pendingDecisions = ref([])
  const decisionHistory = ref([])

  const isGenerating = ref(false)
  const workflowStages = ref([])
  const currentPhase = ref('initializing')
  const currentStep = ref(0)
  const totalSteps = ref(0)
  const startTime = ref(null)
  const roles = ref(['architect', 'frontend', 'backend', 'reviewer', 'fallback'])
  const modelAssignments = ref({})
  const modelConfigVersion = ref('')
  const modelContextRevision = ref(null)
  const currentModel = ref(null)
  const currentAgent = ref(null)
  const fallbackHistory = ref([])
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

  function createNewSession(snapshot = {}) {
    const persistedSnapshot = Object.fromEntries(
      Object.entries(snapshot).filter(([key]) => !key.startsWith('_'))
    )
    const newId = Date.now().toString()
    const newSession = {
      id: newId,
      prompt: projectPrompt.value || '',
      timestamp: Date.now(),
      filesCount: 0, files: [], logs: [], thinking: [], steps: [],
      workflowStages: [], pendingDecisions: [], decisionHistory: [],
      currentPhase: '', currentStep: 0, totalSteps: 0,
      startTime: null, modelAssignments: {}, modelConfigVersion: '', modelContextRevision: null,
      currentModel: null, currentAgent: null, fallbackHistory: [], recoveryAttempts: [],
      ...persistedSnapshot
    }
    sessionHistory.value = [newSession, ...sessionHistory.value].slice(0, MAX_HISTORY_ENTRIES)
    _saveSessionHistory()
    currentSessionId.value = newId
    return newId
  }

  function deleteSession(id) {
    sessionHistory.value = sessionHistory.value.filter(s => s.id !== id)
    _saveSessionHistory()
    if (currentSessionId.value === id) {
      currentSessionId.value = null
      // 清理被删除会话的状态
      projectPrompt.value = ''
      workflowStages.value = []
      pendingDecisions.value = []
      decisionHistory.value = []
      currentPhase.value = ''
      currentStep.value = ''
      totalSteps.value = 0
      startTime.value = null
      modelAssignments.value = {}
      modelConfigVersion.value = ''
      modelContextRevision.value = null
      currentModel.value = null
      currentAgent.value = null
      fallbackHistory.value = []
      recoveryAttempts.value = []
    }
  }

  function switchSession(id, context = null) {
    const session = sessionHistory.value.find(s => s.id === id)
    if (session) {
      currentSessionId.value = id
      projectPrompt.value = session.prompt || ''

      if (context) {
        workflowStages.value = session.workflowStages || []
        pendingDecisions.value = session.pendingDecisions || []
        decisionHistory.value = session.decisionHistory || []
        currentPhase.value = session.currentPhase || 'initializing'
        currentStep.value = session.currentStep || 0
        totalSteps.value = session.totalSteps || 0
        startTime.value = session.startTime || null
        modelAssignments.value = session.modelAssignments || {}
        modelConfigVersion.value = session.modelConfigVersion || ''
        modelContextRevision.value = session.modelContextRevision ?? null
        currentModel.value = session.currentModel || null
        currentAgent.value = session.currentAgent || null
        fallbackHistory.value = session.fallbackHistory || []
        recoveryAttempts.value = session.recoveryAttempts || []
        context._generation.workflowStages = workflowStages.value
        context._generation.currentPhase = currentPhase.value
        context._generation.currentStep = currentStep.value
        context._generation.totalSteps = totalSteps.value
        context._generation.startTime = startTime.value
        context._generation.modelAssignments = modelAssignments.value
        context._generation.modelConfigVersion = modelConfigVersion.value
        context._generation.modelContextRevision = modelContextRevision.value
        context._generation.currentModel = currentModel.value
        context._generation.currentAgent = currentAgent.value
        context._generation.fallbackHistory = fallbackHistory.value
        context._generation.recoveryAttempts = recoveryAttempts.value
        context._workspace.pendingDecisions = pendingDecisions.value
        context._workspace.decisionHistory = decisionHistory.value
        context._workspace.logs = session.logs || []
        context._workspace.thinkingMessages = session.thinkingMessages || session.thinking || []
        context._workspace.executionDetails = session.executionDetails || []
        context._files.generatedFiles = session.generatedFiles || session.files || []
      }
      return true
    }
    return false
  }

  function saveSessionState(snapshot = {}) {
    const session = sessionHistory.value.find(item => item.id === currentSessionId.value)
    if (!session) return false
    Object.assign(session, {
      ...snapshot,
      prompt: projectPrompt.value,
      timestamp: Date.now(),
      filesCount: snapshot.generatedFiles?.length || 0
    })
    sessionHistory.value = [session, ...sessionHistory.value.filter(item => item.id !== session.id)]
      .slice(0, MAX_HISTORY_ENTRIES)
    _saveSessionHistory()
    return true
  }

  function restoreSessionState() {
    return sessionHistory.value.find(item => item.id === currentSessionId.value) || null
  }

  function startAutoSave(shouldSave, save) {
    stopAutoSave()
    autoSaveTimer = setInterval(() => {
      if (shouldSave()) save()
    }, 5000)
  }

  function stopAutoSave() {
    if (autoSaveTimer) clearInterval(autoSaveTimer)
    autoSaveTimer = null
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
    currentModel.value = null
    currentAgent.value = null
    modelContextRevision.value = null
    fallbackHistory.value = []
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

  function getModelContextSnapshot() {
    const snapshot = {
      config_version: modelConfigVersion.value,
      roles: Object.fromEntries(
        Object.entries(modelAssignments.value).map(([role, assignment]) => [role, assignment.model || ''])
      ),
      current_model: currentModel.value,
      current_agent: currentAgent.value,
      assignments: Object.fromEntries(
        Object.entries(modelAssignments.value).map(([role, assignment]) => [role, {
          model: assignment.model || '',
          calls: assignment.calls || 0,
          success_rate: assignment.successRate ?? 100
        }])
      ),
      fallback_history: fallbackHistory.value
    }
    snapshot.expected_revision = modelContextRevision.value ?? 0
    return snapshot
  }

  function applyModelContext(context = {}, revision = null) {
    modelContextRevision.value = revision
    modelConfigVersion.value = context.config_version || ''
    currentModel.value = context.current_model || null
    currentAgent.value = context.current_agent || null
    fallbackHistory.value = context.fallback_history || []
    if (context.assignments) {
      modelAssignments.value = Object.fromEntries(
        Object.entries(context.assignments).map(([role, assignment]) => [role, {
          model: assignment.model || context.roles?.[role] || '',
          calls: assignment.calls || 0,
          successRate: assignment.success_rate ?? 100
        }])
      )
      roles.value = Object.keys(modelAssignments.value)
    }
  }

  async function fetchRoles() {
    try {
      const { api } = await import('@/utils/api')
      const response = await api.get('/api/v1/models/agent-config')
      const data = response.data || response
      modelConfigVersion.value = data.version || ''
      // v3.0: roles is an object {role: model_id}, keys are role names
      if (data.roles && typeof data.roles === 'object' && !Array.isArray(data.roles)) {
        const roleNames = Object.keys(data.roles)
        if (roleNames.length > 0) {
          roles.value = roleNames
          const existing = modelAssignments.value || {}
          const updated = {}
          for (const role of roleNames) {
            updated[role] = {
              model: existing[role]?.model || data.roles[role] || '',
              calls: existing[role]?.calls || 0,
              successRate: existing[role]?.successRate ?? 100
            }
          }
          modelAssignments.value = updated
        }
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

  function getOverallProgress() {
    return overallProgress.value
  }

  function getPlaceholder(hasFiles) {
    if (hasFiles) {
      return '描述你需要修改或新增的内容，例如：\n\n添加用户权限验证功能...\n优化登录页面UI...\n新增数据导出功能...\n\n或者描述遇到的问题：\n\n用户登录时出现500错误...\n数据保存失败...'
    }
    return '描述你想要生成的项目，例如：\n\n一个带用户登录功能的 Vue 3 + FastAPI 项目...\n\n或者选择下面的快速模板：'
  }

  // Initialize
  _buildAssignments()
  loadSessionHistory()

  return {
    // State
    currentSessionId, projectPrompt, sessionHistory,
    isGenerating, workflowStages, currentPhase, currentStep, totalSteps, startTime,
    roles, modelAssignments, modelConfigVersion, modelContextRevision, currentModel, currentAgent,
    fallbackHistory, recoveryAttempts,
    // Computed
    sessionId, overallProgress,
    // Session methods
    loadSessionHistory, createNewSession, switchSession, deleteSession,
    saveSessionState, restoreSessionState, startAutoSave, stopAutoSave,
    // Generation methods
    ensureStage, updateStageStatus, addThinkingToStage,
    resetStages, resetState, fetchRoles, getETA, getOverallProgress, getPlaceholder,
    getModelContextSnapshot, applyModelContext
  }
})
