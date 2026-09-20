// @vitest-environment jsdom
import { defineComponent, h } from 'vue'
import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/composables/useToast', () => ({
  useToast: () => ({ warning: vi.fn(), success: vi.fn(), error: vi.fn() })
}))

import { useOfflineQueue } from './useOfflineQueue'

const QUEUE_KEY = 'offlineMessageQueue'

let queue
const Host = defineComponent({
  setup() {
    queue = useOfflineQueue()
    return () => h('div')
  }
})

describe('useOfflineQueue', () => {
  beforeEach(() => {
    localStorage.clear()
    queue = null
  })

  it('flushQueue 发送失败时按原顺序保留失败消息及其后续消息', async () => {
    mount(Host)
    queue.queueMessage({ prompt: 'a' })
    queue.queueMessage({ prompt: 'b' })
    queue.queueMessage({ prompt: 'c' })

    const sent = []
    queue.setSendCallback(async message => {
      sent.push(message.prompt)
      if (message.prompt === 'b') {
        throw new Error('network down')
      }
    })

    await queue.flushQueue()

    expect(sent).toEqual(['a', 'b'])
    expect(queue.pendingMessages.value.map(m => m.prompt)).toEqual(['b', 'c'])
  })

  it('挂载时已在线的恢复队列会被自动补发', async () => {
    localStorage.setItem(
      QUEUE_KEY,
      JSON.stringify([{ id: 'queued_1', prompt: 'restored', queuedAt: 1 }])
    )

    mount(Host)
    const sendCallback = vi.fn().mockResolvedValue(undefined)
    queue.setSendCallback(sendCallback)

    await new Promise(resolve => setTimeout(resolve, 0))

    expect(sendCallback).toHaveBeenCalledWith(
      expect.objectContaining({ prompt: 'restored' })
    )
    expect(queue.pendingMessages.value).toEqual([])
  })
})
