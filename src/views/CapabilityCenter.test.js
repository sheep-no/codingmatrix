import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMock = vi.hoisted(() => ({
  listSkills: vi.fn(),
  uploadSkill: vi.fn(),
  deleteSkill: vi.fn(),
  listAgentHostSessions: vi.fn(),
  listKnowledgeDocs: vi.fn(),
  listUploadedProjects: vi.fn(),
  analyzeImage: vi.fn()
}))

vi.mock('@/utils/api/index', () => ({ api: apiMock }))

import CapabilityCenter from './CapabilityCenter.vue'

function mountCapabilityCenter() {
  return mount(CapabilityCenter, {
    global: {
      mocks: { $router: { push: vi.fn() } }
    }
  })
}

async function openTab(wrapper, label) {
  const button = wrapper.findAll('[role="tab"]').find(tab => tab.get('span').text() === label)
  await button.trigger('click')
  await flushPromises()
}

describe('CapabilityCenter', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiMock.listSkills.mockResolvedValue([])
    apiMock.listAgentHostSessions.mockResolvedValue([])
    apiMock.listKnowledgeDocs.mockResolvedValue([])
    apiMock.listUploadedProjects.mockResolvedValue([])
    apiMock.deleteSkill.mockResolvedValue(undefined)
  })

  it('loads an inactive tab on first entry and caches its result', async () => {
    const wrapper = mountCapabilityCenter()

    expect(apiMock.listSkills).not.toHaveBeenCalled()
    await openTab(wrapper, 'Skills')
    expect(apiMock.listSkills).toHaveBeenCalledOnce()
    expect(wrapper.text()).toContain('暂无 Skills')

    await openTab(wrapper, '视觉工具')
    await openTab(wrapper, 'Skills')
    expect(apiMock.listSkills).toHaveBeenCalledOnce()
  })

  it('shows a panel error and retries the failed request', async () => {
    apiMock.listSkills
      .mockRejectedValueOnce(new Error('服务暂不可用'))
      .mockResolvedValueOnce([{ name: 'review', category: 'workflow' }])
    const wrapper = mountCapabilityCenter()

    await openTab(wrapper, 'Skills')
    expect(wrapper.text()).toContain('服务暂不可用')

    await wrapper.get('.state-action').trigger('click')
    await flushPromises()
    expect(apiMock.listSkills).toHaveBeenCalledTimes(2)
    expect(wrapper.text()).toContain('review · workflow')
  })

  it('requires confirmation before deleting a skill', async () => {
    apiMock.listSkills.mockResolvedValue([{ name: 'review', category: 'workflow' }])
    const confirm = vi.spyOn(window, 'confirm').mockReturnValueOnce(false).mockReturnValueOnce(true)
    const wrapper = mountCapabilityCenter()

    await openTab(wrapper, 'Skills')
    const deleteButton = wrapper.findAll('button').find(button => button.text() === '删除')
    await deleteButton.trigger('click')
    expect(apiMock.deleteSkill).not.toHaveBeenCalled()

    await deleteButton.trigger('click')
    await flushPromises()
    expect(apiMock.deleteSkill).toHaveBeenCalledWith('review')
    expect(apiMock.listSkills).toHaveBeenCalledTimes(2)
    confirm.mockRestore()
  })

  it('supports keyboard tab navigation and associates the selected panel', async () => {
    const wrapper = mountCapabilityCenter()
    await wrapper.get('#tab-vision').trigger('keydown', { key: 'ArrowDown' })
    await flushPromises()
    expect(wrapper.get('#tab-knowledge').attributes('aria-selected')).toBe('true')
    expect(wrapper.get('#tab-knowledge').attributes('tabindex')).toBe('0')
    expect(wrapper.get('#tab-vision').attributes('tabindex')).toBe('-1')
    expect(wrapper.get('[role="tabpanel"]').attributes('aria-labelledby')).toBe('tab-knowledge')
    expect(apiMock.listKnowledgeDocs).toHaveBeenCalledOnce()
    await wrapper.get('#tab-knowledge').trigger('keydown', { key: 'End' })
    expect(wrapper.get('#tab-projects').attributes('aria-selected')).toBe('true')
    await wrapper.get('#tab-projects').trigger('keydown', { key: 'ArrowDown' })
    expect(wrapper.get('#tab-vision').attributes('aria-selected')).toBe('true')
    wrapper.unmount()
  })

  it('shows the selected filename and prevents concurrent image operations', async () => {
    let finish
    apiMock.analyzeImage.mockReturnValue(new Promise(resolve => { finish = resolve }))
    const wrapper = mountCapabilityCenter()
    const file = new File(['fixture'], 'layout.png', { type: 'image/png' })
    const input = wrapper.get('input[type="file"]')
    Object.defineProperty(input.element, 'files', { value: [file] })
    await input.trigger('change')
    expect(wrapper.get('.drop-zone').text()).toContain('layout.png')
    await wrapper.get('.actions button').trigger('click')
    expect(apiMock.analyzeImage).toHaveBeenCalledOnce()
    expect(wrapper.findAll('.actions button').every(button => button.element.disabled)).toBe(true)
    finish({ description: '图片处理完成' })
    await flushPromises()
    expect(wrapper.get('pre').text()).toContain('图片处理完成')
    expect(wrapper.get('.actions button').element.disabled).toBe(false)
    wrapper.unmount()
  })
})
