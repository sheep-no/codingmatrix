import { mount, flushPromises } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn() }) }))
vi.mock('@/stores/apikey', () => ({ useApiKeyStore: () => ({ hasSiliconflowKey: true, siliconflowKey: { token: 'fixture' } }) }))
vi.mock('@/stores/user', () => ({ useUserStore: () => ({ getAccessToken: () => '' }) }))
import ImageGenerate from './ImageGenerate.vue'

describe('ImageGenerate interaction', () => {
  let wrapper
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({ items: [] }) }))
    wrapper = mount(ImageGenerate)
  })
  afterEach(() => { wrapper.unmount(); vi.unstubAllGlobals() })

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
})
