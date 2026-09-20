// @vitest-environment jsdom
import { describe, expect, it, vi } from 'vitest'

const { postMock, putMock } = vi.hoisted(() => ({
  postMock: vi.fn(),
  putMock: vi.fn(),
}))

vi.mock('@/stores/user', () => ({
  useUserStore: () => ({
    restoreUser: vi.fn(),
    setUser: vi.fn(),
    clearUser: vi.fn(),
    refreshAccessToken: vi.fn(),
  }),
}))

vi.mock('@/composables/useToast', () => ({
  useToast: () => ({ error: vi.fn(), success: vi.fn() }),
}))

vi.mock('@/utils/api/index', () => ({
  api: { post: postMock, put: putMock },
}))

import { useAuth } from '@/composables/useAuth'

describe('useAuth 与后端认证端点契约', () => {
  it('register 请求 /register（后端挂在 /api/v1/register）', async () => {
    postMock.mockResolvedValue({ ok: true, json: async () => ({}) })
    const { register } = useAuth()

    const result = await register('user', 'user@example.com', 'secret')

    expect(result).toEqual({ success: true })
    expect(postMock).toHaveBeenCalledWith('/register', {
      username: 'user',
      email: 'user@example.com',
      password: 'secret',
    })
  })

  it('不再暴露 updateProfile（后端无资料更新端点）', () => {
    expect(useAuth().updateProfile).toBeUndefined()
    expect(putMock).not.toHaveBeenCalled()
  })
})
