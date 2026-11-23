import { mount, shallowMount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import CenterContent from './centerContent.vue'
import MessageList from './chat/MessageList.vue'

vi.mock('@/utils/api/index', () => ({ api: {} }))

describe('chat resize scrolling', () => {
  let wrapper
  let container
  let height
  let top
  let writes

  beforeEach(async () => {
    vi.useFakeTimers()
    vi.stubGlobal('indexedDB', { open: () => ({}) })
    vi.stubGlobal('requestAnimationFrame', vi.fn(() => 1))
    vi.stubGlobal('cancelAnimationFrame', vi.fn())
    wrapper = shallowMount(CenterContent, {
      props: {
        conversationId: 'temp_a',
        hasMoreHistory: false,
        conversationHistory: Array.from({ length: 80 }, (_, id) => ({ id, prompt: 'hello' }))
      }
    })
    container = wrapper.get('.messages-container').element
    height = 18000
    top = height - 500
    writes = []
    Object.defineProperties(container, {
      clientHeight: { configurable: true, get: () => 500 },
      scrollHeight: { configurable: true, get: () => height },
      scrollTop: {
        configurable: true,
        get: () => top,
        set: value => { writes.push(value); top = Math.min(value, height - 500) }
      }
    })
    await nextTick()
  })

  afterEach(() => {
    wrapper.unmount()
    vi.clearAllTimers()
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  const resize = (key = 0, height = 600) => {
    wrapper.findComponent(MessageList).vm.$emit('item-resize', { key, height })
  }

  it('follows the growing bottom after a message is measured', async () => {
    height += 400
    resize()
    await nextTick()
    expect(top).toBe(height - 500)
    expect(writes).toContain(height)
  })

  it('preserves measured heights across loaded transitions and resets on conversation change', async () => {
    top = 0
    container.dispatchEvent(new Event('scroll'))
    resize()
    await nextTick()
    await nextTick()
    const spacers = () => wrapper.findAll('.virtual-spacer').map(node => node.attributes('style'))
    const measured = spacers()
    expect(measured).toEqual(['height: 0px;', 'height: 16576px;'])
    await wrapper.setProps({ historyItem: { conversation_id: 'temp_a' } })
    await vi.advanceTimersByTimeAsync(100)
    expect(spacers()).toEqual(measured)
    await wrapper.setProps({ historyItem: { conversation_id: 'temp_a', title: 'updated' } })
    await vi.advanceTimersByTimeAsync(100)
    expect(spacers()).toEqual(measured)
    await wrapper.setProps({ conversationId: 'temp_b' })
    expect(spacers()).not.toEqual(measured)
  })

  it('cancels a pending bottom adjustment when the conversation changes', async () => {
    resize()
    await wrapper.setProps({ conversationId: 'temp_b' })
    await nextTick()
    expect(writes).toEqual([])
  })

  it('updates the conversation title when a newer message arrives', async () => {
    await wrapper.setProps({ historyItem: { conversation_id: 'temp_a', title: '旧标题' } })
    expect(wrapper.get('#conversation-title').text()).toBe('hello')

    await wrapper.setProps({
      conversationHistory: [
        ...wrapper.props('conversationHistory'),
        { id: 999, prompt: '最新一轮提问', title: '最新一轮提问' }
      ]
    })

    expect(wrapper.get('#conversation-title').text()).toBe('最新一轮提问')
  })

  it('opens the header menu and keeps it open on a repeated click', async () => {
    const trigger = wrapper.get('.header-menu-btn')
    expect(trigger.attributes('aria-expanded')).toBe('false')
    expect(wrapper.find('.header-menu-list').exists()).toBe(false)

    await trigger.trigger('click')
    expect(trigger.attributes('aria-expanded')).toBe('true')
    expect(wrapper.find('.header-menu-list').exists()).toBe(true)

    await trigger.trigger('click')
    expect(trigger.attributes('aria-expanded')).toBe('true')
    expect(wrapper.find('.header-menu-list').exists()).toBe(true)

    document.body.dispatchEvent(new Event('pointerdown', { bubbles: true }))
    await nextTick()
    expect(trigger.attributes('aria-expanded')).toBe('false')
    expect(wrapper.find('.header-menu-list').exists()).toBe(false)
  })

  it('respects an upward scroll before the animation frame runs', async () => {
    resize()
    top -= 300
    container.dispatchEvent(new Event('scroll'))
    await nextTick()
    expect(writes).toEqual([])
    await vi.advanceTimersByTimeAsync(2100)
    resize(1)
    await nextTick()
    expect(writes).toEqual([])
  })

  it('respects a changed scroll position even before the scroll event arrives', async () => {
    resize()
    top -= 300
    await nextTick()
    expect(writes).toEqual([])
  })

  it('resumes following when the user returns to the bottom', async () => {
    top -= 300
    container.dispatchEvent(new Event('scroll'))
    top = height - 500
    container.dispatchEvent(new Event('scroll'))
    height += 400
    resize()
    await nextTick()
    expect(top).toBe(height - 500)
  })
})

describe('chat source rendering', () => {
  it('renders file sources as text and web sources as links', async () => {
    const wrapper = mount(CenterContent, {
      props: { conversationId: '1', conversationHistory: [{ id: 1, prompt: 'q', response: 'a', sources: [
        { kind: 'file', title: 'notes.txt' },
        { kind: 'web', title: 'Docs', url: 'https://example.com', snippet: 'reference' }
      ] }] },
      global: { stubs: { MessageList: { template: '<div><slot :message="messages[0]" /></div>', props: ['messages'] } } }
    })
    expect(wrapper.findAll('.chat-sources span').map(node => node.text())).toContain('notes.txt')
    expect(wrapper.findAll('.chat-sources span').some(node => node.element.tagName === 'SPAN')).toBe(true)
    expect(wrapper.get('.chat-sources a').attributes('href')).toBe('https://example.com')
    expect(wrapper.text()).toContain('reference')
    wrapper.unmount()
  })

  it('places user and assistant turns in distinct conversation columns', async () => {
    const wrapper = mount(CenterContent, {
      props: {
        conversationId: 'layout',
        conversationHistory: [{
          id: 2,
          prompt: '解释闭包',
          response: '闭包会记住外层作用域。',
          model: 'demo-model',
          usage: { total_tokens: 42 }
        }]
      },
      global: { stubs: { MessageList: { template: '<div><slot :message="messages[0]" /></div>', props: ['messages'] } } }
    })
    expect(wrapper.get('.message-user').classes()).toContain('message-user')
    expect(wrapper.get('.message-ai .sender-ai').text()).toBe('CodingMatrix')
    expect(wrapper.get('.user-text').text()).toContain('解释闭包')
    expect(wrapper.get('.message-meta').text()).toContain('demo-model')
    expect(wrapper.get('.message-meta').text()).toContain('42 Token/令牌')
    wrapper.unmount()
  })

  it('renders a failed turn once in the error card with a retry button', async () => {
    const wrapper = mount(CenterContent, {
      props: {
        conversationId: 'error',
        conversationHistory: [{
          id: 3,
          prompt: '解释这段代码',
          response: '',
          requestError: { message: '检测到疑似 XSS 攻击内容，请移除脚本标签后重试', action: '重试' },
          retryRequest: { prompt: '解释这段代码' }
        }]
      },
      global: { stubs: { MessageList: { template: '<div><slot :message="messages[0]" /></div>', props: ['messages'] } } }
    })

    const alert = wrapper.get('.response-error-actions')
    expect(alert.text()).toContain('检测到疑似 XSS 攻击内容')
    expect(alert.text()).not.toContain('HTTP error! status')
    expect(wrapper.findAll('.response-error-actions')).toHaveLength(1)
    expect(wrapper.get('.response-retry-btn').text()).toBe('重试')
    wrapper.unmount()
  })

  it('marks an answer as unverified when search returned no sources', async () => {
    const wrapper = mount(CenterContent, {
      props: {
        conversationId: 'unverified',
        conversationHistory: [{
          id: 4,
          prompt: '人工智能最近的进展有哪些？',
          response: '人工智能最近在推理能力上有进展。',
          sources: [],
          searchUnavailable: true
        }]
      },
      global: { stubs: { MessageList: { template: '<div><slot :message="messages[0]" /></div>', props: ['messages'] } } }
    })

    const notice = wrapper.get('.response-notice')
    expect(notice.text()).toContain('未能联网核实')
    expect(notice.attributes('role')).toBe('note')
    expect(wrapper.text()).toContain('人工智能最近在推理能力上有进展。')
    wrapper.unmount()
  })

  it('does not show the unverified notice when search returned sources', async () => {
    const wrapper = mount(CenterContent, {
      props: {
        conversationId: 'verified',
        conversationHistory: [{
          id: 5,
          prompt: '诺奖得主',
          response: '答案。',
          sources: [{ kind: 'web', title: '来源', url: 'https://example.com' }],
          searchUnavailable: false
        }]
      },
      global: { stubs: { MessageList: { template: '<div><slot :message="messages[0]" /></div>', props: ['messages'] } } }
    })

    expect(wrapper.find('.response-notice').exists()).toBe(false)
    wrapper.unmount()
  })

  it('suppresses the duplicated search warning once the unverified notice is shown', async () => {
    const wrapper = mount(CenterContent, {
      props: {
        conversationId: 'dedupe',
        conversationHistory: [{
          id: 6,
          prompt: '今天是几号？',
          response: '今天是 11 月 23 日。',
          sources: [],
          searchUnavailable: true,
          warnings: ['第 2 轮搜索未获得有效结果，将使用已有资料回答。']
        }]
      },
      global: { stubs: { MessageList: { template: '<div><slot :message="messages[0]" /></div>', props: ['messages'] } } }
    })

    expect(wrapper.get('.response-notice').text()).toContain('未能联网核实')
    expect(wrapper.find('.chat-warnings').exists()).toBe(false)
    wrapper.unmount()
  })
})

describe('code block copy', () => {
  const CODE_RESPONSE = '示例：\n\n```js\nconst answer = 42\n```\n'
  let execCommand

  beforeEach(() => {
    // jsdom 未实现 execCommand，按需注入以便观察降级路径
    execCommand = vi.fn()
    Object.defineProperty(document, 'execCommand', {
      configurable: true,
      writable: true,
      value: execCommand,
    })
  })

  const mountWithCode = () => mount(CenterContent, {
    props: {
      conversationId: 'copy',
      conversationHistory: [{ id: 1, prompt: '给一段代码', response: CODE_RESPONSE }]
    },
    global: { stubs: { MessageList: { template: '<div><slot :message="messages[0]" /></div>', props: ['messages'] } } }
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
    delete navigator.clipboard
    delete document.execCommand
  })

  it('falls back to execCommand when the Clipboard API rejects', async () => {
    vi.stubGlobal('isSecureContext', true)
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText: vi.fn().mockRejectedValue(new Error('NotAllowedError')) },
    })
    execCommand.mockReturnValue(true)

    const wrapper = mountWithCode()
    await nextTick()
    await nextTick()

    const button = wrapper.get('.copy-button')
    await button.trigger('click')
    await new Promise(resolve => setTimeout(resolve, 0))

    expect(execCommand).toHaveBeenCalledWith('copy')
    expect(button.text()).toContain('已复制')
    expect(document.querySelector('textarea')).toBeNull()
    wrapper.unmount()
  })

  it('reports failure when both clipboard paths are rejected', async () => {
    vi.stubGlobal('isSecureContext', false)
    execCommand.mockReturnValue(false)

    const wrapper = mountWithCode()
    await nextTick()
    await nextTick()

    const button = wrapper.get('.copy-button')
    await button.trigger('click')
    await new Promise(resolve => setTimeout(resolve, 0))

    expect(execCommand).toHaveBeenCalledWith('copy')
    expect(button.text()).toContain('复制失败')
    expect(document.querySelector('textarea')).toBeNull()
    wrapper.unmount()
  })
})
