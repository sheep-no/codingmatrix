import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import MessageAttachments from './MessageAttachments.vue'
import MessageList from './MessageList.vue'
import MessageThinking from './MessageThinking.vue'
import FilePreview from '../FilePreview.vue'

describe('message parts', () => {
  it('renders image attachments with accessible lazy-loaded images', () => {
    const wrapper = mount(MessageAttachments, {
      props: { files: [{ name: 'preview.png', preview: '/preview.png' }] }
    })

    const image = wrapper.get('img')
    expect(image.attributes()).toMatchObject({
      src: '/preview.png',
      alt: 'preview.png',
      loading: 'lazy',
      decoding: 'async',
      width: '200',
      height: '150'
    })
    expect(wrapper.text()).toContain('preview.png')
  })

  it('loads a thumbnail first and exposes the original image on demand', () => {
    const wrapper = mount(MessageAttachments, {
      props: {
        files: [{ name: 'large.png', thumbnail: 'data:image/webp;base64,thumb', originalUrl: '/original.png' }]
      }
    })

    expect(wrapper.get('img').attributes('src')).toBe('data:image/webp;base64,thumb')
    expect(wrapper.get('a').attributes('href')).toBe('/original.png')
  })

  it('shows a stable fallback when an attachment URL is missing', () => {
    const wrapper = mount(MessageAttachments, { props: { files: [{ name: 'missing.png' }] } })

    expect(wrapper.find('img').exists()).toBe(false)
    expect(wrapper.text()).toContain('图片预览不可用')
  })

  it('defers an original-only image until the user opens its link', () => {
    const wrapper = mount(MessageAttachments, {
      props: { files: [{ name: 'original.png', originalUrl: '/original.png' }] }
    })

    expect(wrapper.find('img').exists()).toBe(false)
    expect(wrapper.get('a').attributes('href')).toBe('/original.png')
    expect(wrapper.text()).toContain('图片预览不可用')
  })

  it('reuses the prepared thumbnail in the composer preview', () => {
    const objectUrlSpy = vi.spyOn(URL, 'createObjectURL')
    const wrapper = mount(FilePreview, {
      props: {
        file: {
          name: 'prepared.png',
          type: 'image/png',
          size: 100,
          thumbnail: 'data:image/webp;base64,prepared'
        }
      }
    })

    expect(wrapper.get('img').attributes()).toMatchObject({
      src: 'data:image/webp;base64,prepared',
      decoding: 'async',
      width: '40',
      height: '40'
    })
    expect(objectUrlSpy).not.toHaveBeenCalled()
    objectUrlSpy.mockRestore()
  })

  it('renders grouped thinking with the supplied markdown renderer', () => {
    const renderMarkdown = vi.fn(content => `<p>${content}</p>`)
    const wrapper = mount(MessageThinking, {
      props: {
        message: {
          reasoning: 'combined',
          thinkingGroups: { Planner: { model: 'model-a', content: 'plan' } },
          isStreaming: false
        },
        renderMarkdown
      }
    })

    expect(wrapper.text()).toContain('Planner 思考过程')
    expect(wrapper.text()).toContain('(model-a)')
    expect(wrapper.html()).toContain('<p>plan</p>')
    expect(renderMarkdown).toHaveBeenCalledWith('plan')
  })

  it('keeps legacy reasoning content compatible', () => {
    const wrapper = mount(MessageThinking, {
      props: {
        message: { reasoning: 'legacy reasoning', isStreaming: true },
        renderMarkdown: content => `<p>${content}</p>`
      }
    })

    expect(wrapper.text()).toContain('正在思考...')
    expect(wrapper.html()).toContain('<p>legacy reasoning</p>')
  })

  it('renders message items with stable accessibility labels', () => {
    const wrapper = mount(MessageList, {
      props: {
        startIndex: 20,
        messages: [
          { id: 'user-message', prompt: 'hello' },
          { id: 'stream-message', isStreaming: true }
        ]
      },
      slots: {
        default: '<span class="slot-content">message</span>'
      }
    })

    const items = wrapper.findAll('article')
    expect(items).toHaveLength(2)
    expect(items[0].attributes('aria-label')).toBe('用户消息')
    expect(items[1].attributes('aria-label')).toBe('AI 正在回复中')
  })
})
