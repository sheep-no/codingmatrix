import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const getServices = vi.fn()

vi.mock('@/utils/api/index', () => ({
  createApiClient: () => ({})
}))

vi.mock('@/utils/api/admin', () => ({
  createAdminClient: () => ({
    getServices
  })
}))

vi.mock('@/stores/user', () => ({
  useUserStore: () => ({ token: 't' })
}))

import ServiceManager from './ServiceManager.vue'

describe('ServiceManager', () => {
  beforeEach(() => {
    getServices.mockReset()
    getServices.mockResolvedValue({ services: [], learned: 0, enabled: 0 })
  })

  it('renders the service board and empty list', async () => {
    const wrapper = mount(ServiceManager)
    expect(wrapper.get('h2').text()).toBe('服务管理')
    expect(wrapper.text()).toContain('启动服务监控')
    expect(wrapper.text()).toContain('服务列表')
    await flushPromises()
    expect(wrapper.text()).toContain('暂无服务')
    expect(wrapper.text()).toContain('已学习服务')
  })

  it('shows fullwidth colons on service details', async () => {
    getServices.mockResolvedValue({
      services: [
        {
          name: 'api',
          port: 8000,
          restart_cmd: 'systemctl restart api',
          process_signature: 'uvicorn',
          fuse_enabled: true
        }
      ],
      learned: 1,
      enabled: 1
    })
    const wrapper = mount(ServiceManager)
    await flushPromises()
    expect(wrapper.text()).toContain('端口：8000')
    expect(wrapper.text()).toContain('重启命令：')
    expect(wrapper.text()).toContain('进程签名：')
    expect(wrapper.text()).toContain('熔断状态：')
  })
})
