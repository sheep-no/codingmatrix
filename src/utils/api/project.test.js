import { describe, expect, it, vi } from 'vitest'
import { createProjectClient } from './project'

describe('project model context client', () => {
  it('controls project lifecycle and retention protection', async () => {
    const baseClient = {
      post: vi.fn().mockResolvedValue({
        ok: true,
        json: vi.fn().mockResolvedValue({ session_id: 'project-1', lifecycle_status: 'archived' })
      }),
      delete: vi.fn().mockResolvedValue({
        ok: true,
        json: vi.fn().mockResolvedValue({ session_id: 'project-1', pinned: false })
      })
    }
    const client = createProjectClient(baseClient)

    await expect(client.archiveProject('project-1')).resolves.toEqual({
      session_id: 'project-1', lifecycle_status: 'archived'
    })
    await expect(client.restoreProject('project-1')).resolves.toEqual({
      session_id: 'project-1', lifecycle_status: 'archived'
    })
    await expect(client.pinProject('project-1')).resolves.toEqual({
      session_id: 'project-1', lifecycle_status: 'archived'
    })
    await expect(client.unpinProject('project-1')).resolves.toEqual({
      session_id: 'project-1', pinned: false
    })

    expect(baseClient.post).toHaveBeenNthCalledWith(1, '/agent/projects/project-1/archive')
    expect(baseClient.post).toHaveBeenNthCalledWith(2, '/agent/projects/project-1/restore')
    expect(baseClient.post).toHaveBeenNthCalledWith(3, '/agent/projects/project-1/pin')
    expect(baseClient.delete).toHaveBeenCalledWith('/agent/projects/project-1/pin')
  })

  it('reclaims a hosted project immediately', async () => {
    const baseClient = {
      delete: vi.fn().mockResolvedValue({
        ok: true,
        json: vi.fn().mockResolvedValue({ session_id: 'project-1', status: 'deleted' })
      })
    }
    const client = createProjectClient(baseClient)

    await expect(client.reclaimProject('project-1')).resolves.toEqual({
      session_id: 'project-1', status: 'deleted'
    })
    expect(baseClient.delete).toHaveBeenCalledWith('/agent/projects/project-1')
  })

  it('keeps reclaim errors distinguishable for 404 and 409', async () => {
    const missing = createProjectClient({
      delete: vi.fn().mockResolvedValue({ ok: false, status: 404 })
    })
    await expect(missing.reclaimProject('gone')).rejects.toMatchObject({
      message: '项目不存在',
      status: 404
    })

    const busy = createProjectClient({
      delete: vi.fn().mockResolvedValue({ ok: false, status: 409 })
    })
    await expect(busy.reclaimProject('busy')).rejects.toMatchObject({
      message: '删除项目失败',
      status: 409
    })
  })

  it('reads and updates session model context', async () => {
    const context = { current_model: 'model-a', expected_revision: 3 }
    const baseClient = {
      get: vi.fn().mockResolvedValue({
        ok: true,
        json: vi.fn().mockResolvedValue({ found: true, revision: 3, context })
      }),
      put: vi.fn().mockResolvedValue({
        ok: true,
        json: vi.fn().mockResolvedValue({ found: true, revision: 4, context })
      })
    }
    const client = createProjectClient(baseClient)

    await expect(client.getAgentModelContext('session-1')).resolves.toEqual({ found: true, revision: 3, context })
    await expect(client.updateAgentModelContext('session-1', context)).resolves.toEqual({ found: true, revision: 4, context })
    expect(baseClient.get).toHaveBeenCalledWith('/agent/sessions/session-1/model-context')
    expect(baseClient.put).toHaveBeenCalledWith('/agent/sessions/session-1/model-context', context)
  })

  it('reports a revision conflict for the caller to reconcile', async () => {
    const baseClient = {
      put: vi.fn().mockResolvedValue({ ok: false, status: 409 })
    }
    const client = createProjectClient(baseClient)

    await expect(client.updateAgentModelContext('session-1', {
      expected_revision: 2
    })).resolves.toEqual({ conflict: true })
  })
})

describe('project deletion client', () => {
  it('permanently deletes a generated project', async () => {
    const baseClient = {
      delete: vi.fn().mockResolvedValue({
        ok: true,
        json: vi.fn().mockResolvedValue({ session_id: 'session/1', status: 'deleted' })
      })
    }
    const client = createProjectClient(baseClient)
    await expect(client.permanentlyDeleteProject('session/1')).resolves.toEqual({
      session_id: 'session/1',
      status: 'deleted'
    })
    expect(baseClient.delete).toHaveBeenCalledWith('/agent/projects/session%2F1')
  })

  it('exposes the backend deletion error and status', async () => {
    const baseClient = {
      delete: vi.fn().mockResolvedValue({
        ok: false,
        status: 409,
        json: vi.fn().mockResolvedValue({ detail: '项目仍有活动任务，暂时无法删除' })
      })
    }
    const client = createProjectClient(baseClient)

    await expect(client.permanentlyDeleteProject('session-1')).rejects.toMatchObject({
      message: '项目仍有活动任务，暂时无法删除',
      status: 409
    })
  })
})
