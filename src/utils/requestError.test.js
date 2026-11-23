import { describe, expect, it } from 'vitest'
import {
  extractApiErrorMessage,
  getRequestErrorMessage,
  normalizeRequestError,
  stripTransportPlaceholderLines
} from './requestError'

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

  it('extracts backend message before detail', () => {
    expect(extractApiErrorMessage({ code: 'INPUT_VALIDATION_FAILED', message: '检测到疑似 XSS 攻击内容' }))
      .toBe('检测到疑似 XSS 攻击内容')
    expect(extractApiErrorMessage({ detail: '模型不存在' })).toBe('模型不存在')
  })

  it('flattens FastAPI validation detail arrays', () => {
    expect(extractApiErrorMessage({ detail: [{ msg: '字段必填' }, { msg: '长度超限' }] }))
      .toBe('字段必填；长度超限')
  })

  it('drops transport placeholder messages so users see the backend text', () => {
    expect(normalizeRequestError(new Error('HTTP error! status: 400')).message).toBe('请求失败')
    expect(normalizeRequestError({ status: 429, message: 'HTTP error! status: 429' }).message)
      .toBe('请求过于频繁或服务额度已用尽，请稍后重试。')
  })

  it('keeps backend detail readable in one line for non-retryable statuses', () => {
    const normalized = normalizeRequestError({ status: 403, message: '当前账号无权访问该工具' })
    expect(normalized.message).toBe('当前账号没有执行此模型调用的权限。（当前账号无权访问该工具）')
    expect(normalized.message).not.toContain('HTTP error! status')
  })

  it('strips legacy transport placeholder lines from stored responses', () => {
    expect(stripTransportPlaceholderLines('正常回答\n\n出错：HTTP error! status: 400\n')).toBe('正常回答')
    expect(stripTransportPlaceholderLines('出错：HTTP error! status: 400')).toBe('')
    expect(stripTransportPlaceholderLines('第一段\n第二段')).toBe('第一段\n第二段')
  })
})
