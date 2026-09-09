import { reactive } from 'vue'

export function useGirlAiCompanion(girlApi) {
  const state = reactive({
    conversationId: null,
    stateRevision: 0,
    emotion: { label: 'neutral', intensity: 0, confidence: 0 },
    intent: { label: 'unknown', confidence: 0 },
    responseStyle: 'standard',
    capabilities: { text: true, voice_input: false, voice_output: false },
    degradedCapabilities: [],
    memories: [],
    isLoading: false,
    error: null
  })

  function mergeState(payload = {}) {
    const hasRevision = Number.isInteger(payload.state_revision)
    if (hasRevision && payload.state_revision < state.stateRevision) return payload
    if (payload.conversation_id) state.conversationId = payload.conversation_id
    if (hasRevision) state.stateRevision = payload.state_revision
    if (payload.emotion) state.emotion = payload.emotion
    if (payload.intent) state.intent = payload.intent
    if (payload.response_style) state.responseStyle = payload.response_style
    if (payload.capabilities) state.capabilities = payload.capabilities
    if (Array.isArray(payload.degraded_capabilities)) {
      state.degradedCapabilities = payload.degraded_capabilities
    }
    return payload
  }

  async function loadState() {
    state.error = null
    try {
      return mergeState(await girlApi.getCompanionState())
    } catch (error) {
      state.error = error
      throw error
    }
  }

  async function loadMemories(status = 'candidate') {
    state.error = null
    try {
      const payload = await girlApi.getCompanionMemories(20, 0, status)
      state.memories = Array.isArray(payload.memories) ? payload.memories : []
      return payload
    } catch (error) {
      state.error = error
      throw error
    }
  }

  async function sendTurn(prompt, characterId, options) {
    state.isLoading = true
    state.error = null
    try {
      const payload = mergeState(await girlApi.sendCompanionTurn(prompt, characterId, options))
      if (Array.isArray(payload.memory_candidates)) {
        state.memories = payload.memory_candidates
      }
      return payload
    } catch (error) {
      state.error = error
      throw error
    } finally {
      state.isLoading = false
    }
  }

  async function sendVoiceTranscription(transcript, characterId, options = {}) {
    state.isLoading = true
    state.error = null
    try {
      const payload = mergeState(
        await girlApi.sendVoiceTranscription(transcript, characterId, options)
      )
      if (Array.isArray(payload.memory_candidates)) state.memories = payload.memory_candidates
      return payload
    } catch (error) {
      state.error = error
      throw error
    } finally {
      state.isLoading = false
    }
  }

  async function confirmMemory(memoryId, data = {}) {
    const memory = await girlApi.confirmCompanionMemory(memoryId, data)
    state.memories = state.memories.filter(item => item.id !== memoryId)
    return memory
  }

  async function deleteMemory(memoryId) {
    const result = await girlApi.deleteCompanionMemory(memoryId)
    state.memories = state.memories.filter(item => item.id !== memoryId)
    return result
  }

  return { state, loadState, loadMemories, sendTurn, sendVoiceTranscription, confirmMemory, deleteMemory }
}
