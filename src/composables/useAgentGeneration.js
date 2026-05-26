import { ref, reactive } from 'vue'

export function useAgentGeneration() {
  const isGenerating = ref(false)
  const workflowStages = ref([])
  const currentPhase = ref('initializing')
  const currentStep = ref(0)
  const totalSteps = ref(0)
  const startTime = ref(null)

  const modelAssignments = ref({
    architecture: { model: '', calls: 0, successRate: 100 },
    frontend: { model: '', calls: 0, successRate: 100 },
    backend: { model: '', calls: 0, successRate: 100 },
    test: { model: '', calls: 0, successRate: 100 },
    review: { model: '', calls: 0, successRate: 100 }
  })
  const recoveryAttempts = ref([])

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

  function getOverallProgress() {
    if (workflowStages.value.length === 0) return 0
    const total = workflowStages.value.reduce((sum, s) => sum + s.progress, 0)
    return total / workflowStages.value.length
  }

  function getETA() {
    if (!startTime.value || getOverallProgress() === 0) return ''
    const elapsed = Date.now() - startTime.value
    const progress = getOverallProgress() / 100
    if (progress === 0) return ''
    if (progress >= 1) return '已完成'
    const estimatedTotal = elapsed / progress
    const remaining = estimatedTotal - elapsed
    if (remaining < 60000) return `${Math.ceil(remaining / 1000)}秒`
    if (remaining < 3600000) return `${Math.ceil(remaining / 60000)}分钟`
    return `${Math.ceil(remaining / 3600000)}小时`
  }

  function getPlaceholder(mode) {
    switch (mode) {
      case 'create': return '描述你想要生成的项目，例如：\n\n一个带用户登录功能的 Vue 3 + FastAPI 项目...\n\n或者选择下面的快速模板：'
      case 'modify': return '描述你需要修改或新增的内容，例如：\n\n添加用户权限验证功能...\n优化登录页面UI...\n新增数据导出功能...'
      case 'debug': return '描述遇到的问题或需要修复的Bug，例如：\n\n用户登录时出现500错误...\n数据保存失败...\n页面加载缓慢...'
      default: return '请输入您的需求...'
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
    modelAssignments.value = {
      architecture: { model: '', calls: 0, successRate: 100 },
      frontend: { model: '', calls: 0, successRate: 100 },
      backend: { model: '', calls: 0, successRate: 100 },
      test: { model: '', calls: 0, successRate: 100 },
      review: { model: '', calls: 0, successRate: 100 }
    }
  }

  return reactive({
    isGenerating, workflowStages, currentPhase, currentStep, totalSteps, startTime,
    modelAssignments, recoveryAttempts,
    ensureStage, updateStageStatus, addThinkingToStage,
    getOverallProgress, getETA, getPlaceholder, resetStages, resetState
  })
}
