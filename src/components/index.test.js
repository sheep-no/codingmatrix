import { createPinia, setActivePinia } from 'pinia'
import { shallowMount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/composables/useKeyboardShortcuts', () => ({
  useKeyboardShortcuts: () => ({ register: () => () => {} })
}))
vi.mock('@/composables/useOfflineQueue', () => ({
  useOfflineQueue: () => ({ addToQueue: vi.fn() })
}))

import HomeWorkspace from './index.vue'

let wrapper

const LeftlistStub = {
  inheritAttrs: false,
  template: '<aside id="leftlist" v-bind="$attrs"><button type="button">新建会话</button></aside>'
}

function mountHomeWorkspace() {
  return shallowMount(HomeWorkspace, {
    attachTo: document.body,
    global: {
      plugins: [createPinia()],
      stubs: {
        ErrorBoundary: { template: '<div><slot /></div>' },
        Leftlist: LeftlistStub,
        ToastContainer: true
      },
      mocks: { $router: { push: vi.fn() } }
    }
  })
}

describe('首页工作台响应式导航', () => {
  beforeEach(() => {
    localStorage.clear()
    setActivePinia(createPinia())
  })

  afterEach(() => {
    wrapper?.unmount()
    wrapper = null
  })

  it('提供主工作区、输入区和移动导航入口', () => {
    wrapper = mountHomeWorkspace()

    expect(wrapper.get('.main-content').attributes('role')).toBe('main')
    expect(wrapper.get('.bottom-wrapper').attributes('aria-label')).toBe('消息输入区')
    expect(wrapper.get('.mobile-home-menu').attributes('aria-label')).toBe('打开主导航')
    expect(wrapper.get('#leftlist').classes()).not.toContain('mobile-home-drawer-open')
    expect(wrapper.findComponent({ name: 'MessageEditor' }).exists()).toBe(false)
    expect(wrapper.findComponent({ name: 'KeyboardShortcutsHelp' }).exists()).toBe(false)
  })

  it('通过遮罩和 Escape 关闭抽屉并恢复触发按钮焦点', async () => {
    wrapper = mountHomeWorkspace()
    const trigger = wrapper.get('.mobile-home-menu')

    await trigger.trigger('click')
    expect(wrapper.get('#leftlist').classes()).toContain('mobile-home-drawer-open')
    expect(wrapper.get('#leftlist').attributes('role')).toBe('dialog')
    expect(wrapper.get('#leftlist').attributes('aria-modal')).toBe('true')

    await wrapper.get('.mobile-home-scrim').trigger('click')
    expect(wrapper.find('.mobile-home-scrim').exists()).toBe(false)
    expect(document.activeElement).toBe(trigger.element)

    await trigger.trigger('click')
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await wrapper.vm.$nextTick()
    expect(wrapper.find('.mobile-home-scrim').exists()).toBe(false)
    expect(document.activeElement).toBe(trigger.element)
  })
})
