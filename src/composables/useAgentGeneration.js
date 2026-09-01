import { reactive } from 'vue'
import { useAgentSessionStore } from '@/stores/agentSession'

export function useAgentGeneration() {
  const store = useAgentSessionStore()

  return reactive({
    get isGenerating() { return store.isGenerating },
    set isGenerating(value) { store.isGenerating = value },
    get workflowStages() { return store.workflowStages },
    set workflowStages(value) { store.workflowStages = value },
    get currentPhase() { return store.currentPhase },
    set currentPhase(value) { store.currentPhase = value },
    get currentStep() { return store.currentStep },
    set currentStep(value) { store.currentStep = value },
    get totalSteps() { return store.totalSteps },
    set totalSteps(value) { store.totalSteps = value },
    get startTime() { return store.startTime },
    set startTime(value) { store.startTime = value },
    get roles() { return store.roles },
    set roles(value) { store.roles = value },
    get modelAssignments() { return store.modelAssignments },
    set modelAssignments(value) { store.modelAssignments = value },
    get modelConfigVersion() { return store.modelConfigVersion },
    set modelConfigVersion(value) { store.modelConfigVersion = value },
    get modelContextRevision() { return store.modelContextRevision },
    set modelContextRevision(value) { store.modelContextRevision = value },
    get currentModel() { return store.currentModel },
    set currentModel(value) { store.currentModel = value },
    get currentAgent() { return store.currentAgent },
    set currentAgent(value) { store.currentAgent = value },
    get fallbackHistory() { return store.fallbackHistory },
    set fallbackHistory(value) { store.fallbackHistory = value },
    get recoveryAttempts() { return store.recoveryAttempts },
    set recoveryAttempts(value) { store.recoveryAttempts = value },
    ensureStage: (...args) => store.ensureStage(...args),
    updateStageStatus: (...args) => store.updateStageStatus(...args),
    addThinkingToStage: (...args) => store.addThinkingToStage(...args),
    getOverallProgress: () => store.getOverallProgress(),
    getETA: () => store.getETA(),
    getPlaceholder: hasFiles => store.getPlaceholder(hasFiles),
    resetStages: () => store.resetStages(),
    resetState: () => store.resetState(),
    fetchRoles: () => store.fetchRoles(),
    getModelContextSnapshot: () => store.getModelContextSnapshot(),
    applyModelContext: (context, revision) => store.applyModelContext(context, revision)
  })
}
