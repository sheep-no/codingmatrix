import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { push, createOutline, updateOutline, approveOutline } = vi.hoisted(() => ({
  push: vi.fn(),
  createOutline: vi.fn(),
  updateOutline: vi.fn(),
  approveOutline: vi.fn(),
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push, go: vi.fn() }),
}))

vi.mock('@/stores/apikey', () => ({
  useApiKeyStore: () => ({ hasSiliconflowKey: true, siliconflowKey: { token: 'test-token' } }),
}))

vi.mock('@/utils/tokenManager', () => ({
  useTokenManager: () => ({ getToken: () => 'test-token' }),
}))

vi.mock('@/utils/api/index', () => ({
  api: {
    ppt: {
      createOutline,
      updateOutline,
      approveOutline,
      getTemplates: vi.fn().mockResolvedValue({ templates: [] }),
      getHistory: vi.fn().mockResolvedValue({ records: [] }),
    },
  },
}))

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}))

import PPTGenerate from './PPTGenerate.vue'

const validSlides = [
  {
    id: 'slide-1',
    position: 0,
    slide_type: 'key_points',
    narrative_role: 'opportunity_map',
    title: '机会判断',
    key_message: '市场窗口已经打开',
    content_blocks: [{ type: 'text', content: '需求正在加速增长', metadata: {} }],
  },
  {
    id: 'slide-2',
    position: 1,
    slide_type: 'comparison',
    narrative_role: 'strategic_choice',
    title: '策略选择',
    key_message: '优先进入核心市场',
    content_blocks: [{ type: 'text', content: '集中资源验证关键假设', metadata: {} }],
  },
]

async function openOutline(wrapper, slides = validSlides) {
  createOutline.mockResolvedValue({ id: 'outline-1', version: 1, slides })
  await wrapper.find('.form-group textarea').setValue('测试主题')
  await wrapper.find('.generate-btn').trigger('click')
  await flushPromises()
}

describe('PPTGenerate workflow', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('edits, adds, reorders and removes outline slides before approval', async () => {
    updateOutline.mockImplementation(async (id, payload) => ({ id, slides: payload.slides }))
    approveOutline.mockImplementation(async id => ({ id, version: 1, slides: updateOutline.mock.calls[0][1].slides }))
    const wrapper = mount(PPTGenerate, { attachTo: document.body })
    await openOutline(wrapper)

    await wrapper.findAll('.outline-title-input')[0].setValue('更新后的机会判断')
    await wrapper.find('.outline-add-btn').trigger('click')
    let editors = wrapper.findAll('.outline-slide-editor')
    expect(editors).toHaveLength(3)

    await editors[2].find('.outline-title-input').setValue('新增页面')
    await editors[2].find('.outline-message-input').setValue('新增页面核心结论')
    await editors[2].find('.outline-content-input').setValue('新增页面内容')
    await editors[2].find('.outline-move-up').trigger('click')

    editors = wrapper.findAll('.outline-slide-editor')
    expect(editors[1].find('.outline-title-input').element.value).toBe('新增页面')
    await editors[2].find('.outline-remove').trigger('click')
    expect(wrapper.findAll('.outline-slide-editor')).toHaveLength(2)

    await wrapper.find('.outline-approve-btn').trigger('click')
    await flushPromises()

    expect(updateOutline).toHaveBeenCalledWith('outline-1', {
      slides: expect.arrayContaining([
        expect.objectContaining({ position: 0, title: '更新后的机会判断' }),
        expect.objectContaining({ position: 1, title: '新增页面' }),
      ]),
    })
    expect(updateOutline.mock.calls[0][1].slides.map(slide => slide.title)).toEqual([
      '更新后的机会判断',
      '新增页面',
    ])
    expect(approveOutline).toHaveBeenCalledWith('outline-1')
  })

  it('keeps outline approval disabled until every slide has required content', async () => {
    const wrapper = mount(PPTGenerate, { attachTo: document.body })
    await openOutline(wrapper, [{
        id: 'slide-1',
        position: 0,
        title: '页面标题',
        key_message: '',
        content_blocks: [{ content: '页面内容' }],
      }])

    expect(wrapper.text()).toContain('第 2 步：审阅大纲')
    expect(wrapper.text()).toContain('请填写页面核心结论')
    const approveButton = wrapper.find('.outline-approve-btn')
    expect(approveButton.attributes('disabled')).toBeDefined()
  })
})
