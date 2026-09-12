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
