import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('@/utils/tokenManager', () => ({
  useTokenManager: () => ({
    clearToken: vi.fn(),
    getToken: vi.fn(() => null),
    isTokenValid: vi.fn(() => false)
  })
}))

import { useUserStore } from './user'

describe('user store 注销清理', () => {
  beforeEach(() => {
    localStorage.clear()
    setActivePinia(createPinia())
  })

  it('clearUser 清除按浏览器持久化的 Agent 会话与生成器状态', () => {
    localStorage.setItem('agent_project_sessions', JSON.stringify([{ id: '1', prompt: 'secret' }]))
    localStorage.setItem('project_generator_state', JSON.stringify({ form: { requirement: 'secret' } }))
    localStorage.setItem('access_token', 'token')

    useUserStore().clearUser()

    expect(localStorage.getItem('agent_project_sessions')).toBeNull()
    expect(localStorage.getItem('project_generator_state')).toBeNull()
    expect(localStorage.getItem('access_token')).toBeNull()
  })

  it('clearUser 清除 API Key / 供应商 / 模型覆盖缓存（FRESCAN-47）', () => {
    localStorage.setItem('codingmatrix_apikeys', JSON.stringify([{ provider: 'siliconflow', token: 'x' }]))
    localStorage.setItem('codingmatrix_rsa_public_key', 'pubkey')
    localStorage.setItem('codingmatrix_model_overrides', JSON.stringify({ siliconflow: ['m'] }))
    localStorage.setItem('codingmatrix_providers', JSON.stringify([{ base_url: 'https://x' }]))

    useUserStore().clearUser()

    expect(localStorage.getItem('codingmatrix_apikeys')).toBeNull()
    expect(localStorage.getItem('codingmatrix_rsa_public_key')).toBeNull()
    expect(localStorage.getItem('codingmatrix_model_overrides')).toBeNull()
    expect(localStorage.getItem('codingmatrix_providers')).toBeNull()
  })

  it('clearUser 清除系统日志与过滤状态（FRESCAN-48）', () => {
    localStorage.setItem('systemLogsState', JSON.stringify({
      systemLogs: [{ level: 'error', message: 'secret' }],
      filterKeyword: 'secret'
    }))

    useUserStore().clearUser()

    expect(localStorage.getItem('systemLogsState')).toBeNull()
  })
})
