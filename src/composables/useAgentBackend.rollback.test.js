import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), error: vi.fn() },
  ElMessageBox: { confirm: vi.fn() }
}))

import { useAgentBackend } from './useAgentBackend'

function createBackend(projectApi) {
  return useAgentBackend(
    projectApi,
    { addLog: vi.fn() },
    { generatedFiles: { value: [] }, selectedFile: { value: null } },
    { workflowStages: { value: [] } }
  )
}

describe('useAgentBackend 快照回滚（FRESCAN-58）', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('把字符串标签传给客户端并关闭分支删除', async () => {
    const projectApi = {
      rollbackToSnapshot: vi.fn().mockResolvedValue({ success: true }),
      getSnapshots: vi.fn().mockResolvedValue({ snapshots: [] })
    }

    await createBackend(projectApi).rollbackToSnapshot('snapshot-v2', 'session-1')

    expect(projectApi.rollbackToSnapshot).toHaveBeenCalledWith(
      'session-1',
      'snapshot-v2',
      { deleteBranch: false }
    )
  })
})
