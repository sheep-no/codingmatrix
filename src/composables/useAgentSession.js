import { reactive } from 'vue'
import { useAgentSessionStore } from '@/stores/agentSession'

/**
 * Thin wrapper around Pinia store for backward compatibility.
 * Prefer importing from '@/stores/agentSession' directly in new code.
 */
export function useAgentSession() {
  const store = useAgentSessionStore()

  return reactive({
    get currentSessionId() { return store.currentSessionId },
    set currentSessionId(v) { store.currentSessionId = v },
    get projectPrompt() { return store.projectPrompt },
    set projectPrompt(v) { store.projectPrompt = v },
    get sessionHistory() { return store.sessionHistory },
    saveSessionState: (...args) => store.saveSessionState(...args),
    restoreSessionState: (...args) => store.restoreSessionState(...args),
    clearSessionState() {
      store.saveSessionState({
        workflowStages: [], pendingDecisions: [], decisionHistory: [],
        generatedFiles: [], thinkingMessages: [], executionDetails: [], logs: [],
        currentPhase: 'initializing', currentStep: 0, totalSteps: 0,
        startTime: null, modelAssignments: {}, recoveryAttempts: []
      })
    },
    loadSessionHistory: (...args) => store.loadSessionHistory(...args),
    createNewSession: (...args) => store.createNewSession(...args),
    switchSession: (...args) => store.switchSession(...args),
    deleteSession: (...args) => store.deleteSession(...args),
    startAutoSave: (...args) => store.startAutoSave(...args),
    stopAutoSave: (...args) => store.stopAutoSave(...args),
    MAX_LOG_ENTRIES: 100,
    MAX_THINKING_ENTRIES: 50,
    MAX_HISTORY_ENTRIES: 10
  })
}
