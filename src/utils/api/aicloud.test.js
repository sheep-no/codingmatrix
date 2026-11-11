// @vitest-environment node
import { describe, expect, it } from 'vitest'

import { createAiCloudClient } from './aicloud'

describe('AiCloud 客户端契约', () => {
  it('审查操作与后端端点一一对应', () => {
    const client = createAiCloudClient({})

    // GET /reviews、POST /reviews/approve、POST /reviews/reject 是后端已挂载的端点。
    expect(typeof client.getReviews).toBe('function')
    expect(typeof client.approveReview).toBe('function')
    expect(typeof client.rejectReview).toBe('function')
    // 后端未定义 /aicloud/reviews/toggle，客户端不应暴露对应方法。
    expect(client.toggleReview).toBeUndefined()
  })

  it('历史加载失败时抛错，供页面展示失败态（FRESCAN-68）', async () => {
    const client = createAiCloudClient({
      get: async () => ({
        ok: false,
        json: async () => ({ detail: '需要管理员权限' })
      })
    })

    await expect(client.getHistory()).rejects.toThrow('需要管理员权限')
  })

  it('历史成功响应统一返回数组（FRESCAN-68）', async () => {
    const emptyClient = createAiCloudClient({
      get: async () => ({ ok: true, json: async () => ({ messages: [] }) })
    })
    await expect(emptyClient.getHistory()).resolves.toEqual([])

    const listClient = createAiCloudClient({
      get: async () => ({ ok: true, json: async () => [{ id: 's1' }] })
    })
    await expect(listClient.getHistory()).resolves.toEqual([{ id: 's1' }])
  })

  it('历史检索使用后端的 keyword 参数（FRESCAN-51）', async () => {
    const calls = []
    const client = createAiCloudClient({
      get: async (path, params) => {
        calls.push({ path, params })
        return { ok: true, json: async () => [{ session_id: 's1' }] }
      }
    })

    await expect(client.searchHistory('部署')).resolves.toEqual([{ session_id: 's1' }])
    expect(calls[0]).toEqual({
      path: '/aicloud/history/search',
      params: { keyword: '部署' }
    })
  })
})
