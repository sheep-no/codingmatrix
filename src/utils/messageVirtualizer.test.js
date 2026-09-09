import { describe, expect, it } from 'vitest'
import {
  calculateVisibleRange,
  getMessageOffset,
  getTotalMessageHeight
} from './messageVirtualizer'

describe('messageVirtualizer', () => {
  const messages = Array.from({ length: 6 }, (_, index) => ({ id: `message-${index}` }))

  it('uses measured heights while retaining estimates for unseen messages', () => {
    const heights = new Map([
      ['message-0', 100],
      ['message-1', 300]
    ])

    expect(getMessageOffset(messages, 2, heights)).toBe(448)
    expect(getTotalMessageHeight(messages, heights)).toBe(1344)
  })

  it('returns a buffered range for variable-height messages', () => {
    const heights = new Map(messages.map(message => [message.id, 100]))

    expect(
      calculateVisibleRange({
        messages,
        measuredHeights: heights,
        scrollTop: 248,
        viewportHeight: 124,
        buffer: 1
      })
    ).toEqual({ start: 1, end: 4 })
  })

  it('keeps ranges within empty and populated list boundaries', () => {
    expect(
      calculateVisibleRange({
        messages: [],
        measuredHeights: new Map(),
        scrollTop: 0,
        viewportHeight: 500,
        buffer: 5
      })
    ).toEqual({ start: 0, end: 0 })
  })
})
