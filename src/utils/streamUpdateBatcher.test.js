import { describe, expect, it, vi } from 'vitest'
import { createStreamUpdateBatcher } from './streamUpdateBatcher'

describe('createStreamUpdateBatcher', () => {
  it('merges text deltas and commits once per scheduled frame', () => {
    const commit = vi.fn()
    let scheduledCallback
    const batcher = createStreamUpdateBatcher(commit, {
      schedule: callback => {
        scheduledCallback = callback
        return 1
      },
      cancel: vi.fn()
    })

    batcher.enqueue({ key: 'session:0', responseDelta: 'a' })
    batcher.enqueue({ key: 'session:0', responseDelta: 'b', reasoningDelta: 'r' })

    expect(commit).not.toHaveBeenCalled()
    scheduledCallback()
    expect(commit).toHaveBeenCalledOnce()
    expect(commit).toHaveBeenCalledWith(expect.objectContaining({
      key: 'session:0',
      responseDelta: 'ab',
      reasoningDelta: 'r'
    }))
  })

  it('flushes pending text immediately for terminal events', () => {
    const commit = vi.fn()
    const cancel = vi.fn()
    const batcher = createStreamUpdateBatcher(commit, {
      schedule: () => 7,
      cancel
    })

    batcher.enqueue({ key: 'session:0', reasoningDelta: 'final' })
    batcher.flush()

    expect(cancel).toHaveBeenCalledWith(7)
    expect(commit).toHaveBeenCalledWith(expect.objectContaining({ reasoningDelta: 'final' }))
  })
})
