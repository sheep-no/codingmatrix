import { mount } from '@vue/test-utils'
import { afterEach, describe, expect, it } from 'vitest'
import UploadModal from './UploadModal.vue'

afterEach(() => {
  document.body.innerHTML = ''
})

describe('UploadModal accessibility', () => {
  it('moves focus into the dialog and restores it when closed', async () => {
    const trigger = document.createElement('button')
    document.body.appendChild(trigger)
    trigger.focus()
    const wrapper = mount(UploadModal, {
      attachTo: document.body,
      props: { modelValue: false }
    })

    await wrapper.setProps({ modelValue: true })
    await wrapper.vm.$nextTick()
    expect(document.activeElement).toBe(document.querySelector('[role="dialog"]'))

    await wrapper.setProps({ modelValue: false })
    expect(document.activeElement).toBe(trigger)
  })

  it('closes on Escape and exposes the upload zone as a keyboard control', async () => {
    const wrapper = mount(UploadModal, {
      attachTo: document.body,
      props: { modelValue: true }
    })
    const dialog = document.querySelector('[role="dialog"]')

    expect(document.querySelector('.upload-zone').getAttribute('tabindex')).toBe('0')
    dialog.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    await wrapper.vm.$nextTick()

    expect(wrapper.emitted('update:modelValue')).toEqual([[false]])
  })
})
