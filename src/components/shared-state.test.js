import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import AppLoading from './AppLoading.vue'
import ErrorState from './ErrorState.vue'
import LoadingState from './LoadingState.vue'
import TaskStatus from './TaskStatus.vue'
import TaskFeedbackPanel from './TaskFeedbackPanel.vue'

describe('shared workbench state components', () => {
  it('renders loading and task status contracts', () => {
    const loading = mount(LoadingState, { props: { label: '加载会话' } })
    const task = mount(TaskStatus, { props: { status: 'running', stage: '生成文件', progress: 42 } })

    expect(loading.text()).toContain('加载会话')
    expect(loading.attributes('role')).toBe('status')
    expect(task.text()).toContain('运行中')
    expect(task.text()).toContain('生成文件')
    expect(task.text()).toContain('42%')
  })

  it('emits retry from an error state', async () => {
    const wrapper = mount(ErrorState, { props: { message: '网络错误' } })

    await wrapper.get('button').trigger('click')

    expect(wrapper.emitted('retry')).toHaveLength(1)
    expect(wrapper.text()).toContain('网络错误')
  })

  it('renders task elapsed time, connection state, error and next action', () => {
    const wrapper = mount(TaskFeedbackPanel, {
      props: {
        feedback: {
          status: 'paused',
          stage: '渲染页面',
          progress: 60,
          elapsedMs: 65000,
          error: '连接中断，内容已保留',
          nextAction: '恢复连接后继续接收进度'
        },
        connectionStatus: 'reconnecting'
      }
    })

    expect(wrapper.text()).toContain('已暂停')
    expect(wrapper.text()).toContain('渲染页面')
    expect(wrapper.text()).toContain('60%')
    expect(wrapper.text()).toContain('耗时 1:05')
    expect(wrapper.text()).toContain('正在恢复连接')
    expect(wrapper.text()).toContain('连接中断，内容已保留')
    expect(wrapper.text()).toContain('恢复连接后继续接收进度')
  })

  it('emits configured task actions', async () => {
    const wrapper = mount(TaskFeedbackPanel, {
      props: {
        feedback: { status: 'failed', stage: '生成失败', elapsedMs: 0, nextAction: '重新尝试' },
        actions: [{ key: 'retry', label: '重试', variant: 'primary' }]
      }
    })

    await wrapper.get('button').trigger('click')
    expect(wrapper.emitted('action')).toEqual([['retry']])
  })

  it('emits primary and secondary actions in their configured order', async () => {
    const wrapper = mount(TaskFeedbackPanel, {
      props: {
        feedback: { status: 'completed', stage: '生成完成', elapsedMs: 1000, nextAction: '预览或下载' },
        actions: [
          { key: 'preview', label: '在线预览', variant: 'primary' },
          { key: 'download', label: '下载文件' }
        ]
      }
    })

    const buttons = wrapper.findAll('button')
    expect(buttons.map(button => button.text())).toEqual(['在线预览', '下载文件'])
    await buttons[0].trigger('click')
    await buttons[1].trigger('click')
    expect(wrapper.emitted('action')).toEqual([['preview'], ['download']])
  })

  it('incrementally rerenders feedback while preserving unchanged context', async () => {
    const feedback = {
      status: 'running',
      stage: '分析需求',
      progress: 20,
      elapsedMs: 1000,
      error: null,
      nextAction: null
    }
    const wrapper = mount(TaskFeedbackPanel, { props: { feedback } })

    await wrapper.setProps({ feedback: { ...feedback, progress: 65, elapsedMs: 3000 } })

    expect(wrapper.text()).toContain('运行中')
    expect(wrapper.text()).toContain('分析需求')
    expect(wrapper.text()).toContain('65%')
    expect(wrapper.text()).toContain('耗时 0:03')
  })

  it('renders feedback safely when no actions are available', () => {
    const wrapper = mount(TaskFeedbackPanel, {
      props: {
        feedback: { status: 'paused', stage: '等待恢复', elapsedMs: 0, nextAction: '恢复连接后继续' },
        actions: [{ key: '', label: '无效操作' }, null]
      }
    })

    expect(wrapper.text()).toContain('恢复连接后继续')
    expect(wrapper.find('button').exists()).toBe(false)
  })

  it('cleans loading timers on unmount and emits retry', async () => {
    vi.useFakeTimers()
    const retry = vi.fn()
    const wrapper = mount(AppLoading, { props: { visible: true, onRetry: retry } })

    await wrapper.setProps({ status: 'error', error: '初始化失败' })
    await document.body.querySelector('.app-loading-error button').click()
    wrapper.unmount()
    vi.advanceTimersByTime(2000)

    expect(retry).toHaveBeenCalledOnce()
    vi.useRealTimers()
  })

  it('advances the startup progress and completes when ready', async () => {
    vi.useFakeTimers()
    const wrapper = mount(AppLoading, { props: { visible: true } })

    await vi.advanceTimersByTimeAsync(300)
    expect(wrapper.vm.progress).toBeGreaterThan(0)
    expect(wrapper.vm.progress).toBeLessThanOrEqual(90)

    await wrapper.setProps({ status: 'ready' })
    expect(wrapper.vm.progress).toBe(100)

    wrapper.unmount()
    vi.useRealTimers()
  })

  it('restarts startup progress when visibility returns', async () => {
    vi.useFakeTimers()
    const wrapper = mount(AppLoading, { props: { visible: true } })

    await vi.advanceTimersByTimeAsync(300)
    await wrapper.setProps({ visible: false })
    expect(wrapper.vm.progress).toBe(100)

    await wrapper.setProps({ visible: true })
    expect(wrapper.vm.progress).toBe(0)

    wrapper.unmount()
    vi.useRealTimers()
  })

  it('loading overlay lets clicks pass through while initialization runs', () => {
    const wrapper = mount(AppLoading, { props: { visible: true, status: 'loading' } })

    const overlay = document.body.querySelector('.app-loading-overlay')
    expect(overlay).not.toBeNull()
    expect(overlay.classList.contains('is-loading')).toBe(true)
    expect(getComputedStyle(overlay).pointerEvents).toBe('none')

    wrapper.unmount()
  })

  it('fading overlay still lets clicks pass through after init completes', async () => {
    const wrapper = mount(AppLoading, { props: { visible: true, status: 'loading' } })

    // 初始化完成后遮罩进入 0.4s 淡出：is-loading 被移除，但节点仍然覆盖全屏。
    // 此时若恢复指针事件，pointerup 会落在遮罩上，整个 click 被浏览器丢弃。
    await wrapper.setProps({ status: 'ready' })
    const overlay = document.body.querySelector('.app-loading-overlay')
    expect(overlay).not.toBeNull()
    expect(overlay.classList.contains('is-loading')).toBe(false)
    expect(getComputedStyle(overlay).pointerEvents).toBe('none')

    wrapper.unmount()
  })

  it('error overlay keeps retry button interactive', async () => {
    const wrapper = mount(AppLoading, { props: { visible: true, status: 'error', error: '初始化失败' } })

    const overlay = document.body.querySelector('.app-loading-overlay')
    expect(getComputedStyle(overlay).pointerEvents).toBe('none')
    expect(document.body.querySelector('.app-loading-error').style.pointerEvents).toBe('auto')

    wrapper.unmount()
  })

  it('removes a fading overlay even when transitionend never fires', async () => {
    vi.useFakeTimers()
    const wrapper = mount(AppLoading, { props: { visible: true } })

    // 模拟后台标签：CSS 过渡已启动，但渲染帧被暂停，transitionend 永远不会派发。
    await wrapper.setProps({ visible: false })
    expect(document.body.querySelector('.app-loading-overlay').classList.contains('is-leaving')).toBe(true)

    await vi.advanceTimersByTimeAsync(800)
    expect(document.body.querySelector('.app-loading-overlay')).toBeNull()

    wrapper.unmount()
    vi.useRealTimers()
  })

  it('removes the overlay as soon as the fade transition ends', async () => {
    vi.useFakeTimers()
    const wrapper = mount(AppLoading, { props: { visible: true } })

    await wrapper.setProps({ visible: false })
    const overlay = document.body.querySelector('.app-loading-overlay')
    const transitionEnd = new Event('transitionend')
    Object.defineProperty(transitionEnd, 'propertyName', { value: 'opacity' })
    overlay.dispatchEvent(transitionEnd)
    await wrapper.vm.$nextTick()

    expect(document.body.querySelector('.app-loading-overlay')).toBeNull()

    wrapper.unmount()
    vi.useRealTimers()
  })
})
