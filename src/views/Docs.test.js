import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it } from 'vitest'
import Docs from './Docs.vue'

function mountDocs() {
  return mount(Docs, {
    global: {
      stubs: {
        'router-link': { template: '<a href="/"><slot /></a>' }
      }
    }
  })
}

describe('Docs workbench guide', () => {
  beforeEach(() => {
    global.IntersectionObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    }
  })

  it('keeps unique section ids for every sidebar link', () => {
    const wrapper = mountDocs()
    const hrefs = wrapper.findAll('.aside-link').map((link) => link.attributes('href').slice(1))
    const sectionIds = wrapper.findAll('section.section').map((section) => section.attributes('id'))

    expect(hrefs.length).toBeGreaterThan(0)
    expect(new Set(sectionIds).size).toBe(sectionIds.length)
    hrefs.forEach((id) => expect(sectionIds).toContain(id))
  })

  it('describes the current workbench instead of the old agent brochure', () => {
    const wrapper = mountDocs()
    const text = wrapper.text()

    expect(text).toContain('智能工作台')
    expect(text).toContain('硅基流动')
    expect(text).toContain('按需联网')
    expect(text).toContain('PPT 生成')
    expect(text).toContain('虚拟姬')
    expect(text).toContain('Kolors')
    expect(text.includes('Architect Agent')).toBe(false)
    expect(text.includes('GirlAI')).toBe(false)
  })
})
