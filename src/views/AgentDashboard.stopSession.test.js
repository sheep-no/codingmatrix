import { createPinia, setActivePinia } from 'pinia'
import { shallowMount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

// 受控的生成文件，使 doStopSession 进入「有文件」分支
vi.mock('@/composables/useAgentFiles', () => ({
  useAgentFiles: () => ({
    generatedFiles: [{ path: 'main.py', name: 'main.py' }],
    selectedFile: null,
    fileDiffs: {},
    fileVersions: {},
    fileSearchQuery: '',
    fileCategories: {},
    clearAll: vi.fn(),
    downloadFile: vi.fn(),
    restoreVersion: vi.fn(),
    rollback: vi.fn(),
    selectFile: vi.fn(),
    toggleCategory: vi.fn(),
    getHighlightedCode: vi.fn(() => ''),
    hasFileDiff: vi.fn(() => false),
    getLineCount: vi.fn(() => 0),
    formatFileSize: vi.fn(() => '0 B'),
    getLanguage: vi.fn(() => 'plaintext')
  })
}))

const confirmMock = vi.fn()
vi.mock('element-plus', async (importOriginal) => {
  const actual = await importOriginal()
  return {
    ...actual,
    ElMessageBox: { ...actual.ElMessageBox, confirm: (...args) => confirmMock(...args) }
  }
})

import { ElMessage } from 'element-plus'
import AgentDashboard from './AgentDashboard.vue'
import { useAgentSessionStore } from '@/stores/agentSession'

let wrapper

const AgentSidebarStub = {
  inheritAttrs: false,
  template: '<aside class="agent-sidebar" v-bind="$attrs" />'
}

function mountAgentDashboard() {
  window.api = {
    getRecommendedConcurrentLimits: vi.fn().mockResolvedValue({}),
    getCacheStats: vi.fn().mockResolvedValue({}),
    getLearningStats: vi.fn().mockResolvedValue({}),
    listSkills: vi.fn().mockResolvedValue([]),
    listAgentHostSessions: vi.fn().mockResolvedValue([]),
    get: vi.fn().mockResolvedValue({ ok: true, json: async () => ({ providers: [] }) }),
    reclaimProject: vi.fn().mockResolvedValue({}),
    downloadProject: vi.fn(),
    stopSession: vi.fn().mockResolvedValue({})
  }

  return shallowMount(AgentDashboard, {
    attachTo: document.body,
    global: {
      plugins: [createPinia()],
      stubs: {
        AgentSidebar: AgentSidebarStub,
        AgentFilePanel: { template: '<aside class="agent-file-panel" />' },
        AgentTopBar: { template: '<header class="agent-topbar" />' },
        AgentWorkspace: { template: '<section class="agent-workspace" />' },
        AgentInputBar: { template: '<div class="agent-input-bar" />' },
        UploadModal: true,
        SettingsModal: true,
        LearningModal: true,
        PerformanceModal: true,
        VersionHistoryModal: true,
        DiffModal: true
      },
      mocks: { $router: { push: vi.fn() } }
    }
  })
}

describe('Agent Dashboard 结束会话与下载', () => {
  beforeEach(() => {
    localStorage.clear()
    setActivePinia(createPinia())
    confirmMock.mockReset()
    vi.spyOn(ElMessage, 'error').mockImplementation(() => {})
    vi.spyOn(ElMessage, 'warning').mockImplementation(() => {})
  })

  afterEach(() => {
    wrapper?.unmount()
    wrapper = null
    vi.restoreAllMocks()
  })

  it('下载失败时不结束会话，保留项目文件', async () => {
    wrapper = mountAgentDashboard()
    const store = useAgentSessionStore()
    store.currentSessionId = 'sess-1'
    wrapper.vm.workspace.currentProjectPath = 'projects/sess-1'
    confirmMock.mockResolvedValue()
    window.api.downloadProject.mockRejectedValue(new Error('network down'))

    await wrapper.vm.doStopSession()

    expect(window.api.downloadProject).toHaveBeenCalledTimes(1)
    expect(window.api.stopSession).not.toHaveBeenCalled()
    expect(ElMessage.error).toHaveBeenCalledWith('下载失败，已取消结束会话以保留项目文件')
  })

  it('下载成功后正常结束会话', async () => {
    wrapper = mountAgentDashboard()
    const store = useAgentSessionStore()
    store.currentSessionId = 'sess-1'
    wrapper.vm.workspace.currentProjectPath = 'projects/sess-1'
    confirmMock.mockResolvedValue()
    window.api.downloadProject.mockResolvedValue()

    await wrapper.vm.doStopSession()

    expect(window.api.downloadProject).toHaveBeenCalledTimes(1)
    expect(window.api.stopSession).toHaveBeenCalledWith('sess-1')
  })
})
