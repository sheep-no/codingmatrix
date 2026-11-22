import { mount } from '@vue/test-utils'
import { afterEach, describe, expect, it } from 'vitest'
import AgentInputBar from './AgentInputBar.vue'

let wrapper

function mountBar(props = {}) {
  return mount(AgentInputBar, {
    attachTo: document.body,
    props: {
      prompt: '写一个登录页',
      generating: true,
      ...props
    }
  })
}

afterEach(() => {
  wrapper?.unmount()
  wrapper = null
  document.body.innerHTML = ''
})

describe('AgentInputBar Esc 停止', () => {
  it('生成中焦点不在输入框时，按 Esc 触发 stop', async () => {
    wrapper = mountBar()
    document.body.focus()
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await wrapper.vm.$nextTick()
    expect(wrapper.emitted('stop')).toHaveLength(1)
  })

  it('未生成时按 Esc 不触发 stop', async () => {
    wrapper = mountBar({ generating: false })
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await wrapper.vm.$nextTick()
    expect(wrapper.emitted('stop')).toBeUndefined()
  })

  it('输入框内按 Esc 由 textarea 自身处理，窗口监听不重复触发', async () => {
    wrapper = mountBar()
    const textarea = wrapper.get('textarea')
    await textarea.trigger('keydown', { key: 'Escape' })
    expect(wrapper.emitted('stop')).toHaveLength(1)
  })

  it('卸载后移除窗口监听', () => {
    wrapper = mountBar()
    const bar = wrapper
    bar.unmount()
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    expect(bar.emitted('stop')).toBeUndefined()
    wrapper = null
  })
})
