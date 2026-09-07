import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMock = vi.hoisted(() => ({
  listSkills: vi.fn(),
  uploadSkill: vi.fn(),
  deleteSkill: vi.fn(),
  listAgentHostSessions: vi.fn(),
  listKnowledgeDocs: vi.fn(),
  listUploadedProjects: vi.fn()
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
  const button = wrapper.findAll('[role="tab"]').find(tab => tab.text() === label)
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
})
