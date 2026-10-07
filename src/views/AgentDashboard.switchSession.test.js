import { createPinia, setActivePinia } from 'pinia'
import * as ElMessageModule from 'element-plus'
import { flushPromises, shallowMount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

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

// session 包装层用 spy 验证「切换前保存」的调用顺序；
// 保存/恢复的具体语义由 stores/agentSession.test.js 与 store 自身测试覆盖
const sessionMock = {
  currentSessionId: 'sess-old',
  projectPrompt: '',
  sessionHistory: [],
  saveSessionState: vi.fn(() => true),
  restoreSessionState: vi.fn(() => null),
  clearSessionState: vi.fn(),
  loadSessionHistory: vi.fn(),
  createNewSession: vi.fn(),
  switchSession: vi.fn(() => true),
  deleteSession: vi.fn(),
  startAutoSave: vi.fn(),
  stopAutoSave: vi.fn(),
  MAX_LOG_ENTRIES: 100,
  MAX_THINKING_ENTRIES: 50,
  MAX_HISTORY_ENTRIES: 10
}
vi.mock('@/composables/useAgentSession', () => ({
  useAgentSession: () => sessionMock
}))

import AgentDashboard from './AgentDashboard.vue'

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
    stopSession: vi.fn().mockResolvedValue({}),
    getAgentModelContext: vi.fn().mockResolvedValue({ context: {}, revision: null })
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

describe('Agent Dashboard 会话切换前保存', () => {
  beforeEach(() => {
    localStorage.clear()
    setActivePinia(createPinia())
    sessionMock.saveSessionState.mockClear()
    sessionMock.switchSession.mockClear()
    sessionMock.currentSessionId = 'sess-old'
    vi.spyOn(ElMessageModule.ElMessage, 'error').mockImplementation(() => {})
    vi.spyOn(ElMessageModule.ElMessage, 'warning').mockImplementation(() => {})
    vi.spyOn(ElMessageModule.ElMessage, 'success').mockImplementation(() => {})
  })

  afterEach(() => {
    wrapper?.unmount()
    wrapper = null
    vi.restoreAllMocks()
  })

  it('切换会话时先落盘旧会话再执行切换', async () => {
    wrapper = mountAgentDashboard()
    await flushPromises()

    await wrapper.vm.doSwitchSession('sess-target')

    expect(sessionMock.saveSessionState).toHaveBeenCalledTimes(1)
    expect(sessionMock.switchSession).toHaveBeenCalledTimes(1)
    const saveOrder = sessionMock.saveSessionState.mock.invocationCallOrder[0]
    const switchOrder = sessionMock.switchSession.mock.invocationCallOrder[0]
    expect(saveOrder).toBeLessThan(switchOrder)
    // 保存与切换使用同一份完整快照（含 store 引用，供 context 回写）
    const savedSnapshot = sessionMock.saveSessionState.mock.calls[0][0]
    const switchSnapshot = sessionMock.switchSession.mock.calls[0][1]
    // 同一同步块内两次构建的瞬时快照内容一致（保存旧态、切换注入同态）
    expect(savedSnapshot).toEqual(switchSnapshot)
    expect(switchSnapshot._generation).toBeDefined()
    expect(switchSnapshot.workflowStages).toEqual(savedSnapshot.workflowStages)
  })

  it('当前无活动会话时直接切换，不调用保存', async () => {
    wrapper = mountAgentDashboard()
    await flushPromises()
    sessionMock.currentSessionId = null

    await wrapper.vm.doSwitchSession('sess-target')

    expect(sessionMock.saveSessionState).not.toHaveBeenCalled()
    expect(sessionMock.switchSession).toHaveBeenCalledTimes(1)
    expect(sessionMock.switchSession.mock.calls[0][0]).toBe('sess-target')
  })

  it('切换目标不存在时不改写会话状态', async () => {
    wrapper = mountAgentDashboard()
    await flushPromises()
    sessionMock.switchSession.mockReturnValueOnce(false)

    const result = await wrapper.vm.doSwitchSession('missing')

    expect(result).toBe(false)
    expect(sessionMock.saveSessionState).toHaveBeenCalledTimes(1)
  })
})
