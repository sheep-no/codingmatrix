import { createPinia, setActivePinia } from 'pinia'
import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { apiMock } = vi.hoisted(() => ({
  apiMock: {
    getProjectFiles: vi.fn().mockResolvedValue({ files: [{ path: 'src/a.py', name: 'a.py' }] }),
    readProjectFile: vi.fn().mockResolvedValue({ content: 'print(1)' }),
    deleteProjectFile: vi.fn().mockResolvedValue({ success: true }),
    getSnapshotDiff: vi.fn().mockResolvedValue({ diff: 'x' }),
    getSnapshots: vi.fn().mockResolvedValue({ snapshots: [] }),
    rollbackToSnapshot: vi.fn().mockResolvedValue({}),
    downloadProject: vi.fn(),
    listKnowledge: vi.fn().mockResolvedValue({ items: [] }),
    searchKnowledge: vi.fn().mockResolvedValue({ results: [] }),
    addKnowledge: vi.fn().mockResolvedValue({})
  }
}))

vi.mock('@/utils/api/index', () => ({ api: apiMock }))
vi.mock('@/utils/api/project', () => ({ createProjectClient: () => ({}) }))
vi.mock('@/utils/streamParser', () => ({ consumeJsonStream: vi.fn() }))
vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn() }) }))
vi.mock('element-plus', async (importOriginal) => {
  const actual = await importOriginal()
  return {
    ...actual,
    ElMessage: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
    ElMessageBox: { ...actual.ElMessageBox, confirm: vi.fn().mockResolvedValue('confirm') }
  }
})

import ProjectGenerator from './ProjectGenerator.vue'

function mountGenerator() {
  localStorage.setItem(
    'project_generator_state',
    JSON.stringify({
      form: { requirement: 'demo', sessionId: 'sess_1' },
      outputDir: 'projects/1/demo',
      generationComplete: true
    })
  )
  return mount(ProjectGenerator, {
    props: { visible: true },
    global: { stubs: { FilePreviewPanel: true } }
  })
}

describe('ProjectGenerator 后端契约对齐', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    vi.clearAllMocks()
  })

  it('项目文件列表/读取/删除携带 project_path', async () => {
    const wrapper = mountGenerator()

    await wrapper.vm.loadProjectFiles()
    expect(apiMock.getProjectFiles).toHaveBeenCalledWith({ project_path: 'projects/1/demo' })

    await wrapper.vm.onSelectProjectFile('src/a.py')
    expect(apiMock.readProjectFile).toHaveBeenCalledWith({
      project_path: 'projects/1/demo',
      file_path: 'src/a.py'
    })

    await wrapper.vm.onDeleteFile('src/a.py')
    expect(apiMock.deleteProjectFile).toHaveBeenCalledWith({
      project_path: 'projects/1/demo',
      file_path: 'src/a.py'
    })
  })

  it('快照对比把 sessionId 作为第一个参数传递', async () => {
    const wrapper = mountGenerator()

    await wrapper.vm.compareSnapshots('v1', 'v2')
    expect(apiMock.getSnapshotDiff).toHaveBeenCalledWith('sess_1', 'v1', 'v2')
  })
})
