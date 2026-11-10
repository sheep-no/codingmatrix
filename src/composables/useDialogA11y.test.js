import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { defineComponent, h, nextTick, ref } from 'vue'

import { useDialogA11y } from './useDialogA11y'

const Host = defineComponent({
  setup() {
    const visible = ref(false)
    const dialogRef = ref(null)
    const close = () => { visible.value = false }
    useDialogA11y(dialogRef, visible, close)
    return { visible, dialogRef }
  },
  render() {
    return h('div', [
      h('button', { id: 'outside' }, 'outside'),
      this.visible
        ? h('div', { ref: 'dialogRef', id: 'dialog', tabindex: '-1' }, [
            h('button', { id: 'first' }, 'first'),
            h('button', { id: 'last' }, 'last')
          ])
        : null
    ])
  }
})

describe('useDialogA11y', () => {
  it('moves focus into the dialog and closes on Escape', async () => {
    const wrapper = mount(Host, { attachTo: document.body })
    const outside = wrapper.get('#outside').element
    outside.focus()

    wrapper.vm.visible = true
    await nextTick()
    await nextTick()

    expect(document.activeElement.id).toBe('dialog')

    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await nextTick()

    expect(wrapper.vm.visible).toBe(false)
    expect(document.activeElement).toBe(outside)
    wrapper.unmount()
  })

  it('wraps Tab focus inside the dialog', async () => {
    const wrapper = mount(Host, { attachTo: document.body })
    wrapper.vm.visible = true
    await nextTick()
    await nextTick()

    wrapper.get('#last').element.focus()
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab' }))
    expect(document.activeElement.id).toBe('first')

    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', shiftKey: true }))
    expect(document.activeElement.id).toBe('last')
    wrapper.unmount()
  })
})
