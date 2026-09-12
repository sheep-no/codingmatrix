import { describe, expect, it } from 'vitest'
import { reactive } from 'vue'
import { cloneForIndexedDb } from './cloneForIndexedDb'

describe('cloneForIndexedDb', () => {
  it('turns vue proxies into plain objects that structured clone can store', () => {
    const messages = reactive([{
      prompt: 'hello',
      retryRequest: { prompt: 'hello' },
      requestError: Object.assign(new Error('timeout'), { status: 503, retryable: true }),
      skip: () => {}
    }])

    const cloned = cloneForIndexedDb(messages)
    expect(cloned).toEqual([{
      prompt: 'hello',
      retryRequest: { prompt: 'hello' },
      requestError: {
        name: 'Error',
        message: 'timeout',
        status: 503,
        retryable: true
      }
    }])
    expect(structuredClone(cloned)).toEqual(cloned)
  })
})
