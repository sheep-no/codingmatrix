import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { push, regenerateOutlineSlide } = vi.hoisted(() => ({
  push: vi.fn(),
  regenerateOutlineSlide: vi.fn(),
}))

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { id: 'task-1' }, query: {} }),
  useRouter: () => ({ push, go: vi.fn() }),
}))

vi.mock('@/stores/apikey', () => ({
  useApiKeyStore: () => ({ siliconflowKey: { token: 'user-token' } }),
}))

vi.mock('@/utils/api/index', () => ({
  api: {
    ppt: {
      previewPPTHtml: vi.fn().mockRejectedValue(new Error('no html preview')),
      getPPTSlides: vi.fn().mockResolvedValue({ slides: [] }),
      getQualityReport: vi.fn().mockResolvedValue({
        overall_score: 88,
        quality_mode: 'refined',
        outline_version: 2,
        outline_id: 'outline-1',
        slide_scores: { 'slide-1': 96, 'slide-2': 80 },
        issues: [{
          slide_id: 'slide-2',
          issue_type: 'text_overflow',
          severity: 'high',
          message: '文本超出文本框边界',
          fix_action: 'reduce_text_or_switch_layout',
        }],
        reflow_attempts: { 'slide-2': 2 },
      }),
      regenerateOutlineSlide,
      generateFromOutline: vi.fn(),
      getOutline: vi.fn(),
    },
  },
}))

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), error: vi.fn() },
}))

import PPTPreview from './PPTPreview.vue'
import { api } from '@/utils/api/index'
import { ElMessage } from 'element-plus'

