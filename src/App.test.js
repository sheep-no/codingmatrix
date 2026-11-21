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
    sessionStorage.clear()
  })

  afterEach(() => {
    vi.useRealTimers()
    sessionStorage.clear()
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
    expect(wrapper.find('.app-loading-overlay').exists()).toBe(true)
    await vi.advanceTimersByTimeAsync(11000)

    expect(wrapper.find('.app-loading-overlay').exists()).toBe(false)
    expect(showError).toHaveBeenCalledWith('应用初始化超时，请重试')
    wrapper.unmount()
  })

  it('初始化期间用户首次点击立即撤下遮罩，初始化继续后台完成', async () => {
    vi.useFakeTimers()
    let resolveInitialization
    window.__appInitialization = new Promise(resolve => {
      resolveInitialization = resolve
    })

    const wrapper = mountApp()
    expect(wrapper.find('.app-loading-overlay').exists()).toBe(true)

    window.dispatchEvent(new Event('pointerdown'))
    await flushPromises()
    expect(wrapper.find('.app-loading-overlay').exists()).toBe(false)

    resolveInitialization()
    await flushPromises()
    expect(showError).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('初始化期间键盘操作同样撤下遮罩', async () => {
    window.__appInitialization = new Promise(() => {})

    const wrapper = mountApp()
    expect(wrapper.find('.app-loading-overlay').exists()).toBe(true)

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter' }))
    await flushPromises()
    expect(wrapper.find('.app-loading-overlay').exists()).toBe(false)
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

  it('同一标签页已初始化过时不再展示遮罩，但仍会后台恢复会话', async () => {
    sessionStorage.setItem('app-initialized', '1')
    const initialization = vi.fn().mockResolvedValue(undefined)
    window.__appInitialization = initialization()

    const wrapper = mountApp()
    expect(wrapper.find('.app-loading-overlay').exists()).toBe(false)

    await flushPromises()
    expect(initialization).toHaveBeenCalledTimes(1)
    expect(showError).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('初始化成功后写入会话标志，后续挂载不再重复展示遮罩', async () => {
    window.__appInitialization = Promise.resolve()

    const first = mountApp()
    await flushPromises()
    expect(sessionStorage.getItem('app-initialized')).toBe('1')
    first.unmount()

    const second = mountApp()
    expect(second.find('.app-loading-overlay').exists()).toBe(false)
    second.unmount()
  })

  it('遮罩展示超过上限后自动撤下，初始化挂起也不阻塞交互', async () => {
    vi.useFakeTimers()
    window.__appInitialization = new Promise(() => {})

    const wrapper = mountApp()
    expect(wrapper.find('.app-loading-overlay').exists()).toBe(true)

    await vi.advanceTimersByTimeAsync(3100)
    expect(wrapper.find('.app-loading-overlay').exists()).toBe(false)
    wrapper.unmount()
  })

  it('重试后旧请求的失败结果不会覆盖新请求', async () => {
    let rejectFirst
    window.__appInitialization = new Promise((_, reject) => {
      rejectFirst = reject
    })
    window.__retryAppInitialization = vi.fn().mockResolvedValue(undefined)

    const wrapper = mountApp()
    await wrapper.findComponent({ name: 'AppLoading' }).vm.$emit('retry')
    await flushPromises()

    rejectFirst(new Error('旧请求失败'))
    await flushPromises()

    expect(showError).not.toHaveBeenCalled()
    wrapper.unmount()
  })
})
