import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

const listApiKeys = vi.hoisted(() => vi.fn())

vi.mock('@/api/apikey', () => ({
  getPublicKey: vi.fn(),
  submitApiKey: vi.fn(),
  testApiKey: vi.fn(),
  deleteApiKey: vi.fn(),
  listApiKeys,
  updateApiKeyEnabled: vi.fn(),
  updateApiKeyContextLengths: vi.fn()
}))
vi.mock('@/utils/crypto', () => ({ encryptWithRSAPublicKey: vi.fn() }))

import { useApiKeyStore } from './apikey'

const AUTH_KEY = 'codingmatrix_apikeys'
const OWNER_KEY = 'codingmatrix_apikeys_owner'

describe('apikey store 账号隔离', () => {
  beforeEach(() => {
    localStorage.clear()
    setActivePinia(createPinia())
    listApiKeys.mockReset()
  })

  it('丢弃属于其他账号的本地密钥缓存', () => {
    localStorage.setItem('username', 'current_user')
    localStorage.setItem(AUTH_KEY, JSON.stringify([{ provider: 'siliconflow', token: 'previous-token' }]))
    localStorage.setItem(OWNER_KEY, 'previous_user')

    const store = useApiKeyStore()

    expect(store.tokens).toEqual([])
    expect(localStorage.getItem(AUTH_KEY)).toBeNull()
    expect(localStorage.getItem(OWNER_KEY)).toBeNull()
  })

  it('旧缓存没有归属标记时视为当前账号并补记归属', () => {
    localStorage.setItem('username', 'current_user')
    localStorage.setItem(AUTH_KEY, JSON.stringify([{ provider: 'siliconflow', token: 'legacy-token' }]))

    const store = useApiKeyStore()

    expect(store.tokens).toHaveLength(1)
    expect(localStorage.getItem(OWNER_KEY)).toBe('current_user')
  })

  it('每个账号每次会话只向后端校准一次', async () => {
    localStorage.setItem('username', 'current_user')
    listApiKeys.mockResolvedValue([{ provider: 'siliconflow', token: 'server-token', enabled: true }])
    const store = useApiKeyStore()

    await store.ensureSynced()
    await store.ensureSynced()

    expect(listApiKeys).toHaveBeenCalledTimes(1)
    expect(store.tokens).toEqual([{ provider: 'siliconflow', token: 'server-token', enabled: true }])
  })

  it('本地已有缓存时首次发送仍以后端记录为准', async () => {
    localStorage.setItem('username', 'current_user')
    localStorage.setItem(AUTH_KEY, JSON.stringify([{ provider: 'siliconflow', token: 'stale-token', enabled: true }]))
    localStorage.setItem(OWNER_KEY, 'current_user')
    listApiKeys.mockResolvedValue([{ provider: 'siliconflow', token: 'server-token', enabled: true }])
    const store = useApiKeyStore()
    expect(store.tokens[0].token).toBe('stale-token')

    await store.ensureSynced()

    expect(listApiKeys).toHaveBeenCalledTimes(1)
    expect(store.tokens[0].token).toBe('server-token')
  })

  it('reset 清空内存状态，避免注销后残留上一账号令牌', () => {
    localStorage.setItem('username', 'current_user')
    listApiKeys.mockResolvedValue([{ provider: 'siliconflow', token: 'server-token', enabled: true }])
    const store = useApiKeyStore()
    store.tokens = [{ provider: 'siliconflow', token: 'server-token', enabled: true }]

    store.reset()

    expect(store.tokens).toEqual([])
    expect(store.siliconflowKey).toBeUndefined()
  })
})
