import { describe, expect, it, vi } from 'vitest'

import { useGirlAiCompanion } from './useGirlAiCompanion'

describe('useGirlAiCompanion', () => {
  it('merges newer turn state and exposes memory candidates', async () => {
    const girlApi = {
      sendCompanionTurn: vi.fn().mockResolvedValue({
        conversation_id: 'conversation-1',
        state_revision: 3,
        emotion: { label: 'happy', intensity: 0.8, confidence: 0.9 },
        memory_candidates: [{ id: 'memory-1', key: '偏好', value: '安静', confidence: 0.8 }]
      })
    }
    const companion = useGirlAiCompanion(girlApi)

    await companion.sendTurn('今天心情不错', 'gentle')

    expect(companion.state.conversationId).toBe('conversation-1')
    expect(companion.state.stateRevision).toBe(3)
    expect(companion.state.emotion.label).toBe('happy')
    expect(companion.state.memories).toHaveLength(1)
    expect(companion.state.isLoading).toBe(false)
  })

  it('removes a memory after confirmation or deletion', async () => {
    const girlApi = {
      getCompanionMemories: vi.fn().mockResolvedValue({
        memories: [{ id: 'memory-1', key: '偏好', value: '安静' }]
      }),
      confirmCompanionMemory: vi.fn().mockResolvedValue({ id: 'memory-1', status: 'confirmed' }),
      deleteCompanionMemory: vi.fn().mockResolvedValue({ id: 'memory-2', status: 'deleted' })
    }
    const companion = useGirlAiCompanion(girlApi)

    await companion.loadMemories()
    await companion.confirmMemory('memory-1')
    expect(companion.state.memories).toEqual([])

    companion.state.memories.push({ id: 'memory-2' })
    await companion.deleteMemory('memory-2')
    expect(companion.state.memories).toEqual([])
  })

  it('keeps the newest revision when responses arrive out of order', async () => {
    const girlApi = {
      getCompanionState: vi.fn()
        .mockResolvedValueOnce({ state_revision: 5, emotion: { label: 'focused' } })
        .mockResolvedValueOnce({ state_revision: 4, emotion: { label: 'sad' } })
    }
    const companion = useGirlAiCompanion(girlApi)

    await companion.loadState()
    await companion.loadState()

    expect(companion.state.stateRevision).toBe(5)
    expect(companion.state.emotion.label).toBe('focused')
  })
})
