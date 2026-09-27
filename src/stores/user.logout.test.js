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
})
