import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

enableAutoUnmount(afterEach)
afterEach(() => vi.unstubAllGlobals())

const { push, uploadFile, createOutline, updateOutline, approveOutline, generateFromOutline, route } = vi.hoisted(() => ({
  route: { query: {} },
  push: vi.fn(),
  uploadFile: vi.fn(),
  createOutline: vi.fn(),
  updateOutline: vi.fn(),
  approveOutline: vi.fn(),
  generateFromOutline: vi.fn(),
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push, go: vi.fn() }),
  useRoute: () => route,
}))

vi.mock('@/stores/apikey', () => ({
  useApiKeyStore: () => ({ hasSiliconflowKey: true, siliconflowKey: { token: 'test-token' } }),
}))

vi.mock('@/utils/tokenManager', () => ({
  useTokenManager: () => ({ getToken: () => 'test-token' }),
}))

vi.mock('@/utils/api/index', () => ({
  api: {
    uploadFile,
    ppt: {
      createOutline,
      updateOutline,
      approveOutline,
      generateFromOutline,
      getTemplates: vi.fn().mockResolvedValue({ templates: [] }),
      getHistory: vi.fn().mockResolvedValue({ records: [] }),
      deleteHistory: vi.fn().mockResolvedValue({ success: true }),
    },
  },
}))

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}))

