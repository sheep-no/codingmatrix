import { describe, expect, it, vi } from 'vitest'

import { createGirlClient } from './girl'


describe('GirlAI client', () => {
  it('sends history deletion parameters in the query string', async () => {
    const response = {
      ok: true,
      json: vi.fn().mockResolvedValue({ status: 'deleted', count: 2 })
    }
    const baseClient = {
      delete: vi.fn().mockResolvedValue(response)
    }
    const client = createGirlClient(baseClient)

    const result = await client.deleteGirlAiHistory(['first', 'second'], false)

    expect(result).toEqual({ status: 'deleted', count: 2 })
    expect(baseClient.delete).toHaveBeenCalledWith(
      '/GirlAi/history?all=false&record_ids=first&record_ids=second'
    )
  })

  it('supports clearing all history without record ids', async () => {
    const baseClient = {
      delete: vi.fn().mockResolvedValue({
        ok: true,
        json: vi.fn().mockResolvedValue({ status: 'deleted', count: 4 })
      })
    }

    await createGirlClient(baseClient).deleteGirlAiHistory([], true)

    expect(baseClient.delete).toHaveBeenCalledWith('/GirlAi/history?all=true')
  })

  it('preserves HTTP status when a request fails', async () => {
    const baseClient = {
      get: vi.fn().mockResolvedValue({
        ok: false,
        status: 503,
        text: vi.fn().mockResolvedValue('{"detail":"temporarily unavailable"}')
      })
    }

    await expect(createGirlClient(baseClient).getCustomCharacters()).rejects.toMatchObject({
      name: 'ApiError',
      status: 503,
      detail: 'temporarily unavailable'
    })
  })

  it('returns an empty list for a successful empty response', async () => {
    const baseClient = {
      get: vi.fn().mockResolvedValue({
        ok: true,
        status: 204,
        text: vi.fn()
      })
    }

    await expect(createGirlClient(baseClient).getCustomCharacters()).resolves.toEqual({
      characters: []
    })
  })
})
