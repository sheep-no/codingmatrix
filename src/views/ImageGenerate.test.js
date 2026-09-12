import { mount, flushPromises } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn() }) }))
vi.mock('@/stores/apikey', () => ({ useApiKeyStore: () => ({ hasSiliconflowKey: true, siliconflowKey: { token: 'fixture' } }) }))
vi.mock('@/stores/user', () => ({ useUserStore: () => ({ getAccessToken: () => '' }) }))
import ImageGenerate from './ImageGenerate.vue'

describe('ImageGenerate interaction', () => {
  let wrapper
  beforeEach(() => {
    sessionStorage.clear()
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({ items: [] }) }))
    wrapper = mount(ImageGenerate)
  })
  afterEach(() => { wrapper.unmount(); sessionStorage.clear(); vi.unstubAllGlobals() })

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
    fetch.mockReturnValueOnce(new Promise(resolve => { finish = resolve }))
    await wrapper.get('#image-prompt').setValue('海边的灯塔')
    await wrapper.get('.btn-generate').trigger('click')
    expect(wrapper.findAll('.mode-tab, .style-card, .btn-random').every(button => button.element.disabled)).toBe(true)
    expect(wrapper.get('.loading-state').attributes('role')).toBe('status')
    finish({ ok: true, json: async () => ({ images: ['/fixture.png'] }) })
    await flushPromises()
    expect(wrapper.get('.generated-image').attributes('alt')).toBe('生成作品 1')
    expect(wrapper.get('[aria-label="下载图片"]').exists()).toBe(true)
    expect(wrapper.get('.btn-generate').element.disabled).toBe(false)
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
    fetch.mockImplementation((url) => {
      if (String(url).includes('text-to-image')) {
        return new Promise((resolve) => { finish = resolve })
      }
      return Promise.resolve({ ok: true, json: async () => ({ items: [] }) })
    })
    wrapper = mount(ImageGenerate)
    await flushPromises()
    expect(wrapper.get('.loading-state').attributes('role')).toBe('status')
    expect(wrapper.get('#image-prompt').element.value).toBe('月光下的狐狸')
    finish({ ok: true, json: async () => ({ images: ['/resumed.png'] }) })
    await flushPromises()
    expect(wrapper.get('.generated-image').attributes('src')).toBe('/resumed.png')
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
