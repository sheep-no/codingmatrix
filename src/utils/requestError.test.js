import { describe, expect, it } from 'vitest'
import { getRequestErrorMessage, normalizeRequestError } from './requestError'

describe('request error normalization', () => {
  it.each([
    [401, 'auth', false],
    [403, 'permission', false],
    [404, 'model', true],
    [429, 'rate_limit', true]
  ])('classifies HTTP %s errors', (status, kind, retryable) => {
    expect(normalizeRequestError({ response: { status }, message: 'upstream error' })).toMatchObject({ kind, status, retryable })
  })

  it('classifies network failures as retryable', () => {
    expect(normalizeRequestError(new TypeError('Failed to fetch'))).toMatchObject({ kind: 'network', retryable: true })
  })

  it('includes provider detail without losing actionable guidance', () => {
    const message = getRequestErrorMessage({ status: 429, message: 'quota exceeded' })
    expect(message).toContain('quota exceeded')
    expect(message).toContain('稍后重试')
  })

  it('redacts credentials from provider error details', () => {
    const normalized = normalizeRequestError(new Error('token=top-secret bearer abc.def'))
    expect(normalized.detail).toBe('token=[已隐藏] Bearer [已隐藏]')
  })
})
