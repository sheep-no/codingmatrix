import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { initApiClient } from './index'

describe('API 客户端形状与契约（FRESCAN-56/57）', () => {
  beforeEach(() => {
    window.api = undefined
    window.userStore = undefined
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => []
    })
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('暴露 aicloud 命名空间，供 Aicloud.vue 的调用点使用', () => {
    const api = initApiClient(null)

    expect(api.aicloud).toBeDefined()
    expect(typeof api.aicloud.listKnowledgeDocs).toBe('function')
    expect(typeof api.aicloud.chatStream).toBe('function')
    expect(typeof api.aicloud.executeCode).toBe('function')
  })

  it('根级 searchKnowledge 走 agent 端点并使用 q 参数', async () => {
    const api = initApiClient(null)

    await api.searchKnowledge('检索词')

    const [url] = global.fetch.mock.calls.at(-1)
    expect(url).toContain('/api/v1/agent/knowledge/search')
    expect(url).toContain('q=%E6%A3%80%E7%B4%A2%E8%AF%8D')
    expect(url).not.toContain('/aicloud/')
  })

  it('agent 检索把后端裸数组归一为 { results }', async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => [{ id: 1, content: '条目' }]
    })
    const api = initApiClient(null)

    const result = await api.searchKnowledge('条目')

    expect(result).toEqual({ results: [{ id: 1, content: '条目' }] })
  })
})
