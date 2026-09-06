import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

const { push, regenerateOutlineSlide } = vi.hoisted(() => ({
  push: vi.fn(),
  regenerateOutlineSlide: vi.fn(),
}))

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { id: 'task-1' }, query: {} }),
  useRouter: () => ({ push, go: vi.fn() }),
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
    },
  },
}))

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), error: vi.fn() },
}))

import PPTPreview from './PPTPreview.vue'

describe('PPTPreview quality report', () => {
  it('shows scores, issues, repair actions and starts regeneration for the affected slide', async () => {
    regenerateOutlineSlide.mockResolvedValue({ task_id: 'task-2' })
    const wrapper = mount(PPTPreview)
    await vi.waitFor(() => expect(wrapper.text()).toContain('生成质量 88'))

    expect(wrapper.text()).toContain('slide-1 96 分')
    expect(wrapper.text()).toContain('slide-2 80 分')
    expect(wrapper.text()).toContain('文本溢出')
    expect(wrapper.text()).toContain('slide-2: 文本超出文本框边界')
    expect(wrapper.text()).toContain('缩减文本或切换布局')
    expect(wrapper.text()).toContain('需人工复核')
    await wrapper.find('.quality-regenerate-btn').trigger('click')

    expect(regenerateOutlineSlide).toHaveBeenCalledWith('outline-1', 'slide-2', 'refined')
    expect(push).toHaveBeenCalledWith('/ppt/generate?task_id=task-2')
  })
})
