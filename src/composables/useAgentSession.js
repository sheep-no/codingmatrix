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
    saveSessionState() { /* no-op, state is in store */ },
    restoreSessionState() { return null },
    clearSessionState() { /* no-op */ },
    loadSessionHistory: store.loadSessionHistory,
    createNewSession: store.createNewSession,
    switchSession: store.switchSession,
    deleteSession: store.deleteSession,
    startAutoSave() { /* no-op */ },
    stopAutoSave() { /* no-op */ },
    MAX_LOG_ENTRIES: 100,
    MAX_THINKING_ENTRIES: 50,
    MAX_HISTORY_ENTRIES: 10
  })
}
