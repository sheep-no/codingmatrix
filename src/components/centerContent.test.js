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
})
