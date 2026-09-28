import { createPinia, setActivePinia } from 'pinia'
import { shallowMount, flushPromises } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ElMessage } from 'element-plus'
import AgentDashboard from './AgentDashboard.vue'

let wrapper

function mountAgentDashboard() {
  // 初始化接口全部失败，验证不再静默吞掉错误
  window.api = {
    getRecommendedConcurrentLimits: vi.fn().mockRejectedValue(new Error('limits down')),
    getCacheStats: vi.fn().mockRejectedValue(new Error('cache down')),
    getLearningStats: vi.fn().mockRejectedValue(new Error('learning down')),
    listSkills: vi.fn().mockRejectedValue(new Error('skills down')),
    listAgentHostSessions: vi.fn().mockResolvedValue([]),
    get: vi.fn().mockRejectedValue(new Error('providers down'))
  }

  return shallowMount(AgentDashboard, {
    global: {
      plugins: [createPinia()],
      stubs: {
        AgentSidebar: { template: '<aside class="agent-sidebar" />' },
        AgentFilePanel: { template: '<aside class="agent-file-panel" />' },
        AgentTopBar: { template: '<header class="agent-topbar" />' },
        AgentWorkspace: { template: '<section class="agent-workspace" />' },
        AgentInputBar: { template: '<div class="agent-input-bar" />' },
        UploadModal: true,
        SettingsModal: true,
        LearningModal: true,
        PerformanceModal: true,
        VersionHistoryModal: true,
        DiffModal: true
      },
      mocks: { $router: { push: vi.fn() } }
    }
  })
}

describe('Agent Dashboard 初始化失败提示', () => {
  beforeEach(() => {
    localStorage.clear()
    setActivePinia(createPinia())
    vi.spyOn(ElMessage, 'error').mockImplementation(() => {})
  })

  afterEach(() => {
    wrapper?.unmount()
    wrapper = null
    vi.restoreAllMocks()
  })

  it('供应商列表加载失败时提示用户', async () => {
    wrapper = mountAgentDashboard()
    await flushPromises()

    expect(window.api.get).toHaveBeenCalledWith('/providers')
    expect(ElMessage.error).toHaveBeenCalledWith('加载供应商列表失败')
  })

  it('后端设置加载失败时提示用户', async () => {
    wrapper = mountAgentDashboard()
    await flushPromises()

    expect(window.api.getRecommendedConcurrentLimits).toHaveBeenCalled()
    expect(ElMessage.error).toHaveBeenCalledWith('加载后端设置失败')
  })
})
