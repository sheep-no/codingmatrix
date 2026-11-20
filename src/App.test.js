// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const showError = vi.fn()

vi.mock('@/utils/theme', () => ({ initTheme: vi.fn() }))
vi.mock('@/composables/useToast', () => ({ useToast: () => ({ error: showError }) }))

vi.mock('@/components/ErrorBoundary.vue', () => ({
  default: { name: 'ErrorBoundary', template: '<div><slot /></div>' }
}))

vi.mock('@/components/AppLoading.vue', () => ({
  default: {
    name: 'AppLoading',
    props: ['visible', 'status', 'error'],
    methods: { reset: vi.fn(), startProgress: vi.fn(), complete: vi.fn() },
    template: '<div v-if="visible" class="app-loading-overlay"></div>'
  }
}))

import App from './App.vue'

function mountApp() {
  return mount(App, {
    global: {
      stubs: {
        RouterView: { template: '<div class="router-view" />' }
      }
    }
  })
}

describe('App 首屏初始化', () => {
  beforeEach(() => {
    showError.mockReset()
  })

  afterEach(() => {
    vi.useRealTimers()
    delete window.__appInitialization
    delete window.__retryAppInitialization
  })

  it('初始化失败后卸载全屏遮罩，避免吞掉页面点击', async () => {
    window.__appInitialization = Promise.reject(new Error('初始化失败'))

    const wrapper = mountApp()
    await flushPromises()

    expect(wrapper.find('.app-loading-overlay').exists()).toBe(false)
    expect(showError).toHaveBeenCalledWith('初始化失败')
    wrapper.unmount()
  })

  it('初始化挂起时按超时结束遮罩', async () => {
    vi.useFakeTimers()
    window.__appInitialization = new Promise(() => {})

    const wrapper = mountApp()
    await vi.advanceTimersByTimeAsync(11000)

    expect(wrapper.find('.app-loading-overlay').exists()).toBe(false)
    expect(showError).toHaveBeenCalledWith('应用初始化超时，请重试')
    wrapper.unmount()
  })

  it('重试时重新执行初始化并恢复遮罩状态', async () => {
    window.__appInitialization = Promise.reject(new Error('初始化失败'))
    const retry = vi.fn().mockResolvedValue(undefined)
    window.__retryAppInitialization = retry

    const wrapper = mountApp()
    await flushPromises()
    expect(showError).toHaveBeenCalledWith('初始化失败')

    await wrapper.findComponent({ name: 'AppLoading' }).vm.$emit('retry')
    await flushPromises()

    expect(retry).toHaveBeenCalledTimes(1)
    expect(wrapper.find('.app-loading-overlay').exists()).toBe(false)
    wrapper.unmount()
  })
})
