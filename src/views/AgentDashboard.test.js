import { createPinia, setActivePinia } from 'pinia'
import { shallowMount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import AgentDashboard from './AgentDashboard.vue'

let wrapper

const AgentSidebarStub = {
  inheritAttrs: false,
  template: '<aside class="agent-sidebar" v-bind="$attrs"><button type="button">会话项</button></aside>'
}

function mountAgentDashboard() {
  window.api = {
    getRecommendedConcurrentLimits: vi.fn().mockResolvedValue({}),
    getCacheStats: vi.fn().mockResolvedValue({}),
    getLearningStats: vi.fn().mockResolvedValue({}),
    listSkills: vi.fn().mockResolvedValue([]),
    listAgentHostSessions: vi.fn().mockResolvedValue([]),
    get: vi.fn().mockResolvedValue({ ok: true, json: async () => ({ providers: [] }) }),
    reclaimProject: vi.fn().mockResolvedValue({ session_id: 'project-1', status: 'deleted' })
  }

  return shallowMount(AgentDashboard, {
    attachTo: document.body,
    global: {
      plugins: [createPinia()],
      stubs: {
        AgentSidebar: AgentSidebarStub,
        AgentFilePanel: { template: '<aside class="agent-file-panel" />' },
        AgentTopBar: { template: '<header class="agent-topbar" />' },
        AgentWorkspace: { template: '<section class="agent-workspace" />' },
        AgentInputBar: { template: '<div class="agent-input-bar"><textarea class="prompt-textarea" /></div>' },
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

describe('Agent Dashboard 响应式工作区', () => {
  beforeEach(() => {
    localStorage.clear()
    setActivePinia(createPinia())
  })

  afterEach(() => {
    wrapper?.unmount()
    wrapper = null
  })

  it('保留桌面三栏结构和移动端工具栏', () => {
    wrapper = mountAgentDashboard()

    expect(wrapper.find('.agent-sidebar').exists()).toBe(true)
    expect(wrapper.find('.agent-center').exists()).toBe(true)
    expect(wrapper.find('.agent-file-panel').exists()).toBe(true)
    expect(wrapper.findAll('.mobile-toolbar-btn')).toHaveLength(2)
  })

  it('关闭会话抽屉后恢复触发按钮焦点', async () => {
    wrapper = mountAgentDashboard()
    const trigger = wrapper.get('[aria-label="打开会话列表"]')

    await trigger.trigger('click')
    expect(wrapper.get('.agent-sidebar').classes()).toContain('mobile-drawer-open')
    expect(wrapper.get('.agent-sidebar').attributes('role')).toBe('dialog')
    expect(wrapper.get('.agent-sidebar').attributes('aria-modal')).toBe('true')

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await wrapper.vm.$nextTick()
    expect(wrapper.find('.agent-mobile-scrim').exists()).toBe(false)
    expect(document.activeElement).toBe(trigger.element)
  })
})
