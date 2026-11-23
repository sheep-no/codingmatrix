import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, shallowMount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/utils/api/index', () => ({
  api: { getRequirementAssociations: vi.fn(), uploadFile: vi.fn() }
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

describe('bottominput 附件随消息发送', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    api.getRequirementAssociations.mockReset()
    api.uploadFile.mockReset()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('上传后把附件路径与文件名带入 send 载荷，且上传请求携带真实会话 ID', async () => {
    api.uploadFile.mockResolvedValue({
      id: 6,
      filename: 'upload-test.txt',
      file_size: 113,
      content_type: 'text/plain',
      download_url: '/api/v1/files/6/download'
    })

    const wrapper = shallowMount(Bottominput, {
      props: { conversationId: 12 },
      global: {
        plugins: [createPinia()],
        stubs: {
          FileDropZone: { template: '<div />', methods: { setupDropZone() {}, cleanupDropZone() {} } }
        }
      }
    })
    const state = wrapper.vm.$.setupState
    const file = new File(['hello'], 'upload-test.txt', { type: 'text/plain' })

    await state.processFile(file)
    await flushPromises()

    expect(api.uploadFile).toHaveBeenCalledWith(file, 12)
    vi.spyOn(state.userStore, 'isLoggedIn', 'get').mockReturnValue(true)
    state.inputMessage = '总结这个文件'
    state.sendMessage()

    const payload = wrapper.emitted('send')[0][0]
    expect(payload.files).toHaveLength(1)
    expect(payload.files[0]).toMatchObject({
      id: 6,
      name: 'upload-test.txt',
      serverPath: 'upload-test.txt'
    })
    wrapper.unmount()
  })

  it('草稿会话 ID 不作为上传参数提交', async () => {
    api.uploadFile.mockResolvedValue({ id: 7, filename: 'a.txt' })
    const wrapper = shallowMount(Bottominput, {
      props: { conversationId: 'temp_1700000000' },
      global: {
        plugins: [createPinia()],
        stubs: {
          FileDropZone: { template: '<div />', methods: { setupDropZone() {}, cleanupDropZone() {} } }
        }
      }
    })

    await wrapper.vm.$.setupState.processFile(new File(['x'], 'a.txt', { type: 'text/plain' }))
    await flushPromises()

    expect(api.uploadFile).toHaveBeenCalledWith(expect.any(File), null)
    wrapper.unmount()
  })
})
