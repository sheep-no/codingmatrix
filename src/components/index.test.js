import { createPinia, setActivePinia } from 'pinia'
import { shallowMount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/composables/useKeyboardShortcuts', () => ({
  useKeyboardShortcuts: () => ({ register: () => () => {} })
}))
vi.mock('@/composables/useOfflineQueue', () => ({
  useOfflineQueue: () => ({ addToQueue: vi.fn() })
}))
vi.mock('@/utils/api/index', () => ({ api: { post: vi.fn(), stream: vi.fn() } }))

import HomeWorkspace from './index.vue'
import Bottominput from './bottominput.vue'
import { api } from '@/utils/api/index'

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
    vi.restoreAllMocks()
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

  it('保留搜索失败提示并显示随后回答的真实模型', async () => {
    wrapper = mountHomeWorkspace()
    const state = wrapper.vm.$.setupState
    state.currentConversationId = '1'
    state.conversationHistory = [{ prompt: 'q' }]
    state.conversationHistoryMap.set('1', [{ prompt: 'q' }])
    state.handleChatStream({ stage: 'searching', status: 'started' }, '1', 0, {})
    expect(state.conversationHistory[0].chatStage).toBe('正在搜索资料')
    state.handleChatStream({ stage: 'searching', status: 'failed', error: '搜索暂不可用' }, '1', 0, {})
    expect(state.conversationHistory[0].chatStage).toBe('')
    state.handleChatStream({ stage: 'answering', status: 'started', model: 'reasoning-model', sources: [] }, '1', 0, {})
    expect(state.conversationHistory[0].warnings).toEqual(['搜索暂不可用'])
    expect(state.conversationHistory[0].model).toBe('reasoning-model')
  })

  it.each([undefined, 'chosen-model'])('传递联网模式并保持自动或显式选模：%s', async model => {
    wrapper = mountHomeWorkspace()
    const state = wrapper.vm.$.setupState
    vi.spyOn(state.userStore, 'isLoggedIn', 'get').mockReturnValue(true)
    vi.spyOn(state.apiKeyStore, 'hasSiliconflowKey', 'get').mockReturnValue(true)
    api.stream.mockResolvedValue({ ok: true, body: new ReadableStream({ start(controller) { controller.close() } }) })
    await state.handleSendMessage({ prompt: 'q', model, search_mode: 'on', search_depth: 'multi', use_reasoning: true })
    const [url, request] = api.stream.mock.calls.at(-1)
    expect(url).toBe('/chat')
    expect(request.search_mode).toBe('on')
    expect(request.search_depth).toBe('multi')
    expect(request.use_reasoning).toBe(true)
    expect(request.model).toBe(model)
    expect(state.conversationHistory[0].chatStage).toBe('')
  })

  it('默认浅搜索，可切换多轮，关闭联网时禁用深度选择', async () => {
    wrapper = shallowMount(Bottominput, { global: {
      plugins: [createPinia()],
      stubs: { FileDropZone: { template: '<div />', methods: { setupDropZone() {}, cleanupDropZone() {} } } }
    } })
    expect(wrapper.find('select[aria-label="搜索深度"]').exists()).toBe(false)
    await wrapper.get('.config-toggle').trigger('click')
    const depth = wrapper.get('select[aria-label="搜索深度"]')
    expect(depth.element.value).toBe('shallow')
    await depth.setValue('multi')
    expect(wrapper.vm.$.setupState.searchDepth).toBe('multi')
    await wrapper.get('select[aria-label="联网模式"]').setValue('off')
    expect(depth.element.disabled).toBe(true)
  })

  it('显示第二轮进度，并保留提前结束的说明', () => {
    wrapper = mountHomeWorkspace()
    const state = wrapper.vm.$.setupState
    state.currentConversationId = '1'
    state.conversationHistory = [{}]
    state.conversationHistoryMap.set('1', [{}])
    state.handleChatStream({ stage: 'searching', status: 'started', round: 2, total_rounds: 2 }, '1', 0, {})
    expect(state.conversationHistory[0].chatStage).toContain('第 2/2 轮')
    state.handleChatStream({ stage: 'searching', status: 'skipped', error: '缺少新文本' }, '1', 0, {})
    expect(state.conversationHistory[0].warnings).toEqual(['缺少新文本'])
  })

  it('从历史接口恢复来源和失败提示', async () => {
    wrapper = mountHomeWorkspace()
    const state = wrapper.vm.$.setupState
    vi.spyOn(api, 'post').mockResolvedValue({ ok: true, json: async () => ({ items: [{
      id: 1, conversation_id: 21, prompt: 'q', response: 'a', metadata: {
         sources: [{ kind: 'file', title: 'report.txt' }],
         warnings: [{ stage: 'searching', error: '搜索失败' }], model: 'model-a', search_depth: 'multi',
         usage: { prompt_tokens: 10, completion_tokens: 4, total_tokens: 14 },
         tool_calls: [{ id: 'call-1', name: 'search', arguments: '{"q":"test"}' }]
      }
    }] }) })
    await state.handleSelectHistory({ conversation_id: 21 })
    expect(state.conversationHistory[0].sources[0].title).toBe('report.txt')
    expect(state.conversationHistory[0].warnings).toEqual(['搜索失败'])
    expect(state.conversationHistory[0].model).toBe('model-a')
    expect(state.conversationHistory[0].searchDepth).toBe('multi')
    expect(state.conversationHistory[0].usage.total_tokens).toBe(14)
    expect(state.conversationHistory[0].toolCalls[0].name).toBe('search')
  })

  it('规范化分页历史并同步会话缓存', async () => {
    wrapper = mountHomeWorkspace()
    const state = wrapper.vm.$.setupState
    state.currentConversationId = 21
    state.conversationHistory = [{ id: 2, prompt: 'newer', response: 'new' }]
    state.conversationHistoryMap.set('21', state.conversationHistory)

    state.handlePrependHistory([{
      id: 1,
      conversation_id: 21,
      prompt: 'older',
      response: 'old',
      thinking: 'reasoning',
      metadata: { usage: { total_tokens: 3 }, tool_calls: [{ name: 'lookup' }] }
    }])

    expect(state.conversationHistory[0].reasoning).toBe('reasoning')
    expect(state.conversationHistory[0].usage.total_tokens).toBe(3)
    expect(state.conversationHistoryMap.get('21')[0].toolCalls[0].name).toBe('lookup')
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
