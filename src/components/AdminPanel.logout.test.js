import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  routerPush: vi.fn(),
  confirm: vi.fn(() => Promise.resolve()),
  logout: vi.fn(),
  clearUser: vi.fn(),
  disconnect: vi.fn(),
  restoreUser: vi.fn()
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: mocks.routerPush })
}))

vi.mock('element-plus', () => ({
  ElMessageBox: { confirm: mocks.confirm }
}))

vi.mock('echarts', () => ({
  init: vi.fn(() => ({
    setOption: vi.fn(),
    dispose: vi.fn(),
    resize: vi.fn()
  }))
}))

vi.mock('@/stores/user', () => ({
  useUserStore: () => ({
    username: 'admin',
    isAdmin: true,
    isSuperUser: false,
    getAccessToken: () => 'token',
    restoreUser: mocks.restoreUser,
    clearUser: mocks.clearUser
  })
}))

vi.mock('@/utils/api/index', () => ({
  API_CONFIG: { WS_BASE_URL: 'ws://localhost' },
  api: { logout: mocks.logout },
  WebSocketManager: class {
    connect() {}
    disconnect() {
      mocks.disconnect()
    }
    scheduleReconnect() {}
  }
}))

import AdminPanel from './AdminPanel.vue'

describe('AdminPanel 退出登录', () => {
  beforeEach(() => {
    localStorage.clear()
    localStorage.setItem('access_token', 'token')
    mocks.routerPush.mockReset()
    mocks.confirm.mockReset()
    mocks.confirm.mockResolvedValue()
    mocks.logout.mockReset()
    mocks.logout.mockResolvedValue({ ok: true })
    mocks.clearUser.mockReset()
    mocks.disconnect.mockReset()
    mocks.restoreUser.mockReset()
  })

  afterEach(() => {
    localStorage.clear()
  })

  it('吊销服务端令牌并清理用户状态（FRESCAN-53）', async () => {
    const wrapper = mount(AdminPanel)
    await flushPromises()

    await wrapper.get('.logout-btn').trigger('click')
    await flushPromises()

    expect(mocks.confirm).toHaveBeenCalled()
    expect(mocks.logout).toHaveBeenCalledTimes(1)
    expect(mocks.clearUser).toHaveBeenCalledTimes(1)
    expect(mocks.routerPush).toHaveBeenCalledWith('/')
    wrapper.unmount()
  })

  it('取消确认时不发起登出请求', async () => {
    mocks.confirm.mockRejectedValueOnce(new Error('cancel'))
    const wrapper = mount(AdminPanel)
    await flushPromises()

    await wrapper.get('.logout-btn').trigger('click')
    await flushPromises()

    expect(mocks.logout).not.toHaveBeenCalled()
    expect(mocks.clearUser).not.toHaveBeenCalled()
    expect(mocks.routerPush).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('服务端登出失败仍完成本地清理', async () => {
    mocks.logout.mockRejectedValueOnce(new Error('network down'))
    const wrapper = mount(AdminPanel)
    await flushPromises()

    await wrapper.get('.logout-btn').trigger('click')
    await flushPromises()

    expect(mocks.clearUser).toHaveBeenCalledTimes(1)
    expect(mocks.routerPush).toHaveBeenCalledWith('/')
    wrapper.unmount()
  })
})