describe('PPTPreview quality report', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.ppt.downloadPDF = vi.fn().mockRejectedValue(new Error('PDF unavailable'))
    api.ppt.getPPTSlides.mockResolvedValue({ slides: [{ title: '测试页', content_blocks: [{ content: '结构内容' }] }] })
    api.ppt.getOutline.mockResolvedValue({ id: 'outline-1', version: 2, slides: [{
      id: 'slide-2', position: 1, title: '原标题', key_message: '原结论', speaker_notes: '备注',
      content_blocks: [{ type: 'text', content: '原正文', metadata: { source: '保留' } }],
    }] })
  })

  it('submits actual edits with the preview version and opens the new task', async () => {
    regenerateOutlineSlide.mockResolvedValue({ task_id: 'task-2' })
    const wrapper = mount(PPTPreview)
    await vi.waitFor(() => expect(wrapper.text()).toContain('生成质量 88'))

    expect(wrapper.text()).toContain('slide-1 96 分')
    expect(wrapper.text()).toContain('slide-2 80 分')
    expect(wrapper.text()).toContain('文本溢出')
    expect(wrapper.text()).toContain('slide-2: 文本超出文本框边界')
    expect(wrapper.text()).toContain('缩减文本或切换布局')
    expect(wrapper.text()).toContain('需人工复核')
    await vi.waitFor(() => expect(wrapper.text()).toContain('结构内容'))
    expect(wrapper.text()).toContain('结构预览')
    expect(wrapper.text()).toContain('重新导出整份 PPTX')
    expect(api.ppt.getOutline).toHaveBeenCalledWith('outline-1', 2)
    await wrapper.find('.slide-title-input').setValue('更新标题')
    await wrapper.find('.slide-block-input').setValue('更新正文')
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    expect(regenerateOutlineSlide).toHaveBeenCalledWith('outline-1', 'slide-2', 'refined', expect.objectContaining({
      title: '更新标题', key_message: '原结论', speaker_notes: '备注',
      content_blocks: [{ type: 'text', content: '更新正文', metadata: { source: '保留' } }],
    }), 2, { auto_images: true, enable_animation: true, api_key_token: 'user-token' })
    expect(push).toHaveBeenCalledWith({ path: '/ppt-generate', query: { task_id: 'task-2' } })
    wrapper.unmount()
  })

  it.each([null, 'vision_review_unavailable: fake-secret'])('shows safe actionable degradation with stage %s', async stage => {
    api.ppt.getQualityReport.mockResolvedValueOnce({ overall_score: 88, quality_mode: 'refined', degraded_stage: stage,
      issues: [{ issue_type: 'vision_review_unavailable', message: 'Authorization: Bearer fake-secret' }],
    })
    const wrapper = mount(PPTPreview)
    await flushPromises()
    const warning = wrapper.find('.quality-report-warning')
    expect(warning.text()).toContain('视觉复审未完成')
    expect(warning.text()).toContain('PDF 渲染依赖')
    expect(wrapper.text()).not.toContain('fake-secret')
    await warning.find('button').trigger('click')
    expect(push).toHaveBeenCalledWith('/settings')
    api.ppt.downloadPPT = vi.fn().mockRejectedValueOnce(new Error('Authorization: Bearer fake-secret'))
    await warning.findAll('button')[1].trigger('click')
    await flushPromises()
    expect(api.ppt.downloadPPT).toHaveBeenCalledWith('task-1', 'pptx')
    expect(ElMessage.error).toHaveBeenCalledWith('成品下载失败，请稍后重试或检查登录状态。')
    wrapper.unmount()
  })

  it('retains edits after dispatch failure and retries the saved version', async () => {
    regenerateOutlineSlide.mockRejectedValueOnce(Object.assign(new Error('修改已保存，导出失败'), { savedVersion: 3 }))
    api.ppt.generateFromOutline.mockResolvedValue({ task_id: 'retry-task' })
    const wrapper = mount(PPTPreview)
    await flushPromises()
    await wrapper.find('.slide-title-input').setValue('保留修改')
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    expect(wrapper.find('.slide-title-input').element.value).toBe('保留修改')
    expect(wrapper.text()).toContain('重试导出已保存版本')
    expect(push).not.toHaveBeenCalled()
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    expect(regenerateOutlineSlide).toHaveBeenCalledTimes(1)
    expect(api.ppt.generateFromOutline).toHaveBeenCalledWith('outline-1', 'refined', 3, expect.any(Object))
    expect(push).toHaveBeenCalledWith({ path: '/ppt-generate', query: { task_id: 'retry-task' } })
    wrapper.unmount()
  })

  it('prefers the authenticated PDF artifact and releases its URL on unmount', async () => {
    const blob = new Blob(['%PDF'], { type: 'application/pdf' })
    api.ppt.downloadPDF.mockResolvedValue(blob)
    URL.createObjectURL = vi.fn().mockReturnValue('blob:rendered-pdf')
    URL.revokeObjectURL = vi.fn()
    const wrapper = mount(PPTPreview)
    await vi.waitFor(() => expect(wrapper.find('iframe').attributes('src')).toBe('blob:rendered-pdf'))
    expect(wrapper.text()).toContain('成品 PDF 预览')
    expect(wrapper.text()).toContain('生成质量 88')
    expect(wrapper.text()).not.toContain('暂无幻灯片数据')
    expect(api.ppt.previewPPTHtml).not.toHaveBeenCalled()
    wrapper.unmount()
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:rendered-pdf')
  })

  it('shows HTML fallback without a contradictory empty state', async () => {
    api.ppt.previewPPTHtml.mockResolvedValueOnce('<html><body>结构内容</body></html>')
    const wrapper = mount(PPTPreview)
    await vi.waitFor(() => expect(wrapper.find('iframe').exists()).toBe(true))
    expect(wrapper.text()).toContain('结构预览')
    expect(wrapper.text()).not.toContain('暂无幻灯片数据')
    wrapper.unmount()
  })

  it('keeps the deck stage beside the quality inspector', async () => {
    const wrapper = mount(PPTPreview)
    await flushPromises()
    expect(wrapper.find('.preview-workspace').exists()).toBe(true)
    expect(wrapper.find('.preview-stage').exists()).toBe(true)
    expect(wrapper.find('.preview-inspector').exists()).toBe(true)
    expect(wrapper.find('.preview-inspector .quality-report-card').exists()).toBe(true)
    wrapper.unmount()
  })
})
