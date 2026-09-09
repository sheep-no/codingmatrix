import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createBaseClient, normalizeApiError } from './base'

describe('base API client', () => {
  beforeEach(() => {
    localStorage.clear()
    sessionStorage.clear()
    window.userStore = undefined
    window.api = undefined
  })

  it('adds authentication to FormData without forcing a content type', async () => {
    const payload = btoa(JSON.stringify({ exp: Math.floor(Date.now() / 1000) + 3600 }))
    const token = `header.${payload}.signature`
    localStorage.setItem('access_token', token)
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue({ ok: true, status: 200 })
    const formData = new FormData()
    formData.append('file', new Blob(['content']), 'test.txt')

    await createBaseClient().request('/files/upload', { method: 'POST', body: formData })

    const [, options] = fetchMock.mock.calls[0]
    expect(options.headers.Authorization).toBe(`Bearer ${token}`)
    expect(options.headers['Content-Type']).toBeUndefined()
    fetchMock.mockRestore()
  })

  it('passes abort signals and normalizes canceled requests', async () => {
    const controller = createBaseClient().createAbortController()
    const abortError = new DOMException('Aborted', 'AbortError')
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockRejectedValue(abortError)

    await expect(createBaseClient().request('/slow', { signal: controller.signal })).rejects.toMatchObject({
      name: 'ApiError',
      code: 'REQUEST_ABORTED',
      isCanceled: true
    })
    expect(fetchMock.mock.calls[0][1].signal).toBe(controller.signal)
    fetchMock.mockRestore()
  })

  it('normalizes arbitrary request errors with a stable code', () => {
    const error = normalizeApiError(new Error('服务不可用'))

    expect(error).toMatchObject({ name: 'ApiError', code: 'API_REQUEST_FAILED', message: '服务不可用' })
  })
})
