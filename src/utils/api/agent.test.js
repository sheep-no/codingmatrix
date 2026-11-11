import { describe, expect, it, vi } from 'vitest'

import { createAgentClient } from './agent'

describe('agent 客户端契约（FRESCAN-57/58）', () => {
  it('快照回滚把标签作为字符串写入 target_tag', async () => {
    const baseClient = {
      post: vi.fn().mockResolvedValue({ ok: true, json: async () => ({ success: true }) })
    }

    await createAgentClient(baseClient).rollbackToSnapshot('session-1', 'snapshot-v2')

    expect(baseClient.post).toHaveBeenCalledWith(
      '/agent/rollback/session-1?target_tag=snapshot-v2'
    )
  })

  it('回滚可显式关闭分支删除', async () => {
    const baseClient = {
      post: vi.fn().mockResolvedValue({ ok: true, json: async () => ({ success: true }) })
    }

    await createAgentClient(baseClient).rollbackToSnapshot('session-1', 'snapshot-v2', {
      deleteBranch: false
    })

    expect(baseClient.post).toHaveBeenCalledWith(
      '/agent/rollback/session-1?target_tag=snapshot-v2&delete_branch=false'
    )
  })

  it('知识检索使用 q 参数并归一为 results 数组', async () => {
    const baseClient = {
      get: vi.fn().mockResolvedValue({ ok: true, json: async () => [{ id: 1 }] })
    }

    const result = await createAgentClient(baseClient).searchKnowledge('检索词')

    expect(baseClient.get).toHaveBeenCalledWith('/agent/knowledge/search', { q: '检索词' })
    expect(result).toEqual({ results: [{ id: 1 }] })
  })
})
