import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createBaseClient } from './base'

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
})
