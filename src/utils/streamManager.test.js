import { beforeEach, describe, expect, it } from 'vitest'
import { streamManager } from './streamManager'

describe('streamManager persisted state', () => {
  beforeEach(() => {
    localStorage.clear()
    streamManager.cleanup()
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

  it('keeps recoverable state when aborting controllers or persisting cleanup', () => {
    streamManager.saveStreamRequestState({ prompt: 'keep' }, { prompt: 'keep' }, 'temp_1')
    streamManager.createAbortController('req_keep')
    streamManager.abortActiveControllers()
    expect(streamManager.getStreamRequestState()?.requestData).toEqual({ prompt: 'keep' })

    streamManager.cleanup({ persistStream: true })
    expect(streamManager.getStreamRequestState()?.isStreaming).toBe(true)
  })

  it('still restores stream state after five minutes', () => {
    streamManager.saveStreamRequestState({ prompt: 'long' }, { prompt: 'long' }, 7)
    const raw = JSON.parse(localStorage.getItem('streamRequestState'))
    raw.timestamp = Date.now() - 6 * 60 * 1000
    localStorage.setItem('streamRequestState', JSON.stringify(raw))
    expect(streamManager.getStreamRequestState()?.requestData.prompt).toBe('long')
  })
})
