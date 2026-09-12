import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import EmptyState from './EmptyState.vue'

describe('EmptyState idle canvas', () => {
  it('renders the idle board and emits a starter prompt', async () => {
    const wrapper = mount(EmptyState)

    expect(wrapper.get('.idle-title').text()).toBe('从一句需求开始')
    expect(wrapper.findAll('.idle-card')).toHaveLength(4)

    await wrapper.findAll('.idle-card')[0].trigger('click')
    expect(wrapper.emitted('quick-prompt')[0][0]).toContain('快速排序')
  })
})
