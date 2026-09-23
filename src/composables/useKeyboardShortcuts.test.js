// @vitest-environment jsdom
import { defineComponent, h } from 'vue'
import { mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useKeyboardShortcuts } from './useKeyboardShortcuts'

let shortcuts = null
let wrapper = null

const Host = defineComponent({
  setup() {
    shortcuts = useKeyboardShortcuts()
    return () => h('div')
  }
})

function press(key, options = {}) {
  // 真实场景中事件目标始终是聚焦元素，从 body 冒泡到 window 上的监听器
  document.body.dispatchEvent(
    new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true, ...options })
  )
}

describe('useKeyboardShortcuts', () => {
  beforeEach(() => {
    wrapper = mount(Host)
  })

  afterEach(() => {
    wrapper.unmount()
    shortcuts = null
  })

  it('Shift+/ 产生的 "?" 归一化为 shift+/，可触发快捷键帮助', () => {
    const handler = vi.fn()
    shortcuts.register('shift+/', handler)

    press('?', { shiftKey: true })

    expect(handler).toHaveBeenCalledTimes(1)
  })

  it('不带 Shift 的 "/" 仍然只触发搜索聚焦', () => {
    const handler = vi.fn()
    shortcuts.register('/', handler)

    press('/')

    expect(handler).toHaveBeenCalledTimes(1)
  })

  it('Ctrl+K 仍然归一化为 mod+k', () => {
    const handler = vi.fn()
    shortcuts.register('mod+k', handler)

    press('k', { ctrlKey: true })

    expect(handler).toHaveBeenCalledTimes(1)
  })
})
