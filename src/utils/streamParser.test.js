import { describe, expect, it } from 'vitest'
import { consumeJsonStream } from './streamParser'

function responseFromChunks(chunks) {
  const encoded = chunks.map(chunk => new TextEncoder().encode(chunk))
  let index = 0
  return {
    body: {
      getReader() {
        return {
          async read() {
            if (index >= encoded.length) return { done: true, value: undefined }
            return { done: false, value: encoded[index++] }
          }
        }
      }
    }
  }
}

describe('consumeJsonStream', () => {
  it('reassembles JSON split across chunks and supports SSE records', async () => {
    const records = []
    await consumeJsonStream(responseFromChunks(['data: {"a":', '1}\n\ndata: {"b":2}\n']), data => {
      records.push(data)
    })

    expect(records).toEqual([{ a: 1 }, { b: 2 }])
  })

  it('flushes the final record without a trailing newline', async () => {
    const records = []
    await consumeJsonStream(responseFromChunks(['{"done":', 'true}']), data => {
      records.push(data)
    })

    expect(records).toEqual([{ done: true }])
  })
})
