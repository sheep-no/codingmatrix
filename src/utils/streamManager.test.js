import { beforeEach, describe, expect, it } from 'vitest'
import { streamManager } from './streamManager'

describe('streamManager persisted state', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('removes credentials from recoverable request state', () => {
    streamManager.saveStreamRequestState(
      {
        prompt: 'test',
        api_key_token: 'secret-token',
        nested: { authorization: 'Bearer secret', safe: true }
      },
      { api_key: 'provider-key', content: 'safe' },
      42
    )

    const state = JSON.parse(localStorage.getItem('streamRequestState'))

    expect(state.requestData).toEqual({ prompt: 'test', nested: { safe: true } })
    expect(state.messageData).toEqual({ content: 'safe' })
  })
})
