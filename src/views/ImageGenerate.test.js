import { mount, flushPromises } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const apiMock = vi.hoisted(() => ({
  kolors: {
    textToImage: vi.fn(),
    imageToImage: vi.fn(),
    getHistory: vi.fn(),
    deleteHistory: vi.fn(),
    clearHistory: vi.fn(),
    getResourceBlob: vi.fn()
  }
}))

vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn() }) }))
vi.mock('@/stores/apikey', () => ({ useApiKeyStore: () => ({ hasSiliconflowKey: true, siliconflowKey: { token: 'fixture' } }) }))
vi.mock('@/utils/api/index', () => ({ api: apiMock }))
import ImageGenerate from './ImageGenerate.vue'

describe('ImageGenerate interaction', () => {
  let wrapper
  beforeEach(() => {
    sessionStorage.clear()
    vi.clearAllMocks()
    apiMock.kolors.getHistory.mockResolvedValue({ items: [] })
    apiMock.kolors.textToImage.mockResolvedValue({ images: [] })
    apiMock.kolors.imageToImage.mockResolvedValue({ images: [] })
    apiMock.kolors.deleteHistory.mockResolvedValue({ status: 'deleted' })
    apiMock.kolors.clearHistory.mockResolvedValue({ status: 'deleted_all' })
    apiMock.kolors.getResourceBlob.mockResolvedValue(new Blob(['fixture'], { type: 'image/png' }))
    vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:fixture')
    vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})
    wrapper = mount(ImageGenerate)
  })
  afterEach(() => { wrapper.unmount(); sessionStorage.clear(); vi.restoreAllMocks() })

  it('selects styles using native buttons and keeps advanced options collapsed', async () => {
    expect(wrapper.get('details').attributes('open')).toBeUndefined()
    const anime = wrapper.findAll('.style-card').find(button => button.text() === '动漫')
    await anime.trigger('click')
    expect(anime.element.tagName).toBe('BUTTON')
    expect(anime.attributes('aria-pressed')).toBe('true')
    expect(wrapper.get('#image-prompt').attributes('maxlength')).toBe('2000')
  })

  it('reports unsupported and oversized uploads without enabling generation', async () => {
    await wrapper.findAll('.mode-tab')[1].trigger('click')
    await wrapper.get('#image-prompt').setValue('海边的灯塔')
    const input = wrapper.get('input[type="file"]')
    Object.defineProperty(input.element, 'files', { configurable: true, value: [new File(['text'], 'notes.txt', { type: 'text/plain' })] })
    await input.trigger('change')
    expect(wrapper.get('[role="alert"]').text()).toContain('JPG、PNG 或 WEBP')
    const large = new File(['fixture'], 'large.png', { type: 'image/png' })
    Object.defineProperty(large, 'size', { value: 11 * 1024 * 1024 })
    Object.defineProperty(input.element, 'files', { value: [large] })
    await input.trigger('change')
    expect(wrapper.get('[role="alert"]').text()).toContain('10MB')
    expect(wrapper.get('.btn-generate').element.disabled).toBe(true)
  })

  it('locks generation settings while a request is pending and renders accessible results', async () => {
    await flushPromises()
    let finish
    apiMock.kolors.textToImage.mockReturnValueOnce(new Promise(resolve => { finish = resolve }))
    await wrapper.get('#image-prompt').setValue('海边的灯塔')
    await wrapper.get('.btn-generate').trigger('click')
    expect(wrapper.findAll('.mode-tab, .style-card, .btn-random').every(button => button.element.disabled)).toBe(true)
    expect(wrapper.get('.loading-state').attributes('role')).toBe('status')
    finish({ images: ['/fixture.png'] })
    await flushPromises()
    expect(wrapper.get('.generated-image').attributes('alt')).toBe('生成作品 1')
    expect(wrapper.get('[aria-label="下载图片"]').exists()).toBe(true)
    expect(wrapper.get('.btn-generate').element.disabled).toBe(false)
    expect(apiMock.kolors.textToImage).toHaveBeenCalledOnce()
  })

  it('persists the prompt and restores the canvas after a refresh', async () => {
    await wrapper.get('#image-prompt').setValue('海边的灯塔')
    await flushPromises()
    expect(JSON.parse(sessionStorage.getItem('image-generate-session-v1')).prompt).toBe('海边的灯塔')

    wrapper.unmount()
    sessionStorage.setItem('image-generate-session-v1', JSON.stringify({
      savedAt: Date.now(),
      mode: 'text2img',
      prompt: '海边的灯塔',
      style: 'anime',
      resolution: '512x512',
      steps: 25,
      cfgScale: 7.5,
      denoising: 0.7,
      seed: -1,
      isGenerating: false,
      generatedImages: [{ url: '/saved.png' }],
      lastGeneratedImage: { url: '/saved.png', prompt: '海边的灯塔' },
      originalPrompt: '海边的灯塔',
    }))
    wrapper = mount(ImageGenerate)
    await flushPromises()
    expect(wrapper.get('#image-prompt').element.value).toBe('海边的灯塔')
    expect(wrapper.get('.generated-image').attributes('src')).toBe('/saved.png')
    const anime = wrapper.findAll('.style-card').find(button => button.text() === '动漫')
    expect(anime.attributes('aria-pressed')).toBe('true')
  })

  it('resumes in-flight generation after a refresh from sessionStorage', async () => {
    wrapper.unmount()
    sessionStorage.setItem('image-generate-session-v1', JSON.stringify({
      savedAt: Date.now(),
      mode: 'text2img',
      prompt: '月光下的狐狸',
      style: 'realistic',
      resolution: '512x512',
      steps: 20,
      cfgScale: 7,
      denoising: 0.7,
      seed: -1,
      isGenerating: true,
      generatedImages: [],
      lastGeneratedImage: null,
      originalPrompt: '',
    }))
    let finish
    apiMock.kolors.textToImage.mockReturnValueOnce(new Promise((resolve) => { finish = resolve }))
    wrapper = mount(ImageGenerate)
    await flushPromises()
    expect(wrapper.get('.loading-state').attributes('role')).toBe('status')
    expect(wrapper.get('#image-prompt').element.value).toBe('月光下的狐狸')
    finish({ images: ['/resumed.png'] })
    await flushPromises()
    expect(wrapper.get('.generated-image').attributes('src')).toBe('/resumed.png')
  })

  it('persists protected resource filenames and restores them through the authenticated client', async () => {
    apiMock.kolors.textToImage.mockResolvedValueOnce({
      paths: ['/workspace/generated_images/keep.png']
    })
    await wrapper.get('#image-prompt').setValue('海边的灯塔')
    await wrapper.get('.btn-generate').trigger('click')
    await flushPromises()

    expect(apiMock.kolors.getResourceBlob).toHaveBeenCalledWith('keep.png')
    const saved = JSON.parse(sessionStorage.getItem('image-generate-session-v1'))
    expect(saved.generatedImages).toEqual([{ ref: 'keep.png' }])
    expect(saved.lastGeneratedImage).toMatchObject({ ref: 'keep.png', url: null })

    wrapper.unmount()
    apiMock.kolors.getResourceBlob.mockClear()
    wrapper = mount(ImageGenerate)
    await flushPromises()

    expect(apiMock.kolors.getResourceBlob).toHaveBeenCalledWith('keep.png')
    expect(wrapper.get('.generated-image').attributes('src')).toBe('blob:fixture')
  })

  it('falls back to text-to-image when restoring an img2img session without a file', async () => {
    wrapper.unmount()
    sessionStorage.setItem('image-generate-session-v1', JSON.stringify({
      savedAt: Date.now(),
      mode: 'img2img',
      prompt: '月光下的狐狸',
      style: 'realistic',
      resolution: '512x512',
      steps: 25,
      cfgScale: 7.5,
      denoising: 0.7,
      seed: -1,
      isGenerating: false,
      generatedImages: [{ url: '/saved.png' }],
      lastGeneratedImage: { url: '/saved.png', prompt: '橘猫' },
      originalPrompt: '橘猫',
    }))
    wrapper = mount(ImageGenerate)
    await flushPromises()
    expect(wrapper.get('#image-prompt').element.value).toBe('月光下的狐狸')
    expect(wrapper.get('.mode-tab.active').text()).toContain('文生图')
    expect(wrapper.get('.btn-generate').element.disabled).toBe(false)
  })
})
