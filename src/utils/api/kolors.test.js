import { describe, expect, it, vi } from 'vitest'

import { createKolorsClient } from './kolors'

function jsonResponse(payload, { ok = true, status = 200 } = {}) {
  return { ok, status, json: vi.fn().mockResolvedValue(payload), blob: vi.fn() }
}

describe('kolors 客户端契约（FRESCAN-70）', () => {
  it('文生图通过基础客户端发送并透传中止信号', async () => {
    const client = { request: vi.fn().mockResolvedValue(jsonResponse({ images: ['a.png'] })) }
    const signal = new AbortController().signal

    const result = await createKolorsClient(client).textToImage('海边灯塔', { width: 512 }, 'token-1', signal)

    expect(client.request).toHaveBeenCalledWith('/kolors/text-to-image', {
      method: 'POST',
      body: JSON.stringify({ prompt: '海边灯塔', api_key_token: 'token-1', width: 512 }),
      signal
    })
    expect(result).toEqual({ images: ['a.png'] })
  })

  it('图生图把 FormData 原样交给基础客户端', async () => {
    const client = { request: vi.fn().mockResolvedValue(jsonResponse({ paths: ['a.png'] })) }
    const formData = new FormData()
    formData.append('prompt', '海边灯塔')

    await createKolorsClient(client).imageToImage(formData)

    expect(client.request).toHaveBeenCalledWith('/kolors/image-to-image', {
      method: 'POST',
      body: formData,
      signal: null
    })
  })

  it('失败时抛出后端 detail 而不是返回畸形数据', async () => {
    const client = {
      request: vi.fn().mockResolvedValue(jsonResponse({ detail: '额度不足' }, { ok: false, status: 429 }))
    }

    await expect(createKolorsClient(client).textToImage('x')).rejects.toThrow('额度不足')
  })

  it('历史分页使用 page_size 参数', async () => {
    const client = { get: vi.fn().mockResolvedValue(jsonResponse({ items: [] })) }

    await createKolorsClient(client).getHistory(2, 50)

    expect(client.get).toHaveBeenCalledWith('/kolors/history', { page: 2, page_size: 50 })
  })

  it('历史图片通过认证端点读取 blob', async () => {
    const blob = new Blob(['fixture'], { type: 'image/png' })
    const response = jsonResponse({})
    response.blob.mockResolvedValue(blob)
    const client = { get: vi.fn().mockResolvedValue(response) }

    const result = await createKolorsClient(client).getResourceBlob('kolors 1.png')

    expect(client.get).toHaveBeenCalledWith('/kolors/resources/kolors%201.png')
    expect(result).toBe(blob)
  })
})
