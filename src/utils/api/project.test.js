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