import PPTGenerate from './PPTGenerate.vue'
import { api } from '@/utils/api/index'

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
    vi.stubGlobal('WebSocket', vi.fn(function () { return { close: vi.fn() } }))
    route.query = {}
    api.ppt.getTemplates.mockResolvedValue({ templates: [] })
    sessionStorage.clear()
  })

  it('submits auto and displays the canonical selection and scenario recommendations', async () => {
    api.ppt.getTemplates.mockImplementation(async (category, options) => options ? {
      scenario: 'business', templates: ['business_report', 'minimal'],
    } : { templates: [{ id: 'business_report', name: 'Business', name_zh: '商务报告', description: '用于经营复盘', scenarios: ['business'], primary_color: '#123456' }] })
    createOutline.mockResolvedValue({ id: 'auto-outline', template_id: 'business_report', scenario: 'business', slides: validSlides })
    const wrapper = mount(PPTGenerate)
    await flushPromises()
    expect(wrapper.text()).toContain('用于经营复盘')
    expect(wrapper.text()).toContain('场景：商务汇报')
    expect(wrapper.text()).toContain('色彩示意')
    await wrapper.find('.template-auto').trigger('click')
    await wrapper.find('.form-group textarea').setValue('季度经营汇报')
    await wrapper.find('.generate-btn').trigger('click')
    await flushPromises()
    expect(createOutline).toHaveBeenCalledWith(expect.objectContaining({ template_id: 'auto' }), expect.objectContaining({ onEvent: expect.any(Function) }))
    expect(wrapper.find('.template-result').text()).toContain('自动选择结果：商务报告')
    expect(wrapper.find('.template-result').text()).toContain('模板 ID：business_report')
    expect(wrapper.find('.template-result').text()).toContain('推荐模板：商务报告、minimal')
    expect(api.ppt.getTemplates).toHaveBeenLastCalledWith(null, { topic: '季度经营汇报', scenario: 'business' })
    expect(wrapper.find('.template-grid .selected').attributes('disabled')).toBeDefined()
    wrapper.unmount()
  })

  it('preserves manual alias selection and retries recommendations without recreating the outline', async () => {
    createOutline.mockResolvedValue({ id: 'manual-outline', template_id: 'business_report', scenario: 'business', slides: validSlides })
    const wrapper = mount(PPTGenerate)
    await flushPromises()
    await wrapper.findAll('.template-grid .template-card')[1].trigger('click')
    await wrapper.find('.form-group textarea').setValue('手动模板')
    await wrapper.find('.generate-btn').trigger('click')
    await flushPromises()
    expect(createOutline).toHaveBeenCalledWith(expect.objectContaining({ template_id: 'business' }), expect.objectContaining({ onEvent: expect.any(Function) }))
    expect(wrapper.find('.template-result').text()).toContain('已采用模板：business_report')
    expect(wrapper.text()).toContain('推荐信息暂不可用')
    api.ppt.getTemplates.mockResolvedValueOnce({ scenario: 'business', templates: ['business_report'] })
    await wrapper.find('.template-result button').trigger('click')
    await flushPromises()
    expect(wrapper.find('.template-result').text()).toContain('推荐模板：business_report')
    expect(createOutline).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })

  it('keeps auto available when the template registry fails and allows reloading', async () => {
    api.ppt.getTemplates.mockRejectedValueOnce(new Error('unavailable'))
    const wrapper = mount(PPTGenerate)
    await flushPromises()
    expect(wrapper.text()).toContain('当前显示备用配色')
    expect(wrapper.find('.template-auto').exists()).toBe(true)
    api.ppt.getTemplates.mockResolvedValueOnce({ templates: [{ id: 'education', name_zh: '教育培训', description: '课程教学', scenarios: ['education'] }] })
    await wrapper.find('.template-hint button').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('课程教学')
    expect(wrapper.text()).not.toContain('当前显示备用配色')
    wrapper.unmount()
  })

  it('resumes the exported task from the route without creating another task', async () => {
    route.query = { task_id: 'revised-task' }
    const socket = { close: vi.fn() }
    const WebSocketMock = vi.fn(function () { return socket })
    vi.stubGlobal('WebSocket', WebSocketMock)
    const wrapper = mount(PPTGenerate)
    await flushPromises()
    expect(WebSocketMock).toHaveBeenCalledWith(expect.stringContaining('/api/v1/ws/ppt/revised-task?'))
    expect(generateFromOutline).not.toHaveBeenCalled()
    socket.onmessage({ data: JSON.stringify({
      type: 'completed', progress: 1, step: 'completed', result: { ppt_id: 'revised-task' },
    }) })
    await flushPromises()
    expect(wrapper.text()).toContain('生成成功!')
    expect(wrapper.find('.preview-placeholder').exists()).toBe(false)
    await wrapper.find('.preview-btn').trigger('click')
    expect(push).toHaveBeenCalledWith('/ppt-preview/revised-task')
    wrapper.unmount()
    vi.unstubAllGlobals()
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
    expect(wrapper.text()).toContain('当前 3 页内容（另加封面）')

    await editors[2].find('.outline-title-input').setValue('新增页面')
    await editors[2].find('.outline-message-input').setValue('新增页面核心结论')
    await editors[2].find('.outline-content-input').setValue('新增页面内容')
    await editors[2].find('.outline-move-up').trigger('click')

    editors = wrapper.findAll('.outline-slide-editor')
    expect(editors[1].find('.outline-title-input').element.value).toBe('新增页面')
    await editors[2].find('.outline-remove').trigger('click')
    expect(wrapper.findAll('.outline-slide-editor')).toHaveLength(2)
    expect(wrapper.text()).toContain('当前 2 页内容（另加封面）')

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

  it('uploads material before creating its versioned outline', async () => {
    uploadFile.mockResolvedValue({ id: 42, filename: 'brief.txt' })
    createOutline.mockResolvedValue({ id: 'outline-material', version: 1, slides: validSlides })
    const wrapper = mount(PPTGenerate, { attachTo: document.body })
    const file = new File(['客户续约率达到 92%'], 'brief.txt', { type: 'text/plain' })
    const input = wrapper.find('input[type="file"]')
    Object.defineProperty(input.element, 'files', { value: [file] })
    await input.trigger('change')
    await wrapper.find('.generate-btn').trigger('click')
    await flushPromises()

    expect(uploadFile).toHaveBeenCalledWith(file)
    expect(createOutline).toHaveBeenCalledWith(expect.objectContaining({
      material_file_ids: [42],
      api_key_token: 'test-token',
    }), expect.objectContaining({ onEvent: expect.any(Function) }))
    expect(createOutline.mock.calls[0][0].num_slides).toBeUndefined()
    expect(wrapper.text()).toContain('页数')
    expect(wrapper.text()).toContain('自动（按主题决定）')
    expect(wrapper.find('.preview-panel .outline-review-panel').exists()).toBe(true)
    expect(wrapper.find('.config-panel .outline-review-panel').exists()).toBe(false)
  })

  it('generates from the approved outline version', async () => {
    updateOutline.mockImplementation(async (id, payload) => ({ id, version: 2, slides: payload.slides }))
    approveOutline.mockImplementation(async id => ({ id, version: 2, slides: validSlides }))
    generateFromOutline.mockResolvedValue({ task_id: 'task-1' })
    const wrapper = mount(PPTGenerate, { attachTo: document.body })
    await wrapper.findAll('.option-select')[1].setValue('markdown')
    for (const checkbox of wrapper.findAll('.option-checkbox')) await checkbox.setValue(false)
    await openOutline(wrapper)
    await wrapper.find('.outline-approve-btn').trigger('click')
    await flushPromises()
    await wrapper.find('.quality-mode-panel .generate-btn').trigger('click')
    await flushPromises()

    expect(generateFromOutline).toHaveBeenCalledWith('outline-1', 'standard', 2, {
      output_format: 'markdown', auto_images: false, enable_animation: false, api_key_token: 'test-token',
    })
    expect(wrapper.find('.generation-live').exists()).toBe(true)
    expect(wrapper.text()).toContain('正在生成 PPT')
    expect(wrapper.text()).toContain('机会判断')
  })

  it('shows outline drafting stages in the main panel while waiting', async () => {
    let resolveDraft
    createOutline.mockImplementation(() => new Promise(resolve => { resolveDraft = resolve }))
    const wrapper = mount(PPTGenerate, { attachTo: document.body })
    await wrapper.find('.form-group textarea').setValue('测试主题')
    await wrapper.find('.generate-btn').trigger('click')
    await flushPromises()

    expect(wrapper.find('.preview-panel .outline-drafting').exists()).toBe(true)
    expect(wrapper.text()).toContain('正在生成大纲')
    expect(wrapper.text()).toContain('分析主题与受众')

    resolveDraft({ id: 'outline-1', version: 1, slides: validSlides })
    await flushPromises()
    expect(wrapper.find('.preview-panel .outline-review-panel').exists()).toBe(true)
    expect(wrapper.find('.outline-drafting').exists()).toBe(false)
  })

  it('shows streamed slides in the main panel while drafting', async () => {
    let onEvent
    createOutline.mockImplementation((_payload, options) => {
      onEvent = options.onEvent
      return new Promise(() => {})
    })
    const wrapper = mount(PPTGenerate, { attachTo: document.body })
    await wrapper.find('.form-group textarea').setValue('测试主题')
    await wrapper.find('.generate-btn').trigger('click')
    await flushPromises()

    onEvent({ type: 'stage', index: 2, label: '起草页面结构' })
    onEvent({ type: 'slide', slide: validSlides[0] })
    await flushPromises()

    expect(wrapper.find('.outline-drafting').exists()).toBe(true)
    expect(wrapper.text()).toContain('起草页面结构')
    expect(wrapper.find('.outline-drafting .generation-slide-list').text()).toContain('机会判断')
  })

  it('resumes outline drafting after a refresh from sessionStorage', async () => {
    createOutline.mockImplementation(() => new Promise(() => {}))
    sessionStorage.setItem('ppt-generate-session-v1', JSON.stringify({
      workflowStep: 1,
      topic: '刷新时仍在起草',
      slideCount: 'auto',
      selectedTemplate: 'modern',
      outlineDrafting: true,
      outlineStageIndex: 1,
      outlineDraft: null,
      outlineSlides: [validSlides[0]],
      generating: false,
      generatedFileUrl: '',
      generatedSlides: [],
      currentTaskId: '',
    }))
    const wrapper = mount(PPTGenerate, { attachTo: document.body })
    await flushPromises()

    expect(wrapper.find('.preview-panel .outline-drafting').exists()).toBe(true)
    expect(wrapper.text()).toContain('正在生成大纲')
    expect(wrapper.text()).toContain('机会判断')
    expect(createOutline).toHaveBeenCalledWith(
      expect.objectContaining({ topic: '刷新时仍在起草' }),
      expect.objectContaining({ onEvent: expect.any(Function) }),
    )
  })

  it('restores outline review after a refresh from sessionStorage', async () => {
    sessionStorage.setItem('ppt-generate-session-v1', JSON.stringify({
      workflowStep: 2,
      topic: '刷新后仍在的主题',
      slideCount: 'auto',
      selectedTemplate: 'modern',
      outlineDraft: { id: 'outline-restored', version: 1, slides: validSlides },
      outlineSlides: validSlides,
      generating: false,
      generatedFileUrl: '',
      generatedSlides: [],
      currentTaskId: '',
    }))
    const wrapper = mount(PPTGenerate, { attachTo: document.body })
    await flushPromises()

    expect(wrapper.find('.form-group textarea').element.value).toBe('刷新后仍在的主题')
    expect(wrapper.find('.preview-panel .outline-review-panel').exists()).toBe(true)
    expect(wrapper.find('.outline-title-input').element.value).toBe('机会判断')
    expect(createOutline).not.toHaveBeenCalled()
  })

  it('reconnects the generating task after a refresh', async () => {
    const socket = { close: vi.fn() }
    const WebSocketMock = vi.fn(function () { return socket })
    vi.stubGlobal('WebSocket', WebSocketMock)
    sessionStorage.setItem('ppt-generate-session-v1', JSON.stringify({
      workflowStep: 3,
      topic: '进行中的主题',
      generating: true,
      currentTaskId: 'task-resume',
      outlineSlides: validSlides,
      generatedFileUrl: '',
      generatedSlides: [],
      progressState: { progress: 0.4, step: 'rendering', message: '正在生成第 1 页...' },
    }))
    const wrapper = mount(PPTGenerate, { attachTo: document.body })
    await flushPromises()

    expect(WebSocketMock).toHaveBeenCalledWith(expect.stringContaining('/api/v1/ws/ppt/task-resume?'))
    expect(wrapper.find('.generation-live').exists()).toBe(true)
    expect(wrapper.text()).toContain('正在生成第 1 页')
    wrapper.unmount()
    vi.unstubAllGlobals()
  })

  it('shows history titles from the backend and opens preview', async () => {
    api.ppt.getHistory.mockResolvedValueOnce({
      records: [{
        task_id: 'hist-1',
        title: '季度经营汇报',
        slide_count: 12,
        has_file: true,
        created_at: '2026-09-12T08:00:00',
      }],
    })
    const wrapper = mount(PPTGenerate)
    await flushPromises()
    await wrapper.find('.header-btn').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('季度经营汇报')
    expect(wrapper.text()).toContain('可预览')
    expect(wrapper.text()).not.toContain('未命名')
    await wrapper.find('.history-preview-btn').trigger('click')
    expect(push).toHaveBeenCalledWith('/ppt-preview/hist-1')
  })

  it('loads a finished history item into the success panel', async () => {
    api.ppt.getHistory.mockResolvedValueOnce({
      records: [{ task_id: 'hist-2', title: '加载这份', slide_count: 8, has_file: true, created_at: '2026-09-12T08:00:00' }],
    })
    const wrapper = mount(PPTGenerate)
    await flushPromises()
    await wrapper.find('.header-btn').trigger('click')
    await flushPromises()
    await wrapper.find('.history-load-btn').trigger('click')
    await flushPromises()
    expect(wrapper.find('.preview-btn').exists()).toBe(true)
    await wrapper.find('.preview-btn').trigger('click')
    expect(push).toHaveBeenCalledWith('/ppt-preview/hist-2')
  })

  it('shows a history load error with retry', async () => {
    api.ppt.getHistory.mockRejectedValueOnce(new Error('网络失败'))
    const wrapper = mount(PPTGenerate)
    await flushPromises()
    await wrapper.find('.header-btn').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('网络失败')
    api.ppt.getHistory.mockResolvedValueOnce({ records: [] })
    await wrapper.find('.history-empty button').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('暂无历史记录')
  })
})
