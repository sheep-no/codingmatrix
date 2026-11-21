import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

const tokenManagerMock = vi.hoisted(() => ({
  getToken: vi.fn(() => null),
  isTokenValid: vi.fn(() => false),
  setToken: vi.fn(),
  clearToken: vi.fn(),
  refreshAccessToken: vi.fn()
}))

vi.mock('@/utils/tokenManager', () => ({
  useTokenManager: () => tokenManagerMock
}))

import { useUserStore } from './user'

describe('user store 会话恢复', () => {
  beforeEach(() => {
    localStorage.clear()
    setActivePinia(createPinia())
    tokenManagerMock.getToken.mockReset().mockReturnValue(null)
    tokenManagerMock.refreshAccessToken.mockReset()
  })

  it('无本地登录身份时不发起刷新', async () => {
    const store = useUserStore()

    await expect(store.ensureSession()).resolves.toBe(false)
    expect(tokenManagerMock.refreshAccessToken).not.toHaveBeenCalled()
  })

  it('有登录身份但无 access token 时用 refresh cookie 换取 token', async () => {
    localStorage.setItem('username', 'admin_test')
    tokenManagerMock.refreshAccessToken.mockResolvedValue(true)
    tokenManagerMock.getToken
      .mockReturnValueOnce(null)
      .mockReturnValue('fresh-token')
    const store = useUserStore()

    await expect(store.ensureSession()).resolves.toBe(true)
    expect(tokenManagerMock.refreshAccessToken).toHaveBeenCalledTimes(1)
    expect(store.isLoggedIn).toBe(true)
  })

  it('刷新失败时清理本地会话', async () => {
    localStorage.setItem('username', 'admin_test')
    tokenManagerMock.refreshAccessToken.mockResolvedValue(false)
    const store = useUserStore()

    await expect(store.ensureSession()).resolves.toBe(false)
    expect(localStorage.getItem('username')).toBeNull()
    expect(store.isLoggedIn).toBe(false)
  })

  it('并发调用共享同一次刷新请求', async () => {
    localStorage.setItem('username', 'admin_test')
    let resolveRefresh
    tokenManagerMock.refreshAccessToken.mockReturnValue(new Promise(resolve => {
      resolveRefresh = resolve
    }))
    const store = useUserStore()

    const first = store.ensureSession()
    const second = store.ensureSession()
    resolveRefresh(true)
    tokenManagerMock.getToken.mockReturnValue('fresh-token')

    await expect(Promise.all([first, second])).resolves.toEqual([true, true])
    expect(tokenManagerMock.refreshAccessToken).toHaveBeenCalledTimes(1)
  })
})
