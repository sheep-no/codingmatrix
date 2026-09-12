import { describe, expect, it, vi } from 'vitest'
import { createPptClient } from './ppt'

describe('outline generation options', () => {
  it('consumes SSE outline events and returns the finished draft', async () => {
    const draft = { id: 'outline-stream', slides: [{ title: '机会' }] }
    const encoder = new TextEncoder()
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode(`data: ${JSON.stringify({ type: 'stage', index: 0 })}\n\n`))
        controller.enqueue(encoder.encode(`data: ${JSON.stringify({ type: 'slide', slide: { title: '机会' } })}\n\n`))
        controller.enqueue(encoder.encode(`data: ${JSON.stringify({ type: 'done', draft })}\n\n`))
        controller.close()
      },
    })
    const request = vi.fn().mockResolvedValue({
      ok: true,
      headers: { get: () => 'text/event-stream' },
      body: stream,
    })
    const events = []
    const result = await createPptClient({ request }).createOutline({ topic: '增长' }, { onEvent: event => events.push(event) })
    expect(request).toHaveBeenCalledWith('/pptx/outlines', expect.objectContaining({
      method: 'POST',
      headers: { Accept: 'text/event-stream' },
    }))
    expect(events.map(event => event.type)).toEqual(['stage', 'slide', 'done'])
    expect(result).toEqual(draft)
  })

  it('falls back to a JSON outline response', async () => {
    const draft = { id: 'outline-json', slides: [] }
    const request = vi.fn().mockResolvedValue({
      ok: true,
      headers: { get: () => 'application/json' },
      json: async () => draft,
    })
    await expect(createPptClient({ request }).createOutline({ topic: '增长' })).resolves.toEqual(draft)
  })

  it('encodes template recommendation queries and retains the plain registry endpoint', async () => {
    const get = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ templates: [] }) })
    const ppt = createPptClient({ get })
    await ppt.getTemplates()
    expect(get).toHaveBeenLastCalledWith('/pptx/templates')
    await ppt.getTemplates(null, { topic: '增长 & 产品', scenario: 'product_pitch' })
    const query = new URL(get.mock.calls[1][0], 'http://test').searchParams
    expect(query.get('topic')).toBe('增长 & 产品')
    expect(query.get('scenario')).toBe('product_pitch')
  })
  it('sends the complete targeted edit and base version', async () => {
    const post = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ task_id: 'new-task' }) })
    const slide = { id: 'slide-2', title: '修改', content_blocks: [{ content: '实际正文' }] }
    await createPptClient({ post }).regenerateOutlineSlide('outline', 'slide-2', 'refined', slide, 2, {
      auto_images: false, enable_animation: false, api_key_token: 'user-token',
    })
    expect(post).toHaveBeenCalledWith('/pptx/outlines/outline/slides/slide-2/regenerate', {
      quality_mode: 'refined', slide, outline_version: 2, output_format: 'pptx',
      auto_images: false, enable_animation: false, api_key_token: 'user-token',
    })
  })

  it('exposes the saved version for export retry', async () => {
    const post = vi.fn().mockResolvedValue({ ok: false, json: async () => ({
      code: 'SERVICE_UNAVAILABLE', message: '修改已保存，导出失败', details: { outline_version: 3 },
    }) })
    await expect(createPptClient({ post }).regenerateOutlineSlide('outline', 'page', 'standard', {}, 2))
      .rejects.toMatchObject({ message: '修改已保存，导出失败', savedVersion: 3 })
  })

  it('preserves explicitly disabled options and the selected output', async () => {
    const post = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ task_id: 'task' }) })
    await createPptClient({ post }).generateFromOutline('outline', 'refined', 3, {
      output_format: 'pdf', auto_images: false, enable_animation: false, api_key_token: 'user-token',
    })
    expect(post).toHaveBeenCalledWith('/pptx/outlines/outline/generate', {
      quality_mode: 'refined', outline_version: 3, output_format: 'pdf',
      auto_images: false, enable_animation: false, api_key_token: 'user-token',
    })
  })

  it('throws when history listing fails', async () => {
    const get = vi.fn().mockResolvedValue({ ok: false, json: async () => ({ detail: '未授权' }) })
    await expect(createPptClient({ get }).getHistory()).rejects.toThrow('未授权')
  })
})
