import { beforeEach, describe, expect, it, vi } from 'vitest'

const axiosMock = vi.hoisted(() => ({ create: vi.fn() }))

vi.mock('axios', () => ({ default: { create: axiosMock.create } }))

async function installInterceptors() {
  vi.resetModules()
  const { createGithubClient } = await import('./github')
  const handlers = {}
  axiosMock.create.mockReturnValue({
    interceptors: {
      request: { use: (onFulfilled) => { handlers.request = onFulfilled } },
      response: { use: (_onFulfilled, onRejected) => { handlers.responseError = onRejected } }
    }
  })
  createGithubClient()
  return handlers
}

describe('toGithubRepoName', () => {
  let toGithubRepoName

  beforeEach(async () => {
    vi.resetModules()
    ;({ toGithubRepoName } = await import('./github'))
  })

  it('keeps a valid GitHub repo name', () => {
    expect(toGithubRepoName('demo-app')).toBe('demo-app')
  })

  it('strips non-ascii characters and edge punctuation', () => {
    expect(toGithubRepoName('项目_2026')).toBe('2026')
    expect(toGithubRepoName('...')).toBe('project')
  })

  it('truncates names longer than 100 characters', () => {
    expect(toGithubRepoName('a'.repeat(120))).toBe('a'.repeat(100))
  })
})

describe('GitHub 客户端认证（FRESCAN-65）', () => {
  beforeEach(() => {
    localStorage.clear()
    sessionStorage.clear()
    window.userStore = undefined
    axiosMock.create.mockReset()
  })

  it('通过 base 客户端的 getValidToken 读取内存 token', async () => {
    window.userStore = { getAccessToken: () => 'memory-token' }
    const { request } = await installInterceptors()

    const config = request({ headers: {} })

    expect(config.headers.Authorization).toBe('Bearer memory-token')
  })

  it('401 时调用 clearUser 并广播 session-expired', async () => {
    const clearUser = vi.fn()
    window.userStore = { getAccessToken: () => 'expired', clearUser }
    const onExpired = vi.fn()
    window.addEventListener('session-expired', onExpired)
    const { responseError } = await installInterceptors()

    await expect(responseError({ response: { status: 401 } })).rejects.toBeDefined()

    expect(clearUser).toHaveBeenCalledOnce()
    expect(onExpired).toHaveBeenCalledOnce()
    expect(onExpired.mock.calls[0][0].detail.message).toContain('会话已过期')
    window.removeEventListener('session-expired', onExpired)
  })
})
