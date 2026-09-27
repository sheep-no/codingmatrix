import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, shallowMount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/utils/api/index', () => ({
  api: { getRequirementAssociations: vi.fn() }
}))

import Bottominput from './bottominput.vue'
import { api } from '@/utils/api/index'

function mountInput() {
  return shallowMount(Bottominput, {
    global: {
      plugins: [createPinia()],
      stubs: {
        FileDropZone: { template: '<div />', methods: { setupDropZone() {}, cleanupDropZone() {} } }
      }
    }
  })
}

describe('bottominput 需求联想面板', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.useFakeTimers()
    api.getRequirementAssociations.mockReset()
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  it('按后端字段 category/content 渲染，点击后追加文本并只移除该项', async () => {
    api.getRequirementAssociations.mockResolvedValue({
      items: [
        { content: '建议A', category: 'functional', confidence: 0.9 },
        { content: '建议B', category: 'risk', confidence: 0.8 }
      ]
    })

    const wrapper = mountInput()
    const state = wrapper.vm.$.setupState
    state.inputMessage = 'x'.repeat(25)

    await vi.advanceTimersByTimeAsync(800)
    await flushPromises()

    const rows = wrapper.findAll('.association-item')
    expect(rows).toHaveLength(2)
    expect(rows[0].text()).toContain('functional')
    expect(rows[0].text()).toContain('建议A')
    expect(rows[1].text()).toContain('risk')
    expect(rows[1].text()).toContain('建议B')

    await rows[0].trigger('click')
    await vi.advanceTimersByTimeAsync(300)
    await flushPromises()

    expect(state.inputMessage).toContain('建议A')
    const remaining = wrapper.findAll('.association-item')
    expect(remaining).toHaveLength(1)
    expect(remaining[0].text()).toContain('建议B')

    wrapper.unmount()
  })
})
