import { describe, expect, it, vi } from 'vitest'
import { createProjectClient } from './project'

describe('project model context client', () => {
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

describe('project lifecycle client', () => {
  it('archives, restores and updates project lifecycle state', async () => {
    const baseClient = {
      post: vi.fn().mockResolvedValue({ ok: true, json: vi.fn().mockResolvedValue({ lifecycle_status: 'archived' }) }),
      delete: vi.fn().mockResolvedValue({ ok: true, json: vi.fn().mockResolvedValue({ pinned: false }) })
    }
    const client = createProjectClient(baseClient)
    await expect(client.archiveProject('session/1')).resolves.toEqual({ lifecycle_status: 'archived' })
    await expect(client.restoreProject('session/1')).resolves.toEqual({ lifecycle_status: 'archived' })
    await client.pinProject('session/1')
    await client.unpinProject('session/1')
    expect(baseClient.post).toHaveBeenCalledWith('/agent/projects/session%2F1/archive')
    expect(baseClient.post).toHaveBeenCalledWith('/agent/projects/session%2F1/restore')
    expect(baseClient.post).toHaveBeenCalledWith('/agent/projects/session%2F1/pin')
    expect(baseClient.delete).toHaveBeenCalledWith('/agent/projects/session%2F1/pin')
  })

  it('lists project sessions with lifecycle metadata', async () => {
    const baseClient = {
      get: vi.fn().mockResolvedValue({
        ok: true,
        json: vi.fn().mockResolvedValue({ sessions: [{ session_id: 'session-1', lifecycle_status: 'archived', pinned: false }] })
      })
    }
    const client = createProjectClient(baseClient)
    await expect(client.listProjectSessions()).resolves.toEqual({
      sessions: [{ session_id: 'session-1', lifecycle_status: 'archived', pinned: false }]
    })
    expect(baseClient.get).toHaveBeenCalledWith('/agent/sessions', { limit: 50 })
  })
})
